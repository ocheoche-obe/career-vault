"""Unit tests for the resume_agent handler — async start / worker / poll (ADR-037).

DynamoDB, S3, Lambda self-invoke, the agent, and rendering are all faked; no test reaches AWS.
"""

import json
import os
import sys
from pathlib import Path

import pytest
from helpers import FakeLambdaContext, api_event, body_of, load_handler

from careervault.pydantic_models.resume import ResumeDocument

_AGENT_DIR = Path(__file__).resolve().parents[2] / "backend" / "functions" / "resume_agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

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
    )


def _fail_result(status):
    return h.agent.AgentResult(
        run_id="01JRUN", status=status, document=None, requirements=None, critique_verdict=None,
        retrieved_ids=[], cumulative_tokens=500, cumulative_cost_usd=0.001, retrieval_iterations=1, revisions_used=0, trace=[],
    )


@pytest.fixture
def stubs(monkeypatch):
    """Stub every external boundary of the handler; tests override individual pieces as needed."""
    state = {"created": [], "finalized": [], "invoked": [], "run": None}

    monkeypatch.setattr(h, "query_entries", lambda uid: [{"entry_id": "E1"}])
    monkeypatch.setattr(h, "get_profile", lambda uid: {"email": "dev@example.com"})
    monkeypatch.setattr(h, "create_resume_run", lambda item: state["created"].append(item))
    monkeypatch.setattr(h, "finalize_resume_run", lambda item: state["finalized"].append(item))
    monkeypatch.setattr(h, "render_html", lambda doc, contact: "<html>résumé</html>")
    monkeypatch.setattr(h, "render_pdf", lambda html: b"%PDF-1.7 fake")

    class _Lambda:
        def invoke(self, **kwargs):
            state["invoked"].append(kwargs)

    class _S3:
        def put_object(self, **kwargs):
            state.setdefault("put", []).append(kwargs)

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
    assert h.handler(_get(), FakeLambdaContext())["statusCode"] == 404


def test_poll_missing_run_id_is_400(stubs):
    assert h.handler(api_event(None, method="GET", path_params=None), FakeLambdaContext())["statusCode"] == 400


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
