"""Integration-test fixtures and cost tiers (ADR-042).

Tiers, by what a run costs:

===========  ====================  ==========================================================
Tier         Marker                What it needs
===========  ====================  ==========================================================
local        ``local``             DynamoDB Local on ``DDB_ENDPOINT_URL`` — $0, no AWS at all
cloud        ``cloud``             Deployed dev stack + AWS creds — ~$0 (no model calls)
bedrock      ``bedrock``           Real Converse round-trips, Haiku only — ~$0.01
expensive    ``expensive``         A full Sonnet résumé run — ~$0.31
===========  ====================  ==========================================================

``scripts/run-integration.sh`` runs ``local`` + ``cloud`` by default and deselects the two paid
tiers. The default has to be free, because the suite that costs nothing is the one that actually
gets run — a uniform suite at ~$0.35 a go is ~14 runs to the monthly ceiling, which is a suite
people avoid rather than use.

Anything unavailable **skips with a reason** rather than failing: a developer without Docker
running should still get a useful signal from the rest.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest

DDB_LOCAL_ENDPOINT = os.environ.get("DDB_ENDPOINT_URL", "http://localhost:8000")
LOCAL_TABLE_NAME = "CareerVaultTable-inttest"


def pytest_configure(config: pytest.Config) -> None:
    for marker, description in [
        ("local", "needs DynamoDB Local; costs nothing"),
        ("cloud", "needs the deployed dev stack; no model calls, ~$0"),
        ("bedrock", "makes real Haiku Converse calls; ~$0.01 per run"),
        ("expensive", "runs the Sonnet résumé agent; ~$0.31 per run"),
    ]:
        config.addinivalue_line("markers", f"{marker}: {description}")


def _reachable(url: str, timeout: float = 1.0) -> bool:
    parsed = urlparse(url)
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 80), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def ddb_local_table():
    """A real DynamoDB table on DynamoDB Local, matching the deployed key schema.

    The point of this tier is the behavior a mock cannot have: conditional writes that actually
    fail, document paths that actually reject, reserved words that actually collide. Section 4.7
    of the architecture doc calls for it by name after the SK-prefix bug slipped past tests that
    only asserted on strings.
    """
    if not _reachable(DDB_LOCAL_ENDPOINT):
        pytest.skip(
            f"DynamoDB Local not reachable at {DDB_LOCAL_ENDPOINT} — "
            "start it with `docker run -d -p 8000:8000 amazon/dynamodb-local`"
        )

    # Set before importing ddb_helpers so get_table() picks up the endpoint, and blank out any real
    # credentials so a misconfigured endpoint cannot reach the actual account.
    os.environ["DDB_ENDPOINT_URL"] = DDB_LOCAL_ENDPOINT
    os.environ["CAREERVAULT_TABLE_NAME"] = LOCAL_TABLE_NAME
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

    import boto3

    from careervault import ddb_helpers

    # get_table() caches the Table at module level for warm-container reuse; a unit test earlier in
    # the same session may have already built one against the real endpoint.
    ddb_helpers._table = None

    resource = boto3.resource("dynamodb", endpoint_url=DDB_LOCAL_ENDPOINT)
    existing = {t.name for t in resource.tables.all()}
    if LOCAL_TABLE_NAME not in existing:
        resource.create_table(
            TableName=LOCAL_TABLE_NAME,
            # Mirrors infrastructure/template.yaml: PK hash, SK range, both strings (ADR-005).
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        ).wait_until_exists()

    yield resource.Table(LOCAL_TABLE_NAME)


@pytest.fixture
def table(ddb_local_table):
    """The local table, emptied before each test so ordering cannot matter."""
    scanned = ddb_local_table.scan(ProjectionExpression="PK,SK").get("Items", [])
    with ddb_local_table.batch_writer() as batch:
        for item in scanned:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
    return ddb_local_table


@pytest.fixture
def user_id() -> str:
    return "int-test-user"
