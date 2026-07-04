"""Integration tests for the retrieval pipeline — requires postgres + indexed corpus.

Run: make up && make index-corpus && pytest tests/integration/

Skipped automatically when postgres is unreachable or corpus is not indexed.
"""

import pytest

from sentryrca.retrieval.models import make_engine, make_session_factory
from sentryrca.retrieval.search import retrieve


async def _count_chunks(session_factory) -> int:  # type: ignore[no-untyped-def]
    import sqlalchemy as sa

    from sentryrca.retrieval.models import Chunk

    async with session_factory() as session:
        result = await session.execute(sa.select(sa.func.count()).select_from(Chunk))
        return result.scalar_one()


@pytest.fixture
def engine():  # type: ignore[no-untyped-def]
    return make_engine()


@pytest.fixture
def session_factory(engine):  # type: ignore[no-untyped-def]
    return make_session_factory(engine)


@pytest.fixture(autouse=True)
async def require_indexed_corpus(session_factory):  # type: ignore[no-untyped-def]
    try:
        count = await _count_chunks(session_factory)
    except Exception as exc:
        pytest.skip(f"postgres unavailable: {exc}")
    if count == 0:
        pytest.skip("corpus not indexed — run: make index-corpus")


@pytest.mark.asyncio
async def test_retrieve_returns_results(session_factory):  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        results = await retrieve("checkout connection pool exhausted", session, top_k=3)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_retrieve_finds_relevant_incident(session_factory):  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        results = await retrieve(
            "checkout-service p99 latency spike connection pool exhausted", session, top_k=5
        )
    # At least one result should reference a checkout-service incident
    assert any("checkout" in r.content.lower() or "checkout" in r.incident_id for r in results)


@pytest.mark.asyncio
async def test_retrieve_scores_are_descending(session_factory):  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        results = await retrieve("payment service TLS certificate expired", session, top_k=5)
    assert len(results) > 0
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_retrieve_chunk_types_present(session_factory):  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        results = await retrieve("redis OOM eviction cache miss", session, top_k=10)
    chunk_types = {r.chunk_type for r in results}
    assert chunk_types & {"alert", "log", "deploy"}


@pytest.mark.asyncio
async def test_retrieve_subset_filter_synthetic_only(session_factory):  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        results = await retrieve(
            "database connection saturation",
            session,
            top_k=5,
            subset_filter=["synthetic"],
        )
    assert len(results) > 0
    for r in results:
        assert r.subset == "synthetic"


@pytest.mark.asyncio
async def test_retrieve_adversarial_subset(session_factory):  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        results = await retrieve(
            "TLS certificate expired payment processor",
            session,
            top_k=5,
            subset_filter=["adversarial"],
        )
    assert len(results) > 0
    for r in results:
        assert r.subset == "adversarial"


@pytest.mark.asyncio
async def test_retrieve_result_has_required_fields(session_factory):  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        results = await retrieve("checkout latency spike", session, top_k=1)
    assert len(results) == 1
    r = results[0]
    assert r.id
    assert r.incident_id
    assert r.subset in {"synthetic", "real_derived", "adversarial"}
    assert r.chunk_type in {"alert", "log", "deploy", "runbook"}
    assert r.content
    assert 0.0 <= r.score  # reranker scores are unbounded but positive for relevant content
