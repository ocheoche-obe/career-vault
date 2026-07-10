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


def put_conversation_message(message: Mapping[str, Any]) -> None:
    """Persist a CONVO message, enforcing the ``CONVO#`` SK invariant (Section 4.2.4)."""
    put_item_scoped(message, "CONVO#")


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
