"""Reciprocal Rank Fusion — pure function, no I/O."""


def fuse(
    *rank_lists: list[str],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse ranked ID lists using RRF.

    score(d) = Σ_r 1 / (k + rank_r(d))

    Returns ids sorted by descending fused score.
    """
    scores: dict[str, float] = {}
    for ranked in rank_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
