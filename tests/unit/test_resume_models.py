"""Unit tests for the resume-agent Pydantic models + tool schemas (Section 3.2 / ADR-036)."""

import pytest
from pydantic import ValidationError

from careervault.pydantic_models.resume import (
    RETRIEVAL_TOOL_NAMES,
    Critique,
    RequirementsAnalysis,
    ResumeDocument,
    build_analysis_tool_config,
    build_critique_tool_config,
    build_draft_tool_config,
    build_retrieval_tool_config,
)


# --- RequirementsAnalysis (Phase 1) ---------------------------------------------------------------

def test_requirements_analysis_validates():
    analysis = RequirementsAnalysis.model_validate(
        {"requirements": ["AWS", "Python"], "sub_queries": ["cloud infra", "backend"], "target_type": "JD"}
    )
    assert analysis.target_type == "JD"
    assert len(analysis.sub_queries) == 2


def test_requirements_analysis_rejects_empty_lists():
    # The Phase 1→2 checkpoint: no requirements / sub-queries means nothing to retrieve on.
    with pytest.raises(ValidationError):
        RequirementsAnalysis.model_validate({"requirements": [], "sub_queries": ["x"], "target_type": "JD"})
    with pytest.raises(ValidationError):
        RequirementsAnalysis.model_validate({"requirements": ["x"], "sub_queries": [], "target_type": "JD"})


def test_requirements_analysis_rejects_bad_target_type():
    with pytest.raises(ValidationError):
        RequirementsAnalysis.model_validate({"requirements": ["x"], "sub_queries": ["y"], "target_type": "NOPE"})


# --- ResumeDocument (Phases 3/5) ------------------------------------------------------------------

def test_resume_document_minimal_is_valid():
    doc = ResumeDocument.model_validate({"summary": "A strong engineer."})
    assert doc.summary == "A strong engineer."
    assert doc.experience == []  # sections default empty


def test_resume_document_ignores_unknown_fields():
    # Lenient (extra="ignore"): a stray generated field is dropped, not a validation failure — a
    # generative payload shouldn't fail the whole draft over one unexpected key.
    doc = ResumeDocument.model_validate(
        {"summary": "x", "hobbies_section": ["chess"], "experience": [{"title": "Eng", "employer": "Acme", "bogus": 1}]}
    )
    assert not hasattr(doc, "hobbies_section")
    assert doc.experience[0].title == "Eng"
    assert not hasattr(doc.experience[0], "bogus")


def test_resume_document_requires_summary():
    with pytest.raises(ValidationError):
        ResumeDocument.model_validate({"skills": ["python"]})


def test_experience_item_requires_title_and_employer():
    with pytest.raises(ValidationError):
        ResumeDocument.model_validate({"summary": "x", "experience": [{"title": "Eng"}]})


# --- Critique (Phase 4) ---------------------------------------------------------------------------

def test_critique_validates_and_defaults():
    critique = Critique.model_validate({"verdict": "PASS"})
    assert critique.verdict == "PASS"
    assert critique.missing_requirements == []


def test_critique_rejects_bad_verdict():
    with pytest.raises(ValidationError):
        Critique.model_validate({"verdict": "MAYBE"})


# --- Tool configs ---------------------------------------------------------------------------------

def test_analysis_tool_config_forces_extract_requirements():
    config = build_analysis_tool_config()
    assert config["toolChoice"] == {"tool": {"name": "extract_requirements"}}
    (tool,) = config["tools"]
    assert tool["toolSpec"]["name"] == "extract_requirements"
    required = tool["toolSpec"]["inputSchema"]["json"]["required"]
    assert set(required) == {"requirements", "sub_queries", "target_type"}


def test_retrieval_tool_config_exposes_four_auto_tools():
    config = build_retrieval_tool_config()
    assert config["toolChoice"] == {"auto": {}}
    names = {t["toolSpec"]["name"] for t in config["tools"]}
    assert names == set(RETRIEVAL_TOOL_NAMES)


def test_draft_tool_config_forces_submit_resume_requiring_summary():
    config = build_draft_tool_config()
    assert config["toolChoice"] == {"tool": {"name": "submit_resume"}}
    schema = config["tools"][0]["toolSpec"]["inputSchema"]["json"]
    assert schema["required"] == ["summary"]
    assert "experience" in schema["properties"]


def test_critique_tool_config_forces_submit_critique():
    config = build_critique_tool_config()
    assert config["toolChoice"] == {"tool": {"name": "submit_critique"}}
    schema = config["tools"][0]["toolSpec"]["inputSchema"]["json"]
    assert schema["properties"]["verdict"]["enum"] == ["PASS", "REVISE"]
