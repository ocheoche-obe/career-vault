"""resume_agent — the payoff feature: a JD/target in, a tailored résumé out (Section 3.2, FR-5).

Résumé generation is an **asynchronous job** (ADR-037): a run takes 40–120 s, far past API Gateway's
29 s ceiling, so one Lambda serves three roles distinguished at the top of :func:`handler`:

- **``POST /resumes/generate``** (API) — validate the target, run the empty-corpus checkpoint, write
  a ``pending`` RESUMERUN item, invoke *this same function* asynchronously with a worker payload, and
  return ``202 {run_id}``.
- **worker invocation** (async ``Event``, off the API path) — run the six-phase agent (:mod:`agent`),
  finalize deterministically (Phase 6: render HTML+PDF via :mod:`rendering`, upload to
  ``resumes/<user_id>/<run_id>/``), and **overwrite** the RESUMERUN item to ``completed``/``failed``
  with the trace (TTL 30 days, §3.2.5).
- **``GET /resumes/{run_id}``** (API) — read the job record; when complete, presign fresh 1-hour GET
  URLs from the stored keys. The client polls this until terminal.

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
    create_resume_run,
    extract_user_id,
    finalize_resume_run,
    from_ddb_numbers,
    get_profile,
    get_resume_run,
    new_ulid,
    query_entries,
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
#: What we keep of the target on the trace item — enough to know what was asked, bounded item size.
_TRACE_TARGET_CHARS = 4_000
_PRESIGN_EXPIRY_SECONDS = 3_600
_TRACE_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days (§3.2.5)

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
                "trace": result.trace,
            }
        )
        if result.document is not None:
            item["document"] = result.document.model_dump(mode="json", exclude_none=True)
    if keys:
        item["html_key"] = keys.get("html_key")
        item["pdf_key"] = keys.get("pdf_key")
    return item


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

    finalize_resume_run(
        _final_item(user_id, run_id, target_text, created_at, status="completed", result=result, keys=keys)
    )
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


def _status(user_id: str, run_id: str | None) -> dict:
    if not run_id:
        return _response(400, {"message": "Missing run id"})
    item = get_resume_run(user_id, run_id)
    if item is None:
        return _response(404, {"message": "Run not found"})

    status = item.get("status")
    created_at = item.get("created_at")

    if status == "completed":
        return _response(
            200,
            {
                "run_id": run_id,
                "status": "completed",
                "created_at": created_at,
                "html_url": _presign_get(item["html_key"]),
                "pdf_url": _presign_get(item["pdf_key"], download_as=f"resume-{run_id}.pdf"),
                "critique_verdict": item.get("critique_verdict"),
                "retrieved_count": len(item.get("retrieved_ids") or []),
                "cost_usd": from_ddb_numbers(item.get("cumulative_cost_usd")),
                "tokens": from_ddb_numbers(item.get("cumulative_tokens")),
            },
        )
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
        run_id = (event.get("pathParameters") or {}).get("run_id")
        return _status(user_id, run_id)

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
