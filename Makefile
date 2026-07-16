# CareerVault — developer workflow wrapper (architecture Section 5.7).
#
# Quickstart for the first vertical slice (auth + GET /settings), after configuring AWS creds:
#
#   aws configure          # or `aws sso login` / set AWS_PROFILE — one-time
#   make bootstrap         # sam build + deploy (dev) + write frontend/.env.local
#   make create-user EMAIL=you@example.com PASSWORD='Chang3!Me'
#   make frontend-dev      # http://localhost:5173 → Sign in → see GET /settings JSON

ENV        ?= dev
REGION     ?= us-east-1
STACK_NAME ?= careervault-$(ENV)
# samconfig uses [default] for dev and [prod] for prod (Section 5.5).
CONFIG_ENV := $(if $(filter dev,$(ENV)),default,$(ENV))

.PHONY: build deploy deploy-frontend deploy-all bootstrap create-user frontend-env frontend-dev test help

# Read a single stack Output value (used by deploy-frontend).
stack-output = $(shell aws cloudformation describe-stacks --stack-name "$(STACK_NAME)" \
	--region "$(REGION)" --query "Stacks[0].Outputs[?OutputKey=='$(1)'].OutputValue" --output text)

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

build: ## Build the SAM app (shared layer + functions)
	cd infrastructure && sam build

deploy: build ## Build + deploy the stack for ENV (default dev)
	cd infrastructure && sam deploy --config-env $(CONFIG_ENV) \
		--no-confirm-changeset --no-fail-on-empty-changeset

frontend-env: ## Write frontend/.env.local + .env.production.local from stack Outputs
	./scripts/write-frontend-env.sh "$(STACK_NAME)" "$(REGION)"

deploy-frontend: frontend-env ## Build the React app and publish it to S3 + CloudFront (ADR-019, §5.7)
	cd frontend && npm ci && npm run build
	aws s3 sync frontend/dist/ "s3://$(call stack-output,SiteBucketName)/" --delete
	aws cloudfront create-invalidation \
		--distribution-id "$(call stack-output,CloudFrontDistributionId)" --paths "/*"
	@echo "Frontend live at: $(call stack-output,CloudFrontUrl)"

deploy-all: deploy deploy-frontend ## Deploy the stack, then build + publish the frontend

bootstrap: deploy frontend-env ## Deploy + generate frontend/.env.local
	@echo ""
	@echo "Stack '$(STACK_NAME)' deployed; frontend/.env.local written."
	@echo "Next: make create-user EMAIL=you@example.com PASSWORD='Chang3!Me'"
	@echo "Then: make frontend-dev"

create-user: ## Create the single Cognito user. Args: EMAIL=, PASSWORD=
	@test -n "$(EMAIL)" || { echo "EMAIL is required (make create-user EMAIL=you@example.com PASSWORD=...)"; exit 1; }
	@test -n "$(PASSWORD)" || { echo "PASSWORD is required"; exit 1; }
	./scripts/create-user.sh "$(STACK_NAME)" "$(REGION)" "$(EMAIL)" "$(PASSWORD)"

frontend-dev: ## Install deps (if needed) and run the Vite dev server
	cd frontend && npm install && npm run dev

test: ## Run backend unit tests in an isolated venv
	./scripts/run-tests.sh
