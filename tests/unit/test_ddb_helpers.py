"""Unit tests for careervault.ddb_helpers identity/key helpers (no AWS calls)."""

import pytest

from careervault.ddb_helpers import extract_user_id, pk_for_user


def _event_with_sub(sub):
    return {"requestContext": {"authorizer": {"claims": {"sub": sub}}}}


def test_extract_user_id_happy_path():
    assert extract_user_id(_event_with_sub("alice-sub-123")) == "alice-sub-123"


def test_extract_user_id_missing_claims_raises():
    with pytest.raises(PermissionError):
        extract_user_id({"requestContext": {}})


def test_extract_user_id_empty_sub_raises():
    with pytest.raises(PermissionError):
        extract_user_id(_event_with_sub(""))


def test_extract_user_id_ignores_body_identity():
    # IDOR guard: identity must come from the validated authorizer, never the body (Section 4.2.4).
    event = _event_with_sub("real-user")
    event["body"] = '{"user_id": "attacker-supplied"}'
    assert extract_user_id(event) == "real-user"


def test_pk_for_user():
    assert pk_for_user("alice-sub-123") == "USER#alice-sub-123"
