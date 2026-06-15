# career-vault
AI-powered career design app that helps you track your career, recording your wins, milestones, and achievements, and using them as context to produce tailored output like resumes, portfolios, and other artifacts upon request.

See `docs/` for the architecture, requirements, and ADRs. Project context for Claude Code lives in `CLAUDE.md`.

## Running the first vertical slice (auth + `GET /settings`)

The current build is the first end-to-end slice: Cognito Hosted UI → React SPA → API Gateway
(REST) + Cognito authorizer → `settings_lambda` → DynamoDB.

**Prerequisites:** AWS CLI + SAM CLI installed, Docker running (for `sam build`), Node 20+, and
AWS credentials for an account in `us-east-1`.

```bash
# 1. Authenticate to AWS (one-time) — e.g. one of:
aws configure                 # static keys
aws sso login                 # if you use IAM Identity Center
export AWS_PROFILE=your-profile

# 2. Build + deploy the dev stack, then write frontend/.env.local from its Outputs
make bootstrap

# 3. Create the single login user (admin-provisioned; no self-service signup per ADR-025)
make create-user EMAIL=you@example.com PASSWORD='Chang3!Me-please'

# 4. Run the SPA, then open http://localhost:5173, click "Sign in", and you should see
#    the GET /settings JSON (a default profile on first run)
make frontend-dev
```

Other targets: `make build`, `make deploy`, `make frontend-env`, `make test`, `make help`.
Deploy a separate prod stack with `make deploy ENV=prod` (uses the `[prod]` samconfig section).

**Note:** the DynamoDB table has Deletion Protection enabled (architecture §4.7.3). To tear down
the dev stack you must first disable it:
`aws dynamodb update-table --table-name CareerVaultTable-dev --no-deletion-protection-enabled`,
then `cd infrastructure && sam delete`.

## Tests

```bash
make test        # backend unit tests in an isolated venv
```
