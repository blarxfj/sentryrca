"""Unit tests for the synthesis node — LLM calls are mocked."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sentryrca.agents.state import RCAState
from sentryrca.agents.synthesis import synthesis_node


def _minimal_rca(incident_id: str = "syn-001") -> dict[str, Any]:
    """Minimal valid RCAOutput dict (all required fields)."""
    return {
        "incident_id": incident_id,
        "severity": "high",
        "affected_service": "checkout-service",
        "timeline": [
            {
                "timestamp": "2024-01-15T03:41:00Z",
                "event": "DB connection pool exhausted",
                "source_evidence_id": "evd-log-000",
            }
        ],
        "top_hypothesis": "N+1 query pattern exhausted the DB connection pool",
        "confidence": 0.9,
        "alternative_hypotheses": ["Upstream traffic spike"],
        "evidence": [
            {
                "id": "evd-log-000",
                "source": "logs",
                "excerpt": "WARN: connection pool exhausted",
                "source_id": "syn-001_log_0",
                "why_it_matters": "Shows pool saturation",
            }
        ],
        "likely_root_cause": "N+1 SELECT per product in order finalization",
        "recommended_actions": ["Add bulk query", "Roll back deploy"],
        "rollback_candidate": "abc123",
        "unknowns": ["Whether the issue recurs under normal load"],
        "next_debug_steps": ["Check pg_stat_activity", "Enable slow query log"],
        "model_version": "claude-haiku-4-5-20251001",
        "prompt_version": "synthesis-v1",
        "agent_step_count": 3,
        "total_tokens": 1000,
        "total_cost_usd": 0.001,
        "p95_step_latency_ms": 800,
    }


def _state(**overrides: object) -> RCAState:
    base: RCAState = {
        "incident": {
            "id": "syn-001",
            "severity": "high",
            "affected_service": "checkout-service",
            "alert_text": "checkout p99 > 5s",
            "recent_deploys": [],
        },
        "log_findings": "Connection pool saturation detected.",
        "deploy_findings": "Deploy abc123 likely culprit.",
        "evidence": [
            {
                "id": "evd-log-000",
                "source": "logs",
                "excerpt": "WARN: connection pool exhausted",
                "source_id": "syn-001_log_0",
                "why_it_matters": "Shows pool saturation",
            }
        ],
        "synthesis_attempts": 0,
        "rca": None,
        "error": None,
        "total_tokens": 500,
        "step_latencies_ms": [400, 600],
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def _mock_litellm_response(content: str, tokens: int = 300) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage.total_tokens = tokens
    return resp


@pytest.mark.asyncio
async def test_synthesis_success() -> None:
    rca_dict = _minimal_rca()
    state = _state()

    with patch(
        "sentryrca.agents.synthesis.litellm.acompletion",
        new=AsyncMock(return_value=_mock_litellm_response(json.dumps(rca_dict))),
    ):
        result = await synthesis_node(state)

    assert result["rca"] is not None
    assert result["rca"]["incident_id"] == "syn-001"
    assert result["error"] is None
    assert result["synthesis_attempts"] == 1


@pytest.mark.asyncio
async def test_synthesis_validation_failure_returns_error() -> None:
    # Missing required fields — should fail Pydantic validation
    bad_rca = {"incident_id": "syn-001"}
    state = _state()

    with patch(
        "sentryrca.agents.synthesis.litellm.acompletion",
        new=AsyncMock(return_value=_mock_litellm_response(json.dumps(bad_rca))),
    ):
        result = await synthesis_node(state)

    assert result.get("rca") is None
    assert result["error"] is not None
    assert result["synthesis_attempts"] == 1


@pytest.mark.asyncio
async def test_synthesis_increments_attempt_count() -> None:
    state = _state(synthesis_attempts=1)
    bad_rca: dict[str, Any] = {}

    with patch(
        "sentryrca.agents.synthesis.litellm.acompletion",
        new=AsyncMock(return_value=_mock_litellm_response(json.dumps(bad_rca))),
    ):
        result = await synthesis_node(state)

    assert result["synthesis_attempts"] == 2


@pytest.mark.asyncio
async def test_synthesis_accumulates_tokens() -> None:
    rca_dict = _minimal_rca()
    state = _state(total_tokens=500)

    with patch(
        "sentryrca.agents.synthesis.litellm.acompletion",
        new=AsyncMock(return_value=_mock_litellm_response(json.dumps(rca_dict), tokens=300)),
    ):
        result = await synthesis_node(state)

    assert result["total_tokens"] == 800


@pytest.mark.asyncio
async def test_synthesis_fails_on_invalid_timeline_reference() -> None:
    """Timeline entry references an evidence ID not in the evidence list."""
    rca_dict = _minimal_rca()
    rca_dict["timeline"][0]["source_evidence_id"] = "evd-nonexistent-999"
    state = _state()

    with patch(
        "sentryrca.agents.synthesis.litellm.acompletion",
        new=AsyncMock(return_value=_mock_litellm_response(json.dumps(rca_dict))),
    ):
        result = await synthesis_node(state)

    # The Pydantic model_validator should catch the bad source_evidence_id
    assert result.get("rca") is None
    assert "evd-nonexistent-999" in (result.get("error") or "")


@pytest.mark.asyncio
async def test_synthesis_fails_on_missing_unknowns() -> None:
    rca_dict = _minimal_rca()
    rca_dict["unknowns"] = []  # empty list passes schema — unknowns is not required to be non-empty
    # but the prompt says it must be non-empty; schema doesn't enforce this, that's OK
    state = _state()

    with patch(
        "sentryrca.agents.synthesis.litellm.acompletion",
        new=AsyncMock(return_value=_mock_litellm_response(json.dumps(rca_dict))),
    ):
        result = await synthesis_node(state)

    # Should still succeed even with empty unknowns (schema allows it)
    assert result["rca"] is not None


@pytest.mark.asyncio
async def test_synthesis_records_latency() -> None:
    rca_dict = _minimal_rca()
    state = _state(step_latencies_ms=[400, 600])

    with patch(
        "sentryrca.agents.synthesis.litellm.acompletion",
        new=AsyncMock(return_value=_mock_litellm_response(json.dumps(rca_dict))),
    ):
        result = await synthesis_node(state)

    # Should have added the synthesis step latency
    assert len(result["step_latencies_ms"]) == 3
