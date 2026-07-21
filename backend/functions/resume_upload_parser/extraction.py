"""PDF/DOCX → plain text for ``resume_upload_parser`` (ADR-035, slice 5).

Function-local rather than in the shared layer on purpose: only this Lambda parses files, and the
shared layer is attached to all seven functions — bundling a PDF reader into the other six buys
nothing.

**Genuinely pure-Python, so no Docker build** (unlike the WeasyPrint layer):
- PDF via ``pypdf`` (pure Python, imported lazily so the presign route pays nothing for it).
- DOCX via the standard library — a ``.docx`` is a ZIP whose ``word/document.xml`` holds the text,
  so ``zipfile`` + ``xml.etree`` extract it without ``python-docx`` (which drags in the compiled
  ``lxml`` — a binary wheel that would need a container build to match Lambda's arm64 Linux).
"""

from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

#: Upload types we accept. ``.doc`` (legacy binary Word) is intentionally excluded — it needs a
#: heavyweight extractor (antiword/LibreOffice); ADR-013 commits to PDF + DOCX only.
CONTENT_TYPE_BY_EXT: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(CONTENT_TYPE_BY_EXT)


class UnsupportedFileType(ValueError):
    """The upload isn't a PDF or DOCX we can parse."""


def ext_from_filename(filename: str) -> str:
    """Lowercased extension without the dot, e.g. ``resume.PDF`` → ``pdf`` (``""`` if none)."""
    head, sep, ext = (filename or "").rpartition(".")
    # rpartition returns the whole string in the last slot when no "." is present; a real
    # extension only exists when there was a separator *and* something before it.
    return ext.lower() if sep and head else ""


def resolve_kind(*, filename: str | None = None, content_type: str | None = None) -> str:
    """Return the parse kind (``"pdf"`` / ``"docx"``) from a filename or content type.

    The filename extension is the primary signal (what the user actually uploaded); content type
    is a fallback. Raises :class:`UnsupportedFileType` for anything else.
    """
    ext = ext_from_filename(filename or "")
    if ext in ALLOWED_EXTENSIONS:
        return ext

    ct = (content_type or "").split(";", 1)[0].strip().lower()
    for kind, known in CONTENT_TYPE_BY_EXT.items():
        if ct == known:
            return kind

    raise UnsupportedFileType(
        f"Unsupported upload (filename={filename!r}, content_type={content_type!r}); "
        "only PDF and DOCX are accepted."
    )


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader  # lazy: only resume_upload_parser installs this

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


#: WordprocessingML namespace — every text-bearing element is qualified with it.
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _extract_docx(data: bytes) -> str:
    """Extract text from a .docx using only the standard library.

    ``word/document.xml`` holds the body; text lives in ``<w:t>`` runs grouped into ``<w:p>``
    paragraphs. Iterating each paragraph's descendants in document order captures body *and* table
    text (table cells contain their own ``<w:p>`` elements), with tabs/breaks preserved so
    space-separated resume fields don't collide.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml = archive.read("word/document.xml")

    root = ET.fromstring(xml)
    lines: list[str] = []
    for para in root.iter(f"{_W}p"):
        buf: list[str] = []
        for node in para.iter():
            if node.tag == f"{_W}t" and node.text:
                buf.append(node.text)
            elif node.tag == f"{_W}tab":
                buf.append("\t")
            elif node.tag == f"{_W}br":
                buf.append("\n")
        lines.append("".join(buf))
    return "\n".join(lines)


def extract_text(data: bytes, *, filename: str | None = None, content_type: str | None = None) -> str:
    """Extract plain text from an uploaded resume's bytes.

    Raises:
        UnsupportedFileType: for anything other than PDF/DOCX.
    """
    kind = resolve_kind(filename=filename, content_type=content_type)
    text = _extract_pdf(data) if kind == "pdf" else _extract_docx(data)
    # Collapse the runs of blank lines PDF extraction tends to produce.
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
