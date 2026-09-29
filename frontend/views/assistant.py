"""Screen 1 — Incident Assistant (+ screen 5 novel-incident display inline)."""
from __future__ import annotations

import html

import streamlit as st

from frontend.api_client import post, safe
from frontend.ui import LEGEND, causal_chain_dot, chip, conf_text, md, mode_banner

DEMO = ("The application is becoming slower and sometimes freezes when users try to open records. "
        "Restarting fixes it temporarily.")


def render_evidence_chain(ch: dict) -> None:
    """The formal 'Why did the system recommend this?' panel."""
    md(f"<div class='muted'>Provenance legend: {LEGEND}</div>")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**1 · Query understood**")
        qu = ch["query_understood"]
        st.caption(f"Expanded with technical concepts: {', '.join(qu['technical_concepts']) or '—'}")
        for m in qu["matched_phrases"]:
            md(f"<span class='muted'>“{html.escape(m['phrase'])}” → {html.escape(m['maps_to'])}</span>")
        if qu.get("hints"):
            st.caption(f"Hints: {qu['hints']}")
        if qu.get("llm_expansion"):
            md(f"LLM expansion {chip('inferred')}: {', '.join(qu['llm_expansion'])}")
        st.markdown("**2 · Extracted fingerprint**")
        fp = ch["extracted_fingerprint"]
        rows = [f"<tr><td>{k}</td><td>{html.escape(str(v))}</td><td>{chip(fp['provenance'][k])}</td></tr>"
                for k, v in fp["values"].items() if v != "Unknown"]
        unknown = [k for k, v in fp["values"].items() if v == "Unknown"]
        md("<table style='font-size:.85rem'>" + "".join(rows) + "</table>")
        if unknown:
            st.caption(f"Unknown (no supporting signal, nothing invented): {', '.join(unknown)}")
    with c2:
        st.markdown("**3 · Matched incident family**")
        fam = ch["matched_incident_family"]
        if fam.get("status") == "insufficient evidence":
            st.info("insufficient evidence")
        else:
            md(f"<b>{fam['family_id']}</b> — {html.escape(fam['name'])}<br>"
               f"match strength <b>{fam['match_strength']:.2f}</b> = vote share {fam['vote_share']:.2f} × best relevance "
               f"{fam['max_relevance']:.2f} · centroid similarity {fam['centroid_similarity']:.2f}")
            if fam.get("runner_up"):
                ru = fam["runner_up"]
                st.caption(f"Runner-up: {ru['family_id']} ({ru['match_strength']})")
        st.markdown("**4 · Evidence strength** (computed, never LLM-guessed)")
        for k, v in ch["evidence_strength"].items():
            val = "insufficient evidence" if v["value"] is None else f"{v['value']:.2f}"
            md(f"<div><b>{k.replace('_', ' ')}</b>: {val} <span class='muted'>— {html.escape(v['basis'])}</span></div>")
    st.markdown("**5 · Retrieved historical incidents used as evidence**")
    for r in ch["retrieved_incidents"]:
        if "incident_id" not in r:
            st.info("insufficient evidence")
            continue
        conf = "—" if r["relevance_confidence"] is None else f"{r['relevance_confidence']:.2f}"
        md(f"<div class='muted'><b>{r['incident_id']}</b> (family {r['family']}) relevance {conf} "
           f"{chip(r['text_provenance'], 'text: ' + str(r['text_provenance']))} — {html.escape(r['why_retrieved'])}</div>")
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**6 · Root-cause evidence**")
        rc = ch["root_cause_evidence"]
        if rc.get("status") == "insufficient evidence":
            st.info("insufficient evidence")
        else:
            md(f"<b>{html.escape(rc['statement'])}</b> — <i>{rc['certainty']}</i> "
               f"({rc['share_of_retrieved']:.0%} of retrieved incidents) {chip('inferred', 'inferred for the new incident')}")
            st.caption(rc["note"])
            for f in rc["fields"][:5]:
                st.caption("• " + f)
    with c4:
        st.markdown("**7 · Resolution evidence**")
        re_ = ch["resolution_evidence"]
        if re_.get("status") == "insufficient evidence":
            st.info("insufficient evidence")
        else:
            md(f"<b>{html.escape(re_['recommended_action'])}</b><br>confidence {conf_text(re_['confidence'], re_['confidence_basis'])}")
            if re_.get("confidence_components"):
                st.caption(" × ".join(f"{k} {v}" for k, v in re_["confidence_components"].items()))
            ep = re_["evidence_provenance"]
            n_orig, n_syn = ep.get("original", 0), ep.get("synthetic", 0)
            md(f"Evidence records: {chip('original', f'{n_orig} original')}{chip('synthetic', f'{n_syn} synthetic')}")
    llm = ch["llm_inference"]
    st.markdown("**8 · LLM inference (kept separate from historical evidence)**")
    if not llm["available"]:
        md(f"<span class='mode'>{html.escape(llm['label'])}</span> no LLM synthesis or LLM validation was performed.")
    elif llm.get("synthesis"):
        md(f"{chip('inferred', 'LLM-generated synthesis')}")
        st.write(llm["synthesis"]["text"])
        if llm.get("validation"):
            v = llm["validation"]
            st.caption(f"Validation: {v['method']} — unsupported steps: {v['unsupported_steps']}")
    md(f"<div class='muted'>Completeness: {ch['completeness']['ratio']:.0%} of evidence fields populated; "
       f"insufficient: {', '.join(ch['completeness']['insufficient']) or 'none'}</div>")


def render_strategy_panel(panel: list[dict], top_key: str | None) -> None:
    if not panel:
        st.info("No historical strategies recorded for this pattern.")
        return
    for s in panel:
        is_top = s["strategy_key"] == top_key
        stats = ""
        if s.get("stats_supported"):
            stats = (f"reopen rate <b>{s['reopen_rate']:.1%}</b> (95% CI {s['reopen_ci_low']:.1%}–{s['reopen_ci_high']:.1%}), "
                     f"median resolution {s['median_resolution_hours']} h, mean reassignments {s['mean_reassignments']}")
        else:
            stats = "historical resolution observed for this pattern — no success statistics (insufficient outcome data)"
        md(f"<div class='card{' primary' if is_top else ''}'><span class='kicker'>{s['kind']}"
           f"{' · current top pick' if is_top else ''}</span><div class='big'>{html.escape(s['label'])}</div>"
           f"<div class='muted'>{s['n_incidents']} incidents · closure codes {s['closure_codes']} · "
           f"wording {chip(s['text_provenance'])}</div><div class='muted'>{stats}</div>"
           f"<div class='muted'>outcome basis: {html.escape(s['basis'])}</div></div>")


def render() -> None:
    st.title("Incident Assistant")
    st.caption("Describe the incident in your own words. The assistant leads with ONE ranked, evidence-backed fix.")
    text = st.text_area("Incident description", value=st.session_state.get("assistant_text", DEMO), height=100)
    with st.expander("Optional details (reported fields / known facts)"):
        c1, c2, c3 = st.columns(3)
        prio = c1.selectbox("Priority (if known)", ["", "1", "2", "3", "4", "5"])
        env = c2.selectbox("Environment", ["", "Production", "Staging", "Development"])
        scope = c3.selectbox("Affected scope", ["", "single user", "multiple users", "team", "organization-wide"])
    if st.button("Analyze incident", type="primary"):
        hints = {k: v for k, v in (("environment", env), ("impact_scope", scope)) if v}
        payload = {"text": text, "hints": hints or None, "fields": {"priority": prio} if prio else None}
        with st.spinner("Understanding → retrieving → matching patterns → ranking resolutions…"):
            res = safe(post, "/incidents/analyze", payload)
        if res:
            st.session_state["analysis"] = res
            st.session_state["assistant_text"] = text
    res = st.session_state.get("analysis")
    if not res:
        return
    mode_banner(res["mode_labels"])
    nov = res["novelty"]
    if nov.get("is_novel"):
        md(f"<div class='card novel'><span class='kicker'>Novel incident detection</span><div class='big'>"
           f"{html.escape(nov['verdict'])}</div><div class='muted'>P(known) = {nov['known_probability']:.2f} "
           f"&lt; validated threshold {nov['threshold']:.2f}. Recommended route: {nov['recommended_route']}. "
           f"No low-confidence historical fix is forced.</div></div>")
        if res.get("escalation_proposal"):
            ep = res["escalation_proposal"]
            st.write(f"Proposed routing: **{ep['tier']}** → {ep['suggested_team']} ({', '.join(ep['tier_reasons'])})")
    top = res["top_resolution"]
    if top and not nov.get("is_novel"):
        safety = "".join(f"<div class='muted'>⚠ {html.escape(n)}</div>" for n in top["safety"]["notes"])
        md(f"<div class='card primary'><span class='kicker'>Recommended first step · {html.escape(top['kind'])}</span>"
           f"<div class='big'>{html.escape(top['action'])}</div><div class='step'>{html.escape(top['step'])}</div>"
           f"<div class='muted'>Historical strategy {top['strategy_key']}: {html.escape(top.get('strategy_label') or '')}</div>"
           f"<div class='muted'>Expected observation: {html.escape(top['expected_observation'] or '—')}</div>"
           f"<div style='margin-top:6px'>Confidence: {conf_text(top['confidence'], top['confidence_basis'])}</div>"
           f"<div class='muted'>Backed by {len(top['supporting_incidents'])} historical incident(s): "
           f"{', '.join(top['supporting_incidents'][:6])}</div>{safety}</div>")
        if st.button("Start guided troubleshooting with this incident →"):
            st.session_state["ts_prefill"] = res.get("incident_id"), st.session_state.get("assistant_text")
            st.switch_page(st.session_state["pages"]["troubleshooting"])
    elif not nov.get("is_novel"):
        st.warning("No evidence-backed resolution found.")
    if nov.get("verdict") == "undetermined":
        st.caption(f"Novelty: undetermined — {nov.get('basis')}")
    cls = res["classification"]
    cols = st.columns(4)
    for c, k in zip(cols, ("category", "priority", "impact", "urgency")):
        v = cls[k]
        prob = f" ({v['probability']:.0%})" if v.get("probability") else ""
        c.metric(k.capitalize(), f"{v['value'] or '—'}{prob}")
        c.caption(v.get("provenance", ""))
    c1, c2 = st.columns(2)
    with c1:
        fam = res["pattern_family"]
        st.markdown("**Pattern family**")
        if fam:
            md(f"<b>{fam['family_id']}</b> · {html.escape(fam['name'])}<br><span class='muted'>size {fam['size']} · "
               f"match strength {fam['match_strength']}</span>")
    with c2:
        rc = res["likely_root_cause"]
        st.markdown("**Likely root cause**")
        if rc.get("status") == "computed":
            md(f"{html.escape(rc['statement'])} — <i>{rc['certainty']}</i> "
               f"<span class='muted'>({rc['share_of_retrieved']:.0%} of evidence)</span> {chip('inferred')}")
        else:
            st.write("insufficient evidence")
    if res.get("llm_synthesis"):
        with st.expander("LLM-generated synthesis (separate from historical evidence)"):
            md(chip("inferred", "LLM-generated synthesis"))
            st.write(res["llm_synthesis"]["text"])
            if res.get("llm_validation"):
                st.json(res["llm_validation"])
    with st.expander("🔎 Why did the system recommend this?  (Evidence Chain)", expanded=False):
        render_evidence_chain(res["evidence_chain"])
    with st.expander("📚 See other historical approaches for this pattern (Resolution Strategy Intelligence)"):
        render_strategy_panel(res["strategy_panel"], top["strategy_key"] if top else None)
    if res.get("family_causal_chain"):
        with st.expander("⛓ Causal chain of the matched family"):
            st.caption("Border style = evidence tag: solid observed · dashed derived · dotted inferred")
            st.graphviz_chart(causal_chain_dot(res["family_causal_chain"]))
    with st.expander(f"Similar historical incidents ({len(res['similar_incidents'])})"):
        for r in res["similar_incidents"]:
            conf = r["scores"]["relevance_confidence"]
            md(f"<div class='card'><b>{r['incident_id']}</b> · {html.escape(r['title'] or '')} "
               f"{chip(r['provenance']['description'], 'text ' + r['provenance']['description'])}"
               f"{'<span class=chip missing>+' + str(r['duplicates_collapsed']) + ' identical</span>' if r['duplicates_collapsed'] else ''}"
               f"<div class='muted'>{html.escape(r['description'] or '')}</div>"
               f"<div><b>Resolution:</b> {html.escape(r['resolution_notes'] or '')}</div>"
               f"<div class='muted'>relevance {('%.2f' % conf) if conf is not None else 'n/a'} · "
               f"{html.escape(r['why_retrieved']['summary'])} · quality {r['quality']['tier']}</div></div>")
    with st.expander("Agent trace (A2A messages) and latency"):
        for m in res["agent_messages"]:
            st.write(f"`{m['sender']}` → `{m['recipient']}` · **{m['intent']}** — {m['summary']}")
        st.json(res["timings_ms"])
