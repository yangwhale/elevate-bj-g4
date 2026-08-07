# Project Elevate — HR & IT assistant

An agent that answers HR policy questions from an approved corpus, and carries
out leave and IT-ticket transactions in WorkWeek and ServiceImmediately.

**Status: deployed, not shippable.** Four absolute safety gates pass; two
quality gates do not. Numbers in
[`tests/eval/evaluation_report.md`](tests/eval/evaluation_report.md).

| | |
| :--- | :--- |
| Agent | Google ADK, `gemini-2.5-flash`, 13 tools |
| Runtime | Vertex AI Agent Engine, `us-central1` |
| Retrieval | Vertex AI Search over 187 handbook sections, `global` |
| Backends | WorkWeek HCM and ServiceImmediately ITSM, live over MCP |
| UI | Cloud Run, ADK web |

---

## Documents

| File | What it is |
| :--- | :--- |
| [`BRD.md`](BRD.md) | The original requirements. Not modified. |
| [`SDD.md`](SDD.md) | Solution design, v1.14. Architecture, sequence flows, guardrails, cost model, and the evaluation contract. |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | How to stand this up from zero, including the failures each step produced the first time. |
| [`docs/BACKEND_CONTRACT.md`](docs/BACKEND_CONTRACT.md) | What the real enterprise service actually does — three differences from the OpenAPI spec, and one place it contradicts `FR-4.3`. |
| [`docs/LESSONS.md`](docs/LESSONS.md) | Twelve things this build taught us, each with the rule it produced. |
| [`deploy/PROVISIONED.md`](deploy/PROVISIONED.md) | Every cloud resource created, with identifiers and creation times. `deploy/teardown.sh` removes them. |
| [`tests/eval/evaluation_report.md`](tests/eval/evaluation_report.md) | Evaluation design, results, and the defects the run found. |

---

## Layout

```
agent/
  agent.py              root agent, before/after callbacks
  prompt.py             the operating rules, in priority order — identity first
  guardrails.py         injection patterns, SPII redaction, RBAC check
  session.py            session service
  tools/
    mcp_client.py       client for the live WorkWeek / ServiceImmediately MCP
    workweek_tool.py    leave and profile; remote when a token is set, mock otherwise
    serviceimmediately_tool.py   tickets, with the FR-4.3 state machine enforced here
    rag_tool.py         Vertex AI Search, falling back to the corpus on disk
    clock_tool.py       today's date, so relative dates resolve to the right year
knowledge/              the approved corpus, 187 sections. The only source of policy fact.
tests/
  test_agent.py         42 unit tests, always against the in-process mocks
  eval/
    build_datasets.py   generator — verifies every citation before writing
    run_cases.py        drives cases in-process with the real caller identity
    eval_config.yaml    4 built-in metrics + 3 local ones
    test_metrics.py     16 tests for the metrics themselves
deploy/                 deployment script, resource register, teardown
terraform/              infrastructure for the surrounding services
```

---

## Running it

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt

# unit tests — never touch the network
pytest tests/ -q

# regenerate the evaluation datasets from the corpus
python3 tests/eval/build_datasets.py

# run the cases, then grade
python3 tests/eval/run_cases.py --dataset tests/eval/datasets/eval-data.json \
                               --out artifacts/traces/single.json
agents-cli eval grade --traces artifacts/traces/single.json \
                      --config tests/eval/eval_config.yaml \
                      --output artifacts/results/single
```

Grade three times and take the mean. A single run of an LLM judge is not a
result — measured spread is 0.006–0.018 on the 52-case suite and 0.043–0.097 on
the 8-case one.

---

## Things worth knowing before you change anything

* **The prompt is an ordered list.** A procedural rule inserted above a safety
  rule can suppress it. Inserting anything near the top means re-running the
  security cases.
* **Unit tests must never reach the live service.** `ELEVATE_FORCE_MOCK=1` is
  set in `tests/conftest.py`. Before that existed, one run wrote test data into
  a real employee record.
* **Datasets are generated, not edited.** Hand-editing a dataset reintroduces
  the failure the generator exists to prevent: an expected answer no document
  supports.
* **Identity comes from the backend token**, not from configuration. The
  datasets resolve the caller at generation time for the same reason.
* **The retrieval tool holds no facts.** An earlier version had a hardcoded
  policy catalog that contradicted the handbook and won every lookup.
