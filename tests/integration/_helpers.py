"""Request/response helpers shared by the deployed-stack tiers (`cloud` and `bedrock`).

Importable from any tier because ``tests/integration`` lands on ``sys.path`` via its ``conftest.py``
— the same mechanism that makes ``tests/helpers.py`` reachable from ``tests/unit``.
"""

from __future__ import annotations

import json
import uuid

import pytest

#: Logical name -> deployed function name. Values not present here are passed through unchanged, so
#: a test may also name a function directly.
FUNCTIONS = {
    "career_crud": "careervault-career-crud-dev",
    "settings": "careervault-settings-dev",
    "checkin": "careervault-checkin-dev",
    "chat": "careervault-chat-dev",
    "resume_agent": "careervault-resume-agent-dev",
}


def invoke(lambda_client, function: str, event: dict) -> dict:
    """Invoke a deployed Lambda synchronously and return its parsed response.

    A function error (an unhandled exception in the handler) fails the test carrying the remote
    traceback, rather than surfacing as a confusing assertion against an error envelope that
    happens to be shaped like a payload.
    """
    response = lambda_client.invoke(
        FunctionName=FUNCTIONS.get(function, function),
        InvocationType="RequestResponse",
        Payload=json.dumps(event).encode(),
    )
    payload = json.loads(response["Payload"].read() or b"{}")

    if response.get("FunctionError"):
        pytest.fail(f"{function} raised {response['FunctionError']}: {payload}")

    return payload


def body_of(proxy_response: dict) -> dict:
    return json.loads(proxy_response.get("body") or "{}")


def api_event(
    *,
    method: str,
    user_id: str,
    body: dict | None = None,
    path_params: dict | None = None,
    email: str = "int-test@example.com",
) -> dict:
    """A REST API Gateway proxy event with Cognito authorizer claims already resolved.

    This is the shape API Gateway hands the Lambda *after* the JWT authorizer has run — precisely
    the boundary being stubbed. Everything downstream of it is real.
    """
    return {
        "httpMethod": method,
        "pathParameters": path_params,
        "requestContext": {
            "requestId": f"int-{uuid.uuid4().hex[:8]}",
            "authorizer": {"claims": {"sub": user_id, "email": email}},
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }
