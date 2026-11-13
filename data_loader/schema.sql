-- ============================================================================
-- AlloyDB AI Schema Setup & Extension Initialization
-- ============================================================================

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS alloydb_scann;
CREATE EXTENSION IF NOT EXISTS google_ml_integration CASCADE;

-- 2. Configure Runtime Flags
SET google_ml_integration.enable_model_support = 'on';

-- 3. Cohere-10M Dataset Table
CREATE TABLE IF NOT EXISTS cohere_wikipedia (
    id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    url TEXT,
    views INTEGER DEFAULT 0,
    langs TEXT DEFAULT 'en',
    embedding vector(768) NOT NULL
);

-- 4. B-Tree Indexes for Relational & Hybrid Predicates
CREATE INDEX IF NOT EXISTS idx_cohere_views ON cohere_wikipedia (views);
CREATE INDEX IF NOT EXISTS idx_cohere_title ON cohere_wikipedia (title);

-- 5. Google ScaNN Index for Vector Search
-- Configured with 1000 centroids (num_leaves) and 8-bit scalar quantization (sq8)
CREATE INDEX IF NOT EXISTS cohere_scann_idx 
ON cohere_wikipedia 
USING scann (embedding vector_cosine_ops)
WITH (
    num_leaves = 1000,
    quantizer = 'sq8'
);

-- 6. Register Vertex AI Gemini Foundation Model for In-Database Predictions
CALL google_ml.create_model(
    model_id => 'gemini-1.5-flash',
    model_provider => 'google',
    model_type => 'text',
    model_qualified_name => 'gemini-1.5-flash',
    model_auth_type => 'alloydb_service_agent_iam'
);
