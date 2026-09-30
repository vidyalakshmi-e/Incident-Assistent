"""Central configuration.

All values can be overridden through environment variables or a `.env` file at the project root.
Nothing here holds a credential; keys are read from the environment only.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

logger = logging.getLogger("incident_intel")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # ---------------- LLM (optional: without a key the app runs in retrieval-only mode) ----------------
    # "openai" = any OpenAI-compatible HTTP endpoint (OpenAI, NVIDIA NIM, Ollama, LM Studio ...)
    # "local"  = a Hugging Face instruct model run in-process with transformers
    # "none"   = force retrieval-only mode
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_s: float = 45.0
    llm_temperature: float = 0.1
    llm_max_tokens: int = 500
    llm_max_tokens_cap: int = 500  # the lab gateway rejects max_tokens above 500 (HTTP 422)

    # ---------------- Embeddings ----------------
    embedding_provider: str = "local"  # local | openai | nvidia
    embedding_model_local: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_model_openai: str = "text-embedding-3-small"
    embedding_model_nvidia: str = "nvidia/nv-embedqa-e5-v5"
    openai_api_key: str = ""
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"

    # ---------------- Reranker ----------------
    reranker_provider: str = "local"  # local | nvidia | none
    reranker_model_local: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_model_nvidia: str = "nvidia/nv-rerankqa-mistral-4b-v3"

    # ---------------- Vector store ----------------
    chroma_mode: str = "embedded"  # embedded | http
    chroma_path: str = str(PROJECT_ROOT / "vectorstore")
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "incident_kb"

    # ---------------- Storage ----------------
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'processed' / 'incidents.db').as_posix()}"
    data_dir: str = str(PROJECT_ROOT / "data")

    # ---------------- Retrieval ----------------
    rrf_k: int = 60
    retrieval_candidates: int = 50  # per retriever before fusion
    rerank_top_n: int = 30  # fused candidates sent to the cross-encoder
    default_top_k: int = 10

    # ---------------- Troubleshooting / clarification ----------------
    troubleshooting_max_rounds: int = 3
    clarification_confidence_threshold: float = 0.45
    clarification_vague_max_tokens: int = 9
    clarification_family_margin: float = 0.08
    max_clarifications_per_session: int = 1

    # ---------------- Escalation ----------------
    # Keep the tier order configurable (prompt: confirm direction against the grading rubric).
    escalation_tiers: str = "L1,L2,L3"

    # ---------------- Live correlation ----------------
    correlation_window_minutes: int = 30
    correlation_min_incidents: int = 2
    correlation_similarity_threshold: float = 0.55

    # ---------------- Knowledge base evolution ----------------
    kb_quality_threshold: float = 0.55

    # ---------------- Misc ----------------
    random_seed: int = 42
    log_level: str = "INFO"
    api_url: str = "http://localhost:8000"

    @property
    def tiers(self) -> list[str]:
        return [t.strip() for t in self.escalation_tiers.split(",") if t.strip()]

    @property
    def processed_dir(self) -> Path:
        return Path(self.data_dir) / "processed"

    @property
    def raw_dir(self) -> Path:
        return Path(self.data_dir) / "raw"

    @property
    def evaluation_dir(self) -> Path:
        return Path(self.data_dir) / "evaluation"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    logging.basicConfig(
        level=getattr(logging, s.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return s


def calibration_available(name: str) -> bool:
    path = Path(get_settings().evaluation_dir) / "calibration.json"
    try:
        return name in json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return False


def load_calibrated(name: str, default: float) -> float:
    """Read a threshold that was calibrated by an evaluation script (e.g. the novelty threshold).

    Thresholds are chosen on validation data (see backend/evaluation) and written to
    data/evaluation/calibration.json, so they are never hand-picked constants in code.
    """
    path = Path(get_settings().evaluation_dir) / "calibration.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return float(data[name]["value"])
    except (FileNotFoundError, KeyError, ValueError, TypeError):
        return default
