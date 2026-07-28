"""Unit tests for the RESUMERUN# DynamoDB helpers (Section 3.2.5 / ADR-037).

A fake table stands in for DynamoDB — these pin the prefix invariant and the create-once vs
overwrite distinction between the pending record and the terminal one.
"""

import pytest
from botocore.exceptions import ClientError

from careervault import ddb_helpers
from careervault.ddb_helpers import create_resume_run, finalize_resume_run, get_resume_run


class FakeTable:
    def __init__(self, item=None):
        self.put_calls = []
        self.get_calls = []
        self._item = item

    def put_item(self, **kwargs):
        self.put_calls.append(kwargs)
        return {}

    def get_item(self, **kwargs):
        self.get_calls.append(kwargs)
        return {"Item": self._item} if self._item is not None else {}


@pytest.fixture
def table(monkeypatch):
    def _install(item=None):
        fake = FakeTable(item=item)
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
