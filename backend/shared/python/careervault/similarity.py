"""Vector-similarity helpers for in-Lambda semantic retrieval (ADR-016).

CareerVault stores each entry's Titan embedding *on the entry item* (Section 2.9) and ranks by
cosine similarity inside the Lambda rather than in a managed vector store — the corpus is small
enough that reading all entries (AP-10) and scoring them in memory is milliseconds and single-digit
RCUs (Section 2.6 / ADR-028).

This module is the one place that math lives, so every consumer shares it:

- **Slice 3 (ADR-033)** — confirm-time duplicate detection: score a candidate against existing
  entries and flag near-duplicates above a threshold.
- **Slice 6** — resume-agent retrieval: rank entries against a job description, take the top-k.
- **Slice 7** — chat-over-your-data: the same retrieval for grounded Q&A.

Embeddings read back from DynamoDB arrive as ``Decimal`` lists; every function here coerces to
``float`` so callers never have to.
"""

from __future__ import annotations

from math import sqrt
from typing import Any, Callable, Sequence


def cosine_similarity(a: Sequence[Any], b: Sequence[Any]) -> float:
    """Cosine similarity of two vectors, in ``[-1.0, 1.0]``.

    Accepts ``float`` or ``Decimal`` components (the latter is how DynamoDB hands embeddings
    back). Titan v2 vectors are L2-normalised at generation time (``normalize=True`` in
    :func:`careervault.bedrock_client.embed`), so for CareerVault's own vectors this reduces to a
    dot product — but the full form is computed anyway so the helper is correct for any input,
    including a hand-built or externally-sourced vector.

    Returns ``0.0`` if the vectors differ in length or either is a zero vector — a "no signal"
    answer rather than a raised exception, since a mismatch here should degrade retrieval, not
    fail the request.
    """
    if len(a) != len(b) or not a:
        return 0.0

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        fx = float(x)
        fy = float(y)
        dot += fx * fy
        norm_a += fx * fx
        norm_b += fy * fy

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (sqrt(norm_a) * sqrt(norm_b))


def rank_by_similarity(
    query: Sequence[Any],
    items: Sequence[dict],
    *,
    embedding_key: str = "embedding",
    vectorize: Callable[[dict], Sequence[Any]] | None = None,
) -> list[tuple[dict, float]]:
    """Score ``items`` against ``query`` and return them sorted most-similar first.

    Each item is paired with its cosine similarity to ``query``. Items missing an embedding (or
    whose ``vectorize`` returns nothing) are dropped rather than scored as ``0.0`` — an absent
    vector is "unknown", not "dissimilar".

    Args:
        query: the reference embedding (e.g. a new entry's vector, or a job description's).
        items: DynamoDB item dicts to rank.
        embedding_key: attribute holding each item's vector (default ``"embedding"``).
        vectorize: optional override to extract the vector from an item, for stores that nest it.
    """
    extract = vectorize or (lambda item: item.get(embedding_key))

    scored: list[tuple[dict, float]] = []
    for item in items:
        vector = extract(item)
        if not vector:
            continue
        scored.append((item, cosine_similarity(query, vector)))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored
