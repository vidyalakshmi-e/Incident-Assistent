"""Shared fixtures.

Unit tests need nothing but the code. Tests marked `integration` need the built artefacts
(`python scripts/build_all.py`) and the local models; they are skipped when artefacts are missing.
All tests write to a temporary SQLite database, never to the demo database or the real vector store.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="incident_intel_tests_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ["SKIP_WARMUP"] = "1"
os.environ["LLM_PROVIDER"] = "openai"
os.environ["LLM_API_KEY"] = ""  # tests exercise retrieval-only mode deterministically

ARTEFACTS = ROOT / "data" / "processed" / "kb_records.parquet"


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: needs built artefacts + local models")
    config.addinivalue_line("markers", "slow: long-running")


def pytest_collection_modifyitems(config, items):
    if not ARTEFACTS.exists():
        skip = pytest.mark.skip(reason="artefacts not built — run python scripts/build_all.py")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(scope="session")
def db():
    from backend.database.session import init_db

    return init_db()


@pytest.fixture(scope="session")
def rt(db):
    from backend.services.runtime import get_runtime

    return get_runtime()


@pytest.fixture(scope="session")
def platform(rt):
    from backend.services.platform import get_platform

    return get_platform()


@pytest.fixture(scope="session")
def client(platform):
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def no_vector_writes(rt, monkeypatch):
    """KB-evolution tests must not write into the real ChromaDB collection, nor into the real
    pattern files (patterns.json / fingerprints.json): the test DB is temporary, those files are not,
    so a saved test incident would show up as a family whose members do not exist."""
    calls = []
    monkeypatch.setattr(rt.vectors, "upsert", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(rt.patterns, "save", lambda *a, **k: None)
    return calls


DEMO = ("The application is becoming slower and sometimes freezes when users try to open records. "
        "Restarting fixes it temporarily.")
