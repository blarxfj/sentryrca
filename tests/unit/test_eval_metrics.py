"""Unit tests for eval metrics aggregation."""

from sentryrca.eval.metrics import EvalCaseResult, aggregate


def _result(
    incident_id: str = "syn-001",
    subset: str = "synthetic",
    score: int = 2,
    faith: float = 1.0,
    latency: int = 5000,
    tokens: int = 2000,
    error: str | None = None,
) -> EvalCaseResult:
    return EvalCaseResult(
        incident_id=incident_id,
        subset=subset,
        judge_score=score,
        top1_correct=score >= 2,
        top1_partial=score >= 1,
        citations_passed=int(faith * 5),
        citations_total=5,
        citation_faithfulness=faith,
        latency_ms=latency,
        total_tokens=tokens,
        error=error,
    )


def test_aggregate_top1_accuracy_perfect() -> None:
    results = [_result(score=2), _result(score=2)]
    agg = aggregate(results)
    assert agg["top_1_accuracy"] == 1.0


def test_aggregate_top1_accuracy_zero() -> None:
    results = [_result(score=0), _result(score=0)]
    agg = aggregate(results)
    assert agg["top_1_accuracy"] == 0.0


def test_aggregate_top1_mixed() -> None:
    results = [_result(score=2), _result(score=0), _result(score=2)]
    agg = aggregate(results)
    assert abs(agg["top_1_accuracy"] - 2 / 3) < 1e-9


def test_aggregate_citation_faithfulness_mean() -> None:
    results = [_result(faith=1.0), _result(faith=0.6)]
    agg = aggregate(results)
    assert abs(agg["citation_faithfulness"] - 0.8) < 1e-9


def test_aggregate_p95_latency() -> None:
    # 4 items: 1000, 2000, 3000, 10000 → sorted, idx=max(0, int(4*0.95)-1)=2 → 3000
    results = [
        _result(latency=1000),
        _result(latency=2000),
        _result(latency=3000),
        _result(latency=10000),
    ]
    agg = aggregate(results)
    assert agg["p95_latency_ms"] == 3000


def test_aggregate_error_rate() -> None:
    results = [_result(), _result(error="timeout"), _result()]
    agg = aggregate(results)
    assert abs(agg["error_rate"] - 1 / 3) < 1e-9


def test_aggregate_errors_excluded_from_accuracy() -> None:
    results = [_result(score=2), _result(error="crash", score=0), _result(score=2)]
    agg = aggregate(results)
    # 2 successful correct out of 3 total
    assert abs(agg["top_1_accuracy"] - 2 / 3) < 1e-9


def test_aggregate_subsets_split_correctly() -> None:
    results = [
        _result(subset="synthetic", score=2),
        _result(subset="synthetic", score=0),
        _result(subset="adversarial", score=2),
    ]
    agg = aggregate(results)
    assert "synthetic" in agg["subsets"]
    assert "adversarial" in agg["subsets"]
    assert agg["subsets"]["synthetic"].eval_set_size == 2
    assert agg["subsets"]["adversarial"].eval_set_size == 1


def test_aggregate_empty_returns_empty() -> None:
    assert aggregate([]) == {}


def test_aggregate_mean_tokens() -> None:
    results = [_result(tokens=1000), _result(tokens=3000)]
    agg = aggregate(results)
    assert agg["mean_tokens"] == 2000.0


def test_eval_case_result_top1_correct_at_score_2() -> None:
    r = _result(score=2)
    assert r.top1_correct is True
    assert r.top1_partial is True


def test_eval_case_result_partial_at_score_1() -> None:
    r = _result(score=1)
    assert r.top1_correct is False
    assert r.top1_partial is True


def test_eval_case_result_wrong_at_score_0() -> None:
    r = _result(score=0)
    assert r.top1_correct is False
    assert r.top1_partial is False
