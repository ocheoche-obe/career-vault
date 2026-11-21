"""Integration-test fixtures and cost tiers (ADR-042).

Tiers, by what a run costs:

===========  ====================  ==========================================================
Tier         Marker                What it needs
===========  ====================  ==========================================================
local        ``local``             DynamoDB Local on ``DDB_ENDPOINT_URL`` — $0, no AWS at all
cloud        ``cloud``             Deployed dev stack + AWS creds — ~$0 (no model calls)
bedrock      ``bedrock``           Real Converse round-trips, Haiku only — ~$0.01
expensive    ``expensive``         A full Sonnet résumé run — ~$0.11 measured
===========  ====================  ==========================================================

``scripts/run-integration.sh`` runs ``local`` + ``cloud`` by default and deselects the two paid
tiers. The default has to be free, because the suite that costs nothing is the one that actually
gets run — a uniform suite is a suite people avoid rather than use.

Anything unavailable **skips with a reason** rather than failing: a developer without Docker
running should still get a useful signal from the rest.
"""

from __future__ import annotations

import os
import socket
import uuid
from urllib.parse import urlparse

import pytest

from _timing import LOG as LATENCY_LOG
from _timing import format_table

DDB_LOCAL_ENDPOINT = os.environ.get("DDB_ENDPOINT_URL", "http://localhost:8000")
LOCAL_TABLE_NAME = "CareerVaultTable-inttest"
DEPLOYED_TABLE_NAME = "CareerVaultTable-dev"


def pytest_configure(config: pytest.Config) -> None:
    for marker, description in [
        ("local", "needs DynamoDB Local; costs nothing"),
        ("cloud", "needs the deployed dev stack; no model calls, ~$0"),
        ("bedrock", "makes real Haiku Converse calls; ~$0.01 per run"),
        ("expensive", "runs the Sonnet résumé agent; ~$0.11 per run"),
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

    # Set before importing ddb_helpers so get_table() picks up the endpoint.
    #
    # The placeholder credentials below are *not* a safety net, despite looking like one: setdefault
    # is a no-op when the variable already exists, and run-integration.sh exports AWS_PROFILE, which
    # boto3 resolves to real SSO credentials regardless. The only thing keeping this tier off the
    # real account is the explicit endpoint_url below. They are set purely so boto3 can construct a
    # client at all when no credentials are configured.
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


# ---------------------------------------------------------------------------
# Deployed-stack fixtures — shared by the `cloud` and `bedrock` tiers.
#
# Lambdas are invoked *directly*, with a synthetic API Gateway event carrying resolved Cognito
# claims, rather than through API Gateway with a real JWT. The app client is deliberately PKCE-only
# (ExplicitAuthFlows is ALLOW_REFRESH_TOKEN_AUTH alone, ADR-025), so there is no unattended way to
# mint a token — and adding one would widen the auth surface permanently to buy a test convenience.
# ---------------------------------------------------------------------------

EXPECTED_ACCOUNT = "768396678224"


@pytest.fixture(scope="session")
def aws_session():
    """A boto3 session pinned to the CareerVault account, or a skip explaining why not.

    The account assertion is not ceremony: this SSO login also reaches a *second* project in a
    different account under the same Organization, so an inherited default profile is exactly how
    these tests would quietly run against the wrong data.
    """
    boto3 = pytest.importorskip("boto3")
    from botocore.exceptions import BotoCoreError, ClientError

    os.environ.setdefault("AWS_PROFILE", "careervault-dev")

    # Undo the `local` tier's rebinding — properly. Popping DDB_ENDPOINT_URL alone is not enough and
    # the previous comment here claimed a guard that did not exist: `get_table()` caches the Table
    # object at module level for warm-container reuse, and `CAREERVAULT_TABLE_NAME` is still pointing
    # at `CareerVaultTable-inttest`. Without all three lines, any in-process `ddb_helpers` call from
    # a "deployed" test reads DynamoDB Local, or a table that does not exist in us-east-1. It is
    # currently masked only by alphabetical collection order (bedrock < cloud < expensive < local),
    # which `-k` or a reordered path argument silently defeats.
    os.environ.pop("DDB_ENDPOINT_URL", None)
    os.environ["CAREERVAULT_TABLE_NAME"] = DEPLOYED_TABLE_NAME

    from careervault import ddb_helpers

    ddb_helpers._table = None

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
    """The *deployed* dev table. Only ever touched under a throwaway test user's partition."""
    return aws_session.resource("dynamodb").Table(DEPLOYED_TABLE_NAME)


@pytest.fixture
def cloud_user_id() -> str:
    """A throwaway user id, unique per test, so nothing can collide with the real profile."""
    return f"int-test-{uuid.uuid4().hex[:12]}"


def _purge_user(live_table, user_id: str) -> None:
    """Delete every item under one user's partition, following pagination to completion.

    Pagination is not optional. A Query returns at most 1 MB, and entries carry a ~1024-float Titan
    embedding each (~20 KB/item, ADR-016) while a RESUMERUN trace stores the agent's whole action
    history — so one test user's partition can exceed a page. Anything left behind is not merely
    untidy: an orphaned PROFILE becomes a permanent recipient for the daily check-in scan.
    """
    from boto3.dynamodb.conditions import Key

    start_key = None
    while True:
        kwargs = {"KeyConditionExpression": Key("PK").eq(f"USER#{user_id}")}
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        response = live_table.query(**kwargs)

        with live_table.batch_writer() as batch:
            for item in response.get("Items", []):
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})

        start_key = response.get("LastEvaluatedKey")
        if not start_key:
            return


@pytest.fixture
def cleanup_user(live_table, cloud_user_id):
    """Delete everything written under the test user, whatever the test did or how it failed."""
    yield cloud_user_id
    _purge_user(live_table, cloud_user_id)


@pytest.fixture
def scheduler_safe_user(live_table, cloud_user_id):
    """A test user that can never be picked up by the daily check-in run.

    Any test that writes a PROFILE needs this. `settings/handler.py` stamps the caller's claim email
    onto the profile, and `is_due` treats *any* profile with an email, not paused, and with no
    `next_checkin_at` as due right now — which is exactly the shape a bare `PUT /settings` creates.
    Teardown normally removes it, but a Ctrl-C, a crashed session, or a hard kill leaves an orphan
    that the 23:00 UTC run then bills a Bedrock compose call for, every day, and tries to deliver to
    an unverified address.

    Seeding `next_checkin_at` far in the future *before* the test writes anything makes that
    impossible rather than unlikely — the item is never due at any point in its life, so no ordering
    of failures can produce an orphan recipient. `ProfileUpdate` never writes this field, so a
    subsequent `PUT /settings` leaves it intact.
    """
    live_table.put_item(
        Item={
            "PK": f"USER#{cloud_user_id}",
            "SK": "PROFILE",
            "next_checkin_at": "2099-01-01T00:00:00Z",
        }
    )
    yield cloud_user_id
    _purge_user(live_table, cloud_user_id)


# ---------------------------------------------------------------------------
# Latency recording (ADR-047).
# ---------------------------------------------------------------------------


@pytest.fixture
def latency():
    """The session-wide latency log.

    Session-scoped state in a function-scoped fixture on purpose: the terminal-summary hook runs
    after every fixture has torn down, so the collector has to outlive them.
    """
    return LATENCY_LOG


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Print the recorded latency table once, after the run.

    Printed unconditionally — including when nothing was recorded, which is itself the signal that
    the tiers carrying the measurements were deselected. ADR-047's ⚠ is that a recorded number only
    helps if somebody reads it; a table that silently omits itself when empty is how "we measure
    latency" quietly becomes false.
    """
    terminalreporter.write_sep("=", "latency (ADR-047)")
    for line in format_table(LATENCY_LOG.samples):
        terminalreporter.write_line(line)

    breached = LATENCY_LOG.breaches()
    if breached:
        terminalreporter.write_line("")
        terminalreporter.write_line("  REGRESSION CEILING BREACHED:")
        for sample in breached:
            terminalreporter.write_line(
                f"    {sample.name} ({sample.kind}) {sample.ms:,.0f} ms "
                f"> ceiling {sample.ceiling_ms:,} ms"
            )
