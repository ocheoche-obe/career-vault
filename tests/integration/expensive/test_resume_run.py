"""A full tailored-résumé run against the deployed agent (~$0.31). Opt in with `--expensive`.

The single most expensive thing CareerVault does, and therefore the one deliberately excluded from
every default run: at ~$0.31 a go, ~16 runs is the entire $5 monthly ceiling. That is a conscious
purchase of budget with coverage, and it leaves the most complex Lambda the least
integration-tested — stated here rather than discovered later.

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


def test_a_tailored_resume_run_completes_and_produces_a_pdf(lambda_client, cleanup_user):
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

    # Reported rather than asserted. Requirements §7.4's original "within 30 seconds" is why
    # generation is async at all (ADR-037), and duration varies with corpus size and whether the
    # critique returns REVISE — an upper bound here would be a flake, not a guarantee (B-020).
    print(
        f"\nrésumé run {run_id}: {elapsed:.0f}s, {polled.get('tokens')} tokens, "
        f"${polled.get('cost_usd')}, critique={polled.get('critique_verdict')}, "
        f"entries={polled.get('retrieved_count')}"
    )

    # Presigned URLs for both artifacts — the PDF is what the user downloads, the HTML is what the
    # in-app preview iframes (slice 6b).
    assert polled.get("pdf_url"), "a completed run must presign a PDF"
    assert polled.get("html_url"), "a completed run must presign an HTML preview"

    _assert_is_a_real_pdf(polled["pdf_url"])


def _assert_is_a_real_pdf(url: str) -> None:
    """Fetch the presigned URL and check the magic bytes.

    Worth the extra request: WeasyPrint runs from a Docker-built native layer, and the failure mode
    when that layer is wrong is a zero-byte or HTML-shaped object at a URL that presigns perfectly
    well. "A URL came back" is not the same claim as "a PDF exists".
    """
    import ssl
    import urllib.request

    from botocore.httpsession import DEFAULT_CA_BUNDLE

    # botocore's bundled CA rather than the interpreter's default trust store: a python.org build on
    # macOS has no system certificates wired up, so plain urlopen fails CERTIFICATE_VERIFY_FAILED on
    # a URL that is perfectly valid. That failure looks like a broken artifact and is not one.
    context = ssl.create_default_context(cafile=DEFAULT_CA_BUNDLE)
    with urllib.request.urlopen(url, timeout=30, context=context) as response:
        head = response.read(5)

    assert head == b"%PDF-", f"presigned object is not a PDF (starts {head!r})"
