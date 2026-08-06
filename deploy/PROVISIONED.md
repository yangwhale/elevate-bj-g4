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

Run `deploy/teardown.sh` to remove everything still live.
