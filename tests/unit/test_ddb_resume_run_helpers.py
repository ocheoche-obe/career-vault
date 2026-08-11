"""Unit tests for the RESUMERUN# and RESUME# DynamoDB helpers (§3.2.5 / ADR-037 / ADR-046).

A fake table stands in for DynamoDB — these pin the prefix invariant, the create-once vs overwrite
distinction between the pending record and the terminal one, and the split ADR-046 introduced
between the expiring trace and the durable résumé.
"""

import pytest
from boto3.dynamodb.conditions import ConditionExpressionBuilder
from botocore.exceptions import ClientError

from careervault import ddb_helpers
from careervault.ddb_helpers import (
    create_resume_record,
    delete_resume_record,
    delete_resume_run_trace,
    create_resume_run,
    finalize_resume_run,
    get_resume_record,
    get_resume_run,
    query_resumes,
)


class FakeTable:
    def __init__(self, item=None, items=None, delete_raises=None):
        self.put_calls = []
        self.get_calls = []
        self.query_calls = []
        self.delete_calls = []
        self._delete_raises = delete_raises
        self._item = item
        self._items = items or []

    def put_item(self, **kwargs):
        self.put_calls.append(kwargs)
        return {}

    def get_item(self, **kwargs):
        self.get_calls.append(kwargs)
        return {"Item": self._item} if self._item is not None else {}

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return {"Items": self._items}

    def delete_item(self, **kwargs):
        self.delete_calls.append(kwargs)
        if self._delete_raises:
            raise self._delete_raises
        return {}


def _key_prefix(query_kwargs):
    """Render the SK prefix out of a boto3 key condition, so tests can assert on it."""
    built = ConditionExpressionBuilder().build_expression(
        query_kwargs["KeyConditionExpression"], is_key_condition=True
    )
    return built.attribute_value_placeholders[":v1"]


@pytest.fixture
def table(monkeypatch):
    def _install(item=None, items=None, delete_raises=None):
        fake = FakeTable(item=item, items=items, delete_raises=delete_raises)
        monkeypatch.setattr(ddb_helpers, "get_table", lambda: fake)
        return fake

    return _install


def _run_item(run_id="01JRUN", **extra):
    item = {"PK": "USER#u", "SK": f"RESUMERUN#{run_id}", "entity_type": "RESUMERUN", "expires_at": 123}
    item.update(extra)
    return item


def test_create_is_conditional_create_once(table):
    fake = table()
    create_resume_run(_run_item(status="pending"))
    assert fake.put_calls[0]["ConditionExpression"] == "attribute_not_exists(SK)"


def test_finalize_is_unconditional_overwrite(table):
    fake = table()
    finalize_resume_run(_run_item(status="completed"))
    # The worker replaces the pending item — no create-once condition (it already exists).
    assert "ConditionExpression" not in fake.put_calls[0]


def test_create_rejects_wrong_prefix(table):
    table()
    with pytest.raises(ValueError):
        create_resume_run({"PK": "USER#u", "SK": "ENTRY#x"})


def test_finalize_rejects_wrong_prefix(table):
    table()
    with pytest.raises(ValueError):
        finalize_resume_run({"PK": "USER#u", "SK": "ENTRY#x"})


def test_get_resume_run_builds_the_key(table):
    fake = table(item=_run_item(status="completed"))
    got = get_resume_run("u", "01JRUN")
    assert got["status"] == "completed"
    assert fake.get_calls[0]["Key"] == {"PK": "USER#u", "SK": "RESUMERUN#01JRUN"}


def test_get_resume_run_absent_returns_none(table):
    table(item=None)
    assert get_resume_run("u", "missing") is None


# --- ADR-046: the durable RESUME# record ----------------------------------------------------------

def _record(run_id="01JRUN", **extra):
    item = {"PK": "USER#u", "SK": f"RESUME#{run_id}", "entity_type": "RESUME"}
    item.update(extra)
    return item


def test_create_record_is_create_once(table):
    fake = table()
    create_resume_record(_record(status="completed"))
    assert fake.put_calls[0]["ConditionExpression"] == "attribute_not_exists(SK)"


def test_create_record_rejects_wrong_prefix(table):
    table()
    with pytest.raises(ValueError):
        create_resume_record({"PK": "USER#u", "SK": "ENTRY#x"})


def test_create_record_rejects_a_trace_item(table):
    """The prefixes differ only at the 7th character; the guard has to reject the near-miss."""
    table()
    with pytest.raises(ValueError):
        create_resume_record({"PK": "USER#u", "SK": "RESUMERUN#01JRUN"})


def test_get_resume_record_builds_the_record_key_not_the_trace_key(table):
    fake = table(item=_record(status="completed"))
    got = get_resume_record("u", "01JRUN")
    assert got["status"] == "completed"
    assert fake.get_calls[0]["Key"] == {"PK": "USER#u", "SK": "RESUME#01JRUN"}


def test_get_resume_record_absent_returns_none(table):
    table(item=None)
    assert get_resume_record("u", "missing") is None


def test_query_resumes_asks_for_the_record_prefix_including_the_hash(table):
    """Dropping the ``#`` would make this query start returning RESUMERUN# traces as history."""
    fake = table(items=[])
    query_resumes("u")
    assert _key_prefix(fake.query_calls[0]) == "RESUME#"


def test_query_resumes_is_newest_first(table):
    fake = table(items=[])
    query_resumes("u")
    # ULID sort keys mean SK order is time order — reversing it is the whole recency mechanism,
    # and no GSI is involved (ADR-028 holds).
    assert fake.query_calls[0]["ScanIndexForward"] is False


def test_query_resumes_aliases_the_reserved_word_status(table):
    """``status`` is reserved in DynamoDB — a bare projection naming it fails at query time."""
    fake = table(items=[])
    query_resumes("u")
    assert fake.query_calls[0]["ExpressionAttributeNames"] == {"#status": "status"}
    assert "#status" in fake.query_calls[0]["ProjectionExpression"]


def test_query_resumes_projects_away_the_bulky_fields(table):
    """B-013's mistake declined in advance: a list read must not ship a whole JD or résumé."""
    fake = table(items=[])
    query_resumes("u")
    projection = fake.query_calls[0]["ProjectionExpression"]
    assert "target_text" not in projection
    assert "document" not in projection
    assert "target_title" in projection and "entry_count" in projection


def test_query_resumes_returns_the_items(table):
    fake = table(items=[{"run_id": "01JB"}, {"run_id": "01JA"}])
    assert [r["run_id"] for r in query_resumes("u")] == ["01JB", "01JA"]
    assert fake.query_calls[0]["Limit"] == 50


# --- deletion (ADR-046 amendment) -----------------------------------------------------------------

def test_delete_record_is_conditional_so_absence_is_distinguishable(table):
    fake = table()
    assert delete_resume_record("u", "01JRUN") is True
    assert fake.delete_calls[0]["Key"] == {"PK": "USER#u", "SK": "RESUME#01JRUN"}
    # Without the condition, deleting a résumé that never existed would report success (ADR-027).
    assert fake.delete_calls[0]["ConditionExpression"] == "attribute_exists(SK)"


def test_delete_record_reports_false_when_it_was_already_gone(table):
    table(delete_raises=ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "DeleteItem"))
    assert delete_resume_record("u", "missing") is False


def test_delete_record_reraises_a_real_failure(table):
    table(delete_raises=ClientError({"Error": {"Code": "ProvisionedThroughputExceeded"}}, "DeleteItem"))
    with pytest.raises(ClientError):
        delete_resume_record("u", "01JRUN")


def test_delete_trace_is_unconditional_because_expiry_is_normal(table):
    fake = table()
    delete_resume_run_trace("u", "01JRUN")
    assert fake.delete_calls[0]["Key"] == {"PK": "USER#u", "SK": "RESUMERUN#01JRUN"}
    # A trace older than 30 days is *supposed* to be gone; a condition here would make the common
    # case look like a failure.
    assert "ConditionExpression" not in fake.delete_calls[0]
