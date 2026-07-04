# SentryRCA

**Eval-driven, observable, multi-agent root cause analysis for production incidents.**

> "Senior SRE who built an AI agent that does what I used to do at 3am — with production-grade LLMOps observability, defensible evals, and SRE discipline applied to the agent itself."

---

## 1. Problem — RCA is the incident-response bottleneck

60–70% of incident time is diagnosis, not remediation. Existing tools (Datadog Watchdog, PagerDuty AIOps) detect anomalies but stop short of a causal narrative. SentryRCA closes that gap: paste an alert, get a structured, cited, machine-checkable RCA in under 90 seconds.

---

## 2. Demo

```bash
make up && make index-corpus && make ui
# open http://localhost:8501
```

Select any of the 69 indexed incidents. Press **Run RCA**. The agent produces:

- Ranked root-cause hypotheses with confidence scores
- A grounded incident timeline — every entry cites a real evidence item
- Verbatim log and deploy excerpts — no hallucinated quotes
- Recommended actions and rollback candidate
- Langfuse trace deep-link

---

## 3. Architecture

```
                [Alert / Streamlit UI / POST /rca]
                              │
                              ▼
                 [LangGraph Supervisor Graph]
                        /            \
                       ▼              ▼
        [LogAnalyst (Haiku)]   [DeployInspector (Haiku)]
               │                          │
               ▼                          ▼
   [Hybrid Retrieval]            [Deploy entry lookup]
   pgvector + FTS + RRF          (deterministic from
   + bge-reranker-base            incident deploy list)
               \                  /
                ▼                ▼
           [Synthesis (Sonnet 4.6)]
           - ranked hypotheses
           - grounded timeline (source_evidence_id validation)
           - full RCAOutput (Pydantic-validated, 3× retry on failure)
                       │
                       ▼
    [FastAPI /rca  ·  Streamlit UI  ·  Slack formatter]
    [Postgres audit table  ·  Langfuse traces]
```

---

## 4. Agent workflow

The LangGraph graph has three nodes and a conditional retry loop:

```
START → log_analyst → deploy_inspector → synthesize ──► END
                                              ▲   │ validation failure (≤3×)
                                              └───┘
```

**LogAnalyst** (Claude Haiku 4.5):
- Queries hybrid retrieval restricted to the current incident's chunks
- Returns 5–6 evidence items with verbatim excerpts from indexed logs

**DeployInspector** (Claude Haiku 4.5):
- Analyses `recent_deploys`, identifies suspicious SHAs
- Builds deploy evidence deterministically from deploy entry data — no LLM-generated text in excerpts

**Synthesis** (Claude Sonnet 4.6):
- Combines both findings into a full `RCAOutput`
- Evidence excerpts are enforced post-synthesis from pre-built verbatim sources
- Retries on Pydantic validation failure, injecting the error into the next prompt

---

## 5. Retrieval design

Stack: **bge-small-en-v1.5** (dense) + **Postgres FTS** → **RRF fusion** → **bge-reranker-base** (cross-encoder rerank).

```
query
  ├── embed → pgvector cosine HNSW search (top-20)
  └── plainto_tsquery → Postgres FTS rank (top-20)
          ↓
     RRF fusion  (k=60, standard formula)
          ↓
   bge-reranker-base cross-encoder (top-5)
```

All retrieval is scoped to the current incident (`incident_id` filter) to guarantee citation faithfulness. Corpus: **69 incidents × ~10 chunks = 736 chunks**.

---

## 6. The strict RCA schema

Every run produces a validated `RCAOutput`. Key anti-hallucination guardrails:

```python
class TimelineEntry(BaseModel):
    timestamp: str
    event: str
    source_evidence_id: str  # must match an EvidenceItem.id — rejects orphan entries

class RCAOutput(BaseModel):
    evidence: list[EvidenceItem]   # verbatim excerpts enforced; LLM paraphrases rejected
    timeline: list[TimelineEntry]  # grounded to evidence — no invented timestamps
    unknowns: list[str]            # required — forces the agent to declare open questions
    confidence: float              # 0–1
    # LLMOps metadata baked into every output:
    model_version: str
    total_tokens: int
    p95_step_latency_ms: int
    ...
```

**`unknowns` is required.** Real RCAs always have open questions. Forcing the agent to declare what it doesn't know is a strong anti-hallucination signal — and an interview talking point.

---

## 7. Evaluation harness

Three subset reports (synthetic / real-derived / adversarial):

| Subset | n | Top-1 acc | Citation faith |
|---|---|---|---|
| Synthetic | 5 | 60% | 100% |
| Real-derived | 3 | 100% | 100% |
| Adversarial | 2 | 50% | 100% |
| **Overall** | **10** | **70%** | **100%** |

*(10-incident fast subset used by CI gate; full 69-incident benchmark: `make eval`.)*

**Citation faithfulness is deterministic**, not LLM-judged. Every `EvidenceItem.excerpt` is checked as a verbatim substring of the incident corpus (`verify_excerpt_in_corpus()`). CI fails if faithfulness drops below 95%.

**LLM judge** (Claude Haiku): scores each RCA 0/1/2 against `ground_truth_root_cause`. Top-1 accuracy = fraction with score ≥ 2. Top-1 may not drop more than 3% vs the stored baseline.

---

## 8. LLMOps observability

Every LLM call, tool call, and synthesis retry is traced in **Langfuse** (self-hosted via Docker Compose). Open `http://localhost:3001` after `make trace`.

Every completed run is persisted to a Postgres `rca_runs` audit table and carries baked-in LLMOps metadata:

```python
model_version, prompt_version, agent_step_count,
total_tokens, total_cost_usd, p95_step_latency_ms
```

---

## 9. Cost-routing comparison

Run `make eval-cost-routing` to reproduce:

| Configuration | Top-1 | Faith | Tokens | $/incident (est.) |
|---|---|---|---|---|
| Hybrid (Sonnet reason + Haiku fast) | 70% | 100% | ~13 400 | ~$0.08 |
| Sonnet-only | — | — | — | ~$0.20 |
| Haiku-only | — | — | — | ~$0.01 |

---

## 10. Design tradeoffs

| What I deliberately did NOT build | Why |
|---|---|
| Fine-tuning | Prompt engineering + retrieval + eval gates achieves defensible accuracy at zero dataset cost. Add after hitting a prompt ceiling. |
| GraphRAG | Hybrid dense + BM25 + RRF + reranker is the right first bet. GraphRAG adds entity-linking complexity with uncertain gains on a sub-100-incident corpus. |
| Time-series anomaly models | The LLM + log retrieval stack already surfaces anomalies from log text. Chronos-Bolt adds infra cost for marginal gain at this corpus size. |
| Third specialist agent | Two specialists cover the two dominant incident classes. Adding HistoryRetriever before validating the two-agent baseline is premature. |
| Real Loki / Datadog connector | Synthetic + real-derived corpus is sufficient for a portfolio eval harness. A live connector is a one-week add-on once the agent architecture is validated. |

---

## 11. How to run locally

**Prerequisites:** Docker, Python 3.12, `uv`

```bash
# 1. Clone and install
git clone <repo> && cd sentryrca
cp .env.example .env     # fill in ANTHROPIC_API_KEY + required secrets
uv sync --group dev
pre-commit install && pre-commit install --hook-type pre-push

# 2. Start infrastructure
make up

# 3. Index the incident corpus (~first run downloads embedding + reranker models)
make index-corpus

# 4. Run the eval suite
make eval-fast            # 10-incident CI subset with gate check
make eval                 # full 69-incident benchmark

# 5. Launch the demo UI
make ui                   # http://localhost:8501

# 6. Open Langfuse traces
make trace                # http://localhost:3001
```

**API:**
```bash
make api                  # FastAPI on http://localhost:8000/docs
curl -sf http://localhost:8000/health
```

---

## 12. What I would add in production

- **Real Loki / Datadog connector** — replace synthetic log_window with a live query window
- **HistoryRetriever specialist** — third agent querying historical incident patterns
- **Human feedback loop** — Langfuse annotation queue where on-call engineers score RCA quality; feeds judge calibration
- **Streaming synthesis** — SSE endpoint so the UI shows the RCA building in real time
- **Cost budget guardrails** — LiteLLM spend limits per incident; auto-downgrade to Haiku on budget exceeded

---

## Corpus

| Subset | Count | Description |
|---|---|---|
| Synthetic | 50 | Generated via Claude, OTel demo app service names, real OTel repo SHAs |
| Real-derived | 10 | Parsed from `danluu/post-mortems` into the incident schema |
| Adversarial | 9 | Misleading-but-not-causal deploys; real cause is upstream (DNS, cert expiry, etc.) |

---

## Make targets

| Target | Description |
|---|---|
| `make up` | Start all services |
| `make index-corpus` | Embed + index all incidents into pgvector |
| `make eval-fast` | 10-incident CI subset + gate check |
| `make eval` | Full 69-incident benchmark |
| `make eval-cost-routing` | Sonnet vs Haiku vs hybrid comparison |
| `make eval-update-baseline` | Overwrite baseline after a confirmed improvement |
| `make ui` | Streamlit demo UI (`http://localhost:8501`) |
| `make api` | FastAPI dev server (`http://localhost:8000`) |
| `make trace` | Open Langfuse UI (`http://localhost:3001`) |
| `make test` | Unit + schema tests with coverage |
| `make lint` | ruff + mypy --strict |

---

## Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph |
| LLM gateway | LiteLLM |
| Models | Claude Sonnet 4.6 (synthesis) · Claude Haiku 4.5 (specialists + judge) |
| Embeddings | bge-small-en-v1.5 |
| Reranker | bge-reranker-base |
| Vector + FTS | Postgres 16 + pgvector (HNSW) |
| API | FastAPI |
| UI | Streamlit |
| Observability | Langfuse (self-hosted) |
| Eval | Custom harness + LLM-as-judge |
| CI | GitHub Actions (lint → test → build → eval-gate → security) |
| Infra | Docker Compose |
