"""Lazy singleton wrapper around bge-reranker-base."""

from typing import Any

from sentence_transformers import CrossEncoder

from sentryrca.config import settings

_model: CrossEncoder | None = None


def _get_model() -> CrossEncoder:
    global _model
    if _model is None:
        _model = CrossEncoder(settings.reranker_model)
    return _model


def rerank(query: str, texts: list[str]) -> list[float]:
    """Score (query, text) pairs. Higher score = more relevant."""
    model = _get_model()
    pairs: list[Any] = [(query, t) for t in texts]
    scores: list[float] = model.predict(pairs).tolist()
    return scores
