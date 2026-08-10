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
| Résumé (history record) | `USER#<user_id>` | `RESUME#<run_id>` (**no TTL** — ADR-046) |
| Resume run trace | `USER#<user_id>` | `RESUMERUN#<run_id>` (TTL 30 days) |
| Check-in audit log | `USER#<user_id>` | `CHECKINLOG#<run_id>` |

All generated IDs are ULIDs (lexicographically time-sortable). Entry subtypes: JOB, PROJECT, MILESTONE, CERT, AWARD, EDUCATION, VOLUNTEER, HOBBY. Per-type schemas in architecture Section 2.7.

## AI prompting patterns

- All Bedrock calls go through `careervault.bedrock_client` in the shared layer
- Converse API for Claude (Haiku, Sonnet); InvokeModel API for Titan embeddings
- Structured output via tool use rather than JSON-prompt — see architecture Section 3.1.2 and 3.2
- The resume agent (Section 3.2) is the most complex flow: six phases, bounded loop with explicit termination conditions, action tracking, progress tracking, HITL at input/output gates only

## Cost constraints

- **$5/month hard ceiling** (NFR-1.1). Tightened from $10 after the account lost its free tier on
  joining an AWS Organization. **July 2026 — the heaviest month — came in at $3.88.**
- **The ceiling constrains Bedrock call volume, not how much infrastructure exists.** Bedrock is
  ~87% of the bill; *all* deployed services combined are under **$0.01/month**. This reframing is
  what decided ADR-041 (a second stack is nearly free, so prod-vs-dev turns on operational cost) and
  ADR-042 (integration tests must be tiered).
- Measured per operation: chat Q&A **~$0.006** · check-in email **~$0.0026** · tailored résumé
  **$0.11–$0.35**. The résumé agent is the only thing that meaningfully costs money, and **its cost
  scales with corpus size** — the app gets pricier as it becomes more useful (B-004, B-020).
- Guards: AWS Budget `careervault-monthly-5usd` (alerts ~$1/$4/$5 + forecast); prod-gated billing
  alarms at $3/$5 (arch §4.1.4); 14-day log retention; per-Lambda reserved concurrency live via
  `samconfig.toml` (ADR-030, §4.7.4).

## Current phase

**v1.1 slice 3 complete (Résumés + résumé history — PR #49). Next: v1.1 slice 4 — voice capture.**
Slices 1 and 2 shipped as PR #43 and PR #48. **The redesign is now complete across all six views**,
and the scaffolding that carried it is gone: **B-036 is closed** — zero shim aliases in `index.css`,
no `.legacy-view` in `App.css`, and no raw hex outside `index.css`. Phase 2 / MVP was declared
2026-07-29 (slice 9, PR #32).

**What slice 3 changed that outlives it (ADR-046):** résumés are now a **durable** `RESUME#<run_id>`
record, split from the 30-day `RESUMERUN#<run_id>` trace, and the `resumes/` S3 lifecycle rule is
gone. Three consequences a future session will trip over:

- **Nothing expires résumé artifacts any more.** That is the point, but it means a failed record
  write orphans S3 objects permanently (**B-039**), and the `--expensive` tier needs its cleanup
  fixture or it leaks test data into the bucket.
- **`DELETE /resumes/{run_id}`** exists and is the only thing that clears a résumé (ADR-046
  amendment 2). It removes S3 artifacts first, then the record, then the trace.
- **`GET /resumes` returns a projection**, not whole items — deliberately, so a pasted job
  description is not shipped on every row.

**Read before touching the frontend:**
[`docs/design/v1.1-redesign/README.md`](docs/design/v1.1-redesign/README.md) (the design handoff) and
[`pre-redesign-audit.md`](docs/design/v1.1-redesign/pre-redesign-audit.md) (18 ranked findings, all
addressed or backlogged). Two things that still bite:

- **The handoff is a proposal, not a contract.** Claude Design was given the repo and filled gaps
  with plausible features that do not exist — gap analysis, streak-break reminders, JSON export,
  account deletion. Build what exists, defer the rest, **never fabricate the data in between**
  (ADR-045; B-015 is the precedent). Slice 3 applied this to the **Sent** and **Draft** résumé
  badges: no send path and no draft state exist, so only *Latest* and *New* shipped.
- **`index.css` is the only file that may define a colour** — now enforceable, since the shim is
  gone. A raw hex in a feature stylesheet is a light-mode bug that dark-mode review cannot see.
  Both themes ship (ADR-044), and users can now pick one explicitly: Light/Dark/System on Details,
  persisted to `localStorage` and applied by a **pre-paint inline script in `index.html`** that must
  stay synchronous and outside the bundle, or the first frame flashes the wrong theme.

Remaining v1.1 scope in `docs/careervault-plan.md` § "v1.1 — graduated scope":

1. **Voice capture (slice 4, next)** — ADR-014, already decided: browser Web Speech API, explicitly
   not Amazon Transcribe. Adds **$0**; the transcript enters the existing `POST /chat` path.
   Frontend-only, zero backend surface. Slice 3 recorded the seam Oche asked for — a
   `DictationProvider` interface with an **optional** `onInterim`, so a buffer-then-POST cloud API
   could satisfy the same contract later — as an **amendment to ADR-014**, not a new ADR. Nothing
   paid is wired now, and anything paid breaks ADR-014's cost premise.
2. **Résumé speed** — B-023 first (measure; NFR-2.1/2.3 have no numbers, and optimising without a
   baseline ships changes that only *feel* faster), then B-020/B-004 (one mechanism — the retrieval
   loop's growing history drives both cost and latency). ~~B-022~~ closed in slice 3.
3. **UI + mobile pass** — B-001 plus NFR-6.2. Slice 3 measured **24 combinations** (6 views × 2
   themes × 2 widths) with zero horizontal overflow, so this is now narrower than the ❓Unverified
   scorecard entry suggests. Enumerate with Playwright MCP before styling.

**Read at session start:** the plan doc's status board + current slice section. Per-slice history,
completion notes, and the reasoning behind every past decision live there and in the ADL — not here.

## Standing constraints (these will bite you)

Each of these caused, or would have caused, a wrong action. Detail is in the linked source.

| Constraint | Where |
|---|---|
| **`careervault-dev` IS the MVP stack.** Not an unfinished promotion — do not deploy prod. | ADR-041 |
| **A prod stack cannot currently deploy.** `CheckinEmailIdentity` isn't env-suffixed and SES identities are unique per account+region, so it collides with dev's. | B-021 |
| **Sonnet 5 is ungrantable on this account.** A commercial-agreement wall, not a misconfiguration. Stop probing; runs on Sonnet 4-6. | B-010 |
| **`required` in a Converse tool schema is a hint, not a constraint.** Validate what makes output *useful*; default what merely makes it *polished*. | ADR-021 |
| **Haiku at temperature 0 is not deterministic.** Structured-output flows need a retry or salvage path. | memory |
| **IAM cannot scope a sort-key prefix.** `LeadingKeys` scopes the partition key only, and one user is one partition — so "this Lambda only touches `CONVO#`" is a *code* invariant, never an IAM one. | arch §4.2.3 |
| **A latency requirement and a delivery model are not independent choices.** Anything over API Gateway's 29s timeout cannot be synchronous. | ADR-037 |

## Testing

663 tests. **The default run of every suite is free** — that is deliberate, because a suite that
costs money is a suite people avoid, and an avoided test still implies coverage nobody has (ADR-042).

```bash
./scripts/run-tests.sh                    # 417 backend unit                        $0
cd frontend && npm test                   # 189 component (Vitest + RTL)            $0
./scripts/run-integration.sh              # 57 · DynamoDB Local + deployed dev      $0
./scripts/run-integration.sh --bedrock    # + real Haiku round-trips           ~$0.01
./scripts/run-integration.sh --expensive  # + a full Sonnet résumé run         ~$0.11
```

- Backend + frontend tests gate every PR in CI. Integration tests are local-only.
- **Never `python -m pytest` directly** — it misses the venv deps; use `./scripts/run-tests.sh`.
- Writing frontend tests: stub `fetch` (`src/test/http.ts`), don't mock the api module. A `vi.fn()`
  returning a rejected promise fails the test *even when the component catches it correctly*.
- **`npm test` does not typecheck.** Vitest transpiles without checking, so a test file can pass the
  suite and still fail CI at `tsc -b` (v1.1 slice 2 hit exactly this: a `vi.fn(() => …)` with no
  declared parameter has call tuple `[]`, so reading `calls[0][0]` is a type error). Run
  `npm run build` before pushing — it is the same `tsc -b` CI runs.
- **A green suite is not evidence a new test works.** Break the code deliberately and confirm the
  test notices; slice 2's fifteen review findings all passed a green suite before they were fixed.

## Session rituals

- **`/start-slice`** and **`/wrap-slice`** (project skills in `.claude/skills/`). **Invoke them; do
  not reproduce their steps from memory** — that is how slice 8 shipped without a code review.
  `/wrap-slice` blocks on: green tests, **both** reviews having *run*, and docs current.
- **`/explain-diff`** renders an interactive explainer into `docs/explanations/`. This project is an
  AWS-learning vehicle — run it on any slice the user wants to understand rather than just merge.
- New decision not covered by the architecture doc? **Write the ADR in `careervault-adl.md` before
  the code.** When live AWS behavior contradicts a doc, say so plainly and correct the doc.

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
