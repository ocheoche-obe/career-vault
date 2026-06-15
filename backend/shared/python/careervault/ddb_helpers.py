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

import os
from typing import Any, Mapping

import boto3
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


def put_item_scoped(item: Mapping[str, Any], sk_prefix: str) -> None:
    """Write ``item`` with an SK-prefix invariant enforced as a conditional expression.

    Defense in depth (Section 4.2.4): even if upstream code constructed an SK outside the
    Lambda's allowed prefix, ``begins_with(SK, :prefix)`` rejects the write. ``item`` must
    already contain valid ``PK`` and ``SK`` attributes.
    """
    get_table().put_item(
        Item=dict(item),
        ConditionExpression="begins_with(SK, :prefix)",
        ExpressionAttributeValues={":prefix": sk_prefix},
    )


def get_profile(user_id: str) -> dict[str, Any] | None:
    """Fetch the singleton ``PROFILE`` item for a user (AP-1), or ``None`` if absent."""
    response = get_table().get_item(
        Key={"PK": pk_for_user(user_id), "SK": "PROFILE"}
    )
    return response.get("Item")
