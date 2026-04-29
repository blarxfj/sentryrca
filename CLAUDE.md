# SentryRCA — Claude Code Instructions

## Project context
Eval-driven, observable, multi-agent root cause analysis system for production
incidents. Full project pack in `docs/PROJECT_PACK.md`. Read it before any
architectural decision.

## Locked scope (do not expand without explicit approval)
- 2 specialist agents: `LogAnalyst`, `DeployInspector`. Supervisor via LangGraph.
- No fine-tuning, no GraphRAG, no time-series models in v1.
- ~70-incident eval set: 50 synthetic + 10–12 real-derived + 8–10 adversarial.
- Stack: LangGraph, LiteLLM, Claude Sonnet 4 + Haiku, bge-small-en-v1.5,
  pgvector + Postgres FTS, bge-reranker-base, FastAPI, Streamlit, Langfuse,
  promptfoo, Docker Compose, GitHub Actions.

## Non-negotiables
1. **Pydantic RCA schema is the contract.** Every agent run produces a validated
   `RCAOutput`. `unknowns` is required. Every `TimelineEntry` must reference a
   real `source_evidence_id` from retrieved evidence. Synthesis retries on
   validation failure (cap: 3 retries, log every failure to Langfuse).
2. **Citation faithfulness is deterministic, not LLM-judged.** Excerpts must
   appear verbatim in the input corpus. Implement `verify_excerpt_in_corpus()`
   and use it in eval.
3. **Every LLM call and tool call is traced via Langfuse.** No exceptions, even
   in scripts. Use the shared `@traced` decorator.
4. **Eval gates block CI.** Drops >3% in top-1 accuracy, <95% citation
   faithfulness, or p95 latency >15s fail the build.
5. **No commit bypasses pre-commit checks.** No `--no-verify`. No direct
   pushes to `main`. See git-workflow skill.

## Code conventions
- Python 3.12, `uv` for deps, `ruff` for lint+format, `mypy --strict` for types.
- Pydantic v2 for all data contracts. No untyped dicts crossing module boundaries.
- All config via `pydantic-settings` reading from `.env`. No hardcoded secrets,
  no hardcoded model names — route through LiteLLM config.
- Tests with `pytest`. Every public function in `sentryrca/` has at least a
  smoke test. Retrieval, schema validation, and citation-faithfulness checks
  have property-based tests where reasonable.
- Logging: `structlog` with JSON output. Never `print()` in library code.
- Async by default in API and agent layers. Sync is fine in scripts and eval.

## Branching strategy (trunk-based with short-lived branches)
- `main` is always green, always deployable. Protected branch.
- Feature work happens on short-lived branches off `main`. Target lifetime:
  under 2 days. If a branch lives longer, it's a sign the task wasn't sliced
  small enough.
- Branch naming: `<type>/<short-kebab-description>` where `<type>` is one of
  `feat` | `fix` | `chore` | `docs` | `eval` | `refactor` | `ci`.
  Examples: `feat/hybrid-retrieval`, `eval/adversarial-subset`,
  `ci/eval-gate-workflow`.
- Every branch ships via PR. No direct commits to `main`. Squash-merge only —
  the PR title becomes the commit on `main`, so write it like a commit message.
- Delete branches after merge.

## Commit conventions
- Conventional Commits format:
  `<type>(<scope>): <subject>` — e.g. `feat(retrieval): add RRF fusion`.
  Types: `feat`, `fix`, `chore`, `docs`, `eval`, `refactor`, `ci`, `test`.
- Subject in imperative mood, lowercase, no trailing period, ≤72 chars.
- Body (optional) explains *why*, not *what*. Reference the ADR if one exists.
- One logical change per commit. If you can't summarize it in 72 chars, split it.

## Pre-commit and pre-push gates
- `pre-commit` framework runs on every `git commit`:
  - `ruff format` (auto-fix)
  - `ruff check --fix`
  - `mypy --strict` on staged files
  - `pytest -q` on the unit-test subset (excludes eval and integration)
  - secret scan via `detect-secrets` or `gitleaks`
  - schema validation: `python -m sentryrca.schema.validate_examples`
- `pre-push` runs the full unit + integration test suite (still excludes the
  full eval — too slow). If it's slow, it's still mandatory.
- `--no-verify` is forbidden. If a hook is broken, fix the hook in its own PR.

## CI/CD pipeline (GitHub Actions)
Every PR triggers, in order, with later jobs depending on earlier ones passing:
1. **`lint`** — `ruff check`, `ruff format --check`, `mypy --strict`.
2. **`test`** — `pytest` with coverage. Fails if coverage drops below 80% on
   `sentryrca/schema/`, `sentryrca/retrieval/`, `sentryrca/eval/`. Other
   packages: 60% floor.
3. **`build`** — docker compose builds successfully; smoke-test the API
   container responds to `/health`.
4. **`eval-gate`** — runs a fast eval subset (10 incidents, deterministic
   seeds, mocked LLM where possible). Fails if top-1 accuracy drops >3% vs
   the baseline stored in `eval/baselines/main.json`, citation faithfulness
   <95%, or p95 latency >15s. Full 70-incident eval runs nightly on `main`.
5. **`security`** — `pip-audit` on lockfile, `gitleaks` scan, Trivy scan on
   the built image.

PR cannot merge until all five jobs pass and at least one approving review
(self-approval permitted on this solo project, but the review checklist in
`.github/pull_request_template.md` must be filled in).

`main` deploys to a staging environment (Hetzner CX22 or local) on every merge
via a `deploy-staging` workflow. Production deploys are tag-triggered:
`v*.*.*` tags push to prod with manual approval gate.

## Repository layout
```
sentryrca/
  agents/         # LangGraph supervisor + LogAnalyst + DeployInspector
  retrieval/      # hybrid search: dense + FTS + RRF + reranker
  schema/         # Pydantic models — the RCA contract lives here
  synthetic/      # incident generator, post-mortem parser, adversarial builder
  eval/           # promptfoo configs, judges, citation checks, cost-routing
  observability/  # Langfuse client, OTel setup, traced decorator
  api/            # FastAPI app
  ui/             # Streamlit demo
tests/
  unit/           # fast, no network, no DB
  integration/    # postgres + langfuse via docker compose
  eval/           # eval harness tests, not the eval cases themselves
docs/
  PROJECT_PACK.md           # the full v2 project pack
  ADR/                      # architecture decision records, one per major choice
.github/
  workflows/                # ci.yml, eval-nightly.yml, deploy-staging.yml, release.yml
  pull_request_template.md
.pre-commit-config.yaml
docker-compose.yml
pyproject.toml
Makefile
.env.example
```

## Workflow expectations
- Before starting work: pull `main`, branch off, install hooks with
  `pre-commit install && pre-commit install --hook-type pre-push`.
- Before writing code for a new module: read the relevant skill in
  `.claude/skills/`.
- When adding a dependency: justify it in the PR description. Default answer
  is no.
- When making a non-trivial design choice: write a short ADR in `docs/ADR/`.
  Format: context, decision, alternatives considered, consequences.
  10 lines is fine.
- Every PR must update tests. Every PR that touches the agent or schema must
  show eval results before/after in the PR description.
- Every PR must fill in the PR template checklist.

## Things to push back on
- Adding a third agent before week 3.
- Skipping Langfuse instrumentation "for now."
- LLM-judged citation checks (must be deterministic).
- Inflated metric claims. Numbers must trace to a reproducible eval run.
- Skipping or bypassing pre-commit / CI gates.
- Long-lived feature branches (>2 days).
- Any work that doesn't ladder to: working demo + eval harness + Langfuse
  traces + cost-routing chart by end of week 3.

## Make targets
- `make up` / `make down` — docker compose
- `make test` — pytest (unit + integration)
- `make test-unit` — fast unit tests only
- `make lint` — ruff + mypy
- `make hooks` — install pre-commit hooks
- `make eval` — full 70-incident benchmark
- `make eval-fast` — 10-incident subset used by the CI eval-gate
- `make eval-cost-routing` — Sonnet vs Haiku vs hybrid comparison
- `make ui` — Streamlit demo
- `make trace` — open Langfuse UI

## My context
Senior SRE pivoting to LLMOps. Deep on Docker/Postgres/Python/FastAPI/observability.
Intermediate on LangGraph/LiteLLM/Langfuse/eval tooling — explain AI-specific
patterns when they come up. 30-day runway, this is portfolio material, ship in 3 weeks.
