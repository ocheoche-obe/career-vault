"""Unit tests for the resume_agent handler — async start / worker / poll (ADR-037).

DynamoDB, S3, Lambda self-invoke, the agent, and rendering are all faked; no test reaches AWS.
"""

import json
import os

import pytest
from helpers import FakeLambdaContext, api_event, body_of, load_handler

from careervault.pydantic_models.resume import ResumeDocument

os.environ.setdefault("DATA_BUCKET_NAME", "careervault-data-test")
os.environ.setdefault("AWS_LAMBDA_FUNCTION_NAME", "careervault-resume-agent-test")

h = load_handler("resume_agent_handler", "resume_agent")


def _ok_result():
    return h.agent.AgentResult(
        run_id="01JRUN",
        status="ok",
        document=ResumeDocument.model_validate({"summary": "Strong engineer."}),
        requirements=None,
        critique_verdict="PASS",
        retrieved_ids=["E1", "E2"],
        cumulative_tokens=4200,
        cumulative_cost_usd=0.021,
        retrieval_iterations=2,
        revisions_used=1,
        trace=[{"phase": "draft"}],
        elapsed_seconds=72.4,
    )


def _fail_result(status):
    return h.agent.AgentResult(
        run_id="01JRUN", status=status, document=None, requirements=None, critique_verdict=None,
        retrieved_ids=[], cumulative_tokens=500, cumulative_cost_usd=0.001, retrieval_iterations=1, revisions_used=0, trace=[],
    )


@pytest.fixture
def stubs(monkeypatch):
    """Stub every external boundary of the handler; tests override individual pieces as needed."""
    state = {"created": [], "finalized": [], "invoked": [], "records": [], "deleted": [], "deleted_traces": [], "run": None}
    # The stored RESUME# record. `_delete` reads it before destroying anything (so an unknown
    # run_id 404s with no side effects) and takes the object keys from it rather than rebuilding
    # them from a filename convention. Tests that need it absent set `state["record"] = None`.
    state["record"] = {
        "run_id": "01JRUN",
        "status": "completed",
        "created_at": "2026-08-01T00:00:00Z",
        "html_key": "resumes/user-sub-1/01JRUN/resume.html",
        "pdf_key": "resumes/user-sub-1/01JRUN/resume.pdf",
        "entry_count": 6,
    }

    monkeypatch.setattr(h, "query_entries", lambda uid: [{"entry_id": "E1"}])
    monkeypatch.setattr(h, "get_profile", lambda uid: {"email": "dev@example.com"})
    monkeypatch.setattr(h, "create_resume_run", lambda item: state["created"].append(item))
    monkeypatch.setattr(h, "finalize_resume_run", lambda item: state["finalized"].append(item))
    # ADR-046's durable RESUME# record, plus its read and delete paths.
    monkeypatch.setattr(h, "create_resume_record", lambda item: state["records"].append(item))
    monkeypatch.setattr(h, "get_resume_record", lambda uid, rid: state["record"])
    monkeypatch.setattr(h, "query_resumes", lambda uid, limit=50: [])
    monkeypatch.setattr(h, "delete_resume_record", lambda uid, rid: state["deleted"].append(rid) or True)
    monkeypatch.setattr(h, "delete_resume_run_trace", lambda uid, rid: state["deleted_traces"].append(rid))
    monkeypatch.setattr(h, "render_html", lambda doc, contact: "<html>résumé</html>")
    monkeypatch.setattr(h, "render_pdf", lambda html: b"%PDF-1.7 fake")

    class _Lambda:
        def invoke(self, **kwargs):
            state["invoked"].append(kwargs)

    class _S3:
        def put_object(self, **kwargs):
            state.setdefault("put", []).append(kwargs)

        def delete_objects(self, **kwargs):
            state.setdefault("s3_deleted", []).append(kwargs)
            # Shaped like the real API: a dict, with `Errors` present and empty on full success.
            # Returning None here would have let the handler's per-key error check pass vacuously.
            return {"Deleted": list(kwargs["Delete"]["Objects"]), "Errors": []}

        def generate_presigned_url(self, op, Params, ExpiresIn):  # noqa: N803
            state.setdefault("presigned", []).append(Params)
            return f"https://s3.example/{Params['Key']}"

    monkeypatch.setattr(h, "_lambda", lambda: _Lambda())
    monkeypatch.setattr(h, "_s3", lambda: _S3())
    return state


# --- POST /resumes/generate (start) ---------------------------------------------------------------

def test_start_returns_202_and_enqueues_worker(stubs):
    resp = h.handler(api_event({"target": "Senior Cloud Engineer JD"}), FakeLambdaContext())
    body = body_of(resp)
    assert resp["statusCode"] == 202
    assert body["status"] == "pending"
    assert len(body["run_id"]) == 26
    # A pending record was written and the worker was invoked asynchronously.
    assert stubs["created"][0]["status"] == "pending"
    assert stubs["invoked"][0]["InvocationType"] == "Event"


def test_start_rejects_empty_target(stubs):
    assert h.handler(api_event({"target": "  "}), FakeLambdaContext())["statusCode"] == 400


def test_start_rejects_oversized_target(stubs):
    resp = h.handler(api_event({"target": "x" * (h._MAX_TARGET_CHARS + 1)}), FakeLambdaContext())
    assert resp["statusCode"] == 400


def test_start_400_when_no_entries(stubs, monkeypatch):
    monkeypatch.setattr(h, "query_entries", lambda uid: [])
    resp = h.handler(api_event({"target": "JD"}), FakeLambdaContext())
    assert resp["statusCode"] == 400
    assert not stubs["invoked"]  # never enqueued a worker


def test_start_missing_sub_is_401(stubs):
    assert h.handler(api_event({"target": "JD"}, sub=None), FakeLambdaContext())["statusCode"] == 401


def test_start_invoke_failure_marks_failed_and_500(stubs, monkeypatch):
    from botocore.exceptions import ClientError

    class _BrokenLambda:
        def invoke(self, **kwargs):
            raise ClientError({"Error": {"Code": "Boom"}}, "Invoke")

    monkeypatch.setattr(h, "_lambda", lambda: _BrokenLambda())
    resp = h.handler(api_event({"target": "JD"}), FakeLambdaContext())
    assert resp["statusCode"] == 500
    assert stubs["finalized"][0]["status"] == "failed"


# --- worker (async) -------------------------------------------------------------------------------

def _worker_event(**over):
    base = {"job": "resume", "user_id": "user-sub-1", "run_id": "01JRUN", "target_text": "JD", "created_at": "2026-07-21T00:00:00Z"}
    base.update(over)
    return base


def test_worker_completes_and_finalizes_with_keys(stubs, monkeypatch):
    monkeypatch.setattr(h.agent, "run_agent", lambda **kw: _ok_result())
    result = h.handler(_worker_event(), FakeLambdaContext())
    assert result["status"] == "completed"
    final = stubs["finalized"][0]
    assert final["status"] == "completed"
    assert final["html_key"].endswith("/resume.html")
    assert final["pdf_key"].endswith("/resume.pdf")
    assert final["document"]["summary"] == "Strong engineer."


def test_worker_agent_failure_finalizes_failed_with_detail(stubs, monkeypatch):
    monkeypatch.setattr(h.agent, "run_agent", lambda **kw: _fail_result("budget_exceeded"))
    result = h.handler(_worker_event(), FakeLambdaContext())
    assert result["status"] == "failed"
    assert stubs["finalized"][0]["detail"] == "budget_exceeded"


def test_worker_bedrock_error_finalizes_bedrock_unavailable(stubs, monkeypatch):
    from careervault.bedrock_client import BedrockError

    def _boom(**kw):
        raise BedrockError("down")

    monkeypatch.setattr(h.agent, "run_agent", _boom)
    h.handler(_worker_event(), FakeLambdaContext())
    assert stubs["finalized"][0]["detail"] == "bedrock_unavailable"


def test_worker_render_failure_finalizes_render_failed(stubs, monkeypatch):
    monkeypatch.setattr(h.agent, "run_agent", lambda **kw: _ok_result())

    def _boom(doc, contact):
        raise RuntimeError("weasyprint blew up")

    monkeypatch.setattr(h, "render_html", _boom)
    h.handler(_worker_event(), FakeLambdaContext())
    assert stubs["finalized"][0]["detail"] == "render_failed"


def test_worker_empty_entries_finalizes_empty_retrieval(stubs, monkeypatch):
    monkeypatch.setattr(h, "query_entries", lambda uid: [])
    h.handler(_worker_event(), FakeLambdaContext())
    assert stubs["finalized"][0]["detail"] == "empty_retrieval"


# --- GET /resumes/{run_id} (poll) -----------------------------------------------------------------

def _get(run_id="01JRUN"):
    return api_event(None, method="GET", path_params={"run_id": run_id})


def test_poll_pending(stubs, monkeypatch):
    monkeypatch.setattr(h, "get_resume_run", lambda uid, rid: {"status": "pending", "created_at": "t"})
    body = body_of(h.handler(_get(), FakeLambdaContext()))
    assert body["status"] == "pending"


def test_poll_completed_presigns_fresh_urls(stubs, monkeypatch):
    monkeypatch.setattr(
        h,
        "get_resume_run",
        lambda uid, rid: {
            "status": "completed",
            "created_at": "t",
            "html_key": "resumes/u/01JRUN/resume.html",
            "pdf_key": "resumes/u/01JRUN/resume.pdf",
            "critique_verdict": "PASS",
            "retrieved_ids": ["E1", "E2"],
            "cumulative_cost_usd": 0.021,
            "cumulative_tokens": 4200,
        },
    )
    body = body_of(h.handler(_get(), FakeLambdaContext()))
    assert body["status"] == "completed"
    assert body["html_url"].endswith("/resume.html")
    assert body["pdf_url"].endswith("/resume.pdf")
    assert body["retrieved_count"] == 2
    assert body["critique_verdict"] == "PASS"


def test_poll_completed_presigns_pdf_as_an_attachment(stubs, monkeypatch):
    """The PDF must save to disk, not open in a tab.

    The frontend link is cross-origin, and HTML's ``download`` attribute is ignored across origins —
    so the disposition has to be baked into the signature. The HTML stays inline: the preview
    renders it in an iframe.
    """
    monkeypatch.setattr(
        h,
        "get_resume_run",
        lambda uid, rid: {
            "status": "completed",
            "created_at": "t",
            "html_key": "resumes/u/01JRUN/resume.html",
            "pdf_key": "resumes/u/01JRUN/resume.pdf",
        },
    )
    h.handler(_get(), FakeLambdaContext())

    by_key = {p["Key"]: p for p in stubs["presigned"]}
    pdf = by_key["resumes/u/01JRUN/resume.pdf"]
    assert pdf["ResponseContentDisposition"] == 'attachment; filename="resume-01JRUN.pdf"'
    assert "ResponseContentDisposition" not in by_key["resumes/u/01JRUN/resume.html"]


def test_poll_failed_returns_friendly_message(stubs, monkeypatch):
    monkeypatch.setattr(h, "get_resume_run", lambda uid, rid: {"status": "failed", "created_at": "t", "detail": "timeout"})
    body = body_of(h.handler(_get(), FakeLambdaContext()))
    assert body["status"] == "failed"
    assert "too long" in body["message"]


def test_poll_not_found_is_404(stubs, monkeypatch):
    monkeypatch.setattr(h, "get_resume_run", lambda uid, rid: None)
    stubs["record"] = None  # neither trace nor durable record — the only real 404 (ADR-046)
    assert h.handler(_get(), FakeLambdaContext())["statusCode"] == 404


# --- ADR-046: the durable RESUME# record ----------------------------------------------------------

def test_worker_writes_the_history_record_after_finalizing_the_trace(stubs, monkeypatch):
    """Ordering is the decision (ADR-046 §3), so it is the thing asserted — not just that both ran.

    Two PutItems, no transaction. Finalizing the trace first means a crash between them costs a list
    row; the reverse would strand a history row behind a poll that never completes.
    """
    order = []
    monkeypatch.setattr(h, "finalize_resume_run", lambda item: order.append("trace"))
    monkeypatch.setattr(h, "create_resume_record", lambda item: order.append("record"))
    monkeypatch.setattr(h.agent, "run_agent", lambda **kw: _ok_result())

    h.handler(_worker_event(), FakeLambdaContext())

    assert order == ["trace", "record"]


def test_history_record_carries_no_ttl(stubs, monkeypatch):
    """The entire durability mechanism: DynamoDB only deletes items that have `expires_at`."""
    monkeypatch.setattr(h.agent, "run_agent", lambda **kw: _ok_result())
    h.handler(_worker_event(), FakeLambdaContext())

    record = stubs["records"][0]
    assert "expires_at" not in record
    # ...while the trace it was split from still expires on schedule.
    assert stubs["finalized"][0]["expires_at"] > 0


def test_history_record_holds_what_the_grid_and_the_copy_button_need(stubs, monkeypatch):
    monkeypatch.setattr(h.agent, "run_agent", lambda **kw: _ok_result())
    h.handler(_worker_event(target_text="Staff Platform Engineer\nWe are hiring..."), FakeLambdaContext())

    record = stubs["records"][0]
    assert record["SK"] == "RESUME#01JRUN"
    assert record["entity_type"] == "RESUME"
    assert record["target_title"] == "Staff Platform Engineer"  # first non-empty line
    assert record["entry_count"] == 2  # len(retrieved_ids)
    assert record["document"]["summary"] == "Strong engineer."  # B-022 survives past day 30
    assert record["elapsed_seconds"] == 72.4  # B-007
    # Trace-only bulk stays on the trace.
    assert "trace" not in record and "retrieved_ids" not in record


def test_both_items_record_the_elapsed_time(stubs, monkeypatch):
    """B-007, asserted on the **writers**.

    The first version of this only checked that the poll *returns* `elapsed_seconds`, using a fake
    item that supplied the field by hand — so it passed while `_final_item` never wrote it, and the
    deployed run reported `None`. A reader test over a hand-built fixture proves nothing about the
    producer; the expensive integration tier is what caught it. Both items are asserted here because
    the poll reads the trace for 30 days and the record forever.
    """
    monkeypatch.setattr(h.agent, "run_agent", lambda **kw: _ok_result())
    h.handler(_worker_event(), FakeLambdaContext())

    assert stubs["finalized"][0]["elapsed_seconds"] == 72.4
    assert stubs["records"][0]["elapsed_seconds"] == 72.4


def test_a_failed_run_writes_no_history_record(stubs, monkeypatch):
    """"Past résumés" must mean résumés that exist — a failure leaves a trace and nothing else."""
    monkeypatch.setattr(h.agent, "run_agent", lambda **kw: _fail_result("budget_exceeded"))
    h.handler(_worker_event(), FakeLambdaContext())

    assert stubs["finalized"][0]["status"] == "failed"
    assert stubs["records"] == []


def test_a_broken_history_write_does_not_fail_a_completed_run(stubs, monkeypatch):
    """The résumé exists and the poll works; a missing list row must not turn that into a failure."""
    from botocore.exceptions import ClientError

    def _boom(item):
        raise ClientError({"Error": {"Code": "Boom"}}, "PutItem")

    monkeypatch.setattr(h, "create_resume_record", _boom)
    monkeypatch.setattr(h.agent, "run_agent", lambda **kw: _ok_result())

    assert h.handler(_worker_event(), FakeLambdaContext())["status"] == "completed"


def test_target_title_falls_back_when_the_target_is_only_whitespace():
    assert h._target_title("\n  \n") == "Untitled target"


def test_target_title_is_bounded():
    assert len(h._target_title("x" * 500)) == h._TARGET_TITLE_CHARS


# --- ADR-046: GET /resumes (history) --------------------------------------------------------------

def test_get_without_a_run_id_lists_history(stubs, monkeypatch):
    """Formerly a 400. Both routes reach one handler; the absent path param *is* the list request."""
    monkeypatch.setattr(
        h,
        "query_resumes",
        lambda uid, limit=50: [
            {"run_id": "01JB", "created_at": "2026-08-02", "target_title": "Staff SRE", "entry_count": 9, "status": "completed"},
            {"run_id": "01JA", "created_at": "2026-07-11", "target_title": "Senior SRE", "entry_count": 7, "status": "completed"},
        ],
    )
    resp = h.handler(api_event(None, method="GET", path_params=None), FakeLambdaContext())
    body = body_of(resp)

    assert resp["statusCode"] == 200
    assert [r["run_id"] for r in body["resumes"]] == ["01JB", "01JA"]
    assert body["resumes"][0]["target_title"] == "Staff SRE"
    assert body["resumes"][0]["entry_count"] == 9


def test_history_list_is_empty_not_an_error_for_a_new_user(stubs):
    body = body_of(h.handler(api_event(None, method="GET", path_params=None), FakeLambdaContext()))
    assert body["resumes"] == []


def test_poll_falls_back_to_the_record_once_the_trace_has_expired(stubs, monkeypatch):
    """The bug ADR-046's split would otherwise introduce: the list shows a row whose View 404s.

    Past 30 days the RESUMERUN# trace is gone but the artifacts are not — the résumé must still
    open from its durable record.
    """
    monkeypatch.setattr(h, "get_resume_run", lambda uid, rid: None)
    monkeypatch.setattr(
        h,
        "get_resume_record",
        lambda uid, rid: {
            "status": "completed",
            "created_at": "2026-01-04",
            "html_key": "resumes/u/01JOLD/resume.html",
            "pdf_key": "resumes/u/01JOLD/resume.pdf",
            "entry_count": 6,
            "document": {"summary": "Still here."},
        },
    )
    resp = h.handler(_get("01JOLD"), FakeLambdaContext())
    body = body_of(resp)

    assert resp["statusCode"] == 200
    assert body["status"] == "completed"
    assert body["html_url"].endswith("/resume.html")
    assert body["retrieved_count"] == 6  # from entry_count; the trace's retrieved_ids are gone
    assert body["document"]["summary"] == "Still here."


def test_poll_404s_only_when_neither_item_exists(stubs, monkeypatch):
    monkeypatch.setattr(h, "get_resume_run", lambda uid, rid: None)
    monkeypatch.setattr(h, "get_resume_record", lambda uid, rid: None)
    assert h.handler(_get(), FakeLambdaContext())["statusCode"] == 404


def test_poll_completed_returns_the_document_and_elapsed_time(stubs, monkeypatch):
    """B-022 (copyable bullets) and B-007 (elapsed survives the run) ride the existing poll."""
    monkeypatch.setattr(
        h,
        "get_resume_run",
        lambda uid, rid: {
            "status": "completed",
            "created_at": "t",
            "html_key": "resumes/u/01JRUN/resume.html",
            "pdf_key": "resumes/u/01JRUN/resume.pdf",
            "retrieved_ids": ["E1"],
            "elapsed_seconds": 72.4,
            "document": {"summary": "S", "experience": [{"title": "SRE", "employer": "Acme", "bullets": ["Did a thing"]}]},
        },
    )
    body = body_of(h.handler(_get(), FakeLambdaContext()))

    assert body["elapsed_seconds"] == 72.4
    assert body["document"]["experience"][0]["bullets"] == ["Did a thing"]


# --- B-008: the résumé identity header --------------------------------------------------------

def test_contact_prefers_profile_name_over_everything():
    contact = h._contact_from_profile(
        {"name": "Ada Lovelace", "email": "stored@x.com", "location": "London"},
        jwt_email="jwt@x.com",
    )

    assert contact["name"] == "Ada Lovelace"
    assert contact["email"] == "stored@x.com"  # the editable row wins over the claim
    assert contact["location"] == "London"


def test_contact_falls_back_to_the_jwt_email_when_no_profile_exists():
    """The B-008 symptom: no PROFILE row at all, so the header had nothing and rendered "Résumé"."""
    contact = h._contact_from_profile(None, jwt_email="jwt@x.com")

    assert contact["email"] == "jwt@x.com"
    assert contact["name"] is None


def test_contact_is_empty_only_when_there_is_genuinely_no_identity():
    contact = h._contact_from_profile(None)

    assert contact["name"] is None and contact["email"] is None


def test_worker_payload_carries_the_jwt_email(monkeypatch):
    """The worker runs async (ADR-037) and never sees the API event, so the claim must be carried."""
    captured: dict = {}

    class _FakeLambda:
        def invoke(self, **kwargs):
            captured.update(json.loads(kwargs["Payload"].decode()))
            return {}

    monkeypatch.setattr(h, "_lambda", lambda: _FakeLambda())
    monkeypatch.setattr(h, "query_entries", lambda user_id: [{"entry_id": "x"}])
    monkeypatch.setattr(h, "create_resume_run", lambda item: True)
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "careervault-resume-agent-test")

    event = api_event({"target": "Senior SRE role"}, method="POST", email="claim@x.com")
    response = h.handler(event, FakeLambdaContext())

    assert response["statusCode"] == 202
    assert captured["jwt_email"] == "claim@x.com"


# --- DELETE /resumes/{run_id} (ADR-046 amendment) -------------------------------------------------

def _delete_event(run_id="01JRUN"):
    return api_event(None, method="DELETE", path_params={"run_id": run_id})


def test_delete_removes_artifacts_record_and_trace(stubs):
    resp = h.handler(_delete_event(), FakeLambdaContext())

    assert resp["statusCode"] == 200
    assert body_of(resp)["deleted"] is True
    assert stubs["deleted"] == ["01JRUN"]
    assert stubs["deleted_traces"] == ["01JRUN"]

    keys = [o["Key"] for o in stubs["s3_deleted"][0]["Delete"]["Objects"]]
    assert keys == ["resumes/user-sub-1/01JRUN/resume.html", "resumes/user-sub-1/01JRUN/resume.pdf"]


def test_delete_removes_the_objects_before_the_record(stubs, monkeypatch):
    """The ordering is the decision, so it is what gets asserted.

    Record-first would leave, on a crash, S3 objects nothing references and nothing will ever expire
    — ADR-046 removed the lifecycle rule — with no row left for the user to retry from. Objects
    first fails the other way: a visible row whose download 404s, deletable again because S3 deletes
    are idempotent. A visible retryable fault beats an invisible permanent one.
    """
    order = []
    monkeypatch.setattr(h, "delete_resume_record", lambda uid, rid: order.append("record") or True)

    class _OrderedS3:
        def delete_objects(self, **kwargs):
            order.append("s3")
            return {"Deleted": list(kwargs["Delete"]["Objects"]), "Errors": []}

    monkeypatch.setattr(h, "_s3", lambda: _OrderedS3())

    h.handler(_delete_event(), FakeLambdaContext())

    assert order == ["s3", "record"]


def test_delete_does_not_touch_the_record_when_s3_fails(stubs, monkeypatch):
    """Pressing on would produce exactly the unrecoverable orphaning the ordering exists to avoid."""
    from botocore.exceptions import ClientError

    class _BrokenS3:
        def delete_objects(self, **kwargs):
            raise ClientError({"Error": {"Code": "Boom"}}, "DeleteObjects")

    monkeypatch.setattr(h, "_s3", lambda: _BrokenS3())

    resp = h.handler(_delete_event(), FakeLambdaContext())

    assert resp["statusCode"] == 500
    assert stubs["deleted"] == []  # the record survives, so the user can retry


def test_delete_of_a_missing_resume_is_404_with_no_side_effects(stubs):
    """A 404 must not be a destructive operation that also reports failure.

    The record is read first precisely so this case changes nothing. Deleting first and *then*
    discovering the record was absent would destroy the RESUMERUN# trace of a run that is still
    `pending` — the user's poll would report it expired while a ~$0.31 Sonnet job kept running — and
    would throw away the only diagnostic artifact of a `failed` one.
    """
    stubs["record"] = None

    resp = h.handler(_delete_event(), FakeLambdaContext())

    assert resp["statusCode"] == 404
    assert stubs["deleted"] == []
    assert stubs["deleted_traces"] == []
    assert stubs.get("s3_deleted", []) == []


def test_delete_uses_the_stored_keys_not_a_rebuilt_convention(stubs):
    """The record is authoritative about where its artifacts live.

    Rebuilding `resumes/{user}/{run}/resume.html` from today's naming would silently miss any record
    written under a different layout — deleting the row and stranding the real objects, which
    nothing references and nothing expires now that ADR-046 removed the lifecycle rule.
    """
    stubs["record"] = {
        **stubs["record"],
        "html_key": "resumes/user-sub-1/01JRUN/legacy-name.html",
        "pdf_key": "resumes/user-sub-1/01JRUN/legacy-name.pdf",
    }

    h.handler(_delete_event(), FakeLambdaContext())

    keys = [o["Key"] for o in stubs["s3_deleted"][0]["Delete"]["Objects"]]
    assert keys == [
        "resumes/user-sub-1/01JRUN/legacy-name.html",
        "resumes/user-sub-1/01JRUN/legacy-name.pdf",
    ]


def test_delete_stops_when_s3_reports_a_per_key_error(stubs, monkeypatch):
    """`delete_objects` returns 200 with an `Errors` list; it does not raise.

    Treating that as success deletes the record and strands the object permanently — the exact
    B-039 orphaning the S3-first ordering exists to prevent. The `except ClientError` never fires
    here, so the response has to be inspected.
    """

    class _PartialS3:
        def delete_objects(self, **kwargs):
            return {
                "Deleted": [{"Key": "resumes/user-sub-1/01JRUN/resume.html"}],
                "Errors": [{"Key": "resumes/user-sub-1/01JRUN/resume.pdf", "Code": "InternalError"}],
            }

    monkeypatch.setattr(h, "_s3", lambda: _PartialS3())

    resp = h.handler(_delete_event(), FakeLambdaContext())

    assert resp["statusCode"] == 500
    assert stubs["deleted"] == []  # the record survives, so the row stays visible and retryable
    assert stubs["deleted_traces"] == []


def test_delete_succeeds_when_the_trace_has_already_expired(stubs, monkeypatch):
    """The normal case for anything older than 30 days — absence is not an error."""
    from botocore.exceptions import ClientError

    def _boom(uid, rid):
        raise ClientError({"Error": {"Code": "Boom"}}, "DeleteItem")

    monkeypatch.setattr(h, "delete_resume_run_trace", _boom)

    assert h.handler(_delete_event(), FakeLambdaContext())["statusCode"] == 200


def test_delete_without_a_run_id_is_400(stubs):
    # Unlike GET, a bare DELETE /resumes has no meaning — it must not be read as "delete them all".
    resp = h.handler(api_event(None, method="DELETE", path_params=None), FakeLambdaContext())
    assert resp["statusCode"] == 400
    assert stubs["deleted"] == []
