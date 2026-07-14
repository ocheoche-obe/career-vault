#!/usr/bin/env bash
# Session-start guard: confirm the careervault-dev profile resolves to the CareerVault AWS account.
#
# CareerVault shares an AWS SSO login with a second project that lives in a *separate* account under
# the same Organization. This check runs at the start of every session in this repo (wired as a
# SessionStart hook in .claude/settings.json) so work here can't silently target the wrong account.
# It is informational and never blocks the session.
set -uo pipefail

PROFILE=careervault-dev
EXPECTED_ACCOUNT=768396678224

acct=$(AWS_PROFILE="$PROFILE" aws sts get-caller-identity --query Account --output text 2>/dev/null)

if [ -z "$acct" ]; then
  echo "⚠  CareerVault AWS: profile '$PROFILE' is not authenticated. Run: aws sso login --profile $PROFILE"
elif [ "$acct" = "$EXPECTED_ACCOUNT" ]; then
  echo "✓  CareerVault AWS OK — '$PROFILE' → account $acct (us-east-1). Prefix AWS/SAM commands with AWS_PROFILE=$PROFILE."
else
  echo "✗  CareerVault AWS MISMATCH — '$PROFILE' resolves to $acct, expected $EXPECTED_ACCOUNT."
  echo "   You may be pointed at another project's account. Do NOT run aws/sam here until this is fixed."
fi

exit 0
