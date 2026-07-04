"""Eval harness — citation faithfulness, LLM judge, metrics aggregation."""

from sentryrca.eval.citation import check_citation_faithfulness, verify_excerpt_in_corpus
from sentryrca.eval.metrics import EvalCaseResult, EvalReport

__all__ = [
    "EvalCaseResult",
    "EvalReport",
    "check_citation_faithfulness",
    "verify_excerpt_in_corpus",
]
