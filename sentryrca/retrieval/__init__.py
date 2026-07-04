"""Hybrid retrieval: dense (pgvector) + FTS (Postgres) + RRF + cross-encoder rerank."""

from sentryrca.retrieval.search import RetrievedChunk, retrieve

__all__ = ["RetrievedChunk", "retrieve"]
