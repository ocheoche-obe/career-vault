"""Unit tests for the check-in scheduling arithmetic (ADR-039).

Pure functions, no AWS, no mocks — which is the point of extracting them. A scheduled job's bugs
surface as an email that silently did not arrive days later, so the due-ness rules are the part of
this slice most worth pinning exhaustively.
"""

from datetime import datetime, timedelta, timezone

import pytest

from careervault.checkin_schedule import (
    advance,
    cadence_of,
    is_due,
    is_paused,
    parse_iso,
    recent_window_start,
    settings_of,
    utcnow_iso,
)

NOW = datetime(2026, 7, 31, 23, 0, 0, tzinfo=timezone.utc)


def profile(**overrides):
    """A minimally valid PROFILE — email present, since `is_due` requires one."""
    return {"PK": "USER#u1", "SK": "PROFILE", "email": "user@example.com", **overrides}


# --- timestamp formatting -------------------------------------------------------------------


def test_utcnow_iso_uses_z_suffix_not_offset():
    """Load-bearing, not cosmetic: `claim_checkin_slot` compares these with DynamoDB's `<`.

    String comparison is lexicographic, and "2026-07-31T23:00:00+00:00" sorts *after*
    "2026-07-31T23:00:00Z" for the same instant ('+' < 'Z' is false — '+' is 0x2B, 'Z' is 0x5A).
    Mixing the two formats would silently break the idempotency condition, so the format is
    asserted rather than assumed.
    """
    assert utcnow_iso(NOW) == "2026-07-31T23:00:00Z"


def test_utcnow_iso_normalises_a_non_utc_datetime():
    aware = datetime(2026, 7, 31, 16, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
    assert utcnow_iso(aware) == "2026-07-31T23:00:00Z"


@pytest.mark.parametrize("value", ["", None, "not-a-date", 12345, "2026-13-45T99:00:00Z"])
def test_parse_iso_returns_none_for_unusable_values(value):
    """Tolerant by design: one malformed attribute must not stop the run for every other user."""
    assert parse_iso(value) is None


def test_parse_iso_assumes_utc_for_a_naive_timestamp():
    assert parse_iso("2026-07-31T23:00:00") == NOW


# --- settings defaulting --------------------------------------------------------------------


def test_settings_absent_entirely_is_the_normal_case():
    """No PROFILE in the live table has a `settings` attribute — this is the inherited state."""
    assert settings_of(profile()) == {}
    assert cadence_of(profile()) == "weekly"
    assert is_paused(profile()) is False


def test_unrecognised_cadence_falls_back_to_weekly():
    assert cadence_of(profile(settings={"checkin_cadence": "fortnightly"})) == "weekly"


def test_only_a_real_boolean_pauses():
    """Failure direction matters: an unexpected value must send, not silently stop sending."""
    assert is_paused(profile(settings={"checkin_paused": True})) is True
    assert is_paused(profile(settings={"checkin_paused": "true"})) is False
    assert is_paused(profile(settings={"checkin_paused": 1})) is False


# --- cadence arithmetic ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cadence", "days"),
    [("weekly", 7), ("biweekly", 14), ("monthly", 30), ("quarterly", 91)],
)
def test_advance_moves_one_cadence_window(cadence, days):
    assert advance(cadence, NOW) == NOW + timedelta(days=days)


def test_recent_window_doubles_the_cadence():
    """The doubling is what stops a missed cycle's entries falling into a gap between windows."""
    assert recent_window_start("weekly", NOW) == NOW - timedelta(days=14)
    assert recent_window_start("monthly", NOW) == NOW - timedelta(days=60)


# --- due-ness -------------------------------------------------------------------------------


def test_missing_next_checkin_at_reads_as_due():
    """How every pre-slice-8 PROFILE seeds its own cycle, with no backfill."""
    assert is_due(profile(), NOW) is True


def test_future_next_checkin_at_is_not_due():
    assert is_due(profile(next_checkin_at="2026-08-07T23:00:00Z"), NOW) is False


def test_past_next_checkin_at_is_due():
    assert is_due(profile(next_checkin_at="2026-07-24T23:00:00Z"), NOW) is True


def test_exactly_now_is_due():
    """`<=`, not `<` — a schedule that fires on the dot must not skip the cycle."""
    assert is_due(profile(next_checkin_at="2026-07-31T23:00:00Z"), NOW) is True


def test_paused_is_never_due_even_when_overdue():
    overdue_and_paused = profile(
        next_checkin_at="2026-01-01T00:00:00Z",
        settings={"checkin_paused": True},
    )
    assert is_due(overdue_and_paused, NOW) is False


def test_pause_does_not_move_next_checkin_at():
    """Unpausing resumes the existing rhythm rather than firing for every elapsed cycle.

    Nothing to assert on the write side here — the point is that `is_due` is the *only* thing
    pause touches, so a paused profile's `next_checkin_at` is untouched and still in the past.
    """
    paused = profile(next_checkin_at="2026-01-01T00:00:00Z", settings={"checkin_paused": True})
    assert is_due(paused, NOW) is False
    assert paused["next_checkin_at"] == "2026-01-01T00:00:00Z"


def test_profile_without_an_email_is_not_due():
    """SES would reject it; skipping here keeps it out of the per-user error path."""
    no_email = {"PK": "USER#u1", "SK": "PROFILE"}
    assert is_due(no_email, NOW) is False


def test_unparseable_next_checkin_at_reads_as_due():
    """Fails toward sending. A garbled timestamp that suppressed sends forever would be invisible."""
    assert is_due(profile(next_checkin_at="whenever"), NOW) is True
