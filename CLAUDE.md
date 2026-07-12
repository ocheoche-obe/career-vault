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
- Reserved concurrency is a per-Lambda runaway-cost guard (§4.7.4) but is **parameterized and off by
  default** until the account's Lambda concurrency quota (currently 10) is raised — see ADR-030.

## Current build phase

**Phase 2 — Implementation (in progress). Current slice: 3 — entries dashboard + CRUD completion.**

- Last completed: slice 2b — chat UI + turn idempotency (ADR-032), deployed to dev and
  smoke-tested from the browser. Before that: 2a chat backend (PR #2), 1 auth + settings (PR #1).
- **The roadmap lives in `docs/careervault-plan.md`** — slice order, per-slice scope, exit
  criteria, open ⚠ decisions, and completion notes (including the slice 1/2a details and the
  Bedrock gotchas that used to live here). Read the status board + current slice section at
  session start; update it when a slice wraps.
- Session rituals: `/start-slice` and `/wrap-slice` (project skills in `.claude/skills/`).

Refer to the architecture doc as you implement. If a decision needs to be made that isn't covered, capture it as a new ADR in `careervault-adl.md` before coding it in.
