"""Unit tests for career_crud — the Phase B confirm/persist path (Section 3.1.3–3.1.5).

Pins the HTTP status contract: 201 created · 200 idempotent duplicate · 422 validation ·
500 embedding/DynamoDB failure · 401 missing claims.
"""

from decimal import Decimal

import pytest
from helpers import FakeLambdaContext, api_event, body_of, load_handler

from careervault import bedrock_client
from careervault.bedrock_client import BedrockError
from careervault.pydantic_models.entry import to_entry_item, validate_entry

crud = load_handler("career_crud_handler", "career_crud")

VALID_JOB = {
    "entry_type": "JOB",
    "title": "Senior Backend Engineer",
    "content": "Led the payments migration.",
    "employer": "Acme Corp",
    "start_date": "2020-03-15",
    "skills_tags": ["python", "aws"],
    "entry_id": "01HXAB3K9T8MQNJ4F5G6H7K8N9",
}


@pytest.fixture
def fake_embed(monkeypatch):
    """Titan returns a short deterministic vector; record what got embedded."""
    embedded: list[str] = []

    def _embed(text, **kwargs):
        embedded.append(text)
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(bedrock_client, "embed", _embed)
    return embedded


@pytest.fixture
def fake_put(monkeypatch):
    """put_entry_conditional succeeds by default; captures the written item.

    Also stubs ``query_entries`` to an empty corpus so the ADR-033 dup check finds no matches —
    dedicated dup tests below install their own corpus.
    """
    written: list[dict] = []

    def _put(item):
        written.append(item)
        return True

    monkeypatch.setattr(crud, "put_entry_conditional", _put)
    monkeypatch.setattr(crud, "get_entry", lambda u, e: None)
    monkeypatch.setattr(crud, "query_entries", lambda u: [])
    return written


def test_valid_entry_returns_201_and_persists(fake_embed, fake_put):
    response = crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext())
    body = body_of(response)

    assert response["statusCode"] == 201
    assert body["entry"]["entry_type"] == "JOB"
    assert body["entry"]["employer"] == "Acme Corp"

    item = fake_put[0]
    assert item["PK"] == "USER#user-sub-1"
    assert item["SK"] == f"ENTRY#{VALID_JOB['entry_id']}"
    assert item["entity_type"] == "ENTRY"
    assert item["event_date"] == "2020-03-15"  # derived from start_date
    assert item["embedding"] == [0.1, 0.2, 0.3]
    assert item["embedding_model"] == "amazon.titan-embed-text-v2:0"


def test_embedding_is_stripped_from_the_response(fake_embed, fake_put):
    body = body_of(crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext()))
    # ~1024 floats are useless to the frontend and exist only for the resume agent (ADR-016).
    assert "embedding" not in body["entry"]


def test_embedding_input_covers_title_content_employer_and_skills(fake_embed, fake_put):
    crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext())
    text = fake_embed[0]
    assert "Senior Backend Engineer" in text
    assert "payments migration" in text
    assert "Acme Corp" in text
    assert "python aws" in text


def test_entry_id_from_body_is_used_as_the_sk(fake_embed, fake_put):
    crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext())
    assert fake_put[0]["SK"] == "ENTRY#01HXAB3K9T8MQNJ4F5G6H7K8N9"


def test_absent_entry_id_is_minted(fake_embed, fake_put):
    payload = {k: v for k, v in VALID_JOB.items() if k != "entry_id"}
    body = body_of(crud.handler(api_event(payload), FakeLambdaContext()))
    assert len(body["entry"]["entry_id"]) == 26


def test_duplicate_confirm_returns_200_with_existing_entry(monkeypatch, fake_embed):
    """A retried confirm must not duplicate or overwrite — it returns the stored item."""
    existing = {
        "PK": "USER#user-sub-1",
        "SK": f"ENTRY#{VALID_JOB['entry_id']}",
        "entry_type": "JOB",
        "title": "Senior Backend Engineer",
        "embedding": [Decimal("0.1")],
        "hours_per_week": Decimal("4"),
    }
    monkeypatch.setattr(crud, "put_entry_conditional", lambda item: False)
    monkeypatch.setattr(crud, "get_entry", lambda u, e: existing)
    # The stored copy shares the candidate's entry_id, so the dup check excludes it — a same-card
    # retry must reach the idempotent 200 path, not trip the 409 dup warning.
    monkeypatch.setattr(crud, "query_entries", lambda u: [existing])

    response = crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext())
    body = body_of(response)

    assert response["statusCode"] == 200
    assert body["entry"]["title"] == "Senior Backend Engineer"
    assert "embedding" not in body["entry"]
    # Decimals from DynamoDB must render as JSON numbers, and integral ones as ints.
    assert body["entry"]["hours_per_week"] == 4


def test_conditional_failure_with_absent_entry_is_500(monkeypatch, fake_embed):
    # The condition also guards the ENTRY# prefix; a failure with no stored item means the
    # prefix guard tripped, which is a bug — not an idempotent replay.
    monkeypatch.setattr(crud, "put_entry_conditional", lambda item: False)
    monkeypatch.setattr(crud, "get_entry", lambda u, e: None)
    monkeypatch.setattr(crud, "query_entries", lambda u: [])

    assert crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext())["statusCode"] == 500


def test_missing_required_field_returns_422_with_field_errors(fake_embed, fake_put):
    payload = {k: v for k, v in VALID_JOB.items() if k != "employer"}
    response = crud.handler(api_event(payload), FakeLambdaContext())
    body = body_of(response)

    assert response["statusCode"] == 422
    assert body["errors"]
    assert any("employer" in err["field"] for err in body["errors"])
    # Validation runs before the paid Titan call.
    assert fake_embed == []


def test_unknown_entry_type_returns_422(fake_embed, fake_put):
    response = crud.handler(api_event({**VALID_JOB, "entry_type": "SABBATICAL"}), FakeLambdaContext())
    assert response["statusCode"] == 422


def test_embedding_failure_returns_500(monkeypatch, fake_put):
    def _boom(text, **kwargs):
        raise BedrockError("titan down")

    monkeypatch.setattr(bedrock_client, "embed", _boom)

    response = crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext())
    assert response["statusCode"] == 500
    assert fake_put == []  # nothing written


def test_missing_sub_claim_is_unauthorized():
    assert crud.handler(api_event(dict(VALID_JOB), sub=None), FakeLambdaContext())["statusCode"] == 401


def test_malformed_json_body_is_bad_request():
    assert crud.handler(api_event("{nope"), FakeLambdaContext())["statusCode"] == 400


def test_entry_id_is_not_rejected_as_an_extra_field(fake_embed, fake_put):
    # entry_id rides along on the confirm payload (Section 3.1.4); extra="forbid" must not trip.
    assert crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext())["statusCode"] == 201


# --- POST /entries: semantic duplicate detection (ADR-033) -------------------

# fake_embed returns [0.1, 0.2, 0.3]; these corpus vectors are chosen relative to it.
_IDENTICAL_VEC = [0.1, 0.2, 0.3]      # cosine 1.0 with the candidate → above 0.90
_OPPOSITE_VEC = [-1.0, 0.0, 0.0]      # cosine < 0 with the candidate → below 0.90


def test_confirm_flags_possible_duplicate_as_409(monkeypatch, fake_embed):
    prior = {"entry_id": "OLD", "entry_type": "AWARD", "title": "Prior award", "embedding": _IDENTICAL_VEC}
    monkeypatch.setattr(crud, "query_entries", lambda u: [prior])
    written: list[dict] = []
    monkeypatch.setattr(crud, "put_entry_conditional", lambda item: written.append(item) or True)

    response = crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext())
    body = body_of(response)

    assert response["statusCode"] == 409
    assert body["message"] == "possible_duplicate"
    assert body["entry_id"] == VALID_JOB["entry_id"]
    assert body["possible_duplicates"][0]["entry_id"] == "OLD"
    assert body["possible_duplicates"][0]["similarity"] >= 0.90
    assert written == []  # nothing persisted while the duplicate is unacknowledged


def test_acknowledge_duplicate_saves_past_the_warning(monkeypatch, fake_embed):
    prior = {"entry_id": "OLD", "entry_type": "AWARD", "title": "Prior", "embedding": _IDENTICAL_VEC}
    monkeypatch.setattr(crud, "query_entries", lambda u: [prior])
    written: list[dict] = []
    monkeypatch.setattr(crud, "put_entry_conditional", lambda item: written.append(item) or True)
    monkeypatch.setattr(crud, "get_entry", lambda u, e: None)

    response = crud.handler(api_event({**VALID_JOB, "acknowledge_duplicate": True}), FakeLambdaContext())

    assert response["statusCode"] == 201
    assert written  # persisted despite the near-duplicate
    assert "acknowledge_duplicate" not in written[0]  # the flag must not leak into the item


def test_dissimilar_entry_is_not_flagged(monkeypatch, fake_embed, fake_put):
    prior = {"entry_id": "OLD", "entry_type": "AWARD", "title": "Unrelated", "embedding": _OPPOSITE_VEC}
    monkeypatch.setattr(crud, "query_entries", lambda u: [prior])
    assert crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext())["statusCode"] == 201


def test_dup_check_excludes_the_candidates_own_entry_id(monkeypatch, fake_embed):
    # A same-card retry carries the same entry_id; matching itself must reach the idempotent
    # 200 path (Section 3.1.4), never a 409.
    twin = {"entry_id": VALID_JOB["entry_id"], "entry_type": "JOB", "title": "Self", "embedding": _IDENTICAL_VEC}
    monkeypatch.setattr(crud, "query_entries", lambda u: [twin])
    monkeypatch.setattr(crud, "put_entry_conditional", lambda item: False)  # already exists
    monkeypatch.setattr(crud, "get_entry", lambda u, e: {**twin, "PK": "USER#user-sub-1", "SK": "ENTRY#x"})

    assert crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext())["statusCode"] == 200


def test_threshold_env_var_lowers_the_bar(monkeypatch, fake_embed):
    # Cosine([0.1,0.2,0.3], [1,1,0]) ≈ 0.567 — below the 0.90 default, above a 0.5 override.
    prior = {"entry_id": "OLD", "entry_type": "AWARD", "title": "Loosely related", "embedding": [1.0, 1.0, 0.0]}
    monkeypatch.setattr(crud, "query_entries", lambda u: [prior])
    monkeypatch.setattr(crud, "put_entry_conditional", lambda item: True)
    monkeypatch.setattr(crud, "get_entry", lambda u, e: None)

    assert crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext())["statusCode"] == 201  # default 0.90
    monkeypatch.setenv("DUP_SIMILARITY_THRESHOLD", "0.5")
    assert crud.handler(api_event(dict(VALID_JOB)), FakeLambdaContext())["statusCode"] == 409  # now flagged


# --- GET /entries ------------------------------------------------------------

def test_list_returns_entries_with_embedding_stripped(monkeypatch):
    items = [
        {"entry_id": "a", "entry_type": "JOB", "title": "X", "embedding": [Decimal("0.1")], "hours_per_week": Decimal("4")},
        {"entry_id": "b", "entry_type": "AWARD", "title": "Y", "embedding": [Decimal("0.2")]},
    ]
    monkeypatch.setattr(crud, "query_entries", lambda u: items)

    response = crud.handler(api_event(method="GET"), FakeLambdaContext())
    body = body_of(response)

    assert response["statusCode"] == 200
    assert len(body["entries"]) == 2
    assert all("embedding" not in e for e in body["entries"])
    assert body["entries"][0]["hours_per_week"] == 4  # Decimal → int for JSON


# --- PUT /entries/{id} -------------------------------------------------------

_JOB_NO_ID = {k: v for k, v in VALID_JOB.items() if k != "entry_id"}


def _existing_job(embedding):
    """A stored ENTRY item for the JOB above, with a caller-chosen embedding + old timestamps."""
    return to_entry_item(
        validate_entry(dict(_JOB_NO_ID)),
        user_id="user-sub-1",
        entry_id="EID",
        embedding=embedding,
        embedding_model="amazon.titan-embed-text-v2:0",
        created_at="2026-01-01T00:00:00Z",
    )


def _put_event(body):
    return api_event(body, method="PUT", path_params={"id": "EID"})


def test_update_reuses_embedding_when_text_unchanged(monkeypatch, fake_embed):
    monkeypatch.setattr(crud, "get_entry", lambda u, e: _existing_job([0.5, 0.5, 0.5]))
    written: list[dict] = []
    monkeypatch.setattr(crud, "put_entry_update", lambda item: written.append(item) or True)

    response = crud.handler(_put_event(dict(_JOB_NO_ID)), FakeLambdaContext())

    assert response["statusCode"] == 200
    assert fake_embed == []  # Titan not called — the embedded text did not change
    assert written[0]["embedding"] == [0.5, 0.5, 0.5]  # stored vector reused
    assert written[0]["created_at"] == "2026-01-01T00:00:00Z"  # preserved
    assert written[0]["updated_at"] != "2026-01-01T00:00:00Z"  # advanced


def test_update_reembeds_when_text_changed(monkeypatch, fake_embed):
    monkeypatch.setattr(crud, "get_entry", lambda u, e: _existing_job([0.5, 0.5, 0.5]))
    written: list[dict] = []
    monkeypatch.setattr(crud, "put_entry_update", lambda item: written.append(item) or True)

    response = crud.handler(_put_event({**_JOB_NO_ID, "content": "Rewrote it in entirely new words."}), FakeLambdaContext())

    assert response["statusCode"] == 200
    assert len(fake_embed) == 1  # re-embedded once
    assert written[0]["embedding"] == [0.1, 0.2, 0.3]  # the fresh Titan vector


def test_update_missing_entry_is_404(monkeypatch, fake_embed):
    monkeypatch.setattr(crud, "get_entry", lambda u, e: None)
    response = crud.handler(_put_event(dict(_JOB_NO_ID)), FakeLambdaContext())
    assert response["statusCode"] == 404
    assert fake_embed == []


def test_update_vanished_between_read_and_write_is_404(monkeypatch, fake_embed):
    monkeypatch.setattr(crud, "get_entry", lambda u, e: _existing_job([0.5, 0.5, 0.5]))
    monkeypatch.setattr(crud, "put_entry_update", lambda item: False)
    response = crud.handler(_put_event({**_JOB_NO_ID, "content": "changed"}), FakeLambdaContext())
    assert response["statusCode"] == 404


def test_update_invalid_payload_is_422(monkeypatch, fake_embed):
    monkeypatch.setattr(crud, "get_entry", lambda u, e: _existing_job([0.5, 0.5, 0.5]))
    body = {k: v for k, v in _JOB_NO_ID.items() if k != "employer"}
    response = crud.handler(_put_event(body), FakeLambdaContext())
    assert response["statusCode"] == 422
    assert fake_embed == []


def test_update_without_id_is_400(fake_embed):
    assert crud.handler(api_event(dict(_JOB_NO_ID), method="PUT"), FakeLambdaContext())["statusCode"] == 400


# --- DELETE /entries/{id} ----------------------------------------------------

def test_delete_returns_200_with_the_deleted_id(monkeypatch):
    monkeypatch.setattr(crud, "delete_entry", lambda u, e: True)
    response = crud.handler(api_event(method="DELETE", path_params={"id": "EID"}), FakeLambdaContext())
    assert response["statusCode"] == 200
    assert body_of(response)["deleted"] == "EID"


def test_delete_missing_entry_is_404(monkeypatch):
    monkeypatch.setattr(crud, "delete_entry", lambda u, e: False)
    response = crud.handler(api_event(method="DELETE", path_params={"id": "gone"}), FakeLambdaContext())
    assert response["statusCode"] == 404


def test_delete_without_id_is_400():
    assert crud.handler(api_event(method="DELETE"), FakeLambdaContext())["statusCode"] == 400


# --- routing -----------------------------------------------------------------

def test_unsupported_method_is_405():
    assert crud.handler(api_event(method="PATCH", path_params={"id": "x"}), FakeLambdaContext())["statusCode"] == 405


def test_missing_sub_claim_is_unauthorized_on_get():
    assert crud.handler(api_event(method="GET", sub=None), FakeLambdaContext())["statusCode"] == 401
