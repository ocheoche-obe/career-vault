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

<!-- Add new rows at the bottom. Keep each item to one line; detail goes in Notes or a linked ADR/plan section. -->
