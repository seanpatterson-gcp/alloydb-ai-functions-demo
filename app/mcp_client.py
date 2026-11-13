"""Google Managed AlloyDB Model Context Protocol (MCP) Client.

Connects to https://alloydb.googleapis.com/mcp to execute SQL statements,
introspect schemas, and retrieve EXPLAIN ANALYZE execution plans using pure
IAM authentication (Application Default Credentials / Service Account).
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
import google.auth
import google.auth.transport.requests
import httpx

logger = logging.getLogger("alloydb-mcp-client")
logger.setLevel(logging.INFO)

MCP_SERVER_URL = "https://alloydb.googleapis.com/mcp"


class AlloyDBManagedMCPClient:
    """Client for Google Cloud's remote managed AlloyDB MCP Server."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        region: Optional[str] = None,
        cluster_id: Optional[str] = None,
        instance_id: Optional[str] = None,
        database: str = "postgres",
    ):
        self.project_id = project_id or os.environ.get("GCP_PROJECT", "gcp-sandbox-sp")
        self.region = region or os.environ.get("ALLOYDB_REGION", "us-west4")
        self.cluster_id = cluster_id or os.environ.get("ALLOYDB_CLUSTER", "alloydb-ai-cluster")
        self.instance_id = instance_id or os.environ.get("ALLOYDB_INSTANCE_ID", "alloydb-ai-primary")
        self.database = database or os.environ.get("ALLOYDB_DATABASE", "postgres")

        # Full resource name format expected by MCP server:
        # projects/{project}/locations/{region}/clusters/{cluster}/instances/{instance}
        if "projects/" in self.instance_id:
            self.instance_resource = self.instance_id
        else:
            self.instance_resource = (
                f"projects/{self.project_id}/locations/{self.region}/"
                f"clusters/{self.cluster_id}/instances/{self.instance_id}"
            )

        self._credentials = None
        self._auth_request = google.auth.transport.requests.Request()
        self._init_credentials()

    def _init_credentials(self):
        """Initializes Google Cloud IAM credentials via Application Default Credentials."""
        try:
            self._credentials, project = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            if not self.project_id and project:
                self.project_id = project
            logger.info(f"Initialized Google Auth credentials for project '{self.project_id}'")
        except Exception as e:
            logger.warning(f"Could not load Google Application Default Credentials: {e}")

    def _get_bearer_token(self) -> str:
        """Retrieves and refreshes the OAuth2 access token for IAM authentication."""
        if not self._credentials:
            self._init_credentials()
        if not self._credentials:
            raise RuntimeError("No Google Cloud Application Default Credentials available.")

        if not self._credentials.valid:
            self._credentials.refresh(self._auth_request)

        return self._credentials.token

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Calls a tool on the Google Managed AlloyDB MCP server via JSON-RPC."""
        token = self._get_bearer_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
            "id": int(time.time() * 1000),
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(MCP_SERVER_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

                if "error" in data:
                    logger.error(f"MCP Server error: {data['error']}")
                    raise RuntimeError(f"MCP Error: {data['error'].get('message', data['error'])}")

                return data.get("result", {})
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling AlloyDB MCP server: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to call MCP tool '{tool_name}': {e}")
            raise

    def execute_sql(self, sql_statement: str, validate_only: bool = False) -> Dict[str, Any]:
        """Executes a SQL query on the AlloyDB instance using the MCP server's execute_sql tool."""
        args = {
            "instance": self.instance_resource,
            "database": self.database,
            "sqlStatement": sql_statement,
            "validateOnly": validate_only,
        }
        return self.call_tool("execute_sql", args)

    def explain_analyze(self, sql_statement: str) -> Dict[str, Any]:
        """Wraps any query with EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) and executes it."""
        clean_sql = sql_statement.strip().rstrip(";")
        explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, COSTS, VERBOSE, FORMAT JSON) {clean_sql};"
        return self.execute_sql(explain_sql)

    def check_connection(self) -> Dict[str, Any]:
        """Validates that the MCP server endpoint responds and can communicate with AlloyDB."""
        try:
            res = self.execute_sql("SELECT version() AS pg_version, current_database() AS db;")
            return {"status": "connected", "details": res}
        except Exception as e:
            return {"status": "degraded_or_offline", "error": str(e)}
