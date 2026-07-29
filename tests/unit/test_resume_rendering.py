"""Unit tests for Phase 6 HTML rendering (Section 3.2.2 / ADR-018).

Only the HTML step is exercised — WeasyPrint's PDF conversion needs the native layer, so
``render_pdf`` is covered by the deployed smoke test, not here (it's imported lazily for exactly
this reason).
"""

from helpers import load_sibling

from careervault.pydantic_models.resume import ResumeDocument

rendering = load_sibling("resume_agent_rendering", "resume_agent", "rendering")

_CONTACT = {"name": None, "email": "dev@example.com", "phone": "555-0100", "location": None, "links": {"GitHub": "https://gh/x"}}


def _doc():
    return ResumeDocument.model_validate(
        {
            "summary": "Senior cloud engineer.",
            "skills": ["AWS", "Python"],
            "experience": [{"title": "Staff Engineer", "employer": "Acme", "dates": "2021–Present", "bullets": ["Cut costs 40%"]}],
            "certs": [{"name": "AWS SA Associate", "issuer": "AWS", "date": "2022"}],
        }
    )


def test_render_html_includes_all_sections():
    html = rendering.render_html(_doc(), contact=_CONTACT)
    assert "Senior cloud engineer." in html
    assert "Staff Engineer" in html
    assert "Acme" in html
    assert "Cut costs 40%" in html
    assert "AWS SA Associate" in html
    assert "dev@example.com" in html  # contact header
    assert "AWS · Python" in html  # skills joined


def test_render_html_omits_absent_sections():
    html = rendering.render_html(ResumeDocument.model_validate({"summary": "Just a summary."}), contact=_CONTACT)
    assert "Experience" not in html
    assert "Projects" not in html
    assert "Certifications" not in html


def test_render_html_escapes_injected_markup():
    # Autoescaping: a stray tag in a bullet is rendered as text, never executed.
    doc = ResumeDocument.model_validate({"summary": "x", "skills": ["<script>alert(1)</script>"]})
    html = rendering.render_html(doc, contact=_CONTACT)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
