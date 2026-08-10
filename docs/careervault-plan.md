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
| 2b | Chat UI + turn idempotency | FR-2.3, FR-2.4 (UI), FR-6.2 | ✅ | [#3](https://github.com/ocheoche-obe/career-vault/pull/3) |
| 3 | Entries dashboard + CRUD completion | FR-3.2, FR-3.3 | ✅ | [#4](https://github.com/ocheoche-obe/career-vault/pull/4) |
| 4 | Frontend hosting (S3 + CloudFront) | NFR (ADR-019) | ✅ | [#20](https://github.com/ocheoche-obe/career-vault/pull/20) |
| 5 | Resume upload bootstrap | ADR-013 ingestion path | ✅ | [#25](https://github.com/ocheoche-obe/career-vault/pull/25) |
| 6a | Resume agent — backend loop | FR-5.1, 5.2 | ✅ | [#27](https://github.com/ocheoche-obe/career-vault/pull/27) |
| 6b | Resume agent — output UI | FR-5.3, 5.4 | ✅ | [#28](https://github.com/ocheoche-obe/career-vault/pull/28) |
| 7 | Chat over your data | FR-6.1 | ✅ | [#29](https://github.com/ocheoche-obe/career-vault/pull/29) |
| 8 | Check-in emails | FR-4 | ✅ | [#31](https://github.com/ocheoche-obe/career-vault/pull/31) |
| 9 | Hardening & MVP close | NFRs, coverage audit | ✅ | [#32](https://github.com/ocheoche-obe/career-vault/pull/32) |
| v1.1-1 | Redesign — audit, tokens, shell, Home | B-001, NFR-6.2, NFR-2.3 | ✅ | [#43](https://github.com/ocheoche-obe/career-vault/pull/43) |
| v1.1-2 | Redesign — Log, Timeline, Import, Details | B-001, NFR-6.2, A3–A11 | ✅ | [#48](https://github.com/ocheoche-obe/career-vault/pull/48) |
| v1.1-3 | Redesign — Résumés + résumé history | B-028, B-036, B-022, B-007, ADR-046 | ✅ | [#50](https://github.com/ocheoche-obe/career-vault/pull/50) |
| v1.1-4 | Voice capture for entry logging | ADR-014, FR-2 | ⏳ | — |

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

**Completion notes:** _(wrapped 2026-07-10, PR #3)_
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

## Slice 3 — Entries dashboard + CRUD completion ✅

**Goal:** The user can see everything they've logged, grouped/chronological, and edit or delete
any entry.

**FRs:** FR-3.2 (dashboard), FR-3.3 (edit/delete).

**Scope — in:** `GET /entries` (Query on `ENTRY#` prefix), `PUT /entries/{id}`,
`DELETE /entries/{id}` in `career_crud` + the Query/UpdateItem/DeleteItem IAM that lands with
them; dashboard UI (grouped by type, chronological within); edit form per entry type; hard delete
with UI confirm (ADR-027); **re-embed on edit only when embedded text changes** (ADR-024 edit-path
note); **semantic duplicate detection at confirm — warn, not block** (ADR-033): a shared-layer
cosine helper, a duplicate check in `POST /entries` returning `409` + `possible_duplicates`, and a
"save anyway" affordance on the proposal card that re-confirms with `acknowledge_duplicate: true`.

**Scope — out:** timeline visualization (stretch, parking lot); goals UI (data-model-only at MVP).

**Key refs:** arch §2 (data model, AP-10 read pattern), §3.1.4/3.1.5 (entry idempotency + status
contract), §4.2.3/4.2.4 (IAM + key isolation), ADR-024 (embed in write path + slice-3 edit note),
ADR-027 (hard delete), ADR-028 (no GSIs — reads are PK Queries), ADR-033 (semantic dedup).

**New infra:** none (routes + IAM on existing Lambda).

**⚠ Decisions:** _(both resolved with Oche 2026-07-12)_
- **Re-embed on edit → resolved:** re-embed synchronously **only when `embedding_input_text`
  changes**, reuse the stored vector otherwise. Captured as an edit-path note on **ADR-024** (not a
  new ADR).
- **Semantic duplicate detection → resolved: include this slice, warn-not-block.** New **ADR-033**:
  confirm-time cosine compare of the new entry's already-computed embedding against existing
  entries (shared-layer helper); `max_similarity >= 0.90` (env-tunable) → `409` with
  `possible_duplicates`, entry not written; client re-confirms with `acknowledge_duplicate: true`
  to save. No new Bedrock cost; builds the retrieval primitive slices 6/7 need.

**Exit criteria:** deployed to dev; list/edit/delete each smoke-tested from the UI; deleted
entry verifiably gone from DynamoDB; edited entry's embedding refreshed only when text changed
(and skipped when it didn't); a re-described accomplishment triggers the `409` "possible
duplicate" warning and "save anyway" writes it.

**Completion notes:** _(wrapped 2026-07-13, PR #4)_
- **Backend:** `career_crud` is now the full entry lifecycle — `GET /entries` (paginated AP-10
  list), `PUT /entries/{id}`, `DELETE /entries/{id}` alongside the original `POST`. New shared
  helpers `query_entries`/`put_entry_update`/`delete_entry` + a reusable `similarity` module
  (cosine + rank, for slices 6/7). IAM widened to `Query` + `DeleteItem`.
- **ADR-033 — semantic dedup (warn, not block):** confirm-time cosine compare of the candidate's
  write-time embedding vs existing entries; `max_similarity ≥ 0.90` (env `DUP_SIMILARITY_THRESHOLD`)
  → `409 {possible_duplicates}`, entry unwritten; client re-confirms with
  `acknowledge_duplicate: true`. Own `entry_id` excluded so §3.1.4 retry-idempotency holds. No new
  Bedrock cost — reuses the write-path embedding.
- **Edit path (ADR-024 note):** an edit is a conditional full-item `PutItem` (`attribute_exists`),
  **not** `UpdateItem` — so no `UpdateItem` grant. Re-embeds only when `embedding_input_text`
  changed; preserves `created_at`, advances `updated_at`. Arch **v1.4** corrects §2.5/§4.2.3 to
  match and flags that AP-10 reads must paginate (embedding-laden items exceed the 1 MB Query page).
- **Frontend:** entries dashboard grouped by type / newest-first, per-type inline edit, hard delete
  with confirm (ADR-027), Chat/Entries nav; ProposalCard "possible duplicate — save anyway"; shared
  `EntryFields` + `entryFields` helpers (DRY across propose + edit).
- **Verified:** 139 unit tests green (39 new). Deployed to dev; 12 end-to-end smoke checks against
  the real Lambda + DynamoDB + Titan passed (create / list / 409-dup at 0.96 similarity /
  acknowledge / edit-reuses-vector / edit-refreshes-vector / delete-gone / 404). UI flows
  (list/edit/delete/dup warning) smoke-tested from the browser by Oche; deleted entry confirmed
  physically gone from DynamoDB. Security review clean.
- **Bug found & fixed in UI testing:** the dashboard edit card stayed stuck on "Saving" after a
  successful PUT (local state never returned to view; stable React key kept the instance) — fixed;
  Refresh gained "Refreshing…" feedback. No frontend test framework exists yet, so this class of
  UI-state bug is uncaught → routed to **slice 9** (Vitest + RTL).
- **Evaluation:** all exit criteria met; no Bedrock $ beyond the existing Titan write-path embed
  (dup-check reuses it, adds only a Query). One improvement → frontend tests at slice 9.
- **Process addenda (this wrap):** `/security-review` is now a blocking wrap-slice gate; added
  GitHub Actions **CodeQL** + **CI** + **Dependabot**; a `SessionStart` AWS-account guard for the
  multi-account SSO safety concern; start-slice step 3 hardened to a hard account assertion.

---

## Slice 4 — Frontend hosting ✅

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

**⚠ Decisions (resolved):**
- Default `*.cloudfront.net` domain vs custom domain (+ Route 53 + ACM cert). **Resolved: default
  domain** — custom domain deferred to v1.x (ADR-019 amendment). Zero recurring cost, HTTPS out of
  the box, and the app client auto-allows the distribution's own domain.

**Exit criteria:** sign in → chat → confirm entry → dashboard, all from the CloudFront URL on a
device that isn't the dev machine. **✅ Met** — verified from a laptop and a phone (2026-07-16).

**Completion notes:** _(wrapped 2026-07-16, [PR #20](https://github.com/ocheoche-obe/career-vault/pull/20))_
- **Shipped:** private S3 site bucket (`careervault-web-${Env}-${AccountId}`, all public access
  blocked, SSE-S3) fronted by a CloudFront distribution (PriceClass_100, HTTP/2+3, default
  `*.cloudfront.net` cert) via **Origin Access Control** — bucket policy trusts only the
  distribution's `SourceArn`. SPA routing via CloudFront `CustomErrorResponses` (S3 403/404 →
  `/index.html` 200). Cognito app client now allowlists both `localhost:5173` and the CloudFront
  origin for callback/logout (distribution domain wired via `!GetAtt` within the stack). Three new
  stack Outputs: `SiteBucketName`, `CloudFrontDistributionId`, `CloudFrontUrl`.
- **Deployed & verified (dev):** `d2qzo95316tvzl.cloudfront.net`. Smoke-tested root (200), SPA
  deep-link fallback (`/entries` → 200), OAC asset fetch from the private bucket, CORS preflight
  (`Access-Control-Allow-Origin: *`), and the Cognito redirect allowlist. Full human exit-criterion
  path (sign in → chat → confirm → dashboard) confirmed cross-device.
- **Decisions forced:** ADR-019 amended (default domain, custom domain → v1.x); **new ADR-034**
  (wildcard CORS — safe for this non-credentialed Bearer-token API; must be revisited if
  cookie/session auth is ever introduced). Security review: clean (OAC least-privilege confirmed;
  wildcard CORS reviewed and cleared for this threat model).
- **Tooling:** `make deploy-frontend` (regenerate env → `npm ci && npm run build` → `s3 sync` →
  CloudFront invalidation) + `make deploy-all`; `write-frontend-env.sh` now emits
  `.env.production.local` (CloudFront redirect for builds) alongside `.env.local` (localhost for
  dev), leaning on Vite's env precedence.
- **Cost:** unchanged in practice — MTD ~$0.05; CloudFront/S3 at single-user scale is cents. No
  Bedrock added this slice.
- **Also landed this branch (pre-slice-4 commit):** Dependabot cadence fix — grouped/monthly
  `dependabot.yml` + the transferred `dependabot-triage` skill, after the first 15-PR wave was
  triaged by hand (12 merged; see the parking lot for the two workflow-scope PRs + TS 7).
- **One thing to improve:** the frontend CI gate is typecheck+build+lint only — no runtime test, so
  "green CI" doesn't prove the app renders. The transferred skill flags this; a minimal smoke test
  (render app root, assert landing state) is worth adding before auto-merging any green frontend
  Dependabot PR. Tracked in the parking lot.

**Threads left open (for the next session / parking lot):**
- Dependabot PRs **#6 (checkout v4→7)** and **#8 (setup-node v4→7)** — green and mergeable but touch
  `.github/workflows/`; the `gh` token lacks the `workflow` scope. Merge via web UI or
  `gh auth refresh -s workflow`.
- Dependabot **#11 (typescript 6→7)** — parked as unmergeable-solo (typescript-eslint peer range);
  the new `lint-toolchain` group should let it land atomically next cadence.

---

## Slice 5 — Resume upload bootstrap ✅

**Goal:** A user with an existing resume doesn't start from zero — upload a PDF/DOCX and have it
parsed into confirmable entries.

**FRs:** ADR-013 (upload supported in MVP); feeds FR-2.3's confirm-before-persist.

**Scope — in:** S3 data bucket `careervault-data-${Environment}-${AccountId}` with `uploads/` +
`resumes/` prefixes and SSE-S3 (arch §4.4.3); **presigned S3 PUT** upload (file goes straight to
`uploads/${user_id}/…`, never through API Gateway/Lambda); `resume_upload_parser` Lambda as a
**parse-only** transform — reads the object, one Claude Haiku tool-use pass → entry *candidates*
(no vectors, no write), returned in a **synchronous** parse-endpoint response; **select-all review
table** UI where the user unchecks junk / edits and saves the kept rows through the existing
`POST /entries` (which embeds via Titan at confirm, so ADR-033 dedup + §3.1.4 idempotency apply for
free). All per **ADR-035**.

**Scope — out:** DOCX *export* (v1.1); the `resumes/` prefix is provisioned here but first
written by slice 6; async (S3-event + poll) parse — deferred behind ADR-035's measured-latency
trigger; a bulk-write endpoint (client makes N `POST /entries` calls).

**Key refs:** **ADR-035** (the whole flow), ADR-013, ADR-024 (+ its slice-5 parser-correction note),
ADR-031 (Haiku IAM precedent for the parser), ADR-033 (§3.1.4 dedup/idempotency the confirm reuses);
arch §4.4 (S3 design), §4.6.2 + §4.7.4 (both carry v1.6 corrections — parser does not embed).

**New infra:** S3 data bucket + prefix-scoped IAM; **`resume_upload_parser` Lambda owning both
routes** — presigned-URL issuance (`s3:PutObject` on `uploads/${user_id}/*`) and the synchronous
parse call (`s3:GetObject` on the same prefix + Haiku IAM per ADR-031). **No** Titan, **no**
DDB-write grant on this Lambda.

**⚠ Decisions:** _(all three resolved with Oche 2026-07-21 → **ADR-035**)_
- **Embedding site → resolved:** parser is **parse-only**; embedding stays at the single confirm
  site (`POST /entries`). Corrects ADR-024 + arch §4.6.2/§4.7.4 (which had the parser embedding).
- **Parse job shape → resolved:** presigned PUT + **synchronous** parse call. Start sync, measure
  real parse latency (exit criterion); escalate to async only if it nears the API GW 29 s ceiling.
- **Bulk-confirm UX → resolved:** **select-all review table** (built for the 5–20 candidates a
  resume yields), not the one-by-one 2b card.

**Exit criteria:** real multi-page resume uploaded from the UI → parsed → select-all review →
confirmed → entries visible on the dashboard with embeddings; a junk/duplicate candidate exercises
the 409 "possible duplicate" path on save; **measured parse latency noted** (drives the sync-vs-async
trigger); budget check after (first Bedrock slice since slice 3 — Haiku parse + Titan-per-confirm).

**Completion notes:** _(wrapped 2026-07-21, [PR #25](https://github.com/ocheoche-obe/career-vault/pull/25))_
- **Shipped (all per ADR-035):** private S3 data bucket `careervault-data-${Env}-${AccountId}`
  (SSE-S3, all public access blocked, bucket CORS scoped to the browser's presigned `PUT`, 1-day
  lifecycle on `uploads/`); `resume_upload_parser` Lambda owning **both** routes —
  `POST /uploads/presign` (user-scoped presigned PUT URL) and `POST /uploads/parse` (one Haiku
  `extract_entries` pass → validated candidates). **Parse-only:** no Titan grant, no DDB grant;
  embedding + persistence stay at `career_crud`'s `POST /entries` (the single embedding site), so
  ADR-033 dedup and §3.1.4 idempotency cover uploaded entries for free.
- **Shared layer:** `build_extract_tool_config()` reuses the exact `propose_entry` per-entry schema,
  so a résumé candidate and a chat candidate validate against the same discriminated union.
- **Text extraction is genuinely pure-Python (no Docker):** pypdf for PDF; **stdlib
  `zipfile`+`xml.etree` for DOCX** — deliberately *not* python-docx, which drags in the compiled
  `lxml` wheel (`sam build` on macOS bundled the Darwin build; it would fail on Lambda arm64 Linux).
  Caught during the first `sam build` inspection; swapped before deploy.
- **Frontend:** presign→PUT→parse client, an Upload view, and a **select-all review table** (per-row
  edit/uncheck, "Save N", per-row 409 "save anyway") wired to the existing `POST /entries`. New
  **Upload résumé** nav tab.
- **Robustness finding (from live testing) — candidate salvage:** the permissive union tool schema
  invites Haiku to (a) attach `impact_metric` (a MILESTONE field) to a JOB whose bullets quantify
  impact and (b) omit the required `content` on terse cert/award lines. Chat recovers via its
  retry loop (§3.1.6); the bulk parser has none, so it prunes stray out-of-type fields and backfills
  a missing `content` from `title`, then revalidates once — turning "drop the whole entry" into
  "keep it." Before this, 2 of 7 entries dropped per run (and *which* two varied — Bedrock isn't
  fully deterministic at temp 0); after, a consistent **7/7, 0 dropped** across runs.
- **Verified:** 162 unit tests green (22 new). Deployed to dev; backend smoke against real
  S3 + Haiku + Titan + DynamoDB: presign 200 → S3 PUT 200 → parse 200 (7/7 candidates, **no
  embeddings**, each with a minted `entry_id`) → confirm **201 (embedded at confirm) → 200 idempotent
  → 409 possible-duplicate (1.0 match) → delete 200**. API Gateway routes 401 unauthenticated,
  preflight 200. UI exit-criterion path confirmed by Oche (upload → itemized review → edit → save →
  dashboard). Security review clean; advisory code review surfaced 3 findings (size-guard before
  read, "Save N" count vs duplicate rows, CORS GET/HEAD unused) — **all fixed in-slice** and
  re-verified.
- **Latency & the sync-vs-async trigger:** measured Haiku parse **~3.4–4.0 s** for a one-page
  résumé — far under API Gateway's 29 s integration timeout, so ADR-035's synchronous choice holds
  and the async-escalation trigger stays untriggered.
- **Cost / budget:** MTD **~$0.09**, unchanged through all testing — a Haiku parse is ~2.5K tokens
  (~$0.0004) and confirm-time Titan embeds are fractions of a cent. Far under the $5 ceiling.
- **Evaluation:** all exit criteria met. One limitation surfaced by Oche and **routed to the backlog
  (B-003)** rather than fixed here: ADR-033 semantic dedup (cosine ≥ 0.90) misses *same credential,
  different wording* — two AZ-900 certs measured 0.86 and both saved. It's a cross-cutting ADR-033
  precision question (affects the chat path too), so it deserves its own pass, not a slice-5 bolt-on.

---

## Slice 6 — Resume agent ⚠→ resolved (split 6a / 6b)

**Goal:** The payoff feature — paste a job description, get a tailored resume (text/HTML/PDF)
built from your logged history. Largest slice; **split into 6a (backend loop) + 6b (output UI)**
at slice start (2026-07-21) per the appetite decision.

**FRs:** FR-5.1–5.4.

**Scope — in (whole slice):** `resume_agent` Lambda with the six-phase bounded loop (arch §3.2:
analyze → retrieve → draft → critique → revise → finalize, explicit termination, action/progress
tracking, HITL at input/output gates only); Sonnet via inference profile; in-Lambda vector
retrieval over entry embeddings (ADR-016); `careervault-weasyprint` layer (ADR-023,
Docker/makefile build); RESUMERUN trace items (TTL 30 days); PDF to `resumes/` prefix; JD-input +
format-select + download UI (FR-5.3/5.4).

**Scope — out:** email/Drive delivery (v1.1 — in-app download only per ADR-015); named-entity
verification pass (v1.1).

**Key refs:** arch §3.2 (the whole flow), ADR-009/-010/-015/-016/-017/-018/-023; **ADR-031 is the
IAM precedent**, **ADR-036** pins the concrete Sonnet model + cost controls for this slice.

**New infra:** `resume_agent` Lambda + route, WeasyPrint layer, Bedrock Sonnet IAM.

**⚠ Decisions:** _(resolved with Oche 2026-07-21 → **ADR-036**, plus two forced live during 6a)_
- **Sonnet model + inference profile → resolved:** inference-profile-only as ADR-031 predicted;
  Phase 1 `extract_requirements` stays on Haiku. **Chosen Sonnet 5**, but the first deploy smoke
  test hit `AccessDenied“sonnet-5 not available for this account”` — **Sonnet 5 is not grantable on
  this account** (`agreement: NOT_AVAILABLE`, account-tier gated), so 6a runs on **Sonnet 4-6** (the
  newest accessible Sonnet; same 3-region fan-out, IAM unchanged). ADR-036 live-access correction;
  flip back if access lands.
- **Cost controls pinned (ADR-036):** token ceiling **150K (~$1/run)** (amends §3.2.4's 500K);
  `wall_clock=240s`. Iteration/revision caps **tuned from measured runs** to
  `max_iterations=8`, `max_revisions=1` (85K→70K tokens, $0.39→$0.31, 230s→176s). **Reserved
  concurrency = 2** (revised from 1 by **ADR-037** — the async self-invoke needs room for a worker
  + a fresh POST/GET).
- **Transport → new decision (ADR-037):** a run is 40–120s, past API Gateway's 29s ceiling, so
  generation is an **async job** — `POST /resumes/generate` returns `202 {run_id}` + async worker;
  `GET /resumes/{run_id}` polls. Corrects arch §3.2.1's synchronous depiction.
- **6a/6b split → resolved: split into two PRs.** 6a = backend loop, API-testable; 6b = output UI.

---

### Slice 6a — Resume agent backend loop ✅ (PR #27)

**Goal:** `POST /resumes/generate` runs the full six-phase agent server-side and returns
`{html_url, pdf_url, run_id}` — verifiable end-to-end against the real API before any UI exists.

**FRs:** FR-5.1 (JD/target intake), FR-5.2 (agentic generation).

**Scope — in:** `resume_agent` Lambda + `POST /resumes/generate` route (Cognito authorizer);
the six-phase loop (arch §3.2) — Phase 1 Haiku `extract_requirements`; Phase 2 Sonnet 5 bounded
retrieval loop over the four tools (`search_entries`/`get_entry`/`list_skills`/`retrieval_done`)
reusing the slice-3 `similarity` helper + Titan query embedding; Phases 3–5 draft/critique/revise
with Pydantic-validated `submit_resume`/`submit_critique`; Phase 6 finalize — Jinja2 → HTML →
WeasyPrint → PDF to `resumes/<user_id>/<run_id>/`, presigned URLs (1h TTL). Termination/progress
mechanisms (§3.2.4–3.2.6) with ADR-036 constants; RESUMERUN trace item (TTL 30d, §3.2.5);
`careervault-weasyprint` layer (ADR-023, Docker/makefile); Bedrock Sonnet IAM (ADR-036) + S3
`PutObject` on the resume prefix; reserved concurrency 1.

**Scope — out:** all UI (→ 6b); email/Drive delivery (v1.1); named-entity verification (v1.1).

**New infra:** `resume_agent` Lambda + route, WeasyPrint layer, Bedrock Sonnet IAM, S3 resume-prefix
write grant, reserved-concurrency cap.

**Exit criteria:** real JD → `POST /resumes/generate` completes within the bounded loop against
real entries → PDF renders and *looks like a resume* (fetched from the presigned URL); RESUMERUN
trace inspectable in DynamoDB; **cost-per-run + token-per-run measured and noted** (validates the
150K ceiling and the $5 posture); WeasyPrint layer builds and loads on Lambda arm64; empty-history
short-circuit (§3.2.6 checkpoint) returns the "add entries first" message. Budget check after.

**Completion notes:** _(wrapped 2026-07-21, [PR #27](https://github.com/ocheoche-obe/career-vault/pull/27))_
- **Shipped:** `resume_agent` Lambda running the full six-phase loop — Phase 1 Haiku
  `extract_requirements`; Phase 2 Sonnet bounded retrieval loop (`search_entries` reusing the
  slice-3 `similarity` helper + a Titan query embed, `get_entry`, `list_skills`, `retrieval_done`);
  Phase 3 draft + Phase 4 critique + Phase 5 revise (Pydantic-gated `submit_resume`/`submit_critique`
  with a single validation retry); Phase 6 deterministic finalize (Jinja2 → HTML → WeasyPrint → PDF
  to `resumes/<user_id>/<run_id>/`). Termination + progress mechanisms (§3.2.4–3.2.6): token/wall-clock
  guards, dup-call nudge, critique stagnation, phase checkpoints. Shared-layer additions:
  `pydantic_models/resume.py` (models + the four tool configs) and RESUMERUN ddb helpers; the agent
  brain (`agent.py`) is invocation-agnostic (a pure function of its inputs).
- **ADR-037 — async job (new decision, forced live):** a run is 40–120s, past API Gateway's 29s
  ceiling, so the arch's synchronous §3.2.1 depiction doesn't hold. One Lambda, three roles:
  `POST /resumes/generate` writes a `pending` RESUMERUN item + self-invokes asynchronously + returns
  `202 {run_id}`; the async worker runs the agent, renders, uploads, and **overwrites** the item to
  `completed`/`failed`; `GET /resumes/{run_id}` polls and presigns fresh 1h URLs on read. Reserved
  concurrency bumped 1→2 (worker + a fresh POST/GET). RESUMERUN doubles as trace (§3.2.5) + job
  record; table gained a TTL (`expires_at`, 30 days).
- **ADR-036 live-access correction — Sonnet 5 ungrantable:** the first smoke run failed at the
  Phase-2 Sonnet call with `AccessDeniedException: anthropic.claude-sonnet-5 is not available for
  this account`. Not IAM (Phase 1 Haiku succeeded) and not the ordinary Model-access toggle —
  `get-foundation-model-availability` shows `agreement: NOT_AVAILABLE` (account-tier gated). Probed
  live: Sonnet **4-6** and 4-5 are accessible, 5 is denied. Switched to **Sonnet 4-6** (newest
  accessible; identical 3-region fan-out, IAM unchanged) — a two-line param flip, per ADR-036's own
  "model swap is one line." Saved to memory alongside the Haiku use-case-form gotcha.
- **Two live bugs the smoke test caught:** (1) `ReadTimeoutError` (a `BotoCoreError`, *not*
  `ClientError`) on long Sonnet draft calls slipped past `_invoke_with_retry` uncaught → the worker
  crashed *without* finalizing → item stuck `pending` (and async-retried, doubling spend). Fixed:
  the shared `bedrock_client` now treats socket timeouts as transient (retry → then a `BedrockError`
  callers already handle), and the agent's Bedrock read timeout is raised to 120s for long
  generations. (2) The WeasyPrint layer needed the Pango closure + fonts + `FONTCONFIG_PATH`/
  `XDG_CACHE_HOME` wiring to render on Lambda arm64 — verified by a real PDF.
- **Verified (deployed to dev):** 221 unit tests green (59 new). Smoke against real API-shaped
  events → Haiku + Sonnet 4-6 + Titan + DynamoDB + S3 + WeasyPrint: `202 pending` → async worker →
  `GET` polls to `completed` → **valid PDF** (PDF-1.7, 24KB) fetched from the presigned URL, a real,
  tailored, truthful résumé tracing to the user's 13 entries; RESUMERUN trace inspected in DynamoDB
  (status/agent_status/trace/keys/cost/tokens, `expires_at` set). WeasyPrint layer built via
  `sam build --use-container` (30 native libs, aarch64 cffi). Security review clean (the async
  worker's trusted `user_id` is sound — the worker path is unreachable externally and its only
  invoker extracts identity from the JWT first).
- **Evaluation vs exit criteria — all met.** Cost/latency measured and **tuned**: first run
  85K tokens / **$0.39** / ~230s → after tuning `max_iterations 15→8`, `max_revisions 2→1`,
  **70K tokens / $0.31 / ~176s** (under the 150K ceiling and 240s budget; ~16 runs/month within $5).
  MTD spend **$0.22**, far under $5. **One thing to improve:** the retrieval loop re-sends its
  growing message history each iteration — the dominant per-run cost; context compaction is a bigger
  change → **backlog B-004**. Also routed: shared `_MAX_OUTPUT_TOKENS` per-phase cap → **B-005**.
- **Process:** added a `PostToolUse`/`PostToolUseFailure` hook (`.claude/check-tests-green.sh`) that
  blocks any test run that isn't clearly green, and hardened `wrap-slice` step 1 to make the
  green-suite run an explicit blocking gate (Oche's request — enforce that tests are actually run and
  pass at wrap).

---

### Slice 6b — Resume agent output UI ✅

**Goal:** JD-input + HTML preview + format-select + download, wired to `POST /resumes/generate`.

**FRs:** FR-5.3 (HTML preview + PDF download), FR-5.4 (regenerate).

**Scope — in:** JD/target input view; **the async poll flow (ADR-037)** — `POST /resumes/generate`
→ `202 {run_id}`, then poll `GET /resumes/{run_id}` until `completed`/`failed`, with a
"generating…" progress state across the ~3-minute run; render the returned HTML preview; Download
PDF (presigned URL) + Regenerate (fresh run); friendly error states for the `failed` `detail`
messages the backend already returns; nav tab. Plus the three small backend/infra items the UI
forces (decisions 2 and 4 below): a `Content-Disposition` on the PDF presign, and the `resumes/`
lifecycle rule.

**Scope — out:** email/Drive delivery (v1.1); named-entity verification (v1.1); **general UI polish
(backlog B-001)** — 6b matches the existing visual language rather than being the design pass.

**Key refs:** **ADR-037** (the 202 + poll contract), the `resume_agent` handler's response shapes
(202 pending / status poll), arch §3.2.1 (with the ADR-037 transport correction), **ADR-015 as
amended 2026-07-27** (30-day `resumes/` retention), ADR-034 (wildcard CORS).

**⚠ Decisions:** _(resolved with Oche 2026-07-27 at slice start, from reading the deployed 6a code)_
- **1. HTML preview transport → `<iframe src={html_url}>`, sandboxed.** The data bucket's CORS
  allows **PUT only** (slice 5 only ever needed the presigned upload), so `fetch(html_url)` +
  `srcdoc` would require a new GET rule. An iframe `src` is a *navigation*, not a fetch — CORS
  doesn't apply — so the preview works against the bucket exactly as it is deployed. No infra
  change. The WeasyPrint-oriented HTML is a complete document, which suits an iframe better than
  inlining anyway.
- **2. PDF presign gains `ResponseContentDisposition` → the download actually downloads.** The 6a
  presign sets no disposition, and HTML's `download` attribute is **ignored for cross-origin URLs**,
  so a "Download PDF" link would open the PDF in a tab instead of saving it. Fixed in the backend
  (one presign parameter: `attachment; filename="resume-<run_id>.pdf"`), not worked around in the UI.
- **3. `run_id` persists in `sessionStorage` for the duration of a run.** A run costs ~$0.31 and
  ~176s server-side; if the id lived only in component state, a reload or tab switch would orphan a
  run that is still burning money and could never be collected. Stashing it means a reload resumes
  polling the same run. Cleared on terminal status.
- **4. `resumes/` lifecycle → flat 30 days, and ADR-015 amended.** The slice-5 template comment
  promised "resumes/ (slice 6) will carry its own ADR-015 lifecycle later" and 6a never added it, so
  generated PDFs currently live forever. Writing the rule surfaced that **ADR-015's original wording
  is not implementable** ("keep the most recent generation indefinitely, 7-day TTL for older" — S3
  lifecycle has no "except the newest" predicate) and that 7 days would leave 30-day RESUMERUN items
  presigning URLs to deleted objects. Amended to a flat 30 days matching the RESUMERUN TTL — see the
  ADR-015 amendment for the full reasoning.

**Exit criteria:** paste a JD from the deployed frontend → "generating…" → preview renders → PDF
downloads and looks like a resume → regenerate produces a fresh run; a failed run surfaces the
friendly message; a mid-run browser reload resumes polling the same `run_id` rather than orphaning
it; the `resumes/` lifecycle rule is live on the deployed bucket. Frontend-render smoke
consideration folded into slice 9.

**Completion notes:** _(wrapped 2026-07-28, [PR #28](https://github.com/ocheoche-obe/career-vault/pull/28))_
- **Shipped:** the `Resume` view (`frontend/src/resume/`) — JD/target input, the ADR-037 async poll
  flow (`POST` → `202 {run_id}` → `GET` every 3s to a terminal status), an elapsed-time progress
  state across the ~3-minute run, the HTML preview, Download PDF, Regenerate, and New target; plus a
  `Résumé` nav tab and the typed client (`startResumeRun`/`getResumeRun`) in `lib/api.ts`. Failure
  states render the backend's own message — the seven `detail` codes are mapped to sentences server-side
  already, so there is no second copy of that vocabulary in the UI.

- **The four ⚠ decisions all came from reading the deployed 6a code rather than the roadmap**, which
  is the reusable lesson: the plan's 6b section was written before 6a existed, so it assumed a UI
  slice was pure frontend. Two of the four turned out to be backend/infra work.
  1. **iframe `src`, not `fetch` + `srcdoc`** — the data bucket's CORS is PUT-only (slice 5 only
     needed the presigned upload). An iframe navigation isn't subject to CORS, so the preview works
     against the bucket exactly as deployed, no infra change. It is also the safer of the two:
     `srcdoc` would render agent-generated HTML in the app's own origin.
  2. **PDF presign gained `ResponseContentDisposition`** — HTML's `download` attribute is *ignored
     cross-origin*, so without a disposition baked into the signature "Download PDF" opens a tab
     instead of saving. Fixed in the backend (`_presign_get(download_as=…)`), not papered over in the
     UI. Verified on the wire: `Content-Disposition: attachment; filename="resume-<run_id>.pdf"`.
  3. **`run_id` in `sessionStorage`** — a run costs ~$0.31 and keeps going server-side regardless of
     who is watching, so component-only state would orphan a paid run on any reload. Confirmed in the
     smoke: reloading mid-run re-attaches and keeps counting.
  4. **`resumes/` lifecycle → flat 30 days + ADR-015 amended** — writing the rule the slice-5
     template had promised surfaced that **ADR-015's original retention rule is not implementable**:
     S3 lifecycle filters on prefix/tag/age with no "except the newest object" predicate, and 7 days
     would have left 30-day RESUMERUN items presigning URLs to deleted objects. Amended to match the
     trace TTL so a run's record and its artifacts die together.
- **Doc correction (arch v1.9):** §3.2.2 still claimed "under 90 seconds for a typical run." Measured
  reality is **~176s**. The estimate predates having six sequential Bedrock round-trips to measure,
  and it is load-bearing, not cosmetic — 176s is ~6× API Gateway's 29s ceiling (the reason ADR-037
  made generation async) and it is what this slice's UI is dimensioned around (3s poll, 330s
  give-up just past the 300s Lambda timeout).
- **Verified:** 222 unit tests green (one new: the PDF presigns with a disposition, the HTML without);
  frontend lint + build clean; deployed to dev; lifecycle rule confirmed live on the bucket via
  `get-bucket-lifecycle-configuration`; presign disposition confirmed by fetching a real completed
  run's URLs (PDF-1.7, 24KB, `attachment` header; HTML inline `text/html`). **Oche's UI smoke on the
  CloudFront URL passed every exit criterion** — 2 runs against 2 different JDs, iframe preview,
  a real PDF download, mid-run reload retaining the run, Regenerate producing a fresh run, New target
  accepting a fresh JD.
- **Evaluation vs exit criteria — all met.** Measured run: **82,867 tokens / 13 entries used /
  critique `REVISE`**. That is above 6a's tuned 70K baseline because this run actually spent its one
  allowed revision (`REVISE`, not `PASS`) — so it is the realistic *upper* end of a normal run, still
  comfortably under the 150K-token / ~$1 ADR-036 ceiling. **Cost figure corrected post-hoc:** the UI
  displayed **$0.35**, but that estimate used the headline on-demand Sonnet rate; every model here is
  invoked through a `us.` cross-region inference profile, which bills ~10% higher (Regional CRIS
  $3.30/$16.50, not $3/$15). True cost is **~$0.39**, and 6a's tuned baseline is **~$0.34, not
  $0.31**. Rates fixed in `agent.py`; see the ADR-036 pricing correction. MTD spend at wrap: **$1.73**
  reported, though Cost Explorer had not yet ingested the day's runs (≈$2.4 real) — well under $5. **One thing to improve:**
  the run-metadata row (entries/critique/tokens/cost) is developer-facing and the elapsed timer
  vanishes exactly when you'd want to compare runs — both routed to **B-006/B-007** rather than fixed
  in-slice, since Oche explicitly wants the metadata visible while the agent is still being evaluated.
- **Also fixed in-slice (not in the plan):** Generate/Regenerate weren't disabled during the POST, so
  a double-click would have started two runs at ~$0.31 each *and* overwritten the first `run_id` in
  storage — orphaning a paid run. Both buttons now guard on a `starting` flag.
- **Security review clean.** The one item worth scrutiny — user-controlled `run_id` interpolated into
  the `Content-Disposition` filename — is not exploitable: the presign is only reached after the
  `run_id` matches a stored item, and RESUMERUN items only exist under server-minted ULIDs. Noted for
  the future: the guardrail is existence-checking, not format-validation. The new preview is the
  first time agent-generated HTML renders in a browser, and it is defended three ways — Jinja2
  `autoescape=True`, `sandbox=""` (no `allow-scripts`), and a cross-origin frame.

---

## Slice 7 — Chat over your data ✅

**Goal:** Chat stops being ingestion-only — the user can *ask* things ("what did I do in 2025?",
"which entries mention Python?", "help me phrase this milestone") and get grounded answers.

**FRs:** FR-6.1 (committed MVP requirement — decided 2026-07-10 to keep in MVP as its own slice).

**Scope — in:** extend `chat_lambda` so a message routes to either entry-parsing (existing two
tools) or Q&A over the user's history — retrieval reusing slice 6's vector-similarity helpers
(ADR-016) + free-text grounded answers; UI unchanged apart from rendering answer turns.

**Scope — out:** anything that writes on the user's behalf beyond the existing propose→confirm
flow.

**Key refs:** arch §3.1 (current parse turn), §3.1.2 (two-tool pattern), §4.2.3 (chat isolation),
ADR-016 (retrieval), **ADR-038** (routing), requirements FR-6.1.

**New infra:** none beyond `chat_lambda` IAM widening to read `ENTRY#` items — this weakens the
current "chat can only touch CONVO#" isolation (§4.2.3); read-only, and stated plainly in ADR-038.
§4.2.3 needs amending at wrap, not quietly outgrowing.

**⚠ Decisions — resolved 2026-07-28 → ADR-038:**
- **Routing design:** ✅ **third tool** (`answer_question`) with `toolChoice=any` **retained**.
  It's a *control-flow* tool (the §3.2 `retrieval_done`/`submit_resume` pattern): it signals "this
  turn is a question" and returns a retrieval query. A Q&A turn is then route (Haiku) →
  deterministic Titan embed + `rank_by_similarity` top-k (no model) → grounded synthesis (Haiku).
  Rejected `toolChoice=auto` (ungrounded answers, and it surrenders the forced-structured-output
  guarantee 2b ingestion relies on) and a `search_entries` agentic loop (unbounded cost; breaks
  `_to_converse_messages`, which flattens tool turns to text precisely because Converse requires
  `toolUse`↔`toolResult` pairing).
- **Framing correction:** "a question can't accidentally create an entry" is a **defect in the
  existing path**, not a hazard introduced by this slice — today a question has no tool that fits
  it, so `toolChoice=any` forces Haiku to bend it into `ask_clarification` or `propose_entry`.
  Routing fixes it.

- **Injection controls (added to scope 2026-07-28):** the `ENTRY#` widening ships *with* four
  API-layer controls, not just an ADR note — model-free retrieval, **no `toolConfig` on the
  synthesis call**, privilege separation across the two calls, and answers rendered as text (never
  HTML/markdown, tested). Prompt-level delimiting is defense in depth only. Threat framing: the risk
  is **indirect** injection via slice 5's résumé upload (poisoned entry content retrieved into a
  prompt), not an outsider reading the user's data.
- **Aggregates (added to scope 2026-07-28):** slice 7 carries the **corpus census** (counts by
  `entry_type` from the already-loaded corpus, ~50 tokens — makes "how many certs do I have?"
  correct now) and a **reserved `intent` field** (`lookup` | `aggregate`) on `answer_question`, of
  which only `lookup` is implemented. Full hybrid retrieval (structured filter branch) is v1.1 →
  backlog. Rationale: `query_entries` already reads the whole corpus, so top-k is a compression we
  choose, not a ceiling — and top-k biases a count toward k, i.e. confidently wrong.

**Backlog groomed:** B-008 (P1, résumé has no identity header — take name/email from JWT claims)
consciously **left out** — it's `resume_agent` work with its own smoke test, better as a small
standalone PR. B-010 (Sonnet 5) re-probed 2026-07-28: still denied, but the error changed from
agreement-pending to `anthropic.claude-sonnet-5 is not available for this account` — reads as a hard
account entitlement, not propagation lag; stop treating it as "wait longer." B-003/B-004/B-006/
B-007/B-009 left (not slice-7 shaped).

**Exit criteria:** ✅ all met.

| Criterion | Verified by |
|---|---|
| Ingestion still passes its 2b smoke tests unchanged | Live: "I passed the AWS Solutions Architect Professional exam on 2026-07-15…" → `parse_candidate` CERT with a minted ULID. All pre-existing chat unit tests untouched and green. |
| Questions about seeded history get correct grounded answers | Live, against the real 13-entry dev corpus: counts, skill lookup, and education questions all answered correctly and traceably (below). |
| A question can't accidentally create an entry | Live: entry count 13 before and 13 after four question turns. Unit: `test_a_question_never_writes_an_entry` asserts every write carries a `CONVO#` SK. |
| `chat_lambda`'s new DDB grant is read-only and `ENTRY#`-scoped | **Criterion was based on a false premise — see the IAM correction below.** The real property (chat cannot *write* an entry) holds and is now test-pinned. |

**Completion notes**

**What shipped.** `answer_question` as a third *control-flow* tool with `toolChoice=any` retained
(ADR-038). A Q&A turn is route (Haiku) → Titan embed → `rank_by_similarity` top-k in-Lambda →
synthesis (Haiku, **no tools**). Ingestion turns are byte-for-byte the same shape as slice 2b. New
`backend/functions/chat/qa.py` holds the census + grounding-block construction as pure functions;
`Chat.tsx` renders answer turns plus a quiet provenance list of the entries that grounded them.

**Measured (live dev, real corpus of 13 entries — 7 JOB, 4 CERT, 2 EDUCATION):**

| Question | Routed to | Result |
|---|---|---|
| "how many certifications do I have?" | `answer_question` (intent `aggregate`) | **"You have 4 certifications"** — correct |
| "which of my entries involve Python or data engineering?" | `answer_question` (`lookup`) | Correct; cited the Columbia internship, the GCP cert, both EY roles |
| "what did I study at university?" | `answer_question` (`lookup`) | Correct; both degrees with GPA and honors |
| "I passed the AWS SAP exam on 2026-07-15…" | `propose_entry` | CERT candidate — ingestion unregressed |
| "I worked at Acme" | `ask_clarification` | "What was your job title at Acme, and when…" — unregressed |

**Cost: ~$0.006 per Q&A turn** (~$0.03 for the whole smoke run; 22.2K input / 960 output tokens
across ~10 Haiku calls at the Regional CRIS rate). Roughly 800 Q&A turns/month inside the $5
ceiling — unlike slice 6, this slice is not a cost story. MTD spend at slice start was $1.73.

**The census earned its keep on the first live run.** Top-k handed the model 8 entries, only 4 of
which were certs. Had it counted what was in front of it, it would have answered 8. It answered 4.
That is the exact predicted failure mode — top-k biases a count toward k — caught by design rather
than by luck. Unprompted bonus: it also flagged the two AZ-900 entries as likely duplicates,
which is **B-003 confirming itself from real data**.

**Correction — the IAM widening this slice was supposed to make does not exist.** The plan, the
first draft of ADR-038, and one exit criterion all said `chat_lambda` would *gain* `dynamodb:Query`
on `ENTRY#`. It already had it: the policy grants `Query` on the table ARN **unconditionally**, and
always has, so those reads were permitted throughout slices 2–6. Nothing in the role changed except
one new `bedrock:InvokeModel` on Titan.

That is not a sloppy original policy — **IAM cannot express the restriction.** All of a user's
items share one partition key, the isolation wanted is by *sort-key prefix*, and
`dynamodb:LeadingKeys` scopes the partition key only (§4.2.1). So §4.2.3's "chat can only touch
`CONVO#`" was never an IAM property; it was always application code, enforced by which
`ddb_helpers` a handler calls. Recorded as the slice's most portable lesson: **a least-privilege
boundary IAM cannot express is a code invariant wearing an IAM costume** — worth keeping, but it
must be documented and tested as code, never assumed to be platform-enforced. Arch §4.2.3 and the
change log (v2.0) carry the correction; ADR-038 carries the reasoning.

**Security review: one LOW finding, fixed in-slice.** `_neutralise_delimiters` originally defanged
only `<entry>`, while the grounding block also uses `<career_history>`, `<census>` and
`<relevant_entries>` — so entry content closing the *outer* tags escaped the data region just as
effectively. Impact was bounded (the real controls — no `toolConfig` on the synthesis call,
model-free retrieval, text-only rendering, PK scoping — all held, so the worst case was a
misleading answer, not escalation or exfiltration), but a control documented as "we delimit the
data" should actually delimit it. Fixed via `_STRUCTURAL_TAGS` + 3 regression tests. No HIGH or
MEDIUM findings.

**Advisory review:** logged **B-013** (every Q&A turn reads the whole corpus *including* ~20 KB of
embeddings per item — fine at 13 entries, felt on the interactive path as the corpus grows). No
in-slice fixes needed beyond the security one.

**Worth knowing for later.** The synthesis prompt ends with two consecutive `user` turns (the
question, then the grounding block). That is deliberate — instructions stay in the system prompt,
data goes in its own turn, so the trust boundary is legible — and Bedrock Converse accepts it with
Anthropic models. Verified live rather than assumed.

**Deferred:** B-011 hybrid retrieval for aggregate questions (the `intent` field ships reserved and
was correctly populated `aggregate`/`lookup` on every live run, so the v1.1 branch has a working
signal to hang off); B-012 keep answers plain-text; B-013 corpus-read weight. **Not pulled in:**
B-008 (P1 résumé identity header — still the highest-value standalone fix).

---

## Slice 8 — Check-in emails ✅

**Goal:** The habit loop — periodic personalized emails nudge the user to log fresh
accomplishments, with a working unsubscribe/pause and bounce handling.

**FRs:** FR-4.1–4.6.

**Scope — in:** SES identity + Configuration Set (arch §4.5); EventBridge Scheduler →
`checkin_lambda` (Haiku + RAG personalization per ADR-011; generic-reminder fallback on
failure/budget, FR-4.5, using the profile's `aspirational_goal`); `ses_event_handler` + the
*second* SNS topic (bounce/complaint — kept separate from the alarm topic per §4.5.5) + SQS DLQs
(§4.5.2); **`settings` sub-object on `PUT /settings`** (cadence/pause, FR-4.6 — the route itself
shipped early with B-008; this slice adds the nested field *and* the merge semantics B-014
requires) + cadence/pause UI on the existing identity form; CHECKINLOG audit items.

**Scope — out:** mobile push (v1.1); per-user time zones and DST-aware send times (see the
scheduling decision below); SES production access.

**Key refs:** arch §3.3 + §4.5, ADR-011, FR-4.

**New infra:** SES email identity + Configuration Set, EventBridge Scheduler schedule + its SQS
DLQ, 2 Lambdas (`checkin_lambda`, `ses_event_handler`) + log groups + error alarms, the
`careervault-ses-events` SNS topic, the `ses_event_handler` async DLQ.

**Pulled in from the backlog:** **B-014** (nested-`settings` merge — a hard prerequisite, since
FR-4.6 needs cadence and pause as independent controls) and **B-015** (fabricated placeholders in
the settings form, plus clearing the invented `name`/`location` from the dev PROFILE).

### Pre-flight findings (verified live at `/start-slice`, 2026-07-28)

Four things the scope above assumed, checked against the deployed account rather than the doc:

1. **SES is in sandbox with zero verified identities.** `ProductionAccessEnabled: false`,
   200 sends/day, 1/sec. Sandbox is sufficient for one recipient, so this is documented rather
   than escalated — but note `AWS::SES::EmailIdentity` only *triggers* the verification email;
   **clicking the link is a manual step** between `sam deploy` and the first successful send.
2. **Due-user lookup cannot be a Query.** See the scheduling decision below.
3. **The live dev PROFILE has no `settings` attribute at all** — B-008's `PUT /settings` only ever
   wrote `name`/`location`/`email`. So "settings block absent" is not an edge case to defend
   against, it is the *only* state that exists today: absent settings must default to
   weekly/unpaused, and an absent `next_checkin_at` must read as due-now.
4. **B-014 confirmed as a blocker**, not a theoretical one — `update_profile` compiles one
   `SET #f<n> = :v<n>` per *top-level* attribute, so a naive `settings` write replaces the object.
5. **`aspirational_goal` does not exist.** Arch §3.3.6 and this slice's scope line both say the
   generic fallback references "the profile's `aspirational_goal`" — the `Profile` model has no such
   field. Exactly the B-008 failure again: a doc describing a field that was never added, where the
   symptom is silent degradation rather than an error. Slice 8 adds it to `Profile`,
   `ProfileUpdate` and the settings form (see ADR-021).

### Decisions (resolved with Oche at slice start)

- **SES sandbox is sufficient for MVP.** One verified recipient, ~4 sends/month against a
  200/day quota. Documented, not escalated. *(Was a ⚠; resolved by the live check above.)*
- **Send window: Friday 23:00 UTC (~4pm PT).** End-of-week, while the week's wins are still
  fresh — the check-in asks a looking-back question, so it belongs at the end of the week rather
  than in Monday planning mode. *(Was a ⚠.)*
- **Scheduling shape: one daily UTC fire + `next_checkin_at`, no per-user time zone.**
  Due-user discovery is a `Scan` with `FilterExpression SK = PROFILE`, not a Query.
  → **ADR-039**.
- **Three fallback tiers, and a budget guard that is structural rather than measured.** §3.3.6's
  `mode` flag is a *content* decision (quiet week → talk about the goal instead); FR-4.5's real
  requirement is surviving Bedrock being unavailable, which neither §3.3.6 mode does since both
  call Haiku. Tier 3 is Jinja2-only, no model call. → **ADR-021** (the placeholder the ADL has
  carried since Phase 1).
- **Nested `settings` merge on `PUT /settings`** — dotted-path `SET settings.#f = :v` per
  sub-field, so cadence and pause move independently. → **ADR-040** (closes B-014).
- **Dev PROFILE `name`/`location` get cleared.** Both were invented by Claude during the B-008
  smoke test and never confirmed; Oche will enter real values through the form during this
  slice's UI smoke.

**Doc corrections this slice owes:** arch §3.3.3 says the Lambda "queries PROFILE items where
`next_checkin_at <= now`" — there is no index that supports that (ADR-028, no GSIs), so it is a
Scan. The same paragraph claims "PROFILE has `checkin_cadence` and `checkin_time_local` attributes
already"; `checkin_time_local` **does not exist** in the `Settings` model and, per ADR-039, is not
being added at MVP.

**Exit criteria:** scheduled run produces a real personalized email in the inbox; pause and
cadence change independently via the settings UI and each takes effect (pause suppresses the next
send; cadence moves `next_checkin_at`); the generic-reminder fallback (FR-4.5) is exercised, not
just coded; a simulated bounce (SES mailbox simulator) lands in `ses_event_handler` and is visible
in logs and on the PROFILE; a CHECKINLOG item is written per send.

**Completion notes:**

Deployed to dev and verified end to end. **All three ADR-021 tiers were exercised live, not just
coded** — each one produced a real email and a CHECKINLOG row:

| Tier | Subject it produced | Entries referenced |
|---|---|---|
| `generic` | "What have you shipped lately?" | 0 |
| `static` | "Anything worth logging this week?" | 1 (fallback fired) |
| `personalized` | "Nice work on the AZ-900" | 1 |

Also verified live: **both** idempotency layers (the due-ness gate, and separately the conditional
slot claim under the real Scheduler-retry shape — due, but sent minutes ago → `skipped_idempotent`,
no second email); pause suppressing a send while leaving `next_checkin_at` untouched; a
weekly→monthly change pacing the next cycle at 30 days rather than 7; and the full bounce pipeline
(SES mailbox simulator → Configuration Set → SNS → `ses_event_handler` → `bounce_count: 1`,
`bounceType: Permanent` on the PROFILE). Both DLQs empty. Test data restored afterwards; the cycle
is anchored to Friday 2026-07-31T23:00Z so the first *unassisted* run is the final confirmation.

Measured **~$0.0026 per check-in** (~1.3K in / ~220 out tokens on Haiku), so ~**$0.01/month** at
weekly cadence — matching §3.3.7's estimate and immaterial against the $5 ceiling.

**Three things worth carrying out of this slice:**

**(1) `required` in a Converse tool schema is a hint, not a constraint.** The first personalized
send returned a complete, well-written email that omitted `sign_off` — a `required` field — and
Pydantic rejected it, dropping a good email to the static tier. The generic send a minute earlier
had included it; same prompt, same temperature 0. The fix was not a looser schema but a split:
`subject` and `prompts` stay strict (without them it is not a check-in), `greeting` and `sign_off`
default. **Validate what makes the output useful; default what merely makes it polished** — a schema
strict about cosmetics converts recoverable model variance into a visible downgrade, and because the
email still *arrives*, that downgrade is invisible without the `CheckinsStaticFallback` metric.

**(2) The docs described two fields that had never existed** — `checkin_time_local` (§3.3.3) and
`aspirational_goal` (§3.3.6). Exactly B-008's failure mode, twice, in the same feature. One was
added (the generic fallback is inert without it) and one deliberately was not (nothing reads it;
a field that implies a capability it does not have is worse than an absent one). The pattern is
worth naming: **prose describing a data model drifts silently, because nothing fails when a field
in a sentence never becomes a field in a schema.**

**(3) The idempotency ordering has a price, and it is the right one here.** Claiming the send slot
before calling SES means a failed send still consumes the cycle. Claiming after would mean a
Scheduler retry delivers a duplicate. Idempotency buys "at most once" by giving up "at least once";
no ordering yields both. Correct for a nudge, wrong for anything transactional → B-016.

**Security review:** one **LOW** finding, fixed in-slice — the check-in prompt builder had none of
the ADR-038 containment `chat/qa.py` established for the *same* threat: no delimited data region,
no delimiter defanging, and `title` (200 chars, attacker-authorable via an uploaded résumé) not
newline-normalised, so it could forge extra lines in a line-oriented prompt. Bounded by the same
architectural controls as slice 7 — the compose call's only tool returns text fields, output is
validated into fixed Pydantic fields, and the email template autoescapes with both `href`s coming
from an environment variable rather than the model — so the realistic worst case was attacker-chosen
*prose* in an email from a trusted sender, not markup or a tool call. Fixed by lifting the defanging
into `careervault/prompt_safety.py` and pointing both prompt builders at it. **The finding is really
about drift:** the control existed, was documented, and was simply absent in the second place it was
needed, because it lived as a private helper in the first. *A defense that is one module's private
function is a defense the next module will not have.* Reviewed clean otherwise — notably the dotted
document paths use generated placeholders with names passed via `ExpressionAttributeNames` (no
injection path), no server-owned state is writable through `PUT /settings`, and the SNS topic policy
scopes publish to `ses.amazonaws.com` with a `SourceAccount` condition.

**Pulled in and closed:** B-014 (nested-`settings` merge — ADR-040, with all four DynamoDB premises
probed against the live table first; the single-expression seed form was in the ADR's first draft as
fact and was wrong), B-015 (fabricated placeholders, plus clearing the invented dev PROFILE values).

**Also fixed in-slice:** a test-harness bug this slice exposed — `checkin/rendering.py` shadowed
`resume_agent/rendering.py` because sibling modules resolved off a shared `sys.path`, breaking the
agent's tests with a misleading error. `load_handler` now isolates each load; the residual case
(tests importing siblings directly) is B-017.

**Deferred:** B-016 (failed send consumes the cycle), B-017 (remaining test-harness `sys.path`
fragility), B-018 (no integration test for the scheduled flow — slice 9 owns it, and it is the
highest-value flow to cover since a scheduled job cannot be smoke-tested by clicking around),
B-019 (bounce state has no UI and no automated response). **Not pulled in:** B-003, B-004, B-005,
B-006/B-007, B-009, B-011, B-012, B-013.

**Docs:** architecture **v2.1** (three corrections — §3.3.3 and §4.5.4 both said "Query" for what
is necessarily a `Scan`; §4.5.4's IAM row gains `dynamodb:Scan`; the `checkin_time_local` claim
retracted). New ADRs **-039**, **-040**, and **-021** promoted from placeholder to accepted.

---

## Slice 9 — Hardening & MVP close ✅

**Goal:** Declare the MVP honestly — verified, documented, and with the loose ends either tied
or explicitly parked.

**Scope — in:** integration test suite against deployed dev + **DynamoDB Local** for
conditional-write semantics (arch §5.6 — the v1.3 changelog explicitly calls for this net after
the SK-prefix bug slipped past string-assertion tests); **frontend unit tests** (Vitest + React
Testing Library) locking the UI-state flows — the propose/confirm card, the dashboard edit/delete
cards, the 409 "save anyway" path — and wired into the CI workflow (the slice-3 stuck-"Saving"
bug is the motivating example: it shipped because no automated test exercises component state).
This subsumes the **slice-4 frontend-render smoke test** flag (a minimal "app root renders + lands
in the expected auth state" gate): the current frontend CI job is typecheck+build+lint only, so
green CI does not prove the app renders. **Pull-earlier trigger:** if we ever enable auto-merge for
green frontend Dependabot PRs, add at least the render smoke test as a standalone PR *first* — a
hollow gate + auto-merge is how a broken build ships silently (see the `dependabot-triage` skill).
Then: README refresh (currently describes only
slice 1); FR/NFR coverage audit against requirements v0.5; **MVP evaluation scorecard** — score
the shipped MVP against the requirements §7 success criteria and the NFRs (cost, latency),
capturing what worked / what to improve and routing each finding into the v1.1 plan or parking
lot; cost review against the $5 ceiling with real Bedrock numbers; memory + docs sweep.

**Scope adjustments made at slice start (2026-07-28):**

- **Folded in from the backlog:** **B-018** (integration coverage for the check-in flow — the
  highest-value flow to cover, since a scheduled job is the one thing that cannot be smoke-tested by
  clicking around) and **B-017** (test-harness `sys.path` fragility, already tagged as a slice-9
  fit). **B-009** is *adjudicated, not implemented*: FR-5.3 says "format-select" and slice 6 shipped
  HTML-vs-PDF rather than layout choice, so the FR audit must rule on met-vs-deferred.
- **Consciously left:** B-001 (UI polish), B-003, B-004, B-006/B-007, B-011, B-013. B-010 (Sonnet 5)
  remains `blocked-external`.
- **Requirements §7.4 is falsified and must be corrected, not scored around.** It asserts tailored
  résumé output "within 30 seconds"; measured reality is **~176s**. Slice 6b corrected architecture
  §3.2.2's parallel "under 90 seconds" claim but left §7.4 standing — the drift got half-fixed. The
  scorecard cannot honestly score a criterion the project already knows to be unmeetable, so §7.4
  gets a defensible target with ADR-037 (async generation) recorded as *why* the original was
  abandoned.
- **Cost reframed by live numbers.** July MTD is **$3.52 / $5.00**, of which Sonnet 4.6 is **$2.88
  (82%)** and *all* non-Bedrock infrastructure is **under $0.01 combined**. The ceiling constrains
  Bedrock call volume, not environment count — which is what settles the prod decision below and
  what forces the integration suite to be tiered.
- **Browser tooling (out of scope, dev-loop only).** Playwright MCP added via a checked-in
  `.mcp.json` (persistent profile at `.playwright-profile/`, gitignored — it holds a live Cognito
  session). It is a tool for *inspecting* the app, not a CI gate: slice 9's frontend deliverable
  remains Vitest + RTL running headless in CI. Its first job is turning B-001 from one vague line
  into a concrete list. No browser-driven E2E enters CI this slice.

**⚠ Decisions:**
- ~~Deploy the prod stack vs declare dev-as-MVP.~~ **Resolved → ADR-041: dev *is* the MVP, prod
  proven by `sam deploy --no-execute-changeset`.** Cost turned out not to be the tie-breaker (idle
  infra is <$0.01/mo); the real costs are operational — a second Cognito pool, a second SES identity
  needing a *manual* verification click, and permanent two-stack drift on a single-user app. The one
  genuine gap, the never-evaluated prod-gated billing alarms, is closed by the dry run at zero cost.
- ~~Integration-suite cost posture.~~ **Resolved → ADR-042: tiered, expensive tier opt-in.** Default
  run is free (DynamoDB Local + deployed dev with Bedrock stubbed); `--bedrock` (~$0.01, Haiku) and
  `--expensive` (~$0.31, the Sonnet résumé run) are explicit. A uniform suite would cost ~$0.35/run
  — ~14 runs to the ceiling — which is a suite that gets avoided rather than run.
- **Still open: which parking-lot items graduate to a v1.1 plan.** Deliberately deferred to *after*
  the MVP scorecard exists — graduating items before the audit produces its findings would be
  deciding without the evidence the audit is meant to generate.

**Exit criteria:** every FR maps to a verified slice or a documented deferral (FR-5.3/B-009
explicitly ruled on); integration tests runnable with one command whose default tier costs **$0**;
frontend unit tests (Vitest + RTL) green in CI, proving the app renders; requirements §7.4 corrected
to a measured, defensible target; prod change set generated and its manual-step gap documented
(ADR-041); MVP scored against the §7 success criteria + NFRs with every finding routed to v1.1 or the
parking lot; README refreshed beyond slice 1 and stating plainly that `careervault-dev` *is* the MVP
stack; this doc's status board all ✅; MVP declared.

**Completion notes:**

**MVP declared.** 461 automated tests where slice 8 ended with 370, and the default run of every
suite costs $0.

**Verification, by cost tier (ADR-042).** 376 backend unit · 23 frontend (Vitest + RTL, new) · 56
integration on DynamoDB Local + deployed dev, free · 5 real-Haiku (`--bedrock`, ~$0.01) · 1 full
Sonnet résumé run (`--expensive`, ~$0.11). The tiering is the load-bearing idea: a uniform suite at
~$0.35 a run is ~14 runs to the ceiling, which is a suite people avoid — and **an avoided test is
worse than an absent one, because it still implies coverage**.

**Five things worth carrying.**

**(1) The frontend CI gate was hollow, and the tests that fill it had to be written a specific way.**
Typecheck + build + lint never execute a component, so a green pipeline proved the code compiled and
nothing else. Filling it surfaced a Vitest trap: **a `vi.fn()` that returns a rejected promise fails
the test even when the component catches it correctly** — the spy's settlement tracking leaves an
unhandled derived chain. Confirmed by bisection (it reproduces with *zero assertions in the test
body* and vanishes without the module mock), so every error-path test is unwritable that way. The
workaround turned out to be the better design: stub `fetch` and keep the real `lib/api`, which puts
the 201/200/409/422/500 mapping under test too and lets assertions check the **actual request body**
— so "Save anyway" now verifies `acknowledge_duplicate: true` goes on the wire.

**(2) The prod dry run found a blocker, and not the one it was run to check.** ADR-041 justified
`--no-execute-changeset` on the never-evaluated billing alarms. The first attempt failed before
producing a change set at all — `AWS::EarlyValidation::ResourceExistenceCheck`, with **no detail in
either `describe-stack-events` or `describe-change-set-hooks`** — and was diagnosed by re-running
the identical template with one parameter changed. `CheckinEmailIdentity` builds an SES identity
from `CheckinSenderAddress`, which is **not** environment-suffixed unlike the ConfigurationSet
directly below it; an SES identity is unique per account+region and dev already owns it. **The prod
stack could never have deployed** (B-021). Once unblocked: 70 resources, and the billing alarms do
validate. *A conditional that has never been evaluated is not "probably fine" — it is untested code,
and the cheapest possible test failed on its first run.*

**(3) A falsified requirement scores itself green.** §7.4 and NFR-2.2 both promised a résumé "within
30 seconds"; measured 72s (2-entry corpus) and ~176s (13-entry), and the target was *structurally
impossible* — anything over API Gateway's 29s integration timeout cannot be served synchronously,
which is what forced ADR-037. Slice 6b corrected the parallel claim in arch §3.2.2 **and stopped
there**, leaving the requirement and the success criterion — the two documents the MVP is graded
against — still asserting a falsehood. *Correcting the description while leaving the specification is
the more dangerous half to skip.* The fix specifies async delivery with a ceiling, not a bigger
number: **a latency requirement and a delivery model are not independent choices.**

**(4) Cost and latency are the same problem.** The `--expensive` run measured **72s / 20,183 tokens
/ $0.113 on a 2-entry corpus** against slice 6b's **176s / 82.9K / $0.35 on 13 entries** — *same
`REVISE` verdict, same phases*, so it is not a cheaper code path. Both scale with corpus size via the
retrieval loop's growing history. The corollary is the uncomfortable one: **the app gets more
expensive and slower precisely as it becomes more useful.** B-004 and B-020 attack one mechanism.

**(5) My own test bugs were caught by tooling, not by re-reading.** A delete test asserted `204`
where `career_crud` returns `200` (a status the system never emits); `tsc` caught an
`ErrorContext`/`Error` mismatch the tests were happy with; a "rejects invalid input" test passed for
the *wrong reason* until it asserted the specific error field; and the integration runner silently
collected the whole repo (401 tests instead of 25) because `"${ARR[@]:-}"` on an empty array under
`set -u` expands to an empty-string path. Two of three `--expensive` failures were **contract**
errors on the most expensive endpoint, now guarded for **$0** in the cloud tier — *on an endpoint
that costs real money, the request contract deserves a free test of its own.*

**Audit outcome** ([scorecard](careervault-mvp-scorecard.md)): 5/6 success criteria clean (the 6th
passed only after correcting the criterion); 20/22 FRs met, 1 partial (B-022 — no copyable bullets,
"technically met" via FR-5.3's AND/OR wording), 1 deliberately deferred (FR-5.4); 16 NFRs met, 4
caveated, 3 unverified, 1 not measurable — *revised at v1.1 slice 1 to 16 met, 5 caveated, 1
unverified, **1 failed**, 1 not measurable, after NFR-2.3 and NFR-6.2 were finally measured.*
**Cost: $3.88 / $5.00** in the project's heaviest month,
with Bedrock at 87% and *all* deployed infrastructure under $0.01 combined — the reframing that
decided both ADR-041 and ADR-042.

**Closed:** B-014, B-017, B-018. **Opened:** B-020 (latency), B-021 (prod SES collision), B-022
(copyable bullets), B-023 (latency unmeasured), B-024 (email clients). **New tooling:** Playwright
MCP for browser-driven UI work (dev-loop only — deliberately not a CI gate). **v1.1 graduated:**
résumé speed + usability, a UI/mobile pass, and voice capture per ADR-014.

---

## v1.1 — graduated scope

Decided with Oche at slice-9 close, *after* the [MVP scorecard](careervault-mvp-scorecard.md)
existed. Sequencing that decision after the audit was deliberate: graduating items beforehand would
have meant choosing without the evidence the audit was run to produce.

The theme is **"the flagship feature, finished"** — plus the one capture affordance the MVP always
intended to add.

### 1. Make the résumé fast and its output usable

| Item | Why it graduated |
|---|---|
| **B-020** — reduce generation latency | 72s–176s. Raised by Oche directly, and requirements §7.4/NFR-2.2 had to be *corrected* rather than met, which is the strongest possible signal that the number matters. |
| **B-004** — retrieval-loop context growth | Same root cause as B-020 seen from the cost side. The slice-9 measurement (2-entry corpus: 72s/$0.113; 13-entry: ~176s/$0.31–0.35, same `REVISE` verdict) makes the shared mechanism concrete. Fixing it pays twice. |
| **B-023** — measure interactive latency | How we would know B-020 worked. NFR-2.1/2.3 currently have no numbers at all; cost has a forcing function (the bill) and latency has none. |
| **B-022** — copyable plain-text bullets | The cheapest real win in the backlog. Most people tailoring a résumé already have one, and today there is no way to get the tailored bullets out except reading them off an iframe or a PDF. |

**Sequencing note:** do **B-023 first**. Optimising latency without a baseline is how you ship a
change that feels faster and isn't.

### 2. UI and mobile pass

| Item | Why it graduated |
|---|---|
| **B-001** — flesh out the UI | Functional but visually basic since slice 4; never had a design pass. |
| **NFR-6.2** — mobile web | Scored ❓ *Unverified* on the scorecard, not ✅. A responsive pass closes a real requirement, not just polish. |

**Start by enumerating, not styling.** Playwright MCP is now wired up (checked-in `.mcp.json`), so
the first task is driving the real app at desktop and mobile viewports and turning B-001's single
line into a specific list — including the accessibility tree, which nobody has ever looked at.

### 3. Voice capture for entry logging (ADR-014)

Requested by Oche at slice-9 close: *"a key feature to make it easier for users to log their entries
without typing long entries."*

This was already decided and parked, not new — **ADR-014** (2026-05-31) deferred voice-mode
ingestion to v1.1 and, importantly, already chose the approach: **the browser's free Web Speech
API**, explicitly *not* Amazon Transcribe, to avoid added cost and complexity.

Two consequences worth carrying into the work:

- **It costs nothing in AWS terms.** Web Speech API is browser-side, so voice capture adds **$0** to
  the bill — the transcript enters the existing `POST /chat` path and costs exactly what a typed
  message costs today. Against a $5 ceiling where Bedrock is 87% of spend, that matters.
- **It compounds with the fallback ladder.** Speech-to-text output is messier than typed input —
  more filler, no punctuation, garbled proper nouns. The existing `ask_clarification` route (FR-2.4)
  is the right landing place for that, so the work is likely *frontend capture + prompt tolerance*
  rather than a new backend path. Worth verifying rather than assuming.
- ⚠️ **Browser support is uneven.** Web Speech API's continuous recognition is well supported in
  Chrome and Safari and historically weak in Firefox. Needs a graceful fallback to typing, which the
  UI already has by default.

### Explicitly *not* graduated (staying in the backlog)

Not dropped — reconsidered when their trigger arrives.

- **Retrieval quality** — B-003 (dedup precision), B-011 (hybrid retrieval for aggregates). Both
  matter as the corpus grows; at ~13 entries neither is felt.
- **Operational loose ends** — B-021 (prod stack cannot deploy), B-019 (bounce state invisible),
  B-024 (email verified in Gmail only). B-021's trigger is explicit: **the moment ADR-041 reverses
  and a prod stack is wanted, this is a blocker**, and it is much cheaper to fix before that day.
- **B-006 / B-007** (agent debug metadata) — still wanted while the agent is being evaluated.
- **B-010** (Sonnet 5) — `blocked-external`, nothing self-serve remains.
- **B-016** (a failed send consumes the cycle) — correct trade for a nudge; revisit only if the
  pattern is copied somewhere transactional.

---

## v1.1 slice 1 — Redesign: audit, tokens, shell, Home ✅

**Goal:** land the design system and the two views that carry it — the app shell and a new Home —
against a measured baseline, fixing the accessibility debt a visual rebuild would otherwise inherit.

**Key refs:** [pre-redesign audit](design/v1.1-redesign/pre-redesign-audit.md) ·
[design handoff](design/v1.1-redesign/README.md) · ADR-043 (token corrections) ·
ADR-044 (both themes) · ADR-045 (client-side aggregates, streak) · ADR-003 · ADR-019 · ADR-025

### ⚠ How to read the design handoff

**It is a proposal informed by the repo, not a contract** — confirmed with Oche 2026-08-07. Claude
Design was given the direction and read access to the repository, and it filled gaps with features
that seemed plausible. Several specified elements **describe things that do not exist**: a résumé
history grid (no list endpoint; `RESUMERUN` is TTL'd at 30 days), a gap-analysis insight line, a
"warn me before the streak breaks" reminder, JSON export, and account deletion.

The rule for this and every later redesign slice: **build against what exists, defer the rest with a
backlog item, and never fabricate the data in between.** B-015 is the standing precedent — invented
placeholder content is logged as a defect, not shipped as a stand-in. Where a designed slot has no
source, either substitute something derivable and on-theme (as ADR-045 does for the third stat card)
or omit it; do not fill it with plausible-looking fiction.

**Amend the design where it does not work.** Oche's explicit direction, 2026-08-07: the handoff was
commissioned as a *concept*, and although it presents itself as pixel-final, judgment overrides
fidelity when an element does not hold up in the real app. Two worked examples from this slice, both
of which only became visible once the thing was on screen:

- **The year grid.** Specified as 130 cells in 26 fortnight columns, which measures 442px inside a
  ~1172px card — a small dense block with two thirds of its card empty, reading as unfinished.
  Rebuilt as one cell per day across 53 week-columns × 7 day-of-week rows (the GitHub
  contribution-graph form), which fills any width and makes a check-in cadence visible as a
  horizontal band.
- **The big stat numerals.** Specified as JetBrains Mono 30px/700. Mono is right for small
  data-chrome — dates, record numbers, uppercase micro-labels — but at 30px it is the largest type
  on the page, and a heavy coding face beside a soft grotesque functions as a second display
  typeface. That is what the handoff itself set out to avoid in dropping 1d's serif accent for "one
  sans across the entire UI", so Figtree with `tabular-nums` is *more* faithful to its stated intent
  than its literal instruction.

The bar for amending: the deviation is recorded with its reasoning, and it serves the design's own
stated goals rather than the implementer's preference. Accessibility deviations are a separate and
stricter case — those go through an ADR (ADR-043).

### Scope — in

1. Design bundle relocated to `docs/design/v1.1-redesign/`. ✅
2. Enumeration pass: a11y tree per view, contrast audit of the incoming design, NFR-2.3 baseline. ✅
3. ADR-043 / ADR-044 / ADR-045. ✅
4. Tokens into `index.css` — both themes per ADR-044; dead Vite starter CSS removed.
5. Shell: `<header>`/`<nav>` as siblings of `<main>`, six-tab nav, `aria-current`, streak pill,
   avatar, **and the auth states the design omits** (loading, error, signed-out, sign-out).
6. Home view — aggregates derived client-side per ADR-045.
7. Responsive: breakpoints per audit §C; the mobile overflow that fails NFR-6.2 is shell-local.
8. Frontend tests updated — `App.test.tsx` asserts nav labels that all change; new tests for the
   streak derivation, which ADR-045 makes falsifiable.

### Scope — out

Log, Timeline, Résumés, Import, Details (v1.1 slice 2). Résumé list endpoint and the `RESUMERUN`
TTL question (**B-028**, now blocking the Résumés view). Gap-analysis line (**B-030**). Aggregate
endpoint (**B-029**). Voice capture and the résumé-latency workstream — separate v1.1 items.

### Exit criteria

- `docs/design/v1.1-redesign/` in place; no stray top-level folder. ✅
- Enumeration artifact committed with a11y findings, contrast remedies, NFR-2.3 baseline. ✅
- ADR-043/044/045 written **before** the code they justify. ✅
- Tokens in `index.css`; **no hex outside it** — a raw hex in a feature CSS file is a light-mode bug
  invisible to dark-mode review, so this is an exit criterion, not a style preference.
- Shell + Home match the handoff at ≥1280px and stack cleanly at 375px, in **both** themes.
- Zero horizontal overflow at 360px on every view (closes the NFR-6.2 failure).
- Banner landmark present; `aria-current` on the active tab; exactly one `<h1>` per view.
- Auth states preserved — the design has no sign-out and we must not lose it.
- Frontend tests green and updated.
- Scorecard NFR-6.2 re-measured and re-scored after the fix.

### Completion notes

**Shipped.** The token layer (`index.css` is now the only file defining a colour, both themes per
ADR-044), a rebuilt shell (banner landmark, six-tab nav with `aria-current`, skip link, account
disclosure carrying the sign-out the handoff omits), and a new Home deriving every number
client-side from `GET /entries` (ADR-045). Backend untouched — a pure frontend diff, which is why
the deployment risk is near zero.

**Two requirements moved off ❓Unverified**, which was the real value of enumerating first:

- **NFR-6.2 was failing, not merely unverified.** 82px of horizontal overflow on all five views at
  360px. The cause was entirely shell-local — a 241px email string that could not compress and a nav
  that neither wrapped nor scrolled — so one fix cleared every view. **Now 0px on all six at 375px.**
  Re-scored ⚠️ rather than ✅: zero overflow is one property of "usable on mobile", and the five
  views behind the shell keep their pre-redesign internals until slice 2.
- **NFR-2.3 splits cold/warm.** Cold **3686ms** against a 2s budget; warm ~940ms. Nearly all of it is
  `GET /entries` (3639ms cold), not rendering. The cold number is the one that counts, and that is
  the non-obvious part: **FR-4's check-in email is designed to bring the user back weekly-to-monthly,
  so the Lambda is reliably cold when they arrive.** The cold path is the core loop's *typical* path,
  not an edge case. Closes B-023's NFR-2.3 half; NFR-2.1 remains open.

**The design shipped two WCAG failures**, neither visible by inspection. `text-faint` failed AA on
every surface at the design's *smallest* type (10–11px, where no large-text exemption applies), and
focus was signalled by a 1.68-contrast border swap after `outline: none`. Both fixed using colours
already in the handoff's own palette (ADR-043), so the deviation is two values — measured,
minimum-magnitude — and a reviewer can diff `:root` against the token table and find exactly those.

**Gotchas discovered**, roughly by how much they would have cost later:

1. **Unset CSS custom properties resolve to nothing, not to a fallback.** Replacing the token layer
   while five views still referenced the old names would have rendered them colourless. A marked
   compatibility shim (5 aliases) covers the gap and dies view-by-view in slice 2.
2. **A `<header>` inside `<main>` silently loses its banner role, but a `<nav>` keeps its own.** The
   live accessibility tree was precise about which one degrades — worth knowing, because the failure
   is invisible by every other means.
3. **Removing the placeholder logo nearly removed all mobile branding.** The wordmark had been hidden
   below 768px *specifically* to make room for the square. Exactly the class of silent regression the
   audit exists to catch — and it was caught only because the audit had been run.
4. **The frontend CI gate is no longer hollow**, contrary to what `dependabot-triage` asserted. 28
   Vitest+RTL tests have gated every PR since slice 9; the skill was corrected in this slice.
5. **Making `main` a plain block broke the five un-redesigned views**, which have no container of
   their own and were centred by the old `main`'s flexbox. Caught by the code review, not by me.

**Evaluation.** Exit criteria met, with one deliberately unmet: the built bundle was **not deployed**
to S3/CloudFront. Verification ran against the deployed dev API from a local dev server, so
API Gateway → Lambda → DynamoDB is exercised end-to-end; the only unverified link is static asset
hosting. Deferred on purpose — `careervault-dev` *is* the MVP stack (ADR-041), and publishing a
half-redesigned app to the thing Oche actually uses is worse than waiting for slice 2.

**Cost: $0 added.** No Bedrock calls, no new AWS resources, no schema change. Month-to-date at slice
start was $0.028.

**One thing to improve.** The code review returned 8 findings on a diff I had already driven in a
browser at two viewports and two themes — including a layout regression affecting five of six views.
Browser verification confirmed the views I *built* and never re-checked the ones I merely *touched*.
The lesson generalises: when a change lands in a shared container, the blast radius is every child,
and "I looked at it" only covers what was on screen. All 8 were fixed in-slice; none deferred.

---

## v1.1 slice 2 — Redesign: Log, Timeline, Import, Details ✅

**Goal:** rebuild four of the five remaining views on the slice-1 token layer, retiring the
compatibility shim and the `.legacy-view` wrapper view-by-view, and fixing the accessibility debt the
audit recorded against each one.

**Key refs:** [pre-redesign audit](design/v1.1-redesign/pre-redesign-audit.md) §Findings (A3–A11) ·
[design handoff](design/v1.1-redesign/README.md) §§2, 3, 5, 6 · ADR-043 (token corrections) ·
ADR-044 (both themes) · ADR-045 (derive client-side; omit rather than fabricate) · ADR-040
(nested settings merge)

### ⚠ Why Résumés is not in this slice

Split out at slice-2 scoping (2026-08-08) and promoted to its own slice. The Résumés view is the one
that **cannot be built honestly from what exists**: `template.yaml` exposes only
`POST /resumes/generate` and `GET /resumes/{run_id}` — there is no list endpoint — and `RESUMERUN`
items carry a 30-day TTL, so even with one, the designed grid ("Built 12 Jul 2026 · 9 records drawn")
could not reach back further than a month. That is **B-028**, and it is not a UI problem: ADR-015 was
*amended* at slice 6b to make résumé artifact retention a flat 30 days precisely to match that TTL,
so any fix reopens a retention decision.

The reasoning for splitting rather than absorbing it: slice 2 is otherwise a **pure frontend diff**,
which is what made slice 1's deployment risk near zero. Folding in a data-model decision, a new API
route, a Lambda change and integration tests would mix two very different risk profiles in one
review. B-028 gets an ADR and a slice of its own.

### Scope — in

1. **Log (chat)** — panel layout, cadence-aware header, proposal cards ([`ProposalCard.tsx`](../frontend/src/chat/ProposalCard.tsx)
   already exists), prompt chips, activity sidebar with show/hide. Sidebar streak card and
   "Logged since Friday" derive from `GET /entries` via the existing [`aggregates.ts`](../frontend/src/lib/aggregates.ts) (ADR-045).
2. **Timeline (entries)** — header + filters, list with year dividers, sticky detail panel, fact rows.
3. **Import (upload)** — dropzone, selectable results rows, commit button.
4. **Details (settings)** — "You" card, cadence options, reminders, data card. **JSON export built**
   (see below).
5. **Accessibility, per the audit's per-view assignments** — **A4** (live region on the chat
   transcript; High), **A5** (message roles exposed to AT), **A6** (typing indicator announces
   meaningfully, not as "…"), **A7** ("Retry" associated with the message that failed), **A9** (file
   input accessible name), plus **A3** (real labels, not placeholder-only), **A10** (exactly one
   `<h1>` per view) and **A11** (live regions for async state) as they apply to each view built here.
6. **Retire the slice-1 scaffolding** — delete each `index.css` shim alias as its stylesheet stops
   using it; drop each view out of `.legacy-view` as it is rebuilt. Four of five aliases should die
   here; the wrapper survives only for Résumés.
7. **B-032 — self-host Figtree and JetBrains Mono**, replacing the Google Fonts `@import`. Frontend-only,
   closes a slice-1 security-review note, and this is the slice already editing `index.css`.

### Scope — out

Résumés (v1.1 slice 3, with **B-028**). Three designed Details features that do not exist and are
**deferred rather than faked**, per the B-015 precedent:

- **"Warn me before the streak breaks"** (**B-033**) — a settings field plus a second scheduled send
  in `checkin_lambda`/EventBridge. Backend work, and it lands next to **B-019**, the other untouched
  check-in-delivery gap. A toggle that persists but sends nothing was explicitly rejected.
- **Account deletion** (**B-034**) — a destructive flow across Cognito, DynamoDB and S3 for a
  single-user MVP whose one user is the developer.
- **Gap-analysis line** (**B-030**) — already blocked on B-028.

Two designed data points have **no source and are omitted**, not invented: the Timeline detail
panel's "from chat" provenance (the `Entry` model has no `source` field; `created_at` supplies the
date half) and "Used in — 1 résumé" (needs résumé history → B-028).

### ⚠ Decisions

**No new ADR is required for this slice** — deliberately, and worth stating rather than manufacturing
one. Every judgment call here resolves under precedent already written: ADR-045 covers *derive
client-side and omit rather than fabricate* (which decides the export, the sidebar aggregates and both
omitted data points), ADR-043/044 cover the token and theme rules, and ADR-040 covers the nested
settings write the cadence and reminder controls need. The decision that **does** need an ADR — B-028's
retention/list-endpoint question — is exactly the one moved to slice 3.

- **JSON export is client-side.** `GET /entries` is already fetched for the view; export is a `Blob`
  download over data in hand, not a new endpoint. This is ADR-045's pattern applied again, and it
  inherits ADR-045's revisit trigger (**B-029**) unchanged.
- **B-012 is a standing invariant this slice must not break.** The Log redesign is the single most
  likely place to reach for a markdown renderer, and doing so would reopen the ADR-038 injection
  exfiltration channel. Chat answers stay plain text; the tested invariant stays tested.

### Exit criteria

- Four views rebuilt against the handoff at ≥1280px and stacked cleanly at 375px, in **both** themes.
- **No hex outside `index.css`** — same exit criterion as slice 1, same reason: a raw hex in a feature
  stylesheet is a light-mode bug that dark-mode review cannot see.
- Zero horizontal overflow at 360px on every view, re-measured rather than assumed.
- Audit findings A4, A5, A6, A7, A9 closed; A3/A10/A11 satisfied on all four views.
- Exactly one `<h1>` per view; live regions announce async state on each.
- Four of five shim aliases deleted; four views out of `.legacy-view`. Both are *checked*, not
  assumed — the remaining contents are named in the completion notes.
- B-012 verified still true: no markdown/HTML renderer anywhere in `frontend/src`.
- Frontend tests green and extended to the rebuilt views; backend suite untouched and still green.
- Every view re-checked in a browser **after** the last shared-container change, not before — the
  slice-1 lesson that cost 8 code-review findings.

### Completion notes

**Shipped.** Log, Timeline, Import and Details rebuilt on the slice-1 token layer, plus **B-032**
(fonts self-hosted). A pure frontend diff — no `backend/`, no `infrastructure/`, no deployed
behaviour changed, which is why the deployment risk is again near zero. **Tests 72 → 139 frontend**
(376 backend unchanged; 574 total).

**Exit criteria: met, with one prediction of my own that was wrong.** I wrote "four of five shim
aliases deleted"; only `--code-bg` could go, because the other four are all referenced by
`resume.css` — they are shared, not one-per-view, so they die together in slice 3. The substance
held: four views rebuilt, four out of `.legacy-view`, and the remaining contents are now *named* in
the `index.css` comment with the grep that verifies them. One raw hex survives outside `index.css` —
`resume.css`'s print paper-white, documented and belonging to slice 3; the other eight became
`--on-accent`.

**Verified across 24 combinations** (6 views × 2 themes × 2 widths): zero horizontal overflow, one
`<h1>` per rebuilt view, `.legacy-view` only on Résumés. A live chat round-trip (~$0.01) exercised
API Gateway → Lambda → DynamoDB and the restyled proposal card; the proposal was deliberately left
unsaved, so no test data entered the vault. Only static asset hosting is unverified — deferred as in
slice 1, since Résumés is still un-redesigned.

**Six defects the browser caught that no review would have.** Recorded because the pattern is the
point — each was invisible in the diff and obvious on screen:

1. **"Logged since Sunday" for a week that starts Monday.** `periodStart` returns a UTC-anchored
   midnight; formatting it locally renders the previous evening. Every UTC-anchored date now formats
   in UTC.
2. **`flex: 1` silently discarded the transcript height.** The shorthand expands to
   `flex-basis: 0%`, which beats `height` on the main axis, so the panel collapsed to bubble-size.
3. **The design's 580px transcript put the composer below the fold** on an 800px window. The panel
   now caps to `100dvh` minus the shell chrome and the transcript flexes inside it.
4. **CSS source order was inverted.** Vite emits child-imported CSS *before* the parent's, so
   `App.css`'s shared `.card { flex-direction: column }` beat `settings.css`'s
   `.data-card { row }` — the data card rendered as a centred column. Fixed structurally by
   importing `App.css` first in `App.tsx`, restoring tokens → shared → feature.
5. **Details had no `<h1>` while loading** — a real §A10 gap invisible to any check that runs after
   the fetch resolves.
6. **Five chips wrapped to four rows at 360px**, eating a height-capped transcript.

**The code review returned 15 findings and all 15 were fixed in-slice.** Two were arithmetic bugs
that a green suite had been hiding, and both were confirmed numerically before being touched:

- **`periodStart(d, "biweekly")` returned a Thursday in the *previous* fortnight.** A week *index*
  cannot be turned back into a timestamp by multiplying by `WEEK_MS` — the Unix epoch is a Thursday,
  so every multiple lands on one. `periodIndex(periodStart(d))` was off by a whole period, so the
  sidebar list and the streak disagreed about which fortnight was current.
- **`relativeSince` divided elapsed milliseconds by 24h instead of counting calendar days**, so an
  entry logged at 23:00 was reported as "today" when read at 09:00 — the exact misstatement the
  function was written to prevent.

The rest: the settings save never told the shell to re-read (so a cadence change left the header
pill, Home and the Log title computing against the old cadence); "Save anyway" persisted an entry
without refreshing anything; Timeline dropped the optimistic update, so a delete left the panel
offering Edit/Delete on a record that no longer existed; the cadence picker replaced a `<select>`
with buttons implementing none of the radiogroup keyboard contract — a net a11y regression in the
slice meant to close a11y findings; the composer became a single-line `<input>`, silently collapsing
newlines on the app's primary ingestion path; `revokeObjectURL` fired synchronously after `click()`
on a detached anchor, which is Chrome-specific behaviour; and four duplications (`isoWeek`, `CHIPS`,
`MAX_MESSAGE_CHARS`, the org lookup, the UTC date helper) now live in `lib/composer.ts` and
`lib/aggregates.ts`.

**Every fix was mutation-verified.** Reintroducing the two arithmetic bugs fails exactly 4 of the new
tests; reverting the overlay, the filter fallback and the settings callback fails exactly 4 more. A
test that passes for the wrong reason is worse than no test, and a green suite is not evidence —
all 15 findings passed a green suite before they were fixed.

**Cost: $0 added infrastructure**, ~$0.01 of Bedrock for the one live verification round-trip.
Month-to-date at wrap was **$0.04** against the $5 ceiling.

**One thing to improve.** I set an exit criterion ("four of five aliases") on an assumption I never
checked — that each alias belonged to one stylesheet. Thirty seconds of grep at planning time would
have said otherwise. The lesson generalises past this slice: a criterion asserting a fact about the
codebase should be *verified when written*, not discovered to be wrong at the gate that was supposed
to enforce it.

---

## v1.1 slice 3 — Redesign: Résumés + résumé history ✅

**Goal:** give the Résumés view a real data source, then rebuild it — retiring the last of the
slice-1 scaffolding, so the redesign is complete across all six views.

**Key refs:** [design handoff](design/v1.1-redesign/README.md) §4 · **ADR-046** (this slice's
decision) · ADR-015 as amended twice (delivery + retention) · ADR-037 (async job, RESUMERUN TTL) ·
ADR-045 (omit rather than fabricate) · ADR-028 (no GSIs) · B-028, B-036, B-022, B-007

### ⚠ Decisions — resolved before code, as ADR-046

B-028 was the blocker: no list endpoint, and a 30-day TTL on both the `RESUMERUN#` item and the
`resumes/` S3 objects, so history could not reach back further than a month. **ADR-046 splits a
durable `RESUME#<run_id>` record (no `expires_at`) from the ephemeral trace (30-day TTL unchanged)
and removes the `resumes/` lifecycle rule.**

The reasoning worth carrying: the 30-day artifact number was never a retention judgment — ADR-015's
amendment chose it to stop a trace item outliving the objects it pointed at. It is a coupling fix,
and once a durable record exists the coupling is gone. This is the revisit ADR-015 explicitly
anticipated ("*alongside the `GENERATED_RESUME` entity*").

**Voice capture was scoped into this slice and then moved out**, at Oche's call, to **v1.1 slice 4**
— it is frontend-only with zero backend surface, so it detaches cleanly, and slice 3 already carries
a data-model change, a new route, a Lambda change and a full view rebuild. Carried into slice 4: the
provider seam Oche asked for (a `DictationProvider` interface with an **optional** `onInterim`, so a
buffer-then-POST cloud API can satisfy the same contract as Web Speech's streaming events) becomes an
**amendment to ADR-014** rather than a new ADR — ADR-014 already chose Web Speech API on cost
grounds, and its own note that Firefox support is weak is what makes a second provider a known case
rather than speculative generality. Any paid cloud STT breaks ADR-014's cost premise; the seam is
where that trade-off gets made explicitly, and nothing paid is wired now.

### Phases

**Phase 0 — deploy current `main` ✅** *(no code; done at slice start)*

Slices 1 and 2 had never been deployed: the live bundle dated **2026-07-28**, pre-redesign. Deploying
first isolates two slices of undeployed UI risk from slice 3's changes — specifically the one thing
localhost cannot verify, which is **self-hosted fonts (B-032) under a production build**: asset
hashing, S3 content-types, CloudFront caching. Verified live: all four woff2 served as `font/woff2`,
CSS/JS content-types correct, Figtree rendering, one `<h1>`, **zero console errors**. Backend stack
untouched (last updated 2026-07-29, correctly — slices 1–2 touched no backend).

*Limitation stated honestly:* verification reached the sign-in screen only. The authenticated views
are unverified on CloudFront until Oche signs in.

**Phase 1 — backend + data model ✅**

Shipped and deployed. **397 → 407 backend tests**, 63 integration, all green; every new assertion
mutation-verified (six mutations, each caught by exactly one test — the right one). Verified
end-to-end with a real `--expensive` run: **74s, 20,455 tokens, $0.116, critique=REVISE**.

*Three things the cheap tiers could not have found, recorded because the pattern is the point:*

- **`elapsed_seconds` came back `null` from the deployed run.** `_record_item` wrote it;
  `_final_item` — the trace the poll actually reads for the first 30 days — did not. The unit test
  passed because its fake item supplied the field by hand: **a reader test over a hand-built fixture
  proves nothing about the producer.** The replacement asserts both writers.
- **Six real résumés had no history record and were 12 days from being unreachable.** Runs that
  completed before ADR-046 have only a trace, and once its TTL fires the artifacts have no record to
  list them, no trace to poll, and — since this slice removed the lifecycle rule — nothing to clean
  them up. Backfilled via `scripts/backfill-resume-records.py` (dry-run first, idempotent via
  `attribute_not_exists`), 6 written, verified through the deployed endpoint. **B-040** retires it.
- **Removing the TTL leaked test data.** The `resumes/` rule was also what swept `--expensive`
  artifacts; the tier gained a cleanup fixture, and 6 objects of slice-9 residue were deleted.

*Two bugs the backfill hit that only a script reading the table could:* `CAREERVAULT_TABLE_NAME` is
read from the environment by the shared helper (the dry run never reached that code path), and
DynamoDB returns numbers as `Decimal` while the write helper marshals through `json.dumps`, which
cannot serialise one. Both are now tested. Neither wrote a partial record — verified at zero before
re-running.

**Phase 1 scope, as built**

1. `RESUME#<run_id>` written on **successful completion only**, after `RESUMERUN#` is finalized
   (ADR-046 §3 — ordering chooses which divergence a crash produces).
2. `GET /resumes` on `resume_agent` — Query `SK begins_with RESUME#`, `ScanIndexForward=False` for
   newest-first, **projected** to `run_id`/`created_at`/`target_title`/`entry_count`/`status` so a
   pasted job description is not shipped per row (declining B-013's mistake in advance).
3. Remove the `ExpireGeneratedResumes` lifecycle rule; `ExpireRawUploads` untouched.
4. **B-022** — expose the `ResumeDocument` bullets as structured data so plain text is copyable.
   The last third of FR-5.3, and the only part of this phase that is a feature rather than plumbing.
5. New `RESUME#`-prefix helpers in `ddb_helpers`, per §4.2.4's SK-scoping invariant.

**Phase 2 — theme selection, the view, and the last of the scaffolding ✅**

Shipped. **139 → 183 frontend tests**; `tsc -b` green (run explicitly — `npm test` does not typecheck).
**B-036 closed and verified by grep, not assumption:** zero shim aliases, zero `.legacy-view`
references, **zero raw hex outside `index.css`** — the print white became `--paper`.

*What the browser caught that neither the tests nor the diff could,* the slice-2 lesson repeating
almost exactly. The Résumés view is behind Cognito and jsdom does no layout, so both rounds needed a
throwaway static harness against the real stylesheets:

- **The Appearance swatches were invisible.** `--swatch-light` on `--surface-sunken` read as an empty
  input; Dark would have vanished identically in dark mode. Each swatch now carries an accent wedge
  and a fixed border.
- **I invented a parallel button vocabulary.** `.primary`/`.secondary`/`.button` resolve to nothing —
  the shell already ships `.btn-primary`/`.btn-quiet`, used by all four slice-2 views. The buttons
  rendered as raw browser defaults.
- **And a parallel layout vocabulary.** `.resume-view`/`.resume-head` duplicated `.view`/`.view-head`,
  which own padding precisely so six views cannot drift apart by a few pixels. Now only `max-width`
  is this view's business.
- **A nested `<main>`** — App.tsx already wraps the view switch in one.

Three of those four are the same mistake: *building a private copy of something the shell already
owned*. Worth naming, because a diff cannot show you what you failed to reuse.

**Verified signed-in on the deployed app** (Oche signed the Playwright profile in), which is what the
static harness could not reach:

- **24 combinations clean** — 6 views × 2 themes × 2 widths (1280px / 360px): exactly one `<h1>`
  each, **zero horizontal page overflow**, and `.legacy-view` absent everywhere. The elements that do
  extend past 360px all sit inside the deliberately scrollable nav, not the page.
- **All six backfilled résumés render** in the history grid, newest-first, correct dates and counts,
  `LATEST` on the newest only.
- **B-022 confirmed against real data** — 5,302 characters of plain text, correct `SUMMARY`/bullet
  structure, clipboard verified by reading it back; the button holds "Copied" for its full 2s window.
- **B-007 degrades exactly as designed on backfilled records** — they predate the measurement, so the
  metadata row simply omits elapsed time rather than rendering `undefined`.
- **Theme selection end-to-end**: applies instantly, persists to `localStorage`, **survives a reload
  via the pre-paint script** with a live session, and returning to System removes the attribute and
  restores `color-scheme: light dark`.
- **Zero console errors** across the entire authenticated session.

**Phase 3 — résumé deletion (added mid-slice, 2026-08-09).** Raised by Oche on seeing the finished
grid: no way to remove a résumé. Built rather than deferred, because **this slice created the gap** —
under the old flat 30-day rule everything cleared itself, so nothing ever needed a delete. See the
second **ADR-046 amendment**: `DELETE /resumes/{run_id}` removes artifacts, record and trace behind
ADR-027's confirm; S3 goes first so a crash leaves a *visible, retryable* fault rather than
unreferenced objects nothing will ever expire. New IAM: `dynamodb:DeleteItem`, `s3:DeleteObject` on
`resumes/*`. **413 → 417 backend, 183 → 188 frontend.** Verified against the deployed stack with a
seeded throwaway record — record, trace and both objects gone, second delete 404s — deliberately not
by deleting one of the six real résumés.

*And a test that proved the wrong thing.* Every delete button announced as "Delete", so each got an
`aria-label` naming its résumé. Titles repeat, so I added the date; a fixture with differing dates
passed, and **the live page still collapsed two labels into one** — the real vault holds two
résumés both titled "Databricks", built four minutes apart on the *same afternoon*. The label now
carries the time, and the test fixture is that exact case rather than the kinder one I had invented.
A fixture you choose can confirm a fix that does not hold on the data you have.

**One more defect, found only by signing in.** `.btn-primary` and `.btn-quiet` were written for
`<button>`, which has no default underline — but "Download PDF" must be a real `<a>`, because
save-to-disk comes from the presigned `Content-Disposition` and a button cannot carry that. The
anchor rendered underlined and stopped matching the buttons beside it. Fixed at the definition
(`a.btn-primary, a.btn-quiet`) rather than in `resume.css`, so any future anchor-as-button inherits
it, and re-verified live.

*Also corrected:* `formatBuiltDate` re-implemented date formatting instead of reusing
`formatEventDate`, which already pins `timeZone: "UTC"` (the slice-2 fix) **and** `en-GB` day-first
order — my version used the reader's locale and rendered "Jul 28, 2026" against a design specifying
"12 Jul 2026".

**Phase 2 scope, as built**

Theme selection was **added mid-slice** (2026-08-09, Oche's call) and is sequenced **first**, ahead of
the view. Two reasons it belongs here rather than in slice 4: it edits `index.css`, which is exactly
the file **B-036** closes out this slice — deferring means reopening it immediately after declaring it
finished — and it makes the slice's own "both themes" exit criterion two clicks instead of an OS
settings trip, across six views × two themes × two widths. See the **ADR-044 amendment**.

5b. **Theme selection (Light · Dark · System)** on Details, defaulting to System — today's behaviour
    unchanged for anyone who never opens it. `localStorage`, applied by a pre-paint inline script in
    `index.html` (a `GET /settings` round-trip cannot beat the first frame, and theme is per-device by
    nature). One mechanism — an attribute selector beside the existing media query, **not** a
    `light-dark()` migration, which cannot express the five gradient tokens. The duplicated light block
    is guarded by a test asserting both definitions declare an identical token set.
6. Résumés rebuilt against handoff §4 — generator card, résumé grid, both themes, 375px and 1280px.
7. **B-036 in full, as the completion condition:** the four shim aliases in `index.css`, the
   `.legacy-view` wrapper in `App.css`, and the `App.test.tsx` carve-out that asserts it are deleted
   together. `resume.css`'s print `#fff` is tokenised or explicitly exempted as non-theme.
8. **B-007** — carry final elapsed time into the completed-run metadata row.

**Phase 4 — the wrap reviews.** The security review came back **clean** — no findings at or above
its confidence threshold. Its rejected-candidates list is the useful part, because the two hazards
this slice actually introduced were examined and held: a crafted `run_id` cannot escape the S3
prefix (the user-controlled segment sits *after* the JWT-derived one, and botocore places keys in
the `DeleteObjects` XML body, escaped, rather than in a normalizable URL path), and it cannot cross
entity prefixes either, because `run_id` is a *suffix* of a fixed literal — `RESUME#` + anything
never yields `RESUMERUN#`. One hardening note taken but not treated as a defect: `run_id` is never
validated with the existing `is_valid_ulid`, which is unreachable today and would become
load-bearing if the key layout changed.

**The code review returned 14 findings; 13 were fixed in-slice and 1 was backlogged (B-043).**
Four were genuinely dire, and three of those live in the delete path added in phase 3 — the newest,
least-exercised code in the slice:

- **`delete_objects` does not raise on a per-key failure.** It returns HTTP 200 with an `Errors`
  list, so `except ClientError` never fired: a half-failed delete removed the record and stranded
  the object *permanently*, which is precisely the B-039 orphaning the S3-first ordering was
  designed to prevent. The ordering was right and the error handling silently opted out of it.
- **A 404 was a destructive operation.** Artifacts and trace were deleted *before* checking whether
  the résumé existed, so `DELETE` on a **pending** run destroyed the trace of a live ~$0.31 Sonnet
  job — the user's poll would then report it expired while it was still running — and destroyed the
  only diagnostic record of a **failed** one. The record is now read first, which also makes the
  404 side-effect-free.
- **The S3 keys were rebuilt from a filename convention** instead of read from the record that
  stores them. Any record written under a different layout — a backfilled one, or anything after a
  future path change — would have had its row deleted and its real objects left behind. Reading the
  record first supplied the fix for all three at once.
- **The generator claimed a vault size it could not know.** "Pulls the *N* records in your vault"
  took `N` from the newest history row's `entry_count` — how many entries *that one run retrieved*
  for *that one target*. With 27 entries and a run that retrieved 13, it told the user their vault
  held 13. That is the ADR-045 / B-015 failure mode exactly: a fabricated statistic presented
  authoritatively. The real count was already in the shell (`GET /entries`) and is now passed down.

The rest: **Regenerate** on a history-opened résumé reran the textarea's contents — a different job
description, or none — spending $0.11–$0.35 against the wrong target, and no endpoint returns the
original `target_text`, so the button is now simply not offered there; `openRun` had no `catch`, so
View was a dead button on any network blip; the **Copy** button inside `<summary>` toggled the
disclosure shut, hiding the very fallback that exists for a blocked clipboard; the durable record
truncated `target_text` to 4,000 chars — a bound chosen for an item that expires in 30 days, applied
to one that never does, contradicting ADR-046 §4's own rationale for keeping it (B-030); the backfill
script never followed `LastEvaluatedKey`, so a migration racing a TTL deadline could have silently
skipped everything past the first 1 MB page; `resumeText`'s EDUCATION branch emitted a stranded
" (2018)" for a date-only entry, the dangling-separator case its neighbours both guard; and the
`watchSystemTheme` subscription was a **no-op** — `setTheme("system")` while already `"system"`, which
React bails out of — so it and the two theme helpers with no production caller were deleted rather
than left as tested dead code.

*Two of these were caught by the review and not by a green suite, again.* The `delete_objects`
partial-failure path passed because the test double returned `None` instead of the API's actual
dict shape — a fake that was wrong in exactly the way that made the assertion vacuous. Every fix
above is mutation-verified: reverting the `Errors` check, the record-first read, the stored-key
lookup, the vault count and the Regenerate gate each fails exactly one test, and the right one.

### Scope — out

- **Voice capture** → slice 4. Its `DictationProvider` seam is now recorded as an **ADR-014
  amendment**, which the review caught missing — CLAUDE.md was already telling the next session to
  look for it in the ADL, where it did not exist.
- **B-030** (gap analysis) — *unblocked* by ADR-046's durable target history, but not built here.
  Needs an inference design that is not a per-load Bedrock call against the ceiling.
- **B-006** (gate the debug metadata row) — deliberately kept visible; B-020/B-004 (résumé speed) is
  the next optimisation work and that row is how runs get compared.
- ~~**Résumé delete**~~ — **moved into scope mid-slice as phase 3** (Oche's call, 2026-08-09). The
  original deferral reasoned that ADR-046 "accepts unbounded history for a single user"; what it
  missed is that removing the lifecycle rule *created* the gap, since nothing clears itself now.
- **History cap** — still out. ADR-027 stands as the precedent for when multi-tenant needs one.
- **B-035** (JSON import), **B-038** (CSP), **B-013** (embedding-heavy reads) — consciously left.

### Exit criteria

- `GET /resumes` returns real history, newest-first, projected — verified against a deployed run.
- A completed run writes both items; a **failed** run writes only the trace. Both asserted in tests.
- `resumes/` objects no longer carry an expiration rule; `uploads/` still expires at 1 day.
- **B-022:** tailored bullets copyable as plain text — FR-5.3 fully met for the first time.
- Résumés rebuilt at ≥1280px and stacked cleanly at 375px, in **both** themes; zero horizontal
  overflow at 360px, re-measured rather than assumed.
- **No hex outside `index.css`** — the one surviving exception (`resume.css`'s print white) resolved
  either way, not left undecided.
- **B-036 closed and *checked*, not assumed:** the `:root` shim block gone, `.legacy-view` gone from
  `App.css`, the `App.test.tsx` carve-out gone. Verify with the grep recorded in the `index.css`
  comment. *(Slice 2's lesson: the "four of five aliases" criterion was written on an unverified
  assumption. Criteria asserting facts about the codebase get verified when written.)*
- Exactly one `<h1>`; live region announces generation state.
- Backend, frontend and integration suites green; new tests **mutation-verified** — break the code,
  confirm the test notices. `npm run build` run before pushing (`npm test` does not typecheck).
- Deployed to dev and exercised in a browser **after** the last shared-container change.

### Evaluation

**Every exit criterion above is met**, with two qualifications stated rather than glossed. `GET
/resumes` returns real projected history verified against a deployed run; both-items-on-success /
trace-only-on-failure is asserted; the `resumes/` expiry is gone and `uploads/` still expires at one
day; B-022 completes FR-5.3; the view holds at 1280px and 375px in both themes with zero horizontal
overflow across 24 measured combinations; B-036 is closed and *grep-verified*, not assumed. The
qualifications: **B-043** (the 50-row list cap) means "history is permanent" is true of the data and
not yet of the *list*, and the phase-3 delete fixes are **not yet deployed** — the SSO session
expired at wrap, so the code review's three delete-path fixes are green locally and untested against
live AWS. That is the one thing in this slice not verified end-to-end, and it is the newest code in
it.

**Cost: $0 added infrastructure.** The slice's Bedrock spend was one `--expensive` verification run
at **$0.116** (74s, 20,455 tokens) plus ~$0.01 of Haiku round-trips. Removing the `resumes/`
lifecycle rule adds S3 storage that grows without bound, which sounds like a cost change and is not
at this scale: six résumés are well under a megabyte, against a bucket costing under $0.01/month.
Bedrock remains ~87% of the bill and the résumé agent remains the only thing that meaningfully
spends. Deletion, added mid-slice, is now the only mechanism that reclaims any of it.

**One thing to improve.** Three of the four dire findings were in `_delete`, which was added
mid-slice on the same day it was reviewed — and the tell was visible before the review ran: I wrote
a docstring arguing carefully for *why* S3 must be deleted first, then wrote code whose error
handling silently opted out of that argument, and a test double whose return shape made the gap
invisible. **The reasoning was in the comment and not in the code, and the test agreed with the
comment.** The generalisable habit is that when a function's docstring makes a safety argument, the
test for it should be written against the *real* API's response shape — here, one dict key
(`Errors`) was the entire difference between a correct implementation and a permanent-data-loss
path that passed a green suite.

---

## Post-MVP parking lot

Not scheduled; revisit at slice 9 / v1.1 planning.

- **CI/CD** — GitHub Actions, OIDC → AWS, `sam build/deploy` + S3 sync + CloudFront invalidation
  (arch §5.7 defers this explicitly).
- **Requirements §3 deferred list** — ~~voice-mode ingestion (ADR-014)~~ **→ graduated to v1.1**,
  multi-tenant, email/Drive output delivery, DOCX export, portfolio-page generator, business-card
  export, cert-study planner, mobile push, interview prep, named-entity verification of generated
  resumes.
- **Stretch (requirements §7)** — timeline visualization; goal tracking with progress indicators
  (GOAL entity is data-model + ingestion-tag only at MVP).
- **Custom domain** — slice 4 shipped the default `*.cloudfront.net` domain (ADR-019 amendment);
  Route 53 + ACM + alias records + Cognito callback-URL updates are the deferred v1.x upgrade.
- **CONVO history growth** — no TTL on chat messages at MVP; fine single-user, revisit before
  multi-tenant.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-10 | Initial roadmap. Slice order and FR-6.1-stays-in-MVP decided with Oche. Slice 1/2a completion notes migrated from CLAUDE.md. |
