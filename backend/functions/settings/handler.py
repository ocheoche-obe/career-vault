"""settings_lambda — profile/settings reads (and, later, writes).

First slice: a single ``GET /settings`` route. Extracts ``user_id`` from the Cognito-validated
JWT claims at handler entry (never from the body — Section 4.2.4), reads the PROFILE singleton
from DynamoDB, and returns it as JSON. If no profile exists yet, returns a coherent default so a
brand-new user gets a usable shape.

Smallest blast radius in the system by design (Section 4.2.3): the only DynamoDB actions its IAM
role grants are ``GetItem`` and ``UpdateItem`` on the PROFILE item.
"""

from __future__ import annotations

import json

from careervault.ddb_helpers import extract_user_id, get_profile
from careervault.observability import bind_request_context, logger, metrics, tracer
from careervault.pydantic_models.profile import default_profile

# CORS for the localhost Vite dev server (hosting deferred this slice). With Lambda proxy
# integration the function itself must echo the allow-origin header on real responses;
# API Gateway's CORS config only covers the OPTIONS preflight.
_CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "http://localhost:5173",
}


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": _CORS_HEADERS,
        "body": json.dumps(body),
    }


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

    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("claims", {})
    ) or {}

    item = get_profile(user_id)
    if item is None:
        logger.info("No PROFILE found; returning default profile")
        profile = default_profile(user_id, email=claims.get("email", ""))
        return _response(200, profile.model_dump())

    logger.info("Returning stored PROFILE")
    return _response(200, item)
