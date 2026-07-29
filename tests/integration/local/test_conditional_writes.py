"""Conditional-write semantics against a real DynamoDB engine (arch §5.6, §4.7).

The unit suite fakes DynamoDB, so it can only assert that the *right arguments* were passed. That
is exactly the gap the SK-prefix bug slipped through, and the architecture doc's v1.3 changelog
calls for this net by name. Here the conditions actually evaluate: a second create really loses,
a document path really rejects, a lexicographic comparison really orders.

Every test in this file costs nothing and touches no AWS account.
"""

from __future__ import annotations

import pytest

from careervault.ddb_helpers import (
    claim_checkin_slot,
    delete_entry,
    get_entry,
    put_conversation_message,
    put_entry_conditional,
    put_entry_update,
    put_item_scoped,
    query_entries,
    pk_for_user,
)

pytestmark = pytest.mark.local


def entry_item(user_id: str, entry_id: str, **extra) -> dict:
    return {
        "PK": pk_for_user(user_id),
        "SK": f"ENTRY#{entry_id}",
        "entry_id": entry_id,
        "entry_type": "CERT",
        "title": "AWS Solutions Architect Associate",
        "content": "Passed SAA-C03.",
        **extra,
    }


class TestEntryIdempotency:
    """Section 3.1.4 — the confirm gate must be safe to hit twice."""

    def test_first_create_wins_and_second_loses(self, table, user_id):
        item = entry_item(user_id, "01JQ0000000000000000000000")

        assert put_entry_conditional(item) is True
        # A double click, a retry, a browser back/forward: same entry_id, same SK.
        assert put_entry_conditional(item) is False

    def test_the_loser_does_not_overwrite_the_stored_entry(self, table, user_id):
        entry_id = "01JQ0000000000000000000000"
        put_entry_conditional(entry_item(user_id, entry_id, title="Original"))

        assert put_entry_conditional(entry_item(user_id, entry_id, title="Clobbered")) is False

        # The distinction that matters: the caller returns 200 rather than 201, and the *stored*
        # entry is untouched. A non-conditional put would return the same 200 having silently
        # replaced the user's data.
        stored = get_entry(user_id, entry_id)
        assert stored["title"] == "Original"

    def test_different_entry_ids_both_persist(self, table, user_id):
        put_entry_conditional(entry_item(user_id, "01JQ0000000000000000000000"))
        put_entry_conditional(entry_item(user_id, "01JQ1111111111111111111111"))

        assert len(query_entries(user_id)) == 2


class TestSkPrefixScoping:
    """Section 4.2.4 — the invariant IAM cannot express, enforced in code.

    ``LeadingKeys`` scopes the partition key only, and a ConditionExpression is evaluated against
    the *stored* item rather than the one being written, so neither can constrain the key about to
    be created. These tests are what make the code-level guard real.
    """

    def test_a_foreign_prefix_raises_before_any_write(self, table, user_id):
        # A chat Lambda bug that built a PROFILE key must not be able to overwrite the profile.
        bad = {"PK": pk_for_user(user_id), "SK": "PROFILE", "title": "hijacked"}

        with pytest.raises(ValueError, match="outside this caller's allowed prefix"):
            put_entry_conditional(bad)

        # Nothing was written — the guard fires before the call, not after.
        assert table.get_item(Key={"PK": pk_for_user(user_id), "SK": "PROFILE"}).get("Item") is None

    def test_scoped_put_rejects_a_mismatched_prefix(self, table, user_id):
        item = {"PK": pk_for_user(user_id), "SK": "ENTRY#01JQ0000000000000000000000"}

        with pytest.raises(ValueError):
            put_item_scoped(item, "CONVO#")

    def test_query_entries_does_not_return_neighbouring_item_types(self, table, user_id):
        put_entry_conditional(entry_item(user_id, "01JQ0000000000000000000000"))
        table.put_item(Item={"PK": pk_for_user(user_id), "SK": "PROFILE", "name": "Oche"})
        table.put_item(Item={"PK": pk_for_user(user_id), "SK": "GOAL#01JQ2222222222222222222222"})

        entries = query_entries(user_id)

        # One partition, several item types — begins_with is the only thing separating them.
        assert [e["SK"] for e in entries] == ["ENTRY#01JQ0000000000000000000000"]


class TestUpdateAndDeleteRequireExistence:
    def test_update_of_a_missing_entry_reports_false_rather_than_creating_it(self, table, user_id):
        item = entry_item(user_id, "01JQ0000000000000000000000", title="Ghost")

        # attribute_exists(SK) is what turns a PUT into an update-only operation. Without it this
        # would resurrect an entry the user had just deleted.
        assert put_entry_update(item) is False
        assert get_entry(user_id, "01JQ0000000000000000000000") is None

    def test_update_of_an_existing_entry_succeeds_and_replaces(self, table, user_id):
        entry_id = "01JQ0000000000000000000000"
        put_entry_conditional(entry_item(user_id, entry_id, title="Before"))

        assert put_entry_update(entry_item(user_id, entry_id, title="After")) is True
        assert get_entry(user_id, entry_id)["title"] == "After"

    def test_delete_distinguishes_deleted_from_never_existed(self, table, user_id):
        entry_id = "01JQ0000000000000000000000"
        put_entry_conditional(entry_item(user_id, entry_id))

        assert delete_entry(user_id, entry_id) is True
        # The second call is what lets the API answer 404 instead of a cheerful 200.
        assert delete_entry(user_id, entry_id) is False


class TestConversationIdempotency:
    def test_the_same_client_message_id_is_accepted_once(self, table, user_id):
        message = {
            "PK": pk_for_user(user_id),
            "SK": "CONVO#sess-1#01JQ0000000000000000000000",
            "role": "user",
            "content": "I passed the SAA exam",
        }

        assert put_conversation_message(message) is True
        assert put_conversation_message(message) is False

    def test_floats_survive_the_round_trip_as_decimals(self, table, user_id):
        # Tool inputs from a model can carry floats; the resource API rejects them outright, so
        # to_ddb_numbers() marshals on the way in. A mock would never surface this.
        message = {
            "PK": pk_for_user(user_id),
            "SK": "CONVO#sess-1#01JQ1111111111111111111111",
            "role": "assistant",
            "tool_calls": {"confidence": 0.87, "nested": [{"score": 0.5}]},
        }

        assert put_conversation_message(message) is True
        stored = table.get_item(Key={"PK": message["PK"], "SK": message["SK"]})["Item"]
        assert float(stored["tool_calls"]["confidence"]) == pytest.approx(0.87)
        assert float(stored["tool_calls"]["nested"][0]["score"]) == pytest.approx(0.5)


class TestCheckinSlotClaim:
    """§3.3.4 / ADR-039 — at-most-once send, bought by giving up at-least-once (B-016)."""

    def test_the_first_claim_wins_and_a_retry_loses(self, table, user_id):
        table.put_item(Item={"PK": pk_for_user(user_id), "SK": "PROFILE"})

        first = claim_checkin_slot(
            user_id,
            now_iso="2026-07-28T23:00:00Z",
            next_checkin_at="2026-08-04T23:00:00Z",
            buffer_iso="2026-07-28T11:00:00Z",
        )
        # An EventBridge Scheduler retry after a Lambda timeout, same cycle.
        second = claim_checkin_slot(
            user_id,
            now_iso="2026-07-28T23:05:00Z",
            next_checkin_at="2026-08-04T23:00:00Z",
            buffer_iso="2026-07-28T11:00:00Z",
        )

        assert (first, second) == (True, False)

    def test_a_later_cycle_claims_again_once_the_buffer_has_passed(self, table, user_id):
        table.put_item(Item={"PK": pk_for_user(user_id), "SK": "PROFILE"})
        claim_checkin_slot(user_id, "2026-07-28T23:00:00Z", "2026-08-04T23:00:00Z", "2026-07-28T11:00:00Z")

        # Next week's fire: last_checkin_sent_at is now older than the buffer.
        assert claim_checkin_slot(
            user_id,
            now_iso="2026-08-04T23:00:00Z",
            next_checkin_at="2026-08-11T23:00:00Z",
            buffer_iso="2026-08-04T11:00:00Z",
        ) is True

    def test_the_claim_advances_next_checkin_at_atomically(self, table, user_id):
        table.put_item(Item={"PK": pk_for_user(user_id), "SK": "PROFILE"})

        claim_checkin_slot(user_id, "2026-07-28T23:00:00Z", "2026-08-04T23:00:00Z", "2026-07-28T11:00:00Z")

        profile = table.get_item(Key={"PK": pk_for_user(user_id), "SK": "PROFILE"})["Item"]
        # Claiming and rescheduling are one write, so a crash after sending cannot strand the user
        # permanently due.
        assert profile["last_checkin_sent_at"] == "2026-07-28T23:00:00Z"
        assert profile["next_checkin_at"] == "2026-08-04T23:00:00Z"

    def test_iso_strings_compare_lexicographically_across_a_year_boundary(self, table, user_id):
        """The reason timestamps are stored as fixed-width ISO-8601 Z strings, not epoch numbers."""
        table.put_item(
            Item={"PK": pk_for_user(user_id), "SK": "PROFILE", "last_checkin_sent_at": "2026-12-31T23:00:00Z"}
        )

        # Buffer in the new year is lexicographically greater, so the claim is admitted.
        assert claim_checkin_slot(
            user_id, "2027-01-07T23:00:00Z", "2027-01-14T23:00:00Z", "2027-01-07T11:00:00Z"
        ) is True
