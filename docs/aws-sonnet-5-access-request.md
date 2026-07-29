# AWS request — Claude Sonnet 5 access (account 768396678224)

> **Status:** ready to submit. Not yet sent.
> **Why this file exists:** the diagnosis behind backlog **B-010** took three sessions and ruled out
> four hypotheses. Rather than re-derive it (or re-probe on a theory that has already failed twice),
> the evidence package is written once, here, ready to paste.
>
> **Where to send it.** The account is on **Basic support**, so technical support cases are not
> available (`DescribeSeverityLevels` → `SubscriptionRequiredException`). Two free routes:
> 1. **AWS Sales contact form** — <https://aws.amazon.com/contact-us/sales-support/>. This is what
>    the error message itself directs you to, and is the most likely correct destination if the
>    model is gated behind a commercial agreement.
> 2. **Support Center → Create case → Account and billing** — free on Basic. Use *Service: Account*,
>    since a model-entitlement mismatch is an account issue rather than a technical one.
>
> Submitting both is reasonable; they route to different teams.

---

## Subject

Claude Sonnet 5 shows fully entitled in the Bedrock control plane but returns AccessDeniedException at invoke time (us-east-1)

## Body — paste from here

**Account:** 768396678224
**Region:** us-east-1
**Model:** `anthropic.claude-sonnet-5` (via inference profiles `us.anthropic.claude-sonnet-5` and `global.anthropic.claude-sonnet-5`)

Every control-plane signal AWS exposes reports this model as fully available to my account, and the Model access page in the console shows the subscription as active. Every data-plane invocation is denied. I would like help reconciling the two, or confirmation that this model requires an agreement my account cannot obtain self-service.

**1. `GetFoundationModelAvailability` reports all four dimensions green:**

```
$ aws bedrock get-foundation-model-availability --region us-east-1 \
      --model-id anthropic.claude-sonnet-5
{
    "modelId": "anthropic.claude-sonnet-5",
    "agreementAvailability": { "status": "AVAILABLE" },
    "authorizationStatus": "AUTHORIZED",
    "entitlementAvailability": "AVAILABLE",
    "regionAvailability": "AVAILABLE"
}
```

**2. This response is byte-identical to a model that works.** `anthropic.claude-sonnet-4-6` returns
exactly the same four values and invokes successfully from the same IAM identity, in the same
region, in the same session. So the difference is not credentials, region, or IAM.

**3. The model and its inference profiles are `ACTIVE`:**

```
$ aws bedrock list-foundation-models --region us-east-1
  anthropic.claude-sonnet-5   inferenceTypesSupported: ["INFERENCE_PROFILE"]   status: ACTIVE

$ aws bedrock list-inference-profiles --region us-east-1
  us.anthropic.claude-sonnet-5       ACTIVE   "US Anthropic Claude Sonnet 5"
  global.anthropic.claude-sonnet-5   ACTIVE   "Global Anthropic Claude Sonnet 5"
```

**4. All three invocation forms are denied:**

```
$ aws bedrock-runtime converse --region us-east-1 \
      --model-id us.anthropic.claude-sonnet-5 \
      --messages '[{"role":"user","content":[{"text":"hi"}]}]' \
      --inference-config maxTokens=5

An error occurred (AccessDeniedException) when calling the Converse operation:
anthropic.claude-sonnet-5 is not available for this account.
You can explore other available models on Amazon Bedrock.
For additional access options, contact AWS Sales at
https://aws.amazon.com/contact-us/sales-support/
```

Identical result for `global.anthropic.claude-sonnet-5` and for the bare foundation-model ID.

**5. No Service Control Policy is involved.** The account's only attached SCP is the default
`FullAWSAccess`.

**6. The Marketplace agreement was accepted and did take effect.** `agreementAvailability`
progressed `NOT_AVAILABLE` → `PENDING` → `AVAILABLE` after
`CreateFoundationModelAgreement`. Invocation was denied before that change and is still denied
several hours after it, with no change in the error.

### What I am asking

1. Is `anthropic.claude-sonnet-5` gated behind a commercial or sales-negotiated agreement that is
   separate from the Marketplace agreement and the Bedrock model-access flow? If so, please say so
   directly — the control-plane response above reporting `AUTHORIZED` / `AVAILABLE` / `AVAILABLE` /
   `AVAILABLE` is then misleading, and I would like to know what the actual prerequisite is.
2. If it is *not* gated that way, this looks like a control-plane/data-plane inconsistency on the
   account, and I would like it corrected so the model is invokable.

### Context

Small single-user personal project (a career-tracking app) with a self-imposed ~$5/month ceiling.
Current usage is roughly 16 Bedrock inference runs per month, presently on Claude Sonnet 4-6.
The interest in Sonnet 5 is that it is materially cheaper per token, so the motivation is cost
efficiency rather than volume. I am not asking for a quota increase — the request is only to make
an already-subscribed model invokable.

## Body — paste to here

---

## If the answer is "sales-gated"

Then B-010 becomes `wontfix` for this account rather than `open`, and the project stays on
Sonnet 4-6 indefinitely. That is an acceptable outcome: 4-6 produces measured résumé runs at
~70–83K tokens / $0.31–$0.35 each, comfortably inside the ceiling. Record the answer in the backlog
note and in ADR-036's live-access section so the question is closed rather than perpetually reopened.

## If access is granted

Two changes, and they must land together:

1. `infrastructure/samconfig.toml` — set `SonnetInferenceProfileId=us.anthropic.claude-sonnet-5`
   and `SonnetFoundationModelId=anthropic.claude-sonnet-5`.
2. `backend/functions/resume_agent/agent.py` — set `_PRICE_PER_TOKEN["sonnet"]` to
   `(2.20, 11.00)` (Regional CRIS rates; **not** the $2.00/$10.00 headline rates — see the
   pricing note in ADR-036).

Then re-run a résumé generation and confirm the reported cost drops by roughly a third.
