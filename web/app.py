"""Web dashboard — read-only monitoring of Claude Code sessions.

Routes:
  GET /                       -> serves the HTML dashboard page
  GET /api/overview           -> JSON data for polling (every 30s)
  GET /api/session/{session_id} -> single session detail

All API errors return consistent JSON: {"error": "message", "code": "ERROR_CODE"}
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

# Ensure lib is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store

logger = logging.getLogger(__name__)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

_HTML_PATH = Path(__file__).parent / "index.html"


# ---------------------------------------------------------------------------
# Error response helper
# ---------------------------------------------------------------------------


def _error_response(message: str, code: str, status_code: int) -> JSONResponse:
    return JSONResponse({"error": message, "code": code}, status_code=status_code)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return _error_response(str(exc), "VALIDATION_ERROR", 400)


@app.exception_handler(json.JSONDecodeError)
async def json_decode_error_handler(request: Request, exc: json.JSONDecodeError):
    logger.error("Corrupt JSON data: %s", exc)
    return _error_response("Data store contains corrupt JSON", "DATA_CORRUPT", 500)


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s: %s", request.url.path, exc, exc_info=True)
    return _error_response("Internal server error", "INTERNAL_ERROR", 500)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
def index():
    return FileResponse(_HTML_PATH, media_type="text/html")


@app.get("/api/overview")
def api_overview():
    return JSONResponse(store.build_overview())


@app.get("/api/session/{session_id}")
def api_session_detail(session_id: str):
    session = store.get_session(session_id)
    if not session:
        return _error_response("Session not found", "NOT_FOUND", 404)
    return JSONResponse(asdict(session))
