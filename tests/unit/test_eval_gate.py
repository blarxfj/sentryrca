"""Unit tests for the CI eval gate comparison logic."""

from sentryrca.eval.__main__ import _gate_check


def _baseline(acc: float = 0.80, faith: float = 0.97, p95: int = 8000) -> dict:
    return {"top_1_accuracy": acc, "citation_faithfulness": faith, "p95_latency_ms": p95}


def _report(acc: float = 0.80, faith: float = 0.97, p95: int = 8000) -> dict:
    return {"top_1_accuracy": acc, "citation_faithfulness": faith, "p95_latency_ms": p95}


def test_all_gates_pass() -> None:
    assert _gate_check(_report(), _baseline()) == []


def test_accuracy_drop_within_threshold_passes() -> None:
    # 2% drop is fine (limit is 3%)
    failures = _gate_check(_report(acc=0.78), _baseline(acc=0.80))
    assert failures == []


def test_accuracy_drop_exceeds_threshold_fails() -> None:
    # 4% drop exceeds 3% limit
    failures = _gate_check(_report(acc=0.76), _baseline(acc=0.80))
    assert len(failures) == 1
    assert "top_1_accuracy" in failures[0]


def test_citation_faithfulness_below_floor_fails() -> None:
    failures = _gate_check(_report(faith=0.94), _baseline())
    assert len(failures) == 1
    assert "citation_faithfulness" in failures[0]


def test_citation_faithfulness_at_floor_passes() -> None:
    failures = _gate_check(_report(faith=0.95), _baseline())
    assert failures == []


def test_p95_latency_above_limit_fails() -> None:
    failures = _gate_check(_report(p95=16000), _baseline())
    assert len(failures) == 1
    assert "p95_latency_ms" in failures[0]


def test_p95_latency_at_limit_passes() -> None:
    failures = _gate_check(_report(p95=15000), _baseline())
    assert failures == []


def test_multiple_gate_failures_reported() -> None:
    failures = _gate_check(
        _report(acc=0.70, faith=0.90, p95=20000),
        _baseline(acc=0.80),
    )
    assert len(failures) == 3


def test_zero_baseline_accuracy_skips_drop_check() -> None:
    # If baseline is 0 we can't compute a meaningful drop — skip it
    failures = _gate_check(_report(acc=0.0), _baseline(acc=0.0))
    assert not any("top_1_accuracy" in f for f in failures)
