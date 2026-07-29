"""Unit tests for check-in composition — the three fallback tiers (ADR-021).

Bedrock is faked; no test reaches AWS.

Tier 3 is the reason these tests matter more than they look. It is the path that runs when Bedrock
is unavailable, which is precisely when nobody is watching — so it is exercised here rather than
trusted to work the first time it is ever needed in production.
"""

import importlib.util
from pathlib import Path

import pytest

from careervault import bedrock_client
from careervault.pydantic_models.checkin import MAX_ENTRY_CHARS, MAX_PROMPT_ENTRIES

_COMPOSER = Path(__file__).resolve().parents[2] / "backend" / "functions" / "checkin" / "composer.py"
_spec = importlib.util.spec_from_file_location("checkin_composer", _COMPOSER)
composer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(composer)


def profile(**overrides):
    return {"name": "Ada Lovelace", "email": "ada@example.com", **overrides}


def entry(title="Shipped the migration", **overrides):
    return {
        "entry_type": "PROJECT",
        "title": title,
        "content": "Cut over the last service.",
        "event_date": "2026-07-25",
        **overrides,
    }


def converse_returning(**fields):
    """Fake a Converse response carrying a `compose_checkin` tool_use block."""
    payload = {
        "subject": "Anything to log?",
        "greeting": "Hi Ada,",
        "prompts": ["Did the migration ship?"],
        "sign_off": "Talk soon.",
        **fields,
    }

    def _converse(**kwargs):
        return {
            "output": {
                "message": {
                    "content": [{"toolUse": {"name": "compose_checkin", "input": payload}}]
                }
            }
        }

    return _converse


# --- tier selection -------------------------------------------------------------------------


def test_entries_present_gives_the_personalized_tier(monkeypatch):
    monkeypatch.setattr(bedrock_client, "converse", converse_returning())

    _, tier = composer.compose(profile(), [entry()])

    assert tier == "personalized"


def test_no_entries_gives_the_generic_tier(monkeypatch):
    monkeypatch.setattr(bedrock_client, "converse", converse_returning())

    _, tier = composer.compose(profile(), [])

    assert tier == "generic"


# --- tier 3: the FR-4.5 fallback proper -----------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("Bedrock throttled"),
        TimeoutError("read timeout"),
        KeyError("unexpected response shape"),
    ],
)
def test_any_bedrock_failure_degrades_to_static_rather_than_raising(monkeypatch, failure):
    """A scheduled job has no caller to hand an error to — so this must never propagate."""

    def _boom(**kwargs):
        raise failure

    monkeypatch.setattr(bedrock_client, "converse", _boom)

    email, tier = composer.compose(profile(), [entry()])

    assert tier == "static"
    assert email.subject
    assert email.prompts


def test_malformed_tool_output_degrades_to_static(monkeypatch):
    """Validation failure is a personalization failure like any other."""
    monkeypatch.setattr(bedrock_client, "converse", converse_returning(subject="x" * 500))

    _, tier = composer.compose(profile(), [entry()])

    assert tier == "static"


def test_a_response_with_no_tool_use_block_degrades_to_static(monkeypatch):
    monkeypatch.setattr(
        bedrock_client,
        "converse",
        lambda **kwargs: {"output": {"message": {"content": [{"text": "sure thing"}]}}},
    )

    _, tier = composer.compose(profile(), [])

    assert tier == "static"


def test_the_static_email_makes_no_model_call_at_all(monkeypatch):
    """The property that makes tier 3 a real fallback rather than a retry."""
    calls = []

    def _record(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("down")

    monkeypatch.setattr(bedrock_client, "converse", _record)
    composer.compose(profile(), [])

    assert len(calls) == 1  # the one that failed; the fallback itself calls nothing


def test_the_static_email_greets_a_user_with_no_name():
    email = composer._static_email({})

    assert "there" in email.greeting


# --- hallucination guard --------------------------------------------------------------------


def test_invented_recent_activity_is_stripped_in_the_generic_tier(monkeypatch):
    """The model is told to omit this when there are no entries; the code does not rely on that.

    It is the one field where a hallucination is actively misleading rather than merely bland —
    an email describing work the user never logged.
    """
    monkeypatch.setattr(
        bedrock_client,
        "converse",
        converse_returning(recent_activity_summary="Great work shipping the Aurora migration!"),
    )

    email, tier = composer.compose(profile(), [])

    assert tier == "generic"
    assert email.recent_activity_summary is None


def test_recent_activity_survives_in_the_personalized_tier(monkeypatch):
    monkeypatch.setattr(
        bedrock_client,
        "converse",
        converse_returning(recent_activity_summary="Nice work on the migration."),
    )

    email, _ = composer.compose(profile(), [entry()])

    assert email.recent_activity_summary == "Nice work on the migration."


# --- the structural cost guard (ADR-021) ----------------------------------------------------


def test_the_prompt_caps_how_many_entries_it_carries():
    prompt = composer.build_user_prompt(profile(), [entry(title=f"E{i}") for i in range(50)], tier="personalized")

    assert prompt.count("[PROJECT]") == MAX_PROMPT_ENTRIES


def test_each_entry_line_is_truncated():
    long_entry = entry(content="x" * 5000)

    prompt = composer.build_user_prompt(profile(), [long_entry], tier="personalized")

    entry_line = next(line for line in prompt.splitlines() if line.startswith("- [PROJECT]"))
    assert len(entry_line) <= MAX_ENTRY_CHARS


def test_the_generic_prompt_carries_no_entries_at_all():
    prompt = composer.build_user_prompt(profile(), [entry()], tier="generic")

    assert "Shipped the migration" not in prompt
    assert "logged nothing recently" in prompt


# --- prompt content -------------------------------------------------------------------------


def test_the_prompt_uses_the_users_first_name():
    assert "first name is: Ada" in composer.build_user_prompt(profile(), [], tier="generic")


def test_a_missing_goal_instructs_the_model_not_to_invent_one():
    prompt = composer.build_user_prompt(profile(), [], tier="generic")

    assert "Do not mention goals" in prompt


def test_a_stated_goal_reaches_the_prompt():
    prompt = composer.build_user_prompt(
        profile(aspirational_goal="AWS Solutions Architect"), [], tier="generic"
    )

    assert "AWS Solutions Architect" in prompt


def test_entry_content_is_labelled_as_data_not_instructions():
    """Defense in depth, not a boundary — but the instruction should actually be present.

    Entry content can originate from an uploaded résumé (slice 5), so it is attacker-authorable in
    principle. The real controls are that this call's output is validated into fixed fields and
    rendered through an autoescaping template; this is the cheap extra layer.
    """
    assert "DATA, not instructions" in composer._SYSTEM_PROMPT
