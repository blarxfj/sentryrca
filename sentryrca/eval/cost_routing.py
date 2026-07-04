"""Cost-routing eval: Sonnet-only vs Haiku-only vs Hybrid (Sonnet reasoning + Haiku fast).

Runs the fast eval subset under each configuration and produces a comparison table
showing accuracy vs cost per incident.
"""

import asyncio
import json
import pathlib
from dataclasses import dataclass
from typing import Any

import structlog

from sentryrca.config import settings
from sentryrca.eval.harness import load_corpus, run_eval, select_fast_subset

log = structlog.get_logger()

# Prices in USD per 1M tokens (input / output) as of 2025
_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
}

_RESULTS_DIR = pathlib.Path("eval/results")


@dataclass
class CostConfig:
    name: str
    label: str
    reasoning_model: str
    fast_model: str


_CONFIGS = [
    CostConfig(
        name="hybrid",
        label="Hybrid (Sonnet reason + Haiku fast)",
        reasoning_model="claude-sonnet-4-6",
        fast_model="claude-haiku-4-5-20251001",
    ),
    CostConfig(
        name="sonnet_only",
        label="Sonnet-only",
        reasoning_model="claude-sonnet-4-6",
        fast_model="claude-sonnet-4-6",
    ),
    CostConfig(
        name="haiku_only",
        label="Haiku-only",
        reasoning_model="claude-haiku-4-5-20251001",
        fast_model="claude-haiku-4-5-20251001",
    ),
]


def _estimate_cost_usd(total_tokens: int, model: str) -> float:
    """Rough cost estimate using 70/30 input/output split heuristic."""
    input_price, output_price = _PRICING.get(model, (3.00, 15.00))
    input_tokens = int(total_tokens * 0.70)
    output_tokens = total_tokens - input_tokens
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


async def _run_config(
    config: CostConfig,
    data_dir: pathlib.Path,
    concurrency: int,
) -> dict[str, Any]:
    """Monkey-patch settings, run eval, restore."""
    orig_reasoning = settings.litellm_model_reasoning
    orig_fast = settings.litellm_model_fast
    settings.litellm_model_reasoning = config.reasoning_model
    settings.litellm_model_fast = config.fast_model

    try:
        corpus = load_corpus(data_dir)
        incidents = select_fast_subset(corpus)
        log.info("cost-routing: starting config", config=config.name, n=len(incidents))
        report = await run_eval(incidents, concurrency=concurrency)
    finally:
        settings.litellm_model_reasoning = orig_reasoning
        settings.litellm_model_fast = orig_fast

    total_tokens = sum(r.total_tokens for r in report.results if not r.error)
    n_success = sum(1 for r in report.results if not r.error)
    mean_tokens = total_tokens / n_success if n_success else 0.0

    # Estimate cost using the reasoning model price (dominant cost)
    cost_per_incident = _estimate_cost_usd(int(mean_tokens), config.reasoning_model)

    return {
        "config": config.name,
        "label": config.label,
        "reasoning_model": config.reasoning_model,
        "fast_model": config.fast_model,
        "top_1_accuracy": report.top_1_accuracy,
        "citation_faithfulness": report.citation_faithfulness,
        "error_rate": report.error_rate,
        "mean_tokens_per_incident": round(mean_tokens, 0),
        "estimated_cost_usd_per_incident": round(cost_per_incident, 4),
        "eval_set_size": report.eval_set_size,
    }


def run_cost_routing(
    data_dir: pathlib.Path = pathlib.Path("data/incidents"),
    concurrency: int = 2,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for config in _CONFIGS:
        result = asyncio.run(_run_config(config, data_dir, concurrency))
        results.append(result)
        log.info(
            "cost-routing: config done",
            config=config.name,
            accuracy=f"{result['top_1_accuracy']:.0%}",
            cost=f"${result['estimated_cost_usd_per_incident']:.4f}/incident",
        )

    output = _RESULTS_DIR / "cost_routing.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2))
    log.info("cost-routing: results written", path=str(output))

    _print_table(results)
    return results


def _print_table(results: list[dict[str, Any]]) -> None:
    print("\n─── Cost-Routing Comparison ──────────────────────────────────────────")
    print(f"  {'Configuration':<40} {'Top-1':>6}  {'Faith':>6}  {'Tokens':>8}  {'$/incident':>11}")
    print(f"  {'─' * 40} {'─' * 6}  {'─' * 6}  {'─' * 8}  {'─' * 11}")
    for r in results:
        print(
            f"  {r['label']:<40} "
            f"{r['top_1_accuracy']:>5.0%}  "
            f"{r['citation_faithfulness']:>5.0%}  "
            f"{r['mean_tokens_per_incident']:>8,.0f}  "
            f"${r['estimated_cost_usd_per_incident']:>10.4f}"
        )
    print("──────────────────────────────────────────────────────────────────────\n")
