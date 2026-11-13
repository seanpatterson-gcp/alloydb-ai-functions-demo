"""FastAPI Application for AlloyDB AI Demo.

Exposes REST APIs and serves the interactive frontend dashboard to demonstrate
AlloyDB GA AI functions, Google ScaNN vector search, and Google Managed MCP server
integration.
"""

import logging
import os
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from app.ai_service import AlloyDBAIService
from app.mcp_client import AlloyDBManagedMCPClient

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("alloydb-ai-app")

app = FastAPI(
    title="AlloyDB AI & ScaNN Functions Showcase",
    description="Full-stack demo for AlloyDB GA AI Functions, ScaNN Indexing, and Google Managed MCP Server",
    version="1.0.0",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup Templates directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Initialize MCP Client & AI Service
mcp_client = AlloyDBManagedMCPClient()
ai_service = AlloyDBAIService(mcp_client=mcp_client)


# Pydantic Request Models
class SearchRequest(BaseModel):
    query_text: str
    limit: Optional[int] = 5
    min_views: Optional[int] = 0
    title_filter: Optional[str] = ""


class EmbeddingRequest(BaseModel):
    text: str
    model_id: Optional[str] = "text-embedding-005"


class PredictRequest(BaseModel):
    passage_id: int
    prompt: Optional[str] = "Provide a concise 2-sentence summary of this passage:"
    model_id: Optional[str] = "gemini-1.5-flash"


class ExplainRequest(BaseModel):
    sql: str


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """Serves the interactive web UI dashboard."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "project_id": mcp_client.project_id,
            "region": mcp_client.region,
            "instance": mcp_client.instance_id,
        },
    )


@app.post("/api/search")
async def api_vector_search(req: SearchRequest):
    """Executes ScaNN vector search and returns results, SQL, and EXPLAIN ANALYZE."""
    return ai_service.scann_vector_search(
        query_text=req.query_text,
        limit=req.limit or 5,
        min_views=req.min_views or 0,
        title_filter=req.title_filter or "",
    )


@app.post("/api/embedding")
async def api_generate_embedding(req: EmbeddingRequest):
    """Generates embedding using google_ml.embedding() via MCP."""
    return ai_service.generate_embedding(
        text=req.text,
        model_id=req.model_id or "text-embedding-005",
    )


@app.post("/api/predict")
async def api_predict_row(req: PredictRequest):
    """Executes in-database prediction using google_ml.predict_row() via MCP."""
    return ai_service.predict_row(
        passage_id=req.passage_id,
        prompt=req.prompt or "Provide a concise summary:",
        model_id=req.model_id or "gemini-1.5-flash",
    )


@app.post("/api/explain")
async def api_explain_query(req: ExplainRequest):
    """Runs EXPLAIN (ANALYZE, BUFFERS) on arbitrary SQL."""
    try:
        plan = mcp_client.explain_analyze(req.sql)
        return {"status": "success", "plan": plan}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/health")
async def health_check():
    """Health check endpoint for Cloud Run and monitoring."""
    status = mcp_client.check_connection()
    return {
        "status": "healthy",
        "mcp_server": "https://alloydb.googleapis.com/mcp",
        "instance": mcp_client.instance_resource,
        "connection_test": status,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
