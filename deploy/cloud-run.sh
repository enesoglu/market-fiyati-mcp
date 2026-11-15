#!/bin/sh
# Deploy only when explicitly invoked by an operator with their own project and credentials.
set -eu
if [ "$#" -ne 4 ]; then
  printf 'Usage: sh deploy/cloud-run.sh PROJECT REGION IMAGE_URL TOKEN_HASH_SECRET\n' >&2
  exit 2
fi
command -v gcloud >/dev/null
PROJECT_ID=$1
REGION=$2
IMAGE_URL=$3
TOKEN_HASH_SECRET=$4
SERVICE_NAME=market-fiyati-mcp
# Bootstrap privately so no unknown public origin is accepted by the MCP endpoint.
gcloud run deploy "$SERVICE_NAME" --project "$PROJECT_ID" --region "$REGION" \
  --image "$IMAGE_URL" --port 8080 --memory 256Mi --cpu 1 --concurrency 24 \
  --timeout 60 --max-instances 3 --no-allow-unauthenticated --quiet \
  --set-env-vars "HOST=0.0.0.0,AUTH_MODE=bearer,PUBLIC_URL=https://bootstrap.invalid" \
  --set-secrets "ACCESS_TOKEN_HASH=$TOKEN_HASH_SECRET:latest"
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --project "$PROJECT_ID" \
  --region "$REGION" --format 'value(status.url)')
gcloud run services update "$SERVICE_NAME" --project "$PROJECT_ID" --region "$REGION" \
  --update-env-vars "PUBLIC_URL=$SERVICE_URL" --quiet
# Platform invocation is public; application-level bearer authentication still protects /mcp.
gcloud run services add-iam-policy-binding "$SERVICE_NAME" --project "$PROJECT_ID" \
  --region "$REGION" --member allUsers --role roles/run.invoker --quiet
printf 'MCP endpoint: %s/mcp\n' "$SERVICE_URL"
