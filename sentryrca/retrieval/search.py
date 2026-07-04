"""Main retrieve() function — dense + FTS → RRF → rerank pipeline."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sentryrca.observability import traced
from sentryrca.retrieval import embedder, reranker
from sentryrca.retrieval.rrf import fuse
from sentryrca.retrieval.store import ChunkRow, dense_search, fts_search


@dataclass
class RetrievedChunk:
    id: str
    incident_id: str
    subset: str
    chunk_type: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


def _chunk_row_to_retrieved(row: ChunkRow, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        id=row.id,
        incident_id=row.incident_id,
        subset=row.subset,
        chunk_type=row.chunk_type,
        content=row.content,
        score=score,
        metadata=row.metadata,
    )


@traced(name="retrieval.retrieve")
async def retrieve(
    query: str,
    session: AsyncSession,
    *,
    n_dense: int = 20,
    n_fts: int = 20,
    top_k: int = 5,
    subset_filter: list[str] | None = None,
    incident_id: str | None = None,
) -> list[RetrievedChunk]:
    """Hybrid retrieve: dense + FTS → RRF fusion → cross-encoder rerank.

    Args:
        query:         Natural-language query from the agent.
        session:       Active SQLAlchemy async session.
        n_dense:       How many results to pull from dense search.
        n_fts:         How many results to pull from FTS.
        top_k:         Final number of results after reranking.
        subset_filter: Optional list of subsets to restrict results to.
        incident_id:   Restrict results to a single incident (agent use case).

    Returns:
        Top-k RetrievedChunk objects, sorted by reranker score descending.
    """
    query_embedding = embedder.embed_one(query)

    dense_rows, fts_rows = (
        await dense_search(
            session,
            query_embedding,
            n=n_dense,
            subset_filter=subset_filter,
            incident_id=incident_id,
        ),
        await fts_search(
            session,
            query,
            n=n_fts,
            subset_filter=subset_filter,
            incident_id=incident_id,
        ),
    )

    dense_ids = [r.id for r in dense_rows]
    fts_ids = [r.id for r in fts_rows]

    fused = fuse(dense_ids, fts_ids)
    candidate_ids = [doc_id for doc_id, _ in fused[: n_dense + n_fts]]

    all_rows_by_id: dict[str, ChunkRow] = {r.id: r for r in dense_rows}
    all_rows_by_id.update({r.id: r for r in fts_rows})

    candidates = [all_rows_by_id[cid] for cid in candidate_ids if cid in all_rows_by_id]

    if not candidates:
        return []

    rerank_pool = candidates[: max(top_k * 4, 20)]
    texts = [c.content for c in rerank_pool]
    scores = reranker.rerank(query, texts)

    ranked = sorted(zip(scores, rerank_pool, strict=True), key=lambda x: x[0], reverse=True)
    return [_chunk_row_to_retrieved(row, float(score)) for score, row in ranked[:top_k]]
