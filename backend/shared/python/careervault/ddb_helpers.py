"""DynamoDB access helpers for CareerVault.

Centralises the patterns the architecture doc commits to once so every Lambda enforces them
uniformly (Section 4.2.4):

- **Per-user PK isolation** — ``user_id`` is *always* taken from the Cognito-validated JWT
  claims, never from a request body (IDOR guard).
- **SK-prefix-scoped writes** — writes go through :func:`put_item_scoped`, which adds a
  ``begins_with(SK, <prefix>)`` belt-and-suspenders condition so a mis-constructed SK is
  rejected at the API rather than corrupting a sibling item collection.

Single-table design per ADR-005 / Section 2.4. Table name from the ``CAREERVAULT_TABLE_NAME``
env var; ``DDB_ENDPOINT_URL`` overrides the endpoint for DynamoDB Local during dev.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from ulid import ULID

# Module-level resource/table cache — boto3 clients are expensive to construct, and a warm
# Lambda container reuses them across invocations.
_table = None


def get_table():
    """Return the cached DynamoDB ``Table`` resource for ``CAREERVAULT_TABLE_NAME``."""
    global _table
    if _table is None:
        kwargs: dict[str, str] = {}
        endpoint = os.environ.get("DDB_ENDPOINT_URL")
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        resource = boto3.resource("dynamodb", **kwargs)
        _table = resource.Table(os.environ["CAREERVAULT_TABLE_NAME"])
    return _table


def new_ulid() -> str:
    """Mint a fresh ULID string (lexicographically sortable, time-ordered)."""
    return str(ULID())


def is_valid_ulid(value: Any) -> bool:
    """True if ``value`` is a well-formed ULID string (26 chars, Crockford base32).

    Client-supplied identifiers (``session_id``, ``client_message_id`` per ADR-032) are embedded
    in sort keys, so they must be validated as ULIDs before key construction — a raw string
    containing ``#`` would distort the SK structure (Section 4.2.4).
    """
    if not isinstance(value, str):
        return False
    try:
        ULID.from_str(value)
        return True
    except ValueError:
        return False


def extract_user_id(event: Mapping[str, Any]) -> str:
    """Extract the Cognito ``sub`` from a REST API Gateway proxy event's JWT claims.

    The ``sub`` is the canonical ``user_id`` throughout CareerVault (Section 2.4). It comes
    from ``requestContext.authorizer.claims`` — the claims block populated by API Gateway's
    Cognito authorizer *after* it has validated the token. Never read identity from the body.

    Raises:
        PermissionError: if no ``sub`` claim is present (treated as unauthenticated).
    """
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("claims", {})
    ) or {}
    user_id = claims.get("sub")
    if not user_id:
        raise PermissionError("No 'sub' claim found in request authorizer context")
    return user_id


def pk_for_user(user_id: str) -> str:
    """Construct the partition key for a user's item collection (``USER#<user_id>``)."""
    return f"USER#{user_id}"


def assert_sk_prefix(item: Mapping[str, Any], sk_prefix: str) -> None:
    """Enforce the SK-prefix invariant in application code (Section 4.2.4).

    **Why this is not a ``ConditionExpression``.** A DynamoDB condition is evaluated against the
    item *already stored* at the target key, not against the item being written. So
    ``begins_with(SK, :prefix)`` asks "does the **existing** item's SK start with the prefix?" —
    which is false for every create, since no item exists yet. Worse, the combination
    ``attribute_not_exists(SK) AND begins_with(SK, :prefix)`` is self-contradictory (the first
    clause requires the item to be absent, the second requires it to be present) and therefore
    fails unconditionally.

    DynamoDB simply offers no way to constrain the key you are about to write. IAM cannot do it
    either — ``dynamodb:LeadingKeys`` scopes the *partition* key only. So the invariant lives
    here, as a loud precondition, and the condition expressions are reserved for the one thing
    they can express: create-once idempotency.

    Raises:
        ValueError: if ``item``'s SK is missing or outside the caller's allowed prefix.
    """
    sk = item.get("SK", "")
    if not isinstance(sk, str) or not sk.startswith(sk_prefix):
        raise ValueError(f"SK {sk!r} is outside this caller's allowed prefix {sk_prefix!r}")


def put_item_scoped(item: Mapping[str, Any], sk_prefix: str) -> None:
    """Write ``item`` once, with its SK constrained to ``sk_prefix``.

    The prefix invariant is checked in code (see :func:`assert_sk_prefix`); the conditional
    write makes the operation create-only, so an unexpected key collision surfaces rather than
    silently overwriting.

    Floats are marshalled to ``Decimal`` on the way in — LLM tool inputs (persisted on CONVO
    messages as ``tool_calls``) can carry them, and the resource API rejects floats outright.
    """
    assert_sk_prefix(item, sk_prefix)
    get_table().put_item(
        Item=to_ddb_numbers(dict(item)),
        ConditionExpression="attribute_not_exists(SK)",
    )


def get_profile(user_id: str) -> dict[str, Any] | None:
    """Fetch the singleton ``PROFILE`` item for a user (AP-1), or ``None`` if absent."""
    response = get_table().get_item(
        Key={"PK": pk_for_user(user_id), "SK": "PROFILE"}
    )
    return response.get("Item")


def update_profile(user_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
    """Upsert user-editable attributes onto the PROFILE singleton (AP-2), returning the new item.

    An ``UpdateItem`` rather than a ``PutItem``, and that choice carries weight here:

    - It is **create-or-update in one call**. A brand-new user has no PROFILE item at all —
      ``settings_lambda``'s read path synthesises a default without persisting it — so the first
      write must create. ``UpdateItem`` does that without a separate existence check, and without
      the read-then-write race a check-then-put would open.
    - It is a **partial** write. The caller sends only the fields the user edited; everything else
      on the item (``settings`` sub-fields, ``created_at``, anything a later slice adds) is left
      untouched. A full-item ``PutItem`` here would silently drop attributes the caller did not
      know about — the opposite of what ``career_crud`` wants for entries, where the client
      genuinely submits the whole re-validated object (§2.5 AP-5).
    - ``created_at`` uses ``if_not_exists`` so it is stamped once, on create, and never moved by a
      later edit.

    The key is constructed here from ``user_id`` and the literal ``"PROFILE"`` sort key, so no
    caller can steer this write at another item — the same in-code enforcement the ``SK``-prefix
    helpers apply to entries and conversations (§4.2.4).

    ``None`` values mean *clear this attribute* and are compiled to ``REMOVE``; DynamoDB has no
    null-assignment that reads back as absent, so the two must be split into ``SET`` and
    ``REMOVE`` clauses.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    set_parts = ["#updated_at = :updated_at", "#created_at = if_not_exists(#created_at, :now)"]
    remove_parts: list[str] = []
    names: dict[str, str] = {"#updated_at": "updated_at", "#created_at": "created_at"}
    values: dict[str, Any] = {":updated_at": now, ":now": now}

    for index, (key, value) in enumerate(attributes.items()):
        placeholder = f"#f{index}"
        names[placeholder] = key
        if value is None:
            remove_parts.append(placeholder)
        else:
            set_parts.append(f"{placeholder} = :v{index}")
            values[f":v{index}"] = value

    expression = "SET " + ", ".join(set_parts)
    if remove_parts:
        expression += " REMOVE " + ", ".join(remove_parts)

    response = get_table().update_item(
        Key={"PK": pk_for_user(user_id), "SK": "PROFILE"},
        UpdateExpression=expression,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=to_ddb_numbers(values),
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes", {})


# ---------------------------------------------------------------------------
# Number marshalling
#
# The boto3 DynamoDB *resource* interface refuses Python floats (they can't round-trip
# exactly) and hands Decimals back on read. Embedding vectors are ~1024 floats, so both
# directions need a conversion — kept here rather than in each Lambda.
# ---------------------------------------------------------------------------

def to_ddb_numbers(value: Any) -> Any:
    """Recursively convert floats to ``Decimal`` so an item can be written by the resource API."""
    return json.loads(json.dumps(value), parse_float=Decimal)


def from_ddb_numbers(value: Any) -> Any:
    """Recursively convert ``Decimal`` back to ``int``/``float`` for JSON responses."""
    if isinstance(value, list):
        return [from_ddb_numbers(item) for item in value]
    if isinstance(value, dict):
        return {key: from_ddb_numbers(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        # Integral Decimals render as ints so `hours_per_week: 4` doesn't become `4.0`.
        return int(value) if value == value.to_integral_value() else float(value)
    return value


# ---------------------------------------------------------------------------
# Conversation messages — CONVO# prefix (chat_lambda only, Section 4.2.3)
# ---------------------------------------------------------------------------

#: Cap on how many prior messages are replayed into a Bedrock prompt. Bounds both the token
#: bill and the prompt size as a session grows (Section 3.1.1).
MAX_HISTORY_MESSAGES = 20


def put_conversation_message(message: Mapping[str, Any]) -> bool:
    """Persist a CONVO message exactly once. Returns ``True`` if created, ``False`` if it existed.

    The ``CONVO#`` prefix invariant is enforced in code by :func:`assert_sk_prefix`. The
    conditional write is what makes a retried chat turn idempotent (ADR-032): the client reuses
    its ``client_message_id`` on retry, the SK collides, and the caller treats ``False`` as
    "already durable — proceed" rather than an error. Same idiom as :func:`put_entry_conditional`.

    Raises:
        ValueError: if the item's SK is not a ``CONVO#`` key.
    """
    assert_sk_prefix(message, "CONVO#")
    try:
        get_table().put_item(
            Item=to_ddb_numbers(dict(message)),
            ConditionExpression="attribute_not_exists(SK)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def query_conversation(
    user_id: str, session_id: str, limit: int = MAX_HISTORY_MESSAGES
) -> list[dict[str, Any]]:
    """Return the most recent ``limit`` messages of a session, oldest-first (AP-12).

    Queries newest-first with a ``Limit`` and then reverses, so a long session replays its
    *latest* turns rather than its first ones — the opposite of what a naive forward scan
    with a limit would give you.
    """
    response = get_table().query(
        KeyConditionExpression=Key("PK").eq(pk_for_user(user_id))
        & Key("SK").begins_with(f"CONVO#{session_id}#"),
        ScanIndexForward=False,
        Limit=limit,
    )
    return list(reversed(response.get("Items", [])))


# ---------------------------------------------------------------------------
# Entries — ENTRY# prefix (career_crud only, Section 4.2.3)
# ---------------------------------------------------------------------------

def get_entry(user_id: str, entry_id: str) -> dict[str, Any] | None:
    """Fetch a single ENTRY item, or ``None`` if absent."""
    response = get_table().get_item(
        Key={"PK": pk_for_user(user_id), "SK": f"ENTRY#{entry_id}"}
    )
    return response.get("Item")


def put_entry_conditional(item: Mapping[str, Any]) -> bool:
    """Write an ENTRY item exactly once. Returns ``True`` if created, ``False`` if it existed.

    The ``ENTRY#`` prefix invariant is enforced in code by :func:`assert_sk_prefix` — a
    mis-constructed SK raises ``ValueError`` before any write is attempted, rather than
    corrupting a sibling item collection.

    ``attribute_not_exists(SK)`` is what makes the confirm idempotent (Section 3.1.4): a
    duplicate confirm — double click, network retry, browser back/forward — fails the condition
    rather than overwriting the entry, and the caller turns that into ``200 OK`` instead of
    ``201 Created``. Because the prefix is already guaranteed, a ``ConditionalCheckFailedException``
    here has exactly one meaning: the entry already exists.

    Raises:
        ValueError: if the item's SK is not an ``ENTRY#`` key.
    """
    assert_sk_prefix(item, "ENTRY#")
    try:
        get_table().put_item(
            Item=to_ddb_numbers(dict(item)),
            ConditionExpression="attribute_not_exists(SK)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def query_entries(user_id: str) -> list[dict[str, Any]]:
    """Return all of a user's ENTRY items (AP-10), following pagination to completion.

    Pagination is not optional here: each entry carries a ~1024-float Titan embedding stored as
    DynamoDB numbers (~20 KB/item), so a few dozen entries already exceed the 1 MB per-Query page
    limit. Stopping at the first page would silently drop entries from both the dashboard (AP-7/8)
    and the resume agent's similarity read (ADR-016) — a correctness bug, not a perf nicety.

    Items are returned in SK order (``ENTRY#<ulid>`` = creation order). Chronological/grouped
    presentation is a client-side re-sort per Section 2.5; callers that need similarity ranking
    use :mod:`careervault.similarity`.
    """
    table = get_table()
    key_condition = Key("PK").eq(pk_for_user(user_id)) & Key("SK").begins_with("ENTRY#")

    items: list[dict[str, Any]] = []
    start_key: dict | None = None
    while True:
        kwargs: dict[str, Any] = {"KeyConditionExpression": key_condition}
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
        start_key = response.get("LastEvaluatedKey")
        if not start_key:
            return items


def put_entry_update(item: Mapping[str, Any]) -> bool:
    """Overwrite an existing ENTRY item (AP-5). ``True`` if written, ``False`` if it was absent.

    An edit submits the *whole* re-validated entry, so the update is a full-item ``PutItem``
    guarded by ``attribute_exists(SK)`` rather than an ``UpdateItem`` with per-field SET/REMOVE
    expressions — the replace semantics match "the user rebuilt this entry", and there is no
    partial-update path to express. The condition makes the write reject (rather than resurrect)
    an entry deleted between the caller's read and this write: ``False`` maps to ``404``. Because
    the create path already guarantees the ``ENTRY#`` prefix, the same in-code assertion is the
    only thing standing between a mis-built SK and a sibling collection.

    Raises:
        ValueError: if the item's SK is not an ``ENTRY#`` key.
    """
    assert_sk_prefix(item, "ENTRY#")
    try:
        get_table().put_item(
            Item=to_ddb_numbers(dict(item)),
            ConditionExpression="attribute_exists(SK)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


# ---------------------------------------------------------------------------
# Resume run traces — RESUMERUN# prefix (resume_agent only, Section 3.2.5 / 4.2.3)
# ---------------------------------------------------------------------------

def create_resume_run(item: Mapping[str, Any]) -> None:
    """Create a RESUMERUN# item exactly once (the ``pending`` job record, ADR-037).

    Written through :func:`put_item_scoped`, so the ``RESUMERUN#`` prefix invariant (Section 4.2.4)
    is enforced in code and ``attribute_not_exists(SK)`` guarantees create-once — the ULID
    ``run_id`` makes a collision impossible in practice, so this is belt-and-suspenders.
    """
    put_item_scoped(item, "RESUMERUN#")


def finalize_resume_run(item: Mapping[str, Any]) -> None:
    """Overwrite the RESUMERUN# item when the async worker completes/fails (ADR-037 / §3.2.5).

    Unlike :func:`create_resume_run`, this is an unconditional full-item ``PutItem`` — the worker
    replaces the ``pending`` record with the terminal one (``completed``/``failed`` + trace, keys,
    tokens, cost). The prefix invariant is still asserted in code; there is no create-once condition
    because by definition the item already exists. TTL'd (30 days) via the caller's ``expires_at``
    epoch attribute, matching the table's TimeToLive configuration.
    """
    assert_sk_prefix(item, "RESUMERUN#")
    get_table().put_item(Item=to_ddb_numbers(dict(item)))


def get_resume_run(user_id: str, run_id: str) -> dict[str, Any] | None:
    """Fetch one RESUMERUN# job record for status polling (ADR-037), or ``None`` if absent."""
    response = get_table().get_item(
        Key={"PK": pk_for_user(user_id), "SK": f"RESUMERUN#{run_id}"}
    )
    return response.get("Item")


def delete_entry(user_id: str, entry_id: str) -> bool:
    """Hard-delete an ENTRY item (AP-6 / ADR-027). ``True`` if deleted, ``False`` if absent.

    Hard delete is irreversible by design (ADR-027 — the UI confirm is the safety net). The
    ``attribute_exists(SK)`` condition lets the caller distinguish "deleted" from "never existed"
    so a delete of an already-gone entry returns ``404`` rather than a misleading success.
    """
    try:
        get_table().delete_item(
            Key={"PK": pk_for_user(user_id), "SK": f"ENTRY#{entry_id}"},
            ConditionExpression="attribute_exists(SK)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
