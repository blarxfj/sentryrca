"""Prompt templates for synthetic incident generation.

Prompts are functions (not constants) so that the embedded JSON schema stays
live: if IncidentCase fields change, the prompt automatically reflects them.
"""

import json
import random

from sentryrca.schema.incident import IncidentCase
from sentryrca.synthetic._otel_fixtures import OtelCommit

# ---------------------------------------------------------------------------
# Shared system instruction embedded in every prompt
# ---------------------------------------------------------------------------

SYNTHETIC_SYSTEM_PROMPT = """\
You are an expert at generating realistic synthetic production incident data \
for AI system evaluation benchmarks.

STRICT OUTPUT RULES:
- Output ONLY valid JSON. No markdown, no code fences, no explanations.
- The JSON must exactly match the schema provided in the user message.
- log_window is a SINGLE STRING where log lines are separated by \\n.
- All timestamps must be ISO 8601 (e.g., 2024-01-15T03:42:17.234Z).
- recent_deploys must be in chronological order (oldest first).

LOG WINDOW REQUIREMENTS (strictly enforced):
- 60-120 log lines (approximately 2,500-5,000 characters total).
- Timestamps progress forward across 10-30 minutes.
- Logs from 2-4 different services (affected service + its dependencies).
- Log levels: DEBUG, INFO, WARN, ERROR, FATAL. Errors escalate gradually.
- Includes BOTH: (a) user-visible symptoms AND (b) internal diagnostic signals.
- Partial stack traces where appropriate (2-4 lines, not full traces).
- Realistic log formats: some services use JSON, some key=value, some plain text.

DEPLOY ENTRY REQUIREMENTS:
- Use the provided commit SHAs exactly — never invent new ones.
- Add plausible changed_files based on the service and commit message.
- The culprit deploy (if relevant) should be the 2nd or 3rd most recent.

GROUND TRUTH REQUIREMENTS:
- ground_truth_root_cause: specific and technical; references the exact SHA \
where a deploy caused the issue.
- ground_truth_remediation: concrete, achievable within 2 hours.
"""

POSTMORTEM_SYSTEM_PROMPT = """\
You are generating realistic synthetic incident data inspired by real-world \
production post-mortems for an AI RCA evaluation benchmark.

STRICT OUTPUT RULES:
- Output ONLY valid JSON matching the schema in the user message.
- Do not copy the post-mortem description verbatim — generate plausible \
  technical details (log lines, stack traces, deploy SHAs) that are consistent \
  with the described incident.
- subset must be "real_derived".
- id must follow the pattern real-NNN where NNN is the provided number.
- recent_deploys must include 5-7 plausible (but fictitious) deploy entries \
  since there are no real OTel SHAs for these cases.

LOG WINDOW: realistic logs that match the failure mode described in the \
post-mortem. Include both symptoms and diagnostic signals. 60-100 lines.
"""

ADVERSARIAL_SYSTEM_PROMPT = """\
You are generating adversarial test cases for an AI root cause analysis system.
These cases test whether the agent can resist "blame the latest deploy" bias.

STRICT OUTPUT RULES:
- Output ONLY valid JSON matching the schema in the user message.
- subset must be "adversarial".
- red_herring must be non-null and must explain: (a) why the suspicious deploy \
  looks causally related, AND (b) what exculpatory evidence appears in the logs.

INCIDENT STRUCTURE:
1. A recent deploy touches files that look causally related to the failure \
   (the RED HERRING). It is timestamped 15-60 minutes before the incident.
2. The REAL cause is completely unrelated to any deploy.
3. The log_window MUST contain evidence of the real cause (DNS NXDOMAIN errors, \
   cert validation failures, cloud provider error codes, etc.).
4. A careful reader CAN find the real cause in the logs — it is not hidden.
"""

# ---------------------------------------------------------------------------
# Category-specific guidance
# ---------------------------------------------------------------------------

_CATEGORY_GUIDANCE: dict[str, str] = {
    "db_saturation": (
        "Logs show increasing query latency, connection pool exhaustion, and "
        "eventual HTTP 5xx responses. Root cause references a specific query "
        "pattern or schema change introduced in a recent deploy. Remediation "
        "includes a rollback or an index addition."
    ),
    "deploy_regression": (
        "Error rate spike or latency increase correlates with a specific deploy "
        "timestamp visible in the logs. Root cause is a code change in the "
        "2nd-most-recent deploy (not the latest). Remediation is a rollback."
    ),
    "dependency_outage": (
        "The affected service is healthy but a downstream OTel service it calls "
        "is unavailable or very slow. Logs show connection refused, timeouts, or "
        "circuit breaker OPEN events. Root cause is the downstream dependency, "
        "NOT the affected service. Remediation involves the dependency team."
    ),
    "config_error": (
        "Service fails to start or behaves incorrectly due to a misconfiguration. "
        "Logs show config parsing errors, missing environment variables, or "
        "invalid values. Root cause references a specific config key changed in "
        "a recent deploy or infra change. Remediation restores the correct value."
    ),
    "resource_exhaustion": (
        "Service runs out of memory, file descriptors, or goroutines/threads. "
        "Logs show OOM kills, GC pressure, or goroutine leak warnings. Root cause "
        "references a specific code path introduced in a recent deploy. "
        "Remediation includes a restart and a code fix."
    ),
}

# ---------------------------------------------------------------------------
# User prompt builders
# ---------------------------------------------------------------------------


def synthetic_user_prompt(
    category: str,
    affected_service: str,
    otel_commits: list[OtelCommit],
    incident_id: str,
    scenario_hint: str,
) -> str:
    schema = json.dumps(IncidentCase.model_json_schema(), indent=2)
    commits_text = json.dumps(otel_commits, indent=2)
    guidance = _CATEGORY_GUIDANCE.get(category, "")

    return (
        f"Generate a synthetic production incident JSON with these parameters:\n\n"
        f"INCIDENT ID: {incident_id}\n"
        f"CATEGORY: {category}\n"
        f"AFFECTED SERVICE: {affected_service}\n"
        f"SCENARIO: {scenario_hint}\n\n"
        f"CATEGORY GUIDANCE:\n{guidance}\n\n"
        f"REAL OTEL COMMIT DATA — use these exact SHAs in recent_deploys:\n"
        f"{commits_text}\n\n"
        f"JSON SCHEMA TO MATCH EXACTLY:\n{schema}\n\n"
        f'The id field must be exactly "{incident_id}".\n'
        f"Return valid JSON only."
    )


def postmortem_user_prompt(
    company: str,
    description: str,
    incident_id: str,
) -> str:
    schema = json.dumps(IncidentCase.model_json_schema(), indent=2)

    return (
        f"Generate a real_derived incident case inspired by this post-mortem:\n\n"
        f"COMPANY / SERVICE: {company}\n"
        f"INCIDENT DESCRIPTION: {description}\n\n"
        f"INCIDENT ID: {incident_id}\n\n"
        f"Choose an appropriate category, affected_service (from the OTel demo "
        f"service list where possible: frontend, checkout-service, payment-service, "
        f"currency-service, cart-service, recommendation-service, email-service, "
        f"ad-service, postgres, redis, kafka), severity, and generate realistic "
        f"log lines and deploy entries consistent with the described incident.\n\n"
        f"JSON SCHEMA TO MATCH EXACTLY:\n{schema}\n\n"
        f'The id field must be exactly "{incident_id}".\n'
        f"Return valid JSON only."
    )


def adversarial_user_prompt(
    incident_id: str,
    red_herring_scenario: str,
    real_cause_scenario: str,
) -> str:
    schema = json.dumps(IncidentCase.model_json_schema(), indent=2)

    # Pick random OTel services for variety
    _rng = random.Random(incident_id)
    affected = _rng.choice(["checkout-service", "payment-service", "frontend", "cart-service"])

    return (
        f"Generate an adversarial incident case with:\n\n"
        f"INCIDENT ID: {incident_id}\n"
        f"AFFECTED SERVICE: {affected}\n\n"
        f"RED HERRING (suspicious but innocent deploy):\n{red_herring_scenario}\n\n"
        f"REAL CAUSE (unrelated to any deploy):\n{real_cause_scenario}\n\n"
        f"The recent_deploys must include the suspicious deploy as one of the entries "
        f"(use plausible but fictitious SHAs — there are no real OTel commits for "
        f"adversarial cases). Invent 5-7 realistic deploys.\n\n"
        f"JSON SCHEMA TO MATCH EXACTLY:\n{schema}\n\n"
        f'The id field must be exactly "{incident_id}".\n'
        f"Return valid JSON only."
    )
