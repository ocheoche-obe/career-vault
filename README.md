# CareerVault

AI-powered career tracking. Log your wins, milestones, and achievements over time through a
conversational interface, and use that accumulated history as context to generate tailored output —
résumés today, portfolios and other artifacts later.

Serverless on AWS: Lambda, DynamoDB, and Amazon Bedrock, packaged with SAM.

> **Status: MVP complete (Phase 2, slice 9).** Single-user by design (ADR-006/-007), with the data
> model built multi-tenant-ready.
>
> **The deployed `careervault-dev` stack *is* the MVP.** A deliberate decision, not an unfinished
> promotion — see [ADR-041](docs/careervault-adl.md). For an app with exactly one user who is also
> the developer, a second environment protects nobody and still charges a keep-in-sync tax. A
> `sam deploy --no-execute-changeset` dry run stands in for the prod deploy — and found a real
> blocker on its first run (**B-021**: the SES email identity collides with dev's, so a prod stack
> could not deploy as configured).

---

## What it does

| Capability | How |
|---|---|
| **Log by chat** | Describe something in plain language; Claude Haiku parses it into a typed entry that you review and edit before anything is saved. |
| **Ask about your own history** | "How many certifications do I have?" — answered from your entries, with retrieval done in Python and the model only narrating (ADR-038). |
| **Bootstrap from an existing résumé** | Upload a PDF or DOCX; it is parsed into entry candidates for review. |
| **Scheduled check-ins** | A personalized email at your chosen cadence referencing what you logged recently, with a fallback ladder that survives Bedrock being unavailable. |
| **Tailored résumés** | Paste a job description; a six-phase agent loop retrieves, drafts, critiques and revises, then renders an HTML preview and a downloadable PDF. |

---

## Architecture

```
CloudFront ──> S3 (React SPA)
     │
     └── Cognito Hosted UI (OAuth2 + PKCE)
              │  JWT
              v
        API Gateway (REST, Cognito JWT authorizer)
              │
    ┌─────────┴───────────────────────────────┐
    │  7 Lambdas (Python 3.13, ARM64)         │
    │  chat · career_crud · resume_agent      │
    │  resume_upload_parser · settings        │
    │  checkin · ses_event_handler            │
    └─────────┬───────────────┬───────────────┘
              │               │
     DynamoDB (single table)  Amazon Bedrock
     S3 (uploads/, resumes/)  Claude Haiku · Sonnet · Titan Embeddings

EventBridge Scheduler ──> checkin ──> SES ──> SNS ──> ses_event_handler
```

- **Region:** `us-east-1` only (ADR-012)
- **Data:** DynamoDB single-table design, no GSIs at MVP (ADR-005, ADR-028)
- **Retrieval:** Titan embeddings stored on the item, cosine similarity computed in-Lambda (ADR-016)
- **Packaging:** AWS SAM — one template, 70 resources, two Lambda layers (ADR-004, ADR-023)

Full detail is in [`docs/careervault-architecture.md`](docs/careervault-architecture.md); every
significant decision has an ADR in [`docs/careervault-adl.md`](docs/careervault-adl.md).

---

## Repository layout

```
backend/functions/<name>/            One folder per Lambda: handler.py + requirements.txt
backend/shared/python/careervault/   Source for the careervault-shared layer
frontend/                            React + Vite SPA
infrastructure/template.yaml         SAM template
infrastructure/weasyprint-layer/     Docker-built native layer for PDF rendering
tests/unit/                          Backend unit tests — no AWS, no cost
tests/integration/                   Tiered integration tests (see Testing)
docs/                                Architecture, requirements, ADRs, roadmap, scorecard
```

---

## Getting started

**Prerequisites:** AWS SAM CLI · Python 3.13 · Node 22+ · Docker (for `sam build`, the WeasyPrint
layer, and DynamoDB Local) · an AWS account with Bedrock model access in `us-east-1`.

> **Prefix AWS and SAM commands with `AWS_PROFILE=careervault-dev`.** This SSO login also reaches a
> second project in a *different* account under the same AWS Organization, so relying on a default
> profile is how work lands in the wrong account. A `SessionStart` hook asserts the account at the
> start of every Claude Code session.

```bash
# 1. Authenticate
aws sso login --profile careervault-dev

# 2. Build + deploy the stack, then write frontend/.env.local from its Outputs
make bootstrap

# 3. Create the single login user (admin-provisioned; no self-service signup, ADR-025)
make create-user EMAIL=you@example.com PASSWORD='Chang3!Me-please'

# 4. Run the SPA, then open http://localhost:5173 and sign in
make frontend-dev
```

Other targets: `make build`, `make deploy`, `make deploy-frontend`, `make deploy-all`,
`make frontend-env`, `make test`, `make help`.

Port **5173** is load-bearing — it is registered as a Cognito callback URL.

### Two steps CloudFormation cannot do for you

- **Verify the SES sender identity.** SES emails a confirmation link that a human must click. Until
  then, check-in emails will not send. SES also remains in **sandbox**, which means it can only send
  *to* verified addresses — sufficient for one user.
- **Create the Cognito user** (`make create-user`, above).

### Notes

- **Reserved concurrency is live**, not off. Per-Lambda caps are set in `infrastructure/samconfig.toml`
  as the runaway-cost guard from arch §4.7.4 (ADR-030). The template default is still `-1` (off) so
  the stack deploys on accounts whose Lambda concurrency limit has not been raised.
- **DynamoDB Deletion Protection is prod-only.** The dev table can be deleted directly
  (`cd infrastructure && sam delete`).
- **A prod stack does not currently deploy** — see B-021 above.

---

## Testing

Four layers, separated by what a run **costs**. The default is free, and that is the design: a suite
that costs money is a suite people avoid, and an avoided test is worse than an absent one because it
still implies coverage ([ADR-042](docs/careervault-adl.md)).

```bash
make test                                   # 376 backend unit tests             $0
cd frontend && npm test                     # 23 component tests (Vitest + RTL)  $0

./scripts/run-integration.sh                # 56 tests: DynamoDB Local + deployed dev  $0
./scripts/run-integration.sh --bedrock      # + real Haiku round-trips           ~$0.01
./scripts/run-integration.sh --expensive    # + a full Sonnet résumé run         ~$0.11
./scripts/run-integration.sh --all          # everything
```

The integration runner starts DynamoDB Local for you. Anything unavailable — Docker down, expired
SSO, wrong AWS account — **skips with a reason** rather than failing.

Backend unit tests and frontend tests both gate every pull request in CI.

---

## Cost

**Ceiling: $5/month**, enforced by an AWS Budget (`careervault-monthly-5usd`) with email alerts and
by per-Lambda reserved concurrency.

The shape of the bill matters more than the total:

| | Share of spend |
|---|---|
| Bedrock (Sonnet + Haiku) | **~87%** |
| All deployed infrastructure combined — S3, DynamoDB, API Gateway, CloudWatch, SNS, Cognito, CloudFront | **under $0.01/month** |

**The ceiling constrains Bedrock call volume, not how much infrastructure exists.** Measured
per-operation: a chat Q&A turn ~$0.006, a check-in email ~$0.0026, a tailored résumé **$0.11–$0.35**
depending on corpus size. The résumé agent is the only thing that meaningfully costs money — and its
cost scales with how much career history you have, which is tracked as B-004 and B-020.

---

## Documentation

| Document | What it owns |
|---|---|
| [`careervault-architecture.md`](docs/careervault-architecture.md) | **How** — system design, data model, per-Lambda contracts |
| [`careervault-adl.md`](docs/careervault-adl.md) | **Why** — every significant decision, as ADRs |
| [`careervault-requirements.md`](docs/careervault-requirements.md) | **What** — functional and non-functional requirements |
| [`careervault-plan.md`](docs/careervault-plan.md) | **What order, what's done** — slice roadmap and status |
| [`careervault-mvp-scorecard.md`](docs/careervault-mvp-scorecard.md) | **How well** — the MVP scored honestly against its own requirements |
| [`careervault-backlog.md`](docs/careervault-backlog.md) | Everything deferred, with the reasoning |
| [`careervault-glossary.md`](docs/careervault-glossary.md) | Terms, AWS services, cross-cloud parallels |
| [`docs/explanations/`](docs/explanations/) | Per-slice interactive explainers |

CareerVault is also a deliberate AWS-learning vehicle. Where live AWS behavior contradicted the
design documents, the contradiction was recorded and the document corrected rather than quietly
coded around — the [MVP scorecard](docs/careervault-mvp-scorecard.md) collects the notable cases.
