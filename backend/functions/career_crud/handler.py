"""career_crud — the full entry lifecycle (Sections 3.1.3–3.1.5, ADR-027, ADR-033).

Routes (all under the Cognito authorizer; ``user_id`` always from the JWT, never the body):

- ``POST   /entries``      — Phase B confirm/persist. Validate → embed → **semantic duplicate
  check** (ADR-033) → conditional ``PutItem``. 201 created · 200 idempotent duplicate ·
  409 possible duplicate (unacknowledged) · 422 validation · 500 embed/DDB failure.
- ``GET    /entries``      — list every entry for the dashboard (AP-10). Embeddings stripped.
- ``PUT    /entries/{id}`` — edit. Re-embeds **only when the embedded text changed** (ADR-024
  edit-path note); a full-item conditional ``PutItem`` (``attribute_exists(SK)``), not UpdateItem.
- ``DELETE /entries/{id}`` — hard delete with the UI confirm as the safety net (ADR-027).

This is the only Lambda permitted to write, update, or delete ``ENTRY#`` items (Section 4.2.3).
"""

from __future__ import annotations

import json
import os

from aws_lambda_powertools.metrics import MetricUnit
from pydantic import ValidationError

from careervault import bedrock_client
from careervault.bedrock_client import BedrockError
from careervault.ddb_helpers import (
    delete_entry,
    extract_user_id,
    from_ddb_numbers,
    get_entry,
    new_ulid,
    put_entry_conditional,
    put_entry_update,
    query_entries,
)
from careervault.observability import bind_request_context, logger, metrics, tracer
from careervault.pydantic_models.entry import (
    embedding_input_text,
    entry_from_item,
    to_entry_item,
    utcnow_iso,
    validate_entry,
)
from careervault.similarity import rank_by_similarity

_CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "http://localhost:5173"),
}

#: Cosine-similarity threshold above which a candidate is flagged a possible duplicate (ADR-033).
#: Env-tunable so it can be calibrated against real entries without a code change.
_DEFAULT_DUP_THRESHOLD = "0.90"


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


def _duplicate_matches(user_id: str, entry_id: str, embedding: list[float]) -> list[dict]:
    """Return existing entries whose embedding is within the dup threshold of ``embedding``.

    The candidate's *own* ``entry_id`` is excluded so this never fights §3.1.4 idempotency: a
    genuine same-card retry (same ``entry_id``) would otherwise match its already-saved self at
    similarity 1.0 and be flagged as a duplicate of itself. Ranked descending, so the first score
    below the threshold ends the scan.
    """
    threshold = float(os.environ.get("DUP_SIMILARITY_THRESHOLD", _DEFAULT_DUP_THRESHOLD))
    others = [e for e in query_entries(user_id) if e.get("entry_id") != entry_id]

    matches: list[dict] = []
    for item, score in rank_by_similarity(embedding, others):
        if score < threshold:
            break
        matches.append(
            {
                "entry_id": item.get("entry_id"),
                "entry_type": item.get("entry_type"),
                "title": item.get("title"),
                "similarity": round(score, 4),
            }
        )
    return matches


def _create(user_id: str, body: dict) -> dict:
    """Phase B confirm/persist with the ADR-033 duplicate check (Sections 3.1.3–3.1.5)."""
    # The ULID minted at propose_entry time (Section 3.1.4). Absent it — a direct API create with
    # no chat turn behind it — we mint one here, and the request is simply not retry-idempotent.
    entry_id = body.pop("entry_id", None) or new_ulid()
    # The client sets this to re-confirm past a 409 dup warning; pop before validation (the
    # discriminated union forbids extra fields).
    acknowledge_duplicate = bool(body.pop("acknowledge_duplicate", False))

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

    # Semantic dup check (ADR-033): reuses the embedding just computed — no extra Bedrock cost.
    # Skipped when the user has already acknowledged the warning and chosen "save anyway".
    if not acknowledge_duplicate:
        matches = _duplicate_matches(user_id, entry_id, embedding)
        if matches:
            logger.info("Possible duplicate at confirm", extra={"match_count": len(matches)})
            metrics.add_metric(name="EntryDuplicateSuspected", unit=MetricUnit.Count, value=1)
            return _response(
                409,
                {"message": "possible_duplicate", "entry_id": entry_id, "possible_duplicates": matches},
            )

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

    # The conditional failed, which now means exactly one thing: the entry already exists (the
    # SK-prefix invariant is enforced in code before the write). Re-read it so the duplicate
    # confirm returns the stored item rather than the one we just built.
    existing = get_entry(user_id, entry_id)
    if existing is None:
        # GetItem is eventually consistent by default, so a just-written item can briefly read
        # as absent. Rare, and a retry resolves it — 500 is the honest answer, not a fabricated 200.
        logger.error("Conditional put failed but entry read back absent")
        return _response(500, {"message": "Could not save entry — please retry."})

    metrics.add_metric(name="EntryDuplicateConfirm", unit=MetricUnit.Count, value=1)
    logger.info("Idempotent duplicate confirm; returning existing entry")
    return _response(200, {"entry": _public_entry(existing)})


def _list(user_id: str) -> dict:
    """Return all of a user's entries for the dashboard (AP-10). Sorting/grouping is client-side."""
    entries = [_public_entry(item) for item in query_entries(user_id)]
    metrics.add_metric(name="EntryList", unit=MetricUnit.Count, value=1)
    return _response(200, {"entries": entries})


def _update(user_id: str, entry_id: str, body: dict) -> dict:
    """Edit an entry (AP-5). Re-embeds only when the embedded text changed (ADR-024 note)."""
    existing = get_entry(user_id, entry_id)
    if existing is None:
        return _response(404, {"message": "Entry not found"})

    body.pop("entry_id", None)
    body.pop("acknowledge_duplicate", None)  # not meaningful on edit — ignore, don't 422

    try:
        entry = validate_entry(body)
    except ValidationError as exc:
        metrics.add_metric(name="EntryValidationFailure", unit=MetricUnit.Count, value=1)
        return _response(422, {"message": "Validation failed", "errors": _validation_errors(exc)})

    logger.append_keys(entry_id=entry_id, entry_type=entry.entry_type)

    new_text = embedding_input_text(entry)
    # Reconstruct the stored entry to compare embedded text. If it can't be reconstructed
    # (schema drift), the safe default is to re-embed rather than trust a stale vector.
    try:
        old_text: str | None = embedding_input_text(entry_from_item(from_ddb_numbers(existing)))
    except ValidationError:
        old_text = None

    if old_text is not None and old_text == new_text and existing.get("embedding"):
        embedding = from_ddb_numbers(existing["embedding"])
        embedding_model = existing.get("embedding_model") or os.environ["BEDROCK_TITAN_EMBED_MODEL_ID"]
        metrics.add_metric(name="EntryReembedSkipped", unit=MetricUnit.Count, value=1)
    else:
        try:
            embedding = bedrock_client.embed(new_text)
        except BedrockError:
            logger.exception("Titan embedding failed on edit")
            metrics.add_metric(name="EntryEmbeddingFailure", unit=MetricUnit.Count, value=1)
            return _response(500, {"message": "Could not save changes — please retry."})
        embedding_model = os.environ["BEDROCK_TITAN_EMBED_MODEL_ID"]

    item = to_entry_item(
        entry,
        user_id=user_id,
        entry_id=entry_id,
        embedding=embedding,
        embedding_model=embedding_model,
        created_at=existing.get("created_at"),  # preserve original creation time
        updated_at=utcnow_iso(),  # record the edit
    )

    if not put_entry_update(item):
        # Existed at read, gone at write — deleted between the two. Honest 404, not a resurrection.
        logger.warning("Entry vanished between read and update")
        return _response(404, {"message": "Entry not found"})

    metrics.add_metric(name="EntryUpdated", unit=MetricUnit.Count, value=1)
    logger.info("Entry updated")
    return _response(200, {"entry": _public_entry(item)})


def _delete(user_id: str, entry_id: str) -> dict:
    """Hard-delete an entry (AP-6 / ADR-027)."""
    if not delete_entry(user_id, entry_id):
        return _response(404, {"message": "Entry not found"})
    metrics.add_metric(name="EntryDeleted", unit=MetricUnit.Count, value=1)
    logger.info("Entry deleted", extra={"entry_id": entry_id})
    return _response(200, {"deleted": entry_id})


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

    method = (event.get("httpMethod") or "").upper()
    entry_id = (event.get("pathParameters") or {}).get("id")

    if method == "GET":
        return _list(user_id)

    if method == "DELETE":
        if not entry_id:
            return _response(400, {"message": "Missing entry id"})
        return _delete(user_id, entry_id)

    # POST and PUT carry a JSON body.
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"message": "Body must be valid JSON"})
    if not isinstance(body, dict):
        return _response(400, {"message": "Body must be a JSON object"})

    if method == "POST":
        return _create(user_id, body)

    if method == "PUT":
        if not entry_id:
            return _response(400, {"message": "Missing entry id"})
        return _update(user_id, entry_id, body)

    return _response(405, {"message": f"{method} not allowed"})
