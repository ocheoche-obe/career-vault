---
name: wrap-slice
description: End-of-slice checklist for CareerVault — verify tests and deployment, run a security review, bring all canonical docs current (CLAUDE.md phase marker is blocking), render the slice explainer, commit, push, open the PR, and hand off cleanly.
---

# Wrap up a slice

Run these steps in order. The docs step is blocking: a slice is not done until the next session can cold-start from `CLAUDE.md` alone.

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

## 3. Advisory code review (non-blocking)

Run a general code review on the slice diff — a different lens than the security review
(correctness, reuse, simplification, efficiency, not vulnerabilities):

```
/code-review
```

- **Advisory, not a gate.** Fix the quick, clear wins in-slice. Anything that isn't a quick fix
  does **not** block the PR and is **not** chased in this slice — append it to
  [`docs/careervault-backlog.md`](../../../docs/careervault-backlog.md) instead (see step 4).
- Timebox the triage so wrap doesn't turn into a second implementation pass.
- Note the outcome in the PR body alongside the security-review result (step 7).

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

PR body: what the slice delivers, exit criteria and how each was verified (including smoke-test evidence), the security-review outcome (clean, or findings + how resolved), the advisory code-review outcome (fixed in-slice vs. logged to backlog), decisions/ADRs added, doc corrections made, and a link to the slice explainer from step 5. End with the "Generated with Claude Code" footer.

## 8. Hand off

Tell the user, explicitly:

- PR URL and what's in it.
- The path to the slice explainer, so they can read it before merging.
- The security-review result and any CodeQL/Dependabot alerts the PR will surface.
- That after they merge, the next `/start-slice` will fast-forward local `main` (or they can `git checkout main && git pull` themselves).
- Any threads deliberately left open, so they land in the next session's plan rather than being forgotten.

Do not merge the PR yourself; merging is the user's call.
