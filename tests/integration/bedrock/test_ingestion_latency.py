"""NFR-2.1 — conversational ingestion latency, with the model call included (ADR-047, B-023).

This lives in the paid tier for one reason: NFR-2.1 says *end-to-end*, and end-to-end contains a
real Haiku parse turn. Timing this path with Bedrock stubbed would measure everything except the
slowest step and report a comfortable number — evidence-shaped, and wrong. ~$0.02 per run.

NFR-2.1 reads "user submits text → confirmation shown", which is two distinct operations the user
experiences as one flow, so both are recorded:

``POST /chat``
    The parse turn. Ends when the confirm card can be drawn — this is the literal wording of the
    requirement, and the number a user waits on before anything appears.
``POST /entries``
    The confirm write. Runs a synchronous Titan embed in the write path (ADR-024), so it is not
    free either, and the flow is not actually finished until it returns.
"""

from __future__ import annotations

import json
from itertools import count

import pytest

from _helpers import api_event, body_of, invoke_timed

pytestmark = pytest.mark.bedrock

#: Repeats are low here because every one is a billed model call. Two is enough for a median that
#: is not a single sample, and cheap enough that nobody avoids running the tier (ADR-042).
REPEATS = 2

#: Generous against NFR-2.1's 5000 ms, per ADR-047 — this catches drift, not compliance.
INGESTION_CEILING_MS = 20_000


_CERT_TITLES = [
    "AWS Solutions Architect Associate",
    "Certified Kubernetes Administrator",
    "Google Professional Cloud Architect",
    "HashiCorp Terraform Associate",
    "Azure Solutions Architect Expert",
]
_CERT_ISSUERS = ["Amazon Web Services", "CNCF", "Google Cloud", "HashiCorp", "Microsoft"]
_CERT_CONTENT = [
    "Passed the SAA-C03 exam covering resilient architectures and cost optimisation.",
    "Passed the CKA performance exam covering cluster administration and networking.",
    "Passed the PCA exam covering solution design and migration planning.",
    "Passed the Terraform Associate exam covering state, modules and providers.",
    "Passed the AZ-305 exam covering identity, governance and data platform design.",
]


class TestIngestionLatency:
    MESSAGE = "I passed the AWS Solutions Architect Associate exam on 14 March 2026."

    def test_the_parse_turn_is_measured_against_nfr_2_1(self, lambda_client, cleanup_user, latency):
        results = latency.measure(
            lambda: invoke_timed(
                lambda_client,
                "careervault-chat-dev",
                api_event(
                    method="POST",
                    user_id=cleanup_user,
                    body={
                        "message": self.MESSAGE,
                        # A fresh id per call: turn idempotency (Section 3.1.4) would otherwise
                        # short-circuit the repeats into cache hits, and the measurement would be of
                        # a dedup lookup rather than of parsing.
                        "client_message_id": _ulid(),
                    },
                ),
            ),
            name="POST /chat — parse turn (confirm card shown)",
            tier="bedrock",
            nfr="NFR-2.1",
            nfr_ms=5_000,
            ceiling_ms=INGESTION_CEILING_MS,
            repeats=REPEATS,
            report_of=lambda result: result[1],
        )

        for response, _report in results:
            assert response["statusCode"] == 200
            body = body_of(response)
            candidate = body.get("candidate") or body.get("entry")
            # Shape, not wording — the model is not deterministic at temperature 0. Without this the
            # number could be timing a clarification round-trip, which is a different, faster path.
            assert candidate, f"no candidate in {json.dumps(body)[:300]}"
            assert candidate["entry_type"] == "CERT"

    def test_the_confirm_write_is_measured_separately(self, lambda_client, cleanup_user, latency):
        """The other half of the flow: the write that makes the entry real.

        Recorded apart from the parse turn rather than added to it. They are separate user actions
        with separate waits, and a single combined figure would hide which one to fix.
        """
        # Each repeat writes a *materially different* entry. The first version of this test posted
        # identical text every time, so ADR-033's semantic dup check answered 409 before the write —
        # and the recorded "confirm write" median described a duplicate rejection, not an ingestion.
        # It was published to the scorecard before the slice-5 code review caught it.
        counter = count()

        def _distinct_entry() -> dict:
            index = next(counter)
            return {
                "entry_type": "CERT",
                "title": f"{_CERT_TITLES[index % len(_CERT_TITLES)]}",
                "content": _CERT_CONTENT[index % len(_CERT_CONTENT)],
                "issuer": _CERT_ISSUERS[index % len(_CERT_ISSUERS)],
                "issued_date": f"202{4 + (index % 3)}-0{1 + (index % 8)}-1{index % 9}",
            }

        results = latency.measure(
            lambda: invoke_timed(
                lambda_client,
                "career_crud",
                api_event(method="POST", user_id=cleanup_user, body=_distinct_entry()),
            ),
            name="POST /entries — confirm write (Titan embed inline)",
            tier="bedrock",
            nfr="NFR-2.1",
            nfr_ms=5_000,
            ceiling_ms=INGESTION_CEILING_MS,
            repeats=REPEATS,
            report_of=lambda result: result[1],
        )

        # Every call must actually have written. A 409 here means the entries were not distinct
        # enough and the number above is timing ADR-033's dup rejection — which returns *before* the
        # DynamoDB write and is therefore not the operation NFR-2.1 is about.
        statuses = [response["statusCode"] for response, _report in results]
        assert all(status == 201 for status in statuses), (
            f"every confirm must create, got {statuses} — a 409 means this measured a duplicate "
            "rejection rather than a write"
        )


def _ulid() -> str:
    from careervault.ddb_helpers import new_ulid

    return new_ulid()
