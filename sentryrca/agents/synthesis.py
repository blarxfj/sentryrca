"""Synthesis node — combines specialist findings into a validated RCAOutput.

Retries up to MAX_RETRIES times if Pydantic validation fails, injecting the
error into the prompt so the model can correct itself.
"""

import json
import re
import time
from typing import Any

import litellm
import structlog
from pydantic import ValidationError

from sentryrca.agents.prompts import SYNTHESIS_PROMPT, SYNTHESIS_RETRY_CONTEXT
from sentryrca.agents.state import RCAState
from sentryrca.config import settings
from sentryrca.observability import traced, update_current_span
from sentryrca.schema.rca import RCAOutput

log = structlog.get_logger()

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

MAX_RETRIES = 3
PROMPT_VERSION = "synthesis-v1"


def _evidence_block(evidence: list[dict[str, Any]]) -> str:
    lines = []
    for item in evidence:
        lines.append(
            f"id={item['id']} | source={item['source']} | source_id={item['source_id']}\n"
            f"excerpt: {item['excerpt'][:300]}\n"
            f"why_it_matters: {item.get('why_it_matters', '')}"
        )
    return "\n\n".join(lines)


def _p95(latencies: list[int]) -> int:
    if not latencies:
        return 0
    sorted_l = sorted(latencies)
    idx = max(0, int(len(sorted_l) * 0.95) - 1)
    return sorted_l[idx]


@traced(name="agent.synthesis")
async def synthesis_node(state: RCAState) -> dict[str, Any]:
    t0 = time.monotonic()
    incident = state["incident"]
    evidence = state.get("evidence", [])
    attempts = state.get("synthesis_attempts", 0)
    total_tokens = state.get("total_tokens", 0)
    latencies = state.get("step_latencies_ms", [])

    retry_context = ""
    if state.get("error"):
        retry_context = SYNTHESIS_RETRY_CONTEXT.format(errors=state["error"])

    prompt = SYNTHESIS_PROMPT.format(
        incident_id=incident["id"],
        severity=incident["severity"],
        affected_service=incident["affected_service"],
        alert_text=incident["alert_text"],
        log_findings=state.get("log_findings") or "No log analysis available.",
        deploy_findings=state.get("deploy_findings") or "No deploy analysis available.",
        evidence_block=_evidence_block(evidence),
        model_version=settings.litellm_model_reasoning,
        prompt_version=PROMPT_VERSION,
        agent_step_count=attempts + 3,  # 3 fixed steps: log_analyst + deploy_inspector + synthesis
        total_tokens=total_tokens,
        total_cost_usd=0.0,  # placeholder; updated after this call
        p95_step_latency_ms=_p95(latencies),
        retry_context=retry_context,
    )

    response = await litellm.acompletion(
        model=settings.litellm_model_reasoning,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    raw_content = (response.choices[0].message.content or "").strip()
    m = _FENCE_RE.match(raw_content)
    content = m.group(1).strip() if m else raw_content

    tokens_used = int(getattr(response.usage, "total_tokens", 0))
    latency_ms = int((time.monotonic() - t0) * 1000)

    total_tokens += tokens_used
    latencies = [*latencies, latency_ms]

    try:
        raw: dict[str, Any] = json.loads(content) if content else {}
        # Patch in accurate LLMOps metadata now that we know the final numbers.
        raw["total_tokens"] = total_tokens
        raw["p95_step_latency_ms"] = _p95(latencies)
        raw["agent_step_count"] = attempts + 3

        rca = RCAOutput.model_validate(raw)

        # Replace RCA evidence with pre-built verbatim items only.
        # The model sometimes invents new IDs or paraphrases excerpts; we strip
        # those and keep only evidence whose excerpts are from retrieved chunks.
        # Replace evidence with pre-built verbatim items; filter out any IDs the
        # model invented. IDs are now deterministic ("evd-<chunk_id>") so this
        # always produces a clean match against the pre-built set.
        pre_built = {item["id"]: item for item in state.get("evidence", [])}
        kept_ids = {ev.id for ev in rca.evidence if ev.id in pre_built}

        if not kept_ids:
            # Fallback: the model used different IDs — use all pre-built items.
            kept_ids = set(pre_built.keys())

        raw["evidence"] = [{**pre_built[eid]} for eid in pre_built if eid in kept_ids]
        raw["timeline"] = [
            t for t in raw.get("timeline", []) if t.get("source_evidence_id") in kept_ids
        ]
        rca = RCAOutput.model_validate(raw)

        update_current_span(
            metadata={
                "incident_id": incident["id"],
                "synthesis_attempts": attempts + 1,
                "total_tokens": total_tokens,
            }
        )
        log.info(
            "synthesis: success",
            incident_id=incident["id"],
            attempts=attempts + 1,
            confidence=rca.confidence,
            tokens=total_tokens,
        )
        return {
            "rca": rca.model_dump(),
            "synthesis_attempts": attempts + 1,
            "error": None,
            "total_tokens": total_tokens,
            "step_latencies_ms": latencies,
        }

    except (ValidationError, json.JSONDecodeError, KeyError) as exc:
        error_msg = str(exc)
        log.warning(
            "synthesis: validation failed",
            incident_id=incident["id"],
            attempt=attempts + 1,
            error=error_msg,
        )
        update_current_span(
            metadata={
                "incident_id": incident["id"],
                "synthesis_attempt": attempts + 1,
                "validation_error": error_msg,
            }
        )
        return {
            "synthesis_attempts": attempts + 1,
            "error": error_msg,
            "total_tokens": total_tokens,
            "step_latencies_ms": latencies,
        }
