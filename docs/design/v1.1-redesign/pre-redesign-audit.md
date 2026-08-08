# Pre-redesign audit — accessibility, contrast, breakpoints

> **Status:** complete (v1.1 slice 1, 2026-08-07). Method: static read of `frontend/src`, plus a
> signed-in Chrome session driven through Playwright MCP against the deployed `careervault-dev` API.
>
> **Why this exists.** The v1.1 plan said to *enumerate before styling*. The obvious reading of that
> was "catalogue what's broken in the current UI" — but most of the current CSS is about to be
> deleted, so defects in it are bug reports against code that won't exist. The enumeration was
> therefore retargeted to the two things that **survive the redesign**:
>
> 1. **Accessibility findings**, which are properties of component and DOM structure — and the
>    redesign keeps the component structure, so it inherits every one of them silently.
> 2. **The incoming design itself**, which is silent on accessibility and ships two measurable WCAG
>    failures. Catching those before implementation is the difference between a fix and a rewrite.
>
> Layout defects in the current CSS were deliberately *not* catalogued.

---

## Part A — Accessibility of the current app

These are structural. Rebuilding the visual layer does not fix any of them; the redesign will carry
them forward unless each is addressed deliberately.

### A1. `<header>` is nested inside `<main>` — the banner landmark is lost

[`App.tsx:46-61`](../../../frontend/src/App.tsx#L46-L61) renders:

```jsx
<main>
  <header className="app-header">…</header>
  <nav className="view-nav">…</nav>
  {view === …}
</main>
```

A `<header>` inside `<main>` is **not** a `banner` landmark — the banner role is only granted when
`<header>` is scoped to the document body. Confirmed in the live accessibility tree, which is
precise about which one survives:

```yaml
- main:
  - generic:                      # <header> — banner role LOST
    - heading "CareerVault" [level=1]
    - generic: oche.ocheobe@gmail.com
    - button "Sign out"
  - navigation:                   # <nav> — navigation role SURVIVES
    - button "Chat"
    …
```

`<nav>` keeps its role wherever it sits, so navigation is intact; `<header>` silently degrades to a
`generic`. The result is a page with **no banner landmark at all**, and since everything lives
inside one `main`, "skip to content" and landmark-based navigation have nothing to work with.

**Fix in redesign:** `<header>` and `<nav>` become siblings of `<main>`, not children. The design's
sticky 66px header is a natural fit for a real `banner`.

### A2. Nav conveys the active tab by CSS class only — no `aria-current`

[`App.tsx:56-60`](../../../frontend/src/App.tsx#L56-L60): active state is `className={view === 'chat' ? 'active' : ''}`.
Nothing in the accessibility tree distinguishes the active view. A screen reader user cannot tell
which of the six tabs they are on.

**Fix in redesign:** `aria-current="page"` on the active nav button. The design's active styling
(`rgba(124,108,255,0.14)` fill, `#cbbcff`, weight 500) then has a semantic counterpart.

### A3. The chat textarea has no accessible name

[`Chat.tsx:154-158`](../../../frontend/src/chat/Chat.tsx#L154-L158): the `<textarea>` carries only
`placeholder="What did you accomplish?"`. A placeholder is not a label (WCAG 3.3.2, 4.1.2) — it is
announced inconsistently and vanishes the moment the user types.

This recurs in the redesign, which specifies placeholder-only inputs in **three** places: the Home
composer ("What did you accomplish? — a line is enough"), the chat input pill ("Tell me what
happened…"), and the résumé target field ("Target role — e.g. Senior AI Solutions Manager").

**Fix in redesign:** a visually-hidden `<label>` or `aria-label` on each. Costs nothing visually.

### A4. No live region on the chat transcript — assistant replies are never announced

[`Chat.tsx:101-145`](../../../frontend/src/chat/Chat.tsx#L101-L145): `.chat-scroll` is a plain `<div>`.
New assistant messages, proposal cards, and errors all append silently. For the app's primary
interaction, a screen reader user gets no notification that anything happened.

Notably, [`Resume.tsx:182`](../../../frontend/src/resume/Resume.tsx#L182) **does** get this right —
`role="status" aria-live="polite"` on the progress region, with `aria-hidden="true"` on the spinner.
The pattern exists in the codebase; it just was never applied to chat.

**Fix in redesign:** `aria-live="polite"` on the message area. The design's `rise` entry animation
is a purely visual analogue of the same event — both should fire together.

### A5. Message roles are invisible to assistive tech

Messages are `<div className={`bubble-row ${turn.role}`}>` — user vs assistant is conveyed by CSS
class, alignment, and colour alone. To a screen reader it is one undifferentiated stream with no
speaker attribution.

The redesign makes this **worse** if ported literally: it adds two more message types (`proposal`,
`note`) distinguished only by bubble fill, border radius, and tail corner.

**Fix in redesign:** a visually-hidden speaker prefix per message, or `role="article"` with an
`aria-label`. Four message types need four distinguishable announcements.

### A6. The typing indicator is an unlabelled literal ellipsis

[`Chat.tsx:145`](../../../frontend/src/chat/Chat.tsx#L145): `<div className="bubble typing">…</div>`
announces as the character "…". It should be `aria-hidden` with a live-region status message
alongside, or carry an accessible label.

### A7. "Retry" has no association with the message that failed

[`Chat.tsx:133-139`](../../../frontend/src/chat/Chat.tsx#L133-L139): the accessible name is bare
"Retry". With several failed sends in a transcript, every button is identically named.

### A8. Total ARIA/label usage across the app: 11 occurrences

`Settings.tsx` (7, wrapping `<label>` — valid implicit association), `EntryFields.tsx` (1),
`ReviewTable.tsx` (1), `Resume.tsx` (2, the good live region). **`Chat.tsx` and `Dashboard.tsx`
have zero** — the two highest-traffic views.

### A9. The file input has no accessible name at all

Confirmed live on the Upload view: `input[type=file]` resolves to **no accessible name** — not a
placeholder, not a label, nothing. A screen reader announces an unlabelled file-upload control.
Worse than A3, which at least has a placeholder.

The redesign replaces this with a dropzone whose visible text is "Drop a PDF or DOCX here". The
underlying input still needs a real name.

### A10. No view has its own `<h1>` — and the redesign will collide with that

Live heading structure, per view:

| View | Headings |
|---|---|
| Chat | `H1: CareerVault` — **no view heading at all** |
| Entries | `H1: CareerVault`, `H2: Jobs 7`, `H2: Certifications 4`, `H2: Education 2` |
| Upload | `H1: CareerVault`, `H2: Import from a resume` |
| Résumé | `H1: CareerVault`, `H2: Generate a tailored résumé` |
| Details | `H1: CareerVault`, `H2: Your details`, `H2: Check-in emails` |

The only `<h1>` anywhere is the app wordmark in the header; every view title is an `<h2>` beneath it.
Chat — the primary view — has no heading of its own at all.

The redesign inverts this: it gives each view a real title styled as `<h1>` (30–32px/700) **and**
keeps the "CareerVault" wordmark in the header. Ported naively that yields **two `<h1>`s per page**.

**Decision for this slice:** the wordmark is not a heading — render it as a `<span>` inside a link or
the banner. Each view's own title becomes the single `<h1>`. Log needs a heading it currently
lacks; "Weekly check-in" from the panel header is the natural candidate.

### A11. Live regions: zero across all five views at rest

The only `aria-live` in the app is inside `Resume.tsx`'s progress block, which renders *only while a
run is in flight* — correct behaviour, but it means at rest there is no live region anywhere. Every
other asynchronous state change in the app (chat replies, entry saves, upload parse results, settings
save confirmation) is silent to assistive tech.

### A12. Dead Vite starter CSS is still the app's design system

[`index.css`](../../../frontend/src/index.css) is largely the unmodified starter template:
`--social-bg` and `#social .button-icon`, `--code-bg` with `code {…}` styling, `.counter`,
`#root { text-align: center }`, and a 56px `h1` scale. **None of `#social`, `.counter`, or `<code>`
appears anywhere in the app.** `src/assets/react.svg`, `vite.svg` and `hero.png` are referenced
nowhere.

Not an accessibility finding, but it materially de-risks the redesign: replacing `index.css`
wholesale removes mostly dead code, and it explains why B-001 reads "functional but visually basic"
— the app never had a design system, it had a template.

**Also relevant:** the current `index.css` sets `color-scheme: light dark` and ships a full
`prefers-color-scheme: dark` palette, so the app follows the system theme today. **The redesign is
dark-only** — one palette, no light variant anywhere in the handoff. Dropping light mode is a real
product change and should be a conscious call, not a side effect of deleting the file.

---

## Part B — Contrast audit of the incoming design

The handoff specifies colours, type sizes, and focus behaviour but never states a contrast target,
and contains no accessibility section. Every token pair was measured against WCAG 2.1.

### B1. Full results

Foreground tokens against all four surface tokens (`bg #0b0b12`, `surface #12121c`,
`surface-sunken #0e0e17`, `surface-raised #16162a`):

| Token | bg | surface | sunken | raised | Verdict |
|---|---|---|---|---|---|
| `text-primary` #f5f3ff | 17.88 | 16.96 | 17.50 | 16.19 | ✅ |
| `text-body` #e8e6f2 | 15.91 | 15.09 | 15.57 | 14.41 | ✅ |
| `text-secondary` #a8a4c0 | 8.16 | 7.74 | 7.99 | 7.39 | ✅ |
| `text-muted` #8b88a8 | 5.78 | 5.48 | 5.65 | 5.23 | ✅ |
| **`text-faint` #6f6c88** | **3.90** | **3.70** | **3.82** | **3.53** | ❌ **fails AA** |
| `accent-text` #cbbcff | 11.37 | 10.79 | 11.13 | 10.30 | ✅ |
| `accent` #7c6cff | 5.09 | 4.82 | 4.98 | 4.61 | ✅ |
| `success` #8ad6b0 | 11.51 | 10.92 | 11.27 | 10.43 | ✅ |
| `danger` #ff9d9d | 9.86 | 9.35 | 9.66 | 8.93 | ✅ |

This is a careful palette with **two specific holes**. Everything else passes comfortably.

### B2. `text-faint` fails AA everywhere it is used — at the smallest size in the design

3.53–3.90 against a 4.5 requirement. There is no large-text exemption available: the handoff assigns
`text-faint` to eyebrows, placeholders, timestamps, record numbers, the year-grid month axis, and
panel/divider labels — **all specified at 10–11px**, far below the 18.66px-bold / 24px threshold. The
smallest text in the app is also its lowest-contrast text.

**Remedy — `#6f6c88` → `#817e99`.** Hue (246.4°) and saturation (11.5%) held exactly; HSL lightness
raised 47.8% → 54.6%. Clears AA on all four surfaces (4.55 / 4.76 / 4.92 / 5.02) at the minimum lift
that does so. The tonal ladder is preserved — it remains clearly fainter than `text-muted` #8b88a8.

### B3. Keyboard focus is effectively unindicated

The handoff specifies `outline: none` on inputs, with focus signalled *only* by swapping the border
from `border-strong #2b2b46` to `border-active #4b3fa8`:

| Measurement | Ratio | Required |
|---|---|---|
| `border-strong` → `border-active` (the state change itself) | **1.68** | — |
| `border-active` #4b3fa8 vs the input fill it sits on | **2.35** | 3.0 (WCAG 1.4.11) |
| `border-active` against the worst surface | **2.18** | 3.0 |

Removing the outline and replacing it with a change this faint fails WCAG 2.4.7 (Focus Visible) and
1.4.11 (Non-text Contrast). Keyboard-only navigation of the app becomes guesswork.

**Remedy — use `accent` #7c6cff for focus, not `border-active`.** The design already contains a token
that clears the bar; no new colour is invented:

| Candidate | Min ratio across surfaces | |
|---|---|---|
| `border-active` #4b3fa8 *(as specified)* | 2.18 | ❌ |
| **`accent` #7c6cff** | **4.61** | ✅ |
| `accent-light` #9d7bff | 5.68 | ✅ |
| `accent-text` #cbbcff | 10.30 | ✅ |

Implement as a real ring (`outline: 2px solid var(--accent); outline-offset: 2px`) rather than a
border swap, so focus is visible on buttons and chips too, not just inputs. `border-active` stays as
specified for **hover**, which carries no contrast requirement.

### B4. Lower-severity, non-blocking

- **Switch "off" track** `#22223a` on `surface` #12121c = **1.20**. A toggle whose off state is
  nearly invisible against its own card. WCAG 1.4.11 wants 3.0 for component state.
- **Year-grid step 1** `#1a1a2c` on `bg` = **1.15**. Arguably intentional (absence should recede),
  but the grid conveys its entire meaning through colour alone with an almost-invisible low end. It
  needs a non-colour affordance regardless — a `title`/tooltip carrying the period and count, which
  the handoff does not specify.
- **Card borders** `#22223a` on `surface` = 1.20. Fine as decoration, but the design uses border
  colour as the *sole* state signal for the selected import row (`#3a3468` vs `#22223a`) — that
  pairs with a checkbox, so it is acceptable; worth re-checking anywhere it stands alone.

---

## Part C — Breakpoints, derived from the design

The handoff states the prototype targets **≥1280px** and that tablet/mobile "were not designed…
Confirm breakpoints before building." These are derived from its own fixed widths rather than from
current-app breakage.

Design widths: **1280** (Home, Log default, Timeline) · **1100** (Résumés) · **1080** (Log, activity
hidden) · **860** (Import, Details) · **320** (activity sidebar, fixed).

| Breakpoint | Behaviour |
|---|---|
| **≥1280px** | The design exactly as specified. |
| **1024–1279px** | Max-widths collapse to viewport; all two-column layouts hold. Log is tightest: 1024 − 64 padding − 320 sidebar − 16 gap = **624px** for messages, workable. |
| **<1024px** | Home's `1.35fr 1fr` row stacks. Timeline's `1.25fr 1fr` → list full-width, detail panel becomes a drawer or its own route (the handoff names this as an open question). Log's activity sidebar moves below the chat panel. |
| **<768px** | Single column throughout: stat trio `repeat(3,1fr)` → 1, résumé grid `repeat(2,1fr)` → 1, cadence options `repeat(3,1fr)` → 1, "You" fields `repeat(2,1fr)` → 1. Page padding 32px → 20px. Header nav already scrolls horizontally by design. |

### C1. The year-in-wins grid cannot fit a mobile viewport

The spec is 130 cells as 26 columns × 5 rows, each 13×13px with 4px gaps:

```
26 × 13px + 25 × 4px = 338 + 100 = 438px
```

At a 375px viewport with 2×16px padding, **343px is available. It overflows by ~95px.** This is a
Home-view component and therefore in scope for this slice.

Options: wrap the grid in an `overflow-x: auto` container (preserves all 26 buckets, costs a scroll
gesture); or shrink cell/gap below 1024px (11px cells + 3px gaps = 356px, still marginal); or reduce
to 13 fortnightly buckets on mobile (changes what the chart means). **Recommend the scroll
container** — it keeps one data model across viewports, which matters because everything on Home
reads from one derived source.

> **Superseded — the grid was redesigned instead.** Building it revealed a second problem the
> measurement missed: at 442px inside a ~1172px card, the specified grid rendered as a small dense
> block with two thirds of its card empty, which read as unfinished rather than deliberate. Neither
> that nor the mobile overflow was fixable without changing the form, so with Oche's sign-off the
> grid became **one cell per day, 53 week-columns × 7 day-of-week rows** — the GitHub
> contribution-graph form. `1fr` columns make it fill any width honestly, and it earns a property
> the fortnight buckets could not: a user who checks in every Friday produces a clean horizontal
> band, so the chart *shows the cadence*, which is the point of Home. The scroll container is still
> there, now with a 620px floor below which cells stop being legible.

---

## Part D — Baseline measurements

Measured 2026-08-07 against the deployed `careervault-dev` API from a local dev server, 13-entry
corpus, Chrome via Playwright MCP.

### D1. NFR-2.3 (dashboard load ≤2s) — **met warm, failed cold**

| Condition | Click → rendered | of which `GET /entries` |
|---|---|---|
| **Cold (first load of session)** | **3686 ms** | 3639 ms |
| Warm, run 1 | 1133 ms | 613 ms |
| Warm, run 2 | 1012 ms | 497 ms |
| Warm, run 3 | 721 ms | 347 ms |
| Warm, run 4 | 895 ms | 397 ms |
| **Warm mean** | **~940 ms** | ~460 ms |

Nearly all latency is the API call, not rendering — the client is not the bottleneck at this corpus
size.

**The cold number is the one that matters, and this is not a nitpick.** NFR-2.3 states no cold/warm
qualifier, so as written the requirement is violated on the first load of every session. Worse, the
product *guarantees* cold starts: FR-4's whole design is a check-in email that brings the user back
on a weekly-to-monthly cadence. A user arriving from that email has not touched the app in a week —
the Lambda is always cold. **The cold path is the typical path for this app's core loop**, not an
edge case, so a warm-path average would be the wrong number to report.

This closes the NFR-2.3 half of **B-023**. The NFR-2.1 (ingestion ≤5s) and résumé-latency halves
remain open and belong to the other v1.1 workstream.

> Payload size could not be captured — `transferSize`/`encodedBodySize` report 0 because the API is
> cross-origin without `Timing-Allow-Origin`. Relevant to **B-013** (full-corpus reads carrying
> embeddings); measure server-side instead.

### D2. NFR-6.2 (mobile web) — **failed on every view**

At a 360px viewport, **every view overflows horizontally by 82px**, with the same offenders each
time:

| Element | Width | Right edge |
|---|---|---|
| `.app-header-user` (email + Sign out) | 241px | 402px |
| nav buttons (no wrap, no scroll) | 54–78px | up to 442px |

The scorecard marks NFR-6.2 ❓*Unverified*. It should read ❌ **Failed** — there is now a number.

> **Fixed in this slice.** After the shell rebuild: **0px overflow on all six views at 375px**,
> verified in-browser. The header's email string moved into a fixed-width account disclosure and the
> nav scrolls horizontally as the handoff specifies. Scorecard re-scored to ⚠️ rather than ✅ — zero
> overflow is one measurable property of "usable on mobile", and the five views behind the shell
> keep their pre-redesign internal layouts until v1.1 slice 2.

**The failure is entirely in the shell**, not in any individual view: `.app-header` is
`width: min(720px, 100%)` with a 241px email string that cannot compress, and `.view-nav` neither
wraps nor scrolls. That is a fortunate result — the shell is exactly what this slice rebuilds, so
one fix clears all five views at once. The design's header already solves it deliberately
(`overflow-x: auto` on the nav with the scrollbar hidden).

### D3. Type-size baseline

**No text in the current app renders below 12px.** Worth recording because the redesign *introduces*
10–11px mono micro-labels where none exist today — and assigns them the one token that fails
contrast (B2). The two compound: new smaller text, in the palette's weakest colour. Both must land
together or the redesign is a net accessibility regression on the smallest text in the app.

---

## Findings summary

| # | Finding | Severity | Where fixed |
|---|---|---|---|
| D2 | **NFR-6.2 failed** — 82px horizontal overflow on all 5 views at 360px, caused by the shell | **High** | Shell rebuild, **this slice** |
| D1 | **NFR-2.3 failed cold** — 3686ms vs a 2s budget; the check-in loop guarantees cold starts | **High** | Backend; feeds B-023 |
| B2 | `text-faint` fails WCAG AA on every surface, at the design's smallest type | **High** | ADR-043 · tokens, **this slice** |
| B3 | Keyboard focus effectively unindicated (`outline: none` + a 1.68 border swap) | **High** | ADR-043 · focus ring, **this slice** |
| A1 | `header` nested in `main` — banner landmark lost (nav survives) | **High** | Shell rebuild, **this slice** |
| A4 | No live region on chat transcript — replies never announced | **High** | Log view, next slice |
| A10 | No view has its own `h1`; redesign would ship two `h1`s per page | Medium | Shell + every view |
| A3 | Inputs labelled by placeholder only — 2 today, 3 in the new design | Medium | Every view as built |
| A9 | File input has no accessible name at all | Medium | Import view, next slice |
| A2 | No `aria-current` on the active nav item | Medium | Shell rebuild, **this slice** |
| A5 | Message roles invisible to AT; the new design adds two more types | Medium | Log view, next slice |
| C1 | Year-grid is 438px wide — overflows a 375px viewport by ~95px | Medium | Home view, **this slice** |
| A11 | No live regions at rest anywhere; all async state changes are silent | Medium | Every view as built |
| A6 | Typing indicator announces as a literal "…" | Low | Log view, next slice |
| A7 | "Retry" not associated with the message that failed | Low | Log view, next slice |
| B4 | Switch off-state 1.20; year-grid encodes meaning by colour alone | Low | Details / Home |
| D3 | Redesign introduces 10–11px text where none exists today — compounds B2 | Note | Ships with B2's fix |
| A12 | Dead starter CSS; light-mode support disappears with the redesign | Note | `index.css` replacement |

**Nine findings land in this slice** (D2, B2, B3, A1, A2, A10, C1, plus A3/A11 as they apply to the
shell and Home). The rest are recorded against the views that will fix them.
