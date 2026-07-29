"""checkin_lambda — the scheduled check-in send (FR-4, §3.3, ADR-011/-021/-039).

Invoked by EventBridge Scheduler once a day with an empty payload; the Lambda discovers who is due
from DynamoDB (ADR-039). Not an API route — there is no JWT, no `user_id` from claims, and no
caller to return a status code to.

**That last point shapes everything here.** A user-facing handler fails loudly to someone who can
react; a scheduled job fails silently to nobody (§3.3.5). So the loudness is manufactured: every
outcome emits a metric, every per-user failure is caught and logged with `user_id` so one bad
profile cannot poison the batch, and a successful send writes a CHECKINLOG audit item — which is
what makes "did my check-in actually go out three weeks ago?" answerable at all.

Ordering matters in the send path and is worth stating explicitly, because the tempting order is
wrong: **claim the slot before calling SES, and write the audit record after.** Claiming first means
a Scheduler retry loses the race rather than the mailbox absorbing a duplicate; auditing after means
a CHECKINLOG item asserts "SES accepted this", not "we meant to send this".
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import boto3
from aws_lambda_powertools.metrics import MetricUnit

from careervault.checkin_schedule import (
    advance,
    cadence_of,
    is_due,
    recent_window_start,
    utcnow_iso,
)
from careervault.ddb_helpers import (
    CHECKIN_IDEMPOTENCY_HOURS,
    claim_checkin_slot,
    new_ulid,
    put_checkin_log,
    query_entries,
    scan_profiles,
)
from careervault.observability import logger, metrics, tracer
from careervault.pydantic_models.checkin import MAX_PROMPT_ENTRIES

from composer import compose
from rendering import render_html, render_text

_ses = None


def _ses_client():
    """Cached SES v2 client — construction is expensive and a warm container reuses it."""
    global _ses
    if _ses is None:
        _ses = boto3.client("sesv2")
    return _ses


def _app_urls() -> tuple[str, str]:
    """Return (dashboard_url, settings_url) for the email's links (FR-4.4).

    ``APP_BASE_URL`` is the CloudFront distribution domain, passed in by the template. The SPA has
    no client-side router, so both links point at the same page — the settings link is a separate
    constant only so the copy can differentiate, and so a future route needs no template change.
    """
    base = os.environ.get("APP_BASE_URL", "").rstrip("/")
    return base, base


def _recent_entries(user_id: str, cadence: str, now: datetime) -> list[dict[str, Any]]:
    """Return the user's entries inside the recency window, newest first.

    Filtered in Python because :func:`query_entries` already reads the whole corpus (ADR-016 keeps
    embeddings in the item, and there is no GSI on `event_date`), so a narrower read is not
    available to ask for. At MVP corpus sizes this is the same read the dashboard and the résumé
    agent already do — see backlog B-013 for the projection work that would trim it.
    """
    cutoff = recent_window_start(cadence, now).date().isoformat()
    recent = [
        entry
        for entry in query_entries(user_id)
        if str(entry.get("event_date") or "") >= cutoff
    ]
    # Newest first, so the cap in `build_user_prompt` keeps the *most relevant* entries rather than
    # whichever happened to be created first.
    recent.sort(key=lambda entry: str(entry.get("event_date") or ""), reverse=True)
    return recent[:MAX_PROMPT_ENTRIES]


def _send_email(*, to_address: str, subject: str, html: str, text: str) -> str:
    """Send one check-in through SES and return the message ID.

    The Configuration Set is what routes Bounce and Complaint events to the SNS topic (§4.5.3) —
    without it the send still works and the events simply vanish, which is the kind of silent gap
    worth naming at the call site.
    """
    response = _ses_client().send_email(
        FromEmailAddress=os.environ["CHECKIN_SENDER_ADDRESS"],
        Destination={"ToAddresses": [to_address]},
        ConfigurationSetName=os.environ["SES_CONFIGURATION_SET"],
        Content={
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": text, "Charset": "UTF-8"},
                    "Html": {"Data": html, "Charset": "UTF-8"},
                },
            }
        },
    )
    return response["MessageId"]


def _process_user(profile: Mapping[str, Any], now: datetime, run_id: str) -> str:
    """Send one user's check-in. Returns the outcome for metrics; raises only on real failure."""
    user_id = str(profile["PK"]).removeprefix("USER#")
    cadence = cadence_of(profile)

    entries = _recent_entries(user_id, cadence, now)
    email, tier = compose(profile, entries)

    # Claimed *before* SES. A Scheduler retry that reaches this line loses the conditional write
    # and returns here having sent nothing (§3.3.4).
    claimed = claim_checkin_slot(
        user_id,
        now_iso=utcnow_iso(now),
        next_checkin_at=utcnow_iso(advance(cadence, now)),
        buffer_iso=utcnow_iso(now - timedelta(hours=CHECKIN_IDEMPOTENCY_HOURS)),
    )
    if not claimed:
        logger.info("Check-in already sent within the idempotency window; skipping", extra={"user_id": user_id})
        return "skipped_idempotent"

    dashboard_url, settings_url = _app_urls()
    message_id = _send_email(
        to_address=str(profile["email"]),
        subject=email.subject,
        html=render_html(email, dashboard_url=dashboard_url, settings_url=settings_url),
        text=render_text(email, dashboard_url=dashboard_url, settings_url=settings_url),
    )

    put_checkin_log(
        {
            "PK": profile["PK"],
            "SK": f"CHECKINLOG#{new_ulid()}",
            "entity_type": "CHECKINLOG",
            "run_id": run_id,
            "tier": tier,
            "cadence": cadence,
            "entries_referenced": len(entries),
            "subject": email.subject,
            "ses_message_id": message_id,
            "sent_at": utcnow_iso(now),
        }
    )

    logger.info(
        "Check-in sent",
        extra={
            "user_id": user_id,
            "tier": tier,
            "cadence": cadence,
            "entries_referenced": len(entries),
            "ses_message_id": message_id,
        },
    )
    metrics.add_metric(name="CheckinsSent", unit=MetricUnit.Count, value=1)
    if tier == "static":
        # ADR-021 wanted the tier as a metric *dimension*. Powertools scopes dimensions to the whole
        # invocation, not to an individual metric, so a per-user dimension inside this loop would
        # relabel every metric the run emits. A separate counter for the one tier worth alarming on
        # is the same signal without that coupling — a nonzero value means personalization is
        # failing, which is otherwise invisible because the email still arrives.
        metrics.add_metric(name="CheckinsStaticFallback", unit=MetricUnit.Count, value=1)
    return f"sent_{tier}"


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def handler(event, context) -> dict:
    """Scheduled entry point. Returns a summary dict — for logs and manual invokes, not a caller."""
    run_id = new_ulid()
    logger.append_keys(run_id=run_id)
    now = datetime.now(timezone.utc)

    profiles = scan_profiles()
    due = [profile for profile in profiles if is_due(profile, now)]

    logger.info(
        "Check-in run starting",
        extra={"profiles_scanned": len(profiles), "profiles_due": len(due)},
    )

    if not due:
        # Not an error — most daily fires have nothing to do at a weekly cadence. The metric is
        # what distinguishes "nothing was due" from "the run never happened" (§3.3.8).
        metrics.add_metric(name="CheckinsNoDueUsers", unit=MetricUnit.Count, value=1)
        return {"run_id": run_id, "scanned": len(profiles), "due": 0, "outcomes": {}}

    outcomes: dict[str, int] = {}
    for profile in due:
        user_id = str(profile.get("PK", "")).removeprefix("USER#")
        try:
            outcome = _process_user(profile, now, run_id)
        except Exception:
            # Per-user isolation (§3.3.5). `exception` captures the traceback; the loop continues so
            # one unverified recipient or malformed profile cannot cost every other user their
            # check-in.
            logger.exception("Check-in failed for user", extra={"user_id": user_id})
            metrics.add_metric(name="CheckinsFailedUser", unit=MetricUnit.Count, value=1)
            outcome = "failed"
        outcomes[outcome] = outcomes.get(outcome, 0) + 1

    logger.info("Check-in run complete", extra={"outcomes": outcomes})
    return {"run_id": run_id, "scanned": len(profiles), "due": len(due), "outcomes": outcomes}
