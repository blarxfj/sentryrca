"""Corpus indexer — reads data/incidents/**/*.json and loads chunks into Postgres.

Run with:
    python -m sentryrca.retrieval.indexer [--data-dir data/incidents]
"""

import asyncio
import json
import pathlib
import sys
from typing import Any

import sqlalchemy as sa
import sqlalchemy.ext.asyncio
import structlog

from sentryrca.retrieval import embedder
from sentryrca.retrieval.chunker import ChunkRecord, chunk_incident
from sentryrca.retrieval.models import make_engine, make_session_factory
from sentryrca.retrieval.store import upsert_chunks
from sentryrca.schema.incident import IncidentCase

log = structlog.get_logger()

_BATCH_SIZE = 32

_DDL = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE IF NOT EXISTS chunks (
        id          TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL,
        subset      TEXT NOT NULL,
        chunk_type  TEXT NOT NULL,
        content     TEXT NOT NULL,
        embedding   vector(384),
        fts_vector  tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
        metadata    JSONB NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx ON chunks USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS chunks_fts_gin_idx ON chunks USING gin (fts_vector)",
    "CREATE INDEX IF NOT EXISTS chunks_incident_id_idx ON chunks (incident_id)",
    """
    CREATE TABLE IF NOT EXISTS rca_runs (
        id              TEXT PRIMARY KEY,
        incident_id     TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        model_version   TEXT NOT NULL,
        prompt_version  TEXT NOT NULL,
        agent_step_count INT NOT NULL,
        total_tokens    INT NOT NULL,
        total_cost_usd  NUMERIC(10, 6) NOT NULL,
        p95_step_latency_ms INT NOT NULL,
        output          JSONB NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS rca_runs_incident_id_idx ON rca_runs (incident_id)",
    "CREATE INDEX IF NOT EXISTS rca_runs_created_at_idx  ON rca_runs (created_at DESC)",
]


def _load_incidents(data_dir: pathlib.Path) -> list[IncidentCase]:
    incidents: list[IncidentCase] = []
    for path in sorted(data_dir.rglob("*.json")):
        try:
            raw = json.loads(path.read_text())
            incidents.append(IncidentCase.model_validate(raw))
        except Exception as exc:
            log.warning("skipping invalid incident file", path=str(path), error=str(exc))
    return incidents


def _chunk_records_to_dicts(
    chunks: list[ChunkRecord],
    embeddings: list[list[float]],
) -> list[dict[str, Any]]:
    assert len(chunks) == len(embeddings)
    return [
        {
            "id": c.id,
            "incident_id": c.incident_id,
            "subset": c.subset,
            "chunk_type": c.chunk_type,
            "content": c.content,
            "embedding": emb,
            "metadata": c.metadata,
        }
        for c, emb in zip(chunks, embeddings, strict=True)
    ]


async def _ensure_schema(engine: sa.ext.asyncio.AsyncEngine) -> None:
    async with engine.begin() as conn:
        for stmt in _DDL:
            await conn.execute(sa.text(stmt))
    log.info("schema ready")


async def _run(data_dir: pathlib.Path) -> None:
    incidents = _load_incidents(data_dir)
    if not incidents:
        log.error("no valid incidents found", data_dir=str(data_dir))
        sys.exit(1)

    log.info("loaded incidents", count=len(incidents))

    all_chunks: list[ChunkRecord] = []
    for incident in incidents:
        all_chunks.extend(chunk_incident(incident))

    log.info("chunked corpus", total_chunks=len(all_chunks))

    engine = make_engine()
    session_factory = make_session_factory(engine)

    await _ensure_schema(engine)

    try:
        for batch_start in range(0, len(all_chunks), _BATCH_SIZE):
            batch = all_chunks[batch_start : batch_start + _BATCH_SIZE]
            texts = [c.content for c in batch]
            embeddings = embedder.embed(texts)
            rows = _chunk_records_to_dicts(batch, embeddings)

            async with session_factory() as session:
                async with session.begin():
                    await upsert_chunks(session, rows)

            log.info(
                "indexed batch",
                batch=f"{batch_start // _BATCH_SIZE + 1}/{-(-len(all_chunks) // _BATCH_SIZE)}",
                chunks=len(batch),
            )
    finally:
        await engine.dispose()

    log.info("indexing complete", total_chunks=len(all_chunks))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Index incident corpus into pgvector")
    parser.add_argument(
        "--data-dir",
        type=pathlib.Path,
        default=pathlib.Path("data/incidents"),
        help="Root directory containing incident JSON files (searched recursively)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.data_dir))


if __name__ == "__main__":
    main()
