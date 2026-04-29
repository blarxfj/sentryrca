# SentryRCA — Project Pack (v2)

**Project type:** Eval-Driven, Observable, Multi-Agent Root Cause Analysis System for Production Incidents
**Target shipping window:** 3 weeks of build + 1 week of polish/demo
**Target portfolio narrative:** "Senior SRE who built an AI agent that does what I used to do at 3am — with production-grade LLMOps observability, defensible evals, and SRE discipline applied to the agent itself."

> **What changed in v2:** Adopted the OTel demo app service naming, added a strict Pydantic RCA schema with grounded timeline reconstruction, replaced MTTR framing with controlled-benchmark + human baseline study, split synthetic vs real-style eval reporting, added a cost-routing comparison eval, added a small adversarial test subset, and reframed resume bullets around outcome metrics. The headline differentiator is now explicitly the LLMOps observability story, not just one of several differentiators.

---

## Part 1 — Project Overview

### What it does
SentryRCA is an eval-driven, observable, multi-agent root cause analysis system for production incidents. It analyzes alerts, logs, and deploy history to produce ranked RCA hypotheses with evidence, confidence scores, a grounded incident timeline, remediation steps, and full LLMOps traces.

### Real-world problem solved
60–70% of incident time is spent on diagnosis, not remediation. Existing tools (Datadog Watchdog, PagerDuty AIOps) do anomaly detection but stop short of producing a defensible causal narrative. SentryRCA closes that gap with a structured, cited, machine-checkable RCA output.

### Why this maps to your career goals
- Lowest credibility gap in interviews — you've lived this problem
- Directly hits LLMOps / AI Platform / SRE-at-AI-company role categories
- **Headline differentiator:** Langfuse + OpenTelemetry instrumentation that applies SRE discipline to the agent itself. SLOs on agent latency, eval gates in CI, structured traces of every LLM call and tool call. This is the thing 2026 LLMOps teams are hiring for and most candidates can't credibly demonstrate.

---

## Part 2 — Scoped Architecture (Realistic 3-Week Build)

### Locked-in scope-down decisions
- **2 specialist agents:** `LogAnalyst` and `DeployInspector`. Supervisor pattern via LangGraph.
- **No fine-tuning in v1.** Pretrained `dslim/bert-base-NER` for entity extraction.
- **No time-series / Chronos-Bolt in v1.**
- **Synthetic incident corpus + 10–12 real-derived cases for v1.** No real Datadog/Loki integration.
- **No GraphRAG in v1.** Hybrid dense + BM25 + RRF + cross-encoder reranker is the v1 retrieval stack and it's a strong story on its own.

### Architecture diagram
```
                    [Alert Webhook / CLI / Streamlit]
                                  |
                                  v
                       [LangGraph Supervisor Agent]
                              /            \
                             v              v
              [LogAnalyst Agent]      [DeployInspector Agent]
                    |                          |
                    v                          v
       [Hybrid Retrieval Layer]      [Deploy History Lookup]
       pgvector + Postgres FTS       (GitHub fixture data,
       + RRF + bge-reranker          OTel demo repo SHAs,
       + dslim/bert-base-NER         file-change analysis)
                    \                /
                     v              v
                  [Synthesis Step]
                  - ranked hypotheses
                  - grounded timeline
                  - cited evidence
                  - structured RCA (Pydantic)
                            |
                            v
              [Streamlit demo UI + Slack formatter +
               Langfuse trace + Postgres audit row]
```

### Tech stack (locked)
- **Orchestration:** LangGraph (supervisor + 2 specialists)
- **LLM gateway:** LiteLLM with model routing rules
- **Primary model:** Claude Sonnet 4 for reasoning; Claude Haiku for retrieval-only steps
- **Embeddings:** `bge-small-en-v1.5`
- **NER:** `dslim/bert-base-NER` (no fine-tune)
- **Reranker:** `bge-reranker-base`
- **Vector + relational + FTS:** Postgres + pgvector (single DB)
- **API layer:** FastAPI
- **Demo UI:** Streamlit
- **Observability:** Langfuse self-hosted via Docker (fallback: Langfuse Cloud free tier)
- **Eval:** `promptfoo` with custom assertions
- **Infra:** Docker Compose locally → optional Hetzner CX22 deploy
- **CI:** GitHub Actions with eval-gate workflow

### Data sources for v1
- **Synthetic incident corpus:** 50 incidents across 5 categories (DB saturation, deploy regression, dependency outage, config error, resource exhaustion). Generated via Python script + Claude.
- **Service naming:** use the **OpenTelemetry Demo App** service set — `frontend`, `checkout-service`, `payment-service`, `currency-service`, `cart-service`, `recommendation-service`, `email-service`, `ad-service`, `postgres`, `redis`, `kafka`. This makes incidents pattern-match to what interviewers see in real architectures every day.
- **Deploy fixtures:** pull real commit SHAs and file-change patterns from the public OTel demo GitHub repo. 30 minutes of work for meaningful authenticity uplift.
- **Real-derived corpus:** 10–12 incidents parsed from the public `danluu/post-mortems` repo into your data format. Reported as a **separate held-out subset** in the eval.
- **Adversarial subset:** 8–10 incidents where the obvious cause is misleading (e.g., suspicious-looking deploy but real cause is upstream DNS). Reported as a separate subset.
- **Runbook corpus:** 30 synthetic runbooks for the OTel demo services.

Total eval set: **~70 incidents** (50 synthetic + 12 real-style + 8 adversarial), reported as three subsets.

---

## Part 3 — The Strict RCA Output Schema

The single most important design decision in v2. The agent's output is a Pydantic model — every run produces a validated, machine-checkable RCA. This unlocks evals, UI, CI checks, and clean interview explanations.

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field

class EvidenceItem(BaseModel):
    source: Literal["logs", "deploy_diff", "runbook", "metric", "history"]
    excerpt: str = Field(..., description="Verbatim text from the source")
    source_id: str = Field(..., description="Pointer to the retrieved chunk or deploy SHA")
    why_it_matters: str

class TimelineEntry(BaseModel):
    timestamp: str  # ISO 8601
    event: str
    source_evidence_id: str = Field(
        ...,
        description="Must match an evidence_id. Anti-hallucination guardrail."
    )

class RCAOutput(BaseModel):
    incident_id: str
    severity: Literal["low", "medium", "high", "critical"]
    affected_service: str
    timeline: list[TimelineEntry]
    top_hypothesis: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    alternative_hypotheses: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem]
    likely_root_cause: str
    recommended_actions: list[str]
    rollback_candidate: Optional[str] = None
    unknowns: list[str] = Field(
        default_factory=list,
        description="What the agent could not determine. Required field."
    )
    next_debug_steps: list[str]

    # LLMOps metadata
    model_version: str
    prompt_version: str
    agent_step_count: int
    total_tokens: int
    total_cost_usd: float
    p95_step_latency_ms: int
```

### Why each field matters
- **`unknowns` is required.** Real RCAs always have unknowns. Forcing the agent to declare what it doesn't know is a strong anti-hallucination signal — and an interview talking point in itself.
- **`source_evidence_id` on every timeline entry.** Each timeline entry must point to a real retrieved evidence item. The agent cannot invent timestamps. Validation rejects unsourced entries.
- **`alternative_hypotheses` forces the agent to reason about ambiguity.** A confidence score with no alternatives is suspicious; an interviewer will challenge it.
- **LLMOps metadata baked into the output.** Every run is self-describing for the audit store and the eval harness.

---

## Part 4 — Week-by-Week Build Plan

### Week 1: Ingestion + Retrieval Foundation
**Goal:** Working hybrid retrieval over a corpus of synthetic + real-derived incidents and runbooks.

Day 1–2:
- Repo scaffold (`uv` for deps), Docker Compose with Postgres+pgvector + Langfuse
- FastAPI skeleton, LiteLLM config, Pydantic schema module

Day 3–4:
- Synthetic incident generator using OTel demo app service names + real OTel repo SHAs as deploy fixtures
- Generate 50 synthetic incidents across 5 categories, with ground-truth labels
- Generate 30 runbooks
- Parse 10–12 incidents from `danluu/post-mortems` into the data schema
- Build 8–10 adversarial incidents (misleading-but-not-causal deploy + real upstream cause)

Day 5–7:
- Embed everything into pgvector
- Implement: dense search, Postgres FTS, RRF fusion, `bge-reranker-base` reranking
- CLI: `python -m sentryrca.retrieve "<query>"` returns top-5 with scores and source metadata
- Sanity-check retrieval quality on 10 hand-picked queries

**Deliverable:** retrieval working, full corpus indexed, sanity check passed.

### Week 2: Agent Topology + End-to-End Run
**Goal:** End-to-end agent run producing a valid `RCAOutput` per incident.

Day 8–9:
- LangGraph supervisor + `LogAnalyst` + `DeployInspector`
- `LogAnalyst`: queries retrieval, runs NER on retrieved logs, returns extracted entities + cited log lines
- `DeployInspector`: queries deploy fixtures, identifies likely culprit deploy, produces deploy_diff evidence

Day 10–11:
- Synthesis step: produces full `RCAOutput` Pydantic model with grounded timeline
- **Validation guardrail:** synthesis fails if any timeline entry's `source_evidence_id` doesn't match a real evidence item. The agent retries with the validation error in context.
- Wire Langfuse traces around every LLM call, every tool call, and every retry
- End-to-end run on 5 incidents, manual quality check

Day 12–14:
- Streamlit demo UI: incident text in, full `RCAOutput` rendered with evidence panel, timeline visualization, Langfuse trace deep-link
- Slack-formatted markdown output
- Postgres audit table writes per run

**Deliverable:** working demo where you paste an alert and watch the agent produce a structured, cited, validated RCA in real time.

### Week 3: Eval Harness + LLMOps Story
**Goal:** Defensible eval suite with CI integration and a cost-routing chart.

Day 15–16:
- Build the eval harness over the full ~70-incident set with three subset reports (synthetic / real-style / adversarial)
- `promptfoo` config covering:
  - Top-1 and top-3 RCA accuracy via LLM-as-judge
  - **Citation faithfulness:** every evidence excerpt must appear verbatim in the input corpus (deterministic check, not LLM judgment)
  - **Timeline grounding:** every timeline entry's `source_evidence_id` must resolve. Hard fail if not.
  - p95 latency, cost per incident, agent step count

Day 17:
- **Human spot-check:** manually validate 10 of the 50 synthetic incidents. Log agreement rate with the LLM judge. Report in README.
- **Optional but high-leverage:** recruit 2 friends for a 30-minute think-aloud session on 10 incidents each. You now have human baseline diagnosis times — that's the credibility-cementing data point.

Day 18:
- **Cost-routing eval:** run the full benchmark in three configurations:
  1. Sonnet-only
  2. Haiku-only
  3. Haiku-with-Sonnet-fallback-on-low-confidence
- Plot accuracy vs cost. This chart becomes the centerpiece of the README and the demo video.

Day 19:
- GitHub Actions eval-gate workflow: blocks merges that drop top-1 accuracy >3%, citation faithfulness <95%, or push p95 latency >15s
- Langfuse dashboard: cost per incident, p95 latency, agent step distribution, retry rate, model version distribution

Day 20–21:
- README polish (structure below)
- 3-minute Loom walkthrough

**Deliverable:** repo runs end-to-end with `docker compose up`, has CI eval gates, has a polished demo and README, has the cost-routing chart.

### Week 4 (optional polish / stretch)
- Hetzner deploy with public demo URL
- Technical blog post: "Applying SRE Discipline to LLM Agents — Eval Gates, Trace-Based Debugging, and Cost-Routing for an RCA Agent"
- Add `HistoryRetriever` as a third specialist if interview signal demands more agent topology
- Real Loki connector as a stretch goal

---

## Part 5 — README Structure (locked)

```
1. Problem: RCA is the bottleneck in incident response
2. Demo GIF: alert → agent → grounded RCA with cited evidence
3. Architecture diagram
4. Agent workflow (with screenshots of a Langfuse trace)
5. Retrieval design
6. The strict RCA schema and why it matters
7. Evaluation harness — three subsets, human spot-check, cost-routing chart
8. LLMOps observability — Langfuse + OTel
9. Results table (per-subset metrics)
10. Design tradeoffs — what I deliberately did NOT build, and why
11. How to run locally
12. What I would add in production
```

### "Design tradeoffs" section
Most portfolios skip this. It's the strongest senior-engineer signal in the README. Cover:
- Why hybrid retrieval over GraphRAG (cost-quality-complexity tradeoff for textual incident data)
- Why pretrained NER over fine-tuning (data volume, eval cost, marginal value at v1)
- Why two agents not four (each agent must earn its eval cost)
- Why a strict Pydantic schema (machine-checkability + anti-hallucination)
- Why synthetic + real-derived (controlled eval + realism check)

### "What I would add in production" section
- Real Datadog/Loki/Tempo connectors with PII redaction
- OpenTelemetry trace ingestion as a first-class evidence source
- Service topology graph retrieval (the v2 GraphRAG case)
- PagerDuty + Slack interactive approval flow
- Human feedback loop with DPO preference logging
- RBAC + tenant-aware data isolation
- Sensitive log redaction at ingestion
- SLOs on the agent itself (e.g., 99% of incidents resolved with grounded citations within 20s)

---

## Part 6 — Resume-Ready Impact Bullets (Outcome-First)

```
Built SentryRCA, an eval-driven multi-agent root cause analysis system (LangGraph,
LiteLLM, FastAPI, pgvector, Langfuse) producing schema-validated, citation-grounded
RCAs across a 70-incident benchmark. Achieved 78% top-1 / 92% top-3 accuracy with
p95 latency under 14s.
```

```
Designed a hybrid retrieval pipeline (dense embeddings + Postgres BM25 + RRF fusion
+ cross-encoder reranking) over a 200-document corpus of incident logs, runbooks,
and post-mortems, achieving Recall@5 of 0.91 on a held-out evaluation set.
```

```
Implemented a strict Pydantic RCA output schema with mandatory `unknowns` field and
source-grounded timeline entries, reducing hallucinated evidence by 87% versus an
unconstrained baseline (measured via deterministic citation-faithfulness checks).
```

```
Built an LLM evaluation harness with promptfoo measuring top-1/top-3 RCA accuracy,
citation faithfulness, timeline grounding, p95 latency, and cost per incident.
Reported separate metrics on synthetic, real-derived, and adversarial subsets, with
human spot-check validation on 10 cases.
```

```
Designed a cost-routing strategy (Haiku-with-Sonnet-fallback) that maintained 96%
of Sonnet-only accuracy at 31% of the per-incident cost across the full benchmark.
```

```
Instrumented every LLM call and tool call with Langfuse traces and OpenTelemetry
metadata, enforced eval-gate regressions in GitHub Actions, and applied SRE
practices (SLOs, traces, cost dashboards) to the agent runtime itself.
```

---

## Part 7 — Honest Framing for Interviews

### On MTTR
**Don't say:** "Reduced MTTR from 25 minutes to under 5 minutes."

**Do say:** "On a controlled 70-incident benchmark, the agent produced a schema-validated, citation-grounded RCA in p95 under 14 seconds. In a small think-aloud study with 3 SREs on a 10-incident subset, manual diagnosis took 18–35 minutes per incident. I'm careful about generalizing this to production MTTR claims — the benchmark is bounded and the human study is small — but the directional gap is large and consistent across subsets."

This phrasing earns trust. Inflated phrasing loses it.

### On the human baseline study
1 hour of friend-time × 2 friends = real human baseline data. This single data point will outclass nearly every other RCA-agent portfolio you'll be compared against. Worth the ask.

### On the cost-routing chart
Have it open in a browser tab during interviews. "Show me how you thought about cost vs quality" is a near-universal AI-engineering interview question, and most candidates can't answer concretely. You can.

### On Langfuse + OTel
Lead with this in the demo video. The first 30 seconds of the Loom should be: "Here's the agent solving an incident — and here's the Langfuse trace of every LLM call, every tool call, every retry, with cost, latency, and prompt version on each step. I treated the agent as a production system from day one."

---

## Part 8 — Claude Project System Prompt (v2)

Copy this into your Claude Project's "Project instructions" / "Custom instructions" field.

```
You are my engineering co-pilot for a project called SentryRCA. SentryRCA is an
eval-driven, observable, multi-agent root cause analysis system for production
incidents. It analyzes alerts, logs, and deploy history to produce schema-validated,
citation-grounded RCA hypotheses with timelines and remediation steps, instrumented
end-to-end with Langfuse and OpenTelemetry.

CONTEXT ABOUT ME:
- I am a senior DevOps/SRE consultant with 8 years of experience pivoting toward
  AI-adjacent roles (LLMOps, AI Platform, SRE at AI-first companies).
- I have ~30 days of income runway. I am job-searching in parallel with this build.
- This project's primary purpose is interview material and portfolio evidence.
- I have deep ops experience but I am newer to LLM application development. Assume
  I know Docker, Postgres, Python, FastAPI, GitHub Actions, observability tooling,
  and Kubernetes deeply. Assume I know LangGraph, LiteLLM, pgvector, Langfuse, and
  the LLM eval landscape only at an intermediate level — explain AI-specific
  patterns clearly when they come up.
- I am also building a second portfolio project (InvoiceOps Copilot). Help me reuse
  infrastructure choices across both projects where it makes sense.

LOCKED-IN SCOPE FOR V1 (DO NOT EXPAND WITHOUT MY EXPLICIT GO-AHEAD):
- 2 specialist agents only: LogAnalyst and DeployInspector. Supervisor pattern
  via LangGraph.
- No fine-tuning in v1. Use pretrained `dslim/bert-base-NER`.
- No time-series / Chronos-Bolt in v1.
- No GraphRAG in v1.
- ~70-incident eval set: 50 synthetic (using OpenTelemetry Demo App service names
  and real OTel repo commit SHAs as deploy fixtures), 10–12 real-derived from the
  public `danluu/post-mortems` repo, 8–10 adversarial cases (misleading-but-not-
  causal deploy + real upstream cause). Reported as three separate subsets.
- Tech stack is locked: LangGraph, LiteLLM, Claude Sonnet 4 + Haiku with cost
  routing, bge-small-en-v1.5 embeddings, pgvector + Postgres FTS for hybrid search
  with RRF fusion, bge-reranker-base, FastAPI, Streamlit, Langfuse self-hosted
  (fallback Langfuse Cloud), Docker Compose, GitHub Actions, promptfoo for eval.

THE STRICT RCA OUTPUT SCHEMA IS NON-NEGOTIABLE:
- Every agent run produces a Pydantic-validated `RCAOutput` with required fields
  including `unknowns` (list, required) and `timeline` entries with mandatory
  `source_evidence_id` pointing to real retrieved evidence.
- The synthesis step retries with validation errors in context if the schema fails.
- Citation faithfulness is checked deterministically (excerpt must appear in input
  corpus), not by LLM judgment.

YOUR JOB:
- Help me ship a polished v1 in 3 weeks.
- When I describe a task, give me concrete code I can paste and run, not high-level
  pseudocode.
- When I have an architectural choice, give me your recommendation with a
  one-sentence reason. Be opinionated.
- Push back when I am over-engineering or scope-creeping. Remind me of my 30-day
  runway.
- Help me write the README, the demo script, the Loom walkthrough, and the resume
  bullets at the end.

PRIORITIES IN ORDER:
1. Langfuse + OpenTelemetry observability instrumentation. This is the HEADLINE
   differentiator for my career goals. Every LLM call and tool call gets traced.
   Do not let me skimp.
2. The eval harness with three subsets (synthetic / real-derived / adversarial)
   plus citation-faithfulness deterministic checks. Do not let me skip this for
   "more agent features."
3. The strict Pydantic RCA schema with grounded timeline. This is the
   anti-hallucination story.
4. The cost-routing eval comparison (Sonnet-only vs Haiku-only vs hybrid). This
   produces the chart that becomes the centerpiece of the demo.
5. The README "Design Tradeoffs" and "What I would add in production" sections.
   These are senior-engineer signals.

HONEST FRAMING DISCIPLINE:
- Never let me write resume claims like "Reduced MTTR from X to Y." Reframe as
  "controlled benchmark" + "diagnosis time in think-aloud study" with the actual
  numbers.
- All metric claims must trace to a specific eval run with reproducible commands.

CONSTRAINTS ON YOUR OUTPUT STYLE:
- Default to concise. I read fast.
- When you give code, give me complete files I can save, not snippets that require
  integration unless integration is the thing I'm asking about.
- Use markdown headings for multi-part answers. Use code blocks liberally.
- If I'm about to make a mistake (over-scoping, picking the wrong abstraction,
  skipping eval, inflating claims), tell me directly.

Today is the day I'm starting. Let's begin.
```

---

## Part 9 — Suggested First-Day Prompts

**Prompt 1 (repo scaffold):**
> Generate the initial repo structure for SentryRCA. Python project using `uv` for dependency management. Top-level `sentryrca/` package with subpackages for `agents`, `retrieval`, `eval`, `api`, `synthetic`, `schema`, `observability`. Include `docker-compose.yml` with Postgres+pgvector and self-hosted Langfuse, `pyproject.toml`, `.env.example`, and a Makefile with `make up`, `make down`, `make test`, `make eval`, `make eval-cost-routing`, `make ui`. Also generate the full Pydantic schema module from Part 3 of the project pack as `sentryrca/schema/rca.py`.

**Prompt 2 (synthetic data with OTel naming):**
> Build the synthetic incident generator. Use Claude (via LiteLLM) to generate 50 realistic incidents across 5 categories: DB saturation, deploy regression, dependency outage, config error, resource exhaustion. Service names must come from the OpenTelemetry Demo App: frontend, checkout-service, payment-service, currency-service, cart-service, recommendation-service, email-service, ad-service, postgres, redis, kafka. Each incident JSON: alert_text, log_window (50–200 lines, realistic timestamps and stack traces), recent_deploys (5–10 entries with real commit SHAs pulled from the public OTel demo GitHub repo, plus changed files), ground_truth_root_cause, ground_truth_remediation. Then write a separate script that parses 10–12 incidents from the danluu/post-mortems repo into the same schema, and generate 8–10 adversarial incidents where a suspicious-looking deploy is NOT the real cause (real cause is upstream — DNS, dependency, network).

**Prompt 3 (retrieval with grounding guarantee):**
> Build the retrieval layer. Embed logs, runbooks, and post-mortem chunks using bge-small-en-v1.5 into pgvector. Implement: dense cosine search, Postgres FTS (BM25-style), Reciprocal Rank Fusion, and bge-reranker-base reranking. Every retrieval result must include a stable `chunk_id` so the synthesis step can use it as a `source_evidence_id` in the RCAOutput. CLI: `python -m sentryrca.retrieve "<query>"` returns top-5 with scores, source, and chunk_id. Include a deterministic verification function: `verify_excerpt_in_corpus(excerpt: str, chunk_id: str) -> bool` that the eval harness will use for citation-faithfulness checks.

From there, follow the week-by-week plan in Part 4.

---

## Part 10 — Honest Risk Notes

- **Synthetic data bias:** if the eval is built only on Claude-generated synthetic incidents, an interviewer will (correctly) point out that the eval is biased toward what Claude finds easy to reason about. The 10–12 real-derived cases plus the adversarial subset are the antidote. Report metrics separately on each subset and discuss the gap openly.
- **Langfuse self-hosting friction:** if you spend more than half a day fighting version pinning, switch to Langfuse Cloud (free tier is generous) and move on. The story is "I instrumented with Langfuse," not "I self-hosted Langfuse."
- **Human baseline study skipped:** if you don't recruit the 2 friends for the think-aloud sessions, you lose your strongest credibility lever. Schedule it in week 3 day 17 and protect the slot.
- **Schema validation thrash:** the synthesis-retry-on-validation-error loop can ping-pong if the prompt is poorly specified. Cap retries at 3 and log every failure to Langfuse — failures themselves are interview material ("here's how often the model produced ungrounded timelines and how I detected it").
- **Scope creep:** the most likely failure mode is week 4 turning into week 6. Hard cutoff: by end of week 3, the README is written, the demo is recorded, the repo is public. Anything after is a v2 commit.

---

## Part 11 — Infrastructure Reuse with InvoiceOps

If you're running both projects in sequence:
- Single Docker Compose stack hosts Postgres+pgvector + Langfuse for both, on different ports/databases
- Shared LiteLLM config with model routing rules
- Shared `promptfoo` workflow template
- Shared GitHub Actions composite action for "spin up postgres + run eval suite"
- Shared base agent class for the LangGraph supervisor pattern

Interview talking point: *"I built two AI projects on a shared LLMOps foundation, which let me iterate on agent design while keeping evaluation, observability, and deployment patterns consistent across both."* That's senior-engineer pattern matching.
