"""Unit tests for chat_lambda — the Phase A parse turn (Section 3.1).

Bedrock and DynamoDB are faked; no test reaches AWS and the suite costs nothing to run.
"""

import pytest
from helpers import FakeLambdaContext, api_event, body_of, load_handler, text_response, tool_use_response

from careervault import bedrock_client
from careervault.bedrock_client import BedrockError

chat = load_handler("chat_handler", "chat")

VALID_CERT_INPUT = {
    "entry_type": "CERT",
    "title": "AWS Solutions Architect Associate",
    "content": "Passed the exam on the first attempt.",
    "issuer": "AWS",
    "issued_date": "2026-05-01",
    "skills_tags": ["aws"],
}

# Client-supplied identifiers must be well-formed ULIDs (ADR-032); the spec's example ULID and a
# sibling serve as fixed session/message ids.
SESSION_ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
MESSAGE_ULID = "01BX5ZZKBKACTAV9WEVGEMMVRZ"


@pytest.fixture
def fake_ddb(monkeypatch):
    """Capture CONVO writes (reporting each as created) and serve empty history."""
    writes: list[dict] = []
    monkeypatch.setattr(chat, "put_conversation_message", lambda msg: writes.append(msg) or True)
    monkeypatch.setattr(chat, "query_conversation", lambda user_id, session_id: [])
    return writes


def _mock_converse(monkeypatch, responses):
    """Patch bedrock_client.converse to return each response in turn; record the requests."""
    seen: list[list[dict]] = []
    queue = list(responses)

    def _fake(messages, **kwargs):
        seen.append(messages)
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(bedrock_client, "converse", _fake)
    return seen


def test_propose_entry_returns_candidate_with_minted_ulid(monkeypatch, fake_ddb):
    _mock_converse(monkeypatch, [tool_use_response("propose_entry", VALID_CERT_INPUT)])

    response = chat.handler(api_event({"message": "I passed the AWS SAA exam."}), FakeLambdaContext())
    body = body_of(response)

    assert response["statusCode"] == 200
    assert body["kind"] == "parse_candidate"
    assert body["candidate"]["entry_type"] == "CERT"
    # The ULID is minted here and travels to career_crud — that's what makes confirm idempotent.
    assert len(body["candidate"]["entry_id"]) == 26
    assert body["session_id"]
    # Both the user message and the assistant tool-call turn are persisted.
    assert len(fake_ddb) == 2
    assert fake_ddb[0]["role"] == "user"
    assert fake_ddb[1]["role"] == "assistant"
    assert fake_ddb[1]["tool_calls"][0]["name"] == "propose_entry"


def test_ask_clarification_returns_question(monkeypatch, fake_ddb):
    _mock_converse(
        monkeypatch,
        [tool_use_response("ask_clarification", {"question": "When did you start?", "reason": "missing_date"})],
    )

    body = body_of(chat.handler(api_event({"message": "I worked at Acme."}), FakeLambdaContext()))

    assert body["kind"] == "clarification"
    assert body["question"] == "When did you start?"
    assert body["reason"] == "missing_date"
    assert fake_ddb[1]["content"] == "When did you start?"


def test_convo_writes_use_convo_sk_prefix(monkeypatch, fake_ddb):
    _mock_converse(monkeypatch, [tool_use_response("propose_entry", VALID_CERT_INPUT)])
    chat.handler(api_event({"message": "hi", "session_id": SESSION_ULID}), FakeLambdaContext())

    for msg in fake_ddb:
        assert msg["SK"].startswith(f"CONVO#{SESSION_ULID}#")
        assert msg["PK"] == "USER#user-sub-1"
        assert msg["entity_type"] == "CONVO_MESSAGE"


def test_supplied_session_id_is_echoed(monkeypatch, fake_ddb):
    _mock_converse(monkeypatch, [tool_use_response("propose_entry", VALID_CERT_INPUT)])
    body = body_of(chat.handler(api_event({"message": "hi", "session_id": SESSION_ULID}), FakeLambdaContext()))
    assert body["session_id"] == SESSION_ULID


def test_invalid_tool_input_retries_once_then_succeeds(monkeypatch, fake_ddb):
    # JOB without `employer` fails the discriminated union; the retry supplies it.
    bad = {"entry_type": "JOB", "title": "Engineer", "content": "Worked.", "start_date": "2020-01-01"}
    good = {**bad, "employer": "Acme Corp"}
    seen = _mock_converse(
        monkeypatch, [tool_use_response("propose_entry", bad), tool_use_response("propose_entry", good)]
    )

    body = body_of(chat.handler(api_event({"message": "I was an engineer."}), FakeLambdaContext()))

    assert body["kind"] == "parse_candidate"
    assert body["candidate"]["employer"] == "Acme Corp"
    # Second call carries the validation error back to the model (Section 3.1.6).
    assert len(seen) == 2
    assert "schema validation" in seen[1][-1]["content"][0]["text"]
    assert "employer" in seen[1][-1]["content"][0]["text"]


def test_invalid_tool_input_twice_returns_chat_error(monkeypatch, fake_ddb):
    bad = {"entry_type": "JOB", "title": "Engineer", "content": "Worked.", "start_date": "2020-01-01"}
    seen = _mock_converse(
        monkeypatch, [tool_use_response("propose_entry", bad), tool_use_response("propose_entry", bad)]
    )

    response = chat.handler(api_event({"message": "I was an engineer."}), FakeLambdaContext())
    body = body_of(response)

    # HTTP 200 keeps the chat session alive rather than dropping the user out (Section 3.1.6).
    assert response["statusCode"] == 200
    assert body["kind"] == "error"
    assert len(seen) == 2  # bounded at _MAX_PARSE_ATTEMPTS; no third paid call


def test_bedrock_failure_returns_chat_error_but_keeps_user_message(monkeypatch, fake_ddb):
    _mock_converse(monkeypatch, [BedrockError("throttled")])

    response = chat.handler(api_event({"message": "I passed the exam."}), FakeLambdaContext())
    body = body_of(response)

    assert response["statusCode"] == 200
    assert body["kind"] == "error"
    # The user's message was persisted before Bedrock was called, so retry costs them nothing.
    assert len(fake_ddb) == 1
    assert fake_ddb[0]["role"] == "user"


def test_user_message_is_persisted_before_bedrock_is_called(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(chat, "query_conversation", lambda u, s: [])
    monkeypatch.setattr(chat, "put_conversation_message", lambda msg: order.append(f"put:{msg['role']}"))

    def _fake(messages, **kwargs):
        order.append("bedrock")
        return tool_use_response("propose_entry", VALID_CERT_INPUT)

    monkeypatch.setattr(bedrock_client, "converse", _fake)
    chat.handler(api_event({"message": "hi"}), FakeLambdaContext())

    assert order == ["put:user", "bedrock", "put:assistant"]


def test_history_is_replayed_into_the_prompt(monkeypatch):
    monkeypatch.setattr(chat, "put_conversation_message", lambda msg: True)
    monkeypatch.setattr(
        chat,
        "query_conversation",
        lambda u, s: [
            {"role": "user", "content": "I got a cert."},
            {"role": "assistant", "content": "Which one?"},
        ],
    )
    seen = _mock_converse(monkeypatch, [tool_use_response("propose_entry", VALID_CERT_INPUT)])

    chat.handler(api_event({"message": "AWS SAA", "session_id": SESSION_ULID}), FakeLambdaContext())

    roles = [m["role"] for m in seen[0]]
    assert roles == ["user", "assistant", "user"]
    assert seen[0][-1]["content"][0]["text"] == "AWS SAA"


# --- turn idempotency (ADR-032) ------------------------------------------------

def test_client_message_id_names_the_persisted_user_message(monkeypatch, fake_ddb):
    _mock_converse(monkeypatch, [tool_use_response("propose_entry", VALID_CERT_INPUT)])

    chat.handler(
        api_event({"message": "hi", "session_id": SESSION_ULID, "client_message_id": MESSAGE_ULID}),
        FakeLambdaContext(),
    )

    assert fake_ddb[0]["message_id"] == MESSAGE_ULID
    assert fake_ddb[0]["SK"] == f"CONVO#{SESSION_ULID}#{MESSAGE_ULID}"


@pytest.mark.parametrize("field", ["session_id", "client_message_id"])
def test_malformed_ulid_identifier_is_bad_request(field, fake_ddb):
    response = chat.handler(api_event({"message": "hi", field: "not#a#ulid"}), FakeLambdaContext())
    assert response["statusCode"] == 400
    assert fake_ddb == []  # rejected before anything was persisted


def test_retried_turn_proceeds_when_message_already_persisted(monkeypatch):
    # put returning False means the SK collided — the client is retrying and the message is
    # already durable. The turn must proceed into inference, not error out.
    monkeypatch.setattr(chat, "put_conversation_message", lambda msg: False)
    monkeypatch.setattr(chat, "query_conversation", lambda u, s: [])
    _mock_converse(monkeypatch, [tool_use_response("propose_entry", VALID_CERT_INPUT)])

    body = body_of(
        chat.handler(
            api_event({"message": "hi", "session_id": SESSION_ULID, "client_message_id": MESSAGE_ULID}),
            FakeLambdaContext(),
        )
    )

    assert body["kind"] == "parse_candidate"


def test_retried_turn_replays_its_own_message_exactly_once(monkeypatch):
    # The failed attempt already persisted this turn's message, so it comes back in history.
    # Replay must drop it — it is appended as the new turn — or the prompt would contain it twice.
    monkeypatch.setattr(chat, "put_conversation_message", lambda msg: False)
    monkeypatch.setattr(
        chat,
        "query_conversation",
        lambda u, s: [
            {"role": "user", "content": "I got a cert.", "message_id": "01BX5ZZKBKACTAV9WEVGEMMVR0"},
            {"role": "assistant", "content": "Which one?", "message_id": "01BX5ZZKBKACTAV9WEVGEMMVR1"},
            {"role": "user", "content": "AWS SAA", "message_id": MESSAGE_ULID},
        ],
    )
    seen = _mock_converse(monkeypatch, [tool_use_response("propose_entry", VALID_CERT_INPUT)])

    chat.handler(
        api_event({"message": "AWS SAA", "session_id": SESSION_ULID, "client_message_id": MESSAGE_ULID}),
        FakeLambdaContext(),
    )

    texts = [m["content"][0]["text"] for m in seen[0]]
    assert texts == ["I got a cert.", "Which one?", "AWS SAA"]  # exactly once, as the final turn


def test_no_tool_use_block_returns_chat_error(monkeypatch, fake_ddb):
    _mock_converse(monkeypatch, [text_response()])
    body = body_of(chat.handler(api_event({"message": "hi"}), FakeLambdaContext()))
    assert body["kind"] == "error"


def test_unknown_tool_returns_chat_error(monkeypatch, fake_ddb):
    _mock_converse(monkeypatch, [tool_use_response("delete_everything", {})])
    body = body_of(chat.handler(api_event({"message": "hi"}), FakeLambdaContext()))
    assert body["kind"] == "error"


def test_missing_sub_claim_is_unauthorized():
    response = chat.handler(api_event({"message": "hi"}, sub=None), FakeLambdaContext())
    assert response["statusCode"] == 401


def test_empty_message_is_bad_request(fake_ddb):
    assert chat.handler(api_event({"message": "   "}), FakeLambdaContext())["statusCode"] == 400


def test_missing_message_is_bad_request(fake_ddb):
    assert chat.handler(api_event({}), FakeLambdaContext())["statusCode"] == 400


def test_oversized_message_is_bad_request(fake_ddb):
    event = api_event({"message": "x" * 4001})
    assert chat.handler(event, FakeLambdaContext())["statusCode"] == 400


def test_malformed_json_body_is_bad_request(fake_ddb):
    assert chat.handler(api_event("{not json"), FakeLambdaContext())["statusCode"] == 400
