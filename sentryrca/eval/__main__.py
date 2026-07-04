"""CLI: python -m sentryrca.eval [--fast] [--data-dir PATH] [--output PATH] [--gate]

--fast   10-incident subset used by CI eval-gate
--gate   compare against eval/baselines/main.json and exit 1 if any gate fails
"""

import argparse
import asyncio
import json
import pathlib
import sys
from typing import Any

import structlog

from sentryrca.eval.harness import load_corpus, run_eval, select_fast_subset

log = structlog.get_logger()

_BASELINE_PATH = pathlib.Path("eval/baselines/main.json")
_RESULTS_DIR = pathlib.Path("eval/results")

# CI gate thresholds (from CLAUDE.md)
_GATE_MAX_ACCURACY_DROP = 0.03  # top-1 may not drop more than 3%
_GATE_MIN_CITATION_FAITH = 0.95  # citation faithfulness floor
# p95 latency gate only applies when running with mocked/stubbed LLM calls;
# live API runs in CI skip it (set EVAL_SKIP_LATENCY_GATE=1 to bypass).
_GATE_MAX_P95_LATENCY_MS = 15_000


def _gate_check(report_dict: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """Return a list of failure messages; empty means all gates pass."""
    failures: list[str] = []

    baseline_acc: float = baseline.get("top_1_accuracy", 0.0)
    current_acc: float = report_dict.get("top_1_accuracy", 0.0)
    if baseline_acc > 0 and (baseline_acc - current_acc) > _GATE_MAX_ACCURACY_DROP:
        failures.append(
            f"top_1_accuracy dropped {baseline_acc - current_acc:.1%} "
            f"(baseline={baseline_acc:.1%}, current={current_acc:.1%}, max_drop=3%)"
        )

    faith: float = report_dict.get("citation_faithfulness", 0.0)
    if faith < _GATE_MIN_CITATION_FAITH:
        failures.append(f"citation_faithfulness={faith:.1%} < {_GATE_MIN_CITATION_FAITH:.0%} floor")

    import os

    if not os.getenv("EVAL_SKIP_LATENCY_GATE"):
        p95: int = report_dict.get("p95_latency_ms", 0)
        if p95 > _GATE_MAX_P95_LATENCY_MS:
            failures.append(f"p95_latency_ms={p95} > {_GATE_MAX_P95_LATENCY_MS} limit")

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="SentryRCA eval harness")
    parser.add_argument("--fast", action="store_true", help="Run 10-incident fast subset")
    parser.add_argument(
        "--data-dir",
        type=pathlib.Path,
        default=pathlib.Path("data/incidents"),
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=None,
        help="Write JSON results to this path (default: eval/results/latest.json)",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Compare against baseline and exit 1 if any gate fails",
    )
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()

    corpus = load_corpus(args.data_dir)
    if not corpus:
        log.error("no incidents found", data_dir=str(args.data_dir))
        sys.exit(1)

    incidents = select_fast_subset(corpus) if args.fast else corpus
    log.info(
        "starting eval",
        total=len(incidents),
        mode="fast" if args.fast else "full",
    )

    report = asyncio.run(run_eval(incidents, concurrency=args.concurrency))

    report_dict = json.loads(report.model_dump_json())

    output_path = args.output or (_RESULTS_DIR / ("fast.json" if args.fast else "latest.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report_dict, indent=2))
    log.info("results written", path=str(output_path))

    # Summary table
    print("\n─── Eval Results ────────────────────────────────────────")
    print(f"  Incidents:           {report.eval_set_size}")
    print(f"  Top-1 accuracy:      {report.top_1_accuracy:.1%}")
    print(f"  Citation faithfulness: {report.citation_faithfulness:.1%}")
    print(f"  p95 latency:         {report.p95_latency_ms} ms")
    print(f"  Mean tokens:         {report.mean_tokens:.0f}")
    print(f"  Error rate:          {report.error_rate:.1%}")
    print()
    for subset, m in report.subsets.items():
        print(
            f"  [{subset:>12}]  n={m.eval_set_size}  "
            f"top-1={m.top_1_accuracy:.0%}  faith={m.citation_faithfulness:.0%}"
        )
    print("─────────────────────────────────────────────────────────\n")

    if args.gate:
        if not _BASELINE_PATH.exists():
            log.warning("no baseline found — skipping gate check", path=str(_BASELINE_PATH))
            return
        baseline = json.loads(_BASELINE_PATH.read_text())
        failures = _gate_check(report_dict, baseline)
        if failures:
            print("EVAL GATE FAILED:")
            for f in failures:
                print(f"  ✗ {f}")
            sys.exit(1)
        print("All eval gates passed ✓")


if __name__ == "__main__":
    main()
