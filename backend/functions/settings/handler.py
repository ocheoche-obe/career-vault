"""settings_lambda — profile/settings reads and writes.

Two routes:

- ``GET /settings`` — read the PROFILE singleton. If none exists, return a coherent default so a
  brand-new user gets a usable shape (the default is *not* persisted; the first explicit write is
  what creates the item).
- ``PUT /settings`` — partial update of the user-editable fields. Added for backlog **B-008**: the
  résumé identity header needs a `name`, and neither DynamoDB nor Cognito had anywhere to put one.

``user_id`` and ``email`` both come from the Cognito-validated JWT claims at handler entry, never
from the body (§4.2.4). That is why :class:`ProfileUpdate` forbids `email` outright rather than
ignoring it — the identity on a résumé should be traceable to an authenticated claim, not to
whatever a request body asserted.

Smallest blast radius in the system by design (§4.2.3): the only DynamoDB actions its IAM role
grants are ``GetItem`` and ``UpdateItem``, and both are constructed against the literal ``PROFILE``
sort key inside ``ddb_helpers``.
"""

from __future__ import annotations

import json
import os

from aws_lambda_powertools.metrics import MetricUnit
from pydantic import ValidationError

from careervault.ddb_helpers import extract_user_id, get_profile, update_profile
from careervault.observability import bind_request_context, logger, metrics, tracer
from careervault.pydantic_models.profile import ProfileUpdate, default_profile

# With Lambda proxy integration the function itself must echo the allow-origin header on real
# responses; API Gateway's CORS config only covers the OPTIONS preflight.
#
# This read the hard-coded string "http://localhost:5173" until B-008. That was a slice-1 artifact
# that ADR-034 (slice 4) fixed across every other Lambda and missed here — nothing in the UI called
# /settings yet, so the browser never got a chance to reject the mismatched origin. The settings
# form added for B-008 is exactly what would have surfaced it, from CloudFront, as an opaque CORS
# failure. The env var is set globally in the SAM template (`CORS_ALLOW_ORIGIN: "*"`, safe for a
# Bearer-token API with no cookies — ADR-034); the literal remains only as a local-dev fallback.
_CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "http://localhost:5173"),
}

_MAX_BODY_BYTES = 16_000


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": _CORS_HEADERS,
        "body": json.dumps(body),
    }


def _claims(event: dict) -> dict:
    return (event.get("requestContext", {}).get("authorizer", {}).get("claims", {})) or {}


def _get(user_id: str, event: dict) -> dict:
    item = get_profile(user_id)
    if item is None:
        logger.info("No PROFILE found; returning default profile")
        return _response(200, default_profile(user_id, email=_claims(event).get("email", "")).model_dump())

    logger.info("Returning stored PROFILE")
    return _response(200, item)


def _put(user_id: str, event: dict) -> dict:
    raw = event.get("body") or "{}"
    if len(raw) > _MAX_BODY_BYTES:
        return _response(413, {"message": "Settings payload too large"})

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return _response(400, {"message": "Body must be valid JSON"})
    if not isinstance(payload, dict):
        return _response(400, {"message": "Body must be a JSON object"})

    try:
        update = ProfileUpdate.model_validate(payload)
    except ValidationError as exc:
        # `extra="forbid"` means a body carrying PK/email/created_at lands here rather than being
        # silently dropped — the caller finds out that the write it thought it made did not happen.
        return _response(
            400,
            {
                "message": "Invalid settings payload",
                "errors": [
                    {"field": ".".join(str(p) for p in e["loc"]), "error": e["msg"]}
                    for e in exc.errors()
                ],
            },
        )

    # Only fields the caller actually sent. `exclude_unset` is what makes this a *partial* update:
    # an omitted field keeps its stored value, while an explicit `null` clears it.
    attributes = update.model_dump(mode="json", exclude_unset=True)

    # The JWT is the sole source of `email`. Stamped on every write so a PROFILE created by this
    # route is never missing the identity the résumé header falls back to.
    email = _claims(event).get("email")
    if email:
        attributes["email"] = email

    if not attributes:
        return _response(400, {"message": "No settings fields supplied"})

    item = update_profile(user_id, attributes)
    logger.info("PROFILE updated", extra={"fields": sorted(attributes)})
    metrics.add_metric(name="SettingsUpdated", unit=MetricUnit.Count, value=1)
    return _response(200, item)


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

    method = (event.get("httpMethod") or "GET").upper()
    if method == "GET":
        return _get(user_id, event)
    if method == "PUT":
        return _put(user_id, event)
    return _response(405, {"message": f"Method {method} not allowed on /settings"})
