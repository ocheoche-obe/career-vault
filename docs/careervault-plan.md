# CareerVault — Implementation Plan & Roadmap

**Status:** Living document — the authoritative "what order, what's done, what's next"
**Version:** 1.0
**Created:** 2026-07-10 (start of Phase 2 slice 2b)

---

## How to use this document

- **Oche:** the [Status board](#status-board) answers "where are we?"; the current slice's detail
  section answers "what are we doing and what do I need to decide?". Items marked ⚠ are decisions
  that will be brought to you *before* they're hit — if you want to think ahead, those are the
  places.
- **Claude:** read this at `/start-slice` (status board + the current slice's detail section);
  update it at `/wrap-slice` (flip the status, fill Completion notes, confirm the next slice's
  scope still holds). A slice is not done until this doc says so.

### Division of authority (no dual sources of truth)

| Document | Owns |
|---|---|
| `docs/careervault-architecture.md` | **How** — system design, data model, per-Lambda contracts |
| `docs/careervault-adl.md` | **Why** — every significant decision, as ADRs |
| `docs/careervault-requirements.md` | **What** — functional/non-functional requirements (FR/NFR) |
| **This document** | **What order & what's done** — slice sequence, scope boundaries, status, completion notes |
| `CLAUDE.md` | Compact session-start context; its phase marker just *points here* |

If this doc ever contradicts the architecture doc on a design matter, the architecture doc wins
and this doc gets fixed (or the contradiction becomes an ADR).

### Status legend

✅ done · 🔨 in progress · ⬜ not started · ⚠ has open decisions

---

## Guiding principles

1. **Vertical slices.** Every slice lands deployed to dev and verified end-to-end (real API
   Gateway → Lambda → downstream), not just unit-tested. "Works on localhost" is not an exit
   criterion unless the slice is frontend-only.
2. **ADR before code.** A decision the architecture doc doesn't cover gets written into
   `careervault-adl.md` *before* the code that implements it.
3. **Docs current before done.** `/wrap-slice` blocks on this doc, the ADL, and (when reality
   contradicted it) the architecture doc being updated.
4. **$5/month ceiling.** Bedrock is the dominant cost driver; slices that add Bedrock usage
   (5, 6, 7, 8) start with a budget-posture check.
5. **This project is an AWS learning vehicle.** When live AWS behavior contradicts the docs, the
   contradiction is surfaced and the doc corrected with reasoning — never silently coded around.

---

## Status board

| Slice | Name | FRs covered | Status | PR |
|---|---|---|---|---|
| P0 | Requirements | — | ✅ | — |
| P1 | Architecture design | — | ✅ | — |
| 1 | Auth + `GET /settings` | FR-1 | ✅ | [#1](https://github.com/ocheoche-obe/career-vault/pull/1) |
| 2a | Chat + entry ingestion (backend) | FR-2 (backend), FR-6.2 | ✅ | [#2](https://github.com/ocheoche-obe/career-vault/pull/2) |
| 2b | Chat UI + turn idempotency | FR-2.3, FR-2.4 (UI), FR-6.2 | ✅ | — |
| 3 | Entries dashboard + CRUD completion | FR-3.2, FR-3.3 | ⬜ ⚠ | — |
| 4 | Frontend hosting (S3 + CloudFront) | NFR (ADR-019) | ⬜ ⚠ | — |
| 5 | Resume upload bootstrap | ADR-013 ingestion path | ⬜ ⚠ | — |
| 6 | Resume agent | FR-5 | ⬜ ⚠ | — |
| 7 | Chat over your data | FR-6.1 | ⬜ ⚠ | — |
| 8 | Check-in emails | FR-4 | ⬜ ⚠ | — |
| 9 | Hardening & MVP close | NFRs, coverage audit | ⬜ ⚠ | — |

FR coverage cross-check: FR-1 ✅ (slice 1) · FR-2 → 2a/2b · FR-3 → 2a (3.1) + 3 · FR-4 → 8 ·
FR-5 → 6 · FR-6 → 2a/2b (6.2) + 7 (6.1). Deferred/v1.1 items live in the
[parking lot](#post-mvp-parking-lot), nowhere else.

---

## Completed slices

### Phase 0 — Requirements ✅

`careervault-requirements.md` v0.4 — six FR groups, NFRs, deferred list, stretch items.

### Phase 1 — Architecture design ✅

`careervault-architecture.md` (v1.1 at completion; v1.3 current after implementation-driven
corrections), all 5 sections + ADRs through ADR-030.

### Slice 1 — Auth + `GET /settings` ✅ (PR #1)

First vertical slice; proved the full stack end-to-end.

- `infrastructure/template.yaml` — SAM template: DynamoDB `CareerVaultTable-${Environment}`
  (PITR + Deletion Protection + AWS-managed SSE), Cognito User Pool + SPA client + Hosted UI
  domain (ADR-025), REST API Gateway with Cognito authorizer, `careervault-shared` layer,
  `settings_lambda` (`GET /settings`), Outputs for the frontend. `infrastructure/samconfig.toml`
  with dev/prod sections.
- `backend/shared/python/careervault/` — `observability.py`, `ddb_helpers.py`,
  `bedrock_client.py` (stub), `pydantic_models/profile.py`.
- `backend/functions/settings/handler.py` — `GET /settings`, returns default profile if none.
  (IAM already grants `UpdateItem` for the future PUT — see slice 8.)
- `frontend/` — Vite React-TS + `react-oidc-context` (ADR-029); Sign in → Hosted UI →
  renders `GET /settings` JSON. Runs on `localhost:5173`; copy `.env.example` → `.env.local`.
- Unit tests in `tests/unit/`; sample API-GW event in `tests/events/settings_get.json`.
- Deploy: `cd infrastructure && sam build && sam deploy` (deletion protection blocks table
  teardown — disable manually first). Create the one user via `aws cognito-idp admin-create-user`
  (`scripts/create-user.sh`, idempotent — doubles as password rotation).
- Cost guards codified: billing alarms ($3 warn / $5 crit, prod-gated), SNS alarm topic, 14-day
  log retention, account-wide budget `careervault-monthly-5usd`.

### Slice 2a — Chat + entry ingestion, backend ✅ (PR #2)

**Deployed to dev and smoke-tested end-to-end** (`POST /chat` → clarification → multi-turn parse
→ `POST /entries` 201 → duplicate confirm 200). React chat UI deferred to slice 2b.

- `backend/functions/chat/` — `POST /chat`, Phase A parse turn; two tools + `toolChoice=any`;
  persists the user message *before* calling Bedrock; one validation-feedback retry (§3.1.6).
- `backend/functions/career_crud/` — `POST /entries`, Phase B; Pydantic validation → Titan embed
  → conditional PutItem; 201/200/422/500 contract (§3.1.5). Only `GetItem`+`PutItem` in IAM;
  Query/Update/Delete land with their routes (slice 3).
- Shared layer: `pydantic_models/{entry,tools,conversation}.py`, real `bedrock_client.py`,
  CONVO/ENTRY `ddb_helpers` + float↔Decimal marshalling.
- **ADR-031**: Claude Haiku 4.5 is invoked via the `us.` cross-region **inference profile**
  (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) — it has no on-demand support. IAM grants
  `bedrock:InvokeModel` on the profile ARN **plus** the foundation-model ARN in us-east-1 /
  us-east-2 / us-west-2. Titan v2 (`amazon.titan-embed-text-v2:0`) stays on-demand. Model IDs
  live in env vars in lockstep with the IAM ARNs.
- Reserved concurrency is **live** (5/5/5) — the account's Lambda limit was restored from 10 to
  1000, so ADR-030's parameterized §4.7.4 guard is switched on via `samconfig.toml`.
- **Bedrock gotcha:** Anthropic models 404 with `ResourceNotFoundException` until the account's
  **Anthropic use-case form** is submitted (Bedrock console → Model access). Titan is unaffected;
  Titan-works-while-Claude-404s is the diagnostic signature. Submitted for this account.
- Arch doc corrected to **v1.3** by two live-API findings: §4.6.2 (Titan v2 has no multi-input
  request form — `embed_many` is a client-side loop) and §4.2.4 (an SK-prefix
  `ConditionExpression` can never succeed; the invariant lives in `assert_sk_prefix`).

---

## Slice 2b — Chat UI + turn idempotency ✅

**Goal:** A user can hold the full ingestion conversation in the browser — chat, get clarifying
questions, review a proposed entry, confirm it, and see it saved — with a clean retry story.

**FRs:** FR-2.3, FR-2.4 (the UI half), FR-6.2 (session-scoped history).

**Scope — in:**
1. **Backend first — ADR-032:** `POST /chat` accepts optional client-minted `client_message_id`
   (ULID, reused on retry); user message persisted with a conditional put
   (`ConditionalCheckFailedException` = retry, proceed); history replay excludes the incoming id;
   ULID-format validation on both `client_message_id` and `session_id` (closes the unvalidated
   `session_id` → SK gap). Unit tests for all four behaviors.
2. **React chat UI:** chat pane on the existing authed app; renders clarifications, proposal
   confirm/edit card; confirm → `POST /entries` (carrying the server-minted `entry_id`, which is
   what makes confirm idempotent per §3.1.4); handles 201 / 200-duplicate / 422 distinctly;
   retry-on-error reuses the same `client_message_id`.

**Scope — out:** entries list/browse view (slice 3), general Q&A chat (slice 7), hosting (slice 4).

**Key refs:** arch §3.1 (two-phase ingestion), §3.1.4–3.1.6; ADR-032; ADR-029 (react-oidc-context).

**New infra:** none (existing endpoints only).

**⚠ Decisions:** none open — ADR-032 settled the one this slice forced.

**Exit criteria:**
- [x] Unit tests green, including the four ADR-032 behaviors (100 passing).
- [x] Deployed to dev; retried chat turn verified idempotent against real DynamoDB (one CONVO
      item, one prompt occurrence).
- [x] Full chat → clarify → propose → confirm → 201 flow smoke-tested *from the UI* (Oche,
      2026-07-10: vague message → clarifying question; concrete message → card → edit → saved).
- [x] Duplicate confirm 200 path — verified at the API level (same `entry_id` twice → 200 with
      the stored item). *Reinterpreted at wrap:* after a successful save the card freezes, so
      this path is UI-reachable only when a confirm fails mid-flight and is retried; the
      duplicate a user actually produces is *semantic* (see completion notes).

**Completion notes:** _(wrapped 2026-07-10, PR #TBD)_
- **Backend (ADR-032):** `POST /chat` takes an optional client-minted `client_message_id`;
  user message persisted with a conditional put (`False` = retry, proceed to inference);
  history replay excludes the incoming id; both `client_message_id` and `session_id` validated
  as ULIDs before SK construction — closing the previously unvalidated `session_id` gap.
  `put_conversation_message` now mirrors `put_entry_conditional`'s True/False contract.
- **Frontend:** chat pane (`frontend/src/chat/`) with clarification/error turns and
  retry-reuses-the-ULID semantics; `ProposalCard` renders all eight entry types generically
  with inline 422 field errors and saved/already-saved/failed states; self-contained ULID
  generator (`src/lib/ulid.ts`, no new dependency); typed API client (`src/lib/api.ts`).
  Replaced the slice-1 settings JSON dump.
- **Verified:** deployed Lambda invoked twice with identical payload → exactly one user CONVO
  item under the client-supplied SK; malformed `session_id` → 400; UI flow smoke-tested by Oche
  against real Bedrock end-to-end.
- **Finding → slice 3:** re-describing the same accomplishment mints a fresh `entry_id`, so it
  saves as a new entry ("Saved", 201) rather than surfacing as a duplicate — §3.1.4 idempotency
  only covers the same proposal card. Semantic duplicate detection via embedding similarity is
  now a slice 3 ⚠ decision. Two real duplicates this produced in dev were hard-deleted.
- Within-session field "memory" (e.g. a start date reappearing on a re-proposal) is AP-12
  history replay, not an entry lookup — a fresh session will ask again.

---

## Slice 3 — Entries dashboard + CRUD completion ⬜ ⚠

**Goal:** The user can see everything they've logged, grouped/chronological, and edit or delete
any entry.

**FRs:** FR-3.2 (dashboard), FR-3.3 (edit/delete).

**Scope — in:** `GET /entries` (Query on `ENTRY#` prefix), `PUT /entries/{id}`,
`DELETE /entries/{id}` in `career_crud` + the Query/UpdateItem/DeleteItem IAM that lands with
them; dashboard UI (grouped by type, chronological within); edit form per entry type; hard delete
with UI confirm (ADR-027).

**Scope — out:** timeline visualization (stretch, parking lot); goals UI (data-model-only at MVP).

**Key refs:** arch §2 (data model, AP-10 read pattern), §4.2.3/4.2.4 (IAM + key isolation),
ADR-027 (hard delete), ADR-028 (no GSIs — reads are PK Queries).

**New infra:** none (routes + IAM on existing Lambda).

**⚠ Decisions:**
- Re-embed on edit: ADR-024 puts embedding in the write path — confirm updates re-embed
  synchronously when text fields change (and skip when they don't). Likely an ADR note, not a
  new ADR.
- **Semantic duplicate detection (found in 2b UI testing, 2026-07-10):** describing the same
  accomplishment in a new message mints a fresh `entry_id`, so it saves as a brand-new entry —
  §3.1.4 idempotency only covers retries of the *same* proposal card. Once Query IAM lands,
  `career_crud` can cosine-compare the new entry's (already-computed) embedding against existing
  entries at confirm time and surface a "possible duplicate — save anyway?" signal. Needs an ADR:
  threshold, warn-vs-block, and response shape.

**Exit criteria:** deployed to dev; list/edit/delete each smoke-tested from the UI; deleted
entry verifiably gone from DynamoDB; edited entry's embedding refreshed.

**Completion notes:** _(filled at wrap)_

---

## Slice 4 — Frontend hosting ⬜ ⚠

**Goal:** The app lives at a real URL — usable from any device, and every later slice is testable
against a deployed frontend.

**FRs:** none directly — ADR-019 infrastructure commitment; prerequisite for FR-4.4 (check-in
emails link to the dashboard).

**Scope — in:** S3 site bucket + CloudFront with Origin Access Control (ADR-019, arch §5.7);
Cognito app-client callback/logout URLs for the hosted origin (keep localhost for dev); frontend
build/deploy steps documented (manual `aws s3 sync` + invalidation at MVP per §5.7).

**Scope — out:** CI/CD (parking lot), custom domain unless decided below.

**Key refs:** ADR-019, ADR-025 (callback URLs), arch §5.7.

**New infra:** S3 site bucket, CloudFront distribution, OAC.

**⚠ Decisions:**
- Default `*.cloudfront.net` domain vs custom domain (+ Route 53 + ACM cert). Cost and effort
  both small but nonzero; default domain is the likely MVP answer.

**Exit criteria:** sign in → chat → confirm entry → dashboard, all from the CloudFront URL on a
device that isn't the dev machine.

**Completion notes:** _(filled at wrap)_

---

## Slice 5 — Resume upload bootstrap ⬜ ⚠

**Goal:** A user with an existing resume doesn't start from zero — upload a PDF/DOCX and have it
parsed into confirmable entries.

**FRs:** ADR-013 (upload supported in MVP); feeds FR-2.3's confirm-before-persist.

**Scope — in:** S3 data bucket `careervault-data-${Environment}-${AccountId}` with `uploads/` +
`resumes/` prefixes and SSE-S3 (arch §4.4.3); presigned-URL upload flow; `resume_upload_parser`
Lambda (PDF/DOCX → entry candidates via Haiku, then N *sequential* Titan embeds per corrected
§4.6.2 — the 5-min timeout in §4.7.4 exists for this); bulk-confirm UI feeding the existing
`POST /entries`.

**Scope — out:** DOCX *export* (v1.1); the `resumes/` prefix is provisioned here but first
written by slice 6.

**Key refs:** arch §4.4 (S3 design), §4.6.2 (sequential embeds), §4.7.4 (timeout), ADR-013,
ADR-024.

**New infra:** S3 data bucket + prefix-scoped IAM, `resume_upload_parser` Lambda + route(s).

**⚠ Decisions:**
- Bulk-confirm UX: confirm entries one-by-one (reuses the 2b card) vs a select-all review table.
- Parse job shape: synchronous request/response vs presigned-upload + poll — depends on realistic
  parse latency for a multi-page resume; measure before choosing.

**Exit criteria:** real multi-page resume uploaded from the UI → parsed → confirmed → entries
visible on the dashboard with embeddings; budget check after (first multi-call Bedrock slice).

**Completion notes:** _(filled at wrap)_

---

## Slice 6 — Resume agent ⬜ ⚠

**Goal:** The payoff feature — paste a job description, get a tailored resume (text/HTML/PDF)
built from your logged history. Largest slice; expect to split 6a (backend loop) / 6b (output UI).

**FRs:** FR-5.1–5.4.

**Scope — in:** `resume_agent` Lambda with the six-phase bounded loop (arch §3.2: retrieve →
draft → critique → revise, explicit termination, action/progress tracking, HITL at input/output
gates only); Sonnet via inference profile; in-Lambda vector retrieval over entry embeddings
(ADR-016); `careervault-weasyprint` layer (ADR-023, Docker/makefile build); RESUMERUN trace items
(TTL 30 days); PDF to `resumes/` prefix; JD-input + format-select + download UI (FR-5.3/5.4).

**Scope — out:** email/Drive delivery (v1.1 — in-app download only per ADR-015); named-entity
verification pass (v1.1).

**Key refs:** arch §3.2 (the whole flow), ADR-009/-010/-015/-016/-017/-018/-023;
**ADR-031 is the IAM precedent** for the Sonnet model below.

**New infra:** `resume_agent` Lambda + route, WeasyPrint layer, Bedrock Sonnet IAM.

**⚠ Decisions:**
- **New ADR before code:** concrete Sonnet model + inference profile ID. Expect
  inference-profile-only like Haiku 4.5 (ADR-031); IAM = profile ARN + regional foundation-model
  ARNs. Also pin the loop's max-iterations / token budget as cost controls.
- Whether 6a/6b actually split into two PRs — decide at slice start based on appetite.

**Exit criteria:** real JD in → agent completes within its bounded loop against real entries →
PDF downloads and *looks like a resume*; RESUMERUN trace inspectable; cost-per-run measured and
noted here (dominant Bedrock cost driver — this number matters for the $5 ceiling).

**Completion notes:** _(filled at wrap)_

---

## Slice 7 — Chat over your data ⬜ ⚠

**Goal:** Chat stops being ingestion-only — the user can *ask* things ("what did I do in 2025?",
"which entries mention Python?", "help me phrase this milestone") and get grounded answers.

**FRs:** FR-6.1 (committed MVP requirement — decided 2026-07-10 to keep in MVP as its own slice).

**Scope — in:** extend `chat_lambda` so a message routes to either entry-parsing (existing two
tools) or Q&A over the user's history — retrieval reusing slice 6's vector-similarity helpers
(ADR-016) + free-text grounded answers; UI unchanged apart from rendering answer turns.

**Scope — out:** anything that writes on the user's behalf beyond the existing propose→confirm
flow.

**Key refs:** arch §3.1 (current parse turn), ADR-016 (retrieval), requirements FR-6.1.

**New infra:** none expected beyond `chat_lambda` IAM widening to read `ENTRY#` items — note
this weakens the current "chat can only touch CONVO#" isolation (§4.2.3); read-only, but say so
in the ADR.

**⚠ Decisions:**
- **Routing design — likely an ADR:** third tool (`answer_question`) with `toolChoice=any`
  retained, vs a router prompt / `toolChoice=auto` with free-text allowed. Interacts with how
  history replays.

**Exit criteria:** ingestion still passes its 2b smoke tests unchanged; questions about seeded
history get correct grounded answers from the UI; a question can't accidentally create an entry.

**Completion notes:** _(filled at wrap)_

---

## Slice 8 — Check-in emails ⬜ ⚠

**Goal:** The habit loop — periodic personalized emails nudge the user to log fresh
accomplishments, with a working unsubscribe/pause and bounce handling.

**FRs:** FR-4.1–4.6.

**Scope — in:** SES identity + Configuration Set (arch §4.5); EventBridge Scheduler →
`checkin_lambda` (Haiku + RAG personalization per ADR-011; generic-reminder fallback on
failure/budget, FR-4.5, using the profile's `aspirational_goal`); `ses_event_handler` + the
*second* SNS topic (bounce/complaint — kept separate from the alarm topic per §4.5.5) + SQS DLQs
(§4.5.2); **settings PUT** (cadence/pause, FR-4.6 — `UpdateItem` IAM already granted since
slice 1) + minimal settings UI; CHECKINLOG audit items.

**Scope — out:** mobile push (v1.1).

**Key refs:** arch §3.3 + §4.5, ADR-011, FR-4.

**New infra:** SES identity/config set, Scheduler schedule, 2 Lambdas + routes/subscriptions,
SNS topic, SQS DLQs.

**⚠ Decisions:**
- SES sandbox: with one verified recipient (Oche), sandbox is likely sufficient for MVP —
  confirm and document rather than requesting production access.
- Default cadence: weekly per FR-4.2; confirm send day/time.

**Exit criteria:** scheduled run produces a real personalized email in the inbox; pause/cadence
change via settings UI takes effect; a simulated bounce (SES mailbox simulator) lands in
`ses_event_handler` and is visible in logs/audit.

**Completion notes:** _(filled at wrap)_

---

## Slice 9 — Hardening & MVP close ⬜ ⚠

**Goal:** Declare the MVP honestly — verified, documented, and with the loose ends either tied
or explicitly parked.

**Scope — in:** integration test suite against deployed dev + **DynamoDB Local** for
conditional-write semantics (arch §5.6 — the v1.3 changelog explicitly calls for this net after
the SK-prefix bug slipped past string-assertion tests); README refresh (currently describes only
slice 1); FR/NFR coverage audit against requirements v0.4; cost review against the $5 ceiling
with real Bedrock numbers; memory + docs sweep.

**⚠ Decisions:**
- Deploy the prod stack (billing alarms are already prod-gated) vs declare dev-as-MVP for a
  single-user app. Genuine fork — cost vs realism.
- Which parking-lot items graduate to a v1.1 plan.

**Exit criteria:** every FR maps to a verified slice or a documented deferral; integration tests
runnable with one command; this doc's status board all ✅; MVP declared.

**Completion notes:** _(filled at wrap)_

---

## Post-MVP parking lot

Not scheduled; revisit at slice 9 / v1.1 planning.

- **CI/CD** — GitHub Actions, OIDC → AWS, `sam build/deploy` + S3 sync + CloudFront invalidation
  (arch §5.7 defers this explicitly).
- **Requirements §3 deferred list** — voice-mode ingestion (ADR-014), multi-tenant, email/Drive
  output delivery, DOCX export, portfolio-page generator, business-card export, cert-study
  planner, mobile push, interview prep, named-entity verification of generated resumes.
- **Stretch (requirements §7)** — timeline visualization; goal tracking with progress indicators
  (GOAL entity is data-model + ingestion-tag only at MVP).
- **Custom domain** (if slice 4 decides against it).
- **CONVO history growth** — no TTL on chat messages at MVP; fine single-user, revisit before
  multi-tenant.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-10 | Initial roadmap. Slice order and FR-6.1-stays-in-MVP decided with Oche. Slice 1/2a completion notes migrated from CLAUDE.md. |
