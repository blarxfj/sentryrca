"""Tests for the traced decorator and update_current_span in no-op mode.

These tests run without LANGFUSE_HOST set, so they exercise the graceful fallback
path — the decorator returns the original function unchanged.
"""

import os


def test_traced_noop_returns_original_function() -> None:
    """Without LANGFUSE_HOST, traced() must return the original function unchanged."""
    os.environ.pop("LANGFUSE_HOST", None)
    os.environ.pop("LANGFUSE_PUBLIC_KEY", None)

    from sentryrca.observability.tracing import traced

    def my_fn(x: int) -> int:
        return x * 2

    wrapped = traced(name="test.fn", capture_io=True)(my_fn)
    assert wrapped is my_fn


def test_traced_noop_decorated_function_executes() -> None:
    """A no-op traced function must still execute normally."""
    os.environ.pop("LANGFUSE_HOST", None)
    os.environ.pop("LANGFUSE_PUBLIC_KEY", None)

    from sentryrca.observability.tracing import traced

    @traced(name="test.add")
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5


def test_update_current_span_noop_is_silent() -> None:
    """update_current_span must not raise when Langfuse is not configured."""
    os.environ.pop("LANGFUSE_HOST", None)
    os.environ.pop("LANGFUSE_PUBLIC_KEY", None)

    from sentryrca.observability.tracing import update_current_span

    update_current_span(usage={"total_tokens": 100}, metadata={"model": "test"})
