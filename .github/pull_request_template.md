## What changed and why
<!-- 2–4 sentences. Explain the change and the motivation. -->

## ADR link
<!-- Link to docs/ADR/ if a non-trivial design choice was made. Otherwise "N/A". -->

## Test plan
<!-- What you ran locally. What CI will run automatically. -->
- [ ] `make lint` passes locally
- [ ] `make test` passes locally
- [ ] New tests added for changed code

## Eval impact
<!-- Required for PRs touching agents/, retrieval/, schema/, or prompts. -->
<!-- Paste before/after metrics from `make eval-fast` or `make eval`. -->
<!-- "N/A — no agent or schema changes" is a valid answer. -->

| Metric | Before | After |
|--------|--------|-------|
| Top-1 accuracy | — | — |
| Citation faithfulness | — | — |
| p95 latency (ms) | — | — |

## Observability impact
<!-- Did you add new Langfuse spans, change tags, or alter the audit-table schema? -->
<!-- If yes, link the Langfuse trace. Otherwise "N/A". -->

## Rollback plan
<!-- One sentence. "Revert the squash commit" is valid for most PRs. -->
<!-- Deploy migrations need an explicit rollback step. -->

---

<!-- CI gates that must pass before merge:
     lint → test → build → eval-gate → security
     All five must be green. No bypasses. -->
