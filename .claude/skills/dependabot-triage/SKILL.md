---
name: dependabot-triage
description: Triage a wave of Dependabot PRs — scope them, classify green/unmergeable/major, root-cause CI failures, merge safely, verify the merged state locally, and fix the config so the wave never recurs. Use when Dependabot has opened multiple dependency PRs (typically right after enabling it, when the first run flushes the whole backlog).
---

# Dependabot wave triage

Portable playbook (no project-specific assumptions). Distilled from the Ledgerly 13-PR
wave of 2026-07-15. The big picture: **the first Dependabot run is a backlog flush, not
the steady state** — once dependencies are current and grouping is configured, expect
roughly one grouped PR per ecosystem per interval.

## 1. Scope the wave

```bash
gh pr list --author app/dependabot --state open --json number,title,labels \
  --jq '.[] | {number, title, labels: [.labels[].name]}'
for n in <numbers>; do echo "--- #$n ---"; \
  gh pr checks $n --json name,state --jq '.[] | "\(.state)\t\(.name)"'; done
```

Bucket every PR into one of three classes before touching anything:

| Class | Signature | Action |
|---|---|---|
| Green minor/patch | All checks pass, semver-minor/patch | Merge in batch (§3) |
| Unmergeable-by-construction | CI fails in *dependency resolution*, before build | Close + fix grouping (§4) |
| Major | Semver-major bump, green or not | Deliberate decision (§5) |

## 2. Root-cause any red CI — read before touching

```bash
BR=$(gh pr view <n> --json headRefName --jq '.headRefName')
RUN=$(gh run list --branch "$BR" --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "$RUN" --log-failed | tail -40
```

The tell for unmergeable-by-construction: `npm error code ERESOLVE` (or pip's resolver
equivalent) during install. This means Dependabot split interdependent packages into
separate PRs — e.g. react 19 in one PR against react-dom 18 on the base, or a plugin
whose new major requires a framework major that has no open PR at all. **No amount of
rerunning fixes these; each solo PR conflicts with the base by definition.**

## 3. Merge the green ones

- Merge sequentially; Dependabot auto-rebases the survivors after each merge lands and
  CI re-runs — that churn is normal, not breakage.
- The Claude Code auto-mode classifier usually **blocks `gh pr merge`** for PRs the agent
  didn't author, even with chat approval. Don't grind against it: hand the user the loop
  (`for n in …; do gh pr merge $n --squash --delete-branch; done`) or the GitHub UI, or
  suggest allowlisting `Bash(gh pr merge:*)` in `.claude/settings.local.json`.
- A grouped PR opened *before* other merges landed may show conflicts or a stale
  lockfile. Comment `@dependabot recreate` on it — Dependabot rebuilds it from scratch
  against current main. (Often it has already rebased itself; the recreate is harmless.)

## 4. Close the unmergeable, fix the config

Close each unmergeable PR **with a comment** explaining why it can never go green solo
and what the plan is (closing tells Dependabot not to re-open that same update). Then fix
the root cause in `.github/dependabot.yml` — see `references/dependabot-template.yml`:

- **Named groups covering ALL update types** for interdependent families (react+react-dom
  +@types, vite+vitest+@vitejs/*), so ecosystem majors land as one atomic PR.
- **A minor/patch catch-all group per ecosystem** (`update-types: [minor, patch]`) with
  `exclude-patterns` for the named-group packages, so routine bumps arrive as one PR.
- **Monthly interval.** Security updates ignore the schedule and arrive immediately, so
  slowing version updates costs nothing on the safety side — it only cuts noise.

## 5. Majors get a deliberate decision

Never merge a major just because CI is green — check what the green actually proves
first (§6). Options, in order of preference: schedule it as a one-branch upgrade task
(all coupled packages together); or close with a "revisit when X" comment. Watch for
toolchain-coupled majors (framework + plugin + test runner) that must move as one set.

## 6. Verify the merged state — and audit what "green" means

After the batch lands, pull main and re-verify every ecosystem locally:

- **npm:** `npm ci && npm run build && npm test`
- **python:** reinstall pinned dev deps into the venv, then `pytest` + `ruff check`
- **IaC:** synth/plan (`cdk synth`, `terraform plan`) — no deploy needed to catch
  breakage from a lib bump

**Audit the test gates while you're here.** A frontend job green on
`vitest run --passWithNoTests` with zero test files proves typecheck+build only —
runtime is unverified until the next deploy. If you find a hollow gate, record a
minimum smoke test (render the app root, assert the landing state) as a near-term task,
and treat "auto-merge green Dependabot PRs" as off the table until the gate is real.

## 7. Prevent the next wave from hurting

- Fold a **Dependabot sweep into the session-start ritual**: security PRs first, then
  merge green grouped minor/patch, then majors as deliberate decisions. Batch-at-start
  beats interrupt-driven mid-work.
- Steady state after grouping + monthly cadence: ~1–2 PRs per interval, five minutes to
  clear. If you're seeing more, the grouping config has a hole — fix it there.
