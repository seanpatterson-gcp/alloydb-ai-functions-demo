#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT:-$(gcloud config get-value project)}"
REGION="us-west4"
SERVICE_NAME="alloydb-ai-frontend"
CLUSTER_ID="alloydb-ai-cluster"
INSTANCE_ID="alloydb-ai-primary"
ALLOYDB_INSTANCE="projects/${PROJECT_ID}/locations/${REGION}/clusters/${CLUSTER_ID}/instances/${INSTANCE_ID}"

echo "============================================================"
echo "Deploying AlloyDB AI Frontend to Cloud Run"
echo "Project:  $PROJECT_ID"
echo "Region:   $REGION"
echo "Service:  $SERVICE_NAME"
echo "============================================================"

# Grant Compute Default Service Account / Cloud Run identity permission to invoke AlloyDB MCP
RUN_SA="${PROJECT_ID}-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${RUN_SA}" \
    --role="roles/alloydb.admin" \
    --quiet

# Deploy Cloud Run Service using Cloud Build
gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars="GCP_PROJECT=${PROJECT_ID},ALLOYDB_REGION=${REGION},ALLOYDB_CLUSTER=${CLUSTER_ID},ALLOYDB_INSTANCE=${ALLOYDB_INSTANCE},ALLOYDB_DATABASE=postgres"

echo "============================================================"
echo "Deployment Complete!"
gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format="value(status.url)"
echo "============================================================"
