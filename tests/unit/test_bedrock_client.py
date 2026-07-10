"""Unit tests for the Bedrock wrapper (ADR-017 / ADR-031, NFR-3.3 retry policy).

No test calls Bedrock. The retry-count assertions matter for cost: every extra attempt is a
paid inference call.
"""

import io
import json

import pytest
from botocore.exceptions import ClientError

from careervault import bedrock_client
from careervault.bedrock_client import MAX_ATTEMPTS, BedrockError, converse, embed, embed_many


class FakeBedrock:
    def __init__(self, *, converse_results=None, invoke_results=None):
        self.converse_calls: list[dict] = []
        self.invoke_calls: list[dict] = []
        self._converse_results = list(converse_results or [])
        self._invoke_results = list(invoke_results or [])

    def converse(self, **kwargs):
        self.converse_calls.append(kwargs)
        result = self._converse_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def invoke_model(self, **kwargs):
        self.invoke_calls.append(kwargs)
        result = self._invoke_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code}}, "Converse")


def _embed_body(vector):
    return {"body": io.BytesIO(json.dumps({"embedding": vector, "inputTextTokenCount": 7}).encode())}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Backoff sleeps would make the suite slow for no benefit."""
    monkeypatch.setattr(bedrock_client.time, "sleep", lambda _: None)


@pytest.fixture
def fake_client(monkeypatch):
    def _install(**kwargs):
        fake = FakeBedrock(**kwargs)
        monkeypatch.setattr(bedrock_client, "get_client", lambda: fake)
        return fake

    return _install


OK_RESPONSE = {"output": {"message": {"content": []}}, "stopReason": "end_turn", "usage": {}}
MESSAGES = [{"role": "user", "content": [{"text": "hi"}]}]


def test_converse_passes_inference_profile_as_model_id(fake_client):
    fake = fake_client(converse_results=[OK_RESPONSE])
    converse(MESSAGES)
    # ADR-031: Haiku 4.5 is invoked through the `us.` profile, not the bare foundation-model ID.
    assert fake.converse_calls[0]["modelId"].startswith("us.anthropic.claude-haiku-4-5")


def test_converse_sends_system_and_tool_config(fake_client):
    fake = fake_client(converse_results=[OK_RESPONSE])
    converse(MESSAGES, system="be terse", tool_config={"tools": [], "toolChoice": {"any": {}}})

    call = fake.converse_calls[0]
    assert call["system"] == [{"text": "be terse"}]
    assert call["toolConfig"]["toolChoice"] == {"any": {}}
    assert call["inferenceConfig"]["temperature"] == 0.0  # determinism for extraction


def test_converse_omits_optional_blocks_when_absent(fake_client):
    fake = fake_client(converse_results=[OK_RESPONSE])
    converse(MESSAGES)
    assert "system" not in fake.converse_calls[0]
    assert "toolConfig" not in fake.converse_calls[0]


def test_transient_error_is_retried_then_succeeds(fake_client):
    fake = fake_client(converse_results=[_client_error("ThrottlingException"), OK_RESPONSE])
    assert converse(MESSAGES)["stopReason"] == "end_turn"
    assert len(fake.converse_calls) == 2


def test_transient_error_is_bounded_at_max_attempts(fake_client):
    fake = fake_client(converse_results=[_client_error("ThrottlingException")] * MAX_ATTEMPTS)
    with pytest.raises(BedrockError):
        converse(MESSAGES)
    # Every attempt is a paid call — the bound is the cost guard (NFR-3.3).
    assert len(fake.converse_calls) == MAX_ATTEMPTS == 3


def test_permanent_error_is_not_retried(fake_client):
    fake = fake_client(converse_results=[_client_error("AccessDeniedException")])
    with pytest.raises(BedrockError):
        converse(MESSAGES)
    assert len(fake.converse_calls) == 1  # retrying a permissions bug just burns money


def test_validation_error_is_not_retried(fake_client):
    fake = fake_client(converse_results=[_client_error("ValidationException")])
    with pytest.raises(BedrockError):
        converse(MESSAGES)
    assert len(fake.converse_calls) == 1


def test_embed_returns_vector_and_uses_bare_model_id(fake_client):
    fake = fake_client(invoke_results=[_embed_body([0.1, 0.2, 0.3])])
    assert embed("hello") == [0.1, 0.2, 0.3]

    call = fake.invoke_calls[0]
    # Titan v2 is ON_DEMAND — bare model ID, no inference profile (ADR-031).
    assert call["modelId"] == "amazon.titan-embed-text-v2:0"
    body = json.loads(call["body"])
    assert body["inputText"] == "hello"
    assert body["dimensions"] == 1024
    assert body["normalize"] is True


def test_embed_retries_transient_errors(fake_client):
    fake = fake_client(invoke_results=[_client_error("ServiceUnavailableException"), _embed_body([0.5])])
    assert embed("hello") == [0.5]
    assert len(fake.invoke_calls) == 2


def test_embed_raises_when_no_vector_returned(fake_client):
    fake_client(invoke_results=[{"body": io.BytesIO(json.dumps({}).encode())}])
    with pytest.raises(BedrockError):
        embed("hello")


def test_embed_many_is_one_call_per_text_in_order(fake_client):
    # Titan v2's InvokeModel takes a single inputText — "batch" is a client-side loop.
    fake = fake_client(invoke_results=[_embed_body([1.0]), _embed_body([2.0])])
    assert embed_many(["a", "b"]) == [[1.0], [2.0]]
    assert len(fake.invoke_calls) == 2
    assert json.loads(fake.invoke_calls[0]["body"])["inputText"] == "a"
    assert json.loads(fake.invoke_calls[1]["body"])["inputText"] == "b"
