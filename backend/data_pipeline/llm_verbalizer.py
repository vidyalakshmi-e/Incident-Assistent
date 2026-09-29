"""LLM verbalizer: an LLM writes the ticket text from a conditioned brief.

The brief (scenario, strategy, real CI name, real impact/urgency phrasing, trigger, note quality)
is fixed by `synthetic.plan_synthetic_rows`; the LLM only chooses the *wording*. That keeps the
generated text statistically tied to the real structured fields while giving natural variety.

Outputs are cached in `data/processed/synthetic_text_cache.jsonl`, keyed by the brief hash, so a
rebuild reproduces the exact same dataset without a GPU or API key.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from backend.data_pipeline.synthetic import Brief, TemplateVerbalizer

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You write realistic IT service-desk ticket text for a bank's incident management system. "
    "You only use the facts you are given and never invent new systems, product names, people or numbers. "
    "You answer with a single JSON object and nothing else."
)

VIEW_DESCRIPTIONS = {
    "user": "an employee describing what they experience, in plain non-technical language, without naming the technical root cause",
    "monitoring": "an automated monitoring alert message, terse and factual",
    "engineer": "a support engineer's technical observation of the symptoms",
}


def build_prompt(b: Brief) -> str:
    lines = [
        "Write the ticket text for ONE incident using these facts.",
        f"Reporter perspective: {VIEW_DESCRIPTIONS[b.view]}.",
        f"Affected service: {b.service}",
        f"Configuration item name: {b.ci}",
        f'What is observed (rephrase in your own words, keep the meaning): "{b.symptom_seed}"',
    ]
    if b.trigger:
        lines.append(f'When it started: "{b.trigger}"')
    if b.scope_sentence:
        lines.append(f'Who is affected: "{b.scope_sentence}"')
    if b.urgency_sentence:
        lines.append(f'Urgency: "{b.urgency_sentence}"')
    if b.environment:
        lines.append(f"Environment: {b.environment}")
    if b.seeded_defect == "contradiction":
        lines.append(f'Resolution facts (engineer voice, past tense): "{b.note_seed}"')
    else:
        lines.append(
            f"Resolution facts (engineer voice, past tense): the root cause was {b.root_cause}; "
            f'action taken: {b.strategy_label}; details: "{b.note_seed}"'
        )
    if b.reassignments >= 3:
        lines.append("Mention in the resolution notes that the ticket went through several teams.")
    lines += [
        "",
        'Return JSON with exactly these keys: "title" (max 8 words), '
        '"description" (1-3 sentences, reporter perspective), '
        '"resolution_notes" (2-3 sentences, past tense).',
    ]
    return "\n".join(lines)


_JSON = re.compile(r"\{.*\}", re.S)


def parse_output(text: str) -> dict[str, str] | None:
    m = _JSON.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    out = {k: str(data.get(k, "")).strip() for k in ("title", "description", "resolution_notes")}
    if not out["description"] or not out["resolution_notes"] or not out["title"]:
        return None
    return out


class TextCache:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.data[rec["key"]] = rec

    def get(self, key: str) -> dict | None:
        return self.data.get(key)

    def put_many(self, recs: list[dict]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            for r in recs:
                self.data[r["key"]] = r
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")


class LocalHFBatchGenerator:
    """Batched generation with a local Hugging Face instruct model (GPU if available)."""

    def __init__(self, model_id: str, seed: int = 42):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.model_id = model_id
        self.seed = seed
        self.tok = AutoTokenizer.from_pretrained(model_id, padding_side="left")
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        self.model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dtype)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device).eval()

    def generate(self, prompts: list[str], max_new_tokens: int = 220, system: str = SYSTEM_PROMPT,
                 temperature: float = 0.7) -> list[str]:
        texts = [
            self.tok.apply_chat_template(
                [{"role": "system", "content": system}, {"role": "user", "content": p}],
                tokenize=False, add_generation_prompt=True,
            )
            for p in prompts
        ]
        enc = self.tok(texts, return_tensors="pt", padding=True).to(self.device)
        self.torch.manual_seed(self.seed)
        with self.torch.no_grad():
            out = self.model.generate(
                **enc, max_new_tokens=max_new_tokens, do_sample=True, temperature=temperature, top_p=0.9,
                pad_token_id=self.tok.pad_token_id or self.tok.eos_token_id,
            )
        gen = out[:, enc["input_ids"].shape[1]:]
        return self.tok.batch_decode(gen, skip_special_tokens=True)


class LLMVerbalizer:
    """Verbalize briefs with an LLM, falling back to the template grammar per row on failure."""

    def __init__(self, generator: LocalHFBatchGenerator | None, cache: TextCache, batch_size: int = 24):
        self.generator = generator
        self.cache = cache
        self.batch_size = batch_size
        self.template = TemplateVerbalizer()
        self.name = f"llm:{generator.model_id}" if generator else None

    def render_all(self, briefs: list[Brief], progress: bool = True) -> list[tuple[dict[str, str], str]]:
        results: dict[str, tuple[dict[str, str], str]] = {}
        todo = []
        for b in briefs:
            hit = self.cache.get(b.key())
            if hit:
                results[b.incident_id] = (hit["text"], hit["generator"])
            else:
                todo.append(b)
        if todo and self.generator is None:
            raise RuntimeError(f"{len(todo)} briefs are not cached and no LLM generator is available")
        for start in range(0, len(todo), self.batch_size):
            batch = todo[start:start + self.batch_size]
            raw = self.generator.generate([build_prompt(b) for b in batch])
            recs = []
            for b, r in zip(batch, raw):
                parsed = parse_output(r)
                if parsed is None:
                    text, gen = self.template.render(b), f"{self.template.name} (llm-parse-fallback)"
                else:
                    text, gen = parsed, self.name
                if b.note_quality == "low":
                    # low-quality notes are seeded deterministically, never LLM-written
                    text["resolution_notes"] = b.low_quality_note
                results[b.incident_id] = (text, gen)
                recs.append({"key": b.key(), "incident_id": b.incident_id, "generator": gen, "text": text, "raw": r})
            self.cache.put_many(recs)
            if progress:
                log.info("LLM verbalizer: %d / %d", min(start + self.batch_size, len(todo)), len(todo))
        return [results[b.incident_id] for b in briefs]
