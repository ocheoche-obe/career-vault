"""chat_lambda — the Phase A parse turn (Section 3.1.1).

``POST /chat`` turns a free-form user message into *either* a structured entry candidate or a
clarifying question. It never persists an entry: that is ``career_crud``'s exclusive privilege
(Section 3.1.3), so a prompt injection or LLM hallucination here cannot bypass the user's
confirmation step. This Lambda's IAM role can only touch ``CONVO#`` items.

Flow per turn:

1. Extract ``user_id`` from the Cognito-validated JWT claims (never the body — Section 4.2.4).
2. Query the session's history (AP-12).
3. Persist the user's message *before* calling Bedrock — if Bedrock fails, the message is already
   durably recorded and the user can retry without retyping (Section 3.1.1).
4. Call Haiku with two tools and ``toolChoice: any``, forcing structured output (Section 3.1.2).
5. Validate the tool input; on ``propose_entry``, mint the ULID that makes the eventual confirm
   idempotent (Section 3.1.4) and hand the candidate back for the user to review.

Errors return HTTP 200 with ``{"kind": "error"}`` so the chat UI keeps the session alive rather
than dropping the user out (Section 3.1.6).
"""

from __future__ import annotations

import json
import os

from aws_lambda_powertools.metrics import MetricUnit
from pydantic import ValidationError

from careervault import bedrock_client
from careervault.bedrock_client import BedrockError
from careervault.ddb_helpers import (
    extract_user_id,
    new_ulid,
    put_conversation_message,
    query_conversation,
)
from careervault.observability import bind_request_context, logger, metrics, tracer
from careervault.pydantic_models.conversation import build_message
from careervault.pydantic_models.entry import validate_entry
from careervault.pydantic_models.tools import build_tool_config

_CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "http://localhost:5173"),
}

_MAX_MESSAGE_CHARS = 4000

_SYSTEM_PROMPT = """\
You are CareerVault's intake assistant. The user tells you about things that happened in their \
career — jobs, projects, milestones, certifications, awards, education, volunteering, hobbies. \
Your only job is to turn what they say into one structured entry, or to ask one focused question \
when you cannot.

Rules:
- Call propose_entry when the message describes one concrete, recordable thing and you have every \
field that type requires.
- Call ask_clarification when the message is vague, describes nothing recordable, or is missing a \
field required for the type you would otherwise choose.
- Never invent dates, employers, issuers, or metrics. Absent information is a reason to ask, not \
to guess.
- Today's date is only relevant if the user says something relative like "last month"; if you \
cannot resolve a relative date confidently, ask.
- Prefer the most specific entry_type that fits. A certification is CERT, not MILESTONE.
"""

# One retry with the validation error appended, per Section 3.1.6. Beyond that we surface the
# generic chat error rather than paying for a third parse.
_MAX_PARSE_ATTEMPTS = 2

_GENERIC_ERROR = "I couldn't process that — please try again."


def _response(status_code: int, body: dict) -> dict:
    return {"statusCode": status_code, "headers": _CORS_HEADERS, "body": json.dumps(body)}


def _extract_tool_use(response: dict) -> dict | None:
    """Pull the single ``toolUse`` block out of a Converse response, if present."""
    for block in response.get("output", {}).get("message", {}).get("content", []):
        if "toolUse" in block:
            return block["toolUse"]
    return None


def _to_converse_messages(history: list[dict], new_message: str) -> list[dict]:
    """Render stored CONVO items plus the new turn into Converse message format.

    Only ``user``/``assistant`` roles are replayed; the system prompt is passed separately, and
    an assistant turn that ended in a tool call is replayed as its text summary rather than a
    dangling ``toolUse`` block (Converse requires every ``toolUse`` be followed by a matching
    ``toolResult``, which this single-shot parse turn never produces).
    """
    messages: list[dict] = []
    for item in history:
        role = item.get("role")
        content = item.get("content") or ""
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": [{"text": content}]})

    messages.append({"role": "user", "content": [{"text": new_message}]})
    return messages


def _proposal_summary(tool_input: dict) -> str:
    """Human-readable text persisted for an assistant turn that proposed an entry.

    The stored ``content`` is what gets replayed into later prompts, so it has to read as
    ordinary assistant prose rather than a serialised tool call.
    """
    entry_type = tool_input.get("entry_type", "ENTRY")
    title = tool_input.get("title", "entry")
    return f"Proposed {entry_type} entry: {title}"


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def handler(event, context) -> dict:
    bind_request_context(event)

    try:
        user_id = extract_user_id(event)
    except PermissionError:
        logger.warning("Request missing sub claim")
        return _response(401, {"message": "Unauthorized"})

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"message": "Body must be valid JSON"})

    message = (body.get("message") or "").strip()
    if not message:
        return _response(400, {"message": "'message' is required"})
    if len(message) > _MAX_MESSAGE_CHARS:
        return _response(400, {"message": f"'message' exceeds {_MAX_MESSAGE_CHARS} characters"})

    # A missing session_id starts a new session. The client echoes it back on subsequent turns.
    session_id = body.get("session_id") or new_ulid()
    logger.append_keys(session_id=session_id)

    history = query_conversation(user_id, session_id)

    # Persist the user's message before calling Bedrock (Section 3.1.1): if inference fails, the
    # input survives and retry is free.
    put_conversation_message(
        build_message(
            user_id=user_id,
            session_id=session_id,
            message_id=new_ulid(),
            role="user",
            content=message,
        ).model_dump()
    )

    messages = _to_converse_messages(history, message)
    tool_config = build_tool_config()

    validation_feedback: str | None = None
    for attempt in range(1, _MAX_PARSE_ATTEMPTS + 1):
        turn = list(messages)
        if validation_feedback:
            turn.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                "Your previous tool call was rejected by schema validation:\n"
                                f"{validation_feedback}\n"
                                "Call the tool again with the errors corrected."
                            )
                        }
                    ],
                }
            )

        try:
            response = bedrock_client.converse(turn, system=_SYSTEM_PROMPT, tool_config=tool_config)
        except BedrockError:
            logger.exception("Bedrock parse turn failed")
            return _response(200, {"kind": "error", "message": _GENERIC_ERROR, "session_id": session_id})

        tool_use = _extract_tool_use(response)
        if not tool_use:
            # toolChoice=any makes this near-impossible; treat as transient and don't retry-loop.
            logger.error("Converse returned no toolUse block", extra={"stop_reason": response.get("stopReason")})
            return _response(200, {"kind": "error", "message": _GENERIC_ERROR, "session_id": session_id})

        tool_name = tool_use.get("name", "")
        tool_input = tool_use.get("input", {}) or {}

        if tool_name == "ask_clarification":
            question = tool_input.get("question", "").strip()
            if not question:
                logger.error("ask_clarification returned an empty question")
                return _response(200, {"kind": "error", "message": _GENERIC_ERROR, "session_id": session_id})

            put_conversation_message(
                build_message(
                    user_id=user_id,
                    session_id=session_id,
                    message_id=new_ulid(),
                    role="assistant",
                    content=question,
                    tool_calls=[{"name": tool_name, "input": tool_input}],
                ).model_dump()
            )
            metrics.add_metric(name="ChatClarification", unit=MetricUnit.Count, value=1)
            return _response(
                200,
                {
                    "kind": "clarification",
                    "question": question,
                    "reason": tool_input.get("reason"),
                    "session_id": session_id,
                },
            )

        if tool_name != "propose_entry":
            logger.error("Converse called an unknown tool", extra={"tool_name": tool_name})
            return _response(200, {"kind": "error", "message": _GENERIC_ERROR, "session_id": session_id})

        # Strict per-type validation. Bedrock enforces the flat tool schema; the discriminated
        # union enforces the per-type requirements the flat schema cannot express (Section 3.1.2).
        try:
            entry = validate_entry(tool_input)
        except ValidationError as exc:
            logger.warning("propose_entry failed validation", extra={"attempt": attempt})
            if attempt < _MAX_PARSE_ATTEMPTS:
                validation_feedback = json.dumps(
                    [{"field": ".".join(str(p) for p in e["loc"]), "error": e["msg"]} for e in exc.errors()]
                )
                continue
            metrics.add_metric(name="ChatParseValidationFailure", unit=MetricUnit.Count, value=1)
            return _response(200, {"kind": "error", "message": _GENERIC_ERROR, "session_id": session_id})

        # The ULID is minted here, once, and travels with the candidate through the confirmation
        # UI back to career_crud — that is what makes the confirm idempotent (Section 3.1.4).
        candidate = entry.model_dump(mode="json", exclude_none=True)
        candidate["entry_id"] = new_ulid()

        put_conversation_message(
            build_message(
                user_id=user_id,
                session_id=session_id,
                message_id=new_ulid(),
                role="assistant",
                content=_proposal_summary(tool_input),
                tool_calls=[{"name": tool_name, "input": tool_input}],
            ).model_dump()
        )
        metrics.add_metric(name="ChatParseCandidate", unit=MetricUnit.Count, value=1)
        return _response(200, {"kind": "parse_candidate", "candidate": candidate, "session_id": session_id})

    # Unreachable: the loop either returns or continues to the final attempt's error path.
    return _response(200, {"kind": "error", "message": _GENERIC_ERROR, "session_id": session_id})
