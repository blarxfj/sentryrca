"""Shared LiteLLM call helper for synthetic generators.

All LLM calls go through call_llm_json(), which:
- Routes through settings.litellm_model_reasoning
- Uses response_format=json_object
- Attaches a Langfuse trace via @traced
- Records token usage on the active span
- Raises ValueError on malformed responses (no choices, non-str content)
"""

import asyncio

import litellm
import structlog

from sentryrca.config import settings
from sentryrca.observability import traced, update_current_span

log = structlog.get_logger()


def _extract_content(response: object) -> str:
    """Narrow litellm's Any-typed response to a plain str.

    Raises ValueError if the response shape is unexpected — surfaces as a
    retryable error in the caller rather than an AttributeError deep in a
    call stack.
    """
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or not choices:
        raise ValueError(f"unexpected litellm response shape (no choices): {response!r}")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if not isinstance(content, str):
        raise ValueError(f"message.content is not str: {content!r}")
    return content


def _record_usage(response: object) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    update_current_span(
        usage={
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        },
        metadata={"model": settings.litellm_model_reasoning},
    )


@traced(name="llm.call_json", capture_io=True)
async def call_llm_json(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    max_attempts: int = 3,
) -> str:
    """Call LiteLLM with JSON mode. Returns raw content string.

    Retries up to max_attempts times on network / API errors with exponential
    backoff. Validation retries (appending the schema error to messages) are
    the caller's responsibility — they need to mutate the messages list.
    """
    effective_model = model or settings.litellm_model_reasoning
    last_exc: Exception = RuntimeError("no attempts made")

    for attempt in range(max_attempts):
        try:
            response = await litellm.acompletion(
                model=effective_model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            content = _extract_content(response)
            _record_usage(response)
            return content
        except Exception as exc:
            last_exc = exc
            log.warning(
                "llm_call_failed",
                attempt=attempt + 1,
                max_attempts=max_attempts,
                error=str(exc)[:200],
            )
            if attempt < max_attempts - 1:
                await asyncio.sleep(2**attempt)

    raise RuntimeError(f"LLM call failed after {max_attempts} attempts") from last_exc
