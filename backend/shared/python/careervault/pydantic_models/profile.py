"""Pydantic models for the PROFILE singleton (Section 2.7 / 2.8).

The PROFILE item holds the user's profile *and* settings as a single DynamoDB item
(``PK=USER#<user_id>``, ``SK=PROFILE``). These models are the application-level schema —
DynamoDB itself stays schemaless (Section 2.7).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _utcnow_iso() -> str:
    """Current UTC time as an ISO 8601 string with a ``Z`` suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


#: Cadence keyword → days between check-ins (FR-4.1). The mapping lives here rather than in
#: `checkin_lambda` because both the write side (validating what a user may select) and the read
#: side (advancing `next_checkin_at` after a send) need the same source of truth.
CADENCE_DAYS: dict[str, int] = {
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "quarterly": 91,
}

#: FR-4.2. Also the value assumed when a PROFILE has no `settings` attribute at all — which is the
#: state of every item written before slice 8, including the live dev one (ADR-039).
DEFAULT_CADENCE = "weekly"


class Settings(BaseModel):
    """User-tunable settings, nested on the PROFILE item (Section 2.8)."""

    checkin_cadence: str = DEFAULT_CADENCE
    checkin_paused: bool = False
    preferred_template_id: str | None = None


class SettingsUpdate(BaseModel):
    """The write-side contract for the nested ``settings`` object on ``PUT /settings``.

    Separate from :class:`Settings` for one reason that matters: **every field must be optional
    with no default that could be materialised**. FR-4.6 needs cadence and pause to move
    independently, so a request that sets only ``checkin_paused`` must not carry a
    ``checkin_cadence`` value at all — not even the correct-looking ``"weekly"``, which would
    overwrite a user's ``monthly`` setting on the way past.

    That is the same replace-don't-merge trap B-014 caught at the top level, reproduced one level
    down and considerably harder to see, since the offending value is a *default* rather than
    something the caller sent. :func:`careervault.ddb_helpers.update_profile` relies on this model
    being dumped with ``exclude_unset=True``; see ADR-040.
    """

    model_config = ConfigDict(extra="forbid")

    checkin_cadence: Literal["weekly", "biweekly", "monthly", "quarterly"] | None = None
    checkin_paused: bool | None = None


class Profile(BaseModel):
    """The PROFILE singleton — user profile plus embedded settings (Section 2.8)."""

    PK: str
    SK: str = "PROFILE"
    entity_type: str = "PROFILE"
    email: str
    # `name` and `location` back the résumé identity header (backlog B-008). They were absent
    # through slice 6, which is why a generated résumé rendered the literal word "Résumé": the
    # template reads `contact.name or contact.email`, `_contact_from_profile` read `profile
    # ["name"]`, and nothing on either side of that ever existed. Cognito cannot supply them
    # either — the user pool holds only `email`, `email_verified` and `sub`.
    name: str | None = None
    location: str | None = None
    summary: str | None = None
    # The check-in's tier-2 fallback talks about where the user is *heading* when there is no
    # recent activity to talk about (§3.3.6, ADR-021). Both the architecture doc and the slice-8
    # plan referenced `profile.aspirational_goal` as though it existed; it did not, exactly as
    # `name`/`location` did not before B-008. Absent it, tier 2 has nothing to say and degrades to
    # the static tier for every user, silently.
    aspirational_goal: str | None = None
    skills: list[str] = Field(default_factory=list)
    portfolio_links: dict[str, str] = Field(default_factory=dict)
    phone: str | None = None
    settings: Settings = Field(default_factory=Settings)
    # Check-in scheduling state (ADR-039). Server-owned: written only by `checkin_lambda` after a
    # send, never accepted from a request body — which is why none of them appear on
    # `ProfileUpdate`. `next_checkin_at` absent means "due now", so an existing PROFILE seeds its
    # own cycle on the first scheduled run with no migration.
    next_checkin_at: str | None = None
    last_checkin_sent_at: str | None = None
    # Written by `ses_event_handler` off the bounce/complaint topic (§4.5.4).
    bounce_count: int = 0
    last_bounce_at: str | None = None
    complained_at: str | None = None
    created_at: str
    updated_at: str


class ProfileUpdate(BaseModel):
    """The write-side contract for ``PUT /settings`` — *only* user-editable fields.

    Deliberately not `Profile`. The server owns `PK`, `SK`, `entity_type`, `created_at`,
    `updated_at`, and — critically — `email`, which comes from the Cognito JWT and must never be
    settable from a request body (§4.2.4 applies to identity generally, not just to `user_id`).
    A client that submits any of them is rejected rather than silently ignored, so a confused
    caller learns immediately instead of believing a write landed.

    Every field is optional: the route is a partial update, and omitting a field leaves the
    stored value alone. Sending an explicit ``null`` is how a field gets cleared.

    **Only fields something actually writes are here**, and that restraint is deliberate rather
    than laziness — a field with no UI ships untested. B-008 admitted ``name``, ``location`` and
    ``phone``; slice 8 admits ``aspirational_goal`` and ``settings``, both of which the settings
    form now writes. ``summary``, ``skills`` and ``portfolio_links`` remain out.

    ``settings`` was the one deliberately withheld by B-008 rather than merely unneeded, and it
    is worth remembering why: partial-update semantics are per *top-level attribute*, so DynamoDB
    would ``SET settings = <what was sent>`` and replace the whole nested object —
    ``{"settings": {"checkin_paused": true}}`` would silently drop ``checkin_cadence``. It is
    admitted here only because ADR-040 fixes the write path underneath it (dotted document paths,
    one per sub-field) and :class:`SettingsUpdate` keeps every sub-field unset-by-default.
    Note the ordering: the merge semantics landed *first*; the field is not what makes it safe.

    Server-owned scheduling state (``next_checkin_at``, ``last_checkin_sent_at``, the bounce
    counters) is **absent by design**, on the same reasoning that keeps ``email`` out — a client
    that could postpone its own next check-in, or clear its own bounce count, is a client that can
    steer a scheduled job from a request body.

    Add a field here when something writes it.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    aspirational_goal: str | None = Field(default=None, max_length=300)
    settings: SettingsUpdate | None = None


def default_profile(user_id: str, email: str) -> Profile:
    """Build the default PROFILE returned on first read when none exists yet.

    Not persisted by the read path — ``settings_lambda`` returns this so a brand-new user
    sees a coherent profile shape; the first explicit write (via ``settings_lambda``'s
    update path, future work) is what actually creates the item.
    """
    now = _utcnow_iso()
    return Profile(
        PK=f"USER#{user_id}",
        email=email,
        created_at=now,
        updated_at=now,
    )
