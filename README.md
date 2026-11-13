# AlloyDB AI Functions & ScaNN Demo

A full-stack, enterprise-grade demo showcasing **Google Cloud AlloyDB for PostgreSQL** and all of its **Generally Available (GA)** AI capabilities.

The application frontend is built with **Python (FastAPI)**, deployed serverlessly on **Cloud Run**, and communicates with the AlloyDB cluster through the **Google Managed Model Context Protocol (MCP) Server** (`https://alloydb.googleapis.com/mcp`) using **Google Cloud IAM authentication**.

---

## Architecture Highlights

- **Database:** AlloyDB for PostgreSQL (PostgreSQL 16+), 8 vCPU, Single-Zone, in **Las Vegas (`us-west4`)**.
- **Connectivity:** **Private Service Connect (PSC)** with enforced connectors (`--require-connectors`).
- **Security:** Zero stored credentials or service account keys. Pure IAM authentication via Application Default Credentials (ADC) / Google Managed MCP Server.
- **AI Extensions & Indexes:**
  - `alloydb_scann`: Google ScaNN index configured with Scalar Quantization (`sq8`) for fast vector search on 768-dim embeddings.
  - `google_ml_integration`: Native in-database embedding generation (`google_ml.embedding()`) and model inference (`google_ml.predict_row()`).
  - `vector`: `pgvector` extension for vector operations.
- **Dataset:** **Cohere-10M** Wikipedia embeddings dataset (`id`, `title`, `text`, `url`, `views`, `langs`, `embedding`).
- **Observability:** Every query surfaces the exact generated SQL and full `EXPLAIN (ANALYZE, BUFFERS)` execution plan in the UI.

---

## Table of Contents

1. [Prerequisites & GCP Setup](#1-prerequisites--gcp-setup)
2. [Automated Infrastructure Provisioning](#2-automated-infrastructure-provisioning)
3. [Database Configuration & Extensions](#3-database-configuration--extensions)
4. [Dataset Loading (Cohere-10M)](#4-dataset-loading-cohere-10m)
5. [Deploying Frontend to Cloud Run](#5-deploying-frontend-to-cloud-run)
6. [How to Use the Application](#6-how-to-use-the-application)
7. [Repository & Git Storage](#7-repository--git-storage)

---

## 1. Prerequisites & GCP Setup

Ensure the following Google Cloud APIs are enabled in your project (e.g. `gcp-sandbox-sp`):

```bash
gcloud services enable \
    alloydb.googleapis.com \
    compute.googleapis.com \
    servicenetworking.googleapis.com \
    run.googleapis.com \
    aiplatform.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com
```

Grant the **AlloyDB Service Agent** permissions to call Vertex AI models:

```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUM=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

# Grant Vertex AI User to AlloyDB Service Agent
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:service-${PROJECT_NUM}@gcp-sa-alloydb.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"
```

---

## 2. Automated Infrastructure Provisioning

A complete provisioning script is provided in `infrastructure/provision_alloydb.sh` (or `.ps1` on Windows).

### AlloyDB Cluster & Instance Specs
- **Cluster ID:** `alloydb-ai-cluster`
- **Region:** `us-west4` (Las Vegas)
- **Networking:** Private Service Connect (`--enable-private-service-connect`)
- **Instance ID:** `alloydb-ai-primary`
- **Instance Type:** `PRIMARY`
- **CPU Count:** `8` vCPUs
- **Availability:** `ZONAL` (Single zone)
- **Database Flags:**
  - `alloydb.iam_authentication=on`
  - `google_ml_integration.enable_model_support=on`

Run the provisioning script:

```bash
# On Linux / macOS
chmod +x infrastructure/provision_alloydb.sh
./infrastructure/provision_alloydb.sh

# On Windows PowerShell
.\infrastructure\provision_alloydb.ps1
```

---

## 3. Database Configuration & Extensions

Connect to your database via AlloyDB Studio, Google Cloud Shell, or Auth Proxy, and enable the required extensions:

```sql
-- 1. Enable Vector & AI Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS alloydb_scann;
CREATE EXTENSION IF NOT EXISTS google_ml_integration CASCADE;

-- 2. Configure Model Support and AI Query Engine
SET google_ml_integration.enable_model_support = 'on';

-- 3. Register Vertex AI Gemini model endpoint (for google_ml.predict_row)
CALL google_ml.create_model(
    model_id => 'gemini-1.5-flash',
    model_provider => 'google',
    model_type => 'text',
    model_qualified_name => 'gemini-1.5-flash',
    model_auth_type => 'alloydb_service_agent_iam'
);
```

---

## 4. Dataset Loading (Cohere-10M)

The schema for the Cohere Wikipedia dataset is initialized in `data_loader/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS cohere_wikipedia (
    id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    url TEXT,
    views INTEGER DEFAULT 0,
    langs TEXT DEFAULT 'en',
    embedding vector(768) NOT NULL
);

-- Build Google ScaNN Index
CREATE INDEX IF NOT EXISTS cohere_scann_idx 
ON cohere_wikipedia 
USING scann (embedding vector_cosine_ops)
WITH (
    num_leaves = 1000,
    quantizer = 'sq8'
);
```

To load sample data or stream full chunks from Hugging Face:

```bash
pip install -r requirements.txt
python data_loader/load_cohere_sample.py --rows 50000
```

---

## 5. Deploying Frontend to Cloud Run

The Python application connects directly to the Google Managed AlloyDB MCP Server (`https://alloydb.googleapis.com/mcp`) via IAM credentials.

### Deploy with Cloud Build & Cloud Run:

```bash
# Set your environment variables
PROJECT_ID=$(gcloud config get-value project)
REGION="us-west4"
SERVICE_NAME="alloydb-ai-frontend"
ALLOYDB_INSTANCE="projects/${PROJECT_ID}/locations/${REGION}/clusters/alloydb-ai-cluster/instances/alloydb-ai-primary"

# Deploy container directly using Google Cloud Build
gcloud run deploy $SERVICE_NAME \
    --source . \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars="GCP_PROJECT=${PROJECT_ID},ALLOYDB_REGION=${REGION},ALLOYDB_INSTANCE=${ALLOYDB_INSTANCE},ALLOYDB_DATABASE=postgres"
```

---

## 6. How to Use the Application

Once deployed (or running locally with `python app/main.py`), open the service URL in your browser:

### 1. **Embedding Generator (`google_ml.embedding`)**
- Enter any search phrase or paragraph (e.g., *"Quantum algorithms for graph isomorphism"*).
- Click **"Generate Embedding"**.
- View the resulting 768-dimensional float array and the exact SQL executed:
  ```sql
  SELECT google_ml.embedding('text-embedding-005', 'Quantum algorithms for graph isomorphism');
  ```

### 2. **ScaNN Semantic Vector Search**
- Type a natural language query and choose Top-$K$ (e.g. 5, 10, 25).
- The application generates the query embedding and performs nearest-neighbor vector search over the Cohere-10M dataset.
- View article title, passage text, views, and cosine similarity score ($1 - \text{distance}$).
- Inspect the generated SQL:
  ```sql
  SELECT id, title, text, views, 1 - (embedding <=> $1) AS similarity
  FROM cohere_wikipedia
  ORDER BY embedding <=> $1
  LIMIT 10;
  ```

### 3. **Hybrid Search (ScaNN + Structured SQL Filters)**
- Combine semantic similarity with relational predicates (e.g., article views $> 50,000$ or title matches).
- Observe how AlloyDB optimizes the joint execution of index scans with relational filter conditions.

### 4. **In-Database LLM Predictions (`google_ml.predict_row`)**
- Select a Wikipedia article chunk and test in-database Gemini inference to summarize or extract insights directly in SQL without leaving the database:
  ```sql
  SELECT google_ml.predict_row(
      model_id => 'gemini-1.5-flash',
      request_body => json_build_object('contents', json_build_array(
          json_build_object('role', 'user', 'parts', json_build_array(
              json_build_object('text', 'Summarize this passage in 2 bullets: ' || text)
          ))
      ))
  ) FROM cohere_wikipedia WHERE id = 1001;
  ```

### 5. **Execution Plan & Performance Lab (`EXPLAIN ANALYZE`)**
- Every query view includes an **"EXPLAIN ANALYZE"** tab.
- Inspect:
  - ScaNN Index Scan vs. Sequential Scan verification.
  - Planning and Execution time in milliseconds.
  - Shared hit buffers and memory footprint.

---

## 7. Repository & Git Storage

This project is configured to push to:
`https://github.com/seanpatterson-gcp/alloydb-ai-functions-demo`

To authenticate and push to your GitHub:

```bash
# 1. Login to GitHub CLI (if not already authenticated)
gh auth login

# 2. Create the remote repository under seanpatterson-gcp
gh repo create seanpatterson-gcp/alloydb-ai-functions-demo --public --source=. --remote=origin --push

# Or push directly via git:
git push -u origin main
```
