"""FastAPI application — AI-Powered Incident Intelligence & Knowledge Base Assistant.

Run: uvicorn backend.main:app --port 8000   (Swagger UI at /docs)
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

try:  # Windows: torch must load its DLLs before onnxruntime/chromadb, else WinError 1114
    import torch  # noqa: F401
except Exception:  # noqa: BLE001
    pass

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend.api.routes import router  # noqa: E402
from backend.config.settings import get_settings  # noqa: E402
from backend.database.session import init_db  # noqa: E402

log = logging.getLogger("incident_intel")


def _warm_up() -> None:
    """Load models and indexes so the first request is not slow. Failures are logged, never fatal."""
    try:
        from backend.services.platform import get_platform

        from backend.knowledge.indexer import ensure_vector_index

        p = get_platform()
        log.info("vector index: %s", ensure_vector_index(p.rt))
        p.health()
        p.search("warm-up query: application slow", top_k=3)
        log.info("warm-up complete")
    except Exception:  # noqa: BLE001
        log.exception("warm-up failed (the API stays up; components will load lazily)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()
    init_db()
    if os.environ.get("SKIP_WARMUP") != "1":
        threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(
    title="Incident Intelligence Platform API",
    description=("An AI-powered Incident Intelligence and Troubleshooting platform: hybrid retrieval, incident "
                 "pattern intelligence (with causal chains), novel-incident detection, live correlation, resolution "
                 "strategy intelligence, evidence chains, guided troubleshooting and an evolving knowledge base."),
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
