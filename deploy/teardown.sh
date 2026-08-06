#!/usr/bin/env bash
# Remove every cloud resource this project created. Safe to re-run: each step
# tolerates the resource already being gone.
set -u
PROJECT="${PROJECT_ID:-chris-pgp-host}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-gs://${PROJECT}-elevate-hr-policies}"
DS_ID="${DS_ID:-elevate-hr-policies}"
ENGINE_ID="${ENGINE_ID:-elevate-hr-search}"
TOKEN() { gcloud auth print-access-token; }

echo "== Agent Engine instances tagged elevate"
for RE in $(curl -s -H "Authorization: Bearer $(TOKEN)" \
    "https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/${REGION}/reasoningEngines" \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print(' '.join(r['name'] for r in d.get('reasoningEngines',[]) if 'elevate' in (r.get('displayName','')+r.get('name','')).lower()))" 2>/dev/null); do
  echo "  deleting $RE"
  curl -s -X DELETE -H "Authorization: Bearer $(TOKEN)" \
    "https://${REGION}-aiplatform.googleapis.com/v1/${RE}?force=true" >/dev/null
done

echo "== Discovery Engine search app"
curl -s -X DELETE -H "Authorization: Bearer $(TOKEN)" -H "x-goog-user-project: ${PROJECT}" \
  "https://discoveryengine.googleapis.com/v1/projects/${PROJECT}/locations/global/collections/default_collection/engines/${ENGINE_ID}" >/dev/null

echo "== Discovery Engine data store"
curl -s -X DELETE -H "Authorization: Bearer $(TOKEN)" -H "x-goog-user-project: ${PROJECT}" \
  "https://discoveryengine.googleapis.com/v1/projects/${PROJECT}/locations/global/collections/default_collection/dataStores/${DS_ID}" >/dev/null

echo "== GCS bucket ${BUCKET}"
gcloud storage rm -r "${BUCKET}" --project="${PROJECT}" 2>/dev/null || echo "  (already gone)"

gcloud storage rm -r "gs://${PROJECT}-elevate-hr-policies-txt" --project="${PROJECT}" 2>/dev/null || echo "  (txt mirror already gone)"

echo "== Staging bucket objects under gs://${PROJECT}-elevate-staging"
gcloud storage rm -r "gs://${PROJECT}-elevate-staging" --project="${PROJECT}" 2>/dev/null || echo "  (already gone)"

echo "Done. Verify with: deploy/verify-clean.sh"
