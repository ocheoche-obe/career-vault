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
| 8 | Check-in emails | FR-4 | 🔨 | — |
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

## Slice 8 — Check-in emails 🔨

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

**Completion notes:** _(filled at wrap)_

---

## Slice 9 — Hardening & MVP close ⬜ ⚠

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

**⚠ Decisions:**
- Deploy the prod stack (billing alarms are already prod-gated) vs declare dev-as-MVP for a
  single-user app. Genuine fork — cost vs realism.
- Which parking-lot items graduate to a v1.1 plan.

**Exit criteria:** every FR maps to a verified slice or a documented deferral; integration tests
runnable with one command; MVP scored against the §7 success criteria + NFRs with findings routed;
this doc's status board all ✅; MVP declared.

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
- **Custom domain** — slice 4 shipped the default `*.cloudfront.net` domain (ADR-019 amendment);
  Route 53 + ACM + alias records + Cognito callback-URL updates are the deferred v1.x upgrade.
- **CONVO history growth** — no TTL on chat messages at MVP; fine single-user, revisit before
  multi-tenant.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-10 | Initial roadmap. Slice order and FR-6.1-stays-in-MVP decided with Oche. Slice 1/2a completion notes migrated from CLAUDE.md. |
