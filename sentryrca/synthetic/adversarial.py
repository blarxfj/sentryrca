"""Generate 9 adversarial incidents where the obvious cause is NOT the root cause.

Run: python -m sentryrca.synthetic.adversarial
Output: data/incidents/adversarial/adv-001.json … adv-009.json

Each adversarial case has:
- A suspicious recent deploy (the red herring) that looks causally related.
- A real root cause that is completely unrelated to any deploy.
- Log evidence for BOTH the red herring AND the real cause.
"""

import asyncio
import sys
from pathlib import Path

import structlog
from pydantic import ValidationError

from sentryrca.schema.incident import IncidentCase
from sentryrca.synthetic._llm import call_llm_json
from sentryrca.synthetic._prompts import ADVERSARIAL_SYSTEM_PROMPT, adversarial_user_prompt

log = structlog.get_logger()

OUTPUT_DIR = Path("data/incidents/adversarial")
CONCURRENCY = 3

# Each entry: (red_herring_scenario, real_cause_scenario)
ADVERSARIAL_SCENARIOS: list[tuple[str, str]] = [
    (
        "Deploy touching nginx rate-limit config 20 minutes before incident, "
        "authored by the on-call engineer during a routine tuning ticket.",
        "Let's Encrypt TLS certificate expiry on the payment processor's "
        "webhook endpoint, causing all payment callbacks to fail with "
        "SSL_CERTIFICATE_EXPIRED errors.",
    ),
    (
        "Database migration adding a composite index on the orders table, "
        "deployed during the scheduled maintenance window.",
        "AWS us-east-1 EC2 instance-store I/O degradation on the database host, "
        "causing random fsync latency spikes unrelated to any application change.",
    ),
    (
        "Feature flag rollout enabling a new recommendation algorithm for 20%% "
        "of traffic, touching ML model serving configuration.",
        "Upstream DNS TTL misconfiguration causing stale A records for the "
        "currency exchange rate API, making all forex lookups time out.",
    ),
    (
        "Dependency version bump in checkout-service upgrading the HTTP client "
        "library from v2.1 to v2.2, touching 14 files.",
        "Kubernetes etcd leader election triggered by a network partition between "
        "control-plane nodes, causing the API server to reject pod scheduling "
        "for 4 minutes.",
    ),
    (
        "Cart service deploy adding a new promotional discount calculation, "
        "modifying the pricing engine and the cart total computation path.",
        "Third-party CDN provider (Fastly) regional outage in eu-west-1 "
        "routing all static asset requests to origin, exhausting the origin "
        "connection pool.",
    ),
    (
        "Email service deploy updating the SMTP relay configuration and "
        "switching from SendGrid to Postmark, authored 35 minutes before the incident.",
        "NTP clock skew of +47 seconds on two frontend nodes causing "
        "JWT token validation to reject all requests as expired.",
    ),
    (
        "Payment service deploy adding idempotency keys to the Stripe charge API "
        "calls — touching the payment flow, transaction logging, and retry logic.",
        "Redis primary node out-of-memory caused by a client that left "
        "MONITOR running, producing 180 GB of output per hour.",
    ),
    (
        "Kubernetes HPA config update for frontend service changing the "
        "scale-up threshold from 60%% to 80%% CPU, deployed 25 minutes prior.",
        "BGP route leak from an upstream transit provider injecting a more-specific "
        "prefix for the payment processor's IP range, black-holing all outbound "
        "payment traffic for 8 minutes.",
    ),
    (
        "Ad service deploy refactoring the A/B testing framework and updating "
        "experiment assignment logic — touching 22 source files.",
        "Hardware NIC failure on the Postgres primary node causing intermittent "
        "packet loss on the database replication channel, triggering cascading "
        "replica lag and read query failures.",
    ),
]


async def _generate_one(
    incident_id: str,
    red_herring_scenario: str,
    real_cause_scenario: str,
    semaphore: asyncio.Semaphore,
) -> IncidentCase:
    async with semaphore:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": ADVERSARIAL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": adversarial_user_prompt(
                    incident_id=incident_id,
                    red_herring_scenario=red_herring_scenario,
                    real_cause_scenario=real_cause_scenario,
                ),
            },
        ]

        for attempt in range(3):
            raw = await call_llm_json(messages)
            try:
                return IncidentCase.model_validate_json(raw)
            except ValidationError as exc:
                log.warning(
                    "adversarial_validation_failed",
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
                            f"Validation errors:\n{exc.errors()}\n\n"
                            "Fix every error and return valid JSON only. "
                            "Remember: subset must be 'adversarial' and "
                            "red_herring must be a non-empty string."
                        ),
                    }
                )

        raise RuntimeError(f"unreachable: {incident_id}")


async def generate_all(output_dir: Path = OUTPUT_DIR) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    tasks: list[tuple[Path, asyncio.Task[IncidentCase]]] = []
    for i, (red_herring, real_cause) in enumerate(ADVERSARIAL_SCENARIOS, start=1):
        incident_id = f"adv-{i:03d}"
        out_path = output_dir / f"{incident_id}.json"
        if out_path.exists():
            log.info("skipping_existing", incident_id=incident_id)
            continue
        task: asyncio.Task[IncidentCase] = asyncio.create_task(
            _generate_one(
                incident_id=incident_id,
                red_herring_scenario=red_herring,
                real_cause_scenario=real_cause,
                semaphore=semaphore,
            )
        )
        tasks.append((out_path, task))

    total = len(ADVERSARIAL_SCENARIOS)
    skipped = total - len(tasks)
    if not tasks:
        log.info("all_adversarial_already_generated")
        return {"ok": 0, "skipped": skipped, "failed": 0}

    log.info("generating_adversarial", count=len(tasks))
    results = await asyncio.gather(*[t for _, t in tasks], return_exceptions=True)

    ok = failed = 0
    for (out_path, _), result in zip(tasks, results, strict=True):
        if isinstance(result, BaseException):
            log.error("adversarial_failed", path=str(out_path), error=str(result))
            failed += 1
        else:
            out_path.write_text(result.model_dump_json(indent=2))
            log.info("generated", path=str(out_path))
            ok += 1

    log.info("adversarial_complete", ok=ok, skipped=skipped, failed=failed)
    return {"ok": ok, "skipped": skipped, "failed": failed}


async def main() -> None:
    counts = await generate_all()
    if counts["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
