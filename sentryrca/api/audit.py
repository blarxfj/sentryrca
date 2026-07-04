"""Write completed RCA runs to the rca_runs audit table."""

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from sentryrca.schema.rca import RCAOutput


async def write_rca_run(session: AsyncSession, rca: RCAOutput) -> str:
    """Insert a completed RCA run into the audit table and return its run id."""
    run_id = str(uuid.uuid4())
    await session.execute(
        sa.text(
            """
            INSERT INTO rca_runs (
                id, incident_id, model_version, prompt_version,
                agent_step_count, total_tokens, total_cost_usd,
                p95_step_latency_ms, output
            ) VALUES (
                :id, :incident_id, :model_version, :prompt_version,
                :agent_step_count, :total_tokens, :total_cost_usd,
                :p95_step_latency_ms, CAST(:output AS jsonb)
            )
            """
        ),
        {
            "id": run_id,
            "incident_id": rca.incident_id,
            "model_version": rca.model_version,
            "prompt_version": rca.prompt_version,
            "agent_step_count": rca.agent_step_count,
            "total_tokens": rca.total_tokens,
            "total_cost_usd": rca.total_cost_usd,
            "p95_step_latency_ms": rca.p95_step_latency_ms,
            "output": rca.model_dump_json(),
        },
    )
    return run_id
