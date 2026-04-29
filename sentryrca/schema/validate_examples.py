"""Smoke-test the RCA schema with a minimal valid example.

Run as: python -m sentryrca.schema.validate_examples
Used by the pre-commit hook to catch import or validation regressions early.
"""

import json
import sys

from sentryrca.schema.rca import EvidenceItem, RCAOutput, TimelineEntry


def _build_valid_example() -> RCAOutput:
    evidence = EvidenceItem(
        id="ev-001",
        source="logs",
        excerpt="FATAL: connection pool exhausted after 120s",
        source_id="chunk-abc123",
        why_it_matters="Confirms database saturation as the proximate cause",
    )
    entry = TimelineEntry(
        timestamp="2024-01-15T03:42:00Z",
        event="checkout-service began returning 500s",
        source_evidence_id="ev-001",
    )
    return RCAOutput(
        incident_id="inc-2024-001",
        severity="high",
        affected_service="checkout-service",
        timeline=[entry],
        top_hypothesis="Postgres connection pool exhausted due to slow queries from v1.4.2 deploy",
        confidence=0.87,
        alternative_hypotheses=["Redis OOM causing session lookup failures"],
        evidence=[evidence],
        likely_root_cause="Deploy v1.4.2 introduced an N+1 query in the order finalization path",
        recommended_actions=["Roll back to v1.4.1", "Add connection pool metrics alert"],
        rollback_candidate="v1.4.1",
        unknowns=["Whether the slow query was present in staging load tests"],
        next_debug_steps=["Check pg_stat_activity for blocked queries", "Review v1.4.2 diff"],
        model_version="claude-sonnet-4-6",
        prompt_version="rca-v0.1.0",
        agent_step_count=4,
        total_tokens=2840,
        total_cost_usd=0.0042,
        p95_step_latency_ms=3200,
    )


def main() -> None:
    rca = _build_valid_example()

    # Validate round-trip serialization
    serialized = rca.model_dump_json()
    restored = RCAOutput.model_validate_json(serialized)
    assert restored == rca, "Round-trip serialization failed"

    # Validate JSON schema generation
    schema = RCAOutput.model_json_schema()
    assert "properties" in schema, "JSON schema missing 'properties'"

    print(json.dumps(schema, indent=2)[:200] + "...", file=sys.stderr)
    print("schema validation OK", file=sys.stderr)


if __name__ == "__main__":
    main()
