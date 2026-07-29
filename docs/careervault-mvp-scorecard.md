# CareerVault — MVP Scorecard

**Status:** Slice 9 deliverable — the honest close-out
**Created:** 2026-07-29
**Scores against:** [`careervault-requirements.md`](careervault-requirements.md) v0.6 (§3 FRs, §4 NFRs, §7 success criteria)

> The point of this document is to be *falsifiable*. A scorecard that marks everything green is a
> press release. Where something is unverified it says unverified — which is a different claim from
> "fails", and both are different from "passes". Each ⚠️ and ❌ routes somewhere: a backlog ID, a
> deferral recorded in the requirements doc, or a v1.1 line.

---

## 1. Success criteria (§7)

The six criteria the MVP was defined against.

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | Sign in via Cognito and reach a dashboard | ✅ **Pass** | Slice 1 + 4. Hosted UI, OAuth2 + PKCE (ADR-025); dashboard on CloudFront. |
| 2 | Log a milestone by chat, see it parsed, confirm it, find it in the dashboard | ✅ **Pass** | Slices 2a/2b/3. End-to-end live; the confirm gate and its 409 path are now test-pinned. |
| 3 | Receive a personalized weekly check-in referencing recent entries | ✅ **Pass** | Slice 8, verified live across all three tiers. Measured ~$0.0026/check-in. |
| 4 | Submit a JD and receive a tailored résumé ~~within 30 seconds~~ | ⚠️ **Pass, criterion corrected** | The résumé is delivered; the *30-second* bound was never met and was never achievable. See §4 below — this is the scorecard's most important entry. |
| 5 | Download a generated résumé as a PDF | ✅ **Pass** | Slice 6b. Now asserted in CI-adjacent form: the `--expensive` tier fetches the presigned object and checks `%PDF-` magic bytes. |
| 6 | Monthly AWS spend under $5 during normal usage | ✅ **Pass, with a caveat** | **$3.88 of $5.00** in July 2026 — the heaviest development month, including agent tuning and paid test runs. The caveat is structural, not accounting: see §5. |

**5 of 6 clean; 1 passed only after correcting the criterion itself.**

---

## 2. Functional requirements (§3)

| FR | Requirement | Verdict | Where |
|---|---|---|---|
| 1.1 | Authenticate via Cognito | ✅ | Slice 1 |
| 1.2 | `user_id` on every record | ✅ | Slice 1 — single-table PK is `USER#<id>` throughout |
| 2.1 | Conversational text input | ✅ | Slice 2b |
| 2.2 | LLM parses free-form input into typed entries | ✅ | Slice 2a — Haiku + tool use |
| 2.3 | Confirm before persisting, allow edits | ✅ | Slice 2b — the propose/confirm card |
| 2.4 | Follow-up clarifying questions | ✅ | Slice 2a — the `ask_clarification` tool |
| 3.1 | Persist entries with metadata + conversation context | ✅ | Slice 2a |
| 3.2 | Dashboard grouped by category and chronologically | ✅ | Slice 3 |
| 3.3 | Edit or delete any entry | ✅ | Slice 3 — hard delete behind a UI confirm (ADR-027) |
| 4.1 | Four configurable cadences | ✅ | Slice 8 — all four paced by `next_checkin_at` (ADR-039) |
| 4.2 | Default weekly | ✅ | Slice 8 |
| 4.3 | LLM-personalized prompt from recent entries | ✅ | Slice 8 |
| 4.4 | Link to the dashboard | ✅ | Slice 8 |
| 4.5 | Fall back to a generic reminder on failure | ✅ | Slice 8 — three tiers, and the degrade is metric-visible (ADR-021) |
| 4.6 | Change cadence and pause from settings | ✅ | Slice 8 — nested-settings merge via ADR-040 |
| 5.1 | Submit a JD, request a tailored résumé | ✅ | Slice 6a/6b |
| 5.2 | Bedrock agent loop: retrieve → draft → critique → revise | ✅ | Slice 6a — six phases, bounded (ADR-036) |
| 5.3 | Return copyable bullets AND/OR HTML preview AND/OR PDF | ⚠️ **2 of 3** | HTML preview + PDF shipped; **copyable plain-text bullets did not**. The "AND/OR" wording admits a subset, so this is met as written — but a user who wants to paste bullets into an existing résumé has no path. → **B-022** |
| 5.4 | Select output format(s) per request | ❌ **Deferred** | Both artifacts are always produced. Recorded with reasoning in requirements v0.6: rendering is deterministic and post-agent, so selection saves no tokens — a UI affordance, not a cost control. |
| 6.1 | Ask questions about your own career data | ✅ | Slice 7 — grounded Q&A (ADR-038) |
| 6.2 | Conversation history within a session | ✅ | Slice 2b |

**20 of 22 fully met · 1 partial (FR-5.3) · 1 deliberately deferred (FR-5.4).** No FR is silently unmet.

---

## 3. Non-functional requirements (§4)

| NFR | Requirement | Verdict | Notes |
|---|---|---|---|
| 1.1 | ≤ $5/month | ✅ | See §5. |
| 1.2 | Billing alarms at $3 / $5 | ⚠️ **Defined, not deployed** | Prod-gated, and under ADR-041 no prod stack exists. The **AWS Budget `careervault-monthly-5usd`** is the live guard. The alarms were confirmed *well-formed* by the slice-9 change-set dry run — the first time that branch was ever evaluated. |
| 1.3 | Haiku for cheap tasks, Sonnet for high-value | ✅ | Chat, parse, check-in on Haiku; résumé agent on Sonnet 4-6. |
| 1.4 | DynamoDB on-demand | ✅ | `PAY_PER_REQUEST`. |
| 2.1 | Ingestion ≤ 5s | ❓ **Unverified** | Never systematically measured. Cost per turn is known (~$0.006); latency is not. → **B-023** |
| 2.2 | Résumé generation ≤ 4 min, async | ✅ | Corrected in v0.6 from an unmeetable 30s. Measured 72s / ~176s. |
| 2.3 | Dashboard load ≤ 2s | ❓ **Unverified** | Same gap as 2.1. Note B-013: every Q&A turn reads the full corpus *including embeddings*, which scales badly on the interactive path. → **B-023** |
| 3.1 | 99% availability | ➖ **Not measurable** | No synthetic monitoring, no SLA, single user. Honest answer: unknown, and appropriately so at MVP. |
| 3.2 | Writes acknowledged before confirmation | ✅ | Conditional writes complete before the API responds. |
| 3.3 | Bedrock retries, exponential backoff, max 3 | ✅ | Verified in `bedrock_client`: botocore's own retries are disabled (`max_attempts: 1`) so the two layers cannot multiply "max 3" into 9+. |
| 3.4 | Background failures logged, not user-blocking | ✅ | Per-user isolation in the check-in loop (§3.3.5). |
| 4.1 | All endpoints require a valid Cognito JWT | ✅ | API Gateway JWT authorizer on every route. |
| 4.2 | Encryption at rest | ✅ | DynamoDB SSE (`aws/dynamodb`), S3 SSE-S3. |
| 4.3 | TLS 1.2+ | ✅ | CloudFront, API Gateway, and SES `TlsPolicy: REQUIRE`. |
| 4.4 | Least-privilege IAM | ⚠️ **True, but narrower than it reads** | Each Lambda has a scoped role. The important caveat, established in slice 7: **IAM cannot express an SK-prefix boundary** — `LeadingKeys` scopes the partition key only, and one user is one partition. "Chat can only touch `CONVO#`" is a *code* invariant wearing an IAM costume (arch v2.0 corrects §4.2.3). Real, but enforced a layer lower than the requirement implies. |
| 4.5 | No secrets in code | ✅ **Vacuously** | Not "secrets are in Parameter Store" — the app has **no secrets at all**. Cognito handles auth; no third-party API keys exist. Worth stating precisely, because the requirement's premise never applied. |
| 5.1 | IaC via SAM | ✅ | One template, 70 resources. |
| 5.2 | `CLAUDE.md` present | ✅ | |
| 5.3 | Powertools logging / tracing / validation | ✅ | All seven Lambdas. |
| 6.1 | Chat primary, minimal navigation | ✅ | Chat is the landing view; five nav items. |
| 6.2 | Usable on desktop **and mobile web** | ❓ **Unverified** | Never tested at mobile viewport. Related to B-001 (UI is functional but basic). → folded into **B-001** |
| 6.3 | Emails render in Gmail, Outlook, Apple Mail | ⚠️ **Gmail only** | Verified in Gmail during slice 8. Outlook is the risk — its rendering engine is the one that breaks HTML email. → **B-024** |

**16 met · 4 caveated · 3 unverified · 1 not measurable.**

---

## 4. The finding that matters most

**Requirements §7.4 and NFR-2.2 both promised a tailored résumé "within 30 seconds." Neither was ever met, and neither was ever achievable.**

Measured: **72 seconds** on a 2-entry corpus, **~176 seconds** on the real 13-entry one. Worse, the target was structurally impossible in the original synchronous design — anything over **API Gateway's 29-second integration timeout** cannot be returned from a request at all, which is exactly what forced the async job design in ADR-037.

Three things make this the scorecard's most instructive entry:

1. **The correction was already half-made.** Slice 6b corrected architecture §3.2.2's parallel "under 90 seconds" claim and *stopped there* — leaving the requirement and the success criterion, the two documents the MVP is actually graded against, still asserting a falsehood. Fixing the description while leaving the specification is the more dangerous half to skip.
2. **It would have scored itself green.** Nothing in the system fails when a latency requirement is wrong. The résumé arrives, the user is happy, and the number in the doc quietly stops meaning anything — the same invisible-degradation shape as slice 8's tier fallback (ADR-021).
3. **The right fix was not a looser number.** NFR-2.2 now specifies *asynchronous with a 4-minute ceiling*, which describes the actual architecture, rather than a bigger number that would still have implied a synchronous request. **A latency requirement and a delivery model are not independent choices.**

Reducing the number honestly is **B-020**, raised by Oche at slice-9 scoping and the highest-value item carried into v1.1.

---

## 5. Cost review (NFR-1.1)

**July 2026 final: $3.88 of the $5.00 ceiling (78%).** This was the heaviest month the project has
had — résumé-agent tuning, slices 7 and 8, and slice 9's paid test runs — so it is close to a
worst-case reading rather than a typical one.

| Line | Amount | Share |
|---|---|---|
| Claude Sonnet 4-6 (résumé agent) | $3.1829 | **82%** |
| Claude Haiku 4.5 (chat, parse, check-in) | $0.1817 | 5% |
| Tax | $0.3700 | 10% |
| **All deployed infrastructure combined** — S3 $0.0057, CloudWatch $0.0001, DynamoDB, API Gateway, SNS, SQS, Cognito, CloudFront | **~$0.008** | **0.2%** |
| **Total** | **$3.8844** | |

**Verdict: NFR-1.1 met**, with ~$1.12 of headroom in the project's most expensive month.

**The $5 ceiling governs Bedrock call volume, not architecture size.** That single reframing decided ADR-041 (a second stack is nearly free, so prod-vs-dev turns on operational cost, not money) and ADR-042 (the integration suite must be tiered, because one résumé run costs more than a month of every other service put together).

The risk to carry into v1.1 is **not** the current total. It is that the dominant cost **scales with corpus size** — the slice-9 measurement showed a 2-entry corpus at $0.113 against a 13-entry corpus at $0.31–0.35 for the same `REVISE` verdict. The app gets more expensive precisely as it becomes more useful. B-004 and B-020 attack the same mechanism.

---

## 6. What this MVP is honestly *not*

Stated plainly so it is a decision rather than an omission:

- **Not multi-user.** Single-tenant by ADR-006/-007. The data model is multi-tenant-*ready*; nothing else is.
- **Not deployed to prod.** `careervault-dev` **is** the MVP (ADR-041). And the slice-9 dry run proved a prod stack *could not have deployed* as configured — the SES email identity collides with dev's (**B-021**).
- **Not visually designed.** The UI is functional and plain; mobile is untested (**B-001**).
- **Not fast at résumé generation.** 72–176 seconds (**B-020**).
- **Not covered by E2E tests.** No browser-driven test runs in CI. Component state and API contracts are covered; the assembled application is verified by hand.
- **Not on Sonnet 5.** Ungrantable on this account — a commercial-agreement wall, not a misconfiguration (**B-010**, `blocked-external`).

---

## 7. Verification inventory

| Layer | Count | Cost | Gate |
|---|---|---|---|
| Backend unit | 376 | $0 | CI on every PR |
| Frontend (Vitest + RTL) | 23 | $0 | CI on every PR |
| Integration — `local` (DynamoDB Local) + `cloud` (deployed) | 56 | $0 | one command, local |
| Integration — `--bedrock` (real Haiku) | 5 | ~$0.01 | opt-in |
| Integration — `--expensive` (Sonnet résumé run) | 1 | ~$0.11 | opt-in |
| **Total** | **461** | | |

The distinction worth keeping: **the default run is free, which is why it gets run.** ADR-042's reasoning was that a uniform suite at ~$0.35 a go is a suite people avoid, and avoided tests are worse than absent ones because they still imply coverage.
