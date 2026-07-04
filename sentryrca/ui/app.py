"""Streamlit demo: paste an alert → watch the agent produce a structured RCA."""

from __future__ import annotations

import asyncio
import json
import pathlib

import streamlit as st

from sentryrca.api.slack import format_slack
from sentryrca.schema.incident import IncidentCase
from sentryrca.schema.rca import RCAOutput

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SentryRCA",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_corpus() -> dict[str, IncidentCase]:
    """Load all incidents from data/incidents/** for the selector."""
    root = pathlib.Path("data/incidents")
    incidents: dict[str, IncidentCase] = {}
    if not root.exists():
        return incidents
    for path in sorted(root.rglob("*.json")):
        try:
            inc = IncidentCase.model_validate(json.loads(path.read_text()))
            incidents[inc.id] = inc
        except Exception:
            pass
    return incidents


def _run_rca_sync(incident: IncidentCase) -> RCAOutput:
    from sentryrca.agents import run_rca

    return asyncio.run(run_rca(incident))


def _severity_color(severity: str) -> str:
    return {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(severity, "⚪")


def _confidence_bar(confidence: float) -> str:
    filled = int(confidence * 10)
    return "█" * filled + "░" * (10 - filled) + f"  {confidence:.0%}"


# ── Sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.title("SentryRCA")
st.sidebar.caption("Multi-agent root cause analysis")

corpus = _load_corpus()
mode = st.sidebar.radio("Input mode", ["Select from corpus", "Paste custom incident"])

selected_incident: IncidentCase | None = None

if mode == "Select from corpus" and corpus:
    incident_id = st.sidebar.selectbox(
        "Incident",
        options=list(corpus.keys()),
        format_func=lambda k: f"{k} — {corpus[k].affected_service} [{corpus[k].severity}]",
    )
    selected_incident = corpus[incident_id]
    with st.sidebar.expander("Alert text"):
        st.text(selected_incident.alert_text)
elif mode == "Paste custom incident":
    st.sidebar.markdown("Paste a JSON incident file:")
    raw_json = st.sidebar.text_area("Incident JSON", height=200)
    if raw_json.strip():
        try:
            selected_incident = IncidentCase.model_validate(json.loads(raw_json))
            st.sidebar.success(f"Loaded: {selected_incident.id}")
        except Exception as exc:
            st.sidebar.error(f"Invalid incident: {exc}")

st.sidebar.divider()
langfuse_url = st.sidebar.text_input("Langfuse URL (optional)", placeholder="http://localhost:3001")
run_button = st.sidebar.button("Run RCA", type="primary", disabled=selected_incident is None)

# ── Main panel ────────────────────────────────────────────────────────────────

st.title("SentryRCA — Multi-Agent Root Cause Analysis")

if not selected_incident:
    st.info("Select an incident from the sidebar or paste a custom one to get started.")
    with st.expander("How it works"):
        st.markdown(
            """
1. **LogAnalyst** retrieves the most relevant log chunks via hybrid retrieval (pgvector + FTS + RRF + reranker)
2. **DeployInspector** analyses recent deploys and identifies regression candidates
3. **Synthesis** combines both findings into a validated `RCAOutput` — every timeline entry references a real evidence item
4. All LLM calls and tool calls are traced in Langfuse
"""
        )
    st.stop()

# ── Run or show cached result ─────────────────────────────────────────────────

rca: RCAOutput | None = st.session_state.get(f"rca_{selected_incident.id}")

if run_button:
    with st.spinner("Running agents — LogAnalyst → DeployInspector → Synthesis …"):
        try:
            rca = _run_rca_sync(selected_incident)
            st.session_state[f"rca_{selected_incident.id}"] = rca
        except Exception as exc:
            st.error(f"RCA failed: {exc}")
            st.stop()

if rca is None:
    st.info("Press **Run RCA** in the sidebar to analyse this incident.")
    st.stop()

# ── Results ───────────────────────────────────────────────────────────────────

col_meta, col_conf = st.columns([3, 1])
with col_meta:
    st.subheader(f"{_severity_color(rca.severity)} {rca.incident_id} — {rca.affected_service}")
    st.caption(
        f"Severity: **{rca.severity}** · "
        f"Tokens: **{rca.total_tokens:,}** · "
        f"Steps: **{rca.agent_step_count}** · "
        f"p95 latency: **{rca.p95_step_latency_ms} ms** · "
        f"Model: `{rca.model_version}`"
    )
with col_conf:
    st.metric("Confidence", f"{rca.confidence:.0%}")
    st.caption(_confidence_bar(rca.confidence))

st.divider()

# Root cause + hypothesis
col_rc, col_hyp = st.columns(2)
with col_rc:
    st.markdown("### Root cause")
    st.info(rca.likely_root_cause)
with col_hyp:
    st.markdown("### Top hypothesis")
    st.warning(rca.top_hypothesis)
    if rca.alternative_hypotheses:
        with st.expander("Alternative hypotheses"):
            for h in rca.alternative_hypotheses:
                st.markdown(f"- {h}")

st.divider()

# Timeline
st.markdown("### Timeline")
evidence_by_id = {e.id: e for e in rca.evidence}
for entry in rca.timeline:
    ev = evidence_by_id.get(entry.source_evidence_id)
    with st.container():
        ts_col, ev_col = st.columns([1, 4])
        with ts_col:
            st.markdown(f"`{entry.timestamp}`")
        with ev_col:
            st.markdown(f"**{entry.event}**")
            if ev:
                st.caption(f"_{ev.source}_ — {ev.why_it_matters}")

st.divider()

# Evidence panel
st.markdown("### Evidence")
tabs = st.tabs([f"{e.source} · {e.id}" for e in rca.evidence])
for tab, evidence in zip(tabs, rca.evidence, strict=True):
    with tab:
        col_why, col_src = st.columns([2, 1])
        with col_why:
            st.markdown(f"**Why it matters:** {evidence.why_it_matters}")
        with col_src:
            st.markdown(f"**Source:** `{evidence.source_id}`")
        st.code(evidence.excerpt, language="text")

st.divider()

# Recommended actions + next steps
col_actions, col_next = st.columns(2)
with col_actions:
    st.markdown("### Recommended actions")
    for i, action in enumerate(rca.recommended_actions, 1):
        st.markdown(f"{i}. {action}")
    if rca.rollback_candidate:
        st.success(f"Rollback candidate: `{rca.rollback_candidate}`")

with col_next:
    st.markdown("### Next debug steps")
    for step in rca.next_debug_steps:
        st.markdown(f"- {step}")
    st.markdown("### Unknowns")
    for u in rca.unknowns:
        st.markdown(f"- {u}")

st.divider()

# Slack output + Langfuse link
col_slack, col_trace = st.columns(2)
with col_slack:
    st.markdown("### Slack output")
    slack_text = format_slack(rca)
    st.text_area("Copy to Slack", slack_text, height=300)

with col_trace:
    st.markdown("### Langfuse trace")
    if langfuse_url:
        st.markdown(f"[Open Langfuse dashboard]({langfuse_url.rstrip('/')}/traces)")
    else:
        st.caption("Enter a Langfuse URL in the sidebar to get a trace link.")
    st.markdown("### Raw RCA JSON")
    with st.expander("View"):
        st.json(rca.model_dump())
