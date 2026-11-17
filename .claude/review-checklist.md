# Review checklist: CareerVault

Read by the harness reviewer (`/harness:review-pr`) **from the PR's base branch**, so a change to
this file takes effect only after it merges. The harness supplies the procedure, the generic
checks and the report format; this file holds what is specific to CareerVault.

## Automated checks

Run from the repo root. These match CI (`.github/workflows/ci.yml`). A failing check is a blocker.

1. Backend unit tests, in a venv outside the working tree (this is what
   `./scripts/run-tests.sh` does, but that script writes `.venv-test` into the repo, which a
   read-only reviewer must not do):
   `python3 -m venv "$TMPDIR/cv-venv" && "$TMPDIR/cv-venv/bin/pip" install -q -r tests/requirements-dev.txt && "$TMPDIR/cv-venv/bin/python" -m pytest tests/unit -q -p no:cacheprovider`
2. `(cd frontend && npm ci --no-audit --no-fund && npm test)`. Report vitest's pass count.
3. `(cd frontend && npm run build && npm run lint)`. This is the typecheck; `npm test` does not
   typecheck.

Never run `./scripts/run-integration.sh`, in any tier. It needs SSO, and its `--bedrock` and
`--expensive` tiers spend money.

## Docs to read

`CLAUDE.md` (conventions and gotchas), then only what the diff touches in
`docs/careervault-architecture.md` and `docs/careervault-adl.md`. The ADL is about 3,000 lines:
search it by ADR number or backlog ID, do not read it end to end.

## Domain checks

- **Live data.** `careervault-dev` is the only stack and holds the owner's only copy of their
  data. In `infrastructure/template.yaml`, flag any change that would replace or delete the table
  or a bucket (a changed logical ID, table name, key schema or other replacement-triggering
  property, or a removed `DeletionPolicy`/`UpdateReplacePolicy`). Flag any bulk data change.
- **Identity and scoping.** `user_id` comes from the JWT claims, never from the request body.
  Every item key is `PK = USER#<user_id>`. All DynamoDB writes go through the prefix-scoped
  helpers in `ddb_helpers`; a direct `put_item`/`update_item`/`delete_item` elsewhere is a finding,
  because IAM cannot enforce the sort-key prefix.
- **Write paths.** The chat Lambda never writes entries; only `career_crud` does, after the user
  confirms.
- **Prompt-injection defences.** The chat call that sees entry content is given no tools, and the
  client renders answers as plain text. Adding a tool to that call or a markdown/HTML renderer to
  chat is a blocker.
- **Bedrock.** All calls go through `careervault.bedrock_client`, which owns retries (botocore's
  are off). Structured output uses tool use validated with Pydantic, with one retry on a
  validation failure. New model calls raise cost against a $5 monthly ceiling: say what each adds.
- **Infrastructure.** Changes go in the SAM template only. A changed parameter default does
  nothing unless `infrastructure/samconfig.toml` sets it. No em dashes in AWS resource names or
  descriptions. Least privilege, no wildcard resources.
- **Résumés.** Records and S3 objects never expire; deletion removes S3 objects first, then the
  record.
- **Frontend.** `frontend/src/index.css` is the only file that defines colours, and both themes
  ship. No `useEffect` writes the state it depends on (this once sent 18,000 requests in two
  seconds). Dictation fills the field and never submits, and the recording disclosure stays. The
  UI never shows invented data. The theme script in `index.html` stays inline and synchronous.
- **Tests.** New behaviour has tests, including failure branches. Frontend tests stub `fetch`
  with `src/test/http.ts` and do not mock the api module.

## Extra hard rules

- AWS context is describe/list only, always with `AWS_PROFILE=careervault-dev`. No `sam deploy`,
  `sam delete`, `make deploy` or any write call. Never `get-secret-value` or
  `batch-get-secret-value`.
- Nothing that calls Bedrock or generates a résumé against the live stack.
- Install frontend dependencies with `npm ci` only.
