"""ses_event_handler — record SES Bounce and Complaint events on the PROFILE (§4.5.3/4.5.4).

SES does not report delivery outcomes synchronously: ``SendEmail`` returns a message ID and
nothing more. What happened to that message arrives later, as an event published by the
Configuration Set to the ``careervault-ses-events`` SNS topic, which invokes this function.

A separate Lambda rather than a second trigger on ``checkin_lambda`` (§4.5.4): this one needs no
Bedrock and no SES, so it gets the tightest role in the system — ``UpdateItem`` to stamp the
PROFILE, plus ``Scan`` to find which PROFILE to stamp. (§4.5.4 lists only ``UpdateItem``, having
assumed the recipient lookup was a Query; see :func:`_user_id_for_recipient`.)

The DLQ attached to it is for *SNS→Lambda* delivery failures and is unrelated to the Scheduler DLQ
on ``checkin_lambda`` — failure handling belongs to whichever component did the invoking, and here
that is two different components at two different layers.

MVP takes **no automated action** on either event (§3.3.8): it records and counts, and that is all.
`CheckinsBounced` / `CheckinsComplained` are emitted but **nothing alarms on them yet** — the only
alarm here is on this function's own errors. Auto-pausing check-ins after repeated bounces is the
v1.1 hook, deliberately not built, because the first thing an auto-pause does when it misfires is
silently stop a working feature.

That gap is a deadline, not a preference: nothing in :func:`careervault.checkin_schedule.is_due`
consults `bounce_count`, so a permanently-bouncing address keeps being sent to indefinitely. Harmless
in the SES sandbox with one self-owned verified recipient; an account-reputation liability the moment
production access is granted. See B-019 — it must be closed *before* leaving the sandbox, not after.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from aws_lambda_powertools.metrics import MetricUnit

from careervault.ddb_helpers import record_bounce, record_complaint, scan_profiles
from careervault.observability import logger, metrics, tracer

_HANDLED_EVENT_TYPES = {"Bounce", "Complaint"}


def _user_id_for_recipient(recipient: str) -> str | None:
    """Resolve a recipient address to a ``user_id`` by scanning PROFILE items (§4.5.4 step 2).

    A Scan for the same reason the check-in run does one: there is no GSI on ``email`` (ADR-028),
    and PROFILE rows for different users sit under different partition keys, so no Query reaches
    them. §4.5.4 calls this "a single Query against the table"; that is not available, and the
    honest description is a Scan — the same correction ADR-039 makes for the due-user lookup.

    Case-insensitive: SES echoes back whatever the envelope carried, which need not match the
    casing a user typed into settings, and an unmatched recipient means the event is dropped.
    """
    needle = recipient.strip().lower()
    for profile in scan_profiles():
        if str(profile.get("email", "")).strip().lower() == needle:
            return str(profile["PK"]).removeprefix("USER#")
    return None


def _process_event(message: Mapping[str, Any]) -> None:
    """Record one SES event against every recipient it names."""
    event_type = message.get("eventType") or message.get("notificationType")
    if event_type not in _HANDLED_EVENT_TYPES:
        # The Configuration Set is subscribed to Bounce and Complaint only, so anything else means
        # the subscription was widened without this handler being taught about it.
        logger.info("Ignoring unhandled SES event type", extra={"event_type": event_type})
        return

    detail = message.get(event_type.lower(), {}) or {}
    occurred_at = detail.get("timestamp") or message.get("mail", {}).get("timestamp") or ""
    recipients = [
        entry.get("emailAddress")
        for entry in detail.get("bouncedRecipients", detail.get("complainedRecipients", []))
        if entry.get("emailAddress")
    ] or list(message.get("mail", {}).get("destination", []))

    for recipient in recipients:
        user_id = _user_id_for_recipient(recipient)
        if user_id is None:
            # Expected for the SES mailbox simulator addresses used to exercise this path — they
            # are not real users, so there is no PROFILE to stamp. Logged rather than raised.
            logger.warning("SES event for unknown recipient", extra={"event_type": event_type})
            continue

        if event_type == "Bounce":
            bounce_type = detail.get("bounceType", "")
            profile = record_bounce(user_id, occurred_at)
            logger.warning(
                "Recorded SES bounce",
                extra={
                    "user_id": user_id,
                    "bounce_type": bounce_type,
                    "bounce_subtype": detail.get("bounceSubType", ""),
                    "bounce_count": int(profile.get("bounce_count", 0)),
                },
            )
            metrics.add_metric(name="CheckinsBounced", unit=MetricUnit.Count, value=1)
        else:
            record_complaint(user_id, occurred_at)
            logger.warning("Recorded SES complaint", extra={"user_id": user_id})
            metrics.add_metric(name="CheckinsComplained", unit=MetricUnit.Count, value=1)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def handler(event, context) -> dict:
    """SNS entry point. One invocation can carry several records; each is isolated."""
    records = event.get("Records", [])
    processed = 0

    for record in records:
        raw = record.get("Sns", {}).get("Message", "")
        try:
            _process_event(json.loads(raw))
            processed += 1
        except json.JSONDecodeError:
            logger.exception("SES event payload was not valid JSON")
        except Exception:
            # Isolated per record for the same reason the check-in loop isolates per user: a
            # raise here would re-deliver *every* record in the batch, re-counting the ones that
            # already succeeded.
            logger.exception("Failed to process SES event record")

    logger.info("SES event batch complete", extra={"records": len(records), "processed": processed})
    return {"records": len(records), "processed": processed}
