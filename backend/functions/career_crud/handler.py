"""career_crud — entry lifecycle (Section 3.1.3).

``POST /entries`` is the Phase B confirm-and-persist path: the user has reviewed (and possibly
edited) the candidate ``chat_lambda`` produced, and now commits it.

Three steps, in order:

1. **Pydantic validation by ``entry_type``** — the discriminated union is the single source of
   truth (ADR-022). A required field the user blanked out in the confirmation UI is caught here
   and returned as ``422`` with field-level errors.
2. **Titan embedding, synchronously** — inline with the write, per ADR-024. A failure bubbles up
   as ``500``; the ULID makes the user's retry land on the same SK, so nothing duplicates.
3. **Conditional PutItem** — ``attribute_not_exists(SK)`` makes the confirm idempotent
   (Section 3.1.4): first write is ``201``, a duplicate confirm is ``200`` with the existing item.

This is the only Lambda permitted to write ``ENTRY#`` items (Section 4.2.3).

Status contract (Section 3.1.5): 201 created · 200 idempotent duplicate · 422 validation ·
500 embedding/DynamoDB failure · 401 handled upstream by the authorizer.
"""

from __future__ import annotations

import json
import os

from aws_lambda_powertools.metrics import MetricUnit
from pydantic import ValidationError

from careervault import bedrock_client
from careervault.bedrock_client import BedrockError
from careervault.ddb_helpers import (
    extract_user_id,
    from_ddb_numbers,
    get_entry,
    new_ulid,
    put_entry_conditional,
)
from careervault.observability import bind_request_context, logger, metrics, tracer
from careervault.pydantic_models.entry import (
    embedding_input_text,
    to_entry_item,
    validate_entry,
)

_CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "http://localhost:5173"),
}


def _response(status_code: int, body: dict) -> dict:
    return {"statusCode": status_code, "headers": _CORS_HEADERS, "body": json.dumps(body)}


def _public_entry(item: dict) -> dict:
    """Strip the embedding before returning an entry to the client.

    The vector is ~1024 floats (10–15 KB) and is useless to the frontend — it exists only for
    the resume agent's in-Lambda cosine similarity (ADR-016). Shipping it would inflate every
    response for no benefit.
    """
    public = {key: value for key, value in item.items() if key != "embedding"}
    return from_ddb_numbers(public)


def _validation_errors(exc: ValidationError) -> list[dict]:
    """Flatten Pydantic errors into the field-level shape React renders inline."""
    return [
        {"field": ".".join(str(part) for part in err["loc"]), "error": err["msg"]}
        for err in exc.errors()
    ]


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def handler(event, context) -> dict:
    bind_request_context(event)

    try:
        user_id = extract_user_id(event)
    except PermissionError:
        logger.warning("Request missing sub claim")
        return _response(401, {"message": "Unauthorized"})

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"message": "Body must be valid JSON"})

    if not isinstance(body, dict):
        return _response(400, {"message": "Body must be a JSON object"})

    # The ULID minted at propose_entry time (Section 3.1.4). Absent it — a direct API create with
    # no chat turn behind it — we mint one here, and the request is simply not retry-idempotent.
    entry_id = body.pop("entry_id", None) or new_ulid()

    try:
        entry = validate_entry(body)
    except ValidationError as exc:
        logger.info("Entry failed validation", extra={"entry_id": entry_id})
        metrics.add_metric(name="EntryValidationFailure", unit=MetricUnit.Count, value=1)
        return _response(422, {"message": "Validation failed", "errors": _validation_errors(exc)})

    logger.append_keys(entry_id=entry_id, entry_type=entry.entry_type)

    # Sync embedding in the write path (ADR-024). Titan failure fails the user's write; the
    # frontend retry lands on the same SK, so the conditional write still protects us.
    try:
        embedding = bedrock_client.embed(embedding_input_text(entry))
    except BedrockError:
        logger.exception("Titan embedding failed")
        metrics.add_metric(name="EntryEmbeddingFailure", unit=MetricUnit.Count, value=1)
        return _response(500, {"message": "Could not save entry — please retry."})

    item = to_entry_item(
        entry,
        user_id=user_id,
        entry_id=entry_id,
        embedding=embedding,
        embedding_model=os.environ["BEDROCK_TITAN_EMBED_MODEL_ID"],
    )

    created = put_entry_conditional(item)
    if created:
        metrics.add_metric(name="EntryCreated", unit=MetricUnit.Count, value=1)
        logger.info("Entry created")
        return _response(201, {"entry": _public_entry(item)})

    # The conditional failed. Re-read to distinguish an idempotent duplicate confirm (the item is
    # there — return it as 200) from a tripped `begins_with` prefix guard (it isn't — that's a
    # bug in SK construction, and a 500 is the honest answer).
    existing = get_entry(user_id, entry_id)
    if existing is None:
        logger.error("Conditional put failed but entry is absent — SK prefix guard tripped")
        return _response(500, {"message": "Could not save entry — please retry."})

    metrics.add_metric(name="EntryDuplicateConfirm", unit=MetricUnit.Count, value=1)
    logger.info("Idempotent duplicate confirm; returning existing entry")
    return _response(200, {"entry": _public_entry(existing)})
