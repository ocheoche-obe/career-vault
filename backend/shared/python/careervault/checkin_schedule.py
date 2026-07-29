"""Check-in scheduling arithmetic (ADR-039) — pure functions, no AWS.

Everything about *when* a check-in is due lives here rather than in ``checkin_lambda``, so the
rules that decide whether a user gets an email can be tested exhaustively without a table, a
schedule, or a Bedrock mock. That matters more than usual for this flow: a scheduled job's bugs
surface as an email that silently did not arrive, days later, with no HTTP status to inspect
(§3.3.5).

The model, restated from ADR-039: one EventBridge schedule fires daily; ``next_checkin_at`` on the
PROFILE is what actually paces each user's cadence. So all four FR-4.1 cadences are served by one
schedule, and changing cadence is a DynamoDB write rather than a control-plane call.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from careervault.pydantic_models.profile import CADENCE_DAYS, DEFAULT_CADENCE

#: Multiplier on the cadence window when selecting "recent" entries to talk about (§3.3.3 step 1).
#: The doubling means a missed cycle's entries still appear in the following check-in instead of
#: falling into a gap between windows — the emails overlap rather than tile.
RECENT_WINDOW_MULTIPLIER = 2


def utcnow_iso(now: datetime | None = None) -> str:
    """Format a UTC datetime the way every timestamp in this table is stored.

    Second precision with a literal ``Z``. The fixed width and fixed suffix are load-bearing, not
    cosmetic: :func:`careervault.ddb_helpers.claim_checkin_slot` compares these strings with
    DynamoDB's ``<`` operator, which is lexicographic. A value formatted ``+00:00`` would sort
    *after* one formatted ``Z`` for the same instant, and the idempotency condition would quietly
    stop working.
    """
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: Any) -> datetime | None:
    """Parse a stored timestamp back to an aware datetime, or ``None`` if unusable.

    Tolerant by design. This reads persisted data that predates the current code, and the caller's
    only sensible response to garbage is "treat this user as due and move on" — which is what
    ``None`` produces upstream. Raising instead would let one malformed attribute stop the whole
    scheduled run for every user.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def settings_of(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Read the nested ``settings`` object, tolerating its complete absence.

    Not defensive programming for a hypothetical: **no PROFILE item in the table has a ``settings``
    attribute today**. It was never written, because ``PUT /settings`` shipped early with B-008 and
    only ever wrote identity fields. So "settings missing" is the normal case this slice inherits,
    not an edge case — and defaulting it here is what lets the feature work with no migration.
    """
    settings = profile.get("settings")
    return dict(settings) if isinstance(settings, Mapping) else {}


def cadence_of(profile: Mapping[str, Any]) -> str:
    """Return the user's cadence keyword, falling back to weekly (FR-4.2).

    An unrecognised stored value also falls back rather than raising. The write path constrains
    this to four literals, so a bad value means hand-edited data or a rolled-back deploy — in
    either case a check-in at the default cadence beats no check-in at all.
    """
    cadence = settings_of(profile).get("checkin_cadence")
    return cadence if cadence in CADENCE_DAYS else DEFAULT_CADENCE


def is_paused(profile: Mapping[str, Any]) -> bool:
    """True if the user has paused check-ins (FR-4.6).

    Compared against ``True`` explicitly rather than truthily: the value arrives from DynamoDB and
    could be a string ``"true"`` if something ever wrote it untyped. Only a real boolean pauses,
    so the failure direction is "we send an email you asked us not to" — visible and correctable —
    rather than "we silently stop sending forever", which is invisible.
    """
    return settings_of(profile).get("checkin_paused") is True


def advance(cadence: str, from_moment: datetime) -> datetime:
    """Return the next check-in instant, one cadence window after ``from_moment``."""
    return from_moment + timedelta(days=CADENCE_DAYS.get(cadence, CADENCE_DAYS[DEFAULT_CADENCE]))


def recent_window_start(cadence: str, now: datetime) -> datetime:
    """Return the earliest ``event_date`` counted as "recent" for this cadence (§3.3.3)."""
    days = CADENCE_DAYS.get(cadence, CADENCE_DAYS[DEFAULT_CADENCE]) * RECENT_WINDOW_MULTIPLIER
    return now - timedelta(days=days)


def is_due(profile: Mapping[str, Any], now: datetime) -> bool:
    """Decide whether this profile should receive a check-in on this run.

    Three conditions, in the order that makes the cheapest one decisive first:

    1. **Not paused.** FR-4.6's pause is absolute — it suppresses the send without touching
       ``next_checkin_at``, so unpausing resumes the existing rhythm rather than firing immediately
       for every cycle that elapsed while paused.
    2. **Has an email to send to.** A PROFILE with no ``email`` cannot be delivered to, and SES
       would reject it; skipping here keeps that out of the per-user error path.
    3. **``next_checkin_at`` has passed** — *or is absent*, which reads as due now. That absence
       case is how every pre-slice-8 PROFILE seeds its own cycle on the first scheduled run, with
       no backfill: the first run sends, and the claim writes the cadence forward.
    """
    if is_paused(profile):
        return False
    if not profile.get("email"):
        return False
    due_at = parse_iso(profile.get("next_checkin_at"))
    return due_at is None or due_at <= now
