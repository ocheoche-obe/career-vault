"""Shared test utilities: handler loading, fake Lambda context, and Converse response builders.

Every Lambda handler is named ``handler.py``, so they are loaded by path under distinct module
names rather than imported — otherwise the second import would resolve to the first.

The same collision applies to their *sibling* modules, which is subtler and bites harder. In Lambda
each function is its own deployment package, so ``rendering.py`` unambiguously means "the one next
to me". Under pytest all the function directories are visible at once, and a bare
``from rendering import ...`` resolves to whichever directory reached ``sys.path`` first — so
``resume_agent`` importing ``render_pdf`` can land in ``checkin``'s renderer and fail with a
genuinely baffling error. :func:`load_handler` therefore isolates each load, rather than leaving
callers to avoid ever reusing a filename.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_FUNCTIONS = _ROOT / "backend" / "functions"


def load_handler(module_name: str, function_dir: str):
    """Load ``backend/functions/<function_dir>/handler.py`` under a unique module name.

    The function's own directory is placed first on ``sys.path`` for the duration of the load and
    removed afterwards, and any module it imported from there is evicted from ``sys.modules`` on
    the way out. Both halves are needed: the path entry makes ``from rendering import ...`` find
    the *right* sibling, and the eviction stops that sibling from being served, from cache, to the
    next function that asks for the same name.
    """
    function_root = _FUNCTIONS / function_dir
    path = function_root / "handler.py"

    before = set(sys.modules)
    sys.path.insert(0, str(function_root))
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(function_root))
        except ValueError:  # pragma: no cover - only if a test mutated sys.path mid-load
            pass
        for name in set(sys.modules) - before:
            origin = getattr(sys.modules[name], "__file__", None) or ""
            if origin.startswith(str(function_root)):
                del sys.modules[name]

    return module


class FakeLambdaContext:
    """Minimal stand-in for the Lambda context object Powertools decorators introspect."""

    function_name = "test-function"
    memory_limit_in_mb = 512
    invoked_function_arn = "arn:aws:lambda:us-east-1:000000000000:function:test-function"
    aws_request_id = "test-request-id"

    def get_remaining_time_in_millis(self) -> int:  # pragma: no cover - trivial
        return 30_000


def api_event(
    body: Any = None,
    *,
    sub: str | None = "user-sub-1",
    email: str = "dev@example.com",
    method: str = "POST",
    path_params: dict | None = None,
) -> dict:
    """Build a REST API Gateway proxy event with Cognito authorizer claims.

    ``method`` defaults to ``POST`` (the original single-route shape); pass ``GET``/``PUT``/
    ``DELETE`` and ``path_params={"id": ...}`` to exercise the slice-3 entry CRUD routes.
    """
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
        "httpMethod": method,
        "pathParameters": path_params,
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
