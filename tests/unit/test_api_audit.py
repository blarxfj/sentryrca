"""Unit tests for the audit writer — DB session is mocked."""

import re
from unittest.mock import AsyncMock

import pytest

from sentryrca.api.audit import write_rca_run
from sentryrca.schema.rca import EvidenceItem, RCAOutput, TimelineEntry


def _rca() -> RCAOutput:
    evidence = EvidenceItem(
        id="evd-log-000",
        source="logs",
        excerpt="WARN: connection pool exhausted",
        source_id="syn-001_log_0",
        why_it_matters="Shows DB saturation",
    )
    timeline = TimelineEntry(
        timestamp="2024-01-15T03:41:00Z",
        event="DB pool exhausted",
        source_evidence_id="evd-log-000",
    )
    return RCAOutput(
        incident_id="syn-001",
        severity="high",
        affected_service="checkout-service",
        timeline=[timeline],
        top_hypothesis="N+1 query",
        confidence=0.85,
        alternative_hypotheses=[],
        evidence=[evidence],
        likely_root_cause="N+1 SELECT",
        recommended_actions=["Roll back"],
        rollback_candidate=None,
        unknowns=["Unknown load pattern"],
        next_debug_steps=["Check logs"],
        model_version="claude-sonnet-4-6",
        prompt_version="synthesis-v1",
        agent_step_count=3,
        total_tokens=1500,
        total_cost_usd=0.002,
        p95_step_latency_ms=800,
    )


@pytest.mark.asyncio
async def test_write_rca_run_returns_uuid() -> None:
    session = AsyncMock()
    run_id = await write_rca_run(session, _rca())
    assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", run_id)


@pytest.mark.asyncio
async def test_write_rca_run_calls_session_execute() -> None:
    session = AsyncMock()
    await write_rca_run(session, _rca())
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_rca_run_passes_incident_id() -> None:
    session = AsyncMock()
    await write_rca_run(session, _rca())
    params = session.execute.call_args[0][1]
    assert params["incident_id"] == "syn-001"


@pytest.mark.asyncio
async def test_write_rca_run_passes_token_count() -> None:
    session = AsyncMock()
    await write_rca_run(session, _rca())
    params = session.execute.call_args[0][1]
    assert params["total_tokens"] == 1500


@pytest.mark.asyncio
async def test_write_rca_run_unique_ids() -> None:
    session = AsyncMock()
    rca = _rca()
    id1 = await write_rca_run(session, rca)
    id2 = await write_rca_run(session, rca)
    assert id1 != id2
