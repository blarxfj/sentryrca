# Skill: Instrumenting code with Langfuse + OTel

1. Import the shared decorator: `from sentryrca.observability import traced`.
2. Every LLM call: `@traced(name="llm.<purpose>", capture_io=True)`.
3. Every tool call: `@traced(name="tool.<name>", capture_io=True)`.
4. Every agent node: `@traced(name="agent.<node>", capture_io=False)` — the
   node's child spans capture I/O; the node itself just timeboxes.
5. Attach metadata: `prompt_version`, `model`, `subset` (for eval runs),
   `incident_id`. These become Langfuse tags and OTel attributes.
6. For eval runs, set `langfuse_session_id = f"eval-{run_id}"` so all 70
   incidents in one run group together in the Langfuse UI.
7. Cost and token counts come from LiteLLM's response — record them on the
   span via `traced.update(usage=...)`.
8. Failures: catch, log to span as `level=ERROR`, re-raise. Never swallow.
9. If Langfuse is unreachable, instrumentation must degrade gracefully (log
   warning, continue). The agent must not fail because the tracer is down.
