"""Pydantic models for the PROFILE singleton (Section 2.7 / 2.8).

The PROFILE item holds the user's profile *and* settings as a single DynamoDB item
(``PK=USER#<user_id>``, ``SK=PROFILE``). These models are the application-level schema —
DynamoDB itself stays schemaless (Section 2.7).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


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
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    portfolio_links: dict[str, str] = Field(default_factory=dict)
    phone: str | None = None
    settings: Settings = Field(default_factory=Settings)
    created_at: str
    updated_at: str


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
