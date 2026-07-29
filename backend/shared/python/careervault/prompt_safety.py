"""Prompt-level containment for user-supplied text (ADR-038, defense in depth).

Entry `title`/`content` can originate in an **uploaded file** (slice 5): a résumé is parsed into
entries by Haiku, so text a user never wrote can end up stored and later replayed into a model
prompt. That is indirect prompt injection, and this module holds the cheap, uniform hygiene applied
wherever such text is interpolated.

**This is hygiene on top of the real controls, not a substitute for them.** ADR-038 is explicit that
prompt-level containment is defense in depth and is never counted on. What actually bounds the
damage is architectural — the call that sees entry content carries no tools, its output is validated
into fixed fields, and those fields render through autoescaping templates. Still worth being
complete: *a control documented as "we delimit the data" should actually delimit it.*

Lifted into the shared layer during slice 8. It began as a private helper in ``chat/qa.py``, and the
check-in prompt builder — written months later against the same threat, with the same uploaded-file
provenance — silently did not have it. Two prompt builders with one shared risk should not carry two
implementations, one of which is empty.
"""

from __future__ import annotations

#: Every structural tag any prompt in this codebase uses to delimit a data region. Defanging only
#: ``</entry>`` is not enough: closing an *outer* tag escapes the region just as effectively, and an
#: injected résumé that knows the prompt shape reaches for the outermost one first. (That gap was
#: found by the slice-7 security review and fixed there; the list is shared so a new region name
#: added to one prompt is defanged in all of them.)
STRUCTURAL_TAGS: tuple[str, ...] = (
    "career_history",
    "census",
    "relevant_entries",
    "entry",
    "recent_entries",
)


def neutralise_delimiters(text: str) -> str:
    """Defang structural tags inside user-supplied content so it cannot close its own data region.

    Neutralises those *specific sequences* rather than stripping angle brackets wholesale, so
    ordinary technical writing — ``List<String>``, ``a -> b`` — survives intact. Mangling a user's
    own résumé text to defend against a threat the architecture already bounds would be a bad trade.
    """
    for tag in STRUCTURAL_TAGS:
        text = text.replace(f"</{tag}", f"&lt;/{tag}").replace(f"<{tag}", f"&lt;{tag}")
    return text


def flatten(text: str) -> str:
    """Collapse newlines so a single field cannot forge extra lines in a line-oriented prompt.

    Matters wherever a prompt puts one record per line. A field carrying ``\\n`` renders as *new
    prompt lines*, which is a structural escape even when no delimiter tag is involved — the
    check-in prompt normalised `content` this way but not `title`, and `title` permits 200
    characters of arbitrary text.
    """
    return " ".join(text.split())


def sanitize_for_prompt(value: object) -> str:
    """Both treatments, for any value about to be interpolated into a prompt."""
    return neutralise_delimiters(flatten(str(value or "")))
