---
name: start-slice
description: Session-start ritual for beginning a new CareerVault slice — reconcile git, reload canonical context, verify AWS access, cut the branch, and agree exit criteria before any code is written.
---

# Start a new slice

Run these steps in order. Do not write code until step 6 is confirmed.

## 1. Reconcile git

```bash
git fetch origin
git status -sb
```

- Local `main` must equal `origin/main`. If behind: `git checkout main && git merge --ff-only origin/main`. If it won't fast-forward, stop and show the user the divergence — never force anything.
- Working tree must be clean. If not, show the user what's dirty and ask before proceeding.
- Slice branches whose PRs are merged can be offered for local deletion (`git branch -d`), but only mention it — deletion is the user's call.

## 2. Reload canonical context

- Read **`docs/careervault-plan.md`**: the status board (where are we) and the current slice's
  detail section (goal, scope in/out, ⚠ decisions, exit criteria). If the board disagrees with
  git history, the CLAUDE.md phase marker, or the deployed state, flag that before anything else.
- Read the ADRs and architecture-doc sections the slice's "Key refs" line names.
- **Groom the backlog** — skim [`docs/careervault-backlog.md`](../../../docs/careervault-backlog.md).
  If an `open` item is a natural fit for (or a prerequisite of) this slice, fold it into scope;
  otherwise consciously leave it. The point is the list gets *looked at* every slice, not just
  written to. Surface anything you pull in when you present scope in step 6.
- Check memory for gotchas that apply (e.g. the Bedrock Anthropic use-case form).

## 3. Verify AWS access — and that it's the *right* account

CareerVault shares an AWS SSO login with a second project that lives in a **separate AWS account**
under the same Organization. Both are reachable from the same SSO session via different profiles, so
the real footgun is doing CareerVault work against the other account. Assert the account — don't just
eyeball it:

```bash
acct=$(AWS_PROFILE=careervault-dev aws sts get-caller-identity --query Account --output text) \
  && { [ "$acct" = "768396678224" ] \
       && echo "✓ CareerVault account $acct (us-east-1)" \
       || echo "✗ WRONG ACCOUNT $acct — expected 768396678224. Stop; do not run aws/sam."; }
```

- Expected account `768396678224`, region `us-east-1`. A mismatch means the profile points at the
  wrong account — stop and fix before any `aws`/`sam` command.
- **Always prefix AWS and SAM commands with `AWS_PROFILE=careervault-dev`.** Never rely on a default
  profile; the default may be the other project's account.
- If the SSO token is expired (the command errors), ask the user to run
  `aws sso login --profile careervault-dev` — do not attempt to log in for them.
- A project-level `SessionStart` hook (`.claude/settings.json` → `.claude/check-aws-profile.sh`) runs
  this same assertion automatically at the start of every session in this repo; this step is the
  manual belt-and-suspenders before you actually deploy.
- Skip only if the slice plan involves no AWS calls at all.

## 4. Confirm cost posture

Only if AWS work is planned this session: sanity-check month-to-date spend is within the $5 ceiling (Budgets console or `aws ce get-cost-and-usage`). One line in the summary is enough.

## 5. Cut the branch

From up-to-date `main`:

```bash
git checkout -b feat/phase2-slice<N>-<short-kebab-name>
```

Naming precedent: `feat/phase2-slice1-auth-settings`, `feat/phase2-slice2-chat-ingestion`.

## 6. Confirm scope and exit criteria — then stop

The plan doc's slice section already states scope, exit criteria, and ⚠ decisions. Before
writing code:

- Present them to the user, adjusted for anything learned since the roadmap was written. If
  scope changed materially, edit the plan doc's slice section so it stays authoritative.
- Resolve the slice's ⚠ decisions with the user. Per project convention, each decision not
  covered by the architecture doc becomes an ADR in `docs/careervault-adl.md` *before* the code
  that implements it.
- Flip the slice's status to 🔨 on the plan doc's status board.

Wait for the user to confirm scope and exit criteria before implementation begins.
