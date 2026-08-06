#!/usr/bin/env python3
"""Drive multi-turn evaluation cases against a running ADK server.

`agents-cli eval generate` accepts a single `prompt` per case, or a prefilled
`agent_data` whose turns end with a user message. Neither shape drives a
conversation, and a multi-turn case is only meaningful if the turns actually
run in order against one session — the third turn's correctness depends on
what the agent did in the first two.

This script sends each turn, collects the events the server emits, and writes
a traces file in the same shape `eval generate` produces, so
`agents-cli eval grade` consumes it unchanged.

Usage:
    python3 tests/eval/run_multi_turn.py \
        --dataset tests/eval/datasets/eval-multi-turn.json \
        --url http://127.0.0.1:8765 --app-name agent \
        --out artifacts/traces/multi_turn.json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


AGENT_ID = "elevate_supervisor_agent"


def post(url: str, payload: dict, timeout: int = 300):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
    return json.loads(body) if body.strip() else None


def run_case(base: str, app: str, case: dict) -> dict:
    user = (case.get("context") or {}).get("employee_id", "EMP-1002")
    session_id = f"eval-{case['eval_case_id']}"
    post(f"{base}/apps/{app}/users/{user}/sessions/{session_id}", {"state": {}})

    turns = []
    for index, message in enumerate(case["conversation"]):
        text = "".join(p.get("text", "") for p in message.get("parts", []))
        events = post(
            f"{base}/run",
            {
                "appName": app,
                "userId": user,
                "sessionId": session_id,
                "newMessage": {"role": "user", "parts": [{"text": text}]},
            },
        ) or []
        turns.append({
            "turn_index": index,
            "turn_id": f"turn_{index}",
            "events": [
                {"author": "user", "content": {"role": "user", "parts": [{"text": text}]}}
            ] + [
                {"author": e.get("author", "agent"), "content": e.get("content", {})}
                for e in events
                if e.get("content")
            ],
        })

    final = []
    for event in reversed(turns[-1]["events"]):
        parts = (event.get("content") or {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if p.get("text"))
        if text and event.get("author") != "user":
            final = [{"text": text}]
            break

    trace = {k: case[k] for k in ("eval_case_id", "tags", "rubric_groups") if k in case}
    trace["prompt"] = case["conversation"][0]
    trace["responses"] = [{"response": {"role": "model", "parts": final}}]
    # `agents` is a mapping keyed by agent id, not a list. A list parses as
    # valid JSON and fails schema validation with a message that names the
    # field but not the file, so this is worth getting right at the source.
    trace["agent_data"] = {
        "agents": {
            AGENT_ID: {"agent_id": AGENT_ID, "agent_type": "LlmAgent"},
        },
        "turns": turns,
    }
    trace["reference"] = {"response": {"role": "model", "parts": [{"text": ""}]}}
    return trace


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--app-name", default="agent")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.dataset).read_text())
    cases = data["eval_cases"] if isinstance(data, dict) else data

    traces, failed = [], []
    for case in cases:
        try:
            traces.append(run_case(args.url.rstrip("/"), args.app_name, case))
            print(f"  ok   {case['eval_case_id']}")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            failed.append((case["eval_case_id"], f"{type(exc).__name__}: {exc}"))
            print(f"  FAIL {case['eval_case_id']}: {exc}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"eval_cases": traces}, indent=2) + "\n")
    print(f"\n{len(traces)}/{len(cases)} succeeded -> {out}")
    if failed:
        print("Failed cases are dropped from the artifact, not silently passed:")
        for cid, why in failed:
            print(f"  {cid}: {why}")
        sys.exit(1)


if __name__ == "__main__":
    main()
