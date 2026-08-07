# Deploying from zero

Everything below was executed against `chris-pgp-host` on 2026-08-07. Steps that
failed the first time carry a note saying how, because Cloud Run and Vertex AI
Search both report these failures in ways that name neither the cause nor the
fix.

## 0. Prerequisites

```bash
gcloud services enable aiplatform.googleapis.com discoveryengine.googleapis.com \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  --project="$PROJECT_ID"
```

A personal access token for the enterprise backend, stored where the client
looks for it:

```bash
mkdir -p ~/.config/elevate
printf '%s' "$MCP_TOKEN" > ~/.config/elevate/mcp-token
chmod 600 ~/.config/elevate/mcp-token
```

Verify it before going further — the token determines which employee the agent
is, and everything downstream depends on that:

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from agent.tools import mcp_client
print(mcp_client.whoami())"
```

## 1. Policy corpus into Cloud Storage

```bash
gcloud storage buckets create "gs://${PROJECT_ID}-elevate-hr-policies" \
  --location=us-central1 --uniform-bucket-level-access
gcloud storage cp -r knowledge/** "gs://${PROJECT_ID}-elevate-hr-policies/"
gcloud storage rm "gs://${PROJECT_ID}-elevate-hr-policies/check_okf.py"
```

Keep the directory structure. Citations are `gs://<bucket>/<section>/<file>.md`
and the resolver checks that exact path.

### The `.txt` mirror, and why it exists

**Vertex AI Search rejects `text/markdown` on import.** All 187 documents fail,
twice — once with `dataSchema=content`, once with an explicit metadata JSONL —
and the error message lists `text/markdown` among the permitted types while
refusing it. The index therefore reads a plain-text copy:

```bash
python3 - <<'PY'
import os, shutil
for dirpath, _, names in os.walk('knowledge'):
    for f in names:
        if not f.endswith('.md'): continue
        rel = os.path.relpath(os.path.join(dirpath, f), 'knowledge')
        out = os.path.join('/tmp/corpus_txt', rel[:-3] + '.txt')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copyfile(os.path.join(dirpath, f), out)
PY
gcloud storage buckets create "gs://${PROJECT_ID}-elevate-hr-policies-txt" \
  --location=us-central1 --uniform-bucket-level-access
gcloud storage cp -r /tmp/corpus_txt/* "gs://${PROJECT_ID}-elevate-hr-policies-txt/"
```

`rag_tool` maps the `.txt` link the index returns back to the `.md` path, so
citations still resolve against the published corpus.

## 2. Vertex AI Search

Every Discovery Engine call needs `x-goog-user-project`; without it the API
returns 403 with a message about quota projects rather than about permissions.

```bash
TOKEN=$(gcloud auth print-access-token)
BASE="https://discoveryengine.googleapis.com/v1/projects/${PROJECT_ID}/locations/global/collections/default_collection"

curl -s -X POST "${BASE}/dataStores?dataStoreId=elevate-hr-policies" \
  -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: ${PROJECT_ID}" \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"Elevate HR Policies","industryVertical":"GENERIC",
       "solutionTypes":["SOLUTION_TYPE_SEARCH"],"contentConfig":"CONTENT_REQUIRED"}'

curl -s -X POST "${BASE}/dataStores/elevate-hr-policies/branches/0/documents:import" \
  -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: ${PROJECT_ID}" \
  -H 'Content-Type: application/json' \
  -d "{\"gcsSource\":{\"inputUris\":[\"gs://${PROJECT_ID}-elevate-hr-policies-txt/**/*.txt\"],
       \"dataSchema\":\"content\"},\"reconciliationMode\":\"FULL\"}"

curl -s -X POST "${BASE}/engines?engineId=elevate-hr-search" \
  -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: ${PROJECT_ID}" \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"Elevate HR Search","solutionType":"SOLUTION_TYPE_SEARCH",
       "dataStoreIds":["elevate-hr-policies"],
       "searchEngineConfig":{"searchTier":"SEARCH_TIER_STANDARD"}}'
```

Check the import actually succeeded. It reports `done: true` either way:

```bash
curl -s "${BASE}/dataStores/elevate-hr-policies/branches/0/operations?pageSize=1" \
  -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: ${PROJECT_ID}" |
  python3 -c "import json,sys; m=json.load(sys.stdin)['operations'][0]['metadata']; \
print('success', m.get('successCount'), 'failure', m.get('failureCount'))"
```

Indexing takes 10–30 minutes. Until it finishes, search returns zero results and
`rag_tool` falls back to reading the corpus from disk — the `retrieval` field of
its result says which path served the answer.

## 3. Agent Engine

Terraform cannot create an Agent Engine instance; deployment goes through the
SDK.

```bash
gcloud storage buckets create "gs://${PROJECT_ID}-elevate-staging" \
  --location=us-central1 --uniform-bucket-level-access
python3 deploy/deploy_agent_engine.py
```

Two constraints found by hitting them:

* **`GOOGLE_CLOUD_PROJECT` is a reserved env-var name.** Passing it fails the
  update with `400 FailedPrecondition`.
* **The model name is resolved at run time, not build time.** A model the
  project cannot serve deploys cleanly and 404s on every turn. `gemini-2.5-flash`
  is verified available in `us-central1`; `gemini-3.5-flash` is not.

## 4. Web UI on Cloud Run

```bash
gcloud artifacts repositories create cloud-run-source-deploy \
  --repository-format=docker --location=us-central1
adk deploy cloud_run --project "$PROJECT_ID" --region us-central1 \
  --service_name elevate-hr-ui --with_ui --trace_to_cloud .
```

This failed four times, and Cloud Run reported all four identically — *"the
container failed to start and listen on the port"*:

| Cause | How it presents | Fix |
| :--- | :--- | :--- |
| Artifact Registry repo missing | Interactive prompt blocks a non-interactive run | Create it first, as above |
| `opentelemetry.exporter` missing | Health-check timeout | Add `opentelemetry-exporter-otlp` |
| `opentelemetry.exporter.cloud_trace` missing | Health-check timeout again | Add `opentelemetry-exporter-gcp-trace` — a separate package |
| App name derived from the directory | `/list-apps` lists it, `/run` rejects it with "Invalid agent name" | Deploy from a directory whose name is a valid Python identifier |

**Dependencies must be in `requirements.txt`.** The ADK deploy path does not read
`pyproject.toml`, so adding them there changes nothing and the next deploy fails
the same way.

**Environment variables do not travel with a source deploy.** Set them on the
service afterwards, or the container comes up unable to reach the backend:

```bash
gcloud run services update elevate-hr-ui --region=us-central1 \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE,GEMINI_MODEL=gemini-2.5-flash,\
VERTEX_AI_SEARCH_ENGINE_ID=elevate-hr-search,VERTEX_AI_SEARCH_LOCATION=global,\
POLICY_CORPUS_URI=gs://${PROJECT_ID}-elevate-hr-policies,\
MCP_BASE_URL=https://mock-saas.aishprabhat.demo.altostrat.com,MCP_TOKEN=${MCP_TOKEN}"
```

## 5. Verify

```bash
URL=$(gcloud run services describe elevate-hr-ui --region=us-central1 --format='value(status.url)')
APP=$(curl -s "$URL/list-apps" | python3 -c 'import json,sys; print(json.load(sys.stdin)[0])')

curl -s -X POST "$URL/apps/$APP/users/$EMP/sessions/check" \
  -H 'Content-Type: application/json' -d '{"state":{}}'
curl -s -X POST "$URL/run" -H 'Content-Type: application/json' \
  -d "{\"appName\":\"$APP\",\"userId\":\"$EMP\",\"sessionId\":\"check\",
       \"newMessage\":{\"role\":\"user\",\"parts\":[{\"text\":\"How many vacation days do I have left?\"}]}}"
```

A correct deployment returns the balance from the real backend. If it says the
employee was not found, the container has no token. If the citation contains a
literal `${PROJECT_ID}`, `POLICY_CORPUS_URI` is unset.

## 6. Access

The UI is public in this deployment so the link can be opened directly, and the
container carries the backend token. Anyone with the URL can act as the token's
employee. Acceptable against a shared mock; not otherwise.

```bash
# close it
gcloud run services remove-iam-policy-binding elevate-hr-ui \
  --region=us-central1 --member=allUsers --role=roles/run.invoker
```

Production puts the token in Secret Manager and the service behind IAP. Neither
is done here.

## 7. Teardown

```bash
deploy/teardown.sh
```

Removes the Agent Engine instance, the search app and data store, all four
buckets, the Cloud Run service and the Artifact Registry repository. Safe to
re-run. Every resource it removes is listed in `deploy/PROVISIONED.md` with its
creation time.
