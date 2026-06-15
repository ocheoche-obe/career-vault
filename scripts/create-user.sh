#!/usr/bin/env bash
# Create the single CareerVault Cognito user with a permanent password (ADR-006 / ADR-025:
# single-tenant, admin-created — no self-service signup). No email delivery is required: the
# message is suppressed and the password is set directly as permanent.
#
# Usage: scripts/create-user.sh <stack-name> <region> <email> <password>
set -euo pipefail

STACK_NAME="${1:?usage: create-user.sh <stack-name> <region> <email> <password>}"
REGION="${2:?region required}"
EMAIL="${3:?email required}"
PASSWORD="${4:?password required}"

POOL_ID="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CognitoUserPoolId'].OutputValue" \
  --output text)"

if [[ -z "$POOL_ID" || "$POOL_ID" == "None" ]]; then
  echo "Could not read CognitoUserPoolId from stack '$STACK_NAME'. Is it deployed?" >&2
  exit 1
fi

echo "Creating user '$EMAIL' in pool '$POOL_ID'..."
aws cognito-idp admin-create-user \
  --user-pool-id "$POOL_ID" --region "$REGION" \
  --username "$EMAIL" \
  --user-attributes Name=email,Value="$EMAIL" Name=email_verified,Value=true \
  --message-action SUPPRESS >/dev/null

aws cognito-idp admin-set-user-password \
  --user-pool-id "$POOL_ID" --region "$REGION" \
  --username "$EMAIL" --password "$PASSWORD" --permanent

echo "Done. Sign in at http://localhost:5173 with '$EMAIL' and the password you supplied."
