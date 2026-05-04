#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project id.}"

POLICY_NAME="${POLICY_NAME:-restailor-edge-policy}"
FRONTEND_BACKEND="${FRONTEND_BACKEND:-restailor-frontend-backend}"
API_BACKEND="${API_BACKEND:-restailor-api-backend}"

ALLOWED_HOSTS_EXPRESSION='has(request.headers["host"]) && !request.headers["host"].lower().matches("^restailor[.]com$|^www[.]restailor[.]com$|^api[.]restailor[.]com$")'
SCANNER_UA_EXPRESSION='has(request.headers["user-agent"]) && (request.headers["user-agent"].contains("CensysInspect") || request.headers["user-agent"].contains("MJ12bot") || request.headers["user-agent"].contains("visionheight.com/scan"))'
SCANNER_PATH_EXPRESSION='request.path.matches("(?i).*/[.]git/.*") || request.path.matches("(?i).*/wp-admin/.*") || request.path.matches("(?i).*/wp-login[.]php.*") || request.path.matches("(?i).*/js/config[.]js.*")'

if ! gcloud compute security-policies describe "$POLICY_NAME" \
  --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute security-policies create "$POLICY_NAME" \
    --project "$PROJECT_ID" \
    --description "Block low-value scanner traffic before Cloud Run"
fi

if ! gcloud compute security-policies rules describe 900 \
  --project "$PROJECT_ID" \
  --security-policy "$POLICY_NAME" >/dev/null 2>&1; then
  gcloud compute security-policies rules create 900 \
    --project "$PROJECT_ID" \
    --security-policy "$POLICY_NAME" \
    --action deny-403 \
    --expression "$ALLOWED_HOSTS_EXPRESSION" \
    --description "Block requests for unrecognized hostnames"
else
  gcloud compute security-policies rules update 900 \
    --project "$PROJECT_ID" \
    --security-policy "$POLICY_NAME" \
    --action deny-403 \
    --expression "$ALLOWED_HOSTS_EXPRESSION" \
    --description "Block requests for unrecognized hostnames"
fi

if ! gcloud compute security-policies rules describe 1000 \
  --project "$PROJECT_ID" \
  --security-policy "$POLICY_NAME" >/dev/null 2>&1; then
  gcloud compute security-policies rules create 1000 \
    --project "$PROJECT_ID" \
    --security-policy "$POLICY_NAME" \
    --action deny-403 \
    --expression "$SCANNER_UA_EXPRESSION" \
    --description "Block obvious scanner user agents"
else
  gcloud compute security-policies rules update 1000 \
    --project "$PROJECT_ID" \
    --security-policy "$POLICY_NAME" \
    --action deny-403 \
    --expression "$SCANNER_UA_EXPRESSION" \
    --description "Block obvious scanner user agents"
fi

if ! gcloud compute security-policies rules describe 1010 \
  --project "$PROJECT_ID" \
  --security-policy "$POLICY_NAME" >/dev/null 2>&1; then
  gcloud compute security-policies rules create 1010 \
    --project "$PROJECT_ID" \
    --security-policy "$POLICY_NAME" \
    --action deny-403 \
    --expression "$SCANNER_PATH_EXPRESSION" \
    --description "Block common exploit scan paths"
else
  gcloud compute security-policies rules update 1010 \
    --project "$PROJECT_ID" \
    --security-policy "$POLICY_NAME" \
    --action deny-403 \
    --expression "$SCANNER_PATH_EXPRESSION" \
    --description "Block common exploit scan paths"
fi

for backend in "$FRONTEND_BACKEND" "$API_BACKEND"; do
  gcloud compute backend-services update "$backend" \
    --project "$PROJECT_ID" \
    --global \
    --security-policy "$POLICY_NAME"
done

echo "Cloud Armor policy ${POLICY_NAME} is attached to ${FRONTEND_BACKEND} and ${API_BACKEND}."
