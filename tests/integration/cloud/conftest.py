"""Fixtures for the deployed-dev tier (ADR-042).

Lambdas are invoked **directly**, with a synthetic API Gateway proxy event carrying Cognito
authorizer claims, rather than through API Gateway with a real JWT. The app client is deliberately
PKCE-only — its ``ExplicitAuthFlows`` is ``ALLOW_REFRESH_TOKEN_AUTH`` alone (ADR-025) — so there is
no unattended way to mint a token, and adding one would widen the auth surface permanently to buy a
test convenience.

What this tier does cover, for real and for ~$0: handler logic, the deployed environment variables,
the IAM policy actually attached to each role, and DynamoDB. What it does not: API Gateway routing,
CORS preflight, and the Cognito JWT authorizer. Those are configuration that changes rarely and that
the working application exercises on every use — a worse trade than a permanent auth-surface change.

Everything writes under a **dedicated test user**, so no fixture can touch the real profile or
entries, and each test cleans up its own partition.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

STACK_NAME = os.environ.get("CAREERVAULT_STACK", "careervault-dev")
EXPECTED_ACCOUNT = "768396678224"

FUNCTIONS = {
    "career_crud": "careervault-career-crud-dev",
    "settings": "careervault-settings-dev",
    "checkin": "careervault-checkin-dev",
}


@pytest.fixture(scope="session")
def aws_session():
    """A boto3 session pinned to the CareerVault account, or a skip explaining why not.

    The account assertion is not ceremony: this AWS SSO login also reaches a *second* project in a
    different account under the same Organization, so an inherited default profile is how these
    tests would quietly run against the wrong data.
    """
    boto3 = pytest.importorskip("boto3")
    from botocore.exceptions import BotoCoreError, ClientError

    os.environ.setdefault("AWS_PROFILE", "careervault-dev")
    # Cleared so a leftover DynamoDB Local endpoint from the `local` tier cannot redirect the real
    # clients built here.
    os.environ.pop("DDB_ENDPOINT_URL", None)

    session = boto3.Session()
    try:
        account = session.client("sts").get_caller_identity()["Account"]
    except (BotoCoreError, ClientError) as exc:
        pytest.skip(f"no usable AWS credentials ({type(exc).__name__}) — run `aws sso login`")

    if account != EXPECTED_ACCOUNT:
        pytest.skip(f"wrong AWS account {account}, expected {EXPECTED_ACCOUNT} — check AWS_PROFILE")

    return session


@pytest.fixture(scope="session")
def lambda_client(aws_session):
    return aws_session.client("lambda")


@pytest.fixture(scope="session")
def live_table(aws_session):
    """The *deployed* dev table. Only ever touched under the test user's partition."""
    return aws_session.resource("dynamodb").Table("CareerVaultTable-dev")


@pytest.fixture
def cloud_user_id() -> str:
    """A throwaway user id, unique per test, so nothing can collide with the real profile."""
    return f"int-test-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def cleanup_user(live_table, cloud_user_id):
    """Delete everything written under the test user, whatever the test did or how it failed."""
    yield cloud_user_id

    key = {"PK": f"USER#{cloud_user_id}"}
    from boto3.dynamodb.conditions import Key

    items = live_table.query(KeyConditionExpression=Key("PK").eq(key["PK"])).get("Items", [])
    with live_table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})


def invoke(lambda_client, function: str, event: dict) -> dict:
    """Invoke a deployed Lambda synchronously and return its parsed proxy response.

    A function error (an unhandled exception in the handler) is surfaced as a test failure carrying
    the remote traceback, rather than as a confusing assertion on a payload that is really an error
    envelope.
    """
    response = lambda_client.invoke(
        FunctionName=FUNCTIONS.get(function, function),
        InvocationType="RequestResponse",
        Payload=json.dumps(event).encode(),
    )
    payload = json.loads(response["Payload"].read() or b"{}")

    if response.get("FunctionError"):
        pytest.fail(f"{function} raised {response['FunctionError']}: {payload}")

    return payload


def body_of(proxy_response: dict) -> dict:
    return json.loads(proxy_response.get("body") or "{}")


def api_event(
    *,
    method: str,
    user_id: str,
    body: dict | None = None,
    path_params: dict | None = None,
    email: str = "int-test@example.com",
) -> dict:
    """A REST API Gateway proxy event with Cognito authorizer claims already resolved.

    This is the shape API Gateway hands the Lambda *after* the JWT authorizer has run, which is
    precisely the boundary being stubbed: everything downstream of it is real.
    """
    return {
        "httpMethod": method,
        "pathParameters": path_params,
        "requestContext": {
            "requestId": f"int-{uuid.uuid4().hex[:8]}",
            "authorizer": {"claims": {"sub": user_id, "email": email}},
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }
