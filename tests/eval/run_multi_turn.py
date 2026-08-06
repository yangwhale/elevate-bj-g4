#!/usr/bin/env python3
"""Drive multi-turn evaluation cases and emit traces for `agents-cli eval grade`.

Two reasons this exists rather than `agents-cli eval generate`:

1. `generate` sends one prompt per case. A multi-turn case is only meaningful
   if the turns run in order against one session, because the third turn's
   correctness depends on what the agent did in the first two.
2. The mock backends keep state in module-level stores, so a case that books
   leave changes the balance the next case sees. Running in-process lets the
   harness reset them between cases. Without that the suite is order-dependent
   and its scores are not reproducible, which is worse than a low score.

Usage:
    python3 tests/eval/run_multi_turn.py \
        --dataset tests/eval/datasets/eval-multi-turn.json \
        --out artifacts/traces/multi_turn.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from google.genai import types  # noqa: E402

from agent import config  # noqa: E402
from agent.agent import root_agent  # noqa: E402
from agent.guardrails import ModelArmorGuard  # noqa: E402
from agent.session import ElevateSessionService  # noqa: E402
from agent.tools import serviceimmediately_tool as itsm  # noqa: E402
from agent.tools import workweek_tool as hcm  # noqa: E402

from google.adk.runners import Runner  # noqa: E402

AGENT_ID = root_agent.name


def _part_to_dict(part) -> dict | None:
    if getattr(part, "text", None):
        return {"text": part.text}
    fc = getattr(part, "function_call", None)
    if fc is not None:
        return {"function_call": {"name": fc.name, "args": dict(fc.args or {})}}
    fr = getattr(part, "function_response", None)
    if fr is not None:
        return {"function_response": {"name": fr.name,
                                      "response": json.loads(json.dumps(dict(fr.response or {}), default=str))}}
    return None


async def run_case(case: dict) -> dict:
    hcm.reset_state_for_testing()
    itsm.reset_state_for_testing()

    user = (case.get("context") or {}).get("employee_id", config.DEFAULT_EMPLOYEE_ID)
    session_id = f"eval-{case['eval_case_id']}"

    hcm.set_active_caller_context(user)
    itsm.set_active_caller_context(user)

    session_service = ElevateSessionService()
    runner = Runner(app_name=config.APP_NAME, agent=root_agent,
                    session_service=session_service)
    await session_service.create_session(
        app_name=config.APP_NAME, user_id=user, session_id=session_id)

    turns = []
    for index, message in enumerate(case["conversation"]):
        text = "".join(p.get("text", "") for p in message.get("parts", []))
        safe, sanitized, _ = ModelArmorGuard.inspect_input(text)
        events = [{"author": "user",
                   "content": {"role": "user", "parts": [{"text": text}]}}]

        if not safe:
            events.append({
                "author": AGENT_ID,
                "content": {"role": "model", "parts": [
                    {"text": "I cannot fulfill this request."}]},
            })
        else:
            content = types.Content(role="user", parts=[types.Part(text=sanitized)])
            async for event in runner.run_async(
                    user_id=user, session_id=session_id, new_message=content):
                if not getattr(event, "content", None):
                    continue
                parts = [p for p in (_part_to_dict(p) for p in event.content.parts) if p]
                if parts:
                    events.append({
                        "author": getattr(event, "author", AGENT_ID),
                        "content": {"role": event.content.role or "model", "parts": parts},
                    })

        turns.append({"turn_index": index, "turn_id": f"turn_{index}", "events": events})

    final = []
    for event in reversed(turns[-1]["events"]):
        if event["author"] == "user":
            continue
        text = "".join(p.get("text", "") for p in event["content"]["parts"] if p.get("text"))
        if text:
            final = [{"text": text}]
            break

    trace = {k: case[k] for k in ("eval_case_id", "tags", "rubric_groups") if k in case}
    trace["prompt"] = case["conversation"][0]
    trace["responses"] = [{"response": {"role": "model", "parts": final}}]
    trace["reference"] = {"response": {"role": "model", "parts": [{"text": ""}]}}
    # `agents` is a mapping keyed by agent id, not a list. A list is valid JSON
    # and fails schema validation with a message naming the field but not the
    # file, so it is worth getting right here.
    trace["agent_data"] = {
        "agents": {AGENT_ID: {"agent_id": AGENT_ID, "agent_type": "LlmAgent"}},
        "turns": turns,
    }
    return trace


async def main_async(args) -> int:
    data = json.loads(Path(args.dataset).read_text())
    cases = data["eval_cases"] if isinstance(data, dict) else data

    traces, failed = [], []
    for case in cases:
        last = None
        for attempt in range(4):
            try:
                traces.append(await run_case(case))
                print(f"  ok   {case['eval_case_id']}")
                last = None
                break
            except Exception as exc:  # noqa: BLE001 - report, do not hide
                last = exc
                # 429 is a rate limit, not a result. Dropping the case on a
                # transient quota error silently shrinks the suite.
                if "RESOURCE_EXHAUSTED" not in str(exc) and "429" not in str(exc):
                    break
                delay = 20 * (attempt + 1)
                print(f"  ...  {case['eval_case_id']} rate limited, retry in {delay}s")
                await asyncio.sleep(delay)
        if last is not None:
            failed.append((case["eval_case_id"], f"{type(last).__name__}: {last}"))
            print(f"  FAIL {case['eval_case_id']}: {last}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"eval_cases": traces}, indent=2) + "\n")
    print(f"\n{len(traces)}/{len(cases)} succeeded -> {out}")
    if failed:
        print("Failed cases are dropped from the artifact, not silently passed:")
        for cid, why in failed:
            print(f"  {cid}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", required=True)
    sys.exit(asyncio.run(main_async(ap.parse_args())))
