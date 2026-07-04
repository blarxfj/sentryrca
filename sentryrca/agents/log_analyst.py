"""LogAnalyst specialist — retrieves relevant log chunks and analyses them with an LLM."""

import json
import re
import time
from typing import Any

import litellm
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sentryrca.agents.prompts import LOG_ANALYST_PROMPT
from sentryrca.agents.state import RCAState
from sentryrca.config import settings
from sentryrca.observability import traced
from sentryrca.retrieval.search import retrieve

log = structlog.get_logger()

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _parse_json(raw: str) -> dict[str, Any]:
    """Parse JSON from model output, stripping markdown fences if present."""
    stripped = (raw or "").strip()
    m = _FENCE_RE.match(stripped)
    if m:
        stripped = m.group(1).strip()
    try:
        result: dict[str, Any] = json.loads(stripped) if stripped else {}
        return result
    except json.JSONDecodeError:
        log.warning("log_analyst: failed to parse JSON response", raw=raw[:200])
        return {}


_SOURCE_MAP: dict[str, str] = {
    "log": "logs",
    "alert": "logs",
    "deploy": "deploy_diff",
    "runbook": "runbook",
}


def _make_chunks_block(chunks: list[Any]) -> str:
    parts = []
    for i, chunk in enumerate(chunks):
        parts.append(f"[chunk {i} | id={chunk.id} | type={chunk.chunk_type}]\n{chunk.content}")
    return "\n\n---\n\n".join(parts)


def _build_evidence_items(
    chunks: list[Any],
    findings: dict[str, Any],
) -> list[dict[str, Any]]:
    """Merge the LLM-produced evidence items with retrieval metadata for faithfulness.

    The LLM writes the `why_it_matters`; we enforce that the excerpt comes from a
    retrieved chunk (by matching source_id back to the chunk pool).
    """
    chunk_by_id = {c.id: c for c in chunks}
    validated: list[dict[str, Any]] = []

    for item in findings.get("evidence_items", []):
        source_id = item.get("source_id", "")
        chunk = chunk_by_id.get(source_id)
        if chunk is None:
            log.warning("log_analyst: evidence item references unknown chunk", source_id=source_id)
            continue
        source_literal = _SOURCE_MAP.get(chunk.chunk_type, "logs")
        validated.append(
            {
                "id": f"evd-{source_id}",  # deterministic; ties back to the chunk
                "source": source_literal,
                "excerpt": chunk.content[: min(500, len(chunk.content))],
                "source_id": source_id,
                "why_it_matters": item.get("why_it_matters", ""),
            }
        )
    return validated


@traced(name="agent.log_analyst")
async def log_analyst_node(
    state: RCAState,
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, Any]:
    t0 = time.monotonic()
    incident = state["incident"]

    async with session_factory() as session:
        chunks = await retrieve(
            incident["alert_text"],
            session,
            top_k=settings.retrieval_top_k,
            incident_id=incident["id"],
        )

    log.info("log_analyst: retrieved chunks", n=len(chunks), incident_id=incident["id"])

    chunks_block = _make_chunks_block(chunks)
    prompt = LOG_ANALYST_PROMPT.format(
        alert_text=incident["alert_text"],
        n_chunks=len(chunks),
        chunks_block=chunks_block,
    )

    response = await litellm.acompletion(
        model=settings.litellm_model_fast,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    content = response.choices[0].message.content or ""
    findings = _parse_json(content)

    evidence_items = _build_evidence_items(chunks, findings)

    tokens_used = int(getattr(response.usage, "total_tokens", 0))
    latency_ms = int((time.monotonic() - t0) * 1000)
    log.info(
        "log_analyst: complete",
        evidence_items=len(evidence_items),
        tokens=tokens_used,
        latency_ms=latency_ms,
    )

    return {
        "log_findings": findings.get("summary", ""),
        "evidence": state.get("evidence", []) + evidence_items,
        "total_tokens": state.get("total_tokens", 0) + tokens_used,
        "step_latencies_ms": [*state.get("step_latencies_ms", []), latency_ms],
    }
