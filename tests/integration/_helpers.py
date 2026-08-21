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


#: Parsed from the Lambda REPORT line. ``init_ms`` is present only on a cold start, which is what
#: makes it the authoritative cold/warm signal — far better than inferring one from wall-clock time,
#: which also contains the caller's DNS, TLS and credential-resolution costs.
class Report(dict):
    """``{"duration_ms": float, "billed_ms": float, "init_ms": float | None}``."""

    @property
    def cold(self) -> bool:
        return self.get("init_ms") is not None


def invoke_timed(lambda_client, function: str, event: dict) -> tuple[dict, Report]:
    """Invoke as :func:`invoke` does, but also return what the Lambda says about itself.

    ``LogType="Tail"`` makes Lambda return the last 4 KB of the invocation log base64-encoded, whose
    final REPORT line carries ``Duration``, ``Billed Duration`` and — **only on a cold start** —
    ``Init Duration``. Reading that is the difference between measuring the Lambda and measuring the
    round trip to it: the first call from a fresh test process also pays for boto3 client
    construction, SSO credential resolution, DNS and a TLS handshake, none of which the app's users
    experience per request and none of which a wall-clock number separates out.
    """
    import base64
    import re

    response = lambda_client.invoke(
        FunctionName=FUNCTIONS.get(function, function),
        InvocationType="RequestResponse",
        LogType="Tail",
        Payload=json.dumps(event).encode(),
    )
    payload = json.loads(response["Payload"].read() or b"{}")

    if response.get("FunctionError"):
        pytest.fail(f"{function} raised {response['FunctionError']}: {payload}")

    log = base64.b64decode(response.get("LogResult", "")).decode("utf-8", errors="replace")

    def number(label: str) -> float | None:
        match = re.search(rf"{label}: ([\d.]+) ms", log)
        return float(match.group(1)) if match else None

    return payload, Report(
        duration_ms=number("\tDuration"),
        billed_ms=number("Billed Duration"),
        init_ms=number("Init Duration"),
    )


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


def seed_entries(live_table, user_id: str, count: int, *, dims: int = 1024) -> list[str]:
    """Write ``count`` realistic ENTRY items straight to the table, bypassing ``career_crud``.

    Bypassing the API is the point, not a shortcut. Creating entries through ``POST /entries`` runs
    a real Titan embed per entry (ADR-024) — slow, and a cost nobody needs in order to make a *read*
    path heavy. What NFR-2.3 turns on is that each stored item carries a full ~1024-float vector,
    since that is what B-013 identifies as dominating the read: ``query_entries`` fetches every
    vector and the handler then strips them before responding.

    Returns the generated entry ids, oldest first.
    """
    import random

    from careervault.ddb_helpers import new_ulid, to_ddb_numbers

    rng = random.Random(f"careervault-latency-{user_id}")
    entry_ids = []

    with live_table.batch_writer() as batch:
        for index in range(count):
            entry_id = new_ulid()
            entry_ids.append(entry_id)
            batch.put_item(
                Item=to_ddb_numbers(
                    {
                        "PK": f"USER#{user_id}",
                        "SK": f"ENTRY#{entry_id}",
                        "entity_type": "ENTRY",
                        "entry_id": entry_id,
                        "entry_type": "CERT",
                        "title": f"Synthetic certification {index + 1}",
                        "content": (
                            f"Seeded latency-test entry {index + 1}. Realistic prose so the item "
                            "carries a plausible payload alongside its vector."
                        ),
                        "issuer": "CareerVault Latency Harness",
                        "event_date": f"2025-{(index % 12) + 1:02d}-15",
                        "embedding": [rng.uniform(-1.0, 1.0) for _ in range(dims)],
                        "embedding_model": "seeded-not-a-real-model",
                        "created_at": f"2025-{(index % 12) + 1:02d}-15T12:00:00Z",
                        "updated_at": f"2025-{(index % 12) + 1:02d}-15T12:00:00Z",
                    }
                )
            )

    return entry_ids
