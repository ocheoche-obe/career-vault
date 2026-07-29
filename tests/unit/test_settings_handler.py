"""Unit tests for settings_lambda — GET and the B-008 PUT.

DynamoDB is faked; no test reaches AWS.
"""

import json
import os

import pytest
from helpers import FakeLambdaContext, api_event, body_of, load_handler

settings = load_handler("settings_handler", "settings")


@pytest.fixture
def fake_ddb(monkeypatch):
    """Fake the PROFILE store: `stored` is the item, `writes` records each update's attributes."""
    state: dict = {"stored": None}
    writes: list[dict] = []

    def _get_profile(user_id):
        return state["stored"]

    def _update_profile(user_id, attributes):
        writes.append(attributes)
        item = dict(state["stored"] or {"PK": f"USER#{user_id}", "SK": "PROFILE"})
        for key, value in attributes.items():
            if value is None:
                item.pop(key, None)
            else:
                item[key] = value
        state["stored"] = item
        return item

    monkeypatch.setattr(settings, "get_profile", _get_profile)
    monkeypatch.setattr(settings, "update_profile", _update_profile)
    return {"state": state, "writes": writes}


# --- GET ------------------------------------------------------------------------------------


def test_get_returns_default_profile_when_none_stored(fake_ddb):
    body = body_of(settings.handler(api_event(method="GET"), FakeLambdaContext()))

    assert body["SK"] == "PROFILE"
    assert body["email"] == "dev@example.com"  # seeded from the JWT claim
    assert body["name"] is None  # B-008: the field now exists, unset


def test_get_returns_stored_profile(fake_ddb):
    fake_ddb["state"]["stored"] = {"PK": "USER#user-sub-1", "SK": "PROFILE", "name": "Ada Lovelace"}

    body = body_of(settings.handler(api_event(method="GET"), FakeLambdaContext()))

    assert body["name"] == "Ada Lovelace"


def test_cors_header_comes_from_the_environment(fake_ddb):
    """Regression for the slice-1 artifact B-008 surfaced: this handler ignored CORS_ALLOW_ORIGIN.

    Every other Lambda read the env var after ADR-034; this one kept a literal
    ``http://localhost:5173``, so ``/settings`` would have failed CORS from CloudFront the moment
    the UI called it — which the B-008 settings form is the first thing to do. conftest sets the
    env var to the deployed wildcard, so the old hardcoded literal fails this assertion.
    """
    response = settings.handler(api_event(method="GET"), FakeLambdaContext())

    assert response["headers"]["Access-Control-Allow-Origin"] == os.environ["CORS_ALLOW_ORIGIN"] == "*"


# --- PUT ------------------------------------------------------------------------------------


def test_put_creates_profile_with_identity_fields(fake_ddb):
    event = api_event({"name": "Ada Lovelace", "location": "London"}, method="PUT")

    body = body_of(settings.handler(event, FakeLambdaContext()))

    assert body["name"] == "Ada Lovelace"
    assert body["location"] == "London"
    # The whole point of B-008: a résumé header can now resolve to a real name.
    assert fake_ddb["state"]["stored"]["name"] == "Ada Lovelace"


def test_put_stamps_email_from_the_jwt_not_the_body(fake_ddb):
    settings.handler(api_event({"name": "Ada"}, method="PUT", email="real@claim.com"), FakeLambdaContext())

    assert fake_ddb["writes"][0]["email"] == "real@claim.com"


def test_put_rejects_an_email_supplied_in_the_body(fake_ddb):
    """Identity must trace to an authenticated claim, so a body `email` is refused, not ignored."""
    event = api_event({"name": "Ada", "email": "attacker@evil.com"}, method="PUT")

    response = settings.handler(event, FakeLambdaContext())

    assert response["statusCode"] == 400
    assert fake_ddb["writes"] == []  # nothing was written


def test_put_rejects_server_owned_keys(fake_ddb):
    for forbidden in ({"PK": "USER#someone-else"}, {"SK": "ENTRY#x"}, {"created_at": "1970-01-01"}):
        response = settings.handler(api_event(forbidden, method="PUT"), FakeLambdaContext())
        assert response["statusCode"] == 400, forbidden
    assert fake_ddb["writes"] == []


def test_put_is_a_partial_update(fake_ddb):
    """An omitted field keeps its stored value; only what was sent is written."""
    fake_ddb["state"]["stored"] = {"PK": "USER#user-sub-1", "SK": "PROFILE", "name": "Ada", "phone": "123"}

    settings.handler(api_event({"location": "London"}, method="PUT"), FakeLambdaContext())

    written = fake_ddb["writes"][0]
    assert "location" in written
    assert "name" not in written  # untouched, not overwritten with a default
    assert fake_ddb["state"]["stored"]["phone"] == "123"


def test_put_null_clears_a_field(fake_ddb):
    fake_ddb["state"]["stored"] = {"PK": "USER#user-sub-1", "SK": "PROFILE", "phone": "123"}

    settings.handler(api_event({"phone": None}, method="PUT"), FakeLambdaContext())

    assert fake_ddb["writes"][0]["phone"] is None
    assert "phone" not in fake_ddb["state"]["stored"]


def test_put_rejects_an_overlong_name(fake_ddb):
    response = settings.handler(api_event({"name": "x" * 200}, method="PUT"), FakeLambdaContext())

    assert response["statusCode"] == 400
    assert fake_ddb["writes"] == []


def test_put_rejects_malformed_json(fake_ddb):
    assert settings.handler(api_event("{not json", method="PUT"), FakeLambdaContext())["statusCode"] == 400


def test_put_rejects_a_non_object_body(fake_ddb):
    assert settings.handler(api_event(json.dumps([1, 2]), method="PUT"), FakeLambdaContext())["statusCode"] == 400


# --- slice 8: the nested `settings` object (FR-4.6, ADR-040) --------------------------------


def test_put_accepts_cadence_and_pause(fake_ddb):
    body = {"settings": {"checkin_cadence": "monthly", "checkin_paused": True}}

    response = settings.handler(api_event(body, method="PUT"), FakeLambdaContext())

    assert response["statusCode"] == 200
    assert fake_ddb["writes"][0]["settings"] == {"checkin_cadence": "monthly", "checkin_paused": True}


def test_put_sends_only_the_sub_field_that_changed(fake_ddb):
    """The B-014 property at the handler boundary.

    `exclude_unset` must reach *into* the nested model. If it did not, this write would carry
    `checkin_cadence: "weekly"` from the model default and silently reset a user on monthly.
    """
    settings.handler(api_event({"settings": {"checkin_paused": True}}, method="PUT"), FakeLambdaContext())

    assert fake_ddb["writes"][0]["settings"] == {"checkin_paused": True}


def test_put_rejects_an_unknown_cadence(fake_ddb):
    response = settings.handler(
        api_event({"settings": {"checkin_cadence": "hourly"}}, method="PUT"), FakeLambdaContext()
    )

    assert response["statusCode"] == 400
    assert fake_ddb["writes"] == []


def test_put_rejects_an_unknown_settings_sub_field(fake_ddb):
    response = settings.handler(
        api_event({"settings": {"send_at_midnight": True}}, method="PUT"), FakeLambdaContext()
    )

    assert response["statusCode"] == 400
    assert fake_ddb["writes"] == []


def test_put_rejects_a_null_settings_object(fake_ddb):
    """Clearing the whole object would drop cadence and pause together — the trap this route avoids."""
    response = settings.handler(api_event({"settings": None}, method="PUT"), FakeLambdaContext())

    assert response["statusCode"] == 400
    assert fake_ddb["writes"] == []


def test_put_rejects_server_owned_scheduling_state(fake_ddb):
    """A client that could postpone its own check-in could steer a scheduled job from a body."""
    for forbidden in (
        {"next_checkin_at": "2099-01-01T00:00:00Z"},
        {"last_checkin_sent_at": "1970-01-01T00:00:00Z"},
        {"bounce_count": 0},
    ):
        response = settings.handler(api_event(forbidden, method="PUT"), FakeLambdaContext())
        assert response["statusCode"] == 400, forbidden
    assert fake_ddb["writes"] == []


def test_put_accepts_the_aspirational_goal(fake_ddb):
    """Tier 2 of ADR-021 reads this; without the field it degrades to static for every user."""
    response = settings.handler(
        api_event({"aspirational_goal": "AWS Solutions Architect"}, method="PUT"), FakeLambdaContext()
    )

    assert response["statusCode"] == 200
    assert fake_ddb["writes"][0]["aspirational_goal"] == "AWS Solutions Architect"


def test_identity_and_settings_can_be_written_together(fake_ddb):
    body = {"name": "Ada Lovelace", "settings": {"checkin_cadence": "biweekly"}}

    settings.handler(api_event(body, method="PUT"), FakeLambdaContext())

    written = fake_ddb["writes"][0]
    assert written["name"] == "Ada Lovelace"
    assert written["settings"] == {"checkin_cadence": "biweekly"}


# --- routing / auth -------------------------------------------------------------------------


def test_missing_sub_claim_is_unauthorized(fake_ddb):
    assert settings.handler(api_event(method="GET", sub=None), FakeLambdaContext())["statusCode"] == 401


def test_unsupported_method_is_405(fake_ddb):
    assert settings.handler(api_event(method="DELETE"), FakeLambdaContext())["statusCode"] == 405
