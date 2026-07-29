"""Unit tests for nested `settings` merge semantics on `update_profile` (ADR-040, closes B-014).

These assert on the *compiled UpdateExpression* rather than on a simulated DynamoDB. That is a
deliberate choice: the bug B-014 caught is entirely about which expression gets built — a
replace-the-object write succeeds, returns 200, and reads back plausibly. Only the expression
distinguishes the correct behaviour from the broken one.

The DynamoDB-side behaviours the expression relies on (a document path cannot be written into an
absent attribute; an expression may not name both `settings` and `settings.x`; the seed is
idempotent; sibling sub-fields survive) were verified against the live table when ADR-040 was
settled, and are recorded there rather than re-simulated here.
"""

import pytest

from careervault import ddb_helpers


class FakeTable:
    """Records every `update_item` call so the compiled expression can be asserted on."""

    def __init__(self):
        self.calls: list[dict] = []

    def update_item(self, **kwargs):
        self.calls.append(kwargs)
        return {"Attributes": {"PK": "USER#u1", "SK": "PROFILE"}}


@pytest.fixture
def table(monkeypatch):
    fake = FakeTable()
    monkeypatch.setattr(ddb_helpers, "get_table", lambda: fake)
    return fake


def expressions(table) -> list[str]:
    return [call["UpdateExpression"] for call in table.calls]


def resolved(call: dict) -> str:
    """Substitute name placeholders back in, so assertions read like the expression they check."""
    expression = call["UpdateExpression"]
    # Longest first: '#settings' must not be partially replaced by a shorter '#s0' match.
    for placeholder, name in sorted(call.get("ExpressionAttributeNames", {}).items(), key=lambda kv: -len(kv[0])):
        expression = expression.replace(placeholder, name)
    return expression


# --- the B-014 bug itself -------------------------------------------------------------------


def test_settings_never_compiles_to_a_whole_object_assignment(table):
    """The regression that motivates all of this: `SET settings = {...}` drops sibling sub-fields."""
    ddb_helpers.update_profile("u1", {"settings": {"checkin_paused": True}})

    for call in table.calls:
        assert "SET settings =" not in resolved(call).replace("SET settings = if_not_exists", "")


def test_each_sub_field_becomes_its_own_document_path(table):
    ddb_helpers.update_profile("u1", {"settings": {"checkin_paused": True, "checkin_cadence": "monthly"}})

    main = resolved(table.calls[-1])
    assert "settings.checkin_paused = :sv" in main.replace(":sv0", ":sv").replace(":sv1", ":sv")
    assert "settings.checkin_cadence = :sv" in main.replace(":sv0", ":sv").replace(":sv1", ":sv")


def test_writing_one_sub_field_never_names_the_other(table):
    """FR-4.6's independence property, at the expression level.

    A request that changes only the pause must not mention `checkin_cadence` at all — not even
    with its correct current value, since the whole failure mode is a plausible-looking write.
    """
    ddb_helpers.update_profile("u1", {"settings": {"checkin_paused": True}})

    assert "checkin_cadence" not in resolved(table.calls[-1])
    assert "checkin_cadence" not in str(table.calls[-1].get("ExpressionAttributeValues", {}))


# --- the seeding call -----------------------------------------------------------------------


def test_settings_write_seeds_the_attribute_first(table):
    """A dotted path into an absent attribute fails, and no live PROFILE has `settings` yet."""
    ddb_helpers.update_profile("u1", {"settings": {"checkin_paused": True}})

    assert len(table.calls) == 2
    assert "if_not_exists(#settings, :empty_map)" in expressions(table)[0]
    assert table.calls[0]["ExpressionAttributeValues"][":empty_map"] == {}


def test_seed_and_sub_paths_are_never_in_one_expression(table):
    """DynamoDB rejects an expression naming both a path and its descendant — hence two calls."""
    ddb_helpers.update_profile("u1", {"settings": {"checkin_paused": True}})

    for expression in expressions(table):
        assert not ("if_not_exists(#settings" in expression and "#settings.#s" in expression)


def test_no_seeding_call_when_no_settings_are_written(table):
    """The extra round trip is paid only by writes that need it."""
    ddb_helpers.update_profile("u1", {"name": "Ada Lovelace"})

    assert len(table.calls) == 1
    assert "if_not_exists(#settings" not in expressions(table)[0]


def test_empty_settings_dict_does_not_seed(table):
    ddb_helpers.update_profile("u1", {"name": "Ada", "settings": {}})

    assert len(table.calls) == 1


# --- mixed and edge payloads ----------------------------------------------------------------


def test_top_level_and_nested_fields_land_in_one_expression(table):
    """Identity and settings submitted together must not need two user-visible writes."""
    ddb_helpers.update_profile("u1", {"name": "Ada", "settings": {"checkin_cadence": "monthly"}})

    main = resolved(table.calls[-1])
    assert "name = :v0" in main
    assert "settings.checkin_cadence" in main


def test_clearing_a_sub_field_compiles_to_remove_on_the_document_path(table):
    """`None` means clear, at both levels — DynamoDB has no null that reads back as absent."""
    ddb_helpers.update_profile("u1", {"settings": {"preferred_template_id": None}})

    main = resolved(table.calls[-1])
    assert "REMOVE settings.preferred_template_id" in main


def test_created_at_is_stamped_once_and_never_moved(table):
    ddb_helpers.update_profile("u1", {"settings": {"checkin_paused": True}})

    assert "if_not_exists(#created_at, :now)" in expressions(table)[-1]


def test_scalar_settings_is_rejected_rather_than_compiled(table):
    """A caller sending `settings: "weekly"` gets an error, not a silently replaced object."""
    with pytest.raises(ValueError, match="mapping of sub-fields"):
        ddb_helpers.update_profile("u1", {"settings": "weekly"})

    assert table.calls == []


def test_the_write_is_always_keyed_to_the_profile_sort_key(table):
    """No caller can steer this write at another item (§4.2.4)."""
    ddb_helpers.update_profile("u1", {"settings": {"checkin_paused": True}})

    for call in table.calls:
        assert call["Key"] == {"PK": "USER#u1", "SK": "PROFILE"}
