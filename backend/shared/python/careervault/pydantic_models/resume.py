"""Pydantic models + Bedrock tool schemas for the resume agent (Section 3.2 / ADR-010 / ADR-036).

The resume agent uses tool use as a **control plane** (Section 3.2.0), not just structured output.
Its tools fall into two groups:

- **Retrieval / control-flow tools** the model calls to *act* — ``search_entries``, ``get_entry``,
  ``list_skills``, ``retrieval_done``. Their inputs are hand-written JSON schemas (the model
  produces them; the Lambda executes them). No Pydantic model — a loose input is fine because the
  Lambda validates the few fields it reads.
- **Structured-output tools** the model calls to *emit a payload* — ``extract_requirements``
  (Phase 1), ``submit_resume`` (Phases 3/5), ``submit_critique`` (Phase 4). Each has a Pydantic
  model here that is the validation gate; the hand-written tool schema mirrors it.

**Why the tool schemas are hand-written rather than derived from these models** (unlike
``tools.py``, which derives ``propose_entry`` from the entry models): ``propose_entry`` is a
*shared* contract — chat and the résumé parser must validate against the identical schema, so
deriving it from one source is load-bearing. These schemas are agent-only, and the models nest
(``ResumeDocument`` contains ``ExperienceItem`` …), which Pydantic renders with ``$defs``/``$ref``.
A concise hand-written schema is lower-risk to hand to Bedrock, and the Pydantic model is still the
authority on validity — so drift degrades to a validation retry (Section 3.2.8), never a bad write.
The models use ``extra="ignore"`` (not ``"forbid"``): a generative résumé payload should tolerate a
stray field by dropping it, not fail the whole draft.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Phase 1 — target analysis (extract_requirements)
# ---------------------------------------------------------------------------

TargetType = Literal["JD", "JOB_TITLE", "ASPIRATIONAL"]


class RequirementsAnalysis(BaseModel):
    """Structured decomposition of the target the user is aiming at (Section 3.2.2, Phase 1).

    ``sub_queries`` powers multi-query retrieval (query expansion): each is embedded and searched
    separately in Phase 2, giving better recall on a multi-faceted JD than one averaged vector.
    Both lists are required non-empty — that is the Phase 1→2 checkpoint (Section 3.2.6).
    """

    model_config = ConfigDict(extra="ignore")

    requirements: list[str] = Field(min_length=1, max_length=40)
    sub_queries: list[str] = Field(min_length=1, max_length=12)
    target_type: TargetType


# ---------------------------------------------------------------------------
# Phases 3 / 5 — the résumé document (submit_resume)
# ---------------------------------------------------------------------------


class ExperienceItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    employer: str
    location: str | None = None
    #: Display-formatted date range, e.g. "Jan 2021 – Present". The agent formats it; Phase 6 does
    #: not re-parse it.
    dates: str | None = None
    bullets: list[str] = Field(default_factory=list)


class ProjectItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str | None = None
    bullets: list[str] = Field(default_factory=list)
    url: str | None = None


class EducationItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    degree: str
    institution: str
    dates: str | None = None
    details: list[str] = Field(default_factory=list)


class CertItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    issuer: str | None = None
    date: str | None = None


class ResumeDocument(BaseModel):
    """The structured résumé the agent emits and Phase 6 renders (Section 3.2.2, Phase 3).

    Every named employer, institution, credential, project, and dated achievement here must trace
    to a retrieved entry — that constraint lives in the draft system prompt (the primary
    hallucination defense, Section 3.2.2). This model only enforces *shape*, not provenance.
    """

    model_config = ConfigDict(extra="ignore")

    summary: str
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    certs: list[CertItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 4 — critique (submit_critique)
# ---------------------------------------------------------------------------

CritiqueVerdict = Literal["PASS", "REVISE"]


class WeakSection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    section: str
    issue: str


class Critique(BaseModel):
    """A hiring-manager critique of a draft (Section 3.2.2, Phase 4).

    ``missing_requirements`` is what stagnation detection compares across revisions (Section 3.2.6):
    if a revise doesn't shrink this list, the loop stops paying Sonnet to fail the same way twice.
    """

    model_config = ConfigDict(extra="ignore")

    verdict: CritiqueVerdict
    missing_requirements: list[str] = Field(default_factory=list)
    weak_sections: list[WeakSection] = Field(default_factory=list)
    suggested_revisions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool configs (Converse ``toolConfig``)
# ---------------------------------------------------------------------------

#: The four Phase-2 retrieval/control tools, by name — used to interpret tool_use blocks.
RETRIEVAL_TOOL_NAMES: tuple[str, ...] = ("search_entries", "get_entry", "list_skills", "retrieval_done")


def _forced(name: str, description: str, schema: dict) -> dict:
    """A single-tool ``toolConfig`` that *forces* the model to call ``name`` (structured output)."""
    return {
        "tools": [{"toolSpec": {"name": name, "description": description, "inputSchema": {"json": schema}}}],
        "toolChoice": {"tool": {"name": name}},
    }


def build_analysis_tool_config() -> dict:
    """Phase 1: force ``extract_requirements`` (Haiku decomposes the target)."""
    schema = {
        "type": "object",
        "properties": {
            "requirements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Concrete skills/experiences/qualifications the target calls for.",
            },
            "sub_queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3–5 focused search phrases to retrieve matching career history, one facet each.",
            },
            "target_type": {
                "type": "string",
                "enum": ["JD", "JOB_TITLE", "ASPIRATIONAL"],
                "description": "JD = full job description; JOB_TITLE = a role name; ASPIRATIONAL = a goal/direction.",
            },
        },
        "required": ["requirements", "sub_queries", "target_type"],
    }
    return _forced(
        "extract_requirements",
        "Decompose the target role/JD into structured requirements and focused retrieval sub-queries.",
        schema,
    )


def build_retrieval_tool_config() -> dict:
    """Phase 2: the four retrieval tools with ``toolChoice: auto`` so the model drives the loop."""
    entry_types_enum = ["JOB", "PROJECT", "MILESTONE", "CERT", "AWARD", "EDUCATION", "VOLUNTEER", "HOBBY"]
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": "search_entries",
                    "description": (
                        "Semantic search over the user's career entries. Returns the most similar "
                        "entries (title, type, snippet, entry_id) for a query. Call once per sub-query, "
                        "and again for any gap you spot."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "What to search for."},
                                "top_k": {
                                    "type": "integer",
                                    "description": "How many results (default 10, max 25).",
                                },
                                "entry_types": {
                                    "type": "array",
                                    "items": {"type": "string", "enum": entry_types_enum},
                                    "description": "Optional filter to specific entry types.",
                                },
                            },
                            "required": ["query"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "get_entry",
                    "description": "Fetch the full detail of one entry by its entry_id (from a search result).",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"entry_id": {"type": "string"}},
                            "required": ["entry_id"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "list_skills",
                    "description": "Get the user's curated profile-level skills list.",
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
            {
                "toolSpec": {
                    "name": "retrieval_done",
                    "description": (
                        "Signal that you have gathered enough material to write the résumé. "
                        "Call this when further searches would be redundant."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "rationale": {
                                    "type": "string",
                                    "description": "One sentence on why retrieval is complete.",
                                }
                            },
                            "required": ["rationale"],
                        }
                    },
                }
            },
        ],
        "toolChoice": {"auto": {}},
    }


def _resume_schema() -> dict:
    """Hand-written JSON schema for ``submit_resume``, mirroring :class:`ResumeDocument`."""
    experience_item = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Role/job title."},
            "employer": {"type": "string"},
            "location": {"type": "string"},
            "dates": {"type": "string", "description": "Display range, e.g. 'Jan 2021 – Present'."},
            "bullets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Achievement bullets, tailored to the target. Lead with impact.",
            },
        },
        "required": ["title", "employer"],
    }
    project_item = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "bullets": {"type": "array", "items": {"type": "string"}},
            "url": {"type": "string"},
        },
        "required": ["name"],
    }
    education_item = {
        "type": "object",
        "properties": {
            "degree": {"type": "string"},
            "institution": {"type": "string"},
            "dates": {"type": "string"},
            "details": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["degree", "institution"],
    }
    cert_item = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "issuer": {"type": "string"},
            "date": {"type": "string"},
        },
        "required": ["name"],
    }
    return {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "2–4 sentence professional summary tailored to the target.",
            },
            "skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Skills relevant to the target, evidenced by the retrieved entries.",
            },
            "experience": {"type": "array", "items": experience_item},
            "projects": {"type": "array", "items": project_item},
            "education": {"type": "array", "items": education_item},
            "certs": {"type": "array", "items": cert_item},
        },
        "required": ["summary"],
    }


def build_draft_tool_config() -> dict:
    """Phases 3/5: force ``submit_resume`` (Sonnet emits/revises the structured résumé)."""
    return _forced(
        "submit_resume",
        (
            "Emit the tailored résumé as structured JSON. Every employer, institution, credential, "
            "project, and dated achievement MUST come from the retrieved career entries — never invent "
            "facts. Order and phrase content to match the target's requirements."
        ),
        _resume_schema(),
    )


def build_critique_tool_config() -> dict:
    """Phase 4: force ``submit_critique`` (Sonnet role-plays a critical hiring manager)."""
    schema = {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["PASS", "REVISE"],
                "description": "PASS if the résumé is strong for the target; REVISE if it needs work.",
            },
            "missing_requirements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Target requirements the résumé does not yet evidence.",
            },
            "weak_sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"section": {"type": "string"}, "issue": {"type": "string"}},
                    "required": ["section", "issue"],
                },
            },
            "suggested_revisions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Concrete, actionable fixes.",
            },
        },
        "required": ["verdict"],
    }
    return _forced(
        "submit_critique",
        "Critically evaluate the draft résumé against the target as a demanding hiring manager would.",
        schema,
    )
