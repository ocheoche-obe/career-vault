"""Unit tests for chat_lambda — the routing turn (Section 3.1 / ADR-038).

Bedrock and DynamoDB are faked; no test reaches AWS and the suite costs nothing to run.
"""

import pytest
from helpers import FakeLambdaContext, api_event, body_of, load_handler, text_response, tool_use_response

from careervault import bedrock_client
from careervault.bedrock_client import BedrockError

# handler.py imports its sibling `qa` module, which resolves from /var/task in Lambda. `load_handler`
# puts the function directory on sys.path for the duration of the load and takes it back off after,
# so no permanent path entry is needed here.
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


# ---------------------------------------------------------------------------------------------
# Slice 7 — chat over your data (FR-6.1 / ADR-038)
#
# A Q&A turn is: route (Haiku, forced tool) -> Titan embed -> rank in-Lambda -> synthesize
# (Haiku, NO tools). The tests below pin both the behaviour and the security properties that
# made the ENTRY# read widening acceptable.
# ---------------------------------------------------------------------------------------------

ANSWER_TOOL_INPUT = {"query": "certifications held by the user", "intent": "aggregate"}


def _entry_item(entry_type="CERT", title="AWS SAA", **extra):
    item = {
        "PK": "USER#user-sub-1",
        "SK": f"ENTRY#{MESSAGE_ULID}",
        "entry_id": MESSAGE_ULID,
        "entry_type": entry_type,
        "title": title,
        "content": "Passed on the first attempt.",
        "embedding": [0.1] * 8,
    }
    item.update(extra)
    return item


def _mock_converse_capturing_kwargs(monkeypatch, responses):
    """Like _mock_converse, but records each call's kwargs so tool_config can be asserted on."""
    calls: list[dict] = []
    queue = list(responses)

    def _fake(messages, **kwargs):
        calls.append({"messages": messages, **kwargs})
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(bedrock_client, "converse", _fake)
    return calls


@pytest.fixture
def fake_corpus(monkeypatch):
    """Serve a fixed ENTRY# corpus and a stub Titan embedding."""
    corpus = [_entry_item("CERT"), _entry_item("CERT", "Azure Fundamentals"), _entry_item("JOB", "SRE")]
    monkeypatch.setattr(chat, "query_entries", lambda user_id: corpus)
    monkeypatch.setattr(bedrock_client, "embed", lambda text: [0.1] * 8)
    return corpus


def test_answer_question_returns_grounded_answer_with_sources(monkeypatch, fake_ddb, fake_corpus):
    _mock_converse_capturing_kwargs(
        monkeypatch,
        [tool_use_response("answer_question", ANSWER_TOOL_INPUT), text_response("You hold two certifications.")],
    )

    response = chat.handler(api_event({"message": "how many certs do I have?"}), FakeLambdaContext())
    body = body_of(response)

    assert response["statusCode"] == 200
    assert body["kind"] == "answer"
    assert body["answer"] == "You hold two certifications."
    assert [s["title"] for s in body["sources"]] == ["AWS SAA", "Azure Fundamentals", "SRE"]


def test_synthesis_call_is_made_with_no_tools(monkeypatch, fake_ddb, fake_corpus):
    """THE injection control (ADR-038): the one call that sees entry content has no tool to call.

    If this fails, injected entry content saying "now call propose_entry" has something to reach,
    and the widening in §4.2.3 stops being defensible. Do not relax it.
    """
    calls = _mock_converse_capturing_kwargs(
        monkeypatch,
        [tool_use_response("answer_question", ANSWER_TOOL_INPUT), text_response("Two.")],
    )

    chat.handler(api_event({"message": "how many certs?"}), FakeLambdaContext())

    routing_call, synthesis_call = calls
    assert routing_call["tool_config"]["toolChoice"] == {"any": {}}  # routing keeps forced tools
    assert synthesis_call.get("tool_config") is None  # synthesis has none at all


def test_routing_call_never_sees_entry_content(monkeypatch, fake_ddb, fake_corpus):
    """Privilege separation: the call *with* tools must not be fed untrusted entry text."""
    calls = _mock_converse_capturing_kwargs(
        monkeypatch,
        [tool_use_response("answer_question", ANSWER_TOOL_INPUT), text_response("Two.")],
    )

    chat.handler(api_event({"message": "how many certs?"}), FakeLambdaContext())

    routing_text = str(calls[0]["messages"])
    assert "Passed on the first attempt" not in routing_text
    assert "career_history" not in routing_text


def test_census_counts_the_whole_corpus_not_the_retrieved_slice(monkeypatch, fake_ddb):
    """The census must survive top-k truncation, or counting questions answer 'k'."""
    corpus = [_entry_item("CERT", f"Cert {i}") for i in range(12)]
    monkeypatch.setattr(chat, "query_entries", lambda user_id: corpus)
    monkeypatch.setattr(bedrock_client, "embed", lambda text: [0.1] * 8)
    calls = _mock_converse_capturing_kwargs(
        monkeypatch,
        [tool_use_response("answer_question", ANSWER_TOOL_INPUT), text_response("Twelve.")],
    )

    body = body_of(chat.handler(api_event({"message": "how many?"}), FakeLambdaContext()))

    grounding = str(calls[1]["messages"])
    assert "CERT: 12" in grounding
    assert "TOTAL: 12" in grounding
    assert len(body["sources"]) == 8  # top-k truncated, census did not


def test_answer_is_persisted_as_an_assistant_turn(monkeypatch, fake_ddb, fake_corpus):
    _mock_converse_capturing_kwargs(
        monkeypatch,
        [tool_use_response("answer_question", ANSWER_TOOL_INPUT), text_response("You hold two certifications.")],
    )

    chat.handler(api_event({"message": "how many certs?"}), FakeLambdaContext())

    assistant_turns = [w for w in fake_ddb if w["role"] == "assistant"]
    assert assistant_turns[-1]["content"] == "You hold two certifications."


def test_a_question_never_writes_an_entry(monkeypatch, fake_ddb, fake_corpus):
    """Exit criterion: asking a question cannot create an entry (§3.1.3 stands)."""
    _mock_converse_capturing_kwargs(
        monkeypatch,
        [tool_use_response("answer_question", ANSWER_TOOL_INPUT), text_response("Two.")],
    )

    body = body_of(chat.handler(api_event({"message": "how many certs?"}), FakeLambdaContext()))

    assert body["kind"] == "answer"
    assert "candidate" not in body
    # Everything this Lambda wrote is a conversation message, never an ENTRY# item.
    assert all(w["SK"].startswith("CONVO#") for w in fake_ddb)


def test_empty_corpus_answers_without_calling_bedrock(monkeypatch, fake_ddb):
    """Nothing to ground against — a model round-trip could only cost more to say the same thing."""
    monkeypatch.setattr(chat, "query_entries", lambda user_id: [])

    def _explode(*args, **kwargs):  # pragma: no cover - asserts it is never reached
        raise AssertionError("embed must not be called on an empty corpus")

    monkeypatch.setattr(bedrock_client, "embed", _explode)
    calls = _mock_converse_capturing_kwargs(
        monkeypatch, [tool_use_response("answer_question", ANSWER_TOOL_INPUT)]
    )

    body = body_of(chat.handler(api_event({"message": "what have I done?"}), FakeLambdaContext()))

    assert body["kind"] == "answer"
    assert body["sources"] == []
    assert "haven't logged anything yet" in body["answer"]
    assert len(calls) == 1  # routing only; no synthesis call


def test_embedding_failure_degrades_to_a_recoverable_chat_error(monkeypatch, fake_ddb, fake_corpus):
    _mock_converse_capturing_kwargs(
        monkeypatch, [tool_use_response("answer_question", ANSWER_TOOL_INPUT)]
    )

    def _fail(text):
        raise BedrockError("titan down")

    monkeypatch.setattr(bedrock_client, "embed", _fail)

    body = body_of(chat.handler(api_event({"message": "how many certs?"}), FakeLambdaContext()))

    assert body["kind"] == "error"  # session stays alive (Section 3.1.6)


def test_synthesis_failure_degrades_to_a_recoverable_chat_error(monkeypatch, fake_ddb, fake_corpus):
    _mock_converse_capturing_kwargs(
        monkeypatch,
        [tool_use_response("answer_question", ANSWER_TOOL_INPUT), BedrockError("haiku down")],
    )

    body = body_of(chat.handler(api_event({"message": "how many certs?"}), FakeLambdaContext()))

    assert body["kind"] == "error"


def test_empty_query_from_the_router_is_an_error_not_a_blind_retrieval(monkeypatch, fake_ddb, fake_corpus):
    _mock_converse_capturing_kwargs(
        monkeypatch, [tool_use_response("answer_question", {"query": "  ", "intent": "lookup"})]
    )

    body = body_of(chat.handler(api_event({"message": "?"}), FakeLambdaContext()))

    assert body["kind"] == "error"
