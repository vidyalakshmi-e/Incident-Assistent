"""Shared UI helpers: provenance chips, mode banners, confidence, causal-chain rendering."""
from __future__ import annotations

import html

import streamlit as st

CSS = """
<style>
:root { --ok:#1f7a4d; --derived:#2d5fa8; --synth:#a36a00; --missing:#6b7280; --inferred:#7a3fa0; }
.block-container { padding-top: 1.6rem; max-width: 1250px; }
.chip { display:inline-block; padding:1px 8px; margin:1px 3px 1px 0; border-radius:10px; font-size:0.74rem;
        font-weight:600; border:1px solid currentColor; line-height:1.5; white-space:nowrap; }
.chip.original, .chip.observed { color:var(--ok); background:rgba(31,122,77,.08); }
.chip.derived { color:var(--derived); background:rgba(45,95,168,.08); border-style:dashed; }
.chip.synthetic { color:var(--synth); background:rgba(163,106,0,.08); }
.chip.inferred { color:var(--inferred); background:rgba(122,63,160,.08); border-style:dotted; }
.chip.missing { color:var(--missing); background:rgba(107,114,128,.08); }
.card { border:1px solid rgba(128,128,128,.28); border-radius:10px; padding:14px 16px; margin:6px 0 10px; }
.card.primary { border-left:5px solid #2d5fa8; }
.card.novel { border-left:5px solid #b42318; background:rgba(180,35,24,.05); }
.card.warn { border-left:5px solid #a36a00; background:rgba(163,106,0,.05); }
.kicker { font-size:.72rem; letter-spacing:.06em; text-transform:uppercase; opacity:.7; font-weight:700; }
.big { font-size:1.12rem; font-weight:650; margin:2px 0 6px; }
.muted { opacity:.72; font-size:.86rem; }
.mode { display:inline-block; padding:3px 10px; border-radius:6px; background:#fff4e5; color:#8a4b00;
        border:1px solid #f0c27a; font-size:.82rem; margin:0 6px 6px 0; font-weight:600; }
.step { font-size:1.02rem; }
</style>
"""

LEGEND = ("<span class='chip original'>original</span><span class='chip derived'>derived</span>"
          "<span class='chip synthetic'>synthetic</span><span class='chip inferred'>inferred</span>"
          "<span class='chip missing'>missing</span>")


def setup() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def chip(tag: str | None, text: str | None = None) -> str:
    tag = (tag or "missing").split(" ")[0].lower()
    cls = tag if tag in {"original", "derived", "synthetic", "inferred", "missing", "observed"} else "missing"
    return f"<span class='chip {cls}'>{html.escape(text or tag)}</span>"


def md(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def mode_banner(labels: list[str] | None) -> None:
    if labels:
        md("".join(f"<span class='mode'>⚠ {html.escape(l)}</span>" for l in labels))


def conf_text(value, basis: str | None = None) -> str:
    if value is None:
        return f"<b>undetermined</b> <span class='muted'>({html.escape(basis or 'no real signal available')})</span>"
    return f"<b>{value:.2f}</b> <span class='muted'>({html.escape(basis or '')})</span>"


TAG_STYLE = {"observed": ("solid", "#1f7a4d"), "derived": ("dashed", "#2d5fa8"), "inferred": ("dotted", "#7a3fa0")}


def causal_chain_dot(links: list[dict], title: str = "") -> str:
    """Graphviz DOT for a causal chain; the tag decides the border style so inferred links never look
    like observed ones."""
    lines = ["digraph G {", 'rankdir=LR; bgcolor="transparent";',
             'node [shape=box, style="rounded,filled", fillcolor="white", fontname="Helvetica", fontsize=10, width=1.6];',
             'edge [color="#888888"];']
    prev = None
    for i, l in enumerate(links):
        tag_key = l.get("tag") or (max(l["tags"], key=l["tags"].get) if l.get("tags") else "inferred")
        style, color = TAG_STYLE.get(tag_key, ("dotted", "#999999"))
        stmt = str(l.get("statement", ""))
        stmt = (stmt[:70] + "…") if len(stmt) > 70 else stmt
        label = f"{l['stage'].replace('_', ' ').upper()}\\n{stmt}".replace('"', "'")
        tag = l.get("tag") or ", ".join(f"{k} {v:.0%}" for k, v in (l.get("tags") or {}).items())
        lines.append(f'n{i} [label="{label}\\n[{tag}]", color="{color}", style="rounded,filled,{style}", penwidth=1.6];')
        if prev is not None:
            lines.append(f"n{prev} -> n{i};")
        prev = i
    lines.append("}")
    return "\n".join(lines)
