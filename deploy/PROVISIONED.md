# Provisioned Cloud Resources

Everything this project created in Google Cloud, so it can be removed without
guessing. Append a row when you create something; do not rely on memory.

**Project:** `chris-pgp-host` (project number 688858276789)
**Owner:** chrisya@google.com
**Purpose:** Project Elevate capstone. Nothing here is production.

| # | Resource | Identifier | Region | Created | Removed |
| :-- | :--- | :--- | :--- | :--- | :--- |
| 0 | Reasoning Engine (empty, created by a permission probe — **already deleted**) | `748733883410808832` | us-central1 | 2026-08-06 23:18 HKT | 2026-08-06 23:18 HKT |
| 1 | GCS bucket, the corpus Vertex AI Search ingests | `gs://chris-pgp-host-elevate-hr-policies` (187 objects) | us-central1 | 2026-08-06 23:50 HKT | — |
| 2 | Vertex AI Search data store | `elevate-hr-policies` (collection `default_collection`) | global | 2026-08-06 23:52 HKT | — |
| 3 | Vertex AI Search app / engine | `elevate-hr-search`, tier STANDARD | global | 2026-08-06 23:53 HKT | — |
| 4 | GCS staging bucket for Agent Engine packaging | `gs://chris-pgp-host-elevate-staging` | us-central1 | 2026-08-07 00:05 HKT | — |
| 5 | Agent Engine instance | `elevate-hr-agent` = `projects/688858276789/locations/us-central1/reasoningEngines/1100014654345707520` | us-central1 | 2026-08-07 00:06 HKT | — |
| 6 | GCS bucket, `.txt` mirror of the corpus. Vertex AI Search rejects `text/markdown`, so the index reads this copy while citations keep the `.md` path | `gs://chris-pgp-host-elevate-hr-policies-txt` (187 objects) | us-central1 | 2026-08-07 01:05 HKT | — |
| 7 | Artifact Registry repo for Cloud Run source builds | `cloud-run-source-deploy` | us-central1 | 2026-08-07 14:52 HKT | — |
| 8 | Cloud Run service, ADK web UI over the agent. **Public — `allUsers` has `run.invoker`**, and the container holds the backend token, so anyone with the URL can act as EMP-246 against the mock HR service | `elevate-hr-ui` → https://elevate-hr-ui-b5lltzdmxq-uc.a.run.app | us-central1 | 2026-08-07 16:45 HKT | — |

Run `deploy/teardown.sh` to remove everything still live.

## Notes

* Vertex AI Search rejects `text/markdown` on import despite listing it in the
  error message's allowed set. The index therefore reads a `.txt` mirror
  (`...-hr-policies-txt`), and `rag_tool` maps the returned link back to the
  `.md` path so citations resolve against the published corpus.
* `GOOGLE_CLOUD_PROJECT` is a reserved env var name on Agent Engine; setting it
  fails the update with 400 FailedPrecondition.
* Nothing here holds customer data. The corpus is a synthetic handbook and the
  HCM/ITSM backends are in-process mocks.

## Access note

The Cloud Run UI is deliberately public so it can be opened from a link. The
container carries `MCP_TOKEN` as an environment variable, so anyone who has the
URL can read and write EMP-246's records in the mock HR service. That is
acceptable for a shared test backend and would not be for anything else. To
close it:

```bash
gcloud run services remove-iam-policy-binding elevate-hr-ui \
  --region=us-central1 --project=chris-pgp-host \
  --member=allUsers --role=roles/run.invoker
```

A production deployment puts the token in Secret Manager and the service behind
IAP; neither is done here.

## Cost shape

Discovery Engine standard tier indexes ~1 MB of text; Agent Engine bills the
runtime while an instance exists. Deleting the Agent Engine instance and the
search app removes the recurring cost; the buckets hold ~2 MB.
