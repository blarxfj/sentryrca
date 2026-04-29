"""Langfuse tracing decorator with graceful no-op fallback.

Usage:
    from sentryrca.observability import traced, update_current_span

    @traced(name="llm.synthesis", capture_io=True)
    async def synthesize(prompt: str) -> str: ...

    # Inside a traced function, attach usage metadata:
    update_current_span(usage={"total_tokens": 1200}, metadata={"model": "claude-sonnet-4-6"})
"""

import os
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def _langfuse_configured() -> bool:
    return bool(os.getenv("LANGFUSE_HOST") and os.getenv("LANGFUSE_PUBLIC_KEY"))


def traced(name: str, capture_io: bool = True) -> Callable[[F], F]:
    """Wrap a callable with a Langfuse observation span.

    Falls back to the original function unchanged when Langfuse is not configured
    (LANGFUSE_HOST or LANGFUSE_PUBLIC_KEY unset), so tests and local runs never
    require a running Langfuse instance.
    """

    def decorator(func: F) -> F:
        if not _langfuse_configured():
            return func
        try:
            from langfuse.decorators import observe

            wrapped: F = observe(
                name=name,
                capture_input=capture_io,
                capture_output=capture_io,
            )(func)
            return wrapped
        except ImportError:
            return func

    return decorator


def update_current_span(**kwargs: Any) -> None:
    """Update the active Langfuse observation with additional metadata.

    No-ops silently if Langfuse is not configured or not installed.
    Typical usage: update_current_span(usage={...}, metadata={...})
    """
    if not _langfuse_configured():
        return
    try:
        from langfuse.decorators import langfuse_context

        langfuse_context.update_current_observation(**kwargs)
    except (ImportError, Exception):  # never let tracing crash the agent
        pass
