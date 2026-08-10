"""resume_agent — the payoff feature: a JD/target in, a tailored résumé out (Section 3.2, FR-5).

Résumé generation is an **asynchronous job** (ADR-037): a run takes 40–120 s, far past API Gateway's
29 s ceiling, so one Lambda serves three roles distinguished at the top of :func:`handler`:

- **``POST /resumes/generate``** (API) — validate the target, run the empty-corpus checkpoint, write
  a ``pending`` RESUMERUN item, invoke *this same function* asynchronously with a worker payload, and
  return ``202 {run_id}``.
- **worker invocation** (async ``Event``, off the API path) — run the six-phase agent (:mod:`agent`),
  finalize deterministically (Phase 6: render HTML+PDF via :mod:`rendering`, upload to
  ``resumes/<user_id>/<run_id>/``), and **overwrite** the RESUMERUN item to ``completed``/``failed``
  with the trace (TTL 30 days, §3.2.5). On success it then writes the durable RESUME# record
  (ADR-046).
- **``GET /resumes``** (API) — the user's résumé history, newest first, projected to the fields the
  grid renders (ADR-046).
- **``GET /resumes/{run_id}``** (API) — read the job record; when complete, presign fresh 1-hour GET
  URLs from the stored keys. The client polls this until terminal.

**Two items, two lifetimes (ADR-046).** ``RESUMERUN#`` is the *run trace* and keeps its 30-day TTL;
``RESUME#`` is the *résumé* and carries no ``expires_at`` at all. The 30 days was never a judgment
about how long a résumé is worth keeping — ADR-015's amendment picked it so a trace item could not
outlive the S3 objects it pointed at, and that coupling disappears once a durable record exists.

The agent is read-only over the user's data (§3.2.7): it reads ENTRY/PROFILE and calls Bedrock; the
only writes are the résumé artifact + the RESUMERUN record. IAM: ``dynamodb:Query`` + ``GetItem`` +
``PutItem``; ``s3:PutObject`` + ``GetObject`` on ``resumes/*``; ``bedrock:InvokeModel`` on the
Sonnet + Haiku profiles (+ regional foundation-model ARNs, ADR-031/036) and the Titan ARN;
``lambda:InvokeFunction`` on its own ARN (ADR-037).
"""

from __future__ import annotations

import json
import os
import time

import boto3
from aws_lambda_powertools.metrics import MetricUnit
from botocore.config import Config
from botocore.exceptions import ClientError

from careervault.bedrock_client import BedrockError
from careervault.ddb_helpers import (
    create_resume_record,
    create_resume_run,
    delete_resume_record,
    delete_resume_run_trace,
    extract_user_id,
    finalize_resume_run,
    from_ddb_numbers,
    get_profile,
    get_resume_record,
    get_resume_run,
    new_ulid,
    query_entries,
    query_resumes,
)
from careervault.observability import bind_request_context, logger, metrics, tracer
from careervault.pydantic_models.entry import utcnow_iso

import agent
from rendering import render_html, render_pdf

_CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "http://localhost:5173"),
}

#: A JD can be long, but this bounds Phase-1 token cost and the persisted trace size.
_MAX_TARGET_CHARS = 20_000
#: What we keep of the target on the *trace* item — enough to know what was asked, bounded item size.
#: Deliberately **not** applied to the durable RESUME# record: 4,000 was chosen for an item that
#: expires in 30 days, and truncation on a permanent record is unrecoverable. ADR-046 §4 keeps the
#: full target text precisely because B-030's gap analysis will read it. At the 20,000-char intake
#: ceiling that is 20 KB against DynamoDB's 400 KB item limit.
_TRACE_TARGET_CHARS = 4_000
_PRESIGN_EXPIRY_SECONDS = 3_600
_TRACE_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days (§3.2.5)

#: Card-heading length for the résumé grid. A target may be a whole pasted JD; the title is the
#: first non-empty line of it, which is the job title in every realistic paste and is *derived
#: deterministically* — no Bedrock call to label a row (ADR-046).
_TARGET_TITLE_CHARS = 120
#: Newest-first page size for `GET /resumes`. One user's history, not a paginated feed.
_RESUME_LIST_LIMIT = 50

#: Worker-payload marker (ADR-037) — an async self-invocation carries this instead of an API event.
_WORKER_JOB = "resume"

#: Friendly messages by failure ``detail`` for the status poll.
_FAILURE_MESSAGES = {
    "budget_exceeded": "Generation budget exceeded — try a more focused target.",
    "timeout": "Generation took too long — please try again.",
    "validation_abort": "Couldn't assemble a valid résumé this run — please try again.",
    "empty_retrieval": "Add a few career entries before generating a résumé.",
    "bedrock_unavailable": "The résumé service was busy — please try again.",
    "render_failed": "Built the résumé but couldn't render it — please try again.",
    "store_failed": "Generated the résumé but couldn't store it — please try again.",
}

_s3_client = None
_lambda_client = None


def _s3():
    """Cached S3 client with SigV4 presigning (stable across warm invocations)."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", config=Config(signature_version="s3v4"))
    return _s3_client


def _lambda():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    return _lambda_client


def _response(status_code: int, body: dict) -> dict:
    return {"statusCode": status_code, "headers": _CORS_HEADERS, "body": json.dumps(body)}


# --- shared item construction ---------------------------------------------------------------------

def _base_item(user_id: str, run_id: str, target_text: str, created_at: str) -> dict:
    return {
        "PK": f"USER#{user_id}",
        "SK": f"RESUMERUN#{run_id}",
        "entity_type": "RESUMERUN",
        "run_id": run_id,
        "target_text": target_text[:_TRACE_TARGET_CHARS],
        "created_at": created_at,
        "expires_at": int(time.time()) + _TRACE_TTL_SECONDS,
    }


def _final_item(
    user_id: str,
    run_id: str,
    target_text: str,
    created_at: str,
    *,
    status: str,
    result: agent.AgentResult | None = None,
    keys: dict[str, str] | None = None,
    detail: str | None = None,
) -> dict:
    """Build the terminal RESUMERUN item — trace + job record in one (§3.2.5 / ADR-037)."""
    item = _base_item(user_id, run_id, target_text, created_at)
    item.update({"status": status, "updated_at": utcnow_iso(), "detail": detail})
    if result is not None:
        item.update(
            {
                "agent_status": result.status,
                "target_type": result.requirements.target_type if result.requirements else None,
                "critique_verdict": result.critique_verdict,
                "retrieved_ids": result.retrieved_ids,
                "retrieval_iterations": result.retrieval_iterations,
                "revisions_used": result.revisions_used,
                "cumulative_tokens": result.cumulative_tokens,
                "cumulative_cost_usd": result.cumulative_cost_usd,
                # B-007. The poll reads *this* item for the first 30 days, so omitting it here made
                # elapsed time null on exactly the runs a user would look at.
                "elapsed_seconds": result.elapsed_seconds,
                "trace": result.trace,
            }
        )
        if result.document is not None:
            item["document"] = result.document.model_dump(mode="json", exclude_none=True)
    if keys:
        item["html_key"] = keys.get("html_key")
        item["pdf_key"] = keys.get("pdf_key")
    return item


def _target_title(target_text: str) -> str:
    """First non-empty line of the target, bounded — the résumé card's heading (ADR-046).

    Deterministic on purpose. The alternative is asking a model to name the row, which would spend
    Bedrock tokens on a label against a $5 ceiling where Bedrock is already 87% of spend.
    """
    for line in target_text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:_TARGET_TITLE_CHARS]
    return "Untitled target"


def _record_item(
    user_id: str,
    run_id: str,
    target_text: str,
    created_at: str,
    *,
    result: agent.AgentResult,
    keys: dict[str, str],
) -> dict:
    """Build the durable RESUME# record for a successful run (ADR-046).

    Carries **no** ``expires_at``: the table's TTL only ever deletes items that have one, so
    omitting it is the whole mechanism by which this outlives its trace.

    It duplicates a handful of fields from the trace item deliberately. What it does *not* copy is
    the bulk — ``trace``, ``retrieved_ids``, ``retrieval_iterations``, ``revisions_used`` — which is
    agent exhaust and dies with the trace on schedule. ``document`` *is* copied, because B-022's
    copyable bullets have to keep working past day 30 now that the artifacts do.
    """
    return {
        "PK": f"USER#{user_id}",
        "SK": f"RESUME#{run_id}",
        "entity_type": "RESUME",
        "run_id": run_id,
        "status": "completed",
        "created_at": created_at,
        "target_text": target_text,
        "target_title": _target_title(target_text),
        "entry_count": len(result.retrieved_ids or []),
        "html_key": keys.get("html_key"),
        "pdf_key": keys.get("pdf_key"),
        "document": result.document.model_dump(mode="json", exclude_none=True) if result.document else None,
        "critique_verdict": result.critique_verdict,
        "cumulative_tokens": result.cumulative_tokens,
        "cumulative_cost_usd": result.cumulative_cost_usd,
        "elapsed_seconds": result.elapsed_seconds,
    }


# --- POST /resumes/generate (start the job) -------------------------------------------------------

def _start(user_id: str, body: dict, *, jwt_email: str | None = None) -> dict:
    target_text = (body.get("target") or "").strip()
    if not target_text:
        return _response(400, {"message": "Provide a job description or target role in `target`."})
    if len(target_text) > _MAX_TARGET_CHARS:
        return _response(400, {"message": f"Target is too long ({_MAX_TARGET_CHARS} character max)."})

    # Empty-corpus checkpoint (§3.2.6), hoisted ahead of any Bedrock spend: no entries → no résumé.
    if not query_entries(user_id):
        return _response(400, {"message": "Add a few career entries before generating a résumé."})

    run_id = new_ulid()
    created_at = utcnow_iso()
    logger.append_keys(run_id=run_id)

    pending = _base_item(user_id, run_id, target_text, created_at)
    pending.update({"status": "pending", "updated_at": created_at, "detail": None})
    create_resume_run(pending)

    try:
        _lambda().invoke(
            FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"],
            InvocationType="Event",  # async — the worker runs detached from this request (ADR-037)
            Payload=json.dumps(
                {
                    "job": _WORKER_JOB,
                    "user_id": user_id,
                    "run_id": run_id,
                    "target_text": target_text,
                    "created_at": created_at,
                    # Carried from the JWT because the worker never sees the API Gateway event
                    # (ADR-037). Only used as the résumé header's fallback when the user has no
                    # PROFILE row yet — see `_contact_from_profile` (B-008).
                    "jwt_email": jwt_email,
                }
            ).encode(),
        )
    except ClientError:
        logger.exception("Failed to enqueue résumé worker")
        finalize_resume_run(
            _final_item(user_id, run_id, target_text, created_at, status="failed", detail="store_failed")
        )
        return _response(500, {"message": "Couldn't start résumé generation — please try again.", "run_id": run_id})

    metrics.add_metric(name="ResumeJobStarted", unit=MetricUnit.Count, value=1)
    logger.info("Résumé job started")
    return _response(202, {"run_id": run_id, "status": "pending"})


# --- worker (async): run the agent + finalize -----------------------------------------------------

def _upload_and_keys(user_id: str, run_id: str, html: str, pdf: bytes) -> dict:
    """Upload HTML + PDF to ``resumes/<user_id>/<run_id>/`` and return the stored keys."""
    bucket = os.environ["DATA_BUCKET_NAME"]
    prefix = f"resumes/{user_id}/{run_id}"
    html_key = f"{prefix}/resume.html"
    pdf_key = f"{prefix}/resume.pdf"
    _s3().put_object(Bucket=bucket, Key=html_key, Body=html.encode("utf-8"), ContentType="text/html; charset=utf-8")
    _s3().put_object(Bucket=bucket, Key=pdf_key, Body=pdf, ContentType="application/pdf")
    return {"html_key": html_key, "pdf_key": pdf_key}


def _contact_from_profile(profile: dict | None, *, jwt_email: str | None = None) -> dict:
    """Deterministic identity for the résumé header — never LLM-generated (§3.2.2).

    Precedence is PROFILE first, JWT email as the fallback, and that order matters: the PROFILE
    row is user-editable through ``PUT /settings``, so a user who has set their details should see
    them, while a user who never opened the settings form still gets *something* real rather than
    the literal word "Résumé" (backlog B-008).

    ``jwt_email`` is threaded down from the API entrypoint because the worker runs asynchronously
    (ADR-037) and never sees the API Gateway event — the claims have to be carried in the job
    payload or they are simply not available at render time.
    """
    profile = profile or {}
    return {
        "name": profile.get("name"),
        "email": profile.get("email") or jwt_email,
        "phone": profile.get("phone"),
        "location": profile.get("location"),
        "links": profile.get("portfolio_links") or {},
    }


def _run_worker(payload: dict) -> dict:
    """Async entrypoint (ADR-037): run the agent, finalize the RESUMERUN item. Return value ignored."""
    user_id = payload["user_id"]
    run_id = payload["run_id"]
    target_text = payload["target_text"]
    created_at = payload.get("created_at") or utcnow_iso()
    logger.append_keys(run_id=run_id)

    def _fail(detail: str, result: agent.AgentResult | None = None) -> dict:
        finalize_resume_run(
            _final_item(user_id, run_id, target_text, created_at, status="failed", detail=detail, result=result)
        )
        metrics.add_metric(name="ResumeJobFailed", unit=MetricUnit.Count, value=1)
        return {"status": "failed", "run_id": run_id, "detail": detail}

    entries = query_entries(user_id)
    if not entries:
        return _fail("empty_retrieval")
    profile = get_profile(user_id)

    try:
        result = agent.run_agent(
            run_id=run_id, user_id=user_id, target_text=target_text, entries=entries, profile=profile
        )
    except BedrockError:
        logger.exception("Bedrock unavailable during agent run")
        return _fail("bedrock_unavailable")

    if not result.ok or result.document is None:
        return _fail(result.status, result=result)

    try:
        html = render_html(
            result.document,
            contact=_contact_from_profile(profile, jwt_email=payload.get("jwt_email")),
        )
        pdf = render_pdf(html)
    except Exception:  # noqa: BLE001 — a render failure shouldn't crash the worker opaquely
        logger.exception("Résumé rendering failed")
        return _fail("render_failed", result=result)

    try:
        keys = _upload_and_keys(user_id, run_id, html, pdf)
    except ClientError:
        logger.exception("Failed to store résumé artifacts")
        return _fail("store_failed", result=result)

    # Order matters and is not arbitrary (ADR-046 §3). These are two PutItems, not a transaction,
    # so a crash between them leaves the pair inconsistent; finalizing the *trace* first chooses the
    # benign inconsistency — the user's poll completes and their résumé downloads, and all that is
    # missing is a row in a list. The reverse order would leave a history row for a run whose poll
    # never reports `completed`, which is the failure worth avoiding.
    finalize_resume_run(
        _final_item(user_id, run_id, target_text, created_at, status="completed", result=result, keys=keys)
    )
    try:
        create_resume_record(_record_item(user_id, run_id, target_text, created_at, result=result, keys=keys))
    except ClientError:
        # Never fail a completed run over its history row — the résumé exists and the poll works.
        logger.exception("Failed to write résumé history record")
        metrics.add_metric(name="ResumeRecordWriteFailed", unit=MetricUnit.Count, value=1)

    metrics.add_metric(name="ResumeJobCompleted", unit=MetricUnit.Count, value=1)
    logger.info(
        "Résumé job completed",
        extra={
            "cumulative_tokens": result.cumulative_tokens,
            "cumulative_cost_usd": result.cumulative_cost_usd,
            "critique_verdict": result.critique_verdict,
        },
    )
    return {"status": "completed", "run_id": run_id}


# --- GET /resumes/{run_id} (poll status) ----------------------------------------------------------

def _presign_get(key: str, *, download_as: str | None = None) -> str:
    """Presign a GET. ``download_as`` forces a save-to-disk instead of in-browser rendering.

    The frontend previews the HTML in an iframe (a navigation, so no bucket CORS needed) but wants
    the PDF *downloaded*. HTML's ``download`` attribute is ignored on cross-origin URLs, so the
    disposition has to come from S3 itself — hence the response-header override on the signature.
    """
    params = {"Bucket": os.environ["DATA_BUCKET_NAME"], "Key": key}
    if download_as:
        params["ResponseContentDisposition"] = f'attachment; filename="{download_as}"'
    return _s3().generate_presigned_url("get_object", Params=params, ExpiresIn=_PRESIGN_EXPIRY_SECONDS)


def _completed_payload(run_id: str, item: dict) -> dict:
    """Shape the `completed` poll response from either item type (ADR-046).

    The trace and the durable record carry the same completion fields under the same names, so one
    formatter serves both. ``retrieved_ids`` is the exception — it is trace-only bulk, and the
    record stores the count it was only ever used to produce.
    """
    retrieved = item.get("retrieved_ids")
    return {
        "run_id": run_id,
        "status": "completed",
        "created_at": item.get("created_at"),
        "html_url": _presign_get(item["html_key"]),
        "pdf_url": _presign_get(item["pdf_key"], download_as=f"resume-{run_id}.pdf"),
        "critique_verdict": item.get("critique_verdict"),
        "retrieved_count": len(retrieved) if retrieved is not None else from_ddb_numbers(item.get("entry_count")),
        "cost_usd": from_ddb_numbers(item.get("cumulative_cost_usd")),
        "tokens": from_ddb_numbers(item.get("cumulative_tokens")),
        # B-007: the elapsed counter used to vanish at exactly the moment you'd compare runs.
        "elapsed_seconds": from_ddb_numbers(item.get("elapsed_seconds")),
        # B-022: the structured résumé, so the client can offer copyable plain-text bullets over
        # data it already has. Formatting stays client-side (ADR-045's derive-don't-endpoint rule).
        "document": from_ddb_numbers(item.get("document")),
    }


def _list(user_id: str) -> dict:
    """`GET /resumes` — the user's résumé history, newest first (ADR-046)."""
    items = query_resumes(user_id, limit=_RESUME_LIST_LIMIT)
    return _response(
        200,
        {
            "resumes": [
                {
                    "run_id": item.get("run_id"),
                    "created_at": item.get("created_at"),
                    "target_title": item.get("target_title"),
                    "entry_count": from_ddb_numbers(item.get("entry_count")),
                    "status": item.get("status"),
                }
                for item in items
            ]
        },
    )


def _delete(user_id: str, run_id: str) -> dict:
    """`DELETE /resumes/{run_id}` — remove a résumé and everything belonging to it (ADR-046).

    Deletion exists because ADR-046 made résumés permanent. Under the old flat 30-day rule there was
    nothing to delete — everything left on its own — so this is the affordance that decision took
    away and has to give back. Hard delete behind a UI confirm, per **ADR-027**, applied unchanged.

    **S3 first, then DynamoDB, and the order is the decision.** These are separate services with no
    transaction between them, so a crash between the two leaves one of two inconsistencies, and the
    ordering picks which:

    - *Objects first:* a failure after they are gone leaves a history row whose View/Download 404 —
      visible, annoying, and **recoverable**, because the row is still there to delete again. S3
      deletes are idempotent, so the retry simply succeeds.
    - *Record first:* a failure after it is gone leaves S3 objects that nothing references and
      nothing will ever expire (the lifecycle rule was removed by ADR-046). The user cannot even see
      the résumé to retry. That is **unrecoverable** orphaning, and exactly B-039's failure mode.

    A visible, retryable fault beats an invisible, permanent one — so objects go first.

    **The record is read before anything is destroyed.** An unknown ``run_id`` must 404 having
    changed nothing: deleting first and reporting "no longer exists" afterwards would destroy the
    trace of a run that is still *pending* — the user's poll would then report the run expired while
    a ~$0.31 Sonnet job is still executing — and would throw away the diagnostic trace of a failed
    one. Reading first also yields the **stored** object keys, which are authoritative; rebuilding
    them from today's filename convention would silently miss any record written under a different
    layout and orphan the real objects.
    """
    record = get_resume_record(user_id, run_id)
    if record is None:
        return _response(404, {"message": "That résumé no longer exists."})

    bucket = os.environ["DATA_BUCKET_NAME"]
    keys = [k for k in (record.get("html_key"), record.get("pdf_key")) if k]
    try:
        if keys:
            result = _s3().delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in keys]})
            # `delete_objects` reports per-key failures in an `Errors` list and still returns 200 —
            # it does *not* raise. Treating that as success would delete the record and strand the
            # object forever, which is the exact B-039 orphaning the ordering above exists to avoid.
            errors = result.get("Errors") or []
            if errors:
                logger.error(
                    "Some résumé artifacts could not be deleted",
                    extra={"run_id": run_id, "errors": [e.get("Code") for e in errors]},
                )
                return _response(500, {"message": "Couldn't delete that résumé — please try again."})
    except ClientError:
        # Stop here rather than pressing on: deleting the record now is precisely the unrecoverable
        # ordering this function exists to avoid. The user retries and nothing has been lost.
        logger.exception("Failed to delete résumé artifacts")
        return _response(500, {"message": "Couldn't delete that résumé — please try again."})

    delete_resume_record(user_id, run_id)
    # Best effort, and unconditional: the trace has usually already expired (30-day TTL), which is
    # normal rather than an error. Its absence must not turn a successful delete into a failure.
    try:
        delete_resume_run_trace(user_id, run_id)
    except ClientError:
        logger.exception("Failed to delete résumé run trace")

    metrics.add_metric(name="ResumeDeleted", unit=MetricUnit.Count, value=1)
    logger.info("Résumé deleted", extra={"run_id": run_id})
    return _response(200, {"run_id": run_id, "deleted": True})


def _status(user_id: str, run_id: str) -> dict:
    item = get_resume_run(user_id, run_id)
    if item is None:
        # The trace has aged out (30-day TTL) but the résumé itself has not — ADR-046 removed the
        # artifacts' expiry, so a run older than 30 days is still viewable and its history row is
        # still listed. Without this fallback the list would offer rows whose View/Download 404.
        record = get_resume_record(user_id, run_id)
        if record is None:
            return _response(404, {"message": "Run not found"})
        return _response(200, _completed_payload(run_id, record))

    status = item.get("status")
    created_at = item.get("created_at")

    if status == "completed":
        return _response(200, _completed_payload(run_id, item))
    if status == "failed":
        detail = item.get("detail")
        return _response(
            200,
            {
                "run_id": run_id,
                "status": "failed",
                "created_at": created_at,
                "message": _FAILURE_MESSAGES.get(detail, "Couldn't generate a résumé — please try again."),
            },
        )
    # pending
    return _response(200, {"run_id": run_id, "status": "pending", "created_at": created_at})


# --- entrypoint -----------------------------------------------------------------------------------

@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def handler(event, context) -> dict:
    # Async worker self-invocation (ADR-037) — not an API Gateway proxy event.
    if isinstance(event, dict) and event.get("job") == _WORKER_JOB:
        return _run_worker(event)

    bind_request_context(event)

    try:
        user_id = extract_user_id(event)
    except PermissionError:
        logger.warning("Request missing sub claim")
        return _response(401, {"message": "Unauthorized"})

    method = (event.get("httpMethod") or "").upper()

    if method == "GET":
        # Two routes share this method: `/resumes` (history) and `/resumes/{run_id}` (poll). API
        # Gateway only populates `run_id` for the latter, so its absence *is* the list request —
        # it is no longer the 400 it was when only one GET route existed.
        run_id = (event.get("pathParameters") or {}).get("run_id")
        return _status(user_id, run_id) if run_id else _list(user_id)

    if method == "DELETE":
        run_id = (event.get("pathParameters") or {}).get("run_id")
        if not run_id:
            return _response(400, {"message": "Missing run id"})
        return _delete(user_id, run_id)

    if method == "POST":
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"message": "Body must be valid JSON"})
        if not isinstance(body, dict):
            return _response(400, {"message": "Body must be a JSON object"})
        # Read from the validated claims, never the body — the same rule `user_id` follows
        # (§4.2.4). This is the only point in the async flow where the JWT is visible.
        jwt_email = (event.get("requestContext", {}).get("authorizer", {}).get("claims", {}) or {}).get("email")
        return _start(user_id, body, jwt_email=jwt_email)

    return _response(405, {"message": f"{method} not allowed"})
