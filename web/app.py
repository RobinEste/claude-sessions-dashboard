"""Web dashboard — read-only monitoring of Claude Code sessions.

Two routes:
  GET /            -> serves the HTML dashboard page
  GET /api/overview -> JSON data for polling (every 30s)
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

# Ensure lib is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

_HTML_PATH = Path(__file__).parent / "index.html"


@app.get("/")
def index():
    return FileResponse(_HTML_PATH, media_type="text/html")


@app.get("/api/overview")
def api_overview():
    return JSONResponse(store.build_overview())


@app.get("/api/session/{session_id}")
def api_session_detail(session_id: str):
    try:
        session = store.get_session(session_id)
    except ValueError:
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    if not session:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return JSONResponse(asdict(session))
