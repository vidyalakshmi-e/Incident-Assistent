"""LLM client (FALLBACKS §1).

Providers:
  openai — any OpenAI-compatible /chat/completions endpoint (OpenAI, NVIDIA NIM, Ollama, LM Studio)
  local  — a Hugging Face instruct model run in-process (no key needed; GPU recommended)
  none   — force retrieval-only mode

If the key is missing, the provider cannot be reached, or a call fails, `available` is False (or
`complete` returns None) and callers switch to "Retrieval-only mode — LLM unavailable". The app
never crashes because of the LLM. Responses are cached on disk to avoid repeated calls.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path

from backend.config.settings import Settings, get_settings

log = logging.getLogger(__name__)

RETRIEVAL_ONLY_LABEL = "Retrieval-only mode — LLM unavailable"


class LLMClient:
    def __init__(self, settings: Settings | None = None, read_cache: bool = True):
        """read_cache=False forces live calls (still written to the cache) — evaluation uses it so LLM
        latency is measured on real generations, not on cache lookups."""
        self.s = settings or get_settings()
        self.read_cache = read_cache
        self.provider = (self.s.llm_provider or "none").lower()
        self.model = self.s.llm_model
        self.unavailable_reason: str | None = None
        self.calls = 0
        self.cache_hits = 0
        self._lock = threading.Lock()
        self._local = None
        self._cache_path = Path(self.s.processed_dir) / "llm_cache.jsonl"
        self._cache: dict[str, str] = {}
        self._load_cache()
        if self.provider == "none":
            self.unavailable_reason = "LLM disabled (LLM_PROVIDER=none)"
        elif self.provider == "openai" and not self.s.llm_api_key.strip():
            self.unavailable_reason = "LLM_API_KEY is not set"
        elif self.provider not in {"openai", "local"}:
            self.unavailable_reason = f"unknown LLM_PROVIDER '{self.provider}'"
        if self.unavailable_reason:
            log.warning("LLM unavailable: %s → retrieval-only mode", self.unavailable_reason)

    # ------------------------------------------------------------------ status
    @property
    def available(self) -> bool:
        return self.unavailable_reason is None

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model}" if self.available else "none"

    def status(self) -> dict:
        return {"available": self.available, "provider": self.provider, "model": self.model,
                "reason": self.unavailable_reason, "calls": self.calls, "cache_hits": self.cache_hits}

    # ------------------------------------------------------------------ cache
    def _load_cache(self) -> None:
        if self._cache_path.exists():
            for line in self._cache_path.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                    self._cache[rec["k"]] = rec["v"]
                except (json.JSONDecodeError, KeyError):
                    continue

    def _key(self, system: str, prompt: str, max_tokens: int) -> str:
        raw = json.dumps([self.provider, self.model, system, prompt, max_tokens])
        return hashlib.sha256(raw.encode()).hexdigest()

    def _store(self, k: str, v: str) -> None:
        self._cache[k] = v
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self._cache_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"k": k, "v": v}) + "\n")
        except OSError:
            pass

    # ------------------------------------------------------------------ calls
    def complete(self, prompt: str, system: str = "You are a careful IT operations assistant.",
                 max_tokens: int | None = None, purpose: str = "") -> str | None:
        """Return the completion text, or None if the LLM is unavailable or the call failed."""
        if not self.available:
            return None
        max_tokens = max_tokens or self.s.llm_max_tokens
        k = self._key(system, prompt, max_tokens)
        if self.read_cache and k in self._cache:
            self.cache_hits += 1
            return self._cache[k]
        try:
            t = time.perf_counter()
            with self._lock:
                out = self._local_complete(system, prompt, max_tokens) if self.provider == "local" \
                    else self._http_complete(system, prompt, max_tokens)
            self.calls += 1
            log.info("LLM call (%s) %.0f ms", purpose or "-", (time.perf_counter() - t) * 1000)
        except Exception as exc:  # noqa: BLE001 — degrade, never crash
            log.warning("LLM call failed (%s): %s", purpose, exc)
            return None
        self._store(k, out)
        return out

    def _http_complete(self, system: str, prompt: str, max_tokens: int) -> str:
        import httpx

        r = httpx.post(
            self.s.llm_base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {self.s.llm_api_key}"},
            json={"model": self.model, "temperature": self.s.llm_temperature, "max_tokens": max_tokens,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
            timeout=self.s.llm_timeout_s,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def _local_complete(self, system: str, prompt: str, max_tokens: int) -> str:
        if self._local is None:
            os.environ.setdefault("USE_TF", "0")
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            try:
                tok = AutoTokenizer.from_pretrained(self.model)
                dtype = torch.float16 if torch.cuda.is_available() else torch.float32
                model = AutoModelForCausalLM.from_pretrained(self.model, torch_dtype=dtype)
                model.to("cuda" if torch.cuda.is_available() else "cpu").eval()
            except Exception as exc:  # noqa: BLE001
                self.unavailable_reason = f"local model '{self.model}' could not be loaded ({exc})"
                raise
            self._local = (tok, model, torch)
        tok, model, torch = self._local
        text = tok.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                                       tokenize=False, add_generation_prompt=True)
        enc = tok(text, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=max_tokens, do_sample=False,
                                 pad_token_id=tok.pad_token_id or tok.eos_token_id)
        return tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()
