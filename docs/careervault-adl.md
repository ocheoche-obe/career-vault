# CareerVault — Architectural Decisions Log (ADL)

**Status:** Living document — updated as decisions are made
**Last updated:** 2026-07-13 (ADR-033 added at the start of slice 3 — semantic duplicate detection; ADR-024 gained an edit-path note)

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

---

## ADR-015: Output delivery for MVP — in-app download only

**Status:** Accepted
**Date:** 2026-05-31

### Context
Resume output could be delivered via in-app download, emailed to the user, pushed to Google Drive, or other channels.

### Decision
v1 supports in-app download (HTML preview + PDF download) and plain-text copy/paste from chat. No email-of-output, no Drive integration.

For PDF storage in S3: keep the most recent generation indefinitely; older generations have a 7-day TTL via S3 lifecycle policy. No DynamoDB record per generation in MVP — the "list past resumes" feature is post-MVP and would add `GENERATED_RESUME` entries later.

### Alternatives considered
- **Email delivery in MVP** — easy via SES, but adds attachment handling complexity.
- **Google Drive integration** — requires OAuth flow with Google, significant scope creep.

### Consequences
- ✅ Tight MVP scope; simplest possible delivery path.
- ⚠️ Power users may want emailed output; revisit post-MVP.

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

## Future ADRs (placeholders)

These decisions are anticipated and will be added as work progresses:

- **ADR-020** — Dashboard UX spec.
- **ADR-021** — Notification fallback rules (when to use generic reminder vs personalized).
