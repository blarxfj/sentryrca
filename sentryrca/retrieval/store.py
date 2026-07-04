"""Async DB operations: upsert chunks, dense search, FTS search."""

from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sentryrca.retrieval.models import Chunk


@dataclass
class ChunkRow:
    id: str
    incident_id: str
    subset: str
    chunk_type: str
    content: str
    metadata: dict[str, Any]


async def upsert_chunks(
    session: AsyncSession,
    chunks: list[dict[str, Any]],
) -> None:
    """Insert or replace chunks in bulk. `chunks` is a list of dicts matching Chunk columns."""
    if not chunks:
        return
    stmt = pg_insert(Chunk.__table__).values(chunks)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "content": stmt.excluded.content,
            "embedding": stmt.excluded.embedding,
            "metadata": stmt.excluded.metadata,
        },
    )
    await session.execute(stmt)


async def dense_search(
    session: AsyncSession,
    query_embedding: list[float],
    n: int = 20,
    subset_filter: list[str] | None = None,
    incident_id: str | None = None,
) -> list[ChunkRow]:
    """Return top-n chunks by cosine similarity (pgvector HNSW)."""
    where_clauses = []
    if subset_filter:
        where_clauses.append(Chunk.subset.in_(subset_filter))
    if incident_id is not None:
        where_clauses.append(Chunk.incident_id == incident_id)

    stmt = (
        sa.select(
            Chunk.id,
            Chunk.incident_id,
            Chunk.subset,
            Chunk.chunk_type,
            Chunk.content,
            Chunk.metadata_,
        )
        .where(Chunk.embedding.isnot(None), *where_clauses)
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(n)
    )
    rows = (await session.execute(stmt)).fetchall()
    return [
        ChunkRow(
            id=r.id,
            incident_id=r.incident_id,
            subset=r.subset,
            chunk_type=r.chunk_type,
            content=r.content,
            metadata=r.metadata_,
        )
        for r in rows
    ]


async def fts_search(
    session: AsyncSession,
    query: str,
    n: int = 20,
    subset_filter: list[str] | None = None,
    incident_id: str | None = None,
) -> list[ChunkRow]:
    """Return top-n chunks by Postgres FTS rank."""
    tsq = sa.func.plainto_tsquery("english", query)
    fts_col = sa.func.to_tsvector("english", Chunk.content)
    rank_col = sa.func.ts_rank(fts_col, tsq)

    where_clauses: list[Any] = [fts_col.op("@@")(tsq)]
    if subset_filter:
        where_clauses.append(Chunk.subset.in_(subset_filter))
    if incident_id is not None:
        where_clauses.append(Chunk.incident_id == incident_id)

    stmt = (
        sa.select(
            Chunk.id,
            Chunk.incident_id,
            Chunk.subset,
            Chunk.chunk_type,
            Chunk.content,
            Chunk.metadata_,
        )
        .where(*where_clauses)
        .order_by(rank_col.desc())
        .limit(n)
    )
    rows = (await session.execute(stmt)).fetchall()
    return [
        ChunkRow(
            id=r.id,
            incident_id=r.incident_id,
            subset=r.subset,
            chunk_type=r.chunk_type,
            content=r.content,
            metadata=r.metadata_,
        )
        for r in rows
    ]


async def fetch_chunks_by_ids(
    session: AsyncSession,
    ids: list[str],
) -> dict[str, ChunkRow]:
    """Bulk-fetch chunks by id. Returns a dict keyed by id."""
    if not ids:
        return {}
    stmt = sa.select(
        Chunk.id,
        Chunk.incident_id,
        Chunk.subset,
        Chunk.chunk_type,
        Chunk.content,
        Chunk.metadata_,
    ).where(Chunk.id.in_(ids))
    rows = (await session.execute(stmt)).fetchall()
    return {
        r.id: ChunkRow(
            id=r.id,
            incident_id=r.incident_id,
            subset=r.subset,
            chunk_type=r.chunk_type,
            content=r.content,
            metadata=r.metadata_,
        )
        for r in rows
    }
