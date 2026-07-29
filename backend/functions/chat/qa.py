"""Grounding helpers for the chat Q&A path (ADR-038).

Everything here is a **pure function of DynamoDB items** — no Bedrock, no boto3, no I/O. That is
deliberate rather than incidental: ADR-038 puts retrieval under the Lambda's control precisely so
that what the model sees is decided by testable code rather than by the model itself. Keeping this
module I/O-free is what makes that claim checkable in unit tests.

Two jobs:

1. **Census** — counts by ``entry_type`` over the *whole* corpus. ``query_entries`` already reads
   every entry (paginated to completion, §2.5 AP-10), so the totals are free. This is what lets
   "how many certs do I have?" be answered correctly without a structured-filter branch: semantic
   top-k hands the model k entries, and a model asked to count k things answers "k" — confidently
   wrong. Python counts; the model only narrates (ADR-038, "Aggregate questions").
2. **Grounding block** — the delimited, projected entry text handed to the synthesis call.

On the projection being an allowlist derived from the entity models: a denylist would work today,
but any internal field added to an entry item later would silently start flowing into a model
prompt. Deriving the allowed names from the eight subtype models means a new *user* field is
included automatically while a new *internal* one is excluded automatically — the same
single-source-of-truth trick :mod:`careervault.pydantic_models.tools` uses for the parse schema.
It is also what keeps the ~1024-float ``embedding`` out of the prompt, which is a cost bug as much
as a hygiene one.
"""

from __future__ import annotations

from typing import Any, Sequence

from careervault.pydantic_models.entry import ENTRY_TYPES, SUBTYPE_MODELS

#: Entry attributes the model may see, derived from the entity models so the set cannot drift.
#: `entry_id` is excluded: it is a ULID the user never refers to, it costs tokens, and echoing it
#: into prose invites the model to cite an opaque identifier at the user.
_PROMPT_FIELDS: frozenset[str] = frozenset(
    name
    for model in SUBTYPE_MODELS
    for name in model.model_fields
    if name != "entry_id"
)

#: Per-entry content cap. Entries allow 5000 chars; at top-k 8 that is a 40K-char prompt in the
#: worst case for no benefit — the first paragraphs carry the substance. Truncation is marked so
#: the model can say "the entry continues" rather than treating the tail as absent.
_MAX_CONTENT_CHARS = 1200

#: How many entries the synthesis call sees. Small on purpose: this is a chat turn, the corpus is
#: one career, and every entry is a second Haiku prompt's worth of tokens.
TOP_K = 8

_TRUNCATION_MARKER = " …[entry continues]"


def build_census(entries: Sequence[dict]) -> dict[str, int]:
    """Count entries by type across the whole corpus, plus a ``total``.

    Every known type is present with an explicit ``0`` rather than omitted. An absent key reads to
    a model as "unknown"; a zero reads as "none", which is the answer the user is owed when they
    ask about a type they have never logged.
    """
    census = {entry_type: 0 for entry_type in ENTRY_TYPES}
    for item in entries:
        entry_type = item.get("entry_type")
        if entry_type in census:
            census[entry_type] += 1
    census["total"] = len(entries)
    return census


def render_census(census: dict[str, int]) -> str:
    """Render the census as one compact line per non-empty type (~50 tokens all in)."""
    lines = [
        f"  {entry_type}: {count}"
        for entry_type, count in census.items()
        if entry_type != "total" and count
    ]
    if not lines:
        return "  (no entries recorded)"
    return "\n".join(lines) + f"\n  TOTAL: {census['total']}"


#: Every tag that gives the grounding block its structure. Content is defanged against *all* of
#: them, not just ``<entry>`` — closing ``</relevant_entries></career_history>`` escapes the data
#: region just as effectively as closing a single entry, and an injected résumé that knows the
#: prompt shape would reach for the outermost tag first.
_STRUCTURAL_TAGS = ("career_history", "census", "relevant_entries", "entry")


def _neutralise_delimiters(text: str) -> str:
    """Defang the grounding block's structural tags inside user-supplied content.

    An entry whose text contains ``</entry>`` — or ``</relevant_entries>``, or
    ``</career_history>`` — could otherwise close the data region early and have the remainder
    read as prompt rather than data. That is the cheapest possible delimiter escape, and the one
    an injected résumé would actually try (entry content can originate in an uploaded file, slice
    5). Neutralising these *specific sequences* rather than stripping all angle brackets keeps
    ordinary technical writing ("List<String>", "a -> b") intact.

    This is hygiene on top of the real controls (the synthesis call has no tools at all, and its
    output is rendered as text) — not a substitute for them. ADR-038 is explicit that prompt-level
    containment is defense in depth and is not counted on. It is still worth being complete: a
    control documented as "we delimit the data" should actually delimit it.
    """
    for tag in _STRUCTURAL_TAGS:
        text = text.replace(f"</{tag}", f"&lt;/{tag}").replace(f"<{tag}", f"&lt;{tag}")
    return text


def project_entry(item: dict) -> dict[str, Any]:
    """Reduce a stored entry item to the allowlisted fields the model may see.

    Drops the embedding, the DynamoDB keys, and every internal timestamp; caps ``content``; and
    coerces values to ``str`` so ``Decimal``/``date`` from DynamoDB render predictably.
    """
    projected: dict[str, Any] = {}
    for name, value in item.items():
        if name not in _PROMPT_FIELDS or value in (None, "", []):
            continue
        if isinstance(value, list):
            rendered = ", ".join(str(v) for v in value)
        else:
            rendered = str(value)
        if name == "content" and len(rendered) > _MAX_CONTENT_CHARS:
            rendered = rendered[:_MAX_CONTENT_CHARS] + _TRUNCATION_MARKER
        projected[name] = _neutralise_delimiters(rendered)
    return projected


def render_grounding(census: dict[str, int], ranked: Sequence[tuple[dict, float]]) -> str:
    """Build the delimited grounding block for the synthesis prompt.

    The census describes the *whole* corpus; the entries are the *nearest* slice. Saying which is
    which matters — without it a model asked "how many certs?" counts the entries in front of it.
    """
    blocks = []
    for position, (item, _score) in enumerate(ranked, start=1):
        fields = "\n".join(f"  {name}: {value}" for name, value in project_entry(item).items())
        blocks.append(f"<entry n=\"{position}\">\n{fields}\n</entry>")

    entries_text = "\n".join(blocks) if blocks else "  (no entries matched this question)"

    return (
        "<career_history>\n"
        "<census note=\"counts across ALL recorded entries, not just those shown below\">\n"
        f"{render_census(census)}\n"
        "</census>\n"
        "<relevant_entries note=\"the entries most similar to the question; NOT the full history\">\n"
        f"{entries_text}\n"
        "</relevant_entries>\n"
        "</career_history>"
    )


def source_refs(ranked: Sequence[tuple[dict, float]]) -> list[dict[str, Any]]:
    """Compact citations for the UI, so an answer can be checked against what produced it.

    Titles and types only — enough to recognise an entry, and nothing the caller does not already
    have the right to read.
    """
    return [
        {
            "entry_id": item.get("entry_id"),
            "entry_type": item.get("entry_type"),
            "title": item.get("title"),
            "score": round(float(score), 4),
        }
        for item, score in ranked
    ]
