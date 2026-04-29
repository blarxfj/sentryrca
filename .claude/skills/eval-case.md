# Skill: Adding or modifying an eval case

1. Eval cases live in `sentryrca/eval/cases/` as JSON files, one per incident,
   with a `subset` field: `synthetic` | `real_derived` | `adversarial`.
2. Schema for an eval case is `EvalCase` in `sentryrca/schema/eval.py`. It
   includes the incident input, ground-truth root cause, ground-truth
   remediation, and the expected `affected_service`.
3. Promptfoo config in `sentryrca/eval/promptfoo.yaml` references cases by
   subset. Run all three subsets in every full eval; report metrics
   per-subset, never aggregated only.
4. Assertions per case:
   - top-1 root cause match (LLM-judge with rubric in `eval/judges/root_cause.md`)
   - top-3 alternative-hypothesis match
   - citation faithfulness (deterministic, calls `verify_excerpt_in_corpus`)
   - timeline grounding (deterministic, every `source_evidence_id` resolves)
   - p95 latency < 15s, cost per incident logged
5. When you add a case, also add it to the human spot-check tracker in
   `docs/eval/human_spotcheck.md` if it's one of the 10 manually validated cases.
6. Never modify a case to make a failing eval pass. If the case is wrong,
   document why and version the change in git.
