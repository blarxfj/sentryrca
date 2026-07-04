"""Unit tests for Reciprocal Rank Fusion — pure function."""

import pytest

from sentryrca.retrieval.rrf import fuse


def test_single_list_returns_same_order() -> None:
    result = fuse(["a", "b", "c"])
    ids = [r[0] for r in result]
    assert ids == ["a", "b", "c"]


def test_scores_decrease_with_rank() -> None:
    result = fuse(["a", "b", "c"])
    scores = [r[1] for r in result]
    assert scores[0] > scores[1] > scores[2]


def test_agreement_boosts_score() -> None:
    # "a" appears first in both lists — should rank above "b" (first in one, second in other)
    result = fuse(["a", "b"], ["a", "c"])
    ids = [r[0] for r in result]
    assert ids[0] == "a"


def test_rrf_formula_exact_value() -> None:
    # rank-1 in one list, k=60: 1/(60+1) = 1/61
    result = fuse(["x"], k=60)
    assert pytest.approx(result[0][1], rel=1e-9) == 1.0 / 61


def test_two_lists_with_no_overlap() -> None:
    result = fuse(["a", "b"], ["c", "d"])
    ids = [r[0] for r in result]
    assert set(ids) == {"a", "b", "c", "d"}
    # rank-1 items from each list should tie
    score_a = next(s for i, s in result if i == "a")
    score_c = next(s for i, s in result if i == "c")
    assert score_a == score_c


def test_empty_lists_return_empty() -> None:
    assert fuse([], []) == []


def test_single_list_single_item() -> None:
    result = fuse(["only"])
    assert len(result) == 1
    assert result[0][0] == "only"


def test_custom_k_changes_scores() -> None:
    result_default = fuse(["a"], k=60)
    result_low_k = fuse(["a"], k=1)
    assert result_low_k[0][1] > result_default[0][1]


def test_three_lists_triple_agreement() -> None:
    result = fuse(["x", "y"], ["x", "z"], ["x", "w"])
    assert result[0][0] == "x"
    # x's score = 3 * 1/(60+1)
    assert pytest.approx(result[0][1], rel=1e-9) == 3.0 / 61
