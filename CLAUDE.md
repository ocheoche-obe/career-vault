# CareerVault — Project Context for Claude Code

> This file is loaded at the start of every Claude Code session. Keep it current
> as the project evolves. The phase marker at the bottom is especially important.

## What this app does

CareerVault is an AWS-native career tracking application. Users log career milestones
(awards, certs, projects, jobs, education, volunteer work) over time via a conversational
chat interface. The app stores this history and uses AI to generate tailored resumes for
specific job descriptions on demand. Periodic check-in emails nudge the user to capture
new accomplishments while they're fresh.

Single-user MVP per ADR-006 and ADR-007, with the data model designed to be multi-tenant-ready.

## Canonical docs (always trust these first)

- **`docs/careervault-architecture.md`** — full architecture document (v1.0, complete). Authoritative source for system design, data model, sequence diagrams, cross-cutting concerns, and SAM template structure.
- **`docs/careervault-plan.md`** — implementation plan & roadmap. Authoritative for slice order, per-slice scope/exit criteria, status, and completion notes.
- **`docs/careervault-requirements.md`** — functional and non-functional requirements (v0.4, complete).
- **`docs/careervault-adl.md`** — Architectural Decision Records. The "why" behind every significant choice.
- **`docs/careervault-glossary.md`** — terms, AWS services, cross-cloud parallels.
- **`docs/render_architecture.py`** + **`careervault_architecture.png/pdf`** — system architecture diagram (regenerable).

When making implementation decisions, consult the architecture doc first. If something
seems off or unclear, the ADL captures the reasoning behind it.

## Architecture summary

- **Frontend:** React + Vite (ADR-003), hosted on S3 + CloudFront with Origin Access Control (ADR-019). Cognito Hosted UI with OAuth2 Authorization Code + PKCE for auth (ADR-025).
- **API:** AWS API Gateway (REST) with Cognito JWT authorizer.
- **Backend:** Python 3.13 Lambda functions (ADR-002), ARM64 architecture, packaged via AWS SAM (ADR-004).
- **Database:** DynamoDB single-table design (ADR-005), table name `CareerVaultTable-${Environment}`. No GSIs at MVP (ADR-028). Hard delete with UI confirm (ADR-027). PITR + Deletion Protection enabled (Section 4.7.3).
- **Storage:** S3 bucket `careervault-data-${Environment}-${AccountId}` with prefixes `uploads/` (user uploads) and `resumes/` (generated PDFs). SSE-S3 encryption (Section 4.4.3).
- **AI:** Amazon Bedrock via Converse API (ADR-017). Claude Haiku for cheap tasks, Sonnet for high-value reasoning (ADR-009). Titan Text Embeddings v2 for semantic retrieval (ADR-016). Synchronous embedding generation in the write path (ADR-024).
- **Notifications:** EventBridge Scheduler → `checkin_lambda` → Claude Haiku → SES. Bounce/Complaint events route via SNS → `ses_event_handler` (Section 4.5).
- **Region:** `us-east-1` only (ADR-012).

## AWS account & profile (check before any AWS command)

CareerVault lives in AWS account **`768396678224`**, region **`us-east-1`**, reached via the
**`careervault-dev`** SSO profile. A second project shares the same SSO login but a *different*
account under the same Organization — so **always prefix AWS/SAM commands with
`AWS_PROFILE=careervault-dev`** and never rely on a default profile. Before deploying, assert the
account resolves to `768396678224`. A `SessionStart` hook (`.claude/settings.json` →
`.claude/check-aws-profile.sh`) and `/start-slice` step 3 both run this check.

## Lambda functions

Seven Lambdas total. Per-function purpose, IAM, and event sources in architecture doc Section 4.2:

1. `chat_lambda` — parses chat messages into entry candidates via Claude Haiku + tool use
2. `career_crud` — entry create/read/update/delete; embeds at write time
3. `resume_agent` — agentic resume generation loop (ADR-010); the only Lambda with the WeasyPrint layer
4. `resume_upload_parser` — parses uploaded PDF/DOCX resumes into entries
5. `settings_lambda` — profile/settings reads and writes
6. `checkin_lambda` — scheduled check-in email composition and send
7. `ses_event_handler` — handles SES Bounce/Complaint events from the SNS topic

## Lambda layers (ADR-023)

Two layers, both built via SAM:

- **`careervault-shared`** (attached to all 7 Lambdas) — Pydantic models, Bedrock client wrapper, DDB helpers, embedding helper, observability helpers built on `aws_lambda_powertools`. Source in `backend/shared/python/careervault/`.
- **`careervault-weasyprint`** (attached only to `resume_agent`) — WeasyPrint + system deps (Pango, Cairo, GDK-PixBuf). Built via SAM Docker `BuildMethod: makefile`. Source in `infrastructure/weasyprint-layer/`.

## Repository layout

```
backend/functions/<lambda_name>/    # One folder per Lambda with handler.py + requirements.txt
backend/shared/python/careervault/  # Source for careervault-shared layer
frontend/                            # React + Vite app
infrastructure/template.yaml         # SAM template (single template, not nested)
infrastructure/samconfig.toml        # Per-env deploy config (dev / prod)
infrastructure/weasyprint-layer/     # Docker-built WeasyPrint layer
tests/                               # Unit and integration tests
docs/                                # Architecture, requirements, ADL, glossary
CLAUDE.md                            # This file
```

## Python conventions

- Python 3.13 runtime on ARM64
- Lambda handlers: `handler(event, context) -> dict` with `{"statusCode": int, "body": json.dumps(...)}`
- Shared code imported as `from careervault import bedrock_client`, `from careervault.pydantic_models import EntrySchema`, etc. — the layer mounts at `/opt/python/`
- Use `boto3` for all AWS SDK calls
- Use `aws_lambda_powertools` (`Logger`, `Tracer`, `Metrics`) — Logger fields and metric conventions in architecture Section 4.1.1
- All DynamoDB writes use the SK-prefix-scoped helpers from `careervault.ddb_helpers` (defense-in-depth per architecture Section 4.2.4)
- User ID extracted from JWT claims at handler entry — never from request body

## DynamoDB design (summary; full detail in architecture Section 2)

Single table: `CareerVaultTable-${Environment}`

| Entity | PK | SK |
|---|---|---|
| Profile / Settings | `USER#<user_id>` | `PROFILE` |
| Entry (any subtype) | `USER#<user_id>` | `ENTRY#<entry_id>` |
| Goal | `USER#<user_id>` | `GOAL#<goal_id>` |
| Conversation message | `USER#<user_id>` | `CONVO#<session_id>#<message_id>` |
| Resume run trace | `USER#<user_id>` | `RESUMERUN#<run_id>` (TTL 30 days) |
| Check-in audit log | `USER#<user_id>` | `CHECKINLOG#<run_id>` |

All generated IDs are ULIDs (lexicographically time-sortable). Entry subtypes: JOB, PROJECT, MILESTONE, CERT, AWARD, EDUCATION, VOLUNTEER, HOBBY. Per-type schemas in architecture Section 2.7.

## AI prompting patterns

- All Bedrock calls go through `careervault.bedrock_client` in the shared layer
- Converse API for Claude (Haiku, Sonnet); InvokeModel API for Titan embeddings
- Structured output via tool use rather than JSON-prompt — see architecture Section 3.1.2 and 3.2
- The resume agent (Section 3.2) is the most complex flow: six phases, bounded loop with explicit termination conditions, action tracking, progress tracking, HITL at input/output gates only

## Cost constraints

- **$5/month effective hard ceiling.** The account lost its 12-month free tier / credits when it
  joined an AWS Organization (now paid), so the project tightened the original $10 NFR-1.1 ceiling
  to $5. Bedrock usage (future slices) is the dominant cost driver; the deployed infra is ~cents/mo
  at idle.
- Guards in place: an account-wide **AWS Budget** `careervault-monthly-5usd` (email alerts at ~$1 /
  $4 / $5 + forecast); template billing alarms tightened to **$3 warning / $5 critical** (prod-gated,
  arch §4.1.4); 14-day CloudWatch log retention.
- Reserved concurrency is a per-Lambda runaway-cost guard (§4.7.4), parameterized per ADR-030
  (template default `-1` = off). The account's Lambda quota was restored to 1000, so the caps are
  **live** via `samconfig.toml`: chat/career_crud/settings = 5, `resume_upload_parser` = 2,
  `resume_agent` = 2 (ADR-037 — needs room for an async worker + a fresh POST/GET).
- **Resume agent = dominant Bedrock cost driver.** A tailored-résumé run is ~70K tokens / **~$0.31**
  on Sonnet 4-6 (~16 runs/month within $5); the per-run token ceiling is 150K (~$1) + reserved
  concurrency 2 (ADR-036/037). Sonnet 5 is *not grantable* on this account (`agreement: NOT_AVAILABLE`)
  — 6a runs on the newest accessible Sonnet, 4-6.

## Current build phase

**Phase 2 — Implementation COMPLETE. 🎉 MVP declared at slice 9 (2026-07-29). Next: v1.1 planning — scope and slice the three graduated themes in `docs/careervault-plan.md` § "v1.1 — graduated scope". (1) **Résumé speed + usability** — B-023 first (measure, since NFR-2.1/2.3 have no numbers and optimising without a baseline ships changes that only feel faster), then B-020/B-004 (one mechanism: the retrieval loop's growing history drives both cost and latency), then B-022 (copyable plain-text bullets — cheapest real win). (2) **UI + mobile pass** — B-001 plus NFR-6.2, which the scorecard marks ❓Unverified, not ✅; start by *enumerating* with Playwright MCP rather than styling. (3) **Voice capture** — ADR-014, already decided: browser Web Speech API, explicitly not Amazon Transcribe, so it adds **$0** to the bill and the transcript enters the existing `POST /chat` path. ⚠ Two standing constraints for any v1.1 work: **`careervault-dev` IS the MVP stack** (ADR-041), and **a prod stack currently cannot deploy** (B-021 — the SES email identity is not env-suffixed and collides with dev's), which becomes a blocker the moment ADR-041 reverses.**

- Last completed: slice 9 — hardening & MVP close. **461 automated tests** (was 370), every default
  run **$0**, tiered by cost (**ADR-042**): 376 backend unit · 23 frontend (Vitest + RTL, new) · 56
  integration (DynamoDB Local + deployed dev) · 5 `--bedrock` (~$0.01) · 1 `--expensive` (~$0.11).
  *A uniform suite at ~$0.35/run is ~14 runs to the ceiling — and an avoided test is worse than an
  absent one, because it still implies coverage.* Five things worth carrying. **(1) A `vi.fn()` that
  returns a rejected promise fails a Vitest test even when the component catches it** — the spy's
  settlement tracking leaves an unhandled derived chain; reproduces with *zero assertions in the test
  body*, vanishes without the module mock. Every error-path test is unwritable that way. Fix was
  better than the original plan: stub `fetch`, keep the real `lib/api`, which puts the
  201/200/409/422/500 mapping under test and lets assertions check the **actual request body**.
  **(2) The ADR-041 prod dry run found a blocker — and not the one it was run to check.**
  `AWS::EarlyValidation::ResourceExistenceCheck` failed with **no detail in `describe-stack-events`
  or `describe-change-set-hooks`**; diagnosed by re-running the identical template with one parameter
  changed. `CheckinEmailIdentity` isn't env-suffixed (unlike the ConfigurationSet right below it) and
  SES identities are unique per account+region, so **prod could never have deployed** (B-021). Once
  unblocked: 70 resources, billing alarms validate. *A conditional never evaluated is not "probably
  fine" — it is untested code.* **(3) A falsified requirement scores itself green.** §7.4 and NFR-2.2
  promised a résumé in 30s; measured 72s/176s, and it was *structurally impossible* — over API
  Gateway's 29s timeout nothing can be synchronous, which is what forced ADR-037. Slice 6b fixed the
  parallel claim in arch §3.2.2 **and stopped there**. *Correcting the description while leaving the
  specification is the more dangerous half to skip* — and the fix specifies async-with-a-ceiling, not
  a bigger number, because **a latency requirement and a delivery model are not independent
  choices.** **(4) Cost and latency are one problem:** 72s/20.2K tokens/$0.113 on a 2-entry corpus vs
  176s/82.9K/$0.35 on 13 — *same `REVISE` verdict*, so it is corpus size, not a cheaper path. **The
  app gets slower and more expensive precisely as it becomes more useful** (B-004 + B-020).
  **(5) Tooling caught my bugs, re-reading didn't:** a delete test asserted `204` where the API
  returns `200`; `tsc` caught an `ErrorContext`/`Error` mismatch the tests accepted; a
  "rejects invalid input" test passed for the *wrong reason*; and `"${ARR[@]:-}"` under `set -u`
  silently widened collection to 401 tests instead of 25. Two of three `--expensive` failures were
  *contract* errors, now guarded for **$0** — *on an endpoint that costs money, the request contract
  deserves a free test of its own.* **Audit:** 5/6 success criteria (the 6th passed only after
  correcting it), 20/22 FRs, 16 NFRs met / 4 caveated / 3 unverified. **Cost $3.88/$5.00** in the
  heaviest month — Bedrock **87%**, all infra **under $0.01 combined**, the reframing behind both
  ADR-041 and ADR-042. Closed B-014/B-017/B-018; opened B-020..B-024. Playwright MCP added as a
  dev-loop tool (deliberately *not* a CI gate).
- Before that: slice 8 — check-in emails (FR-4). EventBridge Scheduler fires `checkin_lambda`
  daily at 23:00 UTC; **`next_checkin_at` on the PROFILE paces the cadence**, so all four FR-4.1
  cadences run off one schedule and a cadence change is a data write, not a control-plane call
  (**ADR-039**). Three things worth carrying. **(1) `required` in a Converse tool schema is a hint,
  not a constraint.** The first personalized send returned a complete email that omitted `sign_off`
  — a `required` field — and validation rejected it, dropping a good email to the static fallback;
  the generic send a minute earlier had included it, same prompt, temperature 0. Fix was a split,
  not a looser schema: `subject`/`prompts` strict, `greeting`/`sign_off` defaulted. *Validate what
  makes output useful; default what merely makes it polished* — and note the downgrade is
  **invisible** without a metric, because the email still arrives (**ADR-021** addendum).
  **(2) The docs described two fields that never existed** — `checkin_time_local` and
  `aspirational_goal` — which is B-008's failure mode repeating twice in one feature. One was added
  (the generic fallback is inert without it), one deliberately not. *Prose describing a data model
  drifts silently, because nothing fails when a field in a sentence never becomes a field in a
  schema.* **(3) Idempotency has a price:** claiming the send slot before calling SES means a failed
  send consumes the cycle; claiming after would duplicate on a Scheduler retry. *At most once is
  bought by giving up at least once* — right for a nudge, wrong for anything transactional (B-016).
  **ADR-040** closed **B-014**: nested `settings` merges via one dotted `SET settings.#f` path per
  sub-field, plus a *separate* idempotent seeding `UpdateItem` — a dotted path cannot be written
  into an absent attribute, and the seed cannot ride along in the same expression (DynamoDB rejects
  naming both a path and its descendant). All four premises were probed against the live table
  before the ADR was settled; the single-expression form was in the first draft as fact and was
  wrong. **Arch v2.1 corrections:** §3.3.3 and §4.5.4 both said "Query" for what is necessarily a
  `Scan` (different partition keys per user + no GSIs per ADR-028 — a GSI is what would *make* it a
  Query, not what would make it faster); §4.5.4's IAM row gains `dynamodb:Scan`. All three tiers,
  both idempotency layers, pause, cadence pacing, and the full SES→SNS→handler bounce path verified
  live. Measured **~$0.0026/check-in** (~$0.01/mo weekly). SES stays in **sandbox** — sufficient for
  one verified recipient, and note identity verification is a **manual link click** CloudFormation
  cannot complete. Deferred: B-016..B-019.
- Interlude after slice 7: **B-008 closed** (PR #30) — generated résumés had no identity header.
  The backlog's proposed fix ("take identity from the JWT") turned out **insufficient**: Cognito
  holds only `email`/`email_verified`/`sub` — no name — and the `Profile` model had neither `name`
  nor `location`, the two fields `_contact_from_profile` reads. Real fix was three-part: those two
  model fields, a `PUT /settings` route to write them (the `UpdateItem` grant had been sitting
  unused since slice 1), and a "Details" view. JWT email is the *fallback*, not the answer. Also
  fixed a latent slice-1 bug it surfaced: `settings/handler.py` hardcoded `http://localhost:5173`
  as its allow-origin instead of reading `CORS_ALLOW_ORIGIN` like every other Lambda does after
  ADR-034, so `GET /settings` would have failed CORS from CloudFront — invisible until something
  called the route. `tests/conftest.py` now uses the *deployed* wildcard so that class of bug fails
  a test. Verified live: header renders **"Oche Obe"** with email + location beneath.

- Before that: slice 7 — chat over your data (FR-6.1). `chat_lambda` now routes a message to
  entry-parsing **or** grounded Q&A via a third *control-flow* tool, `answer_question`, with
  `toolChoice=any` **retained** (**ADR-038**). A Q&A turn is route (Haiku) → Titan embed →
  `rank_by_similarity` top-k **in-Lambda** → synthesis (Haiku, **no tools**); ingestion is
  unchanged from 2b. Two things worth carrying: **(1) the corpus census.** Semantic top-k is the
  wrong index for counting — hand a model k entries and it answers "k" — so every synthesis prompt
  carries counts by `entry_type` over the *whole* corpus, computed in Python. Live proof: top-k
  returned 8 entries of which 4 were certs, and "how many certifications do I have?" answered **4**.
  *Let Python count, let the model narrate.* **(2) The IAM widening this slice was supposed to make
  did not exist.** Chat's `dynamodb:Query` grant was always unconditional on the table ARN, so
  `ENTRY#` reads were permitted since slice 2; the only real policy delta is Titan `InvokeModel`.
  §4.2.3's "chat can only touch `CONVO#`" was never enforceable in IAM (one PK per user;
  `LeadingKeys` scopes the partition key only) and was always an application-code invariant —
  **a least-privilege boundary IAM cannot express is a code invariant wearing an IAM costume**
  (arch v2.0 corrects §4.2.3). Injection controls that *are* real and test-pinned: no `toolConfig`
  on the synthesis call, model-free retrieval, privilege separation across the two calls,
  answers rendered as text never markdown. Security review found one LOW issue (delimiter
  defanging covered only `<entry>`, not the outer block tags) — **fixed in-slice**. Measured
  **~$0.006/Q&A turn**. Deferred: B-011 hybrid retrieval for aggregates (the `intent` field ships
  reserved), B-012 keep answers plain-text, B-013 full-corpus read weight. Before that: slice 6b —
  resume agent output UI (FR-5.3/5.4). The `Résumé` tab runs the ADR-037
  async flow end to end: JD input → `POST` `202 {run_id}` → 3s poll with an elapsed counter → iframe
  HTML preview + PDF download + Regenerate. Two of its four slice-start decisions turned out to be
  *backend* work, which is the lesson: **the PDF presign needed a `Content-Disposition: attachment`
  override** (HTML's `download` attribute is ignored cross-origin, so the button opened a tab
  instead of saving), and the preview uses an **iframe `src`** because the data bucket's CORS is
  PUT-only — an iframe navigation isn't subject to CORS, and it keeps agent-generated HTML out of
  the app's origin. `run_id` lives in `sessionStorage` so a mid-run reload re-attaches to a paid run
  instead of orphaning it. **ADR-015 amended:** `resumes/` now expires on a flat 30-day lifecycle
  matching the RESUMERUN TTL — the original "keep the newest indefinitely, 7 days for the rest" is
  not expressible as an S3 lifecycle rule. **Arch v1.9 correction:** §3.2.2's "under 90 seconds per
  run" is wrong; measured ~176s, which is exactly why generation is async. Measured run: 82.9K
  tokens / **$0.35** (a `REVISE` run — the realistic upper end vs 6a's 70K/$0.31 `PASS` baseline).
  Deferred: the run-metadata row is developer-facing and the elapsed timer disappears on completion
  → backlog B-006/B-007. Before that: slice 6a — resume agent backend loop (ADR-036/-037; arch §3.2 corrected). The
  `resume_agent` Lambda runs the six-phase bounded loop (Haiku analyze → Sonnet 4-6 retrieve/draft/
  critique/revise → deterministic HTML+PDF finalize) as an **async job** (ADR-037: `POST
  /resumes/generate` → `202 {run_id}` + self-invoked worker; `GET /resumes/{run_id}` polls,
  presigns 1h URLs). New: `careervault-weasyprint` layer (Docker/makefile, renders PDF on arm64),
  RESUMERUN trace items (table TTL), Bedrock Sonnet IAM. **Sonnet 5 ungrantable on this account →
  runs on Sonnet 4-6** (ADR-036 live-access correction). Measured ~70K tokens / **$0.31** / ~176s
  per run after tuning (`max_iterations 15→8`, `max_revisions 2→1`). Deployed to dev; async
  start→poll→**valid PDF** smoke-verified. Retrieval-loop context growth (dominant cost) → backlog
  B-004. Before that: slice 5 — resume upload bootstrap (ADR-035; arch v1.7). Private S3 data bucket
  (`careervault-data-${Env}-${AccountId}`, `uploads/`+`resumes/`) + `resume_upload_parser` owning
  `POST /uploads/presign` and `POST /uploads/parse` — a **parse-only** Haiku transform (no Titan, no
  DDB grant): presigned PUT → parse to entry candidates → select-all review table → saved through
  the existing `POST /entries` (the single embedding site). Pure-Python extraction (pypdf + stdlib
  `zipfile`/`xml.etree` for DOCX — deliberately no python-docx/lxml). Deployed to dev, backend +
  UI smoke passed; parse ~3.4–4s (sync route holds). Dedup-precision gap for exact-identity certs
  → backlog B-003. Before that: slice 4 — frontend hosting (S3 + CloudFront via OAC; ADR-019
  amendment; ADR-034 wildcard CORS; arch v1.5, PR #20); slice 3 — entries dashboard + CRUD (ADR-033;
  arch v1.4, PR #4); 2b chat UI (PR #3); 2a chat backend (PR #2); 1 auth + settings (PR #1).
- **The roadmap lives in `docs/careervault-plan.md`** — slice order, per-slice scope, exit
  criteria, open ⚠ decisions, and completion notes (including the slice 1/2a details and the
  Bedrock gotchas that used to live here). Read the status board + current slice section at
  session start; update it when a slice wraps.
- Session rituals: `/start-slice` and `/wrap-slice` (project skills in `.claude/skills/`).
- Learning artifacts: `/explain-diff` renders an interactive explainer for a slice/PR (background →
  intuition → code walkthrough → quiz) into `docs/explanations/`. This project is an AWS-learning
  vehicle; run it on any slice the user wants to understand rather than just merge.

Refer to the architecture doc as you implement. If a decision needs to be made that isn't covered, capture it as a new ADR in `careervault-adl.md` before coding it in.

## AWS Guidance

- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed
  execution, observability, and audit logging. If unavailable, use the
  AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available.
  Load the skill with `retrieve_skill` and prefer its guidance over
  general knowledge.
- When uncertain about specific AWS details (API parameters, permissions,
  limits, error codes), verify against documentation rather than guessing.
  State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or
  CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework
  principles.
- Do not use em dashes in AWS resource names or descriptions. Use
  hyphens instead.

### Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret,
  credential, API key, token, or password task. MUST NOT call
  `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST
  NOT hit the Secrets Manager Agent daemon directly. MUST use
  `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with
  `asm-exec` so the secret resolves at runtime without entering context.
