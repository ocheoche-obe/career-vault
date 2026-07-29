"""Real Converse round-trips, Haiku only (~$0.01 per run). Opt in with `--bedrock`.

This tier exists because of one specific class of bug, and slice 8 supplied the canonical example.
A Converse response omitted `sign_off` — a field the tool schema marked `required` — validation
rejected the whole email, and a perfectly good personalized send silently degraded to the static
fallback. No mock would have produced that response, because the mock is written *from* the schema.
A mock encodes the author's belief about the model; this class of bug lives exactly in the gap
between that belief and the model.

So these tests deliberately assert *shape and usability*, not content. A model is not deterministic
even at temperature 0 (see the `bedrock-converse-temp0-nondeterministic` note), so any assertion on
exact wording would be a flake generator. What is worth pinning is that the response parses, that
validation accepts it, and that the flow does not fall through to a lower tier.
"""

from __future__ import annotations

import json
import os
import re

import pytest

from _helpers import api_event, body_of, invoke

pytestmark = pytest.mark.bedrock


@pytest.fixture(scope="module")
def composer(aws_session):
    """The check-in composer, loaded in-process so it runs against real Bedrock.

    Depends on `aws_session` for two things it cannot do for itself. First, the **account
    assertion**: this fixture bills real Converse calls, and `os.environ.setdefault("AWS_PROFILE",
    ...)` — which is what it used to do — is a no-op when AWS_PROFILE is already set to the *other*
    project's profile sharing this SSO login, so the calls would land on the wrong account silently.
    Second, the **skip**: `compose()` never raises (it catches everything and returns the static
    tier), so with absent or expired credentials these tests would fail on
    `assert 'static' == 'personalized'` rather than skipping — contradicting this suite's contract
    that anything unavailable skips with a reason.
    """
    from helpers import load_sibling

    return load_sibling("int_checkin_composer", "checkin", "composer")


class TestCheckinComposition:
    """ADR-021 — the tier that degrades invisibly when the model surprises the schema."""

    PROFILE = {"PK": "USER#int-test", "email": "int-test@example.com", "name": "Ada Lovelace"}
    ENTRIES = [
        {
            "entry_type": "CERT",
            "title": "AWS Solutions Architect Associate",
            "content": "Passed SAA-C03.",
            "issued_date": "2026-07-01",
        },
        {
            "entry_type": "PROJECT",
            "title": "Migrated billing to event-driven ingest",
            "content": "Cut month-end close from 6 hours to 20 minutes.",
        },
    ]

    def test_a_personalized_email_survives_validation(self, composer):
        email, tier = composer.compose(self.PROFILE, self.ENTRIES)

        # The assertion that matters: the real model's output reached the personalized tier rather
        # than being rejected into a fallback. That downgrade is invisible in production — the email
        # still arrives — which is why it needs a test rather than a metric alone.
        assert tier == "personalized"
        assert email.subject.strip()
        assert email.prompts, "a personalized check-in with no prompts is not doing its job"

    def test_optional_polish_fields_never_block_a_usable_email(self, composer):
        """The slice-8 split: validate what makes output useful, default what makes it polished."""
        email, _ = composer.compose(self.PROFILE, self.ENTRIES)

        # greeting/sign_off are defaulted rather than required precisely so their absence cannot
        # cost a good email. They must always be present after validation, whatever the model sent.
        assert isinstance(email.greeting, str) and email.greeting.strip()
        assert isinstance(email.sign_off, str) and email.sign_off.strip()

    def test_a_user_with_no_recent_entries_gets_the_generic_tier(self, composer):
        email, tier = composer.compose(self.PROFILE, [])

        assert tier == "generic"
        assert email.subject.strip()


class TestChatIngestion:
    """Section 3.1 — the routing turn, against the deployed chat Lambda and a real Haiku call."""

    def test_a_natural_language_milestone_parses_into_a_candidate(self, lambda_client, cleanup_user):
        response = invoke(
            lambda_client,
            "careervault-chat-dev",
            api_event(
                method="POST",
                user_id=cleanup_user,
                body={
                    "message": "I passed the AWS Solutions Architect Associate exam on 14 March 2026.",
                    "client_message_id": "01JQ0000000000000000000000",
                },
            ),
        )

        assert response["statusCode"] == 200
        candidate = body_of(response).get("candidate") or body_of(response).get("entry")
        assert candidate, f"no candidate in {json.dumps(body_of(response))[:400]}"
        # Type and title are what the confirm card renders; exact wording is the model's business.
        assert candidate["entry_type"] == "CERT"
        assert "solutions architect" in candidate["title"].lower()


class TestGroundedQa:
    """ADR-038 — retrieval happens in Python; the model only narrates."""

    def test_a_question_is_answered_from_the_users_own_corpus(self, lambda_client, cleanup_user):
        # Seed one entry through the real CRUD path so it is embedded the same way production is.
        invoke(
            lambda_client,
            "career_crud",
            api_event(
                method="POST",
                user_id=cleanup_user,
                body={
                    "entry_type": "CERT",
                    "title": "AWS Solutions Architect Associate",
                    "content": "Passed the SAA-C03 exam.",
                    "issuer": "Amazon Web Services",
                    "issued_date": "2026-03-14",
                },
            ),
        )

        response = invoke(
            lambda_client,
            "careervault-chat-dev",
            api_event(
                method="POST",
                user_id=cleanup_user,
                body={
                    "message": "How many certifications do I have?",
                    "client_message_id": "01JQ1111111111111111111111",
                },
            ),
        )

        assert response["statusCode"] == 200
        answer = body_of(response).get("answer") or ""
        assert answer, f"no answer in {json.dumps(body_of(response))[:400]}"
        # Word-boundary match, not a substring. `"one" in answer` is satisfied by "someone",
        # "none" and "done", and `"1" in answer` by any date containing a 1 — so the obvious
        # assertion passes even if a census regression made the model answer "8 certifications".
        assert re.search(r"\b(1|one)\b", answer, re.IGNORECASE), answer
