"""Unit tests for the vector-similarity helpers (ADR-016 / ADR-033)."""

from decimal import Decimal

import pytest

from careervault.similarity import cosine_similarity, rank_by_similarity


# --- cosine_similarity -------------------------------------------------------

def test_identical_vectors_score_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_orthogonal_vectors_score_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_opposite_vectors_score_minus_one():
    assert cosine_similarity([1.0, 1.0], [-1.0, -1.0]) == pytest.approx(-1.0)


def test_magnitude_is_normalised_away():
    # Same direction, different length → still 1.0 (cosine ignores magnitude).
    assert cosine_similarity([2.0, 0.0], [5.0, 0.0]) == 1.0


def test_accepts_decimal_components_from_dynamodb():
    # Embeddings read back from DynamoDB arrive as Decimals — must not raise.
    score = cosine_similarity([Decimal("1.0"), Decimal("0.0")], [Decimal("1.0"), Decimal("0.0")])
    assert score == 1.0


def test_length_mismatch_is_zero_not_error():
    assert cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


def test_zero_vector_is_zero_not_nan():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_empty_vectors_are_zero():
    assert cosine_similarity([], []) == 0.0


# --- rank_by_similarity ------------------------------------------------------

def test_ranks_items_most_similar_first():
    query = [1.0, 0.0]
    items = [
        {"entry_id": "far", "embedding": [0.0, 1.0]},       # orthogonal → 0.0
        {"entry_id": "near", "embedding": [1.0, 0.05]},     # nearly aligned → ~1.0
        {"entry_id": "mid", "embedding": [1.0, 1.0]},       # 45° → ~0.707
    ]
    ranked = rank_by_similarity(query, items)

    assert [item["entry_id"] for item, _ in ranked] == ["near", "mid", "far"]
    assert ranked[0][1] > ranked[1][1] > ranked[2][1]


def test_items_without_an_embedding_are_dropped_not_scored_zero():
    # An absent vector is "unknown", not "dissimilar" — it should not appear at all.
    items = [{"entry_id": "has"}, {"entry_id": "none", "embedding": [1.0, 0.0]}]
    ranked = rank_by_similarity([1.0, 0.0], items)
    assert [item["entry_id"] for item, _ in ranked] == ["none"]


def test_empty_corpus_ranks_to_empty():
    assert rank_by_similarity([1.0, 0.0], []) == []
