---
name: wrap-slice
description: End-of-slice checklist for CareerVault — verify tests and deployment, bring all canonical docs current (CLAUDE.md phase marker is blocking), commit, push, open the PR, and hand off cleanly.
---

# Wrap up a slice

Run these steps in order. The docs step is blocking: a slice is not done until the next session can cold-start from `CLAUDE.md` alone.

## 1. Verify the work

- Unit tests green: `python -m pytest tests/unit -q`.
- If the slice changed deployed behavior, confirm it was actually deployed to dev and smoke-tested end-to-end (real API Gateway → Lambda → downstream, not just unit tests). If smoke testing didn't happen, say so plainly — do not mark the slice complete.

## 2. Bring the docs current (blocking)

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
- **Memory** — save durable gotchas (account-level constraints, API behaviors that contradict docs) that future sessions need; update `MEMORY.md` index.

## 3. Commit and push

- Commits follow the existing conventional style (`feat(infra):`, `fix(ddb):`, `docs:`, `test:`), each ending with the Co-Authored-By trailer.
- Logical commits: infra / backend / tests / docs separated where it's natural, matching the history's grain.
- Push the slice branch to origin.

## 4. Open the PR

```bash
gh pr create --base main
```

PR body: what the slice delivers, exit criteria and how each was verified (including smoke-test evidence), decisions/ADRs added, doc corrections made. End with the "Generated with Claude Code" footer.

## 5. Hand off

Tell the user, explicitly:

- PR URL and what's in it.
- That after they merge, the next `/start-slice` will fast-forward local `main` (or they can `git checkout main && git pull` themselves).
- Any threads deliberately left open, so they land in the next session's plan rather than being forgotten.

Do not merge the PR yourself; merging is the user's call.
