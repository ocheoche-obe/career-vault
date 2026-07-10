"""Unit tests for career_crud — the Phase B confirm/persist path (Section 3.1.3–3.1.5).

Pins the HTTP status contract: 201 created · 200 idempotent duplicate · 422 validation ·
500 embedding/DynamoDB failure · 401 missing claims.
"""

from decimal import Decimal

import pytest
from helpers import FakeLambdaContext, api_event, body_of, load_handler

from careervault import bedrock_client
from careervault.bedrock_client import BedrockError

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
    """put_entry_conditional succeeds by default; captures the written item."""
    written: list[dict] = []

    def _put(item):
        written.append(item)
        return True

    monkeypatch.setattr(crud, "put_entry_conditional", _put)
    monkeypatch.setattr(crud, "get_entry", lambda u, e: None)
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
