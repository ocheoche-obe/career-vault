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

**Phase 2 — Implementation (in progress). Next slice: 7 — chat over your data (FR-6.1: `chat_lambda` routes a message to either entry-parsing or grounded Q&A over the user's history, reusing the ADR-016 retrieval helpers). ⚠ open decision: routing design — a third `answer_question` tool with `toolChoice=any` vs a router prompt with `toolChoice=auto`; likely an ADR before code.**

- Last completed: slice 6b — resume agent output UI (FR-5.3/5.4). The `Résumé` tab runs the ADR-037
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
