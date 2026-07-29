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


def _load_isolated(module_name: str, function_root: Path, path: Path):
    """Execute ``path`` as ``module_name`` with ``function_root`` temporarily first on ``sys.path``.

    The path entry makes a bare ``from rendering import ...`` inside the loaded module find the
    *right* sibling; removing it afterwards, and evicting anything the load pulled in from that
    directory, stops that sibling from being served from cache to the next function that asks for
    the same name. Both halves are needed — a path entry alone still leaves a poisoned
    ``sys.modules``.
    """
    before = set(sys.modules)
    sys.path.insert(0, str(function_root))
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        # Register *before* executing. Class construction at module scope — Pydantic models and
        # dataclasses — resolves its own defining module via ``sys.modules[cls.__module__]`` to
        # reach the enclosing namespace; if the module is not there yet that lookup yields ``None``
        # and the class body dies with a bare ``AttributeError: 'NoneType' object has no attribute
        # '__dict__'``, which points nowhere near the real cause. Handlers happen not to declare
        # such types at module level, which is why ``load_handler`` never needed this.
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
    finally:
        try:
            sys.path.remove(str(function_root))
        except ValueError:  # pragma: no cover - only if a test mutated sys.path mid-load
            pass
        # Evict anything the load pulled in from this function's directory *under its bare name* —
        # that is what would otherwise be served from cache to the next function asking for
        # ``rendering``. ``module_name`` itself is deliberately kept: it is unique by construction,
        # so it cannot collide, and the types created above need it to stay reachable.
        for name in set(sys.modules) - before - {module_name}:
            origin = getattr(sys.modules[name], "__file__", None) or ""
            if origin.startswith(str(function_root)):
                del sys.modules[name]

    return module


def load_handler(module_name: str, function_dir: str):
    """Load ``backend/functions/<function_dir>/handler.py`` under a unique module name."""
    function_root = _FUNCTIONS / function_dir
    return _load_isolated(module_name, function_root, function_root / "handler.py")


def load_sibling(module_name: str, function_dir: str, sibling: str):
    """Load ``backend/functions/<function_dir>/<sibling>.py`` under a unique module name.

    The counterpart to :func:`load_handler` for tests that exercise a non-handler module directly
    (``agent``, ``qa``, ``rendering``, ``extraction``). Importing those with a bare ``import
    rendering`` after a *permanent* ``sys.path.insert`` — the shape these tests used to have — makes
    the resolution order-dependent: whichever function directory reached ``sys.path`` first wins, so
    ``resume_agent``'s renderer and ``checkin``'s renderer resolve to the same name and the loser
    fails somewhere unrelated. Loading by explicit path removes the ambiguity entirely rather than
    relying on nobody ever reusing a filename.
    """
    function_root = _FUNCTIONS / function_dir
    return _load_isolated(module_name, function_root, function_root / f"{sibling}.py")


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
