"""Pydantic models for the PROFILE singleton (Section 2.7 / 2.8).

The PROFILE item holds the user's profile *and* settings as a single DynamoDB item
(``PK=USER#<user_id>``, ``SK=PROFILE``). These models are the application-level schema —
DynamoDB itself stays schemaless (Section 2.7).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


def _utcnow_iso() -> str:
    """Current UTC time as an ISO 8601 string with a ``Z`` suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class Settings(BaseModel):
    """User-tunable settings, nested on the PROFILE item (Section 2.8)."""

    checkin_cadence: str = "weekly"
    checkin_paused: bool = False
    preferred_template_id: str | None = None


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
    skills: list[str] = Field(default_factory=list)
    portfolio_links: dict[str, str] = Field(default_factory=dict)
    phone: str | None = None
    settings: Settings = Field(default_factory=Settings)
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
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    summary: str | None = Field(default=None, max_length=2000)
    skills: list[str] | None = Field(default=None, max_length=100)
    portfolio_links: dict[str, str] | None = None
    settings: Settings | None = None


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
