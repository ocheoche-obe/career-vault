"""The deployed dev stack, exercised end to end below the authorizer (ADR-042 `cloud` tier).

Costs ~$0: no model is called anywhere in this file. What it proves that a unit test cannot is that
the *deployed artifact* works — the layer resolved, the environment variables are set, and above all
the IAM policy actually attached to each role permits what the code assumes. IAM is the thing that
is impossible to test locally and the thing most likely to be wrong after a template edit.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from _helpers import api_event, body_of, invoke

pytestmark = pytest.mark.cloud


class TestSettingsRoundTrip:
    def test_a_new_user_gets_an_empty_profile_rather_than_a_404(self, lambda_client, cleanup_user):
        response = invoke(lambda_client, "settings", api_event(method="GET", user_id=cleanup_user))

        assert response["statusCode"] == 200

    def test_identity_fields_written_by_put_come_back_on_get(self, lambda_client, cleanup_user):
        # B-008's fix, verified against the deployed function: PUT /settings is what puts a name on a
        # generated résumé, and the UpdateItem grant it needs sat unused from slice 1 until then.
        put = invoke(
            lambda_client,
            "settings",
            api_event(
                method="PUT",
                user_id=cleanup_user,
                body={"name": "Ada Lovelace", "location": "London, England"},
            ),
        )
        assert put["statusCode"] == 200

        got = body_of(invoke(lambda_client, "settings", api_event(method="GET", user_id=cleanup_user)))
        profile = got.get("profile", got)
        assert profile["name"] == "Ada Lovelace"
        assert profile["location"] == "London, England"

    def test_nested_settings_sub_fields_move_independently(self, lambda_client, cleanup_user):
        """ADR-040 through the deployed function, not just through the helper."""
        invoke(
            lambda_client,
            "settings",
            api_event(method="PUT", user_id=cleanup_user, body={"settings": {"checkin_cadence": "monthly"}}),
        )
        invoke(
            lambda_client,
            "settings",
            api_event(method="PUT", user_id=cleanup_user, body={"settings": {"checkin_paused": True}}),
        )

        got = body_of(invoke(lambda_client, "settings", api_event(method="GET", user_id=cleanup_user)))
        settings = (got.get("profile", got)).get("settings", {})
        assert settings.get("checkin_cadence") == "monthly"
        assert settings.get("checkin_paused") is True

    def test_the_cors_header_is_the_deployed_wildcard(self, lambda_client, cleanup_user):
        # The slice-1 bug B-008 surfaced: settings/handler.py hardcoded http://localhost:5173 instead
        # of reading CORS_ALLOW_ORIGIN, so GET /settings would have failed CORS from CloudFront and
        # nothing would have noticed until something called the route (ADR-034).
        response = invoke(lambda_client, "settings", api_event(method="GET", user_id=cleanup_user))
        headers = {k.lower(): v for k, v in (response.get("headers") or {}).items()}
        assert headers.get("access-control-allow-origin") == "*"


class TestEntryLifecycle:
    # Per-type schema, ADR-022: CERT requires `issued_date`, not the generic `event_date`. Getting
    # this wrong is precisely what a deployed round-trip catches and a hand-written fixture does not.
    ENTRY = {
        "entry_type": "CERT",
        "title": "AWS Solutions Architect Associate",
        "content": "Passed the SAA-C03 exam in an integration test.",
        "issuer": "Amazon Web Services",
        "issued_date": "2026-03-14",
    }

    def test_create_read_update_delete(self, lambda_client, cleanup_user):
        created = invoke(
            lambda_client, "career_crud", api_event(method="POST", user_id=cleanup_user, body=self.ENTRY)
        )
        assert created["statusCode"] == 201
        entry_id = body_of(created)["entry"]["entry_id"]

        listed = body_of(invoke(lambda_client, "career_crud", api_event(method="GET", user_id=cleanup_user)))
        assert [e["entry_id"] for e in listed["entries"]] == [entry_id]
        # ADR-016 stores a ~1024-float Titan vector on the item; the API must strip it before it
        # reaches a browser, or every dashboard load moves ~20 KB per entry for nothing.
        assert "embedding" not in listed["entries"][0]

        updated = invoke(
            lambda_client,
            "career_crud",
            api_event(
                method="PUT",
                user_id=cleanup_user,
                path_params={"id": entry_id},
                body={**self.ENTRY, "entry_id": entry_id, "title": "AWS SAA (renewed)"},
            ),
        )
        assert updated["statusCode"] == 200

        deleted = invoke(
            lambda_client,
            "career_crud",
            api_event(method="DELETE", user_id=cleanup_user, path_params={"id": entry_id}),
        )
        assert deleted["statusCode"] == 200
        # Hard delete (ADR-027) — the row is gone, not tombstoned.
        assert body_of(invoke(lambda_client, "career_crud", api_event(method="GET", user_id=cleanup_user)))["entries"] == []

    def test_deleting_twice_reports_404_the_second_time(self, lambda_client, cleanup_user):
        created = invoke(
            lambda_client, "career_crud", api_event(method="POST", user_id=cleanup_user, body=self.ENTRY)
        )
        entry_id = body_of(created)["entry"]["entry_id"]

        first = invoke(
            lambda_client,
            "career_crud",
            api_event(method="DELETE", user_id=cleanup_user, path_params={"id": entry_id}),
        )
        second = invoke(
            lambda_client,
            "career_crud",
            api_event(method="DELETE", user_id=cleanup_user, path_params={"id": entry_id}),
        )

        assert (first["statusCode"], second["statusCode"]) == (200, 404)

    def test_one_users_entries_are_invisible_to_another(self, lambda_client, cleanup_user, live_table):
        """The tenancy boundary, on the deployed roles rather than in a mock.

        User id comes from the authorizer claims at handler entry, never from the body — so a
        request naming someone else's id in its payload still reads its own partition.
        """
        invoke(lambda_client, "career_crud", api_event(method="POST", user_id=cleanup_user, body=self.ENTRY))

        other = body_of(
            invoke(lambda_client, "career_crud", api_event(method="GET", user_id="int-test-someone-else"))
        )
        assert other["entries"] == []

    def test_an_unparseable_date_is_rejected_with_a_field_error(self, lambda_client, cleanup_user):
        response = invoke(
            lambda_client,
            "career_crud",
            api_event(
                method="POST",
                user_id=cleanup_user,
                body={**self.ENTRY, "issued_date": "the fourteenth of March"},
            ),
        )

        assert response["statusCode"] == 422
        # Asserting the field, not merely that *something* failed: an assertion on a non-empty error
        # list passes for any validation failure, including one the test did not intend to cause.
        assert [e["field"] for e in body_of(response)["errors"]] == ["CERT.issued_date"]

    def test_a_missing_type_specific_field_is_rejected(self, lambda_client, cleanup_user):
        """ADR-022's per-type schemas are enforced by the deployed function, not just the model."""
        body = {k: v for k, v in self.ENTRY.items() if k != "issued_date"}
        response = invoke(lambda_client, "career_crud", api_event(method="POST", user_id=cleanup_user, body=body))

        assert response["statusCode"] == 422
        assert [e["field"] for e in body_of(response)["errors"]] == ["CERT.issued_date"]


class TestResumeAgentRejectionPaths:
    """The résumé agent's guard rails, which cost nothing because they fire before any Bedrock call.

    §3.2.6 hoists both checks ahead of spend deliberately, and that is exactly what makes them
    testable in the free tier. Worth having for a second reason: the request contract is the easiest
    thing to get wrong about the most expensive endpoint, and getting it wrong in the `--expensive`
    tier costs a real run to find out.
    """

    def test_a_missing_target_is_rejected_before_any_spend(self, lambda_client, cleanup_user):
        response = invoke(
            lambda_client, "resume_agent", api_event(method="POST", user_id=cleanup_user, body={})
        )

        assert response["statusCode"] == 400
        # The field is `target` — it takes a full job description or a bare role name.
        assert "`target`" in body_of(response)["message"]

    def test_an_empty_corpus_is_rejected_before_any_spend(self, lambda_client, cleanup_user):
        # No entries were created for this throwaway user, so the empty-corpus checkpoint fires.
        response = invoke(
            lambda_client,
            "resume_agent",
            api_event(method="POST", user_id=cleanup_user, body={"target": "Senior Cloud Engineer"}),
        )

        assert response["statusCode"] == 400
        assert "career entries" in body_of(response)["message"]

    def test_an_unknown_run_id_is_not_found(self, lambda_client, cleanup_user):
        response = invoke(
            lambda_client,
            "resume_agent",
            api_event(
                method="GET", user_id=cleanup_user, path_params={"run_id": "01JQ9999999999999999999999"}
            ),
        )

        assert response["statusCode"] == 404


class TestCheckinRun:
    """§3.3.3 / §4.5.4 — the scheduled path, invoked without sending anything.

    Deliberately narrow. `_process_user` runs only for *due* users, so an invoke on a run where
    nobody is due calls no Bedrock and sends no SES message — but it still executes the full
    `scan_profiles()` step, which is the one thing here that needs an IAM grant the template only
    gained in slice 8 (arch v2.1 added `dynamodb:Scan` to §4.5.4's row after both §3.3.3 and §4.5.4
    described this as a Query, which it cannot be: one partition per user and no GSI per ADR-028).
    """

    def test_a_run_with_nobody_due_scans_cleanly_and_sends_nothing(self, lambda_client, live_table):
        from careervault.checkin_schedule import is_due

        # Never invoke while a real user is due: that would send an actual email and consume their
        # cycle, since the slot is claimed before SES (B-016). Reading the state first is what keeps
        # this test free of side effects rather than merely usually free of them.
        profiles = live_table.scan(FilterExpression="SK = :sk", ExpressionAttributeValues={":sk": "PROFILE"}).get("Items", [])
        now = datetime.now(timezone.utc)
        if any(is_due(p, now) for p in profiles):
            pytest.skip("a real user is due for a check-in — invoking would send them an email")

        result = invoke(lambda_client, "checkin", {})

        assert result["due"] == 0
        assert result["outcomes"] == {}
        # The Scan itself is the assertion: it saw the profiles, which means the IAM grant is real.
        assert result["scanned"] >= len(profiles)
