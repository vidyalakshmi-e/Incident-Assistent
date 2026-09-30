"""LLM client.

Providers:
  openai — any OpenAI-compatible /chat/completions endpoint (OpenAI, NVIDIA NIM, Ollama, LM Studio)
  local  — a Hugging Face instruct model run in-process (no key needed; GPU recommended)
  none   — force retrieval-only mode

If the key is missing, the provider cannot be reached, or a call fails, `available` is False (or
`complete` returns None) and callers switch to "Retrieval-only mode — LLM unavailable". The app
never crashes because of the LLM. Responses are cached on disk to avoid repeated calls.

A key that is set but does not work (wrong gateway URL, wrong model, expired key) is detected: after
FAIL_LIMIT failed calls in a row the client reports itself unavailable, with the last error as the reason,
so the UI shows the retrieval-only label instead of claiming full mode. It tries again after COOLDOWN_S.
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
FAIL_LIMIT = 3  # consecutive failed calls before the client stops trying
COOLDOWN_S = 120.0  # then it waits this long before trying again


def _looks_like_key(value: str) -> bool:
    """API keys are one ASCII token. Text with spaces, '#' or non-ASCII characters is a pasted comment or
    placeholder (python-dotenv keeps `KEY=# comment` as the value), which would otherwise be sent as a bearer token."""
    v = value.strip()
    return v.isascii() and v.isprintable() and not any(c.isspace() for c in v) and not v.startswith("#")


def _short_error(exc: Exception) -> str:
    """HTTP status + reason for endpoint errors (401 = bad key, 404 = wrong URL or model), else the message."""
    resp = getattr(exc, "response", None)
    if resp is not None:
        return f"HTTP {resp.status_code} from {resp.request.url.host}"
    return f"{type(exc).__name__}: {exc}"[:160]


def parse_json_reply(text: str) -> dict | list | None:
    """Pull the first JSON object/array out of a model reply (fenced or surrounded by prose)."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = s.find(opener), s.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


class LLMClient:
    def __init__(self, settings: Settings | None = None, read_cache: bool = True):
        """read_cache=False forces live calls (still written to the cache) — evaluation uses it so LLM
        latency is measured on real generations, not on cache lookups."""
        self.s = settings or get_settings()
        self.read_cache = read_cache
        self.provider = (self.s.llm_provider or "none").lower()
        self.model = self.s.llm_model
        self._static_reason: str | None = None  # configuration problem: needs a restart
        self._tripped_at: float | None = None  # runtime problem: calls kept failing
        self.last_error: str | None = None
        self.consecutive_failures = 0
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
        elif self.provider == "openai" and not _looks_like_key(self.s.llm_api_key):
            self.unavailable_reason = ("LLM_API_KEY does not look like a key (it has spaces or non-ASCII characters; "
                                       "a comment on the same line in .env can end up as the value)")
        elif self.provider not in {"openai", "local"}:
            self.unavailable_reason = f"unknown LLM_PROVIDER '{self.provider}'"
        if self.unavailable_reason:
            log.warning("LLM unavailable: %s → retrieval-only mode", self.unavailable_reason)

    # ------------------------------------------------------------------ status
    @property
    def unavailable_reason(self) -> str | None:
        if self._static_reason:
            return self._static_reason
        if self._tripped_at is not None:
            if time.time() - self._tripped_at < COOLDOWN_S:
                return f"the LLM endpoint keeps failing ({self.last_error}); retrying in a couple of minutes"
            self._tripped_at, self.consecutive_failures = None, 0  # cooldown over: give it another go
        return None

    @unavailable_reason.setter
    def unavailable_reason(self, value: str | None) -> None:
        self._static_reason = value

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model or 'server-default'}" if self.available else "none"

    def status(self) -> dict:
        return {"available": self.available, "provider": self.provider, "model": self.model,
                "base_url": self.s.llm_base_url if self.provider == "openai" else None,
                "reason": self.unavailable_reason, "last_error": self.last_error,
                "calls": self.calls, "cache_hits": self.cache_hits}

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
            if self.provider == "local":
                with self._lock:  # one in-process model: generations must not overlap
                    out = self._local_complete(system, prompt, max_tokens)
            else:  # HTTP calls are independent, so guidance for several candidates can run side by side
                out = self._http_complete(system, prompt, max_tokens)
            self.calls += 1
            self.consecutive_failures = 0
            self.last_error = None
            log.info("LLM call (%s) %.0f ms", purpose or "-", (time.perf_counter() - t) * 1000)
        except Exception as exc:  # noqa: BLE001 — degrade, never crash
            self.last_error = _short_error(exc)
            self.consecutive_failures += 1
            if self.consecutive_failures >= FAIL_LIMIT and self._tripped_at is None:
                self._tripped_at = time.time()
            log.warning("LLM call failed (%s): %s", purpose, self.last_error)
            return None
        self._store(k, out)
        return out

    def complete_json(self, prompt: str, system: str = "You are a careful IT operations assistant.",
                      max_tokens: int | None = None, purpose: str = "") -> dict | list | None:
        """`complete`, parsed as JSON. Models often wrap JSON in ``` fences or add a sentence around it; both are
        tolerated. Returns None when the LLM is unavailable or the reply is not valid JSON."""
        out = self.complete(prompt, system=system + " Reply with a single JSON value and nothing else.",
                            max_tokens=max_tokens, purpose=purpose)
        return parse_json_reply(out) if out else None

    def _http_complete(self, system: str, prompt: str, max_tokens: int) -> str:
        import httpx

        body = {"temperature": self.s.llm_temperature, "max_tokens": min(max_tokens, self.s.llm_max_tokens_cap),
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if self.model:  # a blank LLM_MODEL lets a gateway pick the model on the server
            body["model"] = self.model
        r = httpx.post(
            self.s.llm_base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {self.s.llm_api_key}"},
            json=body,
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
