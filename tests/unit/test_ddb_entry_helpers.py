"""Unit tests for the conversation/entry DynamoDB helpers (Sections 3.1.4, 4.2.4).

A fake table stands in for DynamoDB — these tests pin the *expressions* we send, which is where
the SK-prefix and idempotency invariants actually live.
"""

from decimal import Decimal

import pytest
from botocore.exceptions import ClientError

from careervault import ddb_helpers
from careervault.ddb_helpers import (
    from_ddb_numbers,
    is_valid_ulid,
    new_ulid,
    put_conversation_message,
    put_entry_conditional,
    query_conversation,
    to_ddb_numbers,
)


class FakeTable:
    def __init__(self, *, query_items=None, query_pages=None, put_error=None, delete_error=None):
        self.put_calls: list[dict] = []
        self.query_calls: list[dict] = []
        self.delete_calls: list[dict] = []
        self._query_items = query_items or []
        # query_pages: successive query responses (each a dict with Items and optional
        # LastEvaluatedKey) — lets a test exercise pagination in query_entries.
        self._query_pages = list(query_pages) if query_pages else None
        self._put_error = put_error
        self._delete_error = delete_error

    def put_item(self, **kwargs):
        self.put_calls.append(kwargs)
        if self._put_error:
            raise self._put_error
        return {}

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        if self._query_pages is not None:
            return self._query_pages.pop(0)
        return {"Items": self._query_items}

    def delete_item(self, **kwargs):
        self.delete_calls.append(kwargs)
        if self._delete_error:
            raise self._delete_error
        return {}


def _conditional_failed() -> ClientError:
    return ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")


@pytest.fixture
def table(monkeypatch):
    def _install(**kwargs):
        fake = FakeTable(**kwargs)
        monkeypatch.setattr(ddb_helpers, "get_table", lambda: fake)
        return fake

    return _install


# --- number marshalling ------------------------------------------------------

def test_to_ddb_numbers_converts_floats_to_decimal():
    result = to_ddb_numbers({"embedding": [0.1, 0.2], "n": 3})
    assert all(isinstance(v, Decimal) for v in result["embedding"])
    assert result["n"] == 3


def test_to_ddb_numbers_handles_nested_tool_calls():
    # LLM tool inputs can carry floats (e.g. hours_per_week) and land on CONVO items.
    result = to_ddb_numbers({"tool_calls": [{"input": {"hours_per_week": 4.5}}]})
    assert isinstance(result["tool_calls"][0]["input"]["hours_per_week"], Decimal)


def test_from_ddb_numbers_roundtrips():
    assert from_ddb_numbers({"a": Decimal("4"), "b": Decimal("0.5"), "c": [Decimal("1.5")]}) == {
        "a": 4,  # integral Decimals render as ints
        "b": 0.5,
        "c": [1.5],
    }


def test_from_ddb_numbers_leaves_other_types_alone():
    assert from_ddb_numbers({"s": "x", "b": True, "n": None}) == {"s": "x", "b": True, "n": None}


# --- ULID validation (ADR-032) ------------------------------------------------

def test_is_valid_ulid_accepts_minted_ulids():
    assert is_valid_ulid(new_ulid()) is True
    assert is_valid_ulid("01ARZ3NDEKTSV4RRFFQ69G5FAV") is True  # spec example


@pytest.mark.parametrize(
    "value",
    [
        "SESS1",  # too short
        "01ARZ3NDEKTSV4RRFFQ69G5FA",  # 25 chars
        "x#injected#CONVO",  # SK-structure injection attempt
        "01ARZ3NDEKTSV4RRFFQ69G5FAV extra",
        "",
        None,
        42,
    ],
)
def test_is_valid_ulid_rejects_malformed_values(value):
    assert is_valid_ulid(value) is False


# --- conversation ------------------------------------------------------------

def test_put_conversation_message_writes_create_only(table):
    fake = table()
    assert put_conversation_message({"PK": "USER#u1", "SK": "CONVO#s1#m1", "role": "user"}) is True

    call = fake.put_calls[0]
    # A condition can only inspect the *existing* item, so it can express create-once and
    # nothing more. `begins_with(SK, ...)` here would be false for every create.
    assert call["ConditionExpression"] == "attribute_not_exists(SK)"
    assert "ExpressionAttributeValues" not in call


def test_put_conversation_message_returns_false_on_duplicate(table):
    # A retried chat turn reuses its client_message_id, so the SK collides — the caller treats
    # False as "already durable, proceed" (ADR-032), mirroring put_entry_conditional.
    table(put_error=_conditional_failed())
    assert put_conversation_message({"PK": "USER#u1", "SK": "CONVO#s1#m1", "role": "user"}) is False


def test_put_conversation_message_reraises_other_errors(table):
    table(put_error=ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "PutItem"))
    with pytest.raises(ClientError):
        put_conversation_message({"PK": "USER#u1", "SK": "CONVO#s1#m1", "role": "user"})


def test_put_conversation_message_rejects_foreign_sk_prefix(table):
    fake = table()
    # chat_lambda must not be able to write an ENTRY item, even via a bug upstream.
    with pytest.raises(ValueError, match="ENTRY#e1"):
        put_conversation_message({"PK": "USER#u1", "SK": "ENTRY#e1"})
    assert fake.put_calls == []  # rejected before it reached DynamoDB


def test_put_item_scoped_rejects_missing_sk(table):
    table()
    with pytest.raises(ValueError):
        ddb_helpers.put_item_scoped({"PK": "USER#u1"}, "CONVO#")


def test_put_conversation_message_marshals_floats(table):
    fake = table()
    put_conversation_message(
        {"PK": "USER#u1", "SK": "CONVO#s1#m1", "tool_calls": [{"input": {"hours_per_week": 4.5}}]}
    )
    written = fake.put_calls[0]["Item"]
    assert isinstance(written["tool_calls"][0]["input"]["hours_per_week"], Decimal)


def test_query_conversation_returns_newest_messages_oldest_first(table):
    # DynamoDB is queried newest-first with a Limit, then reversed — so a long session replays
    # its most recent turns, not its first ones.
    fake = table(query_items=[{"SK": "CONVO#s1#c"}, {"SK": "CONVO#s1#b"}])
    items = query_conversation("u1", "s1", limit=2)

    assert fake.query_calls[0]["ScanIndexForward"] is False
    assert fake.query_calls[0]["Limit"] == 2
    assert [i["SK"] for i in items] == ["CONVO#s1#b", "CONVO#s1#c"]


# --- entries -----------------------------------------------------------------

def test_put_entry_conditional_returns_true_on_create(table):
    fake = table()
    assert put_entry_conditional({"PK": "USER#u1", "SK": "ENTRY#e1"}) is True

    call = fake.put_calls[0]
    # `attribute_not_exists(SK) AND begins_with(SK, :prefix)` is self-contradictory — the first
    # clause requires the item absent, the second requires it present — so it never succeeds.
    # Idempotency is the only thing the condition can express; the prefix is checked in code.
    assert call["ConditionExpression"] == "attribute_not_exists(SK)"
    assert "ExpressionAttributeValues" not in call


def test_put_entry_conditional_returns_false_on_duplicate(table):
    table(put_error=_conditional_failed())
    assert put_entry_conditional({"PK": "USER#u1", "SK": "ENTRY#e1"}) is False


def test_put_entry_conditional_rejects_foreign_sk_prefix(table):
    fake = table()
    with pytest.raises(ValueError, match="CONVO#"):
        put_entry_conditional({"PK": "USER#u1", "SK": "CONVO#s1#m1"})
    assert fake.put_calls == []


def test_put_entry_conditional_reraises_other_errors(table):
    table(put_error=ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "PutItem"))
    with pytest.raises(ClientError):
        put_entry_conditional({"PK": "USER#u1", "SK": "ENTRY#e1"})


def test_put_entry_conditional_marshals_embedding_floats(table):
    fake = table()
    put_entry_conditional({"PK": "USER#u1", "SK": "ENTRY#e1", "embedding": [0.1, 0.2]})
    assert all(isinstance(v, Decimal) for v in fake.put_calls[0]["Item"]["embedding"])


# --- query_entries (AP-10) ---------------------------------------------------

def test_query_entries_queries_the_entry_prefix(table):
    fake = table(query_items=[{"SK": "ENTRY#a"}, {"SK": "ENTRY#b"}])
    items = ddb_helpers.query_entries("u1")

    assert [i["SK"] for i in items] == ["ENTRY#a", "ENTRY#b"]
    # A single page with no LastEvaluatedKey means exactly one query and no ExclusiveStartKey.
    assert len(fake.query_calls) == 1
    assert "ExclusiveStartKey" not in fake.query_calls[0]


def test_query_entries_follows_pagination_to_completion(table):
    # Embedding-laden items blow past the 1 MB page limit, so query_entries must page — stopping
    # at page one would silently drop entries from the dashboard and the resume-agent read.
    fake = table(
        query_pages=[
            {"Items": [{"SK": "ENTRY#a"}], "LastEvaluatedKey": {"PK": "USER#u1", "SK": "ENTRY#a"}},
            {"Items": [{"SK": "ENTRY#b"}]},  # no LastEvaluatedKey → last page
        ]
    )
    items = ddb_helpers.query_entries("u1")

    assert [i["SK"] for i in items] == ["ENTRY#a", "ENTRY#b"]
    assert len(fake.query_calls) == 2
    # The second query resumes from the first page's LastEvaluatedKey.
    assert fake.query_calls[1]["ExclusiveStartKey"] == {"PK": "USER#u1", "SK": "ENTRY#a"}


# --- put_entry_update (AP-5) -------------------------------------------------

def test_put_entry_update_requires_existing_item(table):
    fake = table()
    assert ddb_helpers.put_entry_update({"PK": "USER#u1", "SK": "ENTRY#e1"}) is True

    call = fake.put_calls[0]
    # Overwrite-if-exists: the opposite condition to create-once.
    assert call["ConditionExpression"] == "attribute_exists(SK)"


def test_put_entry_update_returns_false_when_absent(table):
    table(put_error=_conditional_failed())
    assert ddb_helpers.put_entry_update({"PK": "USER#u1", "SK": "ENTRY#e1"}) is False


def test_put_entry_update_rejects_foreign_sk_prefix(table):
    fake = table()
    with pytest.raises(ValueError, match="CONVO#"):
        ddb_helpers.put_entry_update({"PK": "USER#u1", "SK": "CONVO#s1#m1"})
    assert fake.put_calls == []


def test_put_entry_update_reraises_other_errors(table):
    table(put_error=ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "PutItem"))
    with pytest.raises(ClientError):
        ddb_helpers.put_entry_update({"PK": "USER#u1", "SK": "ENTRY#e1"})


# --- delete_entry (AP-6 / ADR-027) -------------------------------------------

def test_delete_entry_returns_true_and_scopes_the_key(table):
    fake = table()
    assert ddb_helpers.delete_entry("u1", "e1") is True

    call = fake.delete_calls[0]
    assert call["Key"] == {"PK": "USER#u1", "SK": "ENTRY#e1"}
    # attribute_exists(SK) distinguishes "deleted" from "never existed" (→ 404).
    assert call["ConditionExpression"] == "attribute_exists(SK)"


def test_delete_entry_returns_false_when_absent(table):
    table(delete_error=_conditional_failed())
    assert ddb_helpers.delete_entry("u1", "missing") is False


def test_delete_entry_reraises_other_errors(table):
    table(delete_error=ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "DeleteItem"))
    with pytest.raises(ClientError):
        ddb_helpers.delete_entry("u1", "e1")
