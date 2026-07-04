"""LangGraph state for the RCA multi-agent graph."""

from typing import Any, TypedDict


class RCAState(TypedDict):
    # ── Input ────────────────────────────────────────────────────────────────
    incident: dict[str, Any]  # IncidentCase.model_dump()

    # ── Specialist outputs ───────────────────────────────────────────────────
    log_findings: str | None  # LogAnalyst narrative summary
    deploy_findings: str | None  # DeployInspector narrative summary

    # Evidence items built by specialists; verbatim excerpts from retrieved chunks.
    # Each item is an EvidenceItem-compatible dict with a stable `id`.
    evidence: list[dict[str, Any]]

    # ── Synthesis ────────────────────────────────────────────────────────────
    synthesis_attempts: int
    rca: dict[str, Any] | None  # RCAOutput.model_dump() on success
    error: str | None

    # ── LLMOps accounting ────────────────────────────────────────────────────
    total_tokens: int
    step_latencies_ms: list[int]
