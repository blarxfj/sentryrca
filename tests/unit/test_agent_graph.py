"""Unit tests for agent graph routing and state helpers."""

from sentryrca.agents.graph import MAX_RETRIES, _route_after_synthesis
from sentryrca.agents.state import RCAState
from sentryrca.agents.synthesis import _evidence_block, _p95

# ─── _route_after_synthesis ───────────────────────────────────────────────────


def _state(**overrides: object) -> RCAState:
    base: RCAState = {
        "incident": {},
        "log_findings": None,
        "deploy_findings": None,
        "evidence": [],
        "synthesis_attempts": 0,
        "rca": None,
        "error": None,
        "total_tokens": 0,
        "step_latencies_ms": [],
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def test_route_ends_on_success() -> None:
    from langgraph.graph import END

    state = _state(rca={"incident_id": "syn-001"})
    assert _route_after_synthesis(state) == END


def test_route_retries_on_failure_below_max() -> None:
    state = _state(synthesis_attempts=1, error="some error")
    assert _route_after_synthesis(state) == "synthesize"


def test_route_ends_after_max_retries() -> None:
    from langgraph.graph import END

    state = _state(synthesis_attempts=MAX_RETRIES, error="still failing")
    assert _route_after_synthesis(state) == END


def test_route_retries_at_zero_attempts() -> None:
    state = _state(synthesis_attempts=0, error="first failure")
    assert _route_after_synthesis(state) == "synthesize"


# ─── _p95 ─────────────────────────────────────────────────────────────────────


def test_p95_empty_returns_zero() -> None:
    assert _p95([]) == 0


def test_p95_single_element() -> None:
    assert _p95([500]) == 500


def test_p95_typical() -> None:
    latencies = list(range(100, 200))  # 100 values: 100..199
    result = _p95(latencies)
    assert result >= 194  # 95th percentile of 100 values


def test_p95_is_sorted_index() -> None:
    latencies = [1000, 100, 200, 300]
    # sorted: [100, 200, 300, 1000]; idx = max(0, int(4*0.95)-1) = max(0,2) = 2 → 300
    assert _p95(latencies) == 300


# ─── _evidence_block ──────────────────────────────────────────────────────────


def test_evidence_block_formats_all_items() -> None:
    items = [
        {
            "id": "evd-log-000",
            "source": "logs",
            "source_id": "syn-001_log_0",
            "excerpt": "WARN connection pool exhausted",
            "why_it_matters": "shows saturation",
        },
        {
            "id": "evd-deploy-000",
            "source": "deploy_diff",
            "source_id": "syn-001_deploy_abc",
            "excerpt": "Deploy abc by dev@example.com",
            "why_it_matters": "likely culprit",
        },
    ]
    block = _evidence_block(items)
    assert "evd-log-000" in block
    assert "evd-deploy-000" in block
    assert "shows saturation" in block
    assert "likely culprit" in block


def test_evidence_block_empty() -> None:
    assert _evidence_block([]) == ""
