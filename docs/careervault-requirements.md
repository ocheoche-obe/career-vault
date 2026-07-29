# CareerVault — Requirements Document

**Version:** 0.6
**Status:** Approved — requirements gathering phase complete
**Last updated:** 2026-07-12

---

## 1. Purpose & Vision

CareerVault is a personal career-tracking application that helps users maintain a living record of their professional milestones, accomplishments, and goals over time. Through periodic check-ins and an AI-powered conversational interface, it lowers the friction of capturing career data when it happens — so that when a user needs to apply for a job, write a resume, or articulate their value, the raw material is already there.

The primary value proposition is **memory and retrieval**, not document generation. The resume output is one valuable artifact among many possible outputs (portfolio pages, business cards, certification plans), but the core asset is the curated career history itself.

A secondary purpose of this project is to serve as a hands-on learning vehicle for AWS solutions architecture, AI engineering, and agentic application design.

---

## 2. Users & Personas

### v1 (single-tenant)
The application owner is the sole user. All architectural decisions assume this constraint for v1, while keeping the data model and auth flow multi-tenant-ready.

### Future (multi-tenant)
- **Career professionals** who want to track their growth without journaling discipline.
- **Job-seekers in active search mode** who need rapid, tailored resume generation.
- **Students / early-career users** building their first portfolio of accomplishments.

---

## 3. Scope

### In scope for MVP (v1)

1. Single-user authentication via Cognito (one user in the pool, expandable later).
2. Conversational text-based ingestion of career milestones, projects, certs, awards, goals, and education.
3. Persistent storage of all career entries with structured tagging.
4. Periodic AI-personalized check-in notifications via email at user-configurable cadence (weekly default; bi-weekly, monthly, quarterly available).
5. RAG-based context retrieval so check-in emails reference recent activity.
6. Reactive resume-generation agent: parse a job description, retrieve relevant career data, draft tailored bullets, self-critique, revise.
7. Output formats: plain text (chat copy/paste), HTML preview in app, PDF download.
8. In-app dashboard showing career history and timeline.

### Deferred (post-MVP)

- Voice-mode ingestion (Web Speech API client-side; cheap to add in v1.1).
- Multi-tenant support (signups, data isolation, abuse prevention).
- Output delivery via email or Google Drive (in-app download covers MVP).
- DOCX export.
- Portfolio webpage generator.
- Business card template export.
- Certification study planning agent.
- Mobile push notifications (only viable if a native app is built).
- Interview prep tooling.
- Post-hoc named-entity verification for generated resumes — programmatic cross-check that every named employer, institution, credential, and project in a generated resume traces to a retrieved entry. MVP relies on prompt constraints and the critique step (see Section 3.2.2 of `careervault-architecture.md`); a deterministic verification gate would catch content hallucination that slips past both.

### Out of scope (explicitly not building)

- Autonomous job-board scanning or external scraping.
- Public-facing or social features (sharing profiles between users).
- Recruiter-facing or employer-facing views.
- Any feature requiring CBRN, biometric, or otherwise sensitive data processing.

---

## 4. Functional Requirements

Numbered for traceability. Each requirement is testable.

### Authentication & user management
- **FR-1.1** The system shall authenticate users via Amazon Cognito.
- **FR-1.2** The system shall associate every stored record with a `user_id` even in single-tenant mode, to preserve forward compatibility with multi-tenancy.

### Career data ingestion
- **FR-2.1** The system shall provide a conversational text input where the user can describe career milestones, projects, achievements, or goals in natural language.
- **FR-2.2** The system shall use an LLM to parse free-form input into structured entries with type tags (MILESTONE, CERT, AWARD, EDUCATION, JOB, GOAL, PROJECT).
- **FR-2.3** The system shall confirm parsed entries with the user before persisting them, allowing edits.
- **FR-2.4** The system shall support follow-up clarifying questions when the user provides ambiguous or sparse input (e.g., "When did this happen?", "What role were you in?").

### Career data storage & retrieval
- **FR-3.1** The system shall persist all career entries in DynamoDB with timestamp, type, free-text content, structured metadata (employer, role, dates, tags), and the originating conversation context.
- **FR-3.2** The system shall expose a dashboard view showing entries grouped by category and chronologically.
- **FR-3.3** The system shall allow the user to edit or delete any entry from the dashboard.

### Periodic check-ins
- **FR-4.1** The system shall send periodic check-in emails to the user at a configurable cadence (weekly, bi-weekly, monthly, quarterly).
- **FR-4.2** The default cadence shall be weekly.
- **FR-4.3** Each check-in email shall include a personalized prompt generated by an LLM with RAG context from recent entries (e.g., "Two weeks ago you mentioned starting the X migration — any progress to log?").
- **FR-4.4** Each check-in email shall include a link to the in-app dashboard.
- **FR-4.5** If LLM personalization fails or exceeds cost budget, the system shall fall back to a generic reminder.
- **FR-4.6** The user shall be able to change cadence and pause notifications from settings.

### Resume generation (reactive agent)
- **FR-5.1** The user shall be able to submit a job description (text input) and request a tailored resume.
- **FR-5.2** The system shall use a Bedrock-hosted agent loop (Claude via tool use) to:
  - Retrieve relevant entries from the user's career data.
  - Draft tailored resume bullets.
  - Critique the draft for relevance, specificity, and impact.
  - Revise based on critique.
- **FR-5.3** The system shall return:
  - Refined bullet points as plain text (copyable), AND/OR
  - A full resume preview in HTML, AND/OR
  - A downloadable PDF version.
- **FR-5.4** The user shall be able to select which output format(s) they want per request.
  *(**Deferred at MVP**, ruled in slice 9. Every run unconditionally produces both an HTML preview
  and a PDF; the user chooses which to **consume** after the fact, not which to **request**. Since
  both artifacts are rendered deterministically from one `ResumeDocument` after the agent finishes,
  per-request selection would save no model tokens — it is a UI affordance, not a cost control,
  which is why it was not worth slice-6 scope. Note this is a distinct question from **B-009**
  (choice of résumé *layout*): FR-5.3 enumerates output **artifacts** — text, HTML, PDF — not
  visual templates, so B-009 is net-new scope rather than unfinished FR-5.3.)*

### Conversational interaction
- **FR-6.1** The system shall provide a chat interface where the user can ask questions about their own career data ("What did I do at Acme Corp?"), request resume help, or ask for guidance on how to log a milestone.
- **FR-6.2** The chat interface shall maintain conversation history within a session.

---

## 5. Non-Functional Requirements

### Cost
- **NFR-1.1** Total monthly AWS spend shall not exceed **$5/month** under normal personal usage. (Tightened from the original $10 after the account lost its 12-month free tier / credits on joining an AWS Organization; enforced by the `careervault-monthly-5usd` AWS Budget.)
- **NFR-1.2** CloudWatch billing alarms shall be configured at **$3/month (warning)** and **$5/month (critical)**, prod-gated (arch §4.1.4).
- **NFR-1.3** Bedrock model selection shall default to Claude Haiku for low-complexity tasks (entry parsing, check-in prompt generation) and reserve Claude Sonnet for high-value tasks (resume tailoring, agent loops).
- **NFR-1.4** All DynamoDB tables shall use on-demand billing mode (no provisioned capacity costs at low usage).

### Performance
- **NFR-2.1** Single conversational entry ingestion shall complete within 5 seconds end-to-end (user submits text → confirmation shown).
- **NFR-2.2** Resume generation (full agent loop) shall complete within **4 minutes**, and shall be
  **asynchronous** — the request returns a run id immediately and the client polls (ADR-037).
  *(Corrected in v0.6. The original "within 30 seconds" was never met and is not achievable with a
  six-phase agent loop: measured **72s** on a 2-entry corpus and **~176s** on the real 13-entry one.
  It also could not have been met synchronously at any duration over API Gateway's 29-second
  integration timeout, which is what forced the async design. The replacement bound is a generous
  ceiling for alerting, not a target — reducing it is tracked as **B-020**.)*
- **NFR-2.3** Dashboard initial load shall complete within 2 seconds.

### Reliability & availability
- **NFR-3.1** The application shall target 99% availability (sufficient for personal use; no SLA).
- **NFR-3.2** All DynamoDB writes shall be acknowledged before the user receives confirmation.
- **NFR-3.3** Failed Bedrock invocations shall be retried with exponential backoff (max 3 attempts).
- **NFR-3.4** Background job failures (check-in emails) shall be logged and visible in CloudWatch but shall not block the user-facing app.

### Security
- **NFR-4.1** All API endpoints shall require valid Cognito JWTs.
- **NFR-4.2** All data in DynamoDB and S3 shall be encrypted at rest using AWS-managed KMS keys.
- **NFR-4.3** All traffic shall be TLS 1.2+.
- **NFR-4.4** IAM roles shall follow least-privilege (each Lambda gets only the permissions it needs).
- **NFR-4.5** No secrets shall be stored in code; all secrets shall live in AWS Systems Manager Parameter Store or Secrets Manager.

### Maintainability
- **NFR-5.1** All infrastructure shall be defined as code via AWS SAM (`infrastructure/template.yaml`).
- **NFR-5.2** The codebase shall include a `CLAUDE.md` for Claude Code session context.
- **NFR-5.3** Lambda functions shall use `aws_lambda_powertools` for structured logging, tracing (X-Ray), and input validation.

### Usability
- **NFR-6.1** The chat interface shall be the primary interaction surface; navigation menus shall be minimal.
- **NFR-6.2** The application shall be usable on desktop and mobile web (responsive design).
- **NFR-6.3** Check-in emails shall render correctly in major email clients (Gmail, Outlook, Apple Mail).

---

## 6. Constraints & Assumptions

### Technical constraints
- All cloud infrastructure shall be on AWS (no multi-cloud for v1).
- Backend language is Python 3.13.
- Frontend is React + Vite.
- LLM access is exclusively through Amazon Bedrock for v1.
- Single AWS region: `us-east-1` (broadest free-tier and Bedrock model coverage).

### Business constraints
- This is a personal weekend project; estimated effort is 5 phases of ~2 weeks part-time work.
- $5/month spend ceiling (see NFR-1.1).
- Single developer (the user) with assistance from Claude Code.

### Assumptions
- The user has an AWS account with free-tier eligibility.
- The user has Claude Pro for Claude Code access during development.
- The user has verified an email address with Amazon SES for sending check-in emails (initially in sandbox mode).
- AWS Bedrock model access is auto-enabled on first invoke (no manual approval needed as of late 2024+).

---

## 7. Success Criteria

The MVP is "done enough to use" when all of the following are true:

1. The user can sign in via Cognito and reach a dashboard.
2. The user can log a career milestone via natural-language chat, see it parsed correctly, confirm it, and find it in the dashboard.
3. The user receives a personalized weekly check-in email referencing recent entries.
4. The user can submit a job description and receive a tailored resume, with progress visible while
   the agent runs. *(Corrected in v0.6 — see NFR-2.2. The original "within 30 seconds" was never met
   and is not achievable: a six-phase agent loop measures 72s–176s depending on corpus size, and
   anything over 29 seconds cannot be served synchronously through API Gateway at all. The criterion
   now describes what the MVP must actually deliver — a completed résumé and a visible wait — rather
   than a number the design deliberately abandoned.)*
5. The user can download a generated resume as a PDF.
6. Monthly AWS spend during normal usage stays under $5.

Stretch (still v1 but nice to have):
- A timeline visualization on the dashboard.
- Goal-tracking with progress indicators.

---

## 8. Resolved Open Questions

Items flagged during requirements gathering that have since been decided. See the Architectural Decisions Log (`careervault-adl.md`) for full reasoning on each.

- **Q-1 (resolved):** Specific shape of structured metadata per entry type (CERT vs. AWARD vs. JOB, etc.). Recognized as a data-modeling design decision rather than a requirements decision; resolved in the architecture phase as **ADR-022** (per-entry-type metadata schemas enforced via Pydantic models in the shared Lambda layer; DynamoDB itself remains schemaless).
- **Q-2 (resolved):** Bedrock API choice → **Converse API**. See ADR-017.
- **Q-3 (resolved):** PDF rendering library → **WeasyPrint** (HTML+CSS templates, shared with the in-app preview). See ADR-018.
- **Q-4 (resolved):** Frontend hosting → **S3 + CloudFront direct** with Origin Access Control. See ADR-019.
- **Q-5 (resolved):** RAG retrieval mechanism → **DynamoDB with in-Lambda vector similarity using Bedrock Titan embeddings**, behind an abstracted retrieval interface so the implementation can be swapped later. See ADR-016.

---

## 9. Glossary

The glossary has graduated to its own document: `careervault-glossary.md`. It is grouped by category (AWS services, AI/ML concepts, Anthropic products, software engineering, security, frontend) and includes cross-cloud parallels for Azure and GCP.

---

## 10. Change Log

| Version | Date       | Changes                                                                                          |
|---------|------------|--------------------------------------------------------------------------------------------------|
| 0.1     | 2026-05-31 | Initial draft after scoping conversation.                                                        |
| 0.2     | 2026-05-31 | Consolidation: locked MVP scope, success criteria, FR/NFR numbering; surfaced open questions.    |
| 0.3     | 2026-06-03 | Resolved open questions Q-2 through Q-5; Q-1 formally deferred to architecture phase. Glossary extracted to standalone document. Requirements phase marked complete. |
| 0.4     | 2026-06-08 | Added post-hoc named-entity verification for generated resumes to the deferred backlog (surfaced during Section 3.2 drafting; addresses content hallucination not programmatically caught in MVP). |
| 0.5     | 2026-07-12 | Corrected the cost ceiling to the authoritative **$5** (NFR-1.1, §7.6) and billing-alarm thresholds to **$3 warning / $5 critical** (NFR-1.2), reconciling the requirements doc with CLAUDE.md and the `careervault-monthly-5usd` budget. The original $10 predated the account losing its free-tier/credits on joining an AWS Org. |
| 0.6     | 2026-07-29 | **Slice 9 FR/NFR audit.** Corrected the two "within 30 seconds" résumé claims — **NFR-2.2** and **§7.4 success criterion** — which were falsified by measurement (72s on a 2-entry corpus, ~176s on the real 13-entry one) and were never achievable anyway: anything over API Gateway's 29-second integration timeout cannot be served synchronously, which is precisely what forced the ADR-037 async design. Slice 6b had already corrected the parallel claim in architecture §3.2.2 but left both of these standing, so the drift was only half-fixed and the success criterion the MVP is scored against still asserted something known to be false. Also recorded **FR-5.4** as deferred with its reasoning, and distinguished it from B-009. Full audit in [`careervault-mvp-scorecard.md`](careervault-mvp-scorecard.md). |
