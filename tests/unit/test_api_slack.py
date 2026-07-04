"""Unit tests for the Slack formatter."""

from sentryrca.api.slack import format_slack
from sentryrca.schema.rca import EvidenceItem, RCAOutput, TimelineEntry


def _rca(**overrides: object) -> RCAOutput:
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
    defaults: dict[str, object] = {
        "incident_id": "syn-001",
        "severity": "high",
        "affected_service": "checkout-service",
        "timeline": [timeline],
        "top_hypothesis": "N+1 query exhausted connection pool",
        "confidence": 0.85,
        "alternative_hypotheses": ["Traffic spike"],
        "evidence": [evidence],
        "likely_root_cause": "N+1 SELECT in order finalization",
        "recommended_actions": ["Roll back deploy", "Add bulk query"],
        "rollback_candidate": "abc123",
        "unknowns": ["Whether the issue is reproducible under normal load"],
        "next_debug_steps": ["Check pg_stat_activity"],
        "model_version": "claude-sonnet-4-6",
        "prompt_version": "synthesis-v1",
        "agent_step_count": 3,
        "total_tokens": 1500,
        "total_cost_usd": 0.002,
        "p95_step_latency_ms": 800,
    }
    defaults.update(overrides)
    return RCAOutput.model_validate(defaults)


def test_slack_contains_incident_id() -> None:
    out = format_slack(_rca())
    assert "syn-001" in out


def test_slack_contains_severity() -> None:
    out = format_slack(_rca())
    assert "HIGH" in out


def test_slack_contains_hypothesis() -> None:
    out = format_slack(_rca())
    assert "N+1 query" in out


def test_slack_contains_root_cause() -> None:
    out = format_slack(_rca())
    assert "N+1 SELECT" in out


def test_slack_contains_timeline_entry() -> None:
    out = format_slack(_rca())
    assert "DB pool exhausted" in out
    assert "2024-01-15T03:41:00Z" in out


def test_slack_contains_recommended_actions() -> None:
    out = format_slack(_rca())
    assert "Roll back deploy" in out
    assert "Add bulk query" in out


def test_slack_contains_rollback_candidate() -> None:
    out = format_slack(_rca())
    assert "abc123" in out


def test_slack_contains_unknowns() -> None:
    out = format_slack(_rca())
    assert "reproducible" in out


def test_slack_contains_token_count() -> None:
    out = format_slack(_rca())
    assert "1,500" in out


def test_slack_severity_emoji_critical() -> None:
    out = format_slack(_rca(severity="critical"))
    assert ":red_circle:" in out


def test_slack_severity_emoji_high() -> None:
    out = format_slack(_rca(severity="high"))
    assert ":large_orange_circle:" in out


def test_slack_with_run_id() -> None:
    out = format_slack(_rca(), run_id="run-xyz-123")
    assert "run-xyz-123" in out


def test_slack_without_rollback_candidate() -> None:
    out = format_slack(_rca(rollback_candidate=None))
    assert "Rollback candidate" not in out


def test_slack_no_alternative_hypotheses() -> None:
    out = format_slack(_rca(alternative_hypotheses=[]))
    assert "Alternative hypotheses" not in out


def test_slack_confidence_shown_as_percent() -> None:
    out = format_slack(_rca(confidence=0.85))
    assert "85%" in out
