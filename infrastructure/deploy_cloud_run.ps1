# PowerShell deploy script for Cloud Run
param (
    [string]$ProjectId = $(gcloud config get-value project),
    [string]$Region = "us-west4",
    [string]$ServiceName = "alloydb-ai-frontend",
    [string]$ClusterId = "alloydb-ai-cluster",
    [string]$InstanceId = "alloydb-ai-primary"
)

$ErrorActionPreference = "Stop"

$alloydbInstance = "projects/$ProjectId/locations/$Region/clusters/$ClusterId/instances/$InstanceId"

Write-Host "Deploying AlloyDB AI Frontend to Cloud Run ($Region)..." -ForegroundColor Cyan

# Deploy directly via gcloud run deploy
gcloud run deploy $ServiceName `
    --source . `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --set-env-vars="GCP_PROJECT=$ProjectId,ALLOYDB_REGION=$Region,ALLOYDB_CLUSTER=$ClusterId,ALLOYDB_INSTANCE=$alloydbInstance,ALLOYDB_DATABASE=postgres"

$url = gcloud run services describe $ServiceName --region $Region --format="value(status.url)"
Write-Host "Deployment Successful! Service URL: $url" -ForegroundColor Green
