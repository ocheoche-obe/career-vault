"""Tests for the test harness itself — module-loading isolation (B-017).

These exist because the harness has already produced one genuinely baffling failure: ``checkin`` and
``resume_agent`` both ship a ``rendering.py``, both export ``render_html``, and the two take
*different keyword arguments*. Under a shared ``sys.path`` a bare ``import rendering`` resolves to
whichever function directory landed first, so the loser does not fail at import — it fails later,
deep inside a call, with a ``TypeError`` about arguments that look correct at the call site. The
error names neither the collision nor the module it actually got.

That failure mode is invisible to every other test in the suite: each one passes in isolation, and
the breakage depends on collection order. So the invariants get pinned here directly.
"""

import os
import sys

import pytest
from helpers import _FUNCTIONS, _load_isolated, load_handler, load_sibling

# Both handlers read these at import time.
os.environ.setdefault("DATA_BUCKET_NAME", "careervault-data-test")
os.environ.setdefault("AWS_LAMBDA_FUNCTION_NAME", "careervault-resume-agent-test")
os.environ.setdefault("CHECKIN_SENDER_ADDRESS", "sender@example.com")
os.environ.setdefault("SES_CONFIGURATION_SET", "careervault-checkins-test")
os.environ.setdefault("APP_BASE_URL", "https://example.cloudfront.net")


def test_same_named_siblings_load_as_distinct_modules():
    """The B-017 collision itself: two ``rendering.py`` files must not shadow each other."""
    agent_rendering = load_sibling("iso_agent_rendering", "resume_agent", "rendering")
    checkin_rendering = load_sibling("iso_checkin_rendering", "checkin", "rendering")

    assert agent_rendering is not checkin_rendering
    assert agent_rendering.__file__ != checkin_rendering.__file__
    assert agent_rendering.__file__.endswith("resume_agent/rendering.py")
    assert checkin_rendering.__file__.endswith("checkin/rendering.py")

    # Both export render_html with incompatible signatures — the reason a collision surfaced as a
    # confusing TypeError rather than an ImportError. Pin that they resolve to the right one.
    assert "contact" in agent_rendering.render_html.__code__.co_varnames
    assert "dashboard_url" in checkin_rendering.render_html.__code__.co_varnames
    assert hasattr(agent_rendering, "render_pdf")
    assert hasattr(checkin_rendering, "render_text")


def test_each_handler_binds_its_own_renderer():
    """The live collision, end to end.

    ``resume_agent/handler.py`` and ``checkin/handler.py`` each do ``from rendering import
    render_html``. Loading both in one process is exactly the situation that used to hand the second
    one the first one's renderer. Assert each bound function came from its *own* directory.

    This is the test with teeth: it fails if the ``sys.modules`` eviction in ``_load_isolated`` is
    removed, because the second handler is then served the first ``rendering`` from cache regardless
    of what ``sys.path`` says.
    """
    agent_handler = load_handler("iso_agent_handler", "resume_agent")
    checkin_handler = load_handler("iso_checkin_handler", "checkin")

    agent_origin = agent_handler.render_html.__code__.co_filename
    checkin_origin = checkin_handler.render_html.__code__.co_filename

    assert agent_origin.endswith("resume_agent/rendering.py"), (
        f"resume_agent bound render_html from {agent_origin}"
    )
    assert checkin_origin.endswith("checkin/rendering.py"), (
        f"checkin bound render_html from {checkin_origin}"
    )


def test_load_leaves_no_bare_sibling_name_in_sys_modules():
    """A load must not publish ``rendering``/``qa`` under its bare name for the next caller."""
    load_handler("iso_leak_agent_handler", "resume_agent")
    load_handler("iso_leak_chat_handler", "chat")

    for bare in ("rendering", "agent", "qa", "extraction", "composer"):
        module = sys.modules.get(bare)
        if module is None:
            continue
        origin = getattr(module, "__file__", None) or ""
        assert not origin.startswith(str(_FUNCTIONS)), (
            f"{bare!r} leaked into sys.modules from {origin} — the next function to import that "
            "name would silently get this one"
        )


def test_load_leaves_sys_path_unchanged():
    before = list(sys.path)
    load_sibling("iso_chat_qa", "chat", "qa")
    assert sys.path == before


def test_uniquely_named_module_stays_importable():
    """The loaded module keeps its ``sys.modules`` entry — Pydantic/dataclass types need it.

    Eviction is scoped to *bare* sibling names. Dropping the uniquely-named module too would
    reintroduce the ``AttributeError: 'NoneType' object has no attribute '__dict__'`` that class
    construction at module scope raises when it cannot find its own defining module.
    """
    module = load_sibling("iso_unique_agent", "resume_agent", "agent")
    assert sys.modules.get("iso_unique_agent") is module


def test_failed_load_does_not_leave_a_half_built_module_registered(tmp_path):
    """An exception mid-exec must unregister, or the next import gets a partial module."""
    broken = tmp_path / "broken.py"
    broken.write_text("RAN = True\nraise RuntimeError('boom')\n")

    with pytest.raises(RuntimeError, match="boom"):
        _load_isolated("iso_broken_module", tmp_path, broken)

    assert "iso_broken_module" not in sys.modules
    assert str(tmp_path) not in sys.path
