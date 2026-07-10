"""Pydantic models for ENTRY items and their eight subtypes (Section 2.7 / ADR-022).

Three layers, deliberately distinct:

- **Subtype models** (:class:`JobEntry`, :class:`CertEntry`, …) — the per-type schemas from
  Section 2.7. Required/optional fields match that table exactly.
- **:data:`Entry`** — a discriminated union over ``entry_type``. This is the strict validation
  gate: ``career_crud`` validates the confirm payload against it (Section 3.1.3), and
  ``chat_lambda`` validates Haiku's ``propose_entry`` tool input against it (Section 3.1.6).
- **:func:`to_entry_item`** — projects a validated candidate into the DynamoDB item shape
  (adds ``PK``/``SK``/``entity_type``/embedding/timestamps).

DynamoDB stays schemaless (ADR-022); enforcement is application-level, here.

``extra="forbid"`` is intentional: a hallucinated or misspelled field from the LLM should fail
loudly at the validation gate rather than land silently in DynamoDB.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

#: The eight ENTRY subtypes (ADR-022 / Section 2.7).
ENTRY_TYPES: tuple[str, ...] = (
    "JOB",
    "PROJECT",
    "MILESTONE",
    "CERT",
    "AWARD",
    "EDUCATION",
    "VOLUNTEER",
    "HOBBY",
)

EmploymentType = Literal["full-time", "part-time", "contract", "internship", "temporary"]


def utcnow_iso() -> str:
    """Current UTC time as an ISO 8601 string with a ``Z`` suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class _EntryCommon(BaseModel):
    """Attributes shared by every ENTRY subtype (Section 2.7, "Common attributes").

    ``entry_id`` is the ULID minted once at ``propose_entry`` time and carried through the
    confirmation UI back to ``career_crud`` — it is what makes the confirm idempotent
    (Section 3.1.4). It is ``None`` on the tool input the model produces, and populated by
    ``chat_lambda`` before the candidate is handed to the client.

    ``event_date`` is optional here and *resolved* at write time by :func:`resolve_event_date`;
    the persisted item always carries one (Section 2.7 footnote 1).
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=5000)
    event_date: date | None = None
    skills_tags: list[str] = Field(default_factory=list, max_length=50)
    entry_id: str | None = None


class JobEntry(_EntryCommon):
    entry_type: Literal["JOB"]
    employer: str = Field(min_length=1)
    start_date: date
    end_date: date | None = None
    location: str | None = None
    employment_type: EmploymentType | None = None


class ProjectEntry(_EntryCommon):
    entry_type: Literal["PROJECT"]
    start_date: date
    end_date: date | None = None
    employer: str | None = None
    url: str | None = None
    related_job_id: str | None = None


class MilestoneEntry(_EntryCommon):
    entry_type: Literal["MILESTONE"]
    employer: str | None = None
    related_job_id: str | None = None
    impact_metric: str | None = None


class CertEntry(_EntryCommon):
    entry_type: Literal["CERT"]
    issuer: str = Field(min_length=1)
    issued_date: date
    expires_date: date | None = None
    credential_id: str | None = None
    credential_url: str | None = None


class AwardEntry(_EntryCommon):
    entry_type: Literal["AWARD"]
    awarded_date: date
    issuer: str | None = None


class EducationEntry(_EntryCommon):
    entry_type: Literal["EDUCATION"]
    institution: str = Field(min_length=1)
    degree: str = Field(min_length=1)
    start_date: date
    end_date: date | None = None
    gpa: str | None = None
    activities: list[str] = Field(default_factory=list)
    honors: list[str] = Field(default_factory=list)
    coursework: list[str] = Field(default_factory=list)


class VolunteerEntry(_EntryCommon):
    entry_type: Literal["VOLUNTEER"]
    organization: str = Field(min_length=1)
    start_date: date
    end_date: date | None = None
    hours_per_week: float | None = Field(default=None, ge=0, le=168)


class HobbyEntry(_EntryCommon):
    entry_type: Literal["HOBBY"]
    start_date: date | None = None
    end_date: date | None = None
    url: str | None = None


#: Discriminated union over ``entry_type`` — the strict validation gate.
Entry = Annotated[
    Union[
        JobEntry,
        ProjectEntry,
        MilestoneEntry,
        CertEntry,
        AwardEntry,
        EducationEntry,
        VolunteerEntry,
        HobbyEntry,
    ],
    Field(discriminator="entry_type"),
]

#: Reusable adapter — building a TypeAdapter is not free, so do it once at import.
ENTRY_ADAPTER: TypeAdapter = TypeAdapter(Entry)

# Per-type fallback used to derive `event_date` when the model didn't supply one. Ordered by
# what best represents "when this happened" for chronological sort (Section 2.7 footnote 1).
_EVENT_DATE_SOURCE: dict[str, str] = {
    "JOB": "start_date",
    "PROJECT": "start_date",
    "CERT": "issued_date",
    "AWARD": "awarded_date",
    "EDUCATION": "start_date",
    "VOLUNTEER": "start_date",
    "HOBBY": "start_date",
    # MILESTONE has no type-specific date; it relies on `event_date` or the created_at fallback.
}

# Fields concatenated into the embedding input, by type (Section 3.1.3): the organisation-ish
# attribute carries most of the retrieval signal beyond title/content/skills.
_EMBED_CONTEXT_FIELD: dict[str, str] = {
    "JOB": "employer",
    "PROJECT": "employer",
    "MILESTONE": "employer",
    "CERT": "issuer",
    "AWARD": "issuer",
    "EDUCATION": "institution",
    "VOLUNTEER": "organization",
}


def validate_entry(payload: dict) -> BaseModel:
    """Validate a raw candidate dict against the per-type schema.

    Raises:
        pydantic.ValidationError: with field-level detail, surfaced as HTTP 422 by
            ``career_crud`` (Section 3.1.5) and used as retry feedback by ``chat_lambda``
            (Section 3.1.6).
    """
    return ENTRY_ADAPTER.validate_python(payload)


def resolve_event_date(entry: BaseModel, created_at: str) -> str:
    """Return the ISO date that should land in the item's ``event_date`` attribute.

    Precedence: an explicit ``event_date`` wins; otherwise the type's natural date field
    (``start_date`` / ``issued_date`` / ``awarded_date``); otherwise the creation date. The
    persisted ENTRY item therefore *always* has an ``event_date`` to sort on, even for a
    HOBBY with no dates at all (Section 2.7 footnote 1).
    """
    explicit = getattr(entry, "event_date", None)
    if explicit is not None:
        return explicit.isoformat()

    source_field = _EVENT_DATE_SOURCE.get(entry.entry_type)
    if source_field:
        value = getattr(entry, source_field, None)
        if value is not None:
            return value.isoformat()

    return created_at[:10]  # created_at is ISO-8601; its date portion is the fallback.


def embedding_input_text(entry: BaseModel) -> str:
    """Build the text embedded by Titan for this entry (Section 3.1.3 / 4.6.2).

    Concatenates title, content, skills tags, and the type's organisation-ish field
    (employer / issuer / institution / organization) — the parts a job description is most
    likely to match semantically.
    """
    parts: list[str] = [entry.title, entry.content]

    context_field = _EMBED_CONTEXT_FIELD.get(entry.entry_type)
    if context_field:
        value = getattr(entry, context_field, None)
        if value:
            parts.append(value)

    if entry.skills_tags:
        parts.append(" ".join(entry.skills_tags))

    return "\n".join(parts)


def to_entry_item(
    entry: BaseModel,
    *,
    user_id: str,
    entry_id: str,
    embedding: list[float],
    embedding_model: str,
    created_at: str | None = None,
) -> dict:
    """Project a validated candidate into the DynamoDB ENTRY item shape (Section 2.8).

    Floats in ``embedding`` are *not* converted to ``Decimal`` here — that is the DynamoDB
    serialisation concern and lives in ``ddb_helpers.put_entry_conditional``.
    """
    now = created_at or utcnow_iso()

    # mode="json" renders `date` fields as ISO strings, which is what DynamoDB stores.
    item = entry.model_dump(mode="json", exclude_none=True)
    item.pop("entry_id", None)

    item.update(
        {
            "PK": f"USER#{user_id}",
            "SK": f"ENTRY#{entry_id}",
            "entity_type": "ENTRY",
            "entry_id": entry_id,
            "event_date": resolve_event_date(entry, now),
            "embedding": embedding,
            "embedding_model": embedding_model,
            "created_at": now,
            "updated_at": now,
        }
    )
    return item
