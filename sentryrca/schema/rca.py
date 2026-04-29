from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class EvidenceItem(BaseModel):
    id: str = Field(
        ..., description="Stable identifier for this evidence item, used by TimelineEntry"
    )
    source: Literal["logs", "deploy_diff", "runbook", "metric", "history"]
    excerpt: str = Field(..., description="Verbatim text from the source")
    source_id: str = Field(..., description="Pointer to the retrieved chunk or deploy SHA")
    why_it_matters: str


class TimelineEntry(BaseModel):
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    event: str
    source_evidence_id: str = Field(
        ...,
        description="Must match an EvidenceItem.id from the parent RCAOutput.evidence list.",
    )


class RCAOutput(BaseModel):
    incident_id: str
    severity: Literal["low", "medium", "high", "critical"]
    affected_service: str
    timeline: list[TimelineEntry]
    top_hypothesis: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    alternative_hypotheses: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem]
    likely_root_cause: str
    recommended_actions: list[str]
    rollback_candidate: str | None = None
    unknowns: list[str] = Field(
        default_factory=list,
        description="What the agent could not determine. Required field — agent must declare unknowns.",
    )
    next_debug_steps: list[str]

    # LLMOps metadata — baked into every output for the audit store and eval harness
    model_version: str
    prompt_version: str
    agent_step_count: int
    total_tokens: int
    total_cost_usd: float
    p95_step_latency_ms: int

    @field_validator("timeline")
    @classmethod
    def timeline_must_not_be_empty(cls, v: list[TimelineEntry]) -> list[TimelineEntry]:
        if not v:
            raise ValueError("timeline must contain at least one entry")
        return v

    @field_validator("evidence")
    @classmethod
    def evidence_must_not_be_empty(cls, v: list[EvidenceItem]) -> list[EvidenceItem]:
        if not v:
            raise ValueError("evidence must contain at least one item")
        return v

    @model_validator(mode="after")
    def _timeline_entries_are_grounded(self) -> "RCAOutput":
        """Every timeline entry must reference a real evidence item (anti-hallucination guardrail)."""
        evidence_ids = {e.id for e in self.evidence}
        for entry in self.timeline:
            if entry.source_evidence_id not in evidence_ids:
                raise ValueError(
                    f"TimelineEntry references unknown evidence id: {entry.source_evidence_id!r}. "
                    f"Valid ids: {sorted(evidence_ids)}"
                )
        return self
