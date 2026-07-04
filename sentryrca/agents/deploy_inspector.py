"""DeployInspector specialist — analyses recent deploys and identifies regression candidates."""

import json
import re
import time
from typing import Any

import litellm
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sentryrca.agents.prompts import DEPLOY_INSPECTOR_PROMPT
from sentryrca.agents.state import RCAState
from sentryrca.config import settings
from sentryrca.observability import traced

log = structlog.get_logger()

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _parse_json(raw: str) -> dict[str, Any]:
    stripped = (raw or "").strip()
    m = _FENCE_RE.match(stripped)
    if m:
        stripped = m.group(1).strip()
    try:
        result: dict[str, Any] = json.loads(stripped) if stripped else {}
        return result
    except json.JSONDecodeError:
        log.warning("deploy_inspector: failed to parse JSON response", raw=raw[:200])
        return {}


def _format_deploys_block(deploys: list[dict[str, Any]]) -> str:
    lines = []
    for d in deploys:
        files = ", ".join(d.get("changed_files", [])) or "no files recorded"
        lines.append(
            f"SHA: {d['sha']}\n"
            f"Author: {d['author']}\n"
            f"Time: {d['timestamp']}\n"
            f"Message: {d['message']}\n"
            f"Files: {files}"
        )
    return "\n\n".join(lines)


def _deploy_excerpt(deploy: dict[str, Any]) -> str:
    """Build verbatim deploy text using the exact same format as the chunker.

    This guarantees the excerpt appears in build_corpus_text() without relying
    on the retrieval layer or LLM to supply accurate source text.
    """
    files = ", ".join(deploy.get("changed_files", [])) or "no files recorded"
    return (
        f"Deploy {deploy['sha']} by {deploy['author']} at {deploy['timestamp']}.\n"
        f"Message: {deploy['message']}\n"
        f"Changed files: {files}"
    )


def _chunk_id_for_deploy(incident_id: str, deploy: dict[str, Any]) -> str:
    """Mirrors the chunk ID scheme in chunker.py."""
    return f"{incident_id}_deploy_{deploy['sha'][:12]}"


def _build_evidence_items(
    incident_id: str,
    deploys: list[dict[str, Any]],
    findings: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build deploy evidence items with verbatim excerpts.

    Matches suspicious SHAs from LLM findings to the incident's actual deploy
    entries; excerpts are generated deterministically from the deploy data.
    """
    # Collect SHAs the LLM flagged as suspicious
    suspicious: set[str] = set()
    culprit = str(findings.get("culprit_sha") or "")
    if culprit:
        suspicious.add(culprit[:12])
    for item in findings.get("evidence_items", []):
        sha = str(item.get("sha") or item.get("source_id") or "")[:12]
        if sha:
            suspicious.add(sha)

    # Match to actual deploy entries
    deploy_by_sha_prefix = {d["sha"][:12]: d for d in deploys}
    matched: list[dict[str, Any]] = [
        deploy_by_sha_prefix[s] for s in suspicious if s in deploy_by_sha_prefix
    ]

    # If the LLM couldn't identify any real SHA, fall back to the most recent deploy
    if not matched and deploys:
        matched = [deploys[-1]]

    validated: list[dict[str, Any]] = []
    seen_shas: set[str] = set()
    for deploy in matched:
        sha_prefix = deploy["sha"][:12]
        if sha_prefix in seen_shas:
            continue
        seen_shas.add(sha_prefix)
        chunk_id = _chunk_id_for_deploy(incident_id, deploy)
        validated.append(
            {
                "id": f"evd-{chunk_id}",
                "source": "deploy_diff",
                "excerpt": _deploy_excerpt(deploy),
                "source_id": chunk_id,
                "why_it_matters": (
                    findings.get("summary", "")[:200] or "Identified as regression candidate"
                ),
            }
        )
    return validated


@traced(name="agent.deploy_inspector")
async def deploy_inspector_node(
    state: RCAState,
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, Any]:
    t0 = time.monotonic()
    incident = state["incident"]
    deploys = incident.get("recent_deploys", [])

    deploys_block = _format_deploys_block(deploys)
    prompt = DEPLOY_INSPECTOR_PROMPT.format(
        alert_text=incident["alert_text"],
        deploys_block=deploys_block,
        log_findings=state.get("log_findings") or "Not yet available.",
    )

    response = await litellm.acompletion(
        model=settings.litellm_model_fast,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    content = response.choices[0].message.content or ""
    findings = _parse_json(content)

    evidence_items = _build_evidence_items(incident["id"], deploys, findings)

    tokens_used = int(getattr(response.usage, "total_tokens", 0))
    latency_ms = int((time.monotonic() - t0) * 1000)
    log.info(
        "deploy_inspector: complete",
        culprit_sha=findings.get("culprit_sha"),
        confidence=findings.get("culprit_confidence"),
        evidence_items=len(evidence_items),
        tokens=tokens_used,
        latency_ms=latency_ms,
    )

    return {
        "deploy_findings": findings.get("summary", ""),
        "evidence": state.get("evidence", []) + evidence_items,
        "total_tokens": state.get("total_tokens", 0) + tokens_used,
        "step_latencies_ms": [*state.get("step_latencies_ms", []), latency_ms],
    }
