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

import pytest

from _helpers import api_event, body_of, invoke_timed

pytestmark = pytest.mark.bedrock

#: Repeats are low here because every one is a billed model call. Two is enough for a median that
#: is not a single sample, and cheap enough that nobody avoids running the tier (ADR-042).
REPEATS = 2

#: Generous against NFR-2.1's 5000 ms, per ADR-047 — this catches drift, not compliance.
INGESTION_CEILING_MS = 20_000


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
        entry = {
            "entry_type": "CERT",
            "title": "AWS Solutions Architect Associate",
            "content": "Passed the SAA-C03 exam.",
            "issuer": "Amazon Web Services",
            "issued_date": "2026-03-14",
        }

        results = latency.measure(
            lambda: invoke_timed(
                lambda_client, "career_crud", api_event(method="POST", user_id=cleanup_user, body=entry)
            ),
            name="POST /entries — confirm write (Titan embed inline)",
            tier="bedrock",
            nfr="NFR-2.1",
            nfr_ms=5_000,
            ceiling_ms=INGESTION_CEILING_MS,
            repeats=REPEATS,
            report_of=lambda result: result[1],
        )

        # The first write creates; the repeats are near-identical text, so ADR-033's semantic dup
        # check is expected to answer 409. Both are real, timed write paths that ran a Titan embed —
        # which is what NFR-2.1 is about — so both count, but the statuses must be the expected ones
        # rather than an error that would make this a measurement of a fast failure.
        statuses = [response["statusCode"] for response, _report in results]
        assert statuses[0] == 201, f"first write should create, got {statuses}"
        assert all(status in (201, 409) for status in statuses), statuses


def _ulid() -> str:
    from careervault.ddb_helpers import new_ulid

    return new_ulid()
