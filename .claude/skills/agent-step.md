# Skill: Adding or modifying an agent step

Every agent step (LangGraph node) follows this pattern:

1. Wrap the LLM call with `@traced(name="agent.<step_name>")` from
   `sentryrca/observability/tracing.py`. Langfuse captures input, output,
   latency, tokens, cost automatically.
2. Route all LLM calls through `litellm.acompletion(...)` using model names
   from `settings.models` — never hardcode `claude-sonnet-4-...`.
3. Tool calls (retrieval, deploy lookup) are also `@traced`. Trace nesting
   matters — child spans must be under the parent agent span.
4. The step's input and output are Pydantic models. No raw dicts crossing
   step boundaries.
5. If the step produces structured output, use LiteLLM's `response_format`
   with the Pydantic model. On parse failure, retry once with the validation
   error appended to the prompt. Cap total retries per step at 3.
6. Every retry is logged to Langfuse as a separate span tagged `retry=true`.
7. Add a test in `tests/agents/` that mocks LiteLLM and asserts: span is
   emitted, retries happen on bad output, output validates against schema.
