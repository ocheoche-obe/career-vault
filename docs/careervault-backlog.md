# CareerVault — Backlog

> Things worth doing that aren't scoped into a numbered slice: UI polish, tech debt,
> follow-ups surfaced by a code review, doc corrections, nice-to-have features. This is
> **not** the roadmap — ordered slice work lives in
> [`careervault-plan.md`](careervault-plan.md). Items here are unordered and may never
> ship; that's fine.
>
> **Lifecycle (this is what keeps it from becoming a junk drawer):**
> - `wrap-slice` appends anything deferred during the slice (code-review findings not
>   fixed in-slice, UI gaps noticed, doc drift spotted).
> - `start-slice` reads this list and either pulls an item into the slice or consciously
>   leaves it — the list gets *looked at* every slice, not just written to.
> - When an item is done, mark it `done` with the slice/PR that closed it, then prune
>   `done` rows once they've been noted in a slice's completion notes.
>
> **Type** ∈ `ui` · `tech-debt` · `feature` · `docs` · `infra` · `test`
> **Priority** ∈ `P1` (do soon) · `P2` (should) · `P3` (someday)
> **Status** ∈ `open` · `in-progress` · `done` · `wontfix`

| ID | Item | Type | Priority | Surfaced in | Status | Notes |
|----|------|------|----------|-------------|--------|-------|
| B-001 | Flesh out the UI — current app is functional but visually basic (styling, layout, empty states, loading/error states, mobile polish). Scope a dedicated design pass; may warrant its own slice. | ui | P2 | post-slice-4 | open | Raised by Oche during post-slice-4 housekeeping. Not covered by any planned slice. |
| B-002 | Reconcile the architecture diagram's ACM Certificate node with reality — slice 4 shipped on the default `*.cloudfront.net` domain and custom domain is deferred, so ACM depicts a future state, not what's deployed. | docs | P2 | post-slice-4 | done | Closed by the post-slice-4 diagram redo (ACM dropped from the current-state diagram). |
| B-003 | Dedup precision for exact-identity entries (CERT/AWARD): ADR-033 semantic cosine (≥0.90) misses "same credential, different wording" — e.g. two AZ-900 certs scored 0.86 and both saved. A structured signal (issuer + normalized credential + date, with date-normalization since Haiku can mis-parse an expiry as the issue date) is more precise. Cross-cutting (chat entry path too), so an ADR-033 amendment, not a slice-5 fix. | feature | P2 | slice-5 | open | Verified by Oche during slice-5 UI test; measured cosine 0.86 < 0.90 (working as designed, not a bug). Consider a per-type threshold and/or structured cert/award identity match. |
| B-004 | Resume agent retrieval loop re-sends its full (growing) message history to Sonnet each iteration — the dominant per-run cost (~70K tokens / $0.31). Explore context compaction: summarise prior tool results, cap the retrieved-entry payload, or (for a small corpus) skip the agentic loop and feed all entries to the draft. Architecture change, not a tune — weigh against ADR-010's "own the loop" learning goal. | tech-debt | P2 | slice-6a | open | Surfaced in 6a advisory review. Tuning (`max_iterations 15→8`, `max_revisions 2→1`) already cut 85K→70K tokens; this is the next lever. Reduces the dominant $ driver vs the $5 ceiling. |
| B-005 | `resume_agent` uses one shared `_MAX_OUTPUT_TOKENS=4096` for all Sonnet phases. Fine for retrieval/critique, but a very rich career history's draft/revise JSON could approach it; today that degrades to `validation_abort` (retry, same cap). Consider a per-phase cap (higher for draft/revise). | tech-debt | P3 | slice-6a | open | Surfaced in 6a advisory review. Not hit in smoke (draft ~1.7K output tokens); robustness only. |
| B-006 | The completed-run metadata row (entries used / critique verdict / tokens / cost) is developer-facing, not user-facing — a real user doesn't need to see `critique: REVISE` or `$0.35`. Gate it behind a debug/dev toggle (or drop it) once the agent is no longer being actively evaluated. | ui | P3 | slice-6b | open | Raised by Oche during the 6b UI smoke: explicitly *wanted* while tuning and evaluating the agent, so keep it visible for now. Revisit at slice 9 hardening or whenever agent tuning settles. |
| B-007 | Total elapsed time vanishes when the résumé renders — the counter only exists during the `generating` phase, so the one moment you'd want to compare runs (right when the result lands) is the moment the number disappears. Carry the final elapsed into the completed-run metadata row. | ui | P3 | slice-6b | open | Raised by Oche during the 6b UI smoke. Pairs with B-006 — same metadata row, same evaluation use case, so do them together. |

<!-- Add new rows at the bottom. Keep each item to one line; detail goes in Notes or a linked ADR/plan section. -->
