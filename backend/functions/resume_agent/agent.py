"""The resume agent's six-phase bounded loop (Section 3.2 / ADR-010 / ADR-036).

This module is the *brain*: given the user's target, their career entries, and their profile, it
runs Phases 1–5 (analyze → retrieve → draft → critique → revise) and returns a validated
:class:`~careervault.pydantic_models.resume.ResumeDocument` plus a full run trace. It performs **no**
DynamoDB writes and **no** S3 or PDF work — Phase 6 (finalize) is the handler's job, so the loop
stays a pure function of its inputs and is unit-testable by faking only ``bedrock_client``.

Cost controls are the reason this is bounded (ADR-036): a cumulative **token-budget ceiling**
(~150K ≈ $1) and a **wall-clock timeout** gate every Bedrock call, on top of the per-phase
iteration/revision caps and stagnation detection (Section 3.2.4–3.2.6). Expected spend is
~$0.10–0.30 per run; the ceiling only fires on a runaway.

Rather than raise on an *expected* agent failure (budget/timeout/validation abort/empty retrieval),
:func:`run_agent` catches it and returns an :class:`AgentResult` with a non-``ok`` ``status`` and the
partial trace — so the handler can persist the trace and map the outcome to an HTTP code uniformly.
Only a genuinely unexpected ``BedrockError`` propagates.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from aws_lambda_powertools.metrics import MetricUnit
from pydantic import ValidationError

from careervault import bedrock_client
from careervault.ddb_helpers import from_ddb_numbers
from careervault.observability import logger, metrics
from careervault.pydantic_models.resume import (
    RETRIEVAL_TOOL_NAMES,
    Critique,
    RequirementsAnalysis,
    ResumeDocument,
    build_analysis_tool_config,
    build_critique_tool_config,
    build_draft_tool_config,
    build_retrieval_tool_config,
)
from careervault.similarity import rank_by_similarity

# --- Bounded-loop constants (ADR-036; all env-tunable) --------------------------------------------
# Defaults tuned down from the arch §3.2.4 15/2 after slice-6a's first live run measured
# 85K tokens / $0.39 / ~230s (ADR-036 cost-tuning note): the agent converged retrieval in ~5
# iterations and the 2nd revision never flipped the critique verdict, so both were mostly spend.
MAX_RETRIEVAL_ITERATIONS = int(os.environ.get("AGENT_MAX_RETRIEVAL_ITERATIONS", "8"))
MAX_REVISIONS = int(os.environ.get("AGENT_MAX_REVISIONS", "1"))
#: Cumulative (input+output) token ceiling across *all* Bedrock calls in a run. ADR-036 tightened
#: this from the arch §3.2.4 500K to 150K (~$1) for the $5/month ceiling.
TOKEN_BUDGET_CEILING = int(os.environ.get("AGENT_TOKEN_BUDGET", "150000"))
WALL_CLOCK_SECONDS = int(os.environ.get("AGENT_WALL_CLOCK_SECONDS", "240"))
#: Overlap of consecutive ``missing_requirements`` lists above which a revise is deemed stagnant.
STAGNATION_OVERLAP = float(os.environ.get("AGENT_STAGNATION_OVERLAP", "0.8"))

#: A `(tool, args)` pair seen this many times triggers a nudge in the tool result (Section 3.2.6).
_DUP_CALL_NUDGE_AT = 3
_DEFAULT_TOP_K = 10
_MAX_TOP_K = 25
_SEARCH_SNIPPET_CHARS = 300
_MAX_OUTPUT_TOKENS = 4096

#: Bedrock pricing (USD per token) for the run-cost estimate in the trace/metrics. Figures for the
#: budget guard, not billing truth — the authoritative cost is AWS Cost Explorer. Titan embed cost is
#: negligible and omitted.
#:
#: **These are the Regional CRIS rates, not the base on-demand rates.** Every model here is invoked
#: through a `us.` cross-region inference profile (ADR-031), and Bedrock bills cross-region inference
#: at a ~10% premium over the headline per-model price — Sonnet 4-6 is $3/$15 on-demand but
#: **$3.30/$16.50** through `us.`. Using the headline numbers understated every run cost we recorded
#: in slices 6a/6b by that 10%; verified against `list-foundation-model-agreement-offers` rate cards
#: (dimensions `USE1_InputTokenCount` / `USE1_OutputTokenCount` = Regional CRIS; the `_Global`
#: variants are the cheaper global-profile rates we don't use).
_PRICE_PER_TOKEN = {
    # Sonnet 4-6 via us.* — swap to (2.20, 11.00) if BEDROCK_SONNET_MODEL_ID moves to Sonnet 5:
    # its Regional CRIS rate is $2.20/$11.00, ~33% cheaper per token (ADR-036 model-swap note).
    "sonnet": (3.30 / 1_000_000, 16.50 / 1_000_000),
    "haiku": (1.10 / 1_000_000, 5.50 / 1_000_000),
}


class AgentError(RuntimeError):
    """Base class for expected, trace-persisting agent terminations."""


class AgentBudgetExceeded(AgentError):
    """Cumulative token ceiling crossed — stop before spending more (Section 3.2.4)."""


class AgentTimeout(AgentError):
    """Wall-clock budget crossed (Section 3.2.4)."""


class AgentValidationAbort(AgentError):
    """A structured tool payload failed validation twice (Section 3.2.8)."""


class AgentEmptyRetrieval(AgentError):
    """Retrieval gathered nothing to write from (Section 3.2.6 checkpoint)."""


def _model_family(model_id: str) -> str:
    lowered = model_id.lower()
    return "haiku" if "haiku" in lowered else "sonnet"


#: Bedrock prompt-caching multipliers on the *input* rate (ADR-048). A cache write costs more than
#: an uncached read, which is why caching a prefix that is never re-read is a net loss — and why
#: only the retrieval loop is cached.
_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.10


def _cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Price one call. ``inputTokens`` excludes anything served from or written to cache.

    Verified against a live response rather than assumed: a 2403-token cached prefix came back as
    ``inputTokens: 13`` with ``cacheReadInputTokens: 2403``, so adding the cache counts to
    ``inputTokens`` would double-count and treating them as free would under-report.
    """
    in_rate, out_rate = _PRICE_PER_TOKEN[_model_family(model_id)]
    return (
        input_tokens * in_rate
        + cache_write_tokens * in_rate * _CACHE_WRITE_MULTIPLIER
        + cache_read_tokens * in_rate * _CACHE_READ_MULTIPLIER
        + output_tokens * out_rate
    )


def _sonnet_model_id() -> str:
    return os.environ["BEDROCK_SONNET_MODEL_ID"]


def _haiku_model_id() -> str:
    return os.environ["BEDROCK_HAIKU_MODEL_ID"]


def _critique_model_id() -> str:
    """Which model judges the draft (ADR-048).

    Env-switchable rather than hard-coded because this is the one model choice in the agent that
    trades *quality* for cost and speed, and ADR-048's stated revert trigger — "critique output that
    stops distinguishing good drafts from bad" — is a judgement made from real output, weeks later,
    by someone who should not need a code change and a container build to act on it. It also made
    the two levers in this slice separately measurable, which is how the split below was obtained.
    """
    return _haiku_model_id() if os.environ.get("AGENT_CRITIQUE_MODEL", "haiku") == "haiku" else _sonnet_model_id()


def _args_hash(tool_name: str, tool_input: dict) -> str:
    payload = json.dumps({"t": tool_name, "i": tool_input}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class RunState:
    """Mutable accounting for one agent run: budget, tool-call history, and the persisted trace."""

    run_id: str
    user_id: str
    target_text: str
    #: Ranking corpus — raw DDB items (embeddings intact, as Decimals). Never leaves this module.
    raw_entries: list[dict]
    #: Public projection by entry_id (no embedding, numbers coerced) for detail + drafting.
    entries_by_id: dict[str, dict]
    profile: dict | None
    started_at: float = field(default_factory=time.monotonic)
    cumulative_tokens: int = 0
    cumulative_cost_usd: float = 0.0
    cumulative_cache_read_tokens: int = 0
    cumulative_cache_write_tokens: int = 0
    call_history: list[str] = field(default_factory=list)
    retrieved_ids: set[str] = field(default_factory=set)
    trace: list[dict] = field(default_factory=list)
    retrieval_iterations: int = 0
    revisions_used: int = 0
    status: str = "ok"

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at


@dataclass
class AgentResult:
    """What :func:`run_agent` returns — outcome, document (if any), and run accounting."""

    run_id: str
    status: str
    document: ResumeDocument | None
    requirements: RequirementsAnalysis | None
    critique_verdict: str | None
    retrieved_ids: list[str]
    cumulative_tokens: int
    cumulative_cost_usd: float
    retrieval_iterations: int
    revisions_used: int
    trace: list[dict]
    #: Wall-clock seconds the agent ran (B-007). Defaulted so a partial result can still be built
    #: in tests; ``run_agent`` always populates it, including on every failure path.
    elapsed_seconds: float = 0.0
    #: Prompt-cache accounting (ADR-048). ``cache_read_tokens`` is the proof caching actually
    #: engaged — a cachePoint below the model minimum is a silent no-op, so a zero here on a
    #: multi-iteration run means the feature is present in the request and absent from the bill.
    cumulative_cache_read_tokens: int = 0
    cumulative_cache_write_tokens: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "ok"


# --- Bedrock call wrapper: tokens, cost, trace, budget --------------------------------------------

def _cache_point() -> dict:
    """A Bedrock prompt-cache breakpoint. Everything *before* it becomes cacheable prefix."""
    return {"cachePoint": {"type": "default"}}


def _cached_system(text: str) -> list[dict]:
    """System prompt plus a cache breakpoint, so it and the tool schemas cache together."""
    return [{"text": text}, _cache_point()]


def _with_moving_breakpoint(messages: list[dict]) -> list[dict]:
    """Return ``messages`` with exactly one cache breakpoint, on the final turn.

    The retrieval loop re-sends a conversation that grows every iteration (B-004), so the thing
    worth caching is not just the static header but *last iteration's history*. Moving the
    breakpoint to the end each time means iteration N+1 reads everything iteration N sent as cache
    rather than paying full input rate for it.

    Old breakpoints are stripped rather than accumulated: Claude allows a small fixed number of
    them, and a loop that adds one per iteration would hit the limit. Stripping is safe because a
    cachePoint is a marker, not content — removing one does not change the token prefix that the
    cache is keyed on.
    """
    cleaned = []
    for message in messages:
        content = [block for block in message["content"] if "cachePoint" not in block]
        cleaned.append({**message, "content": content})
    if cleaned:
        cleaned[-1] = {**cleaned[-1], "content": [*cleaned[-1]["content"], _cache_point()]}
    return cleaned


def _converse(
    run: RunState,
    *,
    phase: str,
    model_id: str,
    system: str | list[dict],
    messages: list[dict],
    tool_config: dict,
) -> dict:
    """Call Converse, meter it into the run budget/trace, then enforce the ceiling.

    The budget is checked *after* recording usage: we may have paid for this call, but we stop
    before making the next one once cumulative tokens or wall-clock cross their limits.
    """
    response = bedrock_client.converse(
        messages,
        system=system,
        tool_config=tool_config,
        model_id=model_id,
        max_tokens=_MAX_OUTPUT_TOKENS,
    )
    usage = response.get("usage", {}) or {}
    in_tok = int(usage.get("inputTokens", 0) or 0)
    out_tok = int(usage.get("outputTokens", 0) or 0)
    cache_read = int(usage.get("cacheReadInputTokens", 0) or 0)
    cache_write = int(usage.get("cacheWriteInputTokens", 0) or 0)

    # Cache tokens count toward the budget ceiling at face value even though they are billed at a
    # fraction. The ceiling exists to bound *context size*, not spend — a run whose prompt has grown
    # past the limit is out of control whether or not the growth is cheap.
    run.cumulative_tokens += in_tok + out_tok + cache_read + cache_write
    run.cumulative_cache_read_tokens += cache_read
    run.cumulative_cache_write_tokens += cache_write
    run.cumulative_cost_usd += _cost(model_id, in_tok, out_tok, cache_read, cache_write)
    run.trace.append(
        {
            "phase": phase,
            "model_family": _model_family(model_id),
            "stop_reason": response.get("stopReason"),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
            "cumulative_tokens": run.cumulative_tokens,
            "cumulative_cost_usd": round(run.cumulative_cost_usd, 6),
        }
    )
    _enforce_budget(run)
    return response


def _enforce_budget(run: RunState) -> None:
    if run.cumulative_tokens > TOKEN_BUDGET_CEILING:
        logger.warning("Token budget exceeded", extra={"cumulative_tokens": run.cumulative_tokens})
        raise AgentBudgetExceeded(f"cumulative {run.cumulative_tokens} > ceiling {TOKEN_BUDGET_CEILING}")
    if run.elapsed() > WALL_CLOCK_SECONDS:
        logger.warning("Wall-clock budget exceeded", extra={"elapsed_s": round(run.elapsed(), 1)})
        raise AgentTimeout(f"elapsed {run.elapsed():.0f}s > ceiling {WALL_CLOCK_SECONDS}s")


def _tool_uses(response: dict) -> list[dict]:
    return [
        block["toolUse"]
        for block in response.get("output", {}).get("message", {}).get("content", [])
        if "toolUse" in block
    ]


def _assistant_turn(response: dict) -> dict:
    return {"role": "assistant", "content": response["output"]["message"]["content"]}


def _tool_result(tool_use_id: str, payload: dict) -> dict:
    return {"toolResult": {"toolUseId": tool_use_id, "content": [{"json": payload}]}}


# --- Phase 1: analyze target ----------------------------------------------------------------------

_ANALYZE_SYSTEM = """\
You analyze a job target for a résumé-tailoring agent. Given a job description, job title, or an \
aspirational goal, decompose it into (1) the concrete requirements a strong candidate must evidence \
and (2) 3–5 focused search phrases (sub-queries) that will retrieve matching items from the \
candidate's career history. Each sub-query should target one facet (a skill, a domain, a kind of \
achievement), not the whole target at once. Always call extract_requirements."""


def _analyze(run: RunState) -> RequirementsAnalysis:
    """Phase 1 — Haiku decomposes the target into requirements + retrieval sub-queries."""
    messages = [{"role": "user", "content": [{"text": run.target_text}]}]
    response = _converse(
        run,
        phase="analyze",
        model_id=_haiku_model_id(),
        system=_ANALYZE_SYSTEM,
        messages=messages,
        tool_config=build_analysis_tool_config(),
    )
    uses = _tool_uses(response)
    raw = uses[0]["input"] if uses else {}
    try:
        analysis = RequirementsAnalysis.model_validate(raw)
    except ValidationError as exc:
        # Phase 1→2 checkpoint: without requirements/sub-queries there is nothing to retrieve on.
        logger.warning("extract_requirements failed validation", extra={"errors": exc.error_count()})
        raise AgentValidationAbort("target analysis produced no usable requirements") from exc
    logger.info(
        "Target analyzed",
        extra={"target_type": analysis.target_type, "sub_queries": len(analysis.sub_queries)},
    )
    return analysis


# --- Phase 2: agentic retrieval -------------------------------------------------------------------

_RETRIEVE_SYSTEM = """\
You are gathering material to write a tailored résumé. You have tools to search the candidate's \
career entries, fetch full entry detail, and list their curated skills. Search once per sub-query, \
then follow up on any gap you notice (a requirement with no matching entry yet). Use get_entry when \
a search snippet looks central and you want its full text. Do NOT write the résumé here — when you \
have enough material, call retrieval_done. Be efficient: avoid repeating the same search."""


def _public_entry(item: dict) -> dict:
    public = {k: v for k, v in item.items() if k != "embedding"}
    return from_ddb_numbers(public)


def _search_entries(run: RunState, tool_input: dict) -> dict:
    """Titan-embed the query, cosine-rank the pre-loaded corpus, return the top-k (Section 3.2.3)."""
    query = (tool_input.get("query") or "").strip()
    if not query:
        return {"error": "empty_query", "retry_advised": False}
    top_k = tool_input.get("top_k") or _DEFAULT_TOP_K
    try:
        top_k = max(1, min(int(top_k), _MAX_TOP_K))
    except (TypeError, ValueError):
        top_k = _DEFAULT_TOP_K
    type_filter = set(tool_input.get("entry_types") or [])

    corpus = run.raw_entries
    if type_filter:
        corpus = [e for e in corpus if e.get("entry_type") in type_filter]

    try:
        query_vec = bedrock_client.embed(query)
    except bedrock_client.BedrockError:
        # A tool failure is data, not control flow (Section 3.2.8): let the agent route around it.
        logger.warning("search_entries embed failed", extra={"query": query[:80]})
        return {"error": "transient_failure", "retry_advised": True}

    results = []
    for item, score in rank_by_similarity(query_vec, corpus)[:top_k]:
        entry_id = item.get("entry_id")
        if not entry_id:
            continue
        run.retrieved_ids.add(entry_id)
        content = str(item.get("content", ""))
        results.append(
            {
                "entry_id": entry_id,
                "entry_type": item.get("entry_type"),
                "title": item.get("title"),
                "snippet": content[:_SEARCH_SNIPPET_CHARS],
                "similarity": round(score, 3),
            }
        )
    return {"results": results, "count": len(results)}


def _get_entry(run: RunState, tool_input: dict) -> dict:
    entry_id = (tool_input.get("entry_id") or "").strip()
    item = run.entries_by_id.get(entry_id)
    if item is None:
        return {"error": "no_match", "retry_advised": False}
    run.retrieved_ids.add(entry_id)
    return {"entry": item}


def _list_skills(run: RunState) -> dict:
    skills = (run.profile or {}).get("skills") or []
    return {"skills": from_ddb_numbers(skills)}


def _execute_tool(run: RunState, tool_use: dict) -> tuple[dict, bool]:
    """Run one retrieval tool call. Returns ``(result_payload, is_done)``."""
    name = tool_use.get("name")
    tool_input = tool_use.get("input") or {}

    if name == "retrieval_done":
        return {"acknowledged": True}, True

    if name == "search_entries":
        payload = _search_entries(run, tool_input)
    elif name == "get_entry":
        payload = _get_entry(run, tool_input)
    elif name == "list_skills":
        payload = _list_skills(run)
    else:
        payload = {"error": "unknown_tool", "retry_advised": False}

    # Duplicate-call nudge (Section 3.2.6): a third identical call gets a soft steer, not a block.
    digest = _args_hash(name, tool_input)
    prior = run.call_history.count(digest)
    run.call_history.append(digest)
    if prior + 1 >= _DUP_CALL_NUDGE_AT:
        payload = dict(payload)
        payload["notice"] = "You have already made this exact call. Use the results you have or try a different tool."
    return payload, False


def _retrieve(run: RunState, analysis: RequirementsAnalysis) -> list[dict]:
    """Phase 2 — Sonnet drives a bounded tool-use loop, returning the retrieved entries.

    Guaranteed non-empty when the corpus is non-empty: if the model calls ``retrieval_done`` without
    ever searching (or a truncation cuts the loop short), we fall back to the whole corpus rather
    than fail a user who *has* entries — the empty-*corpus* case is short-circuited by the handler.
    """
    sub_queries = "\n".join(f"- {q}" for q in analysis.sub_queries)
    requirements = "\n".join(f"- {r}" for r in analysis.requirements)
    prompt = (
        f"Target type: {analysis.target_type}\n\n"
        f"Requirements to evidence:\n{requirements}\n\n"
        f"Suggested search sub-queries:\n{sub_queries}\n\n"
        "Gather the material, then call retrieval_done."
    )
    messages = [{"role": "user", "content": [{"text": prompt}]}]
    tool_config = build_retrieval_tool_config()

    for iteration in range(1, MAX_RETRIEVAL_ITERATIONS + 1):
        run.retrieval_iterations = iteration
        # Prompt caching (ADR-048) applies *here* and nowhere else in the agent. This is the only
        # phase that re-sends a prefix — every other Sonnet call is one-shot, where a cache write at
        # 1.25x with no subsequent read is a pure loss. The system breakpoint caches the instructions
        # and tool schemas; the moving one caches the conversation so far.
        response = _converse(
            run,
            phase="retrieve",
            model_id=_sonnet_model_id(),
            system=_cached_system(_RETRIEVE_SYSTEM),
            messages=_with_moving_breakpoint(messages),
            tool_config=tool_config,
        )
        messages.append(_assistant_turn(response))
        stop = response.get("stopReason")

        if stop != "tool_use":
            # end_turn (model decided it's done) or a truncation — exit with what we have. Not an
            # error: the Phase-2→3 checkpoint below handles "nothing gathered".
            logger.info("Retrieval loop ended", extra={"stop_reason": stop, "iteration": iteration})
            break

        remaining = MAX_RETRIEVAL_ITERATIONS - iteration
        done = False
        result_blocks = []
        for tool_use in _tool_uses(response):
            payload, is_done = _execute_tool(run, tool_use)
            payload["iterations_remaining"] = f"{remaining} of {MAX_RETRIEVAL_ITERATIONS}"
            result_blocks.append(_tool_result(tool_use["toolUseId"], payload))
            done = done or is_done
        messages.append({"role": "user", "content": result_blocks})
        if done:
            logger.info("Retrieval complete", extra={"iteration": iteration, "retrieved": len(run.retrieved_ids)})
            break

    retrieved = [run.entries_by_id[eid] for eid in run.retrieved_ids if eid in run.entries_by_id]
    if not retrieved:
        if not run.raw_entries:
            raise AgentEmptyRetrieval("no entries retrieved and corpus is empty")
        logger.warning("Retrieval gathered nothing; falling back to full corpus")
        retrieved = [_public_entry(item) for item in run.raw_entries]
    metrics.add_metric(name="ResumeRetrievedEntries", unit=MetricUnit.Count, value=len(retrieved))
    return retrieved


# --- Phases 3 & 5: draft / revise -----------------------------------------------------------------

_DRAFT_SYSTEM = """\
You write a tailored, truthful résumé as structured JSON via the submit_resume tool. Hard rules:
- Every employer, institution, credential, project name, and dated achievement MUST come from the \
retrieved career entries. Never invent facts, employers, dates, or metrics.
- Select and order content to match the target's requirements; drop history irrelevant to it.
- Write crisp, impact-first bullets. Prefer the candidate's own quantified outcomes.
- If the material is thin for a requirement, simply omit it rather than fabricating.
Always call submit_resume."""


def _entries_block(entries: list[dict]) -> str:
    return json.dumps(entries, ensure_ascii=False, default=str)


def _validate_resume(raw: dict) -> ResumeDocument:
    return ResumeDocument.model_validate(raw)


def _structured_resume_call(run: RunState, *, phase: str, system: str, messages: list[dict]) -> ResumeDocument:
    """One forced ``submit_resume`` call with a single validation retry (Section 3.2.8)."""
    tool_config = build_draft_tool_config()
    response = _converse(run, phase=phase, model_id=_sonnet_model_id(), system=system, messages=messages, tool_config=tool_config)
    uses = _tool_uses(response)
    raw = uses[0]["input"] if uses else {}
    try:
        return _validate_resume(raw)
    except ValidationError as exc:
        logger.info("submit_resume failed validation; retrying once", extra={"phase": phase})
        messages.append(_assistant_turn(response))
        messages.append(
            {
                "role": "user",
                "content": [{"text": f"That résumé failed validation: {exc}. Re-emit a corrected submit_resume."}],
            }
        )
        retry = _converse(run, phase=phase, model_id=_sonnet_model_id(), system=system, messages=messages, tool_config=tool_config)
        retry_uses = _tool_uses(retry)
        retry_raw = retry_uses[0]["input"] if retry_uses else {}
        try:
            return _validate_resume(retry_raw)
        except ValidationError as exc2:
            raise AgentValidationAbort("submit_resume failed validation twice") from exc2


def _draft(run: RunState, analysis: RequirementsAnalysis, entries: list[dict]) -> ResumeDocument:
    """Phase 3 — single Sonnet call producing the first structured draft."""
    prompt = (
        f"TARGET:\n{run.target_text}\n\n"
        f"REQUIREMENTS:\n" + "\n".join(f"- {r}" for r in analysis.requirements) + "\n\n"
        f"RETRIEVED CAREER ENTRIES (the only facts you may use):\n{_entries_block(entries)}\n\n"
        "Write the tailored résumé now via submit_resume."
    )
    messages = [{"role": "user", "content": [{"text": prompt}]}]
    return _structured_resume_call(run, phase="draft", system=_DRAFT_SYSTEM, messages=messages)


_REVISE_SYSTEM = _DRAFT_SYSTEM + "\nYou are revising an existing draft to address a critique."


def _revise(run: RunState, analysis: RequirementsAnalysis, entries: list[dict], draft: ResumeDocument, critique: Critique) -> ResumeDocument:
    """Phase 5 — one revision pass addressing the critique, re-emitting the whole résumé."""
    prompt = (
        f"TARGET:\n{run.target_text}\n\n"
        f"CURRENT DRAFT:\n{draft.model_dump_json()}\n\n"
        f"CRITIQUE TO ADDRESS:\n{critique.model_dump_json()}\n\n"
        f"RETRIEVED CAREER ENTRIES (the only facts you may use):\n{_entries_block(entries)}\n\n"
        "Re-emit the improved résumé via submit_resume."
    )
    messages = [{"role": "user", "content": [{"text": prompt}]}]
    return _structured_resume_call(run, phase="revise", system=_REVISE_SYSTEM, messages=messages)


# --- Phase 4: critique ----------------------------------------------------------------------------

_CRITIQUE_SYSTEM = """\
You are a demanding hiring manager reviewing a résumé against a specific target. Judge only how well \
it evidences the target's requirements and how compelling it reads. Return verdict=PASS only if it \
is genuinely strong and complete for this target; otherwise REVISE with the specific missing \
requirements, weak sections, and concrete fixes. Always call submit_critique."""


def _critique(run: RunState, analysis: RequirementsAnalysis, draft: ResumeDocument) -> Critique | None:
    """Phase 4 — Sonnet role-plays a critical reviewer. Returns ``None`` if it can't be validated.

    A double validation failure here degrades gracefully (Section 3.2.8): rather than abort the whole
    run, ``None`` tells the caller to finalize with the current draft — an un-critiqued résumé beats
    no résumé.
    """
    prompt = (
        f"TARGET:\n{run.target_text}\n\n"
        f"REQUIREMENTS:\n" + "\n".join(f"- {r}" for r in analysis.requirements) + "\n\n"
        f"DRAFT RÉSUMÉ:\n{draft.model_dump_json()}\n\n"
        "Critique it via submit_critique."
    )
    messages = [{"role": "user", "content": [{"text": prompt}]}]
    tool_config = build_critique_tool_config()
    # Critique runs on Haiku (ADR-048): it judges a finished draft against a fixed rubric rather
    # than reasoning multi-step, which is NFR-1.3's own criterion for a Haiku task. Note this moves
    # the phase out of prompt-caching range — Haiku 4.5's minimum is ~4096 tokens — but a one-shot
    # call had nothing to re-read anyway.
    response = _converse(run, phase="critique", model_id=_critique_model_id(), system=_CRITIQUE_SYSTEM, messages=messages, tool_config=tool_config)
    uses = _tool_uses(response)
    raw = uses[0]["input"] if uses else {}
    try:
        return Critique.model_validate(raw)
    except ValidationError:
        logger.info("submit_critique failed validation; retrying once")
        messages.append(_assistant_turn(response))
        messages.append({"role": "user", "content": [{"text": "Re-emit a valid submit_critique."}]})
        retry = _converse(run, phase="critique", model_id=_critique_model_id(), system=_CRITIQUE_SYSTEM, messages=messages, tool_config=tool_config)
        retry_uses = _tool_uses(retry)
        try:
            return Critique.model_validate(retry_uses[0]["input"] if retry_uses else {})
        except (ValidationError, IndexError):
            logger.warning("Critique unrecoverable; finalizing with current draft")
            return None


def _stagnant(prev: list[str] | None, current: list[str]) -> bool:
    """True if ``current`` overlaps ``prev`` by ≥ the stagnation threshold (Section 3.2.6)."""
    if not prev or not current:
        return False
    prev_set = {r.strip().lower() for r in prev}
    cur_set = {r.strip().lower() for r in current}
    if not cur_set:
        return False
    overlap = len(prev_set & cur_set) / len(cur_set)
    return overlap >= STAGNATION_OVERLAP


def _critique_revise(run: RunState, analysis: RequirementsAnalysis, entries: list[dict], draft: ResumeDocument) -> tuple[ResumeDocument, str | None]:
    """Phases 4–5 — critique, then revise up to ``MAX_REVISIONS`` times (Section 3.2.4–3.2.6)."""
    prev_missing: list[str] | None = None
    last_verdict: str | None = None

    while True:
        critique = _critique(run, analysis, draft)
        if critique is None:
            break  # graceful: finalize current draft
        last_verdict = critique.verdict
        if critique.verdict == "PASS":
            break
        if run.revisions_used >= MAX_REVISIONS:
            logger.info("Revisions exhausted", extra={"revisions": run.revisions_used})
            break
        if _stagnant(prev_missing, critique.missing_requirements):
            logger.info("Critique stagnation detected; finalizing")
            break
        draft = _revise(run, analysis, entries, draft, critique)
        run.revisions_used += 1
        prev_missing = critique.missing_requirements

    return draft, last_verdict


# --- Orchestration --------------------------------------------------------------------------------

def run_agent(
    *,
    run_id: str,
    user_id: str,
    target_text: str,
    entries: list[dict],
    profile: dict | None,
    on_draft: Callable[[ResumeDocument], None] | None = None,
) -> AgentResult:
    """Run Phases 1–5 and return an :class:`AgentResult` (never raises on an expected termination).

    ``entries`` are raw DynamoDB items (embeddings intact) — the caller pre-loads them once so the
    corpus is shared across search, get_entry, and the empty-corpus short-circuit. A ``BedrockError``
    (unexpected infra failure) is allowed to propagate; every *expected* agent termination is caught
    and reflected in ``status`` with the partial trace attached.

    ``on_draft`` is invoked once, with the Phase-3 draft, before critique and revise run (ADR-037
    amendment). It exists so the handler can publish a ``draft_ready`` poll state at roughly T+60s
    instead of withholding everything until the run is terminal. It is a *callback* rather than a
    write from inside this module on purpose: the original ADR-037 decision earned its "the agent
    brain stays invocation-agnostic" property, and teaching the loop about DynamoDB would spend it.

    A failing ``on_draft`` must never take the run down — the draft is a progress signal, and losing
    the signal is not a reason to lose the résumé.
    """
    entries_by_id = {e["entry_id"]: _public_entry(e) for e in entries if e.get("entry_id")}
    run = RunState(
        run_id=run_id,
        user_id=user_id,
        target_text=target_text,
        raw_entries=entries,
        entries_by_id=entries_by_id,
        profile=profile,
    )
    document: ResumeDocument | None = None
    requirements: RequirementsAnalysis | None = None
    verdict: str | None = None

    try:
        requirements = _analyze(run)
        retrieved = _retrieve(run, requirements)
        draft = _draft(run, requirements, retrieved)
        if on_draft is not None:
            try:
                on_draft(draft)
            except Exception:  # pragma: no cover - progress signal, never the run's problem
                logger.exception("on_draft callback failed; continuing the run")
        document, verdict = _critique_revise(run, requirements, retrieved, draft)
        run.status = "ok"
    except AgentBudgetExceeded:
        run.status = "budget_exceeded"
    except AgentTimeout:
        run.status = "timeout"
    except AgentValidationAbort:
        run.status = "validation_abort"
    except AgentEmptyRetrieval:
        run.status = "empty_retrieval"

    logger.info(
        "Agent run finished",
        extra={
            "status": run.status,
            "cumulative_tokens": run.cumulative_tokens,
            "cumulative_cost_usd": round(run.cumulative_cost_usd, 4),
            "retrieval_iterations": run.retrieval_iterations,
            "revisions_used": run.revisions_used,
        },
    )
    metrics.add_metric(name="ResumeAgentTokens", unit=MetricUnit.Count, value=run.cumulative_tokens)

    return AgentResult(
        run_id=run_id,
        status=run.status,
        document=document,
        requirements=requirements,
        critique_verdict=verdict,
        retrieved_ids=sorted(run.retrieved_ids),
        cumulative_tokens=run.cumulative_tokens,
        cumulative_cache_read_tokens=run.cumulative_cache_read_tokens,
        cumulative_cache_write_tokens=run.cumulative_cache_write_tokens,
        cumulative_cost_usd=round(run.cumulative_cost_usd, 6),
        retrieval_iterations=run.retrieval_iterations,
        revisions_used=run.revisions_used,
        trace=run.trace,
        elapsed_seconds=round(run.elapsed(), 1),
    )
