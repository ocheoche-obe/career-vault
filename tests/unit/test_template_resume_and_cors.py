"""Template settings behind two fresh-eyes review fixes, which nothing at runtime exercises.

- The résumé worker's async retries are off: each retry would re-run the Sonnet agent at full cost.
- API Gateway's own 4XX/5XX responses carry CORS headers (B-041), so the SPA can read an expired
  session's 401 instead of seeing an opaque CORS failure.
"""

import pytest
from helpers import load_template_resources


@pytest.fixture(scope="module")
def resources():
    return load_template_resources()


def test_the_resume_worker_is_never_retried(resources):
    config = resources["ResumeAgentFunction"]["Properties"]["EventInvokeConfig"]
    assert config["MaximumRetryAttempts"] == 0


def test_a_throttled_worker_event_expires_before_the_poll_calls_the_run_lost(resources):
    # Throttles are requeued for up to 6h regardless of MaximumRetryAttempts. The event must die
    # before the poll's verdict, or an unpolled run can be claimed and billed hours later.
    from helpers import load_handler

    handler = load_handler("resume_agent_handler_template", "resume_agent")
    verdict_after = handler._WORKER_TIMEOUT_SECONDS + handler._WORKER_GRACE_SECONDS
    config = resources["ResumeAgentFunction"]["Properties"]["EventInvokeConfig"]
    assert 60 <= config["MaximumEventAgeInSeconds"] < verdict_after


def test_the_resume_agent_can_make_its_conditional_updates(resources):
    statements = resources["ResumeAgentFunction"]["Properties"]["Policies"][0]["Statement"]
    table_actions = next(
        s["Action"] for s in statements if s["Resource"] == {"!GetAtt": "CareerVaultTable.Arn"}
    )
    assert "dynamodb:UpdateItem" in table_actions


@pytest.mark.parametrize("response_type", ["DEFAULT_4XX", "DEFAULT_5XX"])
def test_gateway_error_responses_carry_cors_headers(resources, response_type):
    headers = resources["ApiGateway"]["Properties"]["GatewayResponses"][response_type][
        "ResponseParameters"
    ]["Headers"]
    assert headers["Access-Control-Allow-Origin"] == "'*'"
    assert "Authorization" in headers["Access-Control-Allow-Headers"]
