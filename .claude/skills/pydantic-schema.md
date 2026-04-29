# Skill: Defining Pydantic schemas for SentryRCA

When defining or modifying a data contract:

1. Pydantic v2, never v1. `from pydantic import BaseModel, Field`.
2. Every field has a type. No `Any`, no bare `dict`, no bare `list`.
3. Use `Literal[...]` for enums of strings. Use `Field(..., description=...)`
   for anything an LLM will populate — descriptions become part of the prompt
   contract via JSON schema.
4. Required fields use `...` as default. Optional fields use `None` with
   `Optional[T]` or `T | None`.
5. Validators (`@field_validator`, `@model_validator`) for cross-field
   invariants. Example: every `TimelineEntry.source_evidence_id` must match
   an `id` in the parent `RCAOutput.evidence` list — enforce in a model
   validator, not in business logic.
6. Schemas live in `sentryrca/schema/`. One module per logical contract.
   Re-export from `sentryrca/schema/__init__.py`.
7. Every schema gets a test in `tests/schema/` with: a valid example, an
   invalid example per validation rule, and a round-trip JSON test.
8. When the schema changes, bump `prompt_version` if it affects LLM output
   shape. The version is part of the audit trail.
