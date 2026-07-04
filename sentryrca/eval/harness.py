"""Eval harness — runs the agent against a corpus and produces an EvalReport."""

import asyncio
import json
import pathlib
import time
from datetime import UTC, datetime

import structlog

from sentryrca.agents import run_rca
from sentryrca.eval.citation import check_citation_faithfulness
from sentryrca.eval.judge import judge_top1
from sentryrca.eval.metrics import EvalCaseResult, EvalReport, aggregate
from sentryrca.schema.incident import IncidentCase

log = structlog.get_logger()

_FAST_SUBSET = {
    "synthetic": 5,
    "real_derived": 3,
    "adversarial": 2,
}


def load_corpus(data_dir: pathlib.Path) -> list[IncidentCase]:
    incidents: list[IncidentCase] = []
    for path in sorted(data_dir.rglob("*.json")):
        try:
            incidents.append(IncidentCase.model_validate(json.loads(path.read_text())))
        except Exception as exc:
            log.warning("skipping invalid incident", path=str(path), error=str(exc))
    return incidents


def select_fast_subset(incidents: list[IncidentCase]) -> list[IncidentCase]:
    """Pick the first N incidents from each subset for the fast eval."""
    by_subset: dict[str, list[IncidentCase]] = {}
    for inc in incidents:
        by_subset.setdefault(inc.subset, []).append(inc)

    selected: list[IncidentCase] = []
    for subset, limit in _FAST_SUBSET.items():
        selected.extend(sorted(by_subset.get(subset, []), key=lambda i: i.id)[:limit])
    return selected


async def _eval_one(incident: IncidentCase) -> EvalCaseResult:
    t0 = time.monotonic()
    try:
        rca = await run_rca(incident)
        latency_ms = int((time.monotonic() - t0) * 1000)

        citations_passed, citations_total = check_citation_faithfulness(rca, incident)
        faithfulness = citations_passed / citations_total if citations_total > 0 else 1.0

        score, _ = await judge_top1(rca, incident.ground_truth_root_cause)
        log.info(
            "eval case complete",
            incident_id=incident.id,
            judge_score=score,
            faithfulness=f"{faithfulness:.0%}",
            latency_ms=latency_ms,
        )
        return EvalCaseResult(
            incident_id=incident.id,
            subset=incident.subset,
            judge_score=score,
            top1_correct=score >= 2,
            top1_partial=score >= 1,
            citations_passed=citations_passed,
            citations_total=citations_total,
            citation_faithfulness=faithfulness,
            latency_ms=latency_ms,
            total_tokens=rca.total_tokens,
        )
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        log.error("eval case failed", incident_id=incident.id, error=str(exc))
        return EvalCaseResult(
            incident_id=incident.id,
            subset=incident.subset,
            judge_score=0,
            top1_correct=False,
            top1_partial=False,
            citations_passed=0,
            citations_total=0,
            citation_faithfulness=0.0,
            latency_ms=latency_ms,
            total_tokens=0,
            error=str(exc),
        )


async def run_eval(
    incidents: list[IncidentCase],
    *,
    concurrency: int = 3,
) -> EvalReport:
    """Run eval with bounded concurrency — avoid hammering the API or DB."""
    sem = asyncio.Semaphore(concurrency)

    async def _bounded(inc: IncidentCase) -> EvalCaseResult:
        async with sem:
            return await _eval_one(inc)

    results = await asyncio.gather(*[_bounded(inc) for inc in incidents])

    agg = aggregate(list(results))
    subset_models = dict(agg.pop("subsets", {}))

    return EvalReport(
        **agg,
        subsets=subset_models,
        results=list(results),
        generated_at=datetime.now(UTC).isoformat(),
    )
