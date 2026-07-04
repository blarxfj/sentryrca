"""CLI: python -m sentryrca.retrieve "<query>" [--top-k N] [--subset ...]

Connects to the configured Postgres instance and runs the full retrieval pipeline,
printing top-k results with scores, chunk types, and source incident IDs.
"""

import argparse
import asyncio

import structlog

from sentryrca.retrieval.models import make_engine, make_session_factory
from sentryrca.retrieval.search import retrieve

log = structlog.get_logger()


async def _run(query: str, top_k: int, subsets: list[str] | None) -> None:
    engine = make_engine()
    session_factory = make_session_factory(engine)
    try:
        async with session_factory() as session:
            results = await retrieve(
                query,
                session,
                top_k=top_k,
                subset_filter=subsets if subsets else None,
            )
    finally:
        await engine.dispose()

    if not results:
        print("No results found.")
        return

    print(f"\nTop-{top_k} results for: {query!r}\n{'─' * 60}")
    for i, chunk in enumerate(results, 1):
        print(
            f"{i}. [{chunk.chunk_type:>6}] {chunk.incident_id}  score={chunk.score:.4f}\n"
            f"   {chunk.content[:200].replace(chr(10), ' ')!r}…\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid retrieval CLI")
    parser.add_argument("query", help="Natural-language retrieval query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--subset",
        nargs="+",
        choices=["synthetic", "real_derived", "adversarial"],
        help="Restrict to one or more corpus subsets",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.query, args.top_k, args.subset))


if __name__ == "__main__":
    main()
