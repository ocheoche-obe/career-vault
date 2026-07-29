"""ADR-040's premises, executed rather than asserted (B-014).

Every claim in ADR-040 is a claim about what the *DynamoDB engine* does, and each was established
by probing the live table by hand during slice 8 — including one the first draft stated as fact and
got wrong (that the seed could ride along in the main expression). Manual probes do not survive
into CI: nothing re-checks them when the code changes, and the ADR is prose either way.

These tests are those probes, made permanent and free. If a future refactor collapses the two calls
back into one, or drops the seed, or lets `settings` reach the top-level compiler, one of these
fails with a message naming the reason.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError

from careervault.ddb_helpers import get_profile, pk_for_user, update_profile

pytestmark = pytest.mark.local


class TestSubFieldsMoveIndependently:
    """The bug B-014 was logged for: a nested write must not drop its siblings."""

    def test_pausing_does_not_reset_the_cadence(self, table, user_id):
        update_profile(user_id, {"settings": {"checkin_cadence": "weekly"}})
        update_profile(user_id, {"settings": {"checkin_paused": True}})

        settings = get_profile(user_id)["settings"]
        # A `SET settings = :v` would leave only checkin_paused here, return 200, and echo back an
        # accurate one-field object. Nothing would surface the loss until a check-in ran at the
        # wrong cadence days later.
        assert settings == {"checkin_cadence": "weekly", "checkin_paused": True}

    def test_changing_the_cadence_does_not_un_pause(self, table, user_id):
        update_profile(user_id, {"settings": {"checkin_paused": True}})
        update_profile(user_id, {"settings": {"checkin_cadence": "monthly"}})

        assert get_profile(user_id)["settings"] == {"checkin_paused": True, "checkin_cadence": "monthly"}

    def test_top_level_and_nested_fields_move_in_one_call(self, table, user_id):
        update_profile(user_id, {"name": "Ada Lovelace", "settings": {"checkin_cadence": "weekly"}})

        profile = get_profile(user_id)
        assert profile["name"] == "Ada Lovelace"
        assert profile["settings"] == {"checkin_cadence": "weekly"}

    def test_an_unset_sub_field_is_removed_without_disturbing_the_others(self, table, user_id):
        update_profile(user_id, {"settings": {"checkin_cadence": "weekly", "checkin_paused": True}})

        update_profile(user_id, {"settings": {"checkin_paused": None}})

        assert get_profile(user_id)["settings"] == {"checkin_cadence": "weekly"}


class TestTheSeedingCall:
    """ADR-040's two engine-level premises, as executable checks."""

    def test_a_dotted_path_works_on_a_profile_that_does_not_exist_yet(self, table, user_id):
        # The live PROFILE had no `settings` attribute at all, so *every* settings write would have
        # failed without the seed. This is the case that forced the second UpdateItem.
        assert get_profile(user_id) is None

        update_profile(user_id, {"settings": {"checkin_paused": True}})

        assert get_profile(user_id)["settings"] == {"checkin_paused": True}

    def test_writing_a_document_path_into_an_absent_attribute_is_rejected(self, table, user_id):
        """Premise 1, stated directly against the engine rather than through update_profile."""
        table.put_item(Item={"PK": pk_for_user(user_id), "SK": "PROFILE"})  # no `settings`

        with pytest.raises(ClientError) as exc:
            table.update_item(
                Key={"PK": pk_for_user(user_id), "SK": "PROFILE"},
                UpdateExpression="SET settings.checkin_paused = :v",
                ExpressionAttributeValues={":v": True},
            )

        assert exc.value.response["Error"]["Code"] == "ValidationException"
        assert "document path" in str(exc.value).lower()

    def test_seeding_and_writing_in_one_expression_is_rejected_as_overlapping(self, table, user_id):
        """Premise 2 — the one the ADR's first draft asserted as fact and got wrong.

        The obvious single-call form is not merely inelegant, it is refused: DynamoDB rejects an
        expression naming both a path and its own descendant.
        """
        table.put_item(Item={"PK": pk_for_user(user_id), "SK": "PROFILE"})

        with pytest.raises(ClientError) as exc:
            table.update_item(
                Key={"PK": pk_for_user(user_id), "SK": "PROFILE"},
                UpdateExpression=(
                    "SET #s = if_not_exists(#s, :empty), #s.checkin_paused = :v"
                ),
                ExpressionAttributeNames={"#s": "settings"},
                ExpressionAttributeValues={":empty": {}, ":v": True},
            )

        assert exc.value.response["Error"]["Code"] == "ValidationException"
        assert "overlap" in str(exc.value).lower()

    def test_the_seed_never_clobbers_an_existing_settings_object(self, table, user_id):
        update_profile(user_id, {"settings": {"checkin_cadence": "weekly"}})

        # Repeated writes re-issue the idempotent seed each time; `if_not_exists` must leave the
        # populated object alone. If the seed were unconditional this would wipe the cadence.
        for _ in range(3):
            update_profile(user_id, {"settings": {"checkin_paused": False}})

        assert get_profile(user_id)["settings"] == {"checkin_cadence": "weekly", "checkin_paused": False}


class TestGuards:
    def test_a_scalar_settings_value_is_rejected_before_any_write(self, table, user_id):
        with pytest.raises(ValueError, match="mapping of sub-fields"):
            update_profile(user_id, {"settings": "weekly"})

        assert get_profile(user_id) is None

    def test_created_at_is_preserved_across_updates(self, table, user_id):
        first = update_profile(user_id, {"name": "Ada"})
        second = update_profile(user_id, {"name": "Ada Lovelace"})

        # `if_not_exists(created_at, :now)` is what makes this hold — a plain SET would silently
        # reset the account's creation date on every profile edit.
        assert second["created_at"] == first["created_at"]
        assert second["name"] == "Ada Lovelace"

        # Deliberately NOT asserting that updated_at advanced. `update_profile` formats with
        # `timespec="seconds"`, so two back-to-back calls almost always produce an identical string
        # and `second >= first` would hold even if the field were frozen or removed entirely —
        # a green assertion carrying no information. Testing it honestly needs an injectable clock,
        # which the helper does not currently expose.
        assert "updated_at" in second
