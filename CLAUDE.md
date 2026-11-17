# CareerVault

A personal career log on AWS. The user describes accomplishments in chat (or uploads an old
résumé), a model proposes typed entries, and the user confirms each one before it is saved. From
that history the app answers questions, sends scheduled check-in emails, and generates résumés
tailored to a job description.

It has one user, who is also the developer, and it doubles as their AWS and AI-engineering learning
project. Explain AWS behaviour that is surprising, and when the live service contradicts a doc, say
so and correct the doc.

## State of things

- **`careervault-dev` is the real, live stack** and holds the user's only copy of their data. There
  is no prod stack and one cannot currently be created (the SES identity collides, B-021). Treat
  dev as production: no table replacement, no `sam delete`, no bulk data changes without asking.
- Current status and what is next: the status board in `docs/careervault-plan.md`, and
  `docs/fresh-eyes-review.md` for the proposed direction. Keep status out of this file.

## Layout

```
backend/functions/<name>/            7 Lambdas (Python 3.13, ARM64): chat, career_crud, resume_agent,
                                     resume_upload_parser, settings, checkin, ses_event_handler
backend/shared/python/careervault/   shared layer: bedrock_client, ddb_helpers, pydantic_models, ...
frontend/                            React 19 + Vite SPA, no router; views switch on state in App.tsx
infrastructure/template.yaml         the single SAM template
infrastructure/samconfig.toml        deploy parameters (model IDs, reserved concurrency)
tests/unit, tests/integration        backend tests; frontend tests sit beside their components
docs/                                architecture, ADRs (careervault-adl.md), plan, backlog
```

The docs are very long (the ADL alone is 3,000 lines). Search them by ADR number or backlog ID
(`ADR-037`, `B-044`); do not read them end to end.

## Commands

```bash
./scripts/run-tests.sh                      # backend unit tests, free
cd frontend && npm test                     # frontend tests, free
cd frontend && npm run build && npm run lint  # the typecheck CI runs; npm test does not typecheck
./scripts/run-integration.sh                # DynamoDB Local + deployed dev stack, free, needs SSO
./scripts/run-integration.sh --bedrock      # adds real Haiku calls, about $0.01
./scripts/run-integration.sh --expensive    # adds a full résumé run, about $0.11

make deploy            # sam build + deploy the backend to dev (needs Docker for the PDF layer)
make deploy-frontend   # build the SPA, sync to S3, invalidate CloudFront
make frontend-dev      # local SPA on http://localhost:5173 (the port is a registered Cognito callback)
```

Use `./scripts/run-tests.sh`, not bare `pytest`: it builds the venv the tests need.

## AWS access

- Account `768396678224`, region `us-east-1`, SSO profile `careervault-dev`. The same SSO login
  reaches a different project's account, so prefix every `aws` and `sam` command with
  `AWS_PROFILE=careervault-dev` and confirm the account before a deploy.
- If the session-start hook reports the profile is not authenticated, ask the user to run
  `aws sso login --profile careervault-dev`. Do not work around it.
- Prefer the AWS MCP server when it is connected, and check it for a relevant AWS skill before a
  task; otherwise use the CLI. Infrastructure changes go in the SAM template, not through one-off
  CLI calls.
- Never read a secret's value into the conversation: no `secretsmanager get-secret-value` or
  `batch-get-secret-value`. For any credential task, load the `aws-secrets-manager` skill first and
  use `asm-exec` with a `{{resolve:secretsmanager:...}}` reference. The app itself has no secrets.

## Money

The ceiling is $5 a month and nearly all of it is Bedrock. Infrastructure costs under a cent, so
adding resources is cheap and adding model calls is not. Haiku handles chat, parsing,
check-ins and the résumé critique; Sonnet is used only for the résumé agent's retrieval and
drafting. A résumé run costs roughly $0.08 to $0.35 and grows with the number of entries. Ask before running anything that spends: the `--bedrock` and
`--expensive` tiers, or generating a résumé against the live stack.

## Conventions

- `user_id` comes from the JWT claims, never from the request body.
- One table. Every item has `PK = USER#<user_id>` and an `SK` of `PROFILE`, `ENTRY#`, `CONVO#`,
  `RESUME#` (permanent), `RESUMERUN#` (30-day trace) or `CHECKINLOG#`. Generated IDs are ULIDs.
- All DynamoDB writes go through the prefix-scoped helpers in `ddb_helpers`. One user is one
  partition and IAM cannot restrict a sort-key prefix, so "this Lambda only writes `CONVO#` items"
  is enforced by that code and nothing else.
- All Bedrock calls go through `careervault.bedrock_client`. It owns retries; botocore's are off.
- Structured model output uses tool use, validated with Pydantic, with one retry on a validation
  failure. Validate what makes the output usable and default the rest.
- The chat Lambda never writes entries; only `career_crud` does, after the user confirms.
- The chat call that sees entry content is given no tools, and the client renders answers as plain
  text. Both are prompt-injection defences. Do not add a tool to that call or a markdown renderer
  to chat.
- `frontend/src/index.css` is the only file that defines colours. Light and dark themes both ship.
- Frontend tests stub `fetch` with `src/test/http.ts`; they do not mock the api module.
- The design handoff in `docs/design/` includes features that do not exist. Build what the backend
  supports and leave the rest out. Never show invented data.
- After adding a test, break the code once to confirm the test fails.

## Gotchas

**Bedrock**
- `required` in a Converse tool schema is not enforced, and Haiku at temperature 0 still varies
  between runs.
- A `cachePoint` below the model's minimum prefix (about 1,024 tokens for Sonnet, 4,096 for
  Haiku 4.5) is ignored without an error and billed in full. Confirm caching from
  `cacheReadInputTokens` in the response.
- Models are called through `us.` inference profiles, which bill about 10% above list price.
  Haiku 4.5 has no on-demand ID. Titan embeddings take one input per call.
- The résumé agent runs on Sonnet 4-6. Sonnet 5 could not be enabled on this account when last
  tried in July 2026 (B-010, a commercial-agreement block). Do not probe repeatedly; ask first.
- This area changes quickly. Check current Bedrock documentation before relying on model IDs,
  limits or prices written anywhere in this repo.

**Infrastructure**
- API Gateway cuts a request off at 29 seconds, which is why résumé generation is an async
  self-invoked job that the client polls.
- CloudFormation reuses a stack's previous parameter values. Changing a default in the template
  does nothing unless `samconfig.toml` sets the parameter.
- Résumé records and their S3 objects never expire. `DELETE /resumes/{run_id}` is the only cleanup,
  and it removes S3 objects first, then the record.

**Frontend**
- The theme is applied by an inline script in `index.html` before first paint. Keep it inline and
  synchronous.
- Do not write state from inside a `useEffect` that depends on that state. The résumé poll did this
  once and sent 18,000 requests in under two seconds.
- Dictation fills the text field and must never submit. Chrome and Safari send the audio to their
  own speech services, and the UI says so while recording; keep that disclosure.
- A zero-overflow check does not prove a mobile layout works: a button that collapses to its
  content overflows nothing. Compare against the layout before the change. All responsive checks
  so far used emulated viewports.
- `related_job_id` exists on project and milestone entries and nothing reads or sets it (B-044).

## Workflow

- Work on a branch and open a PR; CI runs the backend and frontend suites.
- `/start-slice` and `/wrap-slice` are the project's slice rituals and `/explain-diff` writes a
  learning explainer. Invoke the skills; do not re-create their steps by hand.
- Record a decision as an ADR when it would be expensive to reverse. Write it before the code.
- Do not use em dashes in AWS resource names or descriptions.
