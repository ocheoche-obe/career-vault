"""resume_upload_parser — resume bootstrap (ADR-013 / ADR-035, slice 5).

Two routes, one self-contained upload Lambda. It is a **parse-only** transform: it never embeds
and never writes to DynamoDB. Embedding stays at the single confirm site (``career_crud``'s
``POST /entries``), which each reviewed candidate is saved through — so ADR-033 dedup and §3.1.4
idempotency cover uploaded entries for free.

- ``POST /uploads/presign`` — mint a short-lived presigned S3 **PUT** URL scoped to
  ``uploads/<user_id>/…`` so the browser uploads the file straight to S3, off the compute plane.
- ``POST /uploads/parse``   — read the uploaded object, extract text (PDF/DOCX), make one Claude
  Haiku ``extract_entries`` pass, validate each candidate against the per-type discriminated
  union, mint an ``entry_id`` per valid one, and return the list synchronously.

IAM: ``s3:PutObject`` + ``s3:GetObject`` on ``uploads/*`` and Bedrock InvokeModel on the Haiku
profile (ADR-031). No Titan grant, no DynamoDB grant — enforced by the SAM policy and relied on
here (Section 4.2.4 defense-in-depth: the ``uploads/<user_id>/`` prefix is asserted in code because
IAM can't scope to a per-request user).
"""

from __future__ import annotations

import json
import os
import time

import boto3
from aws_lambda_powertools.metrics import MetricUnit
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import ValidationError

from careervault import bedrock_client
from careervault.bedrock_client import BedrockError
from careervault.ddb_helpers import extract_user_id, new_ulid
from careervault.observability import bind_request_context, logger, metrics, tracer
from careervault.pydantic_models.entry import validate_entry
from careervault.pydantic_models.tools import build_extract_tool_config

from extraction import (
    ALLOWED_EXTENSIONS,
    CONTENT_TYPE_BY_EXT,
    UnsupportedFileType,
    ext_from_filename,
    extract_text,
    resolve_kind,
)

_CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "http://localhost:5173"),
}

#: The uploaded file never transits this Lambda's request/response — it goes browser→S3 via the
#: presigned PUT — but the parse route reads it back, so cap the bytes we'll pull and extract.
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB — a very large resume is a few hundred KB.
#: Bound the text handed to Haiku so token cost/latency stay predictable regardless of file size.
_MAX_TEXT_CHARS = 40_000
#: Below this, extraction effectively found nothing (e.g. a scanned-image PDF with no text layer).
_MIN_TEXT_CHARS = 20
_PRESIGN_EXPIRY_SECONDS = 300
#: An array of entries is larger than a single propose_entry call — give the model room.
_EXTRACT_MAX_TOKENS = 8_192

_SYSTEM_PROMPT = """\
You are CareerVault's resume parser. You are given the plain text of a user's resume. Extract every \
distinct career entry into the extract_entries tool — one array element per job, project, \
certification, award, degree, volunteer role, or notable milestone.

Rules:
- One entry per distinct item, in the order it appears in the resume.
- Choose the most specific entry_type that fits. A certification is CERT, not MILESTONE.
- Use only what the resume states. Never invent dates, employers, issuers, or metrics; omit any \
optional field the resume does not give you.
- title and content are both required. Put the person's description of the item — including \
quantified impact ("cut costs 38%") — into content; keep the headline in title. When the resume \
gives no separate description (common for certifications and awards), set content to a brief \
restatement of the item. Do not use fields that don't belong to the entry_type.
- Dates must be ISO YYYY-MM-DD; use the first of the month/year when only a month or year is given, \
and omit end_date for anything ongoing ("Present").
- If the text contains nothing recordable, return an empty entries array."""

_s3_client = None


def _s3():
    """Cached S3 client with SigV4 presigning (stable across warm invocations)."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", config=Config(signature_version="s3v4"))
    return _s3_client


def _response(status_code: int, body: dict) -> dict:
    return {"statusCode": status_code, "headers": _CORS_HEADERS, "body": json.dumps(body)}


def _uploads_prefix(user_id: str) -> str:
    return f"uploads/{user_id}/"


def _extract_tool_use(response: dict) -> dict | None:
    """Pull the single ``toolUse`` block out of a Converse response, if present."""
    for block in response.get("output", {}).get("message", {}).get("content", []):
        if "toolUse" in block:
            return block["toolUse"]
    return None


def _validate_candidate(raw: dict) -> object | None:
    """Validate one extracted entry, salvaging a fixable near-miss instead of dropping it.

    The ``propose_entry`` schema the model fills is a *permissive union* of every subtype's fields
    (Section 3.1.2), and a resume line is often terse — so two near-misses are common and safe to
    repair rather than lose a whole entry over:

    - **A field belonging to another subtype** (``extra_forbidden``) — most often ``impact_metric``
      (a MILESTONE field) attached to a JOB whose bullets quantify impact. The stray field is
      dropped; its information is already in ``content``.
    - **Missing ``content``** on an item with no description (typical of certifications/awards) —
      backfilled from ``title``. This restates a fact the model already extracted, not a fabrication.

    Chat recovers from these via its validation-retry loop (Section 3.1.6); the bulk parser has no
    such loop, so it applies these narrow repairs and revalidates once. Anything still invalid — a
    genuinely missing required field like a JOB's ``employer`` — is dropped.
    """
    try:
        return validate_entry(raw)
    except ValidationError as exc:
        fixed = dict(raw)
        changed = False
        for err in exc.errors():
            field = err["loc"][-1]
            if err.get("type") == "extra_forbidden":
                fixed.pop(field, None)
                changed = True
            elif err.get("type") == "missing" and field == "content" and fixed.get("title"):
                fixed["content"] = fixed["title"]
                changed = True
        if not changed:
            return None
        try:
            return validate_entry(fixed)
        except ValidationError:
            return None


def _presign(user_id: str, body: dict) -> dict:
    """Mint a presigned PUT URL for a new ``uploads/<user_id>/<ulid>.<ext>`` object."""
    filename = (body.get("filename") or "").strip()
    content_type = (body.get("content_type") or "").strip()

    try:
        kind = resolve_kind(filename=filename, content_type=content_type)
    except UnsupportedFileType:
        return _response(
            415,
            {"message": f"Only PDF and DOCX resumes are supported ({', '.join(sorted(ALLOWED_EXTENSIONS))})."},
        )

    resolved_content_type = CONTENT_TYPE_BY_EXT[kind]
    # We name the key (not the client) so it always lands under this user's prefix — the browser
    # only ever sees a key it cannot point elsewhere.
    key = f"{_uploads_prefix(user_id)}{new_ulid()}.{kind}"

    try:
        url = _s3().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": os.environ["DATA_BUCKET_NAME"],
                "Key": key,
                "ContentType": resolved_content_type,
            },
            ExpiresIn=_PRESIGN_EXPIRY_SECONDS,
        )
    except ClientError:
        logger.exception("Failed to presign upload URL")
        return _response(500, {"message": "Could not start the upload — please retry."})

    metrics.add_metric(name="UploadPresigned", unit=MetricUnit.Count, value=1)
    logger.info("Presigned upload URL issued", extra={"kind": kind})
    # The browser must PUT with exactly this Content-Type for the signature to match.
    return _response(200, {"url": url, "key": key, "content_type": resolved_content_type})


class _UploadTooLarge(Exception):
    """The uploaded object is larger than we'll read into memory."""


def _download(bucket: str, key: str) -> bytes | None:
    """Fetch the uploaded object's bytes, or ``None`` if it isn't there (client raced/aborted).

    The size is checked against ``ContentLength`` (a response header, available *before* the body
    is streamed) so an oversized upload is rejected without first reading it into the Lambda's
    memory — the presigned PUT itself can't cap object size, so this is the effective guard.
    """
    try:
        obj = _s3().get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "AccessDenied"):
            return None
        raise
    if int(obj.get("ContentLength") or 0) > _MAX_UPLOAD_BYTES:
        raise _UploadTooLarge
    return obj["Body"].read()


def _parse(user_id: str, body: dict) -> dict:
    """Read an uploaded resume and return validated entry candidates (no embed, no write)."""
    key = (body.get("key") or "").strip()
    # Defense-in-depth (Section 4.2.4): the key must be inside *this* user's prefix. IAM grants
    # uploads/* to the whole Lambda; this is what stops one user reading another's key.
    if not key.startswith(_uploads_prefix(user_id)):
        return _response(400, {"message": "Invalid upload key."})
    if ext_from_filename(key) not in ALLOWED_EXTENSIONS:
        return _response(400, {"message": "Invalid upload key."})

    bucket = os.environ["DATA_BUCKET_NAME"]
    try:
        data = _download(bucket, key)
    except _UploadTooLarge:
        return _response(413, {"message": "That file is too large (10 MB max)."})
    if data is None:
        return _response(404, {"message": "Upload not found — please upload the file again."})

    try:
        text = extract_text(data, filename=key)
    except UnsupportedFileType:
        return _response(415, {"message": "Only PDF and DOCX resumes are supported."})
    except Exception:  # noqa: BLE001 — a corrupt/encrypted file shouldn't 500 the Lambda
        logger.exception("Text extraction failed")
        metrics.add_metric(name="UploadExtractFailure", unit=MetricUnit.Count, value=1)
        return _response(422, {"message": "Could not read that file — it may be corrupt or password-protected."})

    if len(text) < _MIN_TEXT_CHARS:
        return _response(
            422,
            {"message": "No readable text found — a scanned/image-only PDF can't be parsed. Try a text-based resume."},
        )
    text = text[:_MAX_TEXT_CHARS]
    logger.append_keys(char_count=len(text))

    started = time.monotonic()
    try:
        response = bedrock_client.converse(
            [{"role": "user", "content": [{"text": text}]}],
            system=_SYSTEM_PROMPT,
            tool_config=build_extract_tool_config(),
            max_tokens=_EXTRACT_MAX_TOKENS,
        )
    except BedrockError:
        logger.exception("Bedrock extract turn failed")
        metrics.add_metric(name="UploadParseFailure", unit=MetricUnit.Count, value=1)
        return _response(502, {"message": "Couldn't parse the resume just now — please try again."})
    parse_ms = int((time.monotonic() - started) * 1000)

    tool_use = _extract_tool_use(response)
    raw_entries = (tool_use or {}).get("input", {}).get("entries", []) if tool_use else []
    if not isinstance(raw_entries, list):
        raw_entries = []

    candidates: list[dict] = []
    dropped = 0
    for raw in raw_entries:
        entry = _validate_candidate(raw) if isinstance(raw, dict) else None
        if entry is None:
            # Unsalvageable (e.g. a required field its type needs is missing) — skip it rather than
            # ship an un-confirmable row. Rare with a well-formed resume.
            dropped += 1
            continue
        candidate = entry.model_dump(mode="json", exclude_none=True)
        candidate["entry_id"] = new_ulid()
        candidates.append(candidate)

    metrics.add_metric(name="UploadParsed", unit=MetricUnit.Count, value=1)
    metrics.add_metric(name="UploadCandidates", unit=MetricUnit.Count, value=len(candidates))
    if dropped:
        metrics.add_metric(name="UploadCandidatesDropped", unit=MetricUnit.Count, value=dropped)
    logger.info(
        "Resume parsed",
        extra={"candidates": len(candidates), "dropped": dropped, "parse_ms": parse_ms},
    )
    return _response(
        200,
        {"candidates": candidates, "dropped": dropped, "char_count": len(text), "parse_ms": parse_ms},
    )


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def handler(event, context) -> dict:
    bind_request_context(event)

    try:
        user_id = extract_user_id(event)
    except PermissionError:
        logger.warning("Request missing sub claim")
        return _response(401, {"message": "Unauthorized"})

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"message": "Body must be valid JSON"})
    if not isinstance(body, dict):
        return _response(400, {"message": "Body must be a JSON object"})

    # Both routes are POST; the API Gateway resource path distinguishes them.
    resource = event.get("resource") or event.get("path") or ""
    if resource.endswith("/presign"):
        return _presign(user_id, body)
    if resource.endswith("/parse"):
        return _parse(user_id, body)

    return _response(404, {"message": f"Unknown route {resource}"})
