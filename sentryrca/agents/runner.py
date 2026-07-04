"""Public entry point: run_rca(incident) → RCAOutput."""

from typing import Any

import structlog

from sentryrca.agents.graph import build_graph
from sentryrca.agents.state import RCAState
from sentryrca.api.audit import write_rca_run
from sentryrca.retrieval.models import make_engine, make_session_factory
from sentryrca.schema.incident import IncidentCase
from sentryrca.schema.rca import RCAOutput

log = structlog.get_logger()


async def run_rca(incident: IncidentCase) -> RCAOutput:
    """Run the full multi-agent RCA pipeline and persist the result to the audit table."""
    engine = make_engine()
    session_factory = make_session_factory(engine)
    try:
        graph = build_graph(session_factory)
        initial_state: RCAState = {
            "incident": incident.model_dump(),
            "log_findings": None,
            "deploy_findings": None,
            "evidence": [],
            "synthesis_attempts": 0,
            "rca": None,
            "error": None,
            "total_tokens": 0,
            "step_latencies_ms": [],
        }
        result: dict[str, Any] = await graph.ainvoke(initial_state)

        if result.get("rca") is None:
            raise RuntimeError(
                f"RCA failed after {result.get('synthesis_attempts', 0)} synthesis attempts. "
                f"Last error: {result.get('error')}"
            )

        rca = RCAOutput.model_validate(result["rca"])

        async with session_factory() as session:
            async with session.begin():
                run_id = await write_rca_run(session, rca)
        log.info("rca run persisted", run_id=run_id, incident_id=rca.incident_id)

        return rca
    finally:
        await engine.dispose()
