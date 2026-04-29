.DEFAULT_GOAL := help
SHELL := /bin/bash
PYTHON := uv run python

# ─── Docker ──────────────────────────────────────────────────────────────────

.PHONY: up
up:  ## Start all services (postgres + langfuse stack)
	docker compose up -d

.PHONY: down
down:  ## Stop and remove containers (keeps volumes)
	docker compose down

.PHONY: down-volumes
down-volumes:  ## Stop containers AND delete all data volumes
	docker compose down -v

# ─── Dev environment ─────────────────────────────────────────────────────────

.PHONY: install
install:  ## Install all deps including dev group
	uv sync --group dev

.PHONY: hooks
hooks:  ## Install pre-commit hooks (run once per clone)
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push

# ─── Lint & type-check ───────────────────────────────────────────────────────

.PHONY: lint
lint:  ## Run ruff (check + format) and mypy --strict
	uv run ruff check sentryrca/ tests/
	uv run ruff format --check sentryrca/ tests/
	uv run mypy --strict sentryrca/

.PHONY: fmt
fmt:  ## Auto-format with ruff
	uv run ruff format sentryrca/ tests/
	uv run ruff check --fix sentryrca/ tests/

# ─── Tests ───────────────────────────────────────────────────────────────────

.PHONY: test
test:  ## Run unit + schema tests with coverage
	uv run pytest tests/unit/ tests/schema/ -v

.PHONY: test-unit
test-unit:  ## Fast unit tests only (no schema, no integration)
	uv run pytest tests/unit/ -q

.PHONY: test-all
test-all:  ## Full test suite including integration (requires docker compose up)
	uv run pytest -v

# ─── Eval ────────────────────────────────────────────────────────────────────

.PHONY: eval
eval:  ## Full 70-incident eval benchmark (week 3)
	@echo "eval harness not implemented yet — coming in week 3"; exit 0

.PHONY: eval-fast
eval-fast:  ## Fast 10-incident CI subset (week 3)
	@echo "eval-fast harness not implemented yet — coming in week 3"; exit 0

.PHONY: eval-cost-routing
eval-cost-routing:  ## Sonnet vs Haiku vs hybrid cost comparison (week 3)
	@echo "cost-routing eval not implemented yet — coming in week 3"; exit 0

# ─── App ─────────────────────────────────────────────────────────────────────

.PHONY: api
api:  ## Start FastAPI dev server
	uv run uvicorn sentryrca.api:app --reload --port 8000

.PHONY: ui
ui:  ## Start Streamlit demo UI
	uv run streamlit run sentryrca/ui/app.py

.PHONY: trace
trace:  ## Open Langfuse UI in browser
	open http://localhost:3000

# ─── Help ────────────────────────────────────────────────────────────────────

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
