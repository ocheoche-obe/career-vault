"""Models and tool config for the check-in email (§3.3, ADR-011, ADR-021).

The structured payload Haiku returns for a check-in, plus the forced-tool ``toolConfig`` that
makes it return one. Structured output via tool use rather than JSON-in-prose, per §3.1.2 — the
same pattern every other Bedrock call in this codebase uses.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: The three composition tiers of ADR-021, in descending order of personalisation. Carried on the
#: CHECKINLOG item and as a CloudWatch metric dimension, so "we have quietly been sending static
#: reminders for a month" is a visible fact rather than an assumption.
CheckinTier = Literal["personalized", "generic", "static"]

#: Hard cap on entries fed to the model, regardless of how many the recency window returns
#: (ADR-021). This *is* the cost guard — bound the prompt so an overrun is unreachable, rather
#: than metering spend at send time.
MAX_PROMPT_ENTRIES = 15

#: Per-entry character budget inside the prompt. Enough for a title plus a sentence or two of
#: context; the model is summarising for a nudge, not reading the full record.
MAX_ENTRY_CHARS = 400

#: Output cap on the Haiku call. A check-in email is a greeting, a couple of sentences and two or
#: three questions — generous at this size, and the other half of the structural budget guard.
MAX_OUTPUT_TOKENS = 700


class CheckinEmail(BaseModel):
    """The composed check-in, as Haiku returns it through the ``compose_checkin`` tool.

    Deliberately a set of *fields* rather than a blob of HTML. The Jinja2 template owns layout and
    escaping (§3.3.3 step 4), so the model never emits markup — which keeps a model that has just
    read arbitrary user-supplied entry content from being able to inject any into an email.
    """

    model_config = ConfigDict(extra="ignore")

    subject: str = Field(max_length=140)
    greeting: str = Field(max_length=200)
    # Present only in the personalized tier; the template hides the block when absent (§3.3.6).
    recent_activity_summary: str | None = Field(default=None, max_length=800)
    prompts: list[str] = Field(default_factory=list, max_length=4)
    aspirational_link: str | None = Field(default=None, max_length=400)
    sign_off: str = Field(max_length=200)


def build_checkin_tool_config() -> dict:
    """Force ``compose_checkin`` — the model may only reply by filling this schema.

    One tool with ``toolChoice: {"tool": ...}``, the same forced-structured-output shape the resume
    agent's phase tools use. Unlike chat's routing turn (ADR-038) there is nothing to route: this
    call has exactly one job, and free-text output would have to be parsed rather than validated.
    """
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": "compose_checkin",
                    "description": (
                        "Compose a short, warm check-in email nudging the user to log recent "
                        "career accomplishments. Return the parts of the email separately; do not "
                        "write HTML or markdown."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "subject": {
                                    "type": "string",
                                    "description": (
                                        "Email subject line. Specific and human, under 60 "
                                        "characters. No emoji, no 'Re:', no all-caps."
                                    ),
                                },
                                "greeting": {
                                    "type": "string",
                                    "description": (
                                        "One-line opening. Use the user's first name if provided."
                                    ),
                                },
                                "recent_activity_summary": {
                                    "type": "string",
                                    "description": (
                                        "One or two sentences referring to specific recent entries "
                                        "by name. Omit entirely if no recent entries were provided "
                                        "— never invent activity."
                                    ),
                                },
                                "prompts": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": (
                                        "Two or three short questions inviting the user to log "
                                        "something new. Concrete beats generic: prefer 'did the "
                                        "migration ship?' over 'any updates?'."
                                    ),
                                },
                                "aspirational_link": {
                                    "type": "string",
                                    "description": (
                                        "One sentence connecting the nudge to the user's stated "
                                        "career goal. Omit if no goal was provided."
                                    ),
                                },
                                "sign_off": {
                                    "type": "string",
                                    "description": "Short closing line. No signature block.",
                                },
                            },
                            "required": ["subject", "greeting", "prompts", "sign_off"],
                        }
                    },
                }
            }
        ],
        "toolChoice": {"tool": {"name": "compose_checkin"}},
    }
