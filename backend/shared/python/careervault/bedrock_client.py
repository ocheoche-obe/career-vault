"""Bedrock client wrapper for CareerVault — STUB.

This module will centralise every Bedrock call per ADR-008 / ADR-017:

- ``converse(...)`` over the Converse API for Claude Haiku + Sonnet (chat parsing, the resume
  agent loop, check-in personalisation), with model routing per ADR-009 and exponential-backoff
  retry per NFR-3.3.
- ``embed(...)`` over the ``InvokeModel`` API for Titan Text Embeddings v2 (write-path embedding
  generation, ADR-016 / ADR-024).

It is intentionally left as a stub for the first vertical slice (auth + GET /settings), which
touches no Bedrock. The real implementation lands when the first Bedrock-using Lambda
(`chat_lambda` or `career_crud`) is built. Model IDs will be read from env vars
(`BEDROCK_HAIKU_MODEL_ID`, `BEDROCK_SONNET_MODEL_ID`, `BEDROCK_TITAN_EMBED_MODEL_ID`) so they
stay in lockstep with the IAM-pinned ARNs (Section 4.3.4).
"""

from __future__ import annotations

from typing import Any


def converse(*args: Any, **kwargs: Any):  # pragma: no cover - stub
    """Claude Converse wrapper (Haiku/Sonnet). Not yet implemented."""
    raise NotImplementedError(
        "bedrock_client.converse is a stub; implement when the first Converse-using "
        "Lambda is built (see ADR-017)."
    )


def embed(*args: Any, **kwargs: Any):  # pragma: no cover - stub
    """Titan Text Embeddings v2 wrapper. Not yet implemented."""
    raise NotImplementedError(
        "bedrock_client.embed is a stub; implement alongside career_crud's write path "
        "(see ADR-016 / ADR-024)."
    )
