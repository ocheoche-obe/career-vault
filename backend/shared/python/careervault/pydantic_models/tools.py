"""Bedrock Converse tool-input schemas for the chat parse turn (Section 3.1.2).

``chat_lambda`` hands Claude exactly two tools and forces a call (``toolChoice: {"any": {}}``):

- ``propose_entry`` — emit a structured entry candidate
- ``ask_clarification`` — ask the user a follow-up question

**Why structured-via-tools rather than structured-via-JSON-prompt:** Bedrock enforces the tool
input schema at the API layer, so the response matches the schema or the model retries before we
ever see it. No JSON-repair code.

**Single source of truth.** ``propose_entry``'s schema is *derived* from the eight subtype models
in :mod:`careervault.pydantic_models.entry` rather than hand-written, so the parse-time contract
can never drift from the validate-time contract (Section 3.1.2 / ADR-023).

The derived schema is deliberately **permissive**: a flat union of every subtype's fields, with
only the universally-required ones (``entry_type``, ``title``, ``content``) marked required. JSON
Schema can't express "``employer`` is required *iff* ``entry_type`` is JOB" without ``oneOf``,
which degrades tool-use quality — so per-type requirements are stated in the tool *description*,
and enforced afterwards by the strict discriminated union (Section 3.1.6 retries on failure).
"""

from __future__ import annotations

from typing import Any

from .entry import (
    ENTRY_TYPES,
    AwardEntry,
    CertEntry,
    EducationEntry,
    HobbyEntry,
    JobEntry,
    MilestoneEntry,
    ProjectEntry,
    VolunteerEntry,
)

_SUBTYPE_MODELS = (
    JobEntry,
    ProjectEntry,
    MilestoneEntry,
    CertEntry,
    AwardEntry,
    EducationEntry,
    VolunteerEntry,
    HobbyEntry,
)

# Universally required across all eight subtypes. Everything else is conditionally required and
# is described in the tool description instead (see module docstring).
_ALWAYS_REQUIRED = ("entry_type", "title", "content")

# `entry_id` is minted by chat_lambda *after* the tool call (Section 3.1.4) — the model must
# never invent one, so it is stripped from the schema the model sees.
_MODEL_INVISIBLE_FIELDS = ("entry_id",)

# Prompt-engineering lives here, not on the entity models: these steer Haiku's extraction and
# have no bearing on validation.
_FIELD_DESCRIPTIONS: dict[str, str] = {
    "entry_type": "The kind of career item this is. Pick the single best fit.",
    "title": "Short headline, e.g. 'Senior Backend Engineer' or 'AWS Solutions Architect Associate'.",
    "content": "Free-text description of what happened, including impact and specifics the user gave.",
    "event_date": "ISO date (YYYY-MM-DD) this happened. Omit if the user did not say.",
    "skills_tags": "Lowercase skills/technologies evidenced by this entry, e.g. ['python', 'aws'].",
    "employer": "Company or organisation name.",
    "start_date": "ISO date (YYYY-MM-DD) this started.",
    "end_date": "ISO date (YYYY-MM-DD) this ended. Omit if ongoing.",
    "location": "City, state/country.",
    "employment_type": "Employment arrangement.",
    "url": "Public URL, if the user mentioned one.",
    "related_job_id": "ULID of a related JOB entry, only if the user explicitly referenced one.",
    "impact_metric": "Quantified outcome, e.g. 'reduced infra costs by 40%'.",
    "issuer": "Body that issued the certification or award.",
    "issued_date": "ISO date (YYYY-MM-DD) the certification was issued.",
    "expires_date": "ISO date (YYYY-MM-DD) the certification expires.",
    "credential_id": "Credential/badge identifier.",
    "credential_url": "Verification URL for the credential.",
    "awarded_date": "ISO date (YYYY-MM-DD) the award was received.",
    "institution": "School or university name.",
    "degree": "Degree earned, e.g. 'BSc Computer Science'.",
    "gpa": "Grade point average, as the user stated it.",
    "activities": "Extracurricular activities.",
    "honors": "Academic honors received.",
    "coursework": "Relevant courses taken.",
    "organization": "Organisation volunteered with.",
    "hours_per_week": "Approximate hours per week committed.",
}

_PROPOSE_ENTRY_DESCRIPTION = """\
Emit a structured career entry parsed from what the user said. Call this when the user has \
described something concrete enough to record.

Per-type required fields (in addition to entry_type, title, content):
- JOB: employer, start_date
- PROJECT: start_date
- MILESTONE: (none)
- CERT: issuer, issued_date
- AWARD: awarded_date
- EDUCATION: institution, degree, start_date
- VOLUNTEER: organization, start_date
- HOBBY: (none)

Only include fields the user actually provided or that follow unambiguously from what they said. \
Never invent dates, employers, or metrics. If a required field for the type you want is missing, \
call ask_clarification instead."""

_ASK_CLARIFICATION_DESCRIPTION = """\
Ask the user one focused follow-up question. Call this when the message is too vague to record, \
or when a field required for the entry type is missing and cannot be inferred."""

_EXTRACT_ENTRIES_DESCRIPTION = """\
Extract every distinct career entry from the resume text — one array element per role, project, \
certification, award, degree, volunteer position, or notable milestone.
Per-type required fields (in addition to entry_type, title, content):
- JOB: employer, start_date
- PROJECT: start_date
- MILESTONE: (none)
- CERT: issuer, issued_date
- AWARD: awarded_date
- EDUCATION: institution, degree, start_date
- VOLUNTEER: organization, start_date
- HOBBY: (none)

Rules:
- Emit each distinct item as its own entry, in the order it appears in the resume.
- Prefer the most specific entry_type that fits (a certification is CERT, not MILESTONE).
- Use only what the resume states. Never invent dates, employers, issuers, or metrics; omit any \
optional field the resume does not provide.
- Only skip an item if it cannot be given the fields its type requires. If nothing recordable is \
present, return an empty entries array."""

#: Why the model is asking — lets the UI/analytics see *what* was ambiguous (Section 3.1.2).
CLARIFICATION_REASONS = (
    "missing_date",
    "ambiguous_type",
    "needs_employer",
    "insufficient_detail",
    "other",
)


def _simplify(node: Any) -> Any:
    """Strip Pydantic's JSON-Schema noise into the lean shape tool use wants.

    Two transforms: collapse ``anyOf: [T, null]`` (how Pydantic renders ``T | None``) down to
    ``T``, and drop ``title``/``default`` keys the model doesn't benefit from reading.
    """
    if isinstance(node, list):
        return [_simplify(item) for item in node]
    if not isinstance(node, dict):
        return node

    any_of = node.get("anyOf")
    if any_of:
        non_null = [opt for opt in any_of if opt.get("type") != "null"]
        if len(non_null) == 1:
            merged = {k: v for k, v in node.items() if k not in ("anyOf", "default", "title")}
            merged.update(non_null[0])
            return _simplify(merged)

    return {
        key: _simplify(value)
        for key, value in node.items()
        if key not in ("title", "default")
    }


def _propose_entry_input_schema() -> dict:
    """Merge the eight subtype schemas into one flat, permissive tool-input schema."""
    properties: dict[str, dict] = {}

    for model in _SUBTYPE_MODELS:
        schema = model.model_json_schema()
        for name, prop in schema.get("properties", {}).items():
            if name in _MODEL_INVISIBLE_FIELDS or name == "entry_type":
                continue
            # Field names are shared across subtypes with identical types (e.g. `start_date`),
            # so first-writer-wins is safe and keeps the merge order-independent.
            properties.setdefault(name, _simplify(prop))

    properties["entry_type"] = {"type": "string", "enum": list(ENTRY_TYPES)}

    for name, description in _FIELD_DESCRIPTIONS.items():
        if name in properties:
            properties[name]["description"] = description

    return {
        "type": "object",
        "properties": properties,
        "required": list(_ALWAYS_REQUIRED),
    }


def _ask_clarification_input_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "One specific question to ask the user. Conversational, not robotic.",
            },
            "reason": {
                "type": "string",
                "enum": list(CLARIFICATION_REASONS),
                "description": "Why the entry could not be recorded from what the user said.",
            },
        },
        "required": ["question", "reason"],
    }


def build_tool_config() -> dict:
    """Return the Converse API ``toolConfig`` for the parse turn.

    ``toolChoice: {"any": {}}`` forces the model to call exactly one of the two tools — it may
    choose *which*, but it may not answer with free text (Section 3.1.2).
    """
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": "propose_entry",
                    "description": _PROPOSE_ENTRY_DESCRIPTION,
                    "inputSchema": {"json": _propose_entry_input_schema()},
                }
            },
            {
                "toolSpec": {
                    "name": "ask_clarification",
                    "description": _ASK_CLARIFICATION_DESCRIPTION,
                    "inputSchema": {"json": _ask_clarification_input_schema()},
                }
            },
        ],
        "toolChoice": {"any": {}},
    }


def _extract_entries_input_schema() -> dict:
    """Wrap the per-entry ``propose_entry`` schema in an array under an ``entries`` key.

    Reusing :func:`_propose_entry_input_schema` keeps the bulk-parse contract identical to the
    single-turn parse contract — both derive from the same eight subtype models, so a resume
    candidate and a chat candidate validate against exactly the same rules (ADR-035).
    """
    return {
        "type": "object",
        "properties": {
            "entries": {
                "type": "array",
                "description": "Every distinct career entry found in the resume, in document order.",
                "items": _propose_entry_input_schema(),
            }
        },
        "required": ["entries"],
    }


def build_extract_tool_config() -> dict:
    """Return the Converse ``toolConfig`` for the resume bulk-extract turn (ADR-035).

    A single forced tool (``toolChoice: {"tool": ...}``): the model must return an ``entries``
    array, one element per distinct career item in the resume. ``resume_upload_parser`` validates
    each element against the same per-type discriminated union ``propose_entry`` uses, mints an
    ``entry_id`` per valid candidate, and hands the list to the review-table UI — which confirms
    each through the existing ``POST /entries`` (the single embedding site).
    """
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": "extract_entries",
                    "description": _EXTRACT_ENTRIES_DESCRIPTION,
                    "inputSchema": {"json": _extract_entries_input_schema()},
                }
            }
        ],
        "toolChoice": {"tool": {"name": "extract_entries"}},
    }
