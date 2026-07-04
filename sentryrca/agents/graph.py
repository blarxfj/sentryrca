"""LangGraph graph: LogAnalyst → DeployInspector → Synthesis (with retry loop).

          ┌─────────────────────────────────────────────────────┐
START ──► │ log_analyst ──► deploy_inspector ──► synthesize ◄──┤
          └──────────────────────────────────────────── retry ──┘
                                                 │ success
                                                 ▼
                                                END
"""

from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sentryrca.agents.deploy_inspector import deploy_inspector_node
from sentryrca.agents.log_analyst import log_analyst_node
from sentryrca.agents.state import RCAState
from sentryrca.agents.synthesis import MAX_RETRIES, synthesis_node


def _route_after_synthesis(state: RCAState) -> str:
    """Retry synthesis up to MAX_RETRIES times on validation failure."""
    if state.get("rca") is not None:
        return END
    if (state.get("synthesis_attempts") or 0) < MAX_RETRIES:
        return "synthesize"
    return END


def build_graph(
    session_factory: async_sessionmaker[AsyncSession],
) -> Any:  # CompiledStateGraph
    """Build and compile the RCA graph with the given DB session factory."""

    # Bind session_factory into each specialist via partial so nodes stay pure functions.
    log_analyst = partial(log_analyst_node, session_factory=session_factory)
    deploy_inspector = partial(deploy_inspector_node, session_factory=session_factory)

    graph: StateGraph = StateGraph(RCAState)  # type: ignore[type-arg]

    graph.add_node("log_analyst", log_analyst)
    graph.add_node("deploy_inspector", deploy_inspector)
    graph.add_node("synthesize", synthesis_node)

    graph.add_edge(START, "log_analyst")
    graph.add_edge("log_analyst", "deploy_inspector")
    graph.add_edge("deploy_inspector", "synthesize")
    graph.add_conditional_edges(
        "synthesize",
        _route_after_synthesis,
        {"synthesize": "synthesize", END: END},
    )

    return graph.compile()
