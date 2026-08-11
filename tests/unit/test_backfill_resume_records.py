"""Unit tests for the one-time RESUME# backfill (ADR-046).

A migration script is exactly the kind of code that gets written once, run against real data, and
never reviewed again — so its mapping is pinned here rather than trusted. These tests cover the
decisions that would corrupt or lose data if wrong: which traces are eligible, that the record it
builds is durable, and that its title rule has not drifted from the handler's.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill-resume-records.py"
_spec = importlib.util.spec_from_file_location("backfill_resume_records", _SCRIPT)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


def _trace(**over):
    trace = {
        "PK": "USER#u",
        "SK": "RESUMERUN#01JRUN",
        "run_id": "01JRUN",
        "status": "completed",
        "created_at": "2026-07-28T15:33:16Z",
        "target_text": "Anthropic\nSolutions Architect, applied AI.",
        "html_key": "resumes/u/01JRUN/resume.html",
        "pdf_key": "resumes/u/01JRUN/resume.pdf",
        "retrieved_ids": ["E1", "E2", "E3"],
        "document": {"summary": "Strong engineer."},
        "critique_verdict": "PASS",
        "expires_at": 1234567890,
    }
    trace.update(over)
    return trace


def test_a_completed_trace_maps_to_a_durable_record():
    record = backfill.record_from_trace(_trace())

    assert record["SK"] == "RESUME#01JRUN"
    assert record["entity_type"] == "RESUME"
    assert record["status"] == "completed"
    assert record["target_title"] == "Anthropic"
    assert record["entry_count"] == 3
    assert record["document"]["summary"] == "Strong engineer."


def test_the_backfilled_record_does_not_inherit_the_traces_ttl():
    """The one mistake that would silently undo the whole migration."""
    record = backfill.record_from_trace(_trace())
    assert "expires_at" not in record


def test_elapsed_time_is_left_absent_rather_than_invented():
    """These runs predate the measurement; a number here would be fabricated (B-015's precedent)."""
    assert "elapsed_seconds" not in backfill.record_from_trace(_trace())


def test_decimals_read_back_from_dynamodb_survive_the_round_trip():
    """The failure that actually happened on the first apply.

    DynamoDB returns every number as `Decimal`, and the write helper marshals items through
    `json.dumps`, which cannot serialise one — so the mapping has to invert before it re-writes.
    The Lambda never hits this because its items are built from Pydantic floats; only something
    that *reads* the table before writing to it does.
    """
    from decimal import Decimal

    record = backfill.record_from_trace(
        _trace(cumulative_cost_usd=Decimal("0.31"), cumulative_tokens=Decimal("70123"))
    )

    assert record["cumulative_cost_usd"] == 0.31
    assert record["cumulative_tokens"] == 70123
    assert not isinstance(record["cumulative_tokens"], Decimal)
    # The real proof: the write helper can now serialise it.
    from careervault.ddb_helpers import to_ddb_numbers

    to_ddb_numbers(record)


@pytest.mark.parametrize("status", ["failed", "pending"])
def test_only_completed_runs_become_history(status):
    assert backfill.record_from_trace(_trace(status=status)) is None


@pytest.mark.parametrize("missing", ["html_key", "pdf_key"])
def test_a_run_without_artifacts_is_skipped(missing):
    """A record whose View and Download both 404 is worse than no record at all."""
    assert backfill.record_from_trace(_trace(**{missing: None})) is None


def test_title_matches_the_handlers_rule():
    """The script re-implements `_target_title`; this is what keeps the two from drifting apart."""
    import os

    os.environ.setdefault("DATA_BUCKET_NAME", "careervault-data-test")
    from helpers import load_handler

    handler = load_handler("resume_agent_handler_for_backfill", "resume_agent")

    assert backfill.TARGET_TITLE_CHARS == handler._TARGET_TITLE_CHARS
    for target in ["Anthropic\nSolutions Architect", "\n\n  Staff SRE  \n", "x" * 400, ""]:
        assert backfill.target_title(target) == handler._target_title(target)
