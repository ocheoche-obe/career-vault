"""Pydantic model for CONVERSATION_MESSAGE items (Section 2.7 / 2.8).

One item per chat turn, keyed ``PK=USER#<user_id>`` / ``SK=CONVO#<session_id>#<message_id>``.
The composite SK means a single ``begins_with(SK, "CONVO#<session_id>#")`` Query returns one
session's history in ULID order — which is chronological order, for free (ADR-026).

``chat_lambda`` is the only writer, and its IAM role can only touch the ``CONVO#`` prefix
(Section 4.2.3): it cannot write ENTRY items even if an LLM told it to.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .entry import utcnow_iso

Role = Literal["user", "assistant", "system"]


class ConversationMessage(BaseModel):
    """A single persisted chat message (Section 2.8 sample shape)."""

    model_config = ConfigDict(extra="forbid")

    PK: str
    SK: str
    entity_type: Literal["CONVO_MESSAGE"] = "CONVO_MESSAGE"
    session_id: str
    message_id: str
    role: Role
    content: str
    #: Populated for assistant turns that invoked a tool — the raw tool name + input, so a
    #: session can be replayed or audited without re-calling Bedrock.
    tool_calls: list[dict[str, Any]] | None = None
    created_at: str = Field(default_factory=utcnow_iso)


def build_message(
    *,
    user_id: str,
    session_id: str,
    message_id: str,
    role: Role,
    content: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> ConversationMessage:
    """Construct a CONVO message with its keys already assembled."""
    return ConversationMessage(
        PK=f"USER#{user_id}",
        SK=f"CONVO#{session_id}#{message_id}",
        session_id=session_id,
        message_id=message_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
    )
