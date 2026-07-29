"""Unit tests for resume_upload_parser's PDF/DOCX text extraction (ADR-035).

The real pypdf/python-docx extraction is exercised end-to-end at deploy time; here we pin the pure
dispatch logic (which extractor for which file) and the whitespace normalisation, with the binary
extractors stubbed so the suite needs no file fixtures or extra dependencies.
"""

import io
import zipfile

import pytest
from helpers import load_sibling

extraction = load_sibling("resume_upload_parser_extraction", "resume_upload_parser", "extraction")


def test_ext_from_filename_is_lowercased_and_dotless():
    assert extraction.ext_from_filename("Resume.PDF") == "pdf"
    assert extraction.ext_from_filename("my.CV.docx") == "docx"
    assert extraction.ext_from_filename("noextension") == ""


def test_resolve_kind_prefers_the_filename():
    assert extraction.resolve_kind(filename="resume.pdf") == "pdf"
    assert extraction.resolve_kind(filename="resume.docx") == "docx"


def test_resolve_kind_falls_back_to_content_type():
    assert extraction.resolve_kind(filename="", content_type="application/pdf") == "pdf"
    assert (
        extraction.resolve_kind(
            filename="blob",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        == "docx"
    )


def test_resolve_kind_rejects_unsupported():
    with pytest.raises(extraction.UnsupportedFileType):
        extraction.resolve_kind(filename="resume.doc", content_type="application/msword")
    with pytest.raises(extraction.UnsupportedFileType):
        extraction.resolve_kind(filename="resume.txt")


def test_extract_text_dispatches_by_kind_and_collapses_blank_lines(monkeypatch):
    monkeypatch.setattr(extraction, "_extract_pdf", lambda data: "Line 1\n\n\n   \nLine 2\n")
    out = extraction.extract_text(b"%PDF-fake", filename="resume.pdf")
    # Blank/whitespace-only lines are dropped, and trailing spaces trimmed.
    assert out == "Line 1\nLine 2"


def test_extract_text_uses_docx_extractor_for_docx(monkeypatch):
    monkeypatch.setattr(extraction, "_extract_docx", lambda data: "docx body")
    monkeypatch.setattr(extraction, "_extract_pdf", lambda data: pytest.fail("used PDF path"))
    assert extraction.extract_text(b"PK-fake", filename="resume.docx") == "docx body"


_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _minimal_docx(paragraphs: list[str]) -> bytes:
    """Build the smallest valid-enough .docx (a ZIP with word/document.xml) for the stdlib parser."""
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>' for text in paragraphs
    )
    document = f'<?xml version="1.0"?><w:document xmlns:w="{_W}"><w:body>{body}</w:body></w:document>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def test_extract_docx_reads_paragraphs_from_a_real_zip():
    # Exercises the actual stdlib extractor (no python-docx / lxml), one line per <w:p>.
    data = _minimal_docx(["Senior Engineer at Acme", "AWS SA Associate — 2022"])
    out = extraction.extract_text(data, filename="resume.docx")
    assert out == "Senior Engineer at Acme\nAWS SA Associate — 2022"
