"""Bedrock client wrapper for CareerVault (ADR-008 / ADR-017 / ADR-031).

Every Bedrock call in the system goes through this module.

- :func:`converse` — the Converse API for Claude (ADR-017). Tool use is first-class, and model
  swapping is a model-ID change rather than a payload rewrite.
- :func:`embed` — ``InvokeModel`` for Titan Text Embeddings v2 (ADR-016 / ADR-024).

**Model identifiers (ADR-031).** Claude Haiku 4.5 has *no on-demand support* — it is reachable
only through an inference profile, so ``BEDROCK_HAIKU_MODEL_ID`` holds the ``us.``-prefixed
cross-region profile ID (``us.anthropic.claude-haiku-4-5-20251001-v1:0``), not the bare
foundation-model ID. Titan v2 is on-demand and uses its bare model ID. Both come from environment
variables set in the SAM template, kept in lockstep with the IAM ARNs (Section 4.3.4).

**Retry policy (NFR-3.3).** Transient Bedrock failures (throttling, 5xx, model timeouts) are
retried with exponential backoff and jitter, to a maximum of 3 attempts. botocore's own retries
are disabled so this loop is the single, predictable authority on attempt count.
"""

from __future__ import annotations

import json
import os
import random
import time
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ConnectTimeoutError, ReadTimeoutError

from .observability import logger, metrics

try:  # pragma: no cover - import shape differs across powertools minor versions
    from aws_lambda_powertools.metrics import MetricUnit
except ImportError:  # pragma: no cover
    from aws_lambda_powertools.metrics.base import MetricUnit  # type: ignore[no-redef]

#: Max attempts for a single logical Bedrock call, per NFR-3.3.
MAX_ATTEMPTS = 3

#: Bedrock error codes worth retrying. Anything else (validation, access denied, malformed
#: request) is a bug or a permissions problem — retrying just burns latency and money.
_TRANSIENT_ERROR_CODES = frozenset(
    {
        "ThrottlingException",
        "TooManyRequestsException",
        "ServiceUnavailableException",
        "InternalServerException",
        "ModelTimeoutException",
        "ModelNotReadyException",
    }
)

_DEFAULT_EMBED_DIMENSIONS = 1024

_client = None


class BedrockError(RuntimeError):
    """A Bedrock call failed permanently (non-transient, or retries exhausted)."""


def get_client():
    """Return the cached ``bedrock-runtime`` client.

    botocore retries are disabled (``max_attempts: 1`` counts the initial try) so that
    :func:`_invoke_with_retry` is the only thing deciding how many times we call Bedrock —
    otherwise the two retry layers multiply and NFR-3.3's "max 3" silently becomes 9+.
    """
    global _client
    if _client is None:
        _client = boto3.client(
            "bedrock-runtime",
            config=Config(
                retries={"max_attempts": 1, "mode": "standard"},
                read_timeout=int(os.environ.get("BEDROCK_READ_TIMEOUT_SECONDS", "25")),
                connect_timeout=5,
            ),
        )
    return _client


def _invoke_with_retry(operation: str, call):
    """Run ``call`` with exponential backoff + jitter on transient Bedrock errors."""
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return call()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            last_error = exc
            if code not in _TRANSIENT_ERROR_CODES:
                logger.exception("Bedrock %s failed permanently", operation, extra={"error_code": code})
                raise BedrockError(f"Bedrock {operation} failed: {code}") from exc
            if attempt == MAX_ATTEMPTS:
                break
            _backoff_sleep(attempt)
            logger.warning(
                "Bedrock %s transient failure; retrying",
                operation,
                extra={"error_code": code, "attempt": attempt},
            )
        except (ReadTimeoutError, ConnectTimeoutError) as exc:
            # A socket timeout is not a ClientError, so it would otherwise crash the caller
            # uncaught. It is transient by nature — retry, then surface as a BedrockError so callers
            # get the one failure type they already handle (this matters for the resume agent, whose
            # long Sonnet calls are the ones most likely to brush the read timeout).
            last_error = exc
            if attempt == MAX_ATTEMPTS:
                break
            _backoff_sleep(attempt)
            logger.warning("Bedrock %s timed out; retrying", operation, extra={"attempt": attempt})

    logger.error("Bedrock %s exhausted %d attempts", operation, MAX_ATTEMPTS)
    raise BedrockError(f"Bedrock {operation} failed after {MAX_ATTEMPTS} attempts") from last_error


def _backoff_sleep(attempt: int) -> None:
    """Exponential backoff with full jitter — spreads retries so concurrent Lambdas don't
    synchronise into a thundering herd against a throttling/slow endpoint."""
    backoff = min(2 ** (attempt - 1), 4) * 0.5
    time.sleep(random.uniform(0, backoff))


def _record_token_metrics(usage: dict) -> None:
    """Emit token counts as CloudWatch metrics — the leading indicator of Bedrock spend."""
    if not usage:
        return
    try:
        metrics.add_metric(name="BedrockInputTokens", unit=MetricUnit.Count, value=usage.get("inputTokens", 0))
        metrics.add_metric(name="BedrockOutputTokens", unit=MetricUnit.Count, value=usage.get("outputTokens", 0))
    except Exception:  # pragma: no cover - metrics must never break the request path
        logger.debug("Could not record token metrics", exc_info=True)


def converse(
    messages: list[dict[str, Any]],
    *,
    system: str | None = None,
    tool_config: dict | None = None,
    model_id: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> dict:
    """Call Claude via the Converse API and return the raw response.

    Args:
        messages: Converse-format turns, e.g. ``[{"role": "user", "content": [{"text": "..."}]}]``.
        system: Optional system prompt.
        tool_config: Optional ``toolConfig`` (see :func:`careervault.pydantic_models.tools.build_tool_config`).
        model_id: Defaults to ``BEDROCK_HAIKU_MODEL_ID`` — an *inference profile* ID per ADR-031.
        max_tokens: Response cap. Also a cost ceiling per call.
        temperature: 0.0 for extraction work — we want determinism, not creativity.

    Raises:
        BedrockError: on permanent failure or exhausted retries.
    """
    resolved_model = model_id or os.environ["BEDROCK_HAIKU_MODEL_ID"]

    request: dict[str, Any] = {
        "modelId": resolved_model,
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system:
        request["system"] = [{"text": system}]
    if tool_config:
        request["toolConfig"] = tool_config

    response = _invoke_with_retry("converse", lambda: get_client().converse(**request))

    usage = response.get("usage", {})
    _record_token_metrics(usage)
    logger.info(
        "Bedrock converse complete",
        extra={
            "model_id": resolved_model,
            "stop_reason": response.get("stopReason"),
            "input_tokens": usage.get("inputTokens"),
            "output_tokens": usage.get("outputTokens"),
        },
    )
    return response


def embed(text: str, *, model_id: str | None = None, dimensions: int | None = None) -> list[float]:
    """Embed a single string with Titan Text Embeddings v2 (ADR-016).

    Titan v2 is an on-demand model invoked by its bare model ID (ADR-031), via ``InvokeModel``
    rather than Converse — Converse is a chat-completion surface and does not cover embeddings.

    Raises:
        BedrockError: on permanent failure or exhausted retries.
    """
    resolved_model = model_id or os.environ["BEDROCK_TITAN_EMBED_MODEL_ID"]
    resolved_dims = dimensions or int(
        os.environ.get("BEDROCK_EMBED_DIMENSIONS", _DEFAULT_EMBED_DIMENSIONS)
    )

    body = json.dumps({"inputText": text, "dimensions": resolved_dims, "normalize": True})

    response = _invoke_with_retry(
        "embed",
        lambda: get_client().invoke_model(
            modelId=resolved_model, body=body, accept="application/json", contentType="application/json"
        ),
    )

    payload = json.loads(response["body"].read())
    embedding = payload.get("embedding")
    if not embedding:
        raise BedrockError("Titan returned no embedding vector")

    logger.debug(
        "Embedding generated",
        extra={
            "model_id": resolved_model,
            "dimensions": len(embedding),
            "input_tokens": payload.get("inputTextTokenCount"),
        },
    )
    return embedding


def embed_many(texts: list[str], *, model_id: str | None = None, dimensions: int | None = None) -> list[list[float]]:
    """Embed several strings, returning vectors in input order.

    **This is a client-side loop, not a batched API call.** Titan Text Embeddings v2's
    ``InvokeModel`` body accepts exactly one ``inputText`` per request — it has no multi-input
    form. (Architecture Section 4.6.2 asserts otherwise; that claim does not hold against the
    live API.) The loop is kept behind this helper so the bulk-upload path in
    ``resume_upload_parser`` has one place to change if a genuinely batched surface — Bedrock
    batch inference, or a model that accepts an array — is adopted later.

    Cost and latency both scale linearly with ``len(texts)``: ~$0.00002 and ~200–500 ms each.
    """
    return [embed(text, model_id=model_id, dimensions=dimensions) for text in texts]
