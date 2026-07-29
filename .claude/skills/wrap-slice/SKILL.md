---
name: wrap-slice
description: End-of-slice checklist for CareerVault — verify tests and deployment, run BOTH reviews (`/security-review` AND `/code-review` — running each is a hard blocker, findings are triaged on judgement), bring all canonical docs current (CLAUDE.md phase marker is blocking), render the slice explainer, commit, push, open the PR, and hand off cleanly.
---

# Wrap up a slice

Run these steps in order. Three things are **blocking**: both reviews must be *run* (steps 2 and 3), and the docs must be current (step 4) — a slice is not done until the next session can cold-start from `CLAUDE.md` alone.

> **Invoke this skill; do not reproduce it from memory.** Working through these steps by hand — even
> with the file open — is how a step gets silently dropped, because nothing then enforces the order
> or the gates. If the user says "wrap the slice" in any form, invoke `/wrap-slice` rather than
> recalling what it contains. This is not a style preference: it has already cost a slice its code
> review (slice 8, PR #31), which went unnoticed until the user asked two slices later.

## 1. Verify the work

- **Run the unit suite and confirm it is green — this is a blocking gate, do it first.** Run
  `./scripts/run-tests.sh` (the canonical runner — it builds the throwaway venv with the right deps;
  a bare `python -m pytest` can miss them). "Green" means the pytest summary line shows **only
  `N passed`** — no `failed`, no `error`, no collection error, not "no tests ran". If it is not
  cleanly green, stop and fix the code until it is; do not proceed to later steps on red or an
  unclear result. (A `PostToolUse` hook — `.claude/check-tests-green.sh` — enforces this: any test
  run that isn't clearly green blocks with feedback, so a red result can't be waved through.) If the
  slice touched the frontend, also run `cd frontend && npm run build && npm run lint` (CI runs both).
- If the slice changed deployed behavior, confirm it was actually deployed to dev and smoke-tested end-to-end (real API Gateway → Lambda → downstream, not just unit tests). If smoke testing didn't happen, say so plainly — do not mark the slice complete.
- **Assert the AWS account before any deploy/verify command** — CareerVault shares an SSO login with a second project in a separate account:

  ```bash
  acct=$(AWS_PROFILE=careervault-dev aws sts get-caller-identity --query Account --output text) \
    && [ "$acct" = "768396678224" ] && echo "✓ account $acct" || echo "✗ WRONG ACCOUNT $acct — stop"
  ```

## 2. Security review (blocking on unresolved findings)

CareerVault stores users' career history, so **every slice that touches code gets a security review before it's committed**:

```
/security-review
```

- Triage each finding: fix it, or record an explicit, reasoned decision to accept/defer it (an ADR, or a plan/parking-lot note). **Do not commit with unexplained findings outstanding.**
- Focus areas for this codebase: per-user data isolation (PK from JWT `sub`, never the body — §4.2.4), authz on every route, input validation at the Pydantic gate, IAM least-privilege on any new actions, no secrets in code/logs, CORS origin scoping.
- This is the *local* gate. The *remote* net is GitHub Actions on the PR — **CodeQL** SAST (`.github/workflows/codeql.yml`) and **Dependabot** (`.github/dependabot.yml`). Treat a CodeQL alert or a Dependabot security update on the PR the same way: triage before merge, don't just merge past it.

## 3. Code review — RUNNING IT IS BLOCKING (findings are advisory)

Run a general code review on the slice diff — a different lens than the security review
(correctness, reuse, simplification, efficiency, not vulnerabilities):

```
/code-review
```

**Separate the two things this step contains, because conflating them is how it gets skipped:**

| | Status |
|---|---|
| **Running the review** | 🚫 **Blocking.** Not optional, not conditional on the slice "looking safe", not skippable because the diff is mostly tests or docs. If it has not run, the slice is not wrapped. |
| **Acting on the findings** | ✅ **Advisory.** Triaged on judgement — see below. |

- **Never skip the run.** "The slice was only tests and docs" is not a reason — slice 9 was almost
  entirely tests and docs, and its review returned **15 findings, two of which could have caused
  real side effects on live data**. The value of the review is not predictable from the shape of
  the diff, which is precisely why the decision to run it is not yours to make.
- **Triage the findings on judgement.** Fix the dire ones in-slice — anything that can corrupt or
  destroy data, cause an unintended side effect on the deployed system, cost real money, or leave a
  test that cannot fail. Everything else is **not** chased in this slice: append it to
  [`docs/careervault-backlog.md`](../../../docs/careervault-backlog.md) with a reason (see step 4).
- **A test that passes for the wrong reason counts as dire.** It is worse than no test, because it
  reports coverage nobody has. When a finding claims a test is toothless, verify by breaking the
  code deliberately and confirming the test notices.
- Timebox the *triage* so wrap doesn't turn into a second implementation pass. Do not timebox the
  run itself.
- **Record the outcome in the PR body** (step 7), even when there is nothing to report — an empty
  result stated explicitly is the only thing that distinguishes "reviewed, clean" from "never ran".

## 4. Bring the docs current (blocking)

- **`docs/careervault-plan.md`** — the linchpin. Flip the slice to ✅ on the status board (add
  the PR link once it exists), fill in its **Completion notes** (what shipped, what was
  deployed/verified, gotchas discovered, wrinkles deferred — same altitude as the slice 1/2a
  notes), check off exit criteria, and sanity-check that the *next* slice's section still
  reflects reality. This is what makes the next session's cold start cheap.
- **Evaluation beat** — close the loop inside the plan's Completion notes: did the slice meet
  its exit criteria and NFR targets, what did it *actually* cost (record real $ vs the $5
  ceiling once a slice adds Bedrock — slices 5–8), and one thing to improve. Route any finding
  to a later slice, an ADR, or the parking lot. The full MVP-level scorecard against
  requirements §7 + NFRs lands at slice 9.
- **`CLAUDE.md` "Current build phase"** — refresh the pointer: current slice, last completed
  slice. It stays compact; detail belongs in the plan doc.
- **`docs/careervault-adl.md`** — every decision the slice forced is captured as an ADR (they should already exist from /start-slice step 6; verify). Update the index table and the "Last updated" line.
- **`docs/careervault-architecture.md`** — if implementation contradicted the doc, correct the doc (don't silently code around it — the user wants these corrections explained), bump the version, add a change-log row.
- **`docs/careervault-backlog.md`** — append anything deferred this slice: code-review findings
  not fixed in-slice (step 3), UI gaps or tech debt noticed, doc drift spotted. One line per item,
  with the type/priority/status columns filled and "Surfaced in" set to this slice. Prune any
  `done` rows whose closure you're recording in the plan's completion notes.
- **Memory** — save durable gotchas (account-level constraints, API behaviors that contradict docs) that future sessions need; update `MEMORY.md` index.

## 5. Render the slice explainer

CareerVault is an AWS-learning vehicle, not just a shipping project — a slice isn't really
delivered until Oche can follow how it works. Run the explainer skill on the slice diff:

```
/explain-diff
```

- It writes `docs/explanations/YYYY-MM-DD-<slug>.html` (background → intuition → code walkthrough
  → five-question quiz). **Commit it with the slice** in step 6 — it's part of the project record,
  and it explains the very diff it ships in.
- Run it *after* step 4, not before: the explainer cites ADR numbers and the doc corrections the
  slice forced, so those have to be final first.
- **Not a blocking gate.** Skip it for a slice with nothing to teach (a docs-only or config-only
  slice, a dependency bump) — but say so explicitly rather than silently dropping it.
- The highest-value material is where **live AWS contradicted the architecture doc** and what
  reality forced. Lead with those; they're why this step exists.

## 6. Commit and push

- Commits follow the existing conventional style (`feat(infra):`, `fix(ddb):`, `docs:`, `test:`, `ci:`, `chore:`), each ending with the Co-Authored-By trailer.
- Logical commits: infra / backend / tests / docs / ci separated where it's natural, matching the history's grain.
- Push the slice branch to origin.

## 7. Open the PR

```bash
gh pr create --base main
```

PR body: what the slice delivers, exit criteria and how each was verified (including smoke-test evidence), decisions/ADRs added, doc corrections made, and a link to the slice explainer from step 5. End with the "Generated with Claude Code" footer.

**A `## Reviews` section is mandatory, with both reviews named explicitly** — the security-review
outcome (clean, or findings + how resolved) *and* the code-review outcome (findings, which were
fixed in-slice, which were logged to the backlog and why). Use those exact words, so the section is
greppable across PRs.

Write both lines even when a review found nothing. A PR body that simply omits one is
indistinguishable from a review that never ran — which is exactly how the slice-8 gap (PR #31) went
unnoticed until the user spotted it two slices later.

## 8. Hand off

Tell the user, explicitly:

- PR URL and what's in it.
- The path to the slice explainer, so they can read it before merging.
- **Both review results, named separately** — security *and* code review — plus any CodeQL/Dependabot
  alerts the PR will surface. If either review did not run, say so plainly rather than omitting it;
  a silent omission is what makes a skipped gate invisible.
- That after they merge, the next `/start-slice` will fast-forward local `main` (or they can `git checkout main && git pull` themselves).
- Any threads deliberately left open, so they land in the next session's plan rather than being forgotten.

Do not merge the PR yourself; merging is the user's call.
