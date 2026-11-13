# PowerShell script for AlloyDB provisioning in Las Vegas (us-west4)
param (
    [string]$ProjectId = $(gcloud config get-value project),
    [string]$Region = "us-west4",
    [string]$ClusterId = "alloydb-ai-cluster",
    [string]$InstanceId = "alloydb-ai-primary",
    [int]$CpuCount = 8
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Provisioning AlloyDB for PostgreSQL (Las Vegas, 8 vCPU, PSC)" -ForegroundColor Cyan
Write-Host "Project: $ProjectId"
Write-Host "Region:  $Region"
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Enable Required Services
Write-Host "[1/5] Enabling GCP APIs..." -ForegroundColor Yellow
gcloud services enable `
    alloydb.googleapis.com `
    compute.googleapis.com `
    servicenetworking.googleapis.com `
    run.googleapis.com `
    aiplatform.googleapis.com `
    artifactregistry.googleapis.com `
    cloudbuild.googleapis.com `
    --project=$ProjectId

# 2. Configure Service Agent IAM for Vertex AI
Write-Host "[2/5] Configuring AlloyDB Service Agent permissions for Vertex AI..." -ForegroundColor Yellow
$projectNumber = gcloud projects describe $ProjectId --format="value(projectNumber)"
$alloydbSa = "service-${projectNumber}@gcp-sa-alloydb.iam.gserviceaccount.com"

# Create identity if not present
gcloud beta services identity create --service=alloydb.googleapis.com --project=$ProjectId 2>$null

gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:${alloydbSa}" `
    --role="roles/aiplatform.user" `
    --quiet

# 3. Create AlloyDB Cluster with Private Service Connect (PSC)
Write-Host "[3/5] Creating AlloyDB Cluster '$ClusterId' with Private Service Connect..." -ForegroundColor Yellow
$adminPass = [System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(16))

$existingCluster = gcloud alloydb clusters describe $ClusterId --region=$Region --project=$ProjectId 2>$null
if (-not $existingCluster) {
    gcloud alloydb clusters create $ClusterId `
        --region=$Region `
        --project=$ProjectId `
        --password=$adminPass `
        --enable-private-service-connect `
        --database-version=POSTGRES_16
    Write-Host "Cluster '$ClusterId' created." -ForegroundColor Green
} else {
    Write-Host "Cluster '$ClusterId' already exists." -ForegroundColor Gray
}

# 4. Create 8 vCPU Single-Zone Primary Instance
Write-Host "[4/5] Creating 8 vCPU primary instance '$InstanceId'..." -ForegroundColor Yellow
$existingInstance = gcloud alloydb instances describe $InstanceId --cluster=$ClusterId --region=$Region --project=$ProjectId 2>$null
if (-not $existingInstance) {
    gcloud alloydb instances create $InstanceId `
        --cluster=$ClusterId `
        --region=$Region `
        --project=$ProjectId `
        --instance-type=PRIMARY `
        --cpu-count=$CpuCount `
        --availability-type=ZONAL `
        --allowed-psc-projects=$ProjectId `
        --require-connectors `
        --ssl-mode=ENCRYPTED_ONLY `
        --database-flags="alloydb.iam_authentication=on,google_ml_integration.enable_model_support=on"
    Write-Host "Instance '$InstanceId' created." -ForegroundColor Green
} else {
    Write-Host "Instance '$InstanceId' already exists." -ForegroundColor Gray
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AlloyDB Provisioning Complete!" -ForegroundColor Green
Write-Host "Managed MCP Server: https://alloydb.googleapis.com/mcp"
Write-Host "Instance: projects/$ProjectId/locations/$Region/clusters/$ClusterId/instances/$InstanceId"
Write-Host "============================================================" -ForegroundColor Cyan
