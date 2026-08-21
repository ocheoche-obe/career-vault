"""A full tailored-résumé run against the deployed agent (~$0.11 measured). Opt in with `--expensive`.

The single most expensive thing CareerVault does, and therefore the one deliberately excluded from
every default run. Measured **$0.113** here — cheaper than the $0.31–0.35 a real corpus costs, but
only because this test seeds a 2-entry fixture; cost scales with corpus size (B-004/B-020), so do
not read this number as the agent's price. It is still a conscious purchase of budget with coverage,
and it leaves the most complex Lambda the least integration-tested — stated rather than discovered.

What earns the money is the part no cheaper tier can reach: that the six-phase bounded loop
terminates, that the deterministic finalize produces a real PDF, and that the ADR-037 async contract
(202 + poll) holds end to end. Assertions stay structural — a model's prose is not a fixture.
"""

from __future__ import annotations

import time

import pytest

from _helpers import api_event, body_of, invoke

pytestmark = pytest.mark.expensive

JOB_DESCRIPTION = """
Senior Cloud Engineer. You will design and operate serverless workloads on AWS: Lambda, DynamoDB,
API Gateway, and EventBridge. Strong Python required. Experience with infrastructure as code and
cost optimisation is highly valued.
"""

SEED_ENTRIES = [
    {
        "entry_type": "CERT",
        "title": "AWS Solutions Architect Associate",
        "content": "Passed the SAA-C03 exam.",
        "issuer": "Amazon Web Services",
        "issued_date": "2026-03-14",
    },
    {
        "entry_type": "JOB",
        "title": "Senior Software Engineer",
        "content": (
            "Built and operated serverless data pipelines on AWS Lambda and DynamoDB. Cut monthly "
            "infrastructure spend by 40% by right-sizing and moving batch work to ARM64."
        ),
        "employer": "Acme Corp",
        "start_date": "2022-01-10",
    },
]

POLL_TIMEOUT_SECONDS = 420  # measured ~176s in slice 6b; generous headroom, not an expectation
POLL_INTERVAL_SECONDS = 5


@pytest.fixture
def cleanup_resume_artifacts(aws_session, cleanup_user):
    """Delete this run's S3 artifacts afterwards — they no longer expire on their own (ADR-046).

    Before ADR-046 the `resumes/` lifecycle rule swept anything this test generated within 30 days,
    so nothing had to be cleaned up. Removing that rule to make *user* résumés durable also made
    *test* résumés durable, and an opt-in tier that leaks ~100 KB per run into a bucket nobody
    reviews is exactly the kind of accumulation that is invisible until it isn't. DynamoDB is
    already handled — `_purge_user` deletes the whole partition, RESUME# records included.
    """
    yield cleanup_user

    account = aws_session.client("sts").get_caller_identity()["Account"]
    s3 = aws_session.client("s3")
    listed = s3.list_objects_v2(
        Bucket=f"careervault-data-dev-{account}", Prefix=f"resumes/{cleanup_user}/"
    )
    keys = [{"Key": obj["Key"]} for obj in listed.get("Contents", [])]
    if keys:
        s3.delete_objects(Bucket=f"careervault-data-dev-{account}", Delete={"Objects": keys})


def test_a_tailored_resume_run_completes_and_produces_a_pdf(
    lambda_client, cleanup_user, aws_session, cleanup_resume_artifacts, latency
):
    for entry in SEED_ENTRIES:
        created = invoke(
            lambda_client, "career_crud", api_event(method="POST", user_id=cleanup_user, body=entry)
        )
        assert created["statusCode"] == 201, body_of(created)

    started = invoke(
        lambda_client,
        "resume_agent",
        # The field is `target`, not `job_description` — it accepts a full JD or a bare role name.
        api_event(method="POST", user_id=cleanup_user, body={"target": JOB_DESCRIPTION}),
    )
    # ADR-037: the request returns immediately and a self-invoked worker does the work — the run
    # takes ~176s, far past API Gateway's 29s integration timeout.
    assert started["statusCode"] == 202, body_of(started)
    run_id = body_of(started)["run_id"]

    # The run's own vocabulary is pending -> completed | failed. Naming the terminal set here rather
    # than inline: an unrecognised status silently polls to the deadline and then fails on a string
    # compare, which is a 7-minute way to learn about a typo.
    terminal = {"completed", "failed"}

    started_at = time.time()
    deadline = started_at + POLL_TIMEOUT_SECONDS
    status, polled = None, {}
    while time.time() < deadline:
        polled = body_of(
            invoke(
                lambda_client,
                "resume_agent",
                api_event(method="GET", user_id=cleanup_user, path_params={"run_id": run_id}),
            )
        )
        status = polled.get("status")
        if status in terminal:
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    elapsed = time.time() - started_at
    assert status == "completed", f"run {run_id} ended as {status!r} after {elapsed:.0f}s: {polled}"

    # Recorded into the ADR-047 table so this number survives the run rather than living in
    # scrollback — a résumé run costs ~$0.11, which is far too much to pay for a measurement nobody
    # can compare against later. NFR-2.2's 4-minute bound is a generous alerting ceiling, not a
    # target (requirements v0.6), so the verdict column will read PASS while B-020 is wide open.
    latency.record(
        name=f"résumé run — {len(SEED_ENTRIES)}-entry corpus, critique={polled.get('critique_verdict')}",
        tier="expensive",
        kind="end-to-end",
        ms=elapsed * 1000,
        nfr="NFR-2.2",
        nfr_ms=240_000,
        ceiling_ms=POLL_TIMEOUT_SECONDS * 1000,
        # Tokens and cost ride along in the same row as the duration, because B-020 and B-004 are
        # one mechanism seen from two sides — a caching change that cut time but not tokens (or the
        # reverse) would mean something quite different from one that cut both.
        notes=(
            f"{polled.get('tokens')} tok · ${polled.get('cost_usd')}"
            f" · cache r/w {polled.get('cache_read_tokens', '—')}/{polled.get('cache_write_tokens', '—')}"
        ),
    )

    # Reported rather than asserted. Requirements §7.4's original "within 30 seconds" is why
    # generation is async at all (ADR-037), and duration varies with corpus size and whether the
    # critique returns REVISE — an upper bound here would be a flake, not a guarantee (B-020).
    print(
        f"\nrésumé run {run_id}: {elapsed:.0f}s, {polled.get('tokens')} tokens, "
        f"${polled.get('cost_usd')}, critique={polled.get('critique_verdict')}, "
        f"entries={polled.get('retrieved_count')}"
    )

    # --- ADR-048: caching must be proven engaged, not merely requested ---------------------------
    # This is the assertion the ADR exists for. A `cachePoint` below the model's token minimum is a
    # silent no-op: Bedrock returns no error, no warning, and bills the full uncached prefix. A test
    # asserting the block was *sent* would pass in exactly that situation. Only a non-zero read back
    # from a real multi-iteration run proves the cache was populated and then used.
    cache_read = polled.get("cache_read_tokens")
    cache_write = polled.get("cache_write_tokens")
    assert cache_write, (
        f"no cache write on a {polled.get('retrieval_iterations', '?')}-iteration run — the prefix "
        f"never became cacheable (below the model minimum?). usage: {cache_read}/{cache_write}"
    )
    assert cache_read, (
        f"cache written ({cache_write} tokens) but never read back. The breakpoint moved in a way "
        "that invalidated the prefix, or the run ended before a second iteration."
    )

    # Presigned URLs for both artifacts — the PDF is what the user downloads, the HTML is what the
    # in-app preview iframes (slice 6b).
    assert polled.get("pdf_url"), "a completed run must presign a PDF"
    assert polled.get("html_url"), "a completed run must presign an HTML preview"

    _assert_is_a_real_pdf(aws_session, polled["pdf_url"])

    # --- ADR-046 / B-022 / B-007: what the poll now carries -------------------------------------
    # The structured résumé is what makes plain-text bullets copyable (B-022); elapsed time is what
    # used to vanish at the moment you'd compare runs (B-007). Structural assertions only.
    assert polled.get("document"), "a completed run must return the structured résumé (B-022)"
    assert polled["document"].get("summary"), "the document must carry a summary to copy"
    assert polled.get("elapsed_seconds"), "a completed run must report its elapsed time (B-007)"

    # --- ADR-046: the durable record, proven by the list endpoint ---------------------------------
    # This is the assertion the unit tests cannot make: that a *real* worker, finishing a *real*
    # run, wrote the second item — and that the projected query reads it back.
    history = body_of(
        invoke(lambda_client, "resume_agent", api_event(method="GET", user_id=cleanup_user, path_params=None))
    )
    rows = {row["run_id"]: row for row in history["resumes"]}
    assert run_id in rows, f"the completed run is missing from history: {history}"

    row = rows[run_id]
    # `_target_title` takes the first non-empty *line*, so a pasted JD yields its opening sentence
    # rather than a bare role. That is the honest behaviour for a paste; the designed input is a
    # short target ("Senior AI Solutions Manager"), where the same rule gives exactly the title.
    assert row["target_title"].startswith("Senior Cloud Engineer.")
    assert len(row["target_title"]) <= 120
    assert row["entry_count"] >= 1
    assert row["status"] == "completed"
    # The list is a projection: the bulky fields must not ride along (B-013 declined in advance).
    assert "target_text" not in row and "document" not in row


def _assert_is_a_real_pdf(aws_session, url: str) -> None:
    """Read the first bytes of the generated PDF and check its magic number.

    Worth the extra request: WeasyPrint runs from a Docker-built native layer, and the failure mode
    when that layer is wrong is a zero-byte or HTML-shaped object at a URL that presigns perfectly
    well. "A URL came back" is not the same claim as "a PDF exists".

    Read through boto3 rather than `urllib`. The obvious version — `urllib.request.urlopen(url)` —
    fails `CERTIFICATE_VERIFY_FAILED` on a python.org macOS build, which has no system trust store
    wired up, and the workaround for *that* was an ssl context built from
    `botocore.httpsession.DEFAULT_CA_BUNDLE`: an undocumented private constant whose relocation
    would break the suite's most expensive test at import time. boto3 already has trust configured,
    a `Range` header fetches five bytes instead of the whole document, and "use boto3 for all AWS SDK
    calls" is the project convention anyway.
    """
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url)
    bucket = parsed.netloc.split(".s3.")[0]
    key = unquote(parsed.path.lstrip("/"))

    response = aws_session.client("s3").get_object(Bucket=bucket, Key=key, Range="bytes=0-4")
    head = response["Body"].read()

    assert head == b"%PDF-", f"generated object is not a PDF (starts {head!r})"
