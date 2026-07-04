"""Pydantic schemas for eval results and metrics aggregation."""

import statistics
from typing import Any

from pydantic import BaseModel, Field


class EvalCaseResult(BaseModel):
    incident_id: str
    subset: str
    judge_score: int = Field(..., ge=0, le=2)
    top1_correct: bool  # score >= 2
    top1_partial: bool  # score >= 1
    citations_passed: int
    citations_total: int
    citation_faithfulness: float = Field(..., ge=0.0, le=1.0)
    latency_ms: int
    total_tokens: int
    error: str | None = None


class SubsetMetrics(BaseModel):
    eval_set_size: int
    top_1_accuracy: float
    top_1_partial_accuracy: float
    citation_faithfulness: float
    p95_latency_ms: int
    mean_tokens: float


class EvalReport(BaseModel):
    top_1_accuracy: float
    top_1_partial_accuracy: float
    citation_faithfulness: float
    p95_latency_ms: int
    mean_tokens: float
    eval_set_size: int
    error_rate: float
    subsets: dict[str, SubsetMetrics]
    results: list[EvalCaseResult]
    generated_at: str


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    return s[max(0, int(len(s) * 0.95) - 1)]


def aggregate(results: list[EvalCaseResult]) -> dict[str, Any]:
    """Compute top-level and per-subset metrics from a list of case results."""
    if not results:
        return {}

    def _subset_metrics(cases: list[EvalCaseResult]) -> SubsetMetrics:
        n = len(cases)
        successful = [c for c in cases if c.error is None]
        latencies = [c.latency_ms for c in successful]
        tokens = [c.total_tokens for c in successful]
        return SubsetMetrics(
            eval_set_size=n,
            top_1_accuracy=sum(c.top1_correct for c in successful) / n if n else 0.0,
            top_1_partial_accuracy=sum(c.top1_partial for c in successful) / n if n else 0.0,
            citation_faithfulness=(
                sum(c.citation_faithfulness for c in successful) / len(successful)
                if successful
                else 0.0
            ),
            p95_latency_ms=_p95(latencies),
            mean_tokens=statistics.mean(tokens) if tokens else 0.0,
        )

    subsets: dict[str, list[EvalCaseResult]] = {}
    for r in results:
        subsets.setdefault(r.subset, []).append(r)

    successful = [r for r in results if r.error is None]
    n = len(results)
    latencies = [r.latency_ms for r in successful]
    tokens = [r.total_tokens for r in successful]

    return {
        "top_1_accuracy": sum(r.top1_correct for r in successful) / n if n else 0.0,
        "top_1_partial_accuracy": sum(r.top1_partial for r in successful) / n if n else 0.0,
        "citation_faithfulness": (
            sum(r.citation_faithfulness for r in successful) / len(successful)
            if successful
            else 0.0
        ),
        "p95_latency_ms": _p95(latencies),
        "mean_tokens": statistics.mean(tokens) if tokens else 0.0,
        "eval_set_size": n,
        "error_rate": sum(1 for r in results if r.error) / n if n else 0.0,
        "subsets": {k: _subset_metrics(v) for k, v in subsets.items()},
    }
