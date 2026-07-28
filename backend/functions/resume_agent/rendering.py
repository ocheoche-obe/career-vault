"""Phase 6 deterministic rendering — structured résumé → HTML → PDF (Section 3.2.2 / ADR-018).

No LLM here: a validated :class:`~careervault.pydantic_models.resume.ResumeDocument` is rendered
through one Jinja2 template to HTML (the in-app preview and the PDF share this single source of
layout, ADR-018), then WeasyPrint converts that HTML to PDF.

**WeasyPrint is imported lazily**, inside :func:`render_pdf`, so this module imports fine in the
unit-test environment (and during ``import`` of the handler) where the ``careervault-weasyprint``
layer's native libraries (Pango/Cairo) are absent. Jinja2 is a pure-Python dependency bundled with
the function, so HTML rendering has no such constraint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from careervault.pydantic_models.resume import ResumeDocument

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_TEMPLATE_NAME = "resume.html.j2"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    # Always escape: this template only ever renders HTML, and its content is LLM- and user-derived,
    # so every value must be escaped. (`select_autoescape` keys off the file extension, which the
    # `.j2` suffix would defeat — an unconditional True is both simpler and safe here.)
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_html(document: ResumeDocument, *, contact: dict[str, Any]) -> str:
    """Render the résumé document + contact header to a self-contained HTML string.

    ``contact`` carries only deterministic profile data (name/email/phone/links) — never
    LLM-generated — so the document body stays the agent's responsibility and identity stays the
    profile's. Autoescaping means any stray markup in a bullet is rendered as text, not executed.
    """
    template = _env.get_template(_TEMPLATE_NAME)
    return template.render(doc=document, contact=contact)


def render_pdf(html: str) -> bytes:
    """Convert rendered HTML to PDF bytes via WeasyPrint (layer-provided, imported lazily)."""
    from weasyprint import HTML  # noqa: PLC0415 — deferred so non-PDF paths need no native deps

    return HTML(string=html).write_pdf()
