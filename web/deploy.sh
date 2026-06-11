#!/usr/bin/env bash
# Deploy Sprout to Cloud Run. Run from the web/ directory (Cloud Shell or local gcloud).
#
# Usage:
#   ./deploy.sh PROJECT_ID NVIDIA_API_KEY
#
# Optional Google Sheets ledger (adds real persistence + a Google service):
#   SHEET_ID=<sheet-id> SA_FILE=path/to/service-account.json ./deploy.sh PROJECT_ID NVIDIA_KEY
set -euo pipefail

PROJECT_ID="${1:?Usage: ./deploy.sh PROJECT_ID NVIDIA_API_KEY}"
NVIDIA_API_KEY="${2:?Usage: ./deploy.sh PROJECT_ID NVIDIA_API_KEY}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-sprout}"

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com

PROJECT_NUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
RUNTIME_SA="${PROJECT_NUM}-compute@developer.gserviceaccount.com"

# One-time: grant the default compute SA the roles Cloud Build/Run need on fresh projects.
for role in roles/cloudbuild.builds.builder roles/run.builder roles/storage.objectViewer \
            roles/logging.logWriter roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${RUNTIME_SA}" --role="$role" --quiet >/dev/null
done

# --- Secret: NVIDIA API key ---
upsert_secret() {  # name, value
  if gcloud secrets describe "$1" >/dev/null 2>&1; then
    printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=- >/dev/null
  else
    printf '%s' "$2" | gcloud secrets create "$1" --data-file=- --replication-policy=automatic >/dev/null
  fi
  gcloud secrets add-iam-policy-binding "$1" \
    --member="serviceAccount:${RUNTIME_SA}" --role="roles/secretmanager.secretAccessor" --quiet >/dev/null
}
upsert_secret sprout-nvidia-key "$NVIDIA_API_KEY"

SECRETS="NVIDIA_API_KEY=sprout-nvidia-key:latest"
ENV_VARS="MAX_INPUT_CHARS=600"

# --- Optional: Google Sheets ledger ---
if [[ -n "${SHEET_ID:-}" && -n "${SA_FILE:-}" ]]; then
  upsert_secret sprout-sa-json "$(cat "$SA_FILE")"
  SECRETS="${SECRETS},GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT=sprout-sa-json:latest"
  ENV_VARS="${ENV_VARS},SPROUT_SHEET_ID=${SHEET_ID}"
  echo "✓ Sheets ledger enabled for sheet ${SHEET_ID}"
fi

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-secrets "$SECRETS" \
  --set-env-vars "$ENV_VARS" \
  --memory 512Mi \
  --min-instances 1 \
  --max-instances 3 \
  --cpu-boost \
  --timeout 60 \
  --quiet

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
echo "✅ Deployed: $URL"
echo "Smoke test:"
echo "  curl -s $URL/healthz"
echo "  curl -sI --compressed $URL/ | grep -i content-encoding"
