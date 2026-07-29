"""Render a composed check-in to the HTML and plain-text bodies SES sends.

Both bodies are built from the same validated :class:`CheckinEmail`, so they cannot drift. The
plain-text part is not optional politeness: a multipart message with only an HTML part is a
well-known spam signal, and it is what a text-only client actually displays.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from careervault.pydantic_models.checkin import CheckinEmail

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    # Unconditionally on. `select_autoescape` keys off the file extension and would not recognise
    # `.j2`, and everything rendered here is model- or user-derived — the same reasoning as the
    # résumé template.
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_html(email: CheckinEmail, *, dashboard_url: str, settings_url: str) -> str:
    """Render the HTML body."""
    return _env.get_template("checkin.html.j2").render(
        email=email,
        dashboard_url=dashboard_url,
        settings_url=settings_url,
    )


def render_text(email: CheckinEmail, *, dashboard_url: str, settings_url: str) -> str:
    """Render the plain-text alternative.

    Built in Python rather than as a second Jinja2 template: it is a handful of joins, and keeping
    it beside the model makes it obvious when a new field needs adding to both parts.
    """
    lines: list[str] = [email.greeting, ""]

    if email.recent_activity_summary:
        lines += [email.recent_activity_summary, ""]

    lines += [f"- {prompt}" for prompt in email.prompts]
    if email.prompts:
        lines.append("")

    if email.aspirational_link:
        lines += [email.aspirational_link, ""]

    lines += [
        f"Log an update: {dashboard_url}",
        "",
        email.sign_off,
        "",
        "--",
        f"Change how often you get these, or pause them: {settings_url}",
    ]
    return "\n".join(lines)
