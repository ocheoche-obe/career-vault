"""Unit tests for the resume agent's six-phase bounded loop (Section 3.2 / ADR-036).

Bedrock (Converse + Titan embed) is faked; no test reaches AWS. These pin the loop's control
behaviors — phase transitions, termination conditions, progress tracking, and the cost-guard
budget — since ``agent.py`` owns the orchestration bugs ADR-010 warned about.
"""

import pytest
from helpers import load_sibling

from careervault.bedrock_client import BedrockError

agent = load_sibling("resume_agent_agent", "resume_agent", "agent")


# --- Converse response builders -------------------------------------------------------------------

def _resp(content, stop="tool_use", intok=100, outtok=50):
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop,
        "usage": {"inputTokens": intok, "outputTokens": outtok},
    }


def _tb(name, inp):
    return {"toolUse": {"toolUseId": f"tu-{name}", "name": name, "input": inp}}


def _forced(name, inp, **kw):
    return _resp([_tb(name, inp)], **kw)


def _multi(pairs, **kw):
    return _resp([_tb(n, i) for n, i in pairs], **kw)


class FakeConverse:
    """Dispatches to a per-phase FIFO queue keyed by the forced tool (auto = retrieval)."""

    def __init__(self):
        self.analysis = []
        self.retrieval = []
        self.resume = []
        self.critique = []
        self.calls = []

    def __call__(self, messages, *, system, tool_config, model_id, max_tokens):
        self.calls.append(model_id)
        choice = tool_config["toolChoice"]
        if "auto" in choice:
            return self.retrieval.pop(0)
        name = choice["tool"]["name"]
        return {"extract_requirements": self.analysis, "submit_resume": self.resume, "submit_critique": self.critique}[name].pop(0)


def _entry(eid, etype="JOB", title="Engineer", content="Built the platform."):
    return {
        "entry_id": eid,
        "entry_type": etype,
        "title": title,
        "content": content,
        "employer": "Acme",
        "embedding": [1.0, 0.0, 0.0],
        "PK": "USER#u",
        "SK": f"ENTRY#{eid}",
    }


ANALYSIS = {"requirements": ["AWS", "Python"], "sub_queries": ["cloud", "backend"], "target_type": "JD"}
DRAFT = {"summary": "Strong engineer.", "experience": [{"title": "Engineer", "employer": "Acme", "bullets": ["Shipped"]}]}


@pytest.fixture
def fake(monkeypatch):
    fc = FakeConverse()
    monkeypatch.setattr(agent.bedrock_client, "converse", fc)
    monkeypatch.setattr(agent.bedrock_client, "embed", lambda text, **kw: [1.0, 0.0, 0.0])
    return fc


def _run(entries=None, profile=None):
    if entries is None:
        entries = [_entry("E1")]
    return agent.run_agent(
        run_id="01JRUN", user_id="u", target_text="Senior Cloud Engineer JD", entries=entries, profile=profile
    )


# --- happy path -----------------------------------------------------------------------------------

def test_full_run_reaches_pass_and_produces_document(fake):
    fake.analysis = [_forced("extract_requirements", ANALYSIS)]
    fake.retrieval = [
        _forced("search_entries", {"query": "cloud"}),
        _forced("retrieval_done", {"rationale": "enough"}),
    ]
    fake.resume = [_forced("submit_resume", DRAFT)]
    fake.critique = [_forced("submit_critique", {"verdict": "PASS"})]

    result = _run()

    assert result.ok
    assert result.status == "ok"
    assert result.document is not None
    assert result.document.summary == "Strong engineer."
    assert result.critique_verdict == "PASS"
    assert result.retrieved_ids == ["E1"]
    assert result.cumulative_tokens > 0
    assert result.cumulative_cost_usd > 0


def test_retrieval_done_in_same_turn_as_search_exits_after_one_iteration(fake):
    fake.analysis = [_forced("extract_requirements", ANALYSIS)]
    fake.retrieval = [_multi([("search_entries", {"query": "cloud"}), ("retrieval_done", {"rationale": "done"})])]
    fake.resume = [_forced("submit_resume", DRAFT)]
    fake.critique = [_forced("submit_critique", {"verdict": "PASS"})]

    result = _run()
    assert result.ok
    assert result.retrieval_iterations == 1


# --- retrieval termination + fallback -------------------------------------------------------------

def test_retrieval_falls_back_to_full_corpus_when_nothing_gathered(fake):
    # Model calls retrieval_done without ever searching → retrieved set empty → fall back to corpus
    # rather than fail a user who has entries.
    fake.analysis = [_forced("extract_requirements", ANALYSIS)]
    fake.retrieval = [_forced("retrieval_done", {"rationale": "lazy"})]
    fake.resume = [_forced("submit_resume", DRAFT)]
    fake.critique = [_forced("submit_critique", {"verdict": "PASS"})]

    result = _run(entries=[_entry("E1"), _entry("E2")])
    assert result.ok  # drafted despite no explicit retrieval


def test_retrieval_stops_at_max_iterations(fake, monkeypatch):
    monkeypatch.setattr(agent, "MAX_RETRIEVAL_ITERATIONS", 3)
    fake.analysis = [_forced("extract_requirements", ANALYSIS)]
    # Never calls retrieval_done — keeps searching. Loop must cap at MAX and proceed.
    fake.retrieval = [_forced("search_entries", {"query": f"q{i}"}) for i in range(3)]
    fake.resume = [_forced("submit_resume", DRAFT)]
    fake.critique = [_forced("submit_critique", {"verdict": "PASS"})]

    result = _run()
    assert result.ok
    assert result.retrieval_iterations == 3


def test_empty_corpus_yields_empty_retrieval_status(fake):
    fake.analysis = [_forced("extract_requirements", ANALYSIS)]
    fake.retrieval = [_forced("retrieval_done", {"rationale": "nothing here"})]

    result = _run(entries=[])
    assert result.status == "empty_retrieval"
    assert result.document is None


# --- phase-1 checkpoint ---------------------------------------------------------------------------

def test_analysis_with_empty_requirements_aborts(fake):
    fake.analysis = [_forced("extract_requirements", {"requirements": [], "sub_queries": ["x"], "target_type": "JD"})]
    result = _run()
    assert result.status == "validation_abort"
    assert result.document is None


# --- draft validation retry -----------------------------------------------------------------------

def test_draft_invalid_then_valid_retries_once(fake):
    fake.analysis = [_forced("extract_requirements", ANALYSIS)]
    fake.retrieval = [_forced("retrieval_done", {"rationale": "done"})]
    # First draft missing the required `summary`; retry succeeds.
    fake.resume = [_forced("submit_resume", {"skills": ["python"]}), _forced("submit_resume", DRAFT)]
    fake.critique = [_forced("submit_critique", {"verdict": "PASS"})]

    result = _run()
    assert result.ok
    assert result.document.summary == "Strong engineer."


def test_draft_invalid_twice_aborts(fake):
    fake.analysis = [_forced("extract_requirements", ANALYSIS)]
    fake.retrieval = [_forced("retrieval_done", {"rationale": "done"})]
    fake.resume = [_forced("submit_resume", {"skills": ["x"]}), _forced("submit_resume", {"skills": ["y"]})]

    result = _run()
    assert result.status == "validation_abort"
    assert result.document is None


# --- critique / revise loop -----------------------------------------------------------------------

def test_stagnation_breaks_the_revise_loop(fake, monkeypatch):
    # Give room for 2 revisions so it's *stagnation* (not the revision cap) that ends the loop.
    monkeypatch.setattr(agent, "MAX_REVISIONS", 2)
    fake.analysis = [_forced("extract_requirements", ANALYSIS)]
    fake.retrieval = [_forced("retrieval_done", {"rationale": "done"})]
    fake.resume = [_forced("submit_resume", DRAFT), _forced("submit_resume", DRAFT)]  # draft + 1 revise
    # Same missing_requirements twice → 100% overlap → stop rather than pay to fail the same way.
    fake.critique = [
        _forced("submit_critique", {"verdict": "REVISE", "missing_requirements": ["leadership", "scale"]}),
        _forced("submit_critique", {"verdict": "REVISE", "missing_requirements": ["leadership", "scale"]}),
    ]

    result = _run()
    assert result.ok
    assert result.revisions_used == 1
    assert result.critique_verdict == "REVISE"


def test_revisions_exhausted_finalizes(fake, monkeypatch):
    monkeypatch.setattr(agent, "MAX_REVISIONS", 2)
    fake.analysis = [_forced("extract_requirements", ANALYSIS)]
    fake.retrieval = [_forced("retrieval_done", {"rationale": "done"})]
    fake.resume = [_forced("submit_resume", DRAFT) for _ in range(3)]  # draft + 2 revises
    # Distinct complaints each time → no stagnation → runs until the revision cap.
    fake.critique = [
        _forced("submit_critique", {"verdict": "REVISE", "missing_requirements": ["a"]}),
        _forced("submit_critique", {"verdict": "REVISE", "missing_requirements": ["b"]}),
        _forced("submit_critique", {"verdict": "REVISE", "missing_requirements": ["c"]}),
    ]

    result = _run()
    assert result.ok
    assert result.revisions_used == 2


def test_unrecoverable_critique_finalizes_with_current_draft(fake):
    fake.analysis = [_forced("extract_requirements", ANALYSIS)]
    fake.retrieval = [_forced("retrieval_done", {"rationale": "done"})]
    fake.resume = [_forced("submit_resume", DRAFT)]
    # Both critique attempts invalid (missing verdict) → degrade gracefully, keep the draft.
    fake.critique = [_forced("submit_critique", {"foo": "bar"}), _forced("submit_critique", {"foo": "baz"})]

    result = _run()
    assert result.ok
    assert result.document is not None
    assert result.critique_verdict is None


# --- budget guard ---------------------------------------------------------------------------------

def test_token_budget_exceeded_halts_run(fake, monkeypatch):
    monkeypatch.setattr(agent, "TOKEN_BUDGET_CEILING", 100)
    # The analyze call alone reports 150 tokens > 100 ceiling → halt before spending more.
    fake.analysis = [_forced("extract_requirements", ANALYSIS, intok=100, outtok=50)]

    result = _run()
    assert result.status == "budget_exceeded"
    assert result.document is None
    assert len(fake.calls) == 1  # stopped after the first call


# --- tool execution internals ---------------------------------------------------------------------

def _run_state(entries):
    entries_by_id = {e["entry_id"]: agent._public_entry(e) for e in entries}
    return agent.RunState(
        run_id="r", user_id="u", target_text="t", raw_entries=entries, entries_by_id=entries_by_id, profile={"skills": ["python"]}
    )


def test_search_entries_returns_ranked_snippets(monkeypatch):
    monkeypatch.setattr(agent.bedrock_client, "embed", lambda text, **kw: [1.0, 0.0, 0.0])
    run = _run_state([_entry("E1"), _entry("E2")])
    payload, done = agent._execute_tool(run, {"name": "search_entries", "input": {"query": "cloud", "top_k": 5}})
    assert done is False
    assert payload["count"] == 2
    assert {r["entry_id"] for r in payload["results"]} == {"E1", "E2"}
    assert "similarity" in payload["results"][0]
    assert run.retrieved_ids == {"E1", "E2"}


def test_search_embed_failure_is_returned_as_data_not_raised(monkeypatch):
    def _boom(text, **kw):
        raise BedrockError("titan down")

    monkeypatch.setattr(agent.bedrock_client, "embed", _boom)
    run = _run_state([_entry("E1")])
    payload, _ = agent._execute_tool(run, {"name": "search_entries", "input": {"query": "x"}})
    assert payload["error"] == "transient_failure"
    assert payload["retry_advised"] is True


def test_get_entry_hit_and_miss():
    run = _run_state([_entry("E1")])
    hit, _ = agent._execute_tool(run, {"name": "get_entry", "input": {"entry_id": "E1"}})
    assert hit["entry"]["title"] == "Engineer"
    miss, _ = agent._execute_tool(run, {"name": "get_entry", "input": {"entry_id": "NOPE"}})
    assert miss["error"] == "no_match"


def test_list_skills_reads_profile():
    run = _run_state([_entry("E1")])
    payload, _ = agent._execute_tool(run, {"name": "list_skills", "input": {}})
    assert payload["skills"] == ["python"]


def test_duplicate_call_gets_a_nudge_on_third_identical_call():
    run = _run_state([_entry("E1")])
    call = {"name": "get_entry", "input": {"entry_id": "E1"}}
    p1, _ = agent._execute_tool(run, call)
    p2, _ = agent._execute_tool(run, call)
    p3, _ = agent._execute_tool(run, call)
    assert "notice" not in p1 and "notice" not in p2
    assert "notice" in p3  # third identical call is nudged (Section 3.2.6)


def test_retrieval_done_signals_completion():
    run = _run_state([_entry("E1")])
    payload, done = agent._execute_tool(run, {"name": "retrieval_done", "input": {"rationale": "ok"}})
    assert done is True
    assert payload["acknowledged"] is True


# --- stagnation helper ----------------------------------------------------------------------------

def test_stagnant_detects_high_overlap():
    assert agent._stagnant(["a", "b", "c"], ["a", "b", "c"]) is True
    assert agent._stagnant(["a", "b", "c"], ["a"]) is True  # 'a' fully overlaps current
    assert agent._stagnant(["a", "b"], ["c", "d"]) is False
    assert agent._stagnant(None, ["a"]) is False
    assert agent._stagnant(["a"], []) is False
