"""Unit tests for citation faithfulness — no network, no DB."""

import pytest

from sentryrca.eval.citation import (
    build_corpus_text,
    check_citation_faithfulness,
    verify_excerpt_in_corpus,
)
from sentryrca.schema.incident import DeployEntry, IncidentCase
from sentryrca.schema.rca import EvidenceItem, RCAOutput, TimelineEntry

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _deploys(n: int = 5) -> list[DeployEntry]:
    return [
        DeployEntry(
            sha=f"{i:07d}abcdef0",
            timestamp="2024-01-15T02:30:00Z",
            author="dev",
            message=f"fix: patch {i}",
            changed_files=[f"src/file{i}.go"],
        )
        for i in range(n)
    ]


def _incident() -> IncidentCase:
    return IncidentCase(
        id="syn-001",
        subset="synthetic",
        category="db_saturation",
        affected_service="checkout-service",
        severity="high",
        alert_text="ALERT: checkout-service p99 latency > 5s for 5 consecutive minutes",
        log_window="2024-01-15T03:41:00Z WARN connection pool exhausted active=20\n" * 5,
        recent_deploys=_deploys(5),
        ground_truth_root_cause="N+1 query",
        ground_truth_remediation="Roll back",
    )


def _rca_with_excerpt(excerpt: str) -> RCAOutput:
    evidence = EvidenceItem(
        id="evd-log-000",
        source="logs",
        excerpt=excerpt,
        source_id="syn-001_log_0",
        why_it_matters="shows saturation",
    )
    timeline = TimelineEntry(
        timestamp="2024-01-15T03:41:00Z",
        event="pool exhausted",
        source_evidence_id="evd-log-000",
    )
    return RCAOutput(
        incident_id="syn-001",
        severity="high",
        affected_service="checkout-service",
        timeline=[timeline],
        top_hypothesis="N+1 query",
        confidence=0.9,
        evidence=[evidence],
        likely_root_cause="N+1 SELECT",
        recommended_actions=["rollback"],
        unknowns=["load pattern"],
        next_debug_steps=["check logs"],
        model_version="claude-sonnet-4-6",
        prompt_version="synthesis-v1",
        agent_step_count=3,
        total_tokens=1500,
        total_cost_usd=0.002,
        p95_step_latency_ms=800,
    )


# ── verify_excerpt_in_corpus ──────────────────────────────────────────────────


def test_verbatim_match_passes() -> None:
    assert verify_excerpt_in_corpus(
        "connection pool exhausted", "connection pool exhausted active=20"
    )


def test_substring_match_passes() -> None:
    assert verify_excerpt_in_corpus("pool exhausted", "WARN connection pool exhausted active=20")


def test_no_match_fails() -> None:
    assert not verify_excerpt_in_corpus("something else entirely", "connection pool exhausted")


def test_empty_excerpt_passes() -> None:
    # Empty string is technically in any string
    assert verify_excerpt_in_corpus("", "any text")


def test_strips_whitespace_before_check() -> None:
    assert verify_excerpt_in_corpus(
        "  pool exhausted  ", "WARN connection pool exhausted active=20"
    )


def test_case_sensitive() -> None:
    assert not verify_excerpt_in_corpus("CONNECTION POOL", "connection pool exhausted")


# ── build_corpus_text ─────────────────────────────────────────────────────────


def test_corpus_text_contains_alert() -> None:
    inc = _incident()
    text = build_corpus_text(inc)
    assert inc.alert_text in text


def test_corpus_text_contains_log_window() -> None:
    inc = _incident()
    text = build_corpus_text(inc)
    assert "pool exhausted" in text


def test_corpus_text_contains_deploy_sha() -> None:
    inc = _incident()
    text = build_corpus_text(inc)
    for d in inc.recent_deploys:
        assert d.sha in text


def test_corpus_text_contains_deploy_message() -> None:
    inc = _incident()
    text = build_corpus_text(inc)
    assert "fix: patch 0" in text


# ── check_citation_faithfulness ───────────────────────────────────────────────


def test_verbatim_excerpt_passes() -> None:
    inc = _incident()
    rca = _rca_with_excerpt("connection pool exhausted active=20")
    passed, total = check_citation_faithfulness(rca, inc)
    assert passed == 1
    assert total == 1


def test_hallucinated_excerpt_fails() -> None:
    inc = _incident()
    rca = _rca_with_excerpt("CPU utilization exceeded 95% threshold")
    passed, total = check_citation_faithfulness(rca, inc)
    assert passed == 0
    assert total == 1


def test_all_pass_returns_full_count() -> None:
    inc = _incident()
    rca = _rca_with_excerpt("WARN connection pool exhausted active=20")
    passed, total = check_citation_faithfulness(rca, inc)
    assert passed == total


def test_empty_evidence_returns_zero_zero() -> None:
    inc = _incident()
    rca = _rca_with_excerpt("x")
    rca.evidence.clear()  # type: ignore[attr-defined]
    passed, total = check_citation_faithfulness(rca, inc)
    assert passed == 0
    assert total == 0


@pytest.mark.parametrize(
    ("excerpt", "expected_pass"),
    [
        ("ALERT: checkout-service p99 latency > 5s", True),  # from alert_text
        ("connection pool exhausted active=20", True),  # from log_window
        ("fix: patch 0", True),  # from deploy message
        ("completely invented log line xyz", False),
    ],
)
def test_various_sources(excerpt: str, expected_pass: bool) -> None:
    inc = _incident()
    rca = _rca_with_excerpt(excerpt)
    passed, _ = check_citation_faithfulness(rca, inc)
    assert bool(passed) == expected_pass
