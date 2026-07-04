"""Unit tests for the search pipeline — all DB and ML calls are mocked."""

from unittest.mock import AsyncMock, patch

import pytest

from sentryrca.retrieval.search import RetrievedChunk, _chunk_row_to_retrieved, retrieve
from sentryrca.retrieval.store import ChunkRow


def _make_row(id: str, content: str = "test content", chunk_type: str = "alert") -> ChunkRow:
    return ChunkRow(
        id=id,
        incident_id="syn-001",
        subset="synthetic",
        chunk_type=chunk_type,
        content=content,
        metadata={},
    )


def test_chunk_row_to_retrieved_maps_fields() -> None:
    row = _make_row("syn-001_alert_0", content="ALERT: latency spike", chunk_type="alert")
    result = _chunk_row_to_retrieved(row, score=0.95)
    assert result.id == "syn-001_alert_0"
    assert result.incident_id == "syn-001"
    assert result.subset == "synthetic"
    assert result.chunk_type == "alert"
    assert result.content == "ALERT: latency spike"
    assert result.score == pytest.approx(0.95)


def test_retrieved_chunk_dataclass_fields() -> None:
    chunk = RetrievedChunk(
        id="x",
        incident_id="syn-001",
        subset="synthetic",
        chunk_type="log",
        content="some log",
        score=0.5,
    )
    assert chunk.metadata == {}


@pytest.mark.asyncio
async def test_retrieve_returns_top_k() -> None:
    rows = [_make_row(f"chunk_{i}", content=f"content {i}") for i in range(5)]
    session = AsyncMock()

    with (
        patch("sentryrca.retrieval.search.embedder.embed_one", return_value=[0.1] * 384),
        patch("sentryrca.retrieval.search.dense_search", new=AsyncMock(return_value=rows)),
        patch("sentryrca.retrieval.search.fts_search", new=AsyncMock(return_value=rows[:3])),
        patch(
            "sentryrca.retrieval.search.reranker.rerank",
            return_value=[0.9, 0.8, 0.7, 0.6, 0.5],
        ),
    ):
        results = await retrieve("checkout latency", session, top_k=3)

    assert len(results) == 3


@pytest.mark.asyncio
async def test_retrieve_returns_empty_on_no_candidates() -> None:
    session = AsyncMock()

    with (
        patch("sentryrca.retrieval.search.embedder.embed_one", return_value=[0.1] * 384),
        patch("sentryrca.retrieval.search.dense_search", new=AsyncMock(return_value=[])),
        patch("sentryrca.retrieval.search.fts_search", new=AsyncMock(return_value=[])),
    ):
        results = await retrieve("nothing matches", session, top_k=5)

    assert results == []


@pytest.mark.asyncio
async def test_retrieve_scores_are_descending() -> None:
    rows = [_make_row(f"chunk_{i}") for i in range(4)]
    session = AsyncMock()

    with (
        patch("sentryrca.retrieval.search.embedder.embed_one", return_value=[0.1] * 384),
        patch("sentryrca.retrieval.search.dense_search", new=AsyncMock(return_value=rows)),
        patch("sentryrca.retrieval.search.fts_search", new=AsyncMock(return_value=[])),
        patch(
            "sentryrca.retrieval.search.reranker.rerank",
            return_value=[0.3, 0.9, 0.1, 0.7],
        ),
    ):
        results = await retrieve("query", session, top_k=4)

    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_retrieve_merges_dense_and_fts_candidates() -> None:
    dense_rows = [_make_row("a"), _make_row("b")]
    fts_rows = [_make_row("c"), _make_row("d")]
    session = AsyncMock()

    with (
        patch("sentryrca.retrieval.search.embedder.embed_one", return_value=[0.1] * 384),
        patch("sentryrca.retrieval.search.dense_search", new=AsyncMock(return_value=dense_rows)),
        patch("sentryrca.retrieval.search.fts_search", new=AsyncMock(return_value=fts_rows)),
        patch(
            "sentryrca.retrieval.search.reranker.rerank",
            return_value=[0.9, 0.8, 0.7, 0.6],
        ),
    ):
        results = await retrieve("query", session, top_k=4)

    result_ids = {r.id for r in results}
    assert result_ids == {"a", "b", "c", "d"}
