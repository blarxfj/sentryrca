"""Generate 50 synthetic incidents (5 categories x 10 each) via Claude.

Run: python -m sentryrca.synthetic.generator
Output: data/incidents/synthetic/syn-001.json … syn-050.json

Idempotent: existing files are skipped. Re-run to fill gaps after failures.
"""

import asyncio
import random
import sys
from pathlib import Path

import structlog
from pydantic import ValidationError

from sentryrca.schema.incident import IncidentCase
from sentryrca.synthetic._llm import call_llm_json
from sentryrca.synthetic._otel_fixtures import load_otel_commits, sample_commits
from sentryrca.synthetic._prompts import SYNTHETIC_SYSTEM_PROMPT, synthetic_user_prompt

log = structlog.get_logger()

OUTPUT_DIR = Path("data/incidents/synthetic")
CONCURRENCY = 5

# 5 categories x 10 scenarios = 50 incidents
# Each entry: (affected_service, scenario_hint)
CATEGORY_MATRIX: dict[str, list[tuple[str, str]]] = {
    "db_saturation": [
        ("checkout-service", "N+1 query in order finalization added in last deploy"),
        ("payment-service", "connection pool size misconfigured after infra ticket"),
        ("cart-service", "bulk import job contending with peak traffic"),
        ("postgres", "autovacuum blocked by long-running analytics query"),
        ("checkout-service", "missing index on high-cardinality foreign key column"),
        ("cart-service", "ORM lazy-loading nested cart items in a loop"),
        ("payment-service", "deadlock between concurrent payment retry transactions"),
        ("postgres", "table bloat from unvacuumed high-churn table"),
        ("checkout-service", "query plan regression after pg_statistics reset"),
        ("cart-service", "connection leak in exception handling path"),
    ],
    "deploy_regression": [
        ("checkout-service", "v2.3.1 runs synchronous DB migration on startup blocking requests"),
        ("payment-service", "dependency bump broke TLS handshake with payment processor"),
        ("frontend", "webpack bundle size regression causing LCP timeout on mobile"),
        ("recommendation-service", "model serving code change broke feature serialization"),
        ("ad-service", "log level accidentally set to DEBUG in production artifact"),
        ("email-service", "template renderer version pin removed causing encoding error"),
        ("checkout-service", "feature flag read before initialization guard is in place"),
        ("currency-service", "floating-point rounding change breaks exchange rate calc"),
        ("frontend", "CSP header change blocks required third-party script"),
        ("payment-service", "retry budget exhausted due to doubled default timeout value"),
    ],
    "dependency_outage": [
        ("checkout-service", "currency-service unavailable due to upstream forex API rate-limit"),
        ("payment-service", "fraud detection service cold-start after scale-to-zero"),
        ("frontend", "recommendation-service timeout cascade degrading homepage"),
        ("checkout-service", "email-service queue backup blocking order confirmation"),
        ("cart-service", "redis cluster failover causing elevated read latency"),
        ("frontend", "ad-service cascade timeout on personalization variant"),
        ("payment-service", "Stripe webhook endpoint slow causing payment retry storm"),
        ("checkout-service", "DNS resolution delay for external shipping API"),
        ("cart-service", "gRPC keepalive timeout mismatch with load balancer idle timeout"),
        ("frontend", "CDN origin shield timeout propagating to all edge nodes"),
    ],
    "config_error": [
        ("currency-service", "rate-limit env var absent after Kubernetes rollout"),
        ("payment-service", "mTLS cert path wrong after secrets rotation"),
        ("kafka", "topic replication factor set to 1 after cluster resize"),
        ("currency-service", "feature-flag service URL wrong in promoted config"),
        ("redis", "maxmemory-policy reset to noeviction after node restart"),
        ("payment-service", "CORS origin list missing new frontend subdomain"),
        ("kafka", "consumer group offsets reset during broker replacement"),
        ("currency-service", "request timeout reverted to default after ConfigMap edit"),
        ("redis", "persistence disabled after RDB snapshot failure alert"),
        ("payment-service", "circuit-breaker threshold misconfigured in Helm values"),
    ],
    "resource_exhaustion": [
        ("frontend", "goroutine leak from unclosed gRPC streams on client disconnect"),
        ("recommendation-service", "ML model cache growing unbounded after feature store change"),
        ("ad-service", "goroutine leak from unclosed HTTP response bodies in client"),
        ("frontend", "response buffer held in middleware after client disconnect"),
        ("recommendation-service", "goroutine leak on context cancellation in batch scorer"),
        ("ad-service", "log buffer not flushed at high throughput causing heap growth"),
        ("email-service", "attachment byte slices retained in memory after send completion"),
        ("frontend", "websocket connection pool not pruned after idle timeout"),
        ("email-service", "template rendering cache with no TTL exhausts heap"),
        ("redis", "maxmemory-policy noeviction fills memory, blocking all writes"),
    ],
}


async def _generate_one(
    incident_id: str,
    category: str,
    affected_service: str,
    scenario_hint: str,
    otel_commits: list[dict[str, str]],
    semaphore: asyncio.Semaphore,
) -> IncidentCase:
    async with semaphore:
        deploy_sample = sample_commits(
            otel_commits,
            n=7,
            rng=random.Random(incident_id),
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYNTHETIC_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": synthetic_user_prompt(
                    category=category,
                    affected_service=affected_service,
                    otel_commits=deploy_sample,
                    incident_id=incident_id,
                    scenario_hint=scenario_hint,
                ),
            },
        ]

        for attempt in range(3):
            raw = await call_llm_json(messages)
            try:
                return IncidentCase.model_validate_json(raw)
            except ValidationError as exc:
                log.warning(
                    "incident_validation_failed",
                    incident_id=incident_id,
                    attempt=attempt + 1,
                    errors=str(exc.errors())[:300],
                )
                if attempt == 2:
                    raise
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"The JSON failed validation with these errors:\n"
                            f"{exc.errors()}\n\n"
                            "Fix every error and return valid JSON only."
                        ),
                    }
                )

        raise RuntimeError(f"unreachable: {incident_id}")


async def generate_all(output_dir: Path = OUTPUT_DIR) -> dict[str, int]:
    """Generate all 50 synthetic incidents. Returns {ok, skipped, failed} counts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    otel_commits = await load_otel_commits()
    semaphore = asyncio.Semaphore(CONCURRENCY)

    tasks: list[tuple[Path, asyncio.Task[IncidentCase]]] = []
    idx = 1
    for category, scenarios in CATEGORY_MATRIX.items():
        for affected_service, scenario_hint in scenarios:
            incident_id = f"syn-{idx:03d}"
            out_path = output_dir / f"{incident_id}.json"
            if out_path.exists():
                log.info("skipping_existing", incident_id=incident_id)
                idx += 1
                continue
            task: asyncio.Task[IncidentCase] = asyncio.create_task(
                _generate_one(
                    incident_id=incident_id,
                    category=category,
                    affected_service=affected_service,
                    scenario_hint=scenario_hint,
                    otel_commits=otel_commits,
                    semaphore=semaphore,
                )
            )
            tasks.append((out_path, task))
            idx += 1

    skipped = 50 - len(tasks)
    if not tasks:
        log.info("all_incidents_already_generated", count=50)
        return {"ok": 0, "skipped": skipped, "failed": 0}

    log.info("generating_incidents", count=len(tasks), concurrency=CONCURRENCY)
    results = await asyncio.gather(*[t for _, t in tasks], return_exceptions=True)

    ok = failed = 0
    for (out_path, _), result in zip(tasks, results, strict=True):
        if isinstance(result, BaseException):
            log.error("generation_failed", path=str(out_path), error=str(result))
            failed += 1
        else:
            out_path.write_text(result.model_dump_json(indent=2))
            log.info("generated", path=str(out_path))
            ok += 1

    log.info(
        "generation_complete",
        ok=ok,
        skipped=skipped,
        failed=failed,
        total=50,
    )
    return {"ok": ok, "skipped": skipped, "failed": failed}


async def main() -> None:
    counts = await generate_all()
    if counts["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
