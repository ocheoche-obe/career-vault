"""Unit tests for the ENTRY subtype models and their projections (Section 2.7 / ADR-022)."""

import pytest
from pydantic import ValidationError

from careervault.pydantic_models.entry import (
    ENTRY_TYPES,
    embedding_input_text,
    resolve_event_date,
    to_entry_item,
    validate_entry,
)

JOB = {
    "entry_type": "JOB",
    "title": "Senior Backend Engineer",
    "content": "Led the payments migration to AWS.",
    "employer": "Acme Corp",
    "start_date": "2020-03-15",
    "skills_tags": ["python", "aws"],
}


def test_all_eight_subtypes_are_reachable():
    assert len(ENTRY_TYPES) == 8


def test_validate_job_happy_path():
    entry = validate_entry(dict(JOB))
    assert entry.entry_type == "JOB"
    assert entry.employer == "Acme Corp"


def test_validate_dispatches_on_entry_type():
    cert = validate_entry(
        {
            "entry_type": "CERT",
            "title": "AWS SAA",
            "content": "Passed.",
            "issuer": "AWS",
            "issued_date": "2026-05-01",
        }
    )
    assert type(cert).__name__ == "CertEntry"


def test_missing_type_required_field_raises():
    # JOB requires `employer` (Section 2.7); the flat tool schema can't express that, so the
    # discriminated union is what actually enforces it.
    payload = {k: v for k, v in JOB.items() if k != "employer"}
    with pytest.raises(ValidationError):
        validate_entry(payload)


def test_unknown_entry_type_raises():
    with pytest.raises(ValidationError):
        validate_entry({**JOB, "entry_type": "SABBATICAL"})


def test_extra_field_is_forbidden():
    # A hallucinated field must fail loudly rather than land in DynamoDB.
    with pytest.raises(ValidationError):
        validate_entry({**JOB, "salary": "150000"})


def test_blank_title_raises():
    with pytest.raises(ValidationError):
        validate_entry({**JOB, "title": ""})


@pytest.mark.parametrize(
    "payload,expected",
    [
        (JOB, "2020-03-15"),  # falls back to start_date
        ({**JOB, "event_date": "2021-01-01"}, "2021-01-01"),  # explicit wins
    ],
)
def test_resolve_event_date_precedence(payload, expected):
    entry = validate_entry(dict(payload))
    assert resolve_event_date(entry, "2026-07-09T10:00:00Z") == expected


def test_resolve_event_date_falls_back_to_created_at():
    # A HOBBY with no dates at all still gets a sortable event_date (Section 2.7 footnote 1).
    entry = validate_entry({"entry_type": "HOBBY", "title": "Bouldering", "content": "Weekly."})
    assert resolve_event_date(entry, "2026-07-09T10:00:00Z") == "2026-07-09"


def test_resolve_event_date_for_cert_uses_issued_date():
    entry = validate_entry(
        {"entry_type": "CERT", "title": "SAA", "content": "x", "issuer": "AWS", "issued_date": "2026-05-01"}
    )
    assert resolve_event_date(entry, "2026-07-09T10:00:00Z") == "2026-05-01"


def test_embedding_input_includes_title_content_org_and_skills():
    text = embedding_input_text(validate_entry(dict(JOB)))
    assert "Senior Backend Engineer" in text
    assert "payments migration" in text
    assert "Acme Corp" in text  # the type's organisation-ish field
    assert "python aws" in text


def test_to_entry_item_shape():
    entry = validate_entry(dict(JOB))
    item = to_entry_item(
        entry,
        user_id="u1",
        entry_id="01ULID",
        embedding=[0.1, 0.2],
        embedding_model="amazon.titan-embed-text-v2:0",
        created_at="2026-07-09T10:00:00Z",
    )

    assert item["PK"] == "USER#u1"
    assert item["SK"] == "ENTRY#01ULID"
    assert item["entity_type"] == "ENTRY"
    assert item["entry_id"] == "01ULID"
    assert item["event_date"] == "2020-03-15"
    assert item["embedding_model"] == "amazon.titan-embed-text-v2:0"
    assert item["created_at"] == item["updated_at"] == "2026-07-09T10:00:00Z"
    # dates must be ISO strings, not date objects — DynamoDB stores strings.
    assert isinstance(item["start_date"], str)
