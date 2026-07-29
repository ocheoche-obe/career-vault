"""Unit tests for checkin_lambda — the scheduled send loop (FR-4, §3.3, ADR-021/-039).

DynamoDB, Bedrock and SES are all faked; no test reaches AWS.

The properties worth pinning here are the ones a scheduled job cannot demonstrate at runtime: it
has no caller, so a broken ordering or a swallowed failure shows up only as an email that quietly
never arrived.
"""

import os
from datetime import datetime, timezone

import pytest
from helpers import FakeLambdaContext, load_handler

from careervault.pydantic_models.checkin import CheckinEmail

# Stand in for what the SAM template sets on this function.
os.environ.setdefault("CHECKIN_SENDER_ADDRESS", "sender@example.com")
os.environ.setdefault("SES_CONFIGURATION_SET", "careervault-checkins-test")
os.environ.setdefault("APP_BASE_URL", "https://example.cloudfront.net")

h = load_handler("checkin_handler", "checkin")


def profile(user="u1", **overrides):
    return {"PK": f"USER#{user}", "SK": "PROFILE", "email": f"{user}@example.com", **overrides}


def entry(title="Shipped the migration", event_date="2026-07-25", **overrides):
    return {
        "SK": "ENTRY#01J",
        "entry_type": "PROJECT",
        "title": title,
        "content": "Cut over the last service.",
        "event_date": event_date,
        **overrides,
    }


@pytest.fixture
def rig(monkeypatch):
    """Fake every boundary the handler touches, and record what it did in what order."""
    state = {
        "profiles": [profile()],
        "entries": [],
        "claim": True,
        "sends": [],
        "logs": [],
        "order": [],
        "email": CheckinEmail(
            subject="Anything to log?",
            greeting="Hi Ada,",
            prompts=["Did it ship?"],
            sign_off="See you next week.",
        ),
        "tier": "personalized",
    }

    def _claim(user_id, **kwargs):
        state["order"].append("claim")
        return state["claim"]

    def _send(**kwargs):
        state["order"].append("send")
        state["sends"].append(kwargs)
        return "ses-message-id-1"

    def _log(item):
        state["order"].append("log")
        state["logs"].append(item)

    monkeypatch.setattr(h, "scan_profiles", lambda: state["profiles"])
    monkeypatch.setattr(h, "query_entries", lambda user_id: state["entries"])
    monkeypatch.setattr(h, "claim_checkin_slot", _claim)
    monkeypatch.setattr(h, "put_checkin_log", _log)
    monkeypatch.setattr(h, "_send_email", _send)
    monkeypatch.setattr(h, "compose", lambda p, e: (state["email"], state["tier"]))
    return state


def run(rig):
    return h.handler({}, FakeLambdaContext())


# --- the happy path -------------------------------------------------------------------------


def test_a_due_user_gets_one_email_and_one_audit_row(rig):
    result = run(rig)

    assert result["due"] == 1
    assert result["outcomes"] == {"sent_personalized": 1}
    assert len(rig["sends"]) == 1
    assert rig["sends"][0]["to_address"] == "u1@example.com"
    assert len(rig["logs"]) == 1


def test_the_slot_is_claimed_before_ses_and_audited_after(rig):
    """The tempting order is wrong in both directions, so it is asserted rather than commented.

    Claim-then-send means a Scheduler retry loses the conditional write instead of the mailbox
    absorbing a duplicate. Audit-after-send means a CHECKINLOG row asserts "SES accepted this",
    not merely "we intended to".
    """
    run(rig)

    assert rig["order"] == ["claim", "send", "log"]


def test_the_audit_row_records_what_was_sent(rig):
    run(rig)
    log = rig["logs"][0]

    assert log["SK"].startswith("CHECKINLOG#")
    assert log["entity_type"] == "CHECKINLOG"
    assert log["ses_message_id"] == "ses-message-id-1"
    assert log["tier"] == "personalized"
    assert log["cadence"] == "weekly"


def test_both_email_bodies_are_sent(rig):
    """A multipart message with no text part is a well-known spam signal."""
    run(rig)
    sent = rig["sends"][0]

    assert "<html" in sent["html"].lower()
    assert "<html" not in sent["text"].lower()
    assert "Did it ship?" in sent["text"]


def test_the_email_links_back_to_the_app(rig):
    """FR-4.4."""
    run(rig)

    assert "https://example.cloudfront.net" in rig["sends"][0]["html"]
    assert "https://example.cloudfront.net" in rig["sends"][0]["text"]


# --- idempotency (§3.3.4) -------------------------------------------------------------------


def test_a_lost_slot_claim_sends_nothing(rig):
    """Scheduler is at-least-once; the retry must reach here and stop."""
    rig["claim"] = False

    result = run(rig)

    assert result["outcomes"] == {"skipped_idempotent": 1}
    assert rig["sends"] == []
    assert rig["logs"] == []


# --- due-ness gating ------------------------------------------------------------------------


def test_a_paused_user_is_not_sent_to(rig):
    """FR-4.6."""
    rig["profiles"] = [profile(settings={"checkin_paused": True})]

    result = run(rig)

    assert result["due"] == 0
    assert rig["sends"] == []


def test_a_user_not_yet_due_is_skipped(rig):
    rig["profiles"] = [profile(next_checkin_at="2099-01-01T00:00:00Z")]

    assert run(rig)["due"] == 0


def test_no_due_users_is_a_clean_exit_not_an_error(rig):
    """Most daily fires have nothing to do at a weekly cadence."""
    rig["profiles"] = []

    result = run(rig)

    assert result == {"run_id": result["run_id"], "scanned": 0, "due": 0, "outcomes": {}}


# --- failure isolation (§3.3.5) -------------------------------------------------------------


def test_one_users_failure_does_not_cost_the_others_their_checkin(rig):
    """The defining property of a batch job: no user may poison the run."""
    rig["profiles"] = [profile("u1"), profile("u2"), profile("u3")]
    sends: list[str] = []

    def _flaky(**kwargs):
        if kwargs["to_address"] == "u2@example.com":
            raise RuntimeError("SES rejected an unverified recipient")
        sends.append(kwargs["to_address"])
        return "mid"

    h._send_email = _flaky
    try:
        result = h.handler({}, FakeLambdaContext())
    finally:
        pass

    assert sends == ["u1@example.com", "u3@example.com"]
    assert result["outcomes"]["failed"] == 1
    assert result["outcomes"]["sent_personalized"] == 2


# --- the recency window ---------------------------------------------------------------------


def test_entries_outside_the_window_are_not_offered_to_the_model(rig, monkeypatch):
    """Weekly cadence looks back 14 days (double the window, §3.3.3)."""
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    rig["entries"] = [entry(event_date="2026-07-25"), entry(title="Old", event_date="2026-01-01")]

    recent = h._recent_entries("u1", "weekly", now)

    assert [e["event_date"] for e in recent] == ["2026-07-25"]


def test_recent_entries_come_back_newest_first(rig):
    """So the prompt cap keeps the most relevant entries, not the earliest-created ones."""
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    rig["entries"] = [
        entry(title="A", event_date="2026-07-20"),
        entry(title="C", event_date="2026-07-30"),
        entry(title="B", event_date="2026-07-25"),
    ]

    recent = h._recent_entries("u1", "weekly", now)

    assert [e["title"] for e in recent] == ["C", "B", "A"]


def test_the_entry_count_is_capped_regardless_of_the_window(rig):
    """ADR-021's structural cost guard: the prompt cannot grow with the corpus."""
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    rig["entries"] = [entry(title=f"E{i}", event_date="2026-07-30") for i in range(40)]

    assert len(h._recent_entries("u1", "weekly", now)) == 15
