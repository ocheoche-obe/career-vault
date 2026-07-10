"""Shared test utilities: handler loading, fake Lambda context, and Converse response builders.

The two Lambda handlers are both named ``handler.py``, so they are loaded by path under distinct
module names rather than imported — otherwise the second import would resolve to the first.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]


def load_handler(module_name: str, function_dir: str):
    """Load ``backend/functions/<function_dir>/handler.py`` under a unique module name."""
    path = _ROOT / "backend" / "functions" / function_dir / "handler.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeLambdaContext:
    """Minimal stand-in for the Lambda context object Powertools decorators introspect."""

    function_name = "test-function"
    memory_limit_in_mb = 512
    invoked_function_arn = "arn:aws:lambda:us-east-1:000000000000:function:test-function"
    aws_request_id = "test-request-id"

    def get_remaining_time_in_millis(self) -> int:  # pragma: no cover - trivial
        return 30_000


def api_event(body: Any = None, *, sub: str | None = "user-sub-1", email: str = "dev@example.com") -> dict:
    """Build a REST API Gateway proxy event with Cognito authorizer claims."""
    claims: dict[str, str] = {}
    if sub is not None:
        claims = {"sub": sub, "email": email}

    if body is None:
        raw_body = None
    elif isinstance(body, str):
        raw_body = body
    else:
        raw_body = json.dumps(body)

    return {
        "requestContext": {"requestId": "req-1", "authorizer": {"claims": claims}},
        "body": raw_body,
        "isBase64Encoded": False,
    }


def tool_use_response(name: str, tool_input: dict) -> dict:
    """A Converse response whose assistant turn calls ``name`` with ``tool_input``."""
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"toolUse": {"toolUseId": "tu-1", "name": name, "input": tool_input}}],
            }
        },
        "stopReason": "tool_use",
        "usage": {"inputTokens": 100, "outputTokens": 20},
    }


def text_response(text: str = "hello") -> dict:
    """A Converse response with no toolUse block — should never happen under toolChoice=any."""
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 5},
    }


def body_of(response: dict) -> dict:
    """Parse a Lambda proxy response body."""
    return json.loads(response["body"])
