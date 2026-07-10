#!/usr/bin/env bash
# Create-or-rotate the single CareerVault Cognito user with a permanent password (ADR-006 /
# ADR-025: single-tenant, admin-created — no self-service signup). No email delivery is required:
# the message is suppressed and the password is set directly as permanent.
#
# Idempotent: if the user already exists, the create step is tolerated and the script falls
# through to (re)set the permanent password — so this doubles as a password-rotation tool.
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

echo "Ensuring user '$EMAIL' exists in pool '$POOL_ID'..."
# Tolerate an already-existing user so the script also serves as a rotation tool. Any other
# error still aborts (the grep is the only non-fatal case; everything else re-raises).
if ! create_err="$(aws cognito-idp admin-create-user \
  --user-pool-id "$POOL_ID" --region "$REGION" \
  --username "$EMAIL" \
  --user-attributes Name=email,Value="$EMAIL" Name=email_verified,Value=true \
  --message-action SUPPRESS 2>&1 >/dev/null)"; then
  if grep -q "UsernameExistsException" <<<"$create_err"; then
    echo "User already exists — rotating password."
  else
    echo "$create_err" >&2
    exit 1
  fi
fi

echo "Setting permanent password..."
aws cognito-idp admin-set-user-password \
  --user-pool-id "$POOL_ID" --region "$REGION" \
  --username "$EMAIL" --password "$PASSWORD" --permanent

echo "Done. Sign in at http://localhost:5173 with '$EMAIL' and the password you supplied."
