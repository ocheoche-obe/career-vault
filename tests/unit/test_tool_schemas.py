"""Unit tests for the Converse tool schemas (Section 3.1.2).

The point of deriving `propose_entry`'s schema from the entry models is that the parse-time and
validate-time contracts cannot drift. These tests pin that property.
"""

from careervault.pydantic_models.entry import ENTRY_TYPES
from careervault.pydantic_models.tools import (
    CLARIFICATION_REASONS,
    build_extract_tool_config,
    build_tool_config,
)


def _propose_schema():
    config = build_tool_config()
    spec = next(t["toolSpec"] for t in config["tools"] if t["toolSpec"]["name"] == "propose_entry")
    return spec["inputSchema"]["json"]


def test_tool_choice_forces_a_tool_call():
    # `any` = the model must call one of the two tools; it may not answer with free text.
    assert build_tool_config()["toolChoice"] == {"any": {}}


def test_exactly_two_tools_are_offered():
    names = {t["toolSpec"]["name"] for t in build_tool_config()["tools"]}
    assert names == {"propose_entry", "ask_clarification"}


def test_entry_type_enum_matches_the_models():
    assert _propose_schema()["properties"]["entry_type"]["enum"] == list(ENTRY_TYPES)


def test_only_universal_fields_are_required():
    # Per-type requirements can't be expressed in a flat schema; they live in the tool
    # description and are enforced by the discriminated union afterwards.
    assert _propose_schema()["required"] == ["entry_type", "title", "content"]


def test_schema_has_no_refs_or_defs():
    # Bedrock tool schemas are happiest fully inlined; Pydantic's $defs/$ref must not leak.
    schema = _propose_schema()
    assert "$defs" not in schema
    assert "$ref" not in str(schema)


def test_optional_fields_are_not_nullable_anyof():
    # `str | None` renders as anyOf[string, null] in Pydantic; _simplify collapses it so the
    # model sees a clean `{"type": "string"}`.
    end_date = _propose_schema()["properties"]["end_date"]
    assert end_date["type"] == "string"
    assert "anyOf" not in end_date


def test_model_never_sees_entry_id():
    # entry_id is minted by chat_lambda after the tool call (Section 3.1.4) — the model must
    # not be able to invent one.
    assert "entry_id" not in _propose_schema()["properties"]


def test_union_of_subtype_fields_is_present():
    props = _propose_schema()["properties"]
    for field in ("employer", "issuer", "institution", "organization", "awarded_date", "degree"):
        assert field in props, field


def test_fields_carry_descriptions():
    props = _propose_schema()["properties"]
    assert props["employer"]["description"]
    assert props["event_date"]["description"]


def test_ask_clarification_schema():
    config = build_tool_config()
    spec = next(t["toolSpec"] for t in config["tools"] if t["toolSpec"]["name"] == "ask_clarification")
    schema = spec["inputSchema"]["json"]
    assert schema["required"] == ["question", "reason"]
    assert schema["properties"]["reason"]["enum"] == list(CLARIFICATION_REASONS)


# --- extract_entries (resume bulk-parse, ADR-035) ---------------------------------------------

def _extract_schema():
    config = build_extract_tool_config()
    spec = next(t["toolSpec"] for t in config["tools"] if t["toolSpec"]["name"] == "extract_entries")
    return spec["inputSchema"]["json"]


def test_extract_forces_the_single_tool():
    config = build_extract_tool_config()
    assert config["toolChoice"] == {"tool": {"name": "extract_entries"}}
    assert [t["toolSpec"]["name"] for t in config["tools"]] == ["extract_entries"]


def test_extract_wraps_the_propose_entry_schema_in_an_array():
    schema = _extract_schema()
    assert schema["required"] == ["entries"]
    entries = schema["properties"]["entries"]
    assert entries["type"] == "array"
    # The per-item schema is exactly the propose_entry schema — so a resume candidate and a chat
    # candidate validate against the same contract (ADR-035).
    item = entries["items"]
    assert item["properties"]["entry_type"]["enum"] == list(ENTRY_TYPES)
    assert item["required"] == ["entry_type", "title", "content"]
    assert "entry_id" not in item["properties"]
