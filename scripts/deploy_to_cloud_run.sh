#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

: "${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project id.}"

REGION="${REGION:-us-east5}"
REPOSITORY="${REPOSITORY:-restailor}"
TAG="${TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"
API_SERVICE="${API_SERVICE:-restailor-api}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-restailor-frontend}"
WORKER_JOB="${WORKER_JOB:-restailor-worker}"
MIGRATION_JOB="${MIGRATION_JOB:-restailor-migrate}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-}"
VPC_CONNECTOR="${VPC_CONNECTOR:-}"
VPC_EGRESS="${VPC_EGRESS:-private-ranges-only}"
NETWORK="${NETWORK:-}"
SUBNET="${SUBNET:-}"
CLOUD_SQL_INSTANCE="${CLOUD_SQL_INSTANCE:-}"
DOPPLER_SECRETS="${DOPPLER_SECRETS:-}"
DOPPLER_PROJECT="${DOPPLER_PROJECT:-restailor}"
DOPPLER_CONFIG="${DOPPLER_CONFIG:-prd}"
CLOUD_RUN_INGRESS="${CLOUD_RUN_INGRESS:-internal-and-cloud-load-balancing}"

NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-https://api.restailor.com}"
NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-$NEXT_PUBLIC_API_BASE_URL}"
NEXT_PUBLIC_SITE_URL="${NEXT_PUBLIC_SITE_URL:-https://restailor.com}"
NEXT_PUBLIC_FEATURE_ANALYTICS="${NEXT_PUBLIC_FEATURE_ANALYTICS:-1}"
NEXT_PUBLIC_TURNSTILE_SITE_KEY="${NEXT_PUBLIC_TURNSTILE_SITE_KEY:-}"
NEXT_PUBLIC_SUPPORT_EMAIL="${NEXT_PUBLIC_SUPPORT_EMAIL:-support@restailor.com}"
NEXT_PUBLIC_GTAG_ID="${NEXT_PUBLIC_GTAG_ID:-}"

IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}"
API_IMAGE="${IMAGE_BASE}/api:${TAG}"
WORKER_IMAGE="${IMAGE_BASE}/worker:${TAG}"
FRONTEND_IMAGE="${IMAGE_BASE}/frontend:${TAG}"

if [[ -z "$DOPPLER_SECRETS" ]]; then
  echo "Set DOPPLER_SECRETS, for example: DOPPLER_TOKEN=restailor-doppler-token:latest" >&2
  exit 1
fi

service_common_flags=()
if [[ -n "$SERVICE_ACCOUNT" ]]; then
  service_common_flags+=(--service-account "$SERVICE_ACCOUNT")
fi
if [[ -n "$NETWORK" ]]; then
  service_common_flags+=(--network "$NETWORK")
fi
if [[ -n "$SUBNET" ]]; then
  service_common_flags+=(--subnet "$SUBNET")
fi
if [[ -n "$VPC_CONNECTOR" ]]; then
  service_common_flags+=(--vpc-connector "$VPC_CONNECTOR")
fi
if [[ -n "$NETWORK" || -n "$SUBNET" || -n "$VPC_CONNECTOR" ]]; then
  service_common_flags+=(--vpc-egress "$VPC_EGRESS")
fi
if [[ -n "$CLOUD_SQL_INSTANCE" ]]; then
  service_common_flags+=(--set-cloudsql-instances "$CLOUD_SQL_INSTANCE")
fi

secret_flags=()
if [[ -n "$DOPPLER_SECRETS" ]]; then
  secret_flags+=(--set-secrets "$DOPPLER_SECRETS")
fi

echo "Building images with tag ${TAG} in project ${PROJECT_ID}..."
gcloud builds submit \
  --project "$PROJECT_ID" \
  --config cloudbuild.yaml \
  --substitutions "_REGION=${REGION},_REPOSITORY=${REPOSITORY},_TAG=${TAG},_NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL},_NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL},_NEXT_PUBLIC_SITE_URL=${NEXT_PUBLIC_SITE_URL},_NEXT_PUBLIC_FEATURE_ANALYTICS=${NEXT_PUBLIC_FEATURE_ANALYTICS},_NEXT_PUBLIC_TURNSTILE_SITE_KEY=${NEXT_PUBLIC_TURNSTILE_SITE_KEY},_NEXT_PUBLIC_SUPPORT_EMAIL=${NEXT_PUBLIC_SUPPORT_EMAIL},_NEXT_PUBLIC_GTAG_ID=${NEXT_PUBLIC_GTAG_ID}" \
  .

echo "Deploying migration job..."
gcloud run jobs deploy "$MIGRATION_JOB" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$API_IMAGE" \
  --command bash \
  --args "-lc,doppler run -p ${DOPPLER_PROJECT} -c ${DOPPLER_CONFIG} -- alembic upgrade head" \
  --env-vars-file deploy/cloudrun/api.env.yaml \
  --memory 1Gi \
  --cpu 1 \
  --task-timeout 900 \
  "${service_common_flags[@]}" \
  "${secret_flags[@]}"

echo "Running migrations..."
gcloud run jobs execute "$MIGRATION_JOB" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --wait

echo "Deploying API service..."
gcloud run deploy "$API_SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$API_IMAGE" \
  --allow-unauthenticated \
  --port 8080 \
  --env-vars-file deploy/cloudrun/api.env.yaml \
  --memory 1Gi \
  --cpu 1 \
  --concurrency 40 \
  --timeout 900 \
  --ingress "$CLOUD_RUN_INGRESS" \
  --min 0 \
  --max 1 \
  --min-instances 0 \
  --max-instances 1 \
  --startup-probe "httpGet.path=/health,initialDelaySeconds=5,timeoutSeconds=3,periodSeconds=10,failureThreshold=12" \
  "${service_common_flags[@]}" \
  "${secret_flags[@]}"

echo "Deploying on-demand worker job..."
gcloud run jobs deploy "$WORKER_JOB" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$WORKER_IMAGE" \
  --command bash \
  --args "-lc,doppler run -p ${DOPPLER_PROJECT} -c ${DOPPLER_CONFIG} -- arq --burst worker.WorkerSettings" \
  --env-vars-file deploy/cloudrun/worker.env.yaml \
  --memory 1Gi \
  --cpu 1 \
  --task-timeout 3600 \
  "${service_common_flags[@]}" \
  "${secret_flags[@]}"

echo "Deploying frontend service..."
gcloud run deploy "$FRONTEND_SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$FRONTEND_IMAGE" \
  --allow-unauthenticated \
  --port 8080 \
  --env-vars-file deploy/cloudrun/frontend.env.yaml \
  --memory 512Mi \
  --cpu 1 \
  --concurrency 80 \
  --timeout 300 \
  --ingress "$CLOUD_RUN_INGRESS" \
  --min 0 \
  --max 1 \
  --min-instances 0 \
  --max-instances 1 \
  "${service_common_flags[@]}"

echo "Done."
echo "API image: ${API_IMAGE}"
echo "Worker image: ${WORKER_IMAGE}"
echo "Frontend image: ${FRONTEND_IMAGE}"
