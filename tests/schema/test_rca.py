"""Tests for the RCAOutput Pydantic schema."""

import pytest
from pydantic import ValidationError

from sentryrca.schema.rca import (
    EvidenceItem,
    RCAOutput,
    TimelineEntry,
)

# ─── Fixtures ────────────────────────────────────────────────────────────────


def _evidence(ev_id: str = "ev-001") -> EvidenceItem:
    return EvidenceItem(
        id=ev_id,
        source="logs",
        excerpt="FATAL: connection pool exhausted",
        source_id="chunk-abc",
        why_it_matters="Confirms proximate cause",
    )


def _timeline_entry(evidence_id: str = "ev-001") -> TimelineEntry:
    return TimelineEntry(
        timestamp="2024-01-15T03:42:00Z",
        event="checkout-service returned 500s",
        source_evidence_id=evidence_id,
    )


def _valid_rca(**overrides: object) -> RCAOutput:
    defaults: dict[str, object] = {
        "incident_id": "inc-001",
        "severity": "high",
        "affected_service": "checkout-service",
        "timeline": [_timeline_entry("ev-001")],
        "top_hypothesis": "Postgres pool exhausted by N+1 query in v1.4.2",
        "confidence": 0.87,
        "evidence": [_evidence("ev-001")],
        "likely_root_cause": "Deploy v1.4.2 introduced N+1 query",
        "recommended_actions": ["Roll back to v1.4.1"],
        "unknowns": ["Whether staging load tests covered this path"],
        "next_debug_steps": ["Check pg_stat_activity"],
        "model_version": "claude-sonnet-4-6",
        "prompt_version": "rca-v0.1.0",
        "agent_step_count": 4,
        "total_tokens": 2840,
        "total_cost_usd": 0.0042,
        "p95_step_latency_ms": 3200,
    }
    defaults.update(overrides)
    return RCAOutput.model_validate(defaults)


# ─── Tests ───────────────────────────────────────────────────────────────────


def test_valid_round_trip() -> None:
    rca = _valid_rca()
    serialized = rca.model_dump_json()
    restored = RCAOutput.model_validate_json(serialized)
    assert restored == rca


def test_unknowns_none_rejected() -> None:
    """unknowns=None must not be accepted (field type is list[str])."""
    with pytest.raises(ValidationError):
        _valid_rca(unknowns=None)


def test_ungrounded_timeline_entry_rejected() -> None:
    """A timeline entry whose source_evidence_id does not match any evidence id must fail."""
    with pytest.raises(ValidationError, match="unknown evidence id"):
        _valid_rca(
            evidence=[_evidence("ev-001")],
            timeline=[_timeline_entry("ev-MISSING")],
        )


def test_confidence_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_rca(confidence=-0.1)
    with pytest.raises(ValidationError):
        _valid_rca(confidence=1.1)


def test_json_schema_generation() -> None:
    schema = RCAOutput.model_json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "timeline" in schema["properties"]
    assert "evidence" in schema["properties"]
    assert "unknowns" in schema["properties"]
    assert "confidence" in schema["properties"]
