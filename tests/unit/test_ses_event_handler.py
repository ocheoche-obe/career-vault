"""Unit tests for ses_event_handler — bounce/complaint recording (§4.5.3/4.5.4).

DynamoDB is faked; no test reaches AWS.

Real SES payload shapes are used rather than minimal stubs. The handler's whole job is reading a
payload shape it does not control, so a test built from a simplified guess at that shape would
verify the guess rather than the handler.
"""

import json

import pytest
from helpers import FakeLambdaContext, load_handler

h = load_handler("ses_event_handler", "ses_event_handler")

PROFILE = {"PK": "USER#u1", "SK": "PROFILE", "email": "ada@example.com"}


@pytest.fixture
def rig(monkeypatch):
    state = {"profiles": [PROFILE], "bounces": [], "complaints": []}

    def _bounce(user_id, at):
        state["bounces"].append((user_id, at))
        return {"bounce_count": len(state["bounces"])}

    def _complaint(user_id, at):
        state["complaints"].append((user_id, at))
        return {}

    monkeypatch.setattr(h, "scan_profiles", lambda: state["profiles"])
    monkeypatch.setattr(h, "record_bounce", _bounce)
    monkeypatch.setattr(h, "record_complaint", _complaint)
    return state


def sns_event(message: dict) -> dict:
    """SES publishes to SNS as a JSON *string* inside the record, not as a nested object."""
    return {"Records": [{"Sns": {"Message": json.dumps(message)}}]}


def bounce_message(email="ada@example.com", bounce_type="Permanent"):
    return {
        "eventType": "Bounce",
        "mail": {"timestamp": "2026-07-31T23:00:00.000Z", "destination": [email]},
        "bounce": {
            "bounceType": bounce_type,
            "bounceSubType": "General",
            "bouncedRecipients": [{"emailAddress": email}],
            "timestamp": "2026-07-31T23:00:05.000Z",
        },
    }


def complaint_message(email="ada@example.com"):
    return {
        "eventType": "Complaint",
        "mail": {"timestamp": "2026-07-31T23:00:00.000Z", "destination": [email]},
        "complaint": {
            "complainedRecipients": [{"emailAddress": email}],
            "timestamp": "2026-07-31T23:01:00.000Z",
        },
    }


# --- the two events -------------------------------------------------------------------------


def test_a_bounce_is_recorded_against_the_right_profile(rig):
    result = h.handler(sns_event(bounce_message()), FakeLambdaContext())

    assert result["processed"] == 1
    assert rig["bounces"] == [("u1", "2026-07-31T23:00:05.000Z")]
    assert rig["complaints"] == []


def test_a_complaint_is_recorded_against_the_right_profile(rig):
    h.handler(sns_event(complaint_message()), FakeLambdaContext())

    assert rig["complaints"] == [("u1", "2026-07-31T23:01:00.000Z")]
    assert rig["bounces"] == []


def test_recipient_matching_is_case_insensitive(rig):
    """SES echoes the envelope address, whose casing need not match what the user typed."""
    h.handler(sns_event(bounce_message(email="Ada@Example.COM")), FakeLambdaContext())

    assert rig["bounces"] == [("u1", "2026-07-31T23:00:05.000Z")]


def test_the_mailbox_simulator_does_not_match_a_real_user(rig):
    """Expected during smoke testing — the simulator addresses are not users."""
    h.handler(sns_event(bounce_message(email="bounce@simulator.amazonses.com")), FakeLambdaContext())

    assert rig["bounces"] == []


# --- payload robustness ---------------------------------------------------------------------


def test_the_legacy_notification_type_key_is_understood(rig):
    """SES emits `eventType` from a Configuration Set and `notificationType` from the older
    identity-notification path. Accepting both costs one `or`."""
    message = bounce_message()
    message["notificationType"] = message.pop("eventType")

    h.handler(sns_event(message), FakeLambdaContext())

    assert rig["bounces"] == [("u1", "2026-07-31T23:00:05.000Z")]


def test_recipients_fall_back_to_the_mail_destination(rig):
    """Some event shapes omit the per-recipient detail block."""
    message = bounce_message()
    message["bounce"].pop("bouncedRecipients")

    h.handler(sns_event(message), FakeLambdaContext())

    assert rig["bounces"] == [("u1", "2026-07-31T23:00:05.000Z")]


def test_an_unsubscribed_event_type_is_ignored(rig):
    """The Configuration Set subscribes to Bounce and Complaint only; anything else is a config
    change this handler was not told about."""
    h.handler(sns_event({"eventType": "Delivery", "mail": {"destination": ["ada@example.com"]}}), FakeLambdaContext())

    assert rig["bounces"] == []
    assert rig["complaints"] == []


def test_malformed_json_does_not_raise(rig):
    """Raising would make SNS redeliver a payload that will never parse."""
    result = h.handler({"Records": [{"Sns": {"Message": "{not json"}}]}, FakeLambdaContext())

    assert result["processed"] == 0


def test_one_bad_record_does_not_drop_the_others(rig):
    """A raise would redeliver the whole batch and re-count the records that already succeeded."""
    event = {
        "Records": [
            {"Sns": {"Message": json.dumps(bounce_message())}},
            {"Sns": {"Message": "{not json"}},
            {"Sns": {"Message": json.dumps(complaint_message())}},
        ]
    }

    result = h.handler(event, FakeLambdaContext())

    assert result["processed"] == 2
    assert len(rig["bounces"]) == 1
    assert len(rig["complaints"]) == 1


def test_an_empty_batch_is_a_clean_exit(rig):
    assert h.handler({"Records": []}, FakeLambdaContext()) == {"records": 0, "processed": 0}


# --- MVP scope ------------------------------------------------------------------------------


def test_a_bounce_does_not_auto_pause_checkins(rig):
    """§3.3.8: MVP records and alarms, it does not act. Auto-pause is the v1.1 hook, and the first
    thing it does when it misfires is silently stop a working feature."""
    for _ in range(5):
        h.handler(sns_event(bounce_message()), FakeLambdaContext())

    assert len(rig["bounces"]) == 5
    assert rig["profiles"][0].get("settings") is None
