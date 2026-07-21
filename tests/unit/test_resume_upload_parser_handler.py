"""Unit tests for resume_upload_parser — presign + parse routes (ADR-035).

Bedrock and S3 are faked; no test reaches AWS. The parser is parse-only, so these tests also pin
the properties that keep it that way: candidates come back *without* embeddings, and each carries a
freshly minted entry_id for the confirm step.
"""

import os
import sys
from pathlib import Path

import pytest
from helpers import FakeLambdaContext, api_event, body_of, load_handler, tool_use_response

from careervault import bedrock_client
from careervault.bedrock_client import BedrockError

_PARSER_DIR = Path(__file__).resolve().parents[2] / "backend" / "functions" / "resume_upload_parser"
if str(_PARSER_DIR) not in sys.path:
    sys.path.insert(0, str(_PARSER_DIR))

os.environ.setdefault("DATA_BUCKET_NAME", "careervault-data-test")

parser = load_handler("resume_parser_handler", "resume_upload_parser")

USER_PREFIX = "uploads/user-sub-1/"

VALID_CERT = {
    "entry_type": "CERT",
    "title": "AWS Solutions Architect Associate",
    "content": "Passed on the first attempt.",
    "issuer": "AWS",
    "issued_date": "2022-05-01",
}
VALID_JOB = {
    "entry_type": "JOB",
    "title": "Senior Engineer",
    "content": "Led the platform team.",
    "employer": "Acme",
    "start_date": "2021-01-01",
}
# JOB is missing its required employer + start_date — validate_entry rejects it, so the parser drops it.
INVALID_JOB = {"entry_type": "JOB", "title": "Contractor", "content": "Did things."}
# JOB carrying impact_metric — a MILESTONE-only field the permissive union schema invites the model
# to attach. Unsalvageable as-is (extra_forbidden), but the parser prunes the stray field and keeps it.
JOB_WITH_STRAY_FIELD = {
    "entry_type": "JOB",
    "title": "Staff Engineer",
    "content": "Ran the reliability org; cut incidents by half.",
    "employer": "Globex",
    "start_date": "2019-03-01",
    "impact_metric": "cut incidents 50%",
}


def _route(event: dict, resource: str) -> dict:
    event["resource"] = resource
    return event


# --- presign ----------------------------------------------------------------------------------

@pytest.fixture
def fake_presigner(monkeypatch):
    class _S3:
        def generate_presigned_url(self, op, Params, ExpiresIn):  # noqa: N803 (boto3 kwarg name)
            self.params = Params
            return "https://s3.example/signed-put"

    fake = _S3()
    monkeypatch.setattr(parser, "_s3", lambda: fake)
    return fake


def test_presign_returns_url_and_user_scoped_key(fake_presigner):
    event = _route(api_event({"filename": "resume.pdf", "content_type": "application/pdf"}), "/uploads/presign")
    response = parser.handler(event, FakeLambdaContext())
    body = body_of(response)

    assert response["statusCode"] == 200
    assert body["url"] == "https://s3.example/signed-put"
    assert body["content_type"] == "application/pdf"
    # The key is server-minted under this user's prefix — the browser can't point it elsewhere.
    assert body["key"].startswith(USER_PREFIX)
    assert body["key"].endswith(".pdf")
    # And that's exactly the object the URL was signed for.
    assert fake_presigner.params["Key"] == body["key"]
    assert fake_presigner.params["ContentType"] == "application/pdf"


def test_presign_rejects_unsupported_type(fake_presigner):
    event = _route(api_event({"filename": "resume.txt", "content_type": "text/plain"}), "/uploads/presign")
    response = parser.handler(event, FakeLambdaContext())
    assert response["statusCode"] == 415


# --- parse ------------------------------------------------------------------------------------

@pytest.fixture
def fake_parse(monkeypatch):
    """Stub the S3 read and text extraction so parse tests exercise only the parser's own logic."""
    monkeypatch.setattr(parser, "_download", lambda bucket, key: b"%PDF-bytes")
    monkeypatch.setattr(parser, "extract_text", lambda data, filename=None: "A resume with plenty of text.")


def _mock_converse(monkeypatch, entries):
    monkeypatch.setattr(
        bedrock_client, "converse", lambda *a, **k: tool_use_response("extract_entries", {"entries": entries})
    )


def test_parse_returns_validated_candidates_and_drops_invalid(monkeypatch, fake_parse):
    _mock_converse(monkeypatch, [VALID_CERT, INVALID_JOB, VALID_JOB])
    event = _route(api_event({"key": f"{USER_PREFIX}01.pdf"}), "/uploads/parse")

    response = parser.handler(event, FakeLambdaContext())
    body = body_of(response)

    assert response["statusCode"] == 200
    assert len(body["candidates"]) == 2  # the invalid JOB was dropped
    assert body["dropped"] == 1
    types = {c["entry_type"] for c in body["candidates"]}
    assert types == {"CERT", "JOB"}
    for candidate in body["candidates"]:
        # Parse-only: no embedding vector rides along, and every candidate gets a fresh entry_id.
        assert "embedding" not in candidate
        assert len(candidate["entry_id"]) == 26
    assert body["char_count"] > 0
    assert "parse_ms" in body


def test_parse_salvages_an_entry_with_a_stray_out_of_type_field(monkeypatch, fake_parse):
    # The JOB carries impact_metric (a MILESTONE field); the parser prunes it and keeps the entry
    # rather than dropping a whole job because of one misplaced field.
    _mock_converse(monkeypatch, [JOB_WITH_STRAY_FIELD])
    event = _route(api_event({"key": f"{USER_PREFIX}01.pdf"}), "/uploads/parse")

    body = body_of(parser.handler(event, FakeLambdaContext()))
    assert body["dropped"] == 0
    assert len(body["candidates"]) == 1
    saved = body["candidates"][0]
    assert saved["entry_type"] == "JOB"
    assert saved["employer"] == "Globex"
    assert "impact_metric" not in saved  # the stray field was pruned


def test_parse_backfills_missing_content_from_title(monkeypatch, fake_parse):
    # A terse CERT line has no description, so the model omits the required `content`; the parser
    # backfills it from the title rather than dropping the certification.
    cert = {
        "entry_type": "CERT",
        "title": "AWS Certified Solutions Architect – Associate",
        "issuer": "Amazon Web Services",
        "issued_date": "2022-03-01",
    }
    _mock_converse(monkeypatch, [cert])
    event = _route(api_event({"key": f"{USER_PREFIX}01.pdf"}), "/uploads/parse")

    body = body_of(parser.handler(event, FakeLambdaContext()))
    assert body["dropped"] == 0
    assert body["candidates"][0]["content"] == cert["title"]


def test_parse_rejects_a_key_outside_the_users_prefix(monkeypatch, fake_parse):
    _mock_converse(monkeypatch, [VALID_CERT])
    event = _route(api_event({"key": "uploads/someone-else/01.pdf"}), "/uploads/parse")
    response = parser.handler(event, FakeLambdaContext())
    assert response["statusCode"] == 400


def test_parse_404_when_upload_missing(monkeypatch):
    monkeypatch.setattr(parser, "_download", lambda bucket, key: None)
    event = _route(api_event({"key": f"{USER_PREFIX}01.pdf"}), "/uploads/parse")
    assert parser.handler(event, FakeLambdaContext())["statusCode"] == 404


def test_parse_413_when_too_large(monkeypatch):
    def _too_large(bucket, key):
        raise parser._UploadTooLarge

    monkeypatch.setattr(parser, "_download", _too_large)
    event = _route(api_event({"key": f"{USER_PREFIX}01.pdf"}), "/uploads/parse")
    assert parser.handler(event, FakeLambdaContext())["statusCode"] == 413


def test_download_rejects_oversized_object_before_reading_it(monkeypatch):
    # ContentLength (a header) is checked before Body.read(), so an oversized object never lands
    # in memory — the presigned PUT can't cap size, so this is the real guard.
    read_called = {"v": False}

    class _Body:
        def read(self):
            read_called["v"] = True
            return b"x" * 999

    class _S3:
        def get_object(self, Bucket, Key):  # noqa: N803
            return {"ContentLength": parser._MAX_UPLOAD_BYTES + 1, "Body": _Body()}

    monkeypatch.setattr(parser, "_s3", lambda: _S3())
    with pytest.raises(parser._UploadTooLarge):
        parser._download("bucket", f"{USER_PREFIX}01.pdf")
    assert read_called["v"] is False  # never read the body


def test_parse_422_when_no_text_extracted(monkeypatch):
    monkeypatch.setattr(parser, "_download", lambda bucket, key: b"%PDF")
    monkeypatch.setattr(parser, "extract_text", lambda data, filename=None: "")
    event = _route(api_event({"key": f"{USER_PREFIX}01.pdf"}), "/uploads/parse")
    assert parser.handler(event, FakeLambdaContext())["statusCode"] == 422


def test_parse_502_on_bedrock_failure(monkeypatch, fake_parse):
    def _boom(*a, **k):
        raise BedrockError("down")

    monkeypatch.setattr(bedrock_client, "converse", _boom)
    event = _route(api_event({"key": f"{USER_PREFIX}01.pdf"}), "/uploads/parse")
    assert parser.handler(event, FakeLambdaContext())["statusCode"] == 502


def test_parse_empty_entries_returns_zero_candidates(monkeypatch, fake_parse):
    _mock_converse(monkeypatch, [])
    event = _route(api_event({"key": f"{USER_PREFIX}01.pdf"}), "/uploads/parse")
    body = body_of(parser.handler(event, FakeLambdaContext()))
    assert body["candidates"] == []
    assert body["dropped"] == 0


# --- routing / auth ---------------------------------------------------------------------------

def test_unknown_route_is_404():
    event = _route(api_event({}), "/uploads/other")
    assert parser.handler(event, FakeLambdaContext())["statusCode"] == 404


def test_missing_sub_is_401():
    event = _route(api_event({"filename": "resume.pdf"}, sub=None), "/uploads/presign")
    assert parser.handler(event, FakeLambdaContext())["statusCode"] == 401
