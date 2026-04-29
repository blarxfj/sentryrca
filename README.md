# SentryRCA

Eval-driven, observable, multi-agent root cause analysis system for production incidents.

**Status: Week 1 — scaffolding**

---

## Make targets

| Target | Description |
|--------|-------------|
| `make up` | Start all services (postgres + Langfuse stack) |
| `make down` | Stop containers (keeps volumes) |
| `make install` | Install all deps including dev group |
| `make hooks` | Install pre-commit hooks (run once per clone) |
| `make lint` | ruff check + format check + mypy --strict |
| `make fmt` | Auto-format with ruff |
| `make test` | Unit + schema tests with coverage |
| `make test-unit` | Fast unit tests only |
| `make test-all` | Full suite including integration |
| `make eval` | Full 70-incident benchmark (week 3) |
| `make eval-fast` | Fast 10-incident CI subset (week 3) |
| `make eval-cost-routing` | Sonnet vs Haiku vs hybrid comparison (week 3) |
| `make api` | FastAPI dev server on :8000 |
| `make ui` | Streamlit demo UI |
| `make trace` | Open Langfuse UI at http://localhost:3000 |
