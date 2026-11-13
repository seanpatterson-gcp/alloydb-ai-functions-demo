#!/usr/bin/env bash
set -euo pipefail

# Configuration
PROJECT_ID="${GCP_PROJECT:-$(gcloud config get-value project)}"
REGION="us-west4" # Las Vegas
CLUSTER_ID="alloydb-ai-cluster"
INSTANCE_ID="alloydb-ai-primary"
DATABASE_NAME="postgres"
CPU_COUNT="8"
AVAILABILITY_TYPE="ZONAL" # Single zone

echo "============================================================"
echo "Provisioning AlloyDB for PostgreSQL (Las Vegas, 8 vCPU, PSC)"
echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo "============================================================"

# 1. Enable Required Services
echo "[1/5] Enabling GCP APIs..."
gcloud services enable \
    alloydb.googleapis.com \
    compute.googleapis.com \
    servicenetworking.googleapis.com \
    run.googleapis.com \
    aiplatform.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    --project="$PROJECT_ID"

# 2. Configure Service Agent IAM for Vertex AI
echo "[2/5] Configuring AlloyDB Service Agent permissions for Vertex AI..."
PROJECT_NUM=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
ALLOYDB_SA="service-${PROJECT_NUM}@gcp-sa-alloydb.iam.gserviceaccount.com"

# Create service identity if not present
gcloud beta services identity create --service=alloydb.googleapis.com --project="$PROJECT_ID" || true

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${ALLOYDB_SA}" \
    --role="roles/aiplatform.user" \
    --quiet

# 3. Create AlloyDB Cluster with Private Service Connect (PSC)
echo "[3/5] Creating AlloyDB Cluster '$CLUSTER_ID' with Private Service Connect..."
# Password for initial cluster creation (IAM authentication is enforced for connections)
ADMIN_PASS="$(openssl rand -base64 16 || echo 'AlloyDBInit#2026Pass')"

if ! gcloud alloydb clusters describe "$CLUSTER_ID" --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    gcloud alloydb clusters create "$CLUSTER_ID" \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --password="$ADMIN_PASS" \
        --enable-private-service-connect \
        --database-version=POSTGRES_16
    echo "Cluster '$CLUSTER_ID' created successfully."
else
    echo "Cluster '$CLUSTER_ID' already exists."
fi

# 4. Create 8 vCPU Single-Zone Primary Instance
echo "[4/5] Creating 8 vCPU primary instance '$INSTANCE_ID'..."
if ! gcloud alloydb instances describe "$INSTANCE_ID" --cluster="$CLUSTER_ID" --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    gcloud alloydb instances create "$INSTANCE_ID" \
        --cluster="$CLUSTER_ID" \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --instance-type=PRIMARY \
        --cpu-count="$CPU_COUNT" \
        --availability-type="$AVAILABILITY_TYPE" \
        --allowed-psc-projects="$PROJECT_ID" \
        --require-connectors \
        --ssl-mode=ENCRYPTED_ONLY \
        --database-flags="alloydb.iam_authentication=on,google_ml_integration.enable_model_support=on"
    echo "Instance '$INSTANCE_ID' created successfully."
else
    echo "Instance '$INSTANCE_ID' already exists."
fi

# 5. Output Summary and Managed MCP Details
echo "============================================================"
echo "AlloyDB Provisioning Complete!"
echo "Cluster:  projects/$PROJECT_ID/locations/$REGION/clusters/$CLUSTER_ID"
echo "Instance: projects/$PROJECT_ID/locations/$REGION/clusters/$CLUSTER_ID/instances/$INSTANCE_ID"
echo "Google Managed MCP Endpoint: https://alloydb.googleapis.com/mcp"
echo "============================================================"
