"""The check-in scheduling state machine against a real engine (B-018, ADR-039).

Slice 8 shipped verified entirely by hand: forced invokes, a temporary entry-date flip to reach the
personalized tier, the SES mailbox simulator for bounces, and manual state resets between runs. That
sequence is repeatable and undocumented outside the slice notes, so every future change to the
scheduled path re-runs it manually or not at all — which for a job that fires at 23:00 UTC means
"not at all".

Scope note. This covers the *decision* half — who is due, who is claimed, how the cadence advances,
how pause behaves — against real conditional writes, for $0 and with no email sent. The composition
half (Bedrock) and the delivery half (SES) are deliberately not here: the fallback ladder makes them
separable, they are what costs money and sends mail, and the decision half is the part that actually
regressed under manual testing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from careervault.checkin_schedule import advance, cadence_of, is_due, is_paused, utcnow_iso
from careervault.pydantic_models.profile import CADENCE_DAYS
from careervault.ddb_helpers import (
    CHECKIN_IDEMPOTENCY_HOURS,
    claim_checkin_slot,
    pk_for_user,
    scan_profiles,
    update_profile,
)

pytestmark = pytest.mark.local

NOW = datetime(2026, 7, 28, 23, 0, 0, tzinfo=timezone.utc)
# Imported, not restated. A local literal here would keep passing if the production window changed
# to a minute — the test would be asserting its own copy rather than the Lambda's behaviour.


def seed_profile(table, user_id: str, **attrs) -> dict:
    item = {"PK": pk_for_user(user_id), "SK": "PROFILE", "email": f"{user_id}@example.com", **attrs}
    table.put_item(Item=item)
    return item


def due_users(now: datetime = NOW) -> list[str]:
    """What the Lambda's step 1 does: Scan every PROFILE, keep the due ones (§3.3.3)."""
    return [
        str(p["PK"]).removeprefix("USER#") for p in scan_profiles() if is_due(p, now)
    ]


def claim(user_id: str, now: datetime = NOW, cadence: str = "weekly") -> bool:
    return claim_checkin_slot(
        user_id,
        now_iso=utcnow_iso(now),
        next_checkin_at=utcnow_iso(advance(cadence, now)),
        buffer_iso=utcnow_iso(now - timedelta(hours=CHECKIN_IDEMPOTENCY_HOURS)),
    )


class TestWhoIsDue:
    def test_a_profile_with_no_next_checkin_at_is_due_immediately(self, table, user_id):
        # How every pre-slice-8 PROFILE seeds its own cycle, with no backfill migration.
        seed_profile(table, user_id)
        assert due_users() == [user_id]

    def test_a_future_next_checkin_at_is_not_due(self, table, user_id):
        seed_profile(table, user_id, next_checkin_at="2026-08-04T23:00:00Z")
        assert due_users() == []

    def test_a_past_next_checkin_at_is_due(self, table, user_id):
        seed_profile(table, user_id, next_checkin_at="2026-07-21T23:00:00Z")
        assert due_users() == [user_id]

    def test_a_paused_profile_is_never_due_however_overdue(self, table, user_id):
        seed_profile(
            table,
            user_id,
            next_checkin_at="2020-01-01T00:00:00Z",
            settings={"checkin_paused": True},
        )
        assert due_users() == []

    def test_a_profile_with_no_email_is_skipped(self, table):
        table.put_item(Item={"PK": pk_for_user("no-email-user"), "SK": "PROFILE"})
        assert due_users() == []

    def test_the_scan_finds_users_across_different_partitions(self, table):
        # The reason §3.3.3 is necessarily a Scan and not a Query: one partition per user and no GSI
        # (ADR-028). Arch v2.1 corrected both §3.3.3 and §4.5.4 on this.
        for name in ("alice", "bob", "carol"):
            seed_profile(table, name)
        seed_profile(table, "dave", next_checkin_at="2026-12-01T00:00:00Z")

        assert sorted(due_users()) == ["alice", "bob", "carol"]

    def test_the_scan_ignores_non_profile_items(self, table, user_id):
        seed_profile(table, user_id)
        table.put_item(Item={"PK": pk_for_user(user_id), "SK": "ENTRY#01JQ0000000000000000000000"})
        table.put_item(Item={"PK": pk_for_user(user_id), "SK": "CHECKINLOG#01JQ1111111111111111111111"})

        assert due_users() == [user_id]


class TestClaimingAndPacing:
    def test_claiming_removes_the_user_from_the_next_run(self, table, user_id):
        seed_profile(table, user_id)
        assert due_users() == [user_id]

        assert claim(user_id) is True

        # ADR-039: next_checkin_at on the PROFILE is what paces the cadence, so one daily fire
        # serves all four cadences and a cadence change is a data write, not a control-plane call.
        assert due_users() == []

    def test_a_scheduler_retry_in_the_same_cycle_claims_nothing(self, table, user_id):
        seed_profile(table, user_id)
        first, second = claim(user_id), claim(user_id, NOW + timedelta(minutes=5))
        assert (first, second) == (True, False)

    def test_the_next_cycle_becomes_due_again_on_schedule(self, table, user_id):
        seed_profile(table, user_id)
        claim(user_id)

        assert due_users(NOW + timedelta(days=6)) == []
        assert due_users(NOW + timedelta(days=7, minutes=1)) == [user_id]

    def test_the_cadence_windows_are_what_fr_4_1_says(self):
        # Pinned as literals in exactly one place so the parametrization below can derive from the
        # constant without becoming tautological. Quarterly is 91 rather than 90 on purpose: 13
        # whole weeks, so a quarterly check-in keeps landing on the same weekday.
        assert CADENCE_DAYS == {"weekly": 7, "biweekly": 14, "monthly": 30, "quarterly": 91}

    @pytest.mark.parametrize(("cadence", "days"), sorted(CADENCE_DAYS.items()))
    def test_each_cadence_paces_its_own_next_due_date(self, table, user_id, cadence, days):
        # All four FR-4.1 cadences run off the one daily schedule — the whole point of ADR-039.
        seed_profile(table, user_id, settings={"checkin_cadence": cadence})
        assert cadence_of(scan_profiles()[0]) == cadence

        claim(user_id, cadence=cadence)

        assert due_users(NOW + timedelta(days=days - 1)) == []
        assert due_users(NOW + timedelta(days=days, minutes=1)) == [user_id]


class TestPauseAndResume:
    def test_pausing_does_not_disturb_the_existing_rhythm(self, table, user_id):
        seed_profile(table, user_id)
        claim(user_id)  # next_checkin_at is now NOW + 7d

        update_profile(user_id, {"settings": {"checkin_paused": True}})
        assert due_users(NOW + timedelta(days=8)) == []

        # FR-4.6: unpausing resumes the existing rhythm rather than firing once per cycle that
        # elapsed while paused — because pause suppresses the send without touching next_checkin_at.
        update_profile(user_id, {"settings": {"checkin_paused": False}})
        assert due_users(NOW + timedelta(days=8)) == [user_id]

    def test_a_cadence_change_while_paused_survives_the_unpause(self, table, user_id):
        # The B-014 trap, from the feature's point of view: two independent settings writes.
        seed_profile(table, user_id)
        update_profile(user_id, {"settings": {"checkin_paused": True}})
        update_profile(user_id, {"settings": {"checkin_cadence": "monthly"}})

        profile = scan_profiles()[0]
        assert is_paused(profile) is True
        assert cadence_of(profile) == "monthly"

    def test_only_a_real_boolean_pauses(self, table, user_id):
        # The failure direction is deliberate: an untyped "true" sends an email the user did not
        # want (visible, correctable) rather than silently stopping delivery forever (invisible).
        seed_profile(table, user_id, settings={"checkin_paused": "true"})
        assert due_users() == [user_id]
