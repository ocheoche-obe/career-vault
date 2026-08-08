# Handoff: Career Vault redesign (dashboard + chat direction)

## Overview
This is the approved redesign of **Career Vault** — the personal career-wins repository that turns a
recurring chat check-in into structured career records, and drafts targeted résumés from them.

The redesign replaces the current tabbed SPA with a **data-centric dark dashboard** plus a **chat-first
logging flow**. The product intent: make the app feel worth returning to on a cadence. Streak, year-in-wins
grid, and category weighting give the user a reason to open it; prompt chips and a conversational log
remove the friction of writing an entry.

Direction chosen: concept **1b "Momentum"** (dark dashboard) merged with two pieces of concept **1d
"Companion"** (prompt chips, expanding chat with inline proposal cards + "Save to vault" wording).

Deliberate changes from the original 1b concept, per user review:
- Navigation is a **horizontal top bar**, not a left rail.
- The word **"Momentum" is removed from all UI copy** (the tab is simply "Home").
- The serif-italic accent face from 1d was dropped — **one sans across the entire UI**.
- The chat's sidebar toggle is labelled **"Hide activity" / "Show activity"**, not "Expand/Collapse".

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes that show intended look
and behavior. They are **not production code to copy directly**.

The target codebase is a **React + TypeScript SPA** (`frontend/src`, per `github.md`): `App.tsx` shell with
feature folders `chat/`, `entries/`, `upload/`, `resume/`, `settings/`, each with a plain `.css` file. The task
is to **recreate these designs in that existing environment using its established patterns** — React
function components, the existing routing/tab state in `App.tsx`, and plain CSS files per feature
(promote the tokens below into `index.css` as CSS custom properties rather than repeating hex values).

The HTML prototype uses inline styles only, because of how the design tool streams. **Do not port inline
styles into React.** Translate them into the codebase's CSS files.

## Fidelity
**High-fidelity.** Colors, typography, spacing, radii, and interactions are final. Recreate pixel-accurately
using the exact values in the Design Tokens section. Content copy in the prototype is representative
sample data drawn from the real user's records — replace with live API data, but **keep the exact
UI/label/microcopy strings**, which were reviewed and approved.

---

## Screens / Views

The app is a single shell: sticky header (66px) + a `<main>` per view. Only one view renders at a time,
driven by a `tab` state value: `home | log | timeline | resumes | import | details`.

### Shell — Header
- **Purpose**: identity, navigation, streak at a glance.
- **Layout**: `position: sticky; top: 0; z-index: 20`. Background `rgba(11,11,18,0.88)` with
  `backdrop-filter: blur(14px)`; bottom border `1px solid #1c1c2c`. Inner row: `max-width: 1280px`,
  `margin: 0 auto`, `padding: 0 32px`, `height: 66px`, `display: flex; align-items: center; gap: 20px`.
- **Components**:
  - **Logo mark**: 26×26, `border-radius: 7px`, `background: linear-gradient(145deg, #7c6cff, #b98cff)`.
    Wordmark "CareerVault" — 17px/700, `letter-spacing: -0.01em`, `#f5f3ff`. Group is
    `display: flex; gap: 10px; flex-shrink: 0`.
  - **Nav**: `display: flex; gap: 2px; min-width: 0; overflow-x: auto; flex-shrink: 1`, scrollbar hidden
    (`scrollbar-width: none`, `-ms-overflow-style: none`, `::-webkit-scrollbar { display: none }`).
    Items in order: **Home, Log, Timeline, Résumés, Import, Details**.
    Each: 15px, `padding: 8px 12px`, `border-radius: 9px`, no border, `white-space: nowrap`, `cursor: pointer`.
    - Inactive: `background: transparent`, `color: #8b88a8`, weight 400. Hover: `color: #f5f3ff`.
    - Active: `background: rgba(124,108,255,0.14)`, `color: #cbbcff`, weight 500.
  - **Streak pill** (right, `margin-left: auto`, group `gap: 14px; flex-shrink: 0`):
    `padding: 7px 13px`, `border-radius: 999px`, `border: 1px solid #26263c`, `background: #12121c`,
    `display: flex; align-items: center; gap: 9px`.
    - **Sparkline**: 8 bars, `display: flex; gap: 2px; align-items: flex-end`. Each bar 3px wide,
      `border-radius: 2px`. Logged week: 13px tall, `#9d7bff`. Missed week: 7px tall, `#2c2c44`.
      Prototype pattern is `[miss, hit ×7]`.
    - **Label**: "6-week streak" — JetBrains Mono 11px, `letter-spacing: 0.08em`, `#cbbcff`, `white-space: nowrap`.
  - **Avatar**: 30×30 circle, `background: #22223a`, initials JetBrains Mono 11px `#a8a4c0`.

### 1. Home
- **Purpose**: the reason to come back — see momentum, then log in one line without leaving the page.
- **Layout**: `<main>` `max-width: 1280px`, `padding: 34px 32px 60px`, `display: flex; flex-direction: column; gap: 22px`.
- **Components (top to bottom)**:
  1. **Greeting row** — `display: flex; align-items: flex-end; justify-content: space-between; gap: 30px`.
     - Left: eyebrow "Thu 30 Jul · week 31" (JetBrains Mono 11px, `letter-spacing: 0.14em`, uppercase, `#8b88a8`);
       `<h1>` "Good evening, Oche." — 32px/700, `letter-spacing: -0.02em`, `#f5f3ff`, `margin: 0`.
       *(Greeting word is time-of-day derived; name from the profile.)*
     - Right: 14px `#8b88a8`, right-aligned, `line-height: 1.5`: "Next check-in **Friday**" (the value in
       `#cbbcff`) then a line break and "Weekly cadence". "Friday" becomes "1 Aug" when cadence is Monthly.
  2. **Composer card** — `padding: 20px`, `border-radius: 16px`, `border: 1px solid #22223a`,
     `background: #12121c`, `display: flex; flex-direction: column; gap: 14px`.
     - Input row: `display: flex; align-items: stretch; gap: 10px`.
       - Text input: `flex: 1`, 16px, `padding: 15px 18px`, `border-radius: 12px`,
         `border: 1px solid #2b2b46`, `background: #0e0e17`, `color: #e8e6f2`, `outline: none`;
         `:focus` → `border-color: #4b3fa8`. Placeholder: "What did you accomplish? — a line is enough"
         (placeholder color `#6f6c88`).
       - Submit button: label **"Start logging"**, 15px/500, `padding: 0 26px`, `border-radius: 12px`,
         no border, `background: linear-gradient(145deg, #7c6cff, #9d7bff)`, `color: #fff`.
     - **Prompt chips row** — `display: flex; align-items: center; gap: 8px; flex-wrap: wrap`.
       Leading label "Not sure where to start" (JetBrains Mono 10px, `letter-spacing: 0.14em`, uppercase,
       `#6f6c88`, `margin-right: 4px`). Chips: 14px, `padding: 8px 14px`, `border-radius: 999px`,
       `border: 1px solid #2b2b46`, `background: #0e0e17`, `color: #cbbcff`;
       hover `border-color: #4b3fa8; background: #16162a`.
       Chips and their behavior:
       | Chip | Action |
       |---|---|
       | Shipped something | seeds input with `"I shipped "` |
       | Got recognized | seeds input with `"I was recognized for "` |
       | Presented or taught | seeds input with `"I presented "` |
       | Learned a skill | seeds input with `"I learned "` |
       | Quiet week | **sends immediately**: "Quiet period — mostly maintenance work and interviews for the new hire." |
       "Quiet week" is styled the same but `color: #8b88a8`; hover `border-color: #4b3fa8; color: #cbbcff`.
  3. **Stat trio** — `display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px`. Each card:
     `padding: 18px`, `border-radius: 14px`, `border: 1px solid #22223a`, `background: #12121c`,
     `display: flex; flex-direction: column; gap: 6px`. Label (JetBrains Mono 10px,
     `letter-spacing: 0.14em`, uppercase, `#8b88a8`) / value (JetBrains Mono 30px/700,
     `letter-spacing: -0.03em`, `#f5f3ff`) / sub (13px `#8b88a8`).
     - "In the vault" / total entry count / "entries since 2022"
     - "This quarter" / count this quarter / "up from 2 in Q2"
     - "Résumés built" / résumé count / "last: <first segment of most recent résumé title>"
  4. **Year in wins** — card `padding: 22px`, `border-radius: 16px`, `border: 1px solid #22223a`,
     `background: #12121c`, `display: flex; flex-direction: column; gap: 16px`.
     - Header row `display: flex; align-items: baseline; justify-content: space-between`:
       "Your year in wins" (16px/600 `#f5f3ff`) and range "Aug 2025 — Jul 2026" (JetBrains Mono 11px `#8b88a8`).
     - **Grid**: `display: grid; grid-auto-flow: column; grid-template-rows: repeat(5, 13px); gap: 4px;
       overflow: hidden`. 130 cells (≈26 weeks × 5 rows of activity buckets), each 13×13,
       `border-radius: 3px`. **Intensity ramp (5 steps)**:
       `#1a1a2c` (none) → `#3b2f7a` → `#5a45c4` → `#7c6cff` → `#a58cff` (most).
       In production, map each cell to a real period bucket and its entry count.
     - Month axis: `display: flex; justify-content: space-between`, JetBrains Mono 10px,
       `letter-spacing: 0.1em`, `#6f6c88`: AUG OCT DEC FEB APR JUN.
  5. **Two-column row** — `display: grid; grid-template-columns: 1.35fr 1fr; gap: 12px; align-items: start`.
     - **"Latest in the vault"** card (`padding: 20px`, `border-radius: 16px`, `border: 1px solid #22223a`,
       `background: #12121c`, `gap: 14px`): title 16px/600 `#f5f3ff`, then 4 rows. Each row is
       `display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; padding-bottom: 11px;
       border-bottom: 1px solid #1c1c2c` — entry title (15px/500 `#e8e6f2`), short date
       ("JUL 26", JetBrains Mono 11px `#6f6c88`), org/meta line (13px `#8b88a8`).
       Footer link button "Open the full timeline →" — 14px, transparent, `color: #cbbcff`,
       `align-self: flex-start`, navigates to Timeline.
     - **"Where the weight is"** card (same shell): title 16px/600. Five bar rows, each
       `display: flex; flex-direction: column; gap: 6px`: label row (13px `#a8a4c0`) with count on the right
       (JetBrains Mono `#6f6c88`); track `height: 6px; border-radius: 999px; background: #1c1c2c;
       overflow: hidden`; fill `height: 100%; border-radius: 999px;
       background: linear-gradient(90deg, #5a45c4, #a58cff)`, width = count / max × 100%.
       Categories: **Roles, Projects, Milestones, Certifications, Awards**.
       Closing insight line, 13px `#8b88a8`, `line-height: 1.5`:
       "Light on certifications — three of your last four résumé targets asked for one."
       *(This should be generated from real gap analysis, not hardcoded.)*

### 2. Log (chat)
- **Purpose**: the check-in conversation — the primary way records are created.
- **Entry points**: the "Log" nav item, or submitting from the Home composer (which switches to this view
  **and** sets `expanded = true`, so the conversation opens into the wider layout).
- **Layout**: `<main>` `width: 100%; margin: 0 auto`. Two states:
  - **Default (activity shown)**: `max-width: 1280px`, `padding: 34px 32px 60px`,
    grid `grid-template-columns: 1fr 320px; gap: 16px; align-items: start`.
  - **Activity hidden**: `max-width: 1080px`, `padding: 24px 32px 40px`,
    grid `grid-template-columns: 1fr` — sidebar unmounted, message area grows.
- **Chat panel**: `border-radius: 18px`, `border: 1px solid #22223a`, `background: #12121c`,
  `display: flex; flex-direction: column; overflow: hidden`.
  - **Panel header**: `padding: 16px 22px`, `border-bottom: 1px solid #1c1c2c`,
    `display: flex; align-items: center; justify-content: space-between`.
    Left: "Weekly check-in" (15px/600 `#f5f3ff`; the word follows cadence) over
    "THU 30 JUL · WEEK 31" (JetBrains Mono 10px, `letter-spacing: 0.14em`, uppercase, `#6f6c88`).
    Right: toggle button — JetBrains Mono 10px, `letter-spacing: 0.14em`, uppercase,
    `padding: 9px 14px`, `border-radius: 8px`, `border: 1px solid #2b2b46`, `background: #0e0e17`,
    `color: #cbbcff`; hover `border-color: #4b3fa8; background: #16162a`.
    Label is **"Hide activity"** when the sidebar is visible, **"Show activity"** when it is hidden.
  - **Message area**: `flex: 1; overflow-y: auto; padding: 24px 22px;
    display: flex; flex-direction: column; gap: 16px`.
    Height **400px** by default, **580px** when activity is hidden, `transition: height 0.32s ease`.
    Auto-scrolls to the bottom whenever a message is appended or the layout toggles.
    Every message row animates in: `animation: rise 0.28s ease both` where
    `@keyframes rise { from { opacity: 0; transform: translateY(8px) } to { opacity: 1; transform: none } }`.
  - **Message types**:
    1. **Prompt** (the check-in question, first message): `padding: 22px 24px`,
       `border-radius: 20px 20px 20px 6px`, `background: #16162a`, `border: 1px solid #26263c`,
       `max-width: 80%`, `gap: 9px`. Question 21px/500, `letter-spacing: -0.01em`,
       `line-height: 1.35`, `#f5f3ff`. Sub-line 13px `#8b88a8`: "Your weekly check-in · Friday".
       Question copy varies by cadence:
       - Weekly: "It's been a week since you logged the GenAI training — what have you been working on?"
       - Biweekly: "Two weeks since you logged the GenAI training — what have you been working on?"
       - Monthly: "It's been a month since the GenAI training landed — what has moved since?"
       *(Production: reference the user's most recent entry, not a fixed one.)*
    2. **User** message: `align-self: flex-end`, `max-width: 74%`, `padding: 15px 20px`,
       `border-radius: 20px 20px 6px 20px`,
       `background: linear-gradient(145deg, #6b5cf0, #8d74ff)`, `color: #fff`, 16px, `line-height: 1.5`.
    3. **Proposal card** (assistant's structured draft of the entry): outer bubble `padding: 20px 22px`,
       `border-radius: 20px 20px 20px 6px`, `background: #16162a`, `border: 1px solid #26263c`,
       `max-width: 84%`, `gap: 14px`.
       - Lead line, 15px `#a8a4c0`: "Here it is as a record — edit anything before it lands:"
       - Inner record preview: `padding: 16px`, `border-radius: 14px`, `background: #0e0e17`,
         `border: 1px solid #26263c`, `gap: 8px`.
         - Meta row `gap: 9px`: **kind badge** — JetBrains Mono 10px/700, `letter-spacing: 0.12em`,
           uppercase, `color: #cbbcff`, `background: rgba(124,108,255,0.16)`, `border-radius: 5px`,
           `padding: 4px 8px` — then "Jul 2026 · KPMG US" (13px `#8b88a8`).
         - Title 17px/600, `letter-spacing: -0.01em`, `#f5f3ff`.
         - Body 15px, `line-height: 1.5`, `#a8a4c0`.
       - **Unsaved actions** `display: flex; gap: 9px`:
         **"Save to vault"** (15px/500, `padding: 11px 20px`, `border-radius: 999px`, no border,
         `background: linear-gradient(145deg, #7c6cff, #9d7bff)`, `color: #fff`) and
         **"Edit"** (same metrics, `border: 1px solid #2b2b46`, transparent, `color: #a8a4c0`;
         hover `color: #f5f3ff; border-color: #4b3fa8`).
       - **After saving**, the buttons are replaced by a confirmation line: JetBrains Mono 11px,
         `letter-spacing: 0.12em`, uppercase, `color: #8ad6b0`: "✓ Saved to vault · record 014".
    4. **Note** (system follow-up after a save): `display: flex; align-items: center; gap: 12px`,
       `padding: 14px 18px`, `border-radius: 14px`, `background: rgba(124,108,255,0.08)`,
       `border: 1px solid #26263c`, `max-width: 82%`; text 15px/500 `#cbbcff`:
       "That is 14 records on deposit — and the streak holds at 7 weeks."
  - **Composer footer**: `padding: 16px 22px 20px`, `border-top: 1px solid #1c1c2c`,
    `display: flex; flex-direction: column; gap: 12px`.
    - **Prompt chips**: same five chips and behaviors as Home. **Visible only while the conversation has
      fewer than 3 messages** — they disappear once the user is engaged.
    - **Input pill**: `display: flex; align-items: center; gap: 10px; padding: 7px 7px 7px 20px;
      border-radius: 999px; background: #0e0e17; border: 1px solid #2b2b46`.
      Input: `flex: 1`, 16px, borderless, transparent, `color: #e8e6f2`,
      placeholder "Tell me what happened…". Send button: 40×40 circle, no border,
      `background: linear-gradient(145deg, #7c6cff, #9d7bff)`, `color: #fff`, glyph "↑" 17px.
      Enter key submits.
    - **Status row**: `display: flex; justify-content: space-between`, 13px `#6f6c88`:
      "<n> entries · 7 roles · <n> projects" and "6-week streak".
- **Activity sidebar** (320px column, `display: flex; flex-direction: column; gap: 12px`) — two cards,
  each `padding: 20px`, `border-radius: 16px`, `border: 1px solid #22223a`, `background: #12121c`:
  1. **Streak**: label (JetBrains Mono 10px, `letter-spacing: 0.14em`, uppercase, `#8b88a8`) "Streak";
     value row `align-items: baseline; gap: 7px` — "6" (JetBrains Mono 34px/700,
     `letter-spacing: -0.03em`, `#f5f3ff`) + "weeks logging" (14px `#8b88a8`);
     8-bar row `display: flex; gap: 4px`, each bar `flex: 1; height: 20px; border-radius: 4px`,
     hit = `linear-gradient(180deg, #7c6cff, #5a45c4)`, miss = `#1c1c2c`;
     caption 13px `#8b88a8`, `line-height: 1.45`: "Best run yet. One entry keeps it alive."
  2. **"Logged since Friday"**: title 15px/600 `#f5f3ff`, then 3 rows —
     `display: flex; flex-direction: column; gap: 3px; padding-bottom: 10px;
     border-bottom: 1px solid #1c1c2c`: entry title 14px `#e8e6f2`, meta 12px `#6f6c88`.

### 3. Timeline
- **Purpose**: browse and manage every record; the vault itself.
- **Layout**: `<main>` `max-width: 1280px`, `padding: 34px 32px 60px`, `gap: 20px`.
  Header row `display: flex; align-items: flex-end; justify-content: space-between; gap: 24px`, then
  `display: grid; grid-template-columns: 1.25fr 1fr; gap: 16px; align-items: start`.
- **Header**: eyebrow "<n> records · 2022 — 2026" (JetBrains Mono 11px, `letter-spacing: 0.14em`,
  uppercase, `#8b88a8`); `<h1>` "Timeline" 30px/700, `letter-spacing: -0.02em`, `#f5f3ff`.
- **Filters** (right of header, `display: flex; gap: 6px`): **All, Roles, Projects, Milestones,
  Certifications**. Each: JetBrains Mono 10px, `letter-spacing: 0.12em`, uppercase,
  `padding: 9px 13px`, `border-radius: 8px`.
  - Inactive: `border: 1px solid #22223a`, transparent, `color: #8b88a8`.
  - Active: `border: 1px solid #4b3fa8`, `background: rgba(124,108,255,0.14)`, `color: #cbbcff`.
- **List** (left column): `border-radius: 16px`, `border: 1px solid #22223a`, `background: #12121c`,
  `overflow: hidden`.
  - **Year divider**, rendered when the year changes: `padding: 12px 22px`, `background: #0e0e17`,
    `border-bottom: 1px solid #1c1c2c`, JetBrains Mono 10px, `letter-spacing: 0.16em`, `#6f6c88`.
  - **Row** (button, full width): `display: flex; flex-direction: column; gap: 6px;
    align-items: flex-start; text-align: left; padding: 16px 22px; border: none;
    border-bottom: 1px solid #1c1c2c`.
    Contents: meta row (kind badge — same badge style as the proposal card — plus date,
    JetBrains Mono 11px `#6f6c88`), title 16px/500 `letter-spacing: -0.01em` `#f5f3ff`,
    org 13px `#8b88a8`.
    - Default: `border-left: 2px solid transparent`, `background: transparent`. Hover: `background: #16162a`.
    - **Selected**: `border-left: 2px solid #7c6cff`, `background: #16162a`.
- **Detail panel** (right column): `position: sticky; top: 90px`, `border-radius: 16px`,
  `border: 1px solid #22223a`, `background: #12121c`.
  - Header strip: `padding: 16px 22px`, `border-bottom: 1px solid #1c1c2c`,
    `display: flex; justify-content: space-between`, JetBrains Mono 10px, `letter-spacing: 0.16em`,
    uppercase, `#6f6c88` — "Record 013" left, kind right in `#cbbcff`.
  - Body: `padding: 26px 22px`, `gap: 20px`. Title `<h2>` 26px/700, `line-height: 1.12`,
    `letter-spacing: -0.02em`, `#f5f3ff`; sub-line JetBrains Mono 11px `#6f6c88` "<org> · <date>";
    body `<p>` 15px, `line-height: 1.6`, `#a8a4c0`.
  - **Fact rows**: container `border-top: 1px solid #1c1c2c`; each row
    `display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #1c1c2c`.
    Keys (JetBrains Mono 10px, `letter-spacing: 0.14em`, uppercase, `#6f6c88`): **Logged** →
    value 14px `#e8e6f2` e.g. "20 Jul 2026, from chat"; **Used in** → value 14px `#cbbcff` e.g. "1 résumé".
  - **Actions**: `display: flex; gap: 9px`, both `flex: 1`, 14px, `padding: 12px 0`,
    `border-radius: 10px`, `border: 1px solid #2b2b46`, transparent.
    "Edit" `color: #f5f3ff` (hover `border-color: #4b3fa8`);
    "Delete" `color: #8b88a8` (hover `color: #ff9d9d; border-color: #4a2b3a`).

### 4. Résumés
- **Purpose**: generate and manage résumés drawn from the vault.
- **Layout**: `<main>` `max-width: 1100px`, `padding: 34px 32px 60px`, `gap: 20px`.
- **Components**:
  - Header: eyebrow "Drawn from your vault"; `<h1>` "Résumés" 30px/700, `letter-spacing: -0.02em`.
  - **Generator card** (`padding: 22px`, `border-radius: 16px`, `border: 1px solid #22223a`,
    `background: #12121c`, `gap: 16px`): "Draw a new one" 16px/600; input row `gap: 10px` with
    text input (`flex: 1`, 16px, `padding: 14px 18px`, `border-radius: 12px`,
    `border: 1px solid #2b2b46`, `background: #0e0e17`; focus `border-color: #4b3fa8`;
    placeholder "Target role — e.g. Senior AI Solutions Manager") and **"Generate"** button
    (15px/500, `padding: 0 24px`, `border-radius: 12px`, gradient
    `linear-gradient(145deg, #7c6cff, #9d7bff)`, `color: #fff`);
    helper 13px `#8b88a8`: "Pulls the <n> records in your vault and ranks them against the target."
    Submitting prepends a new card tagged "New" with meta "Built just now · <n> records ranked".
  - **Résumé grid**: `display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px`. Each card
    `padding: 20px`, `border-radius: 16px`, `border: 1px solid #22223a`, `background: #12121c`,
    `gap: 12px`: title row (`justify-content: space-between; gap: 12px; align-items: flex-start`) —
    title 17px/600 `letter-spacing: -0.01em` `#f5f3ff` and status badge (JetBrains Mono 10px,
    `letter-spacing: 0.12em`, uppercase, `color: #cbbcff`, `background: rgba(124,108,255,0.16)`,
    `border-radius: 5px`, `padding: 4px 8px`, `white-space: nowrap` — values: **Latest, Sent, Draft, New**);
    meta 13px `#8b88a8` "Built 12 Jul 2026 · 9 records drawn"; actions `gap: 8px; padding-top: 4px` —
    "View" and "Download", both 14px, `padding: 10px 16px`, `border-radius: 10px`,
    `border: 1px solid #2b2b46`, transparent (View `#f5f3ff`, Download `#a8a4c0`).

### 5. Import
- **Purpose**: one-time backfill — seed the vault from an existing résumé.
- **Layout**: `<main>` `max-width: 860px`, `padding: 34px 32px 60px`, `gap: 20px`.
- **Components**:
  - Header: eyebrow "One-time backfill"; `<h1>` "Import a résumé" 30px/700; intro `<p>`
    `max-width: 60ch`, 15px, `line-height: 1.6`, `#8b88a8`: "Start the vault with what you already have.
    We read the file, split it into records, and let you keep the ones worth keeping."
  - **Dropzone**: `padding: 44px`, `border-radius: 16px`, `border: 1px dashed #33335a`,
    `background: #0e0e17`, centered column `gap: 12px`. Icon tile 40×40, `border-radius: 12px`,
    `background: rgba(124,108,255,0.16)`, glyph "↑" 18px `#cbbcff`. Primary text 16px `#e8e6f2`
    "Drop a PDF or DOCX here"; file status 13px `#6f6c88`.
  - **Results card** (`padding: 22px`, `border-radius: 16px`, `border: 1px solid #22223a`,
    `background: #12121c`, `gap: 14px`): header row — "6 records found" 16px/600 and
    "<n> selected" (JetBrains Mono 11px `#8b88a8`).
    - **Selectable rows** (`display: flex; flex-direction: column; gap: 8px`), each a button:
      `display: flex; align-items: center; gap: 13px; width: 100%; padding: 14px 16px;
      border-radius: 12px`.
      - Selected: `background: #16162a`, `border: 1px solid #3a3468`.
      - Deselected: `background: #0e0e17`, `border: 1px solid #22223a`. Hover: `border-color: #4b3fa8`.
      - Checkbox 20×20, `border-radius: 6px`, `flex-shrink: 0`, centered "✓" 12px `#fff`;
        checked `background: #7c6cff; border: 1px solid #7c6cff`,
        unchecked `background: transparent; border: 1px solid #33335a`.
      - Text column `gap: 3px; text-align: left`: title 15px/500 `#f5f3ff`, meta 13px `#8b88a8`.
      - All rows start **selected**.
    - **Commit button**: "Save <n> to vault" — 15px/500, `padding: 13px 22px`, `border-radius: 12px`,
      gradient, `color: #fff`, `align-self: flex-start`. Navigates to Timeline on success.

### 6. Details (settings)
- **Purpose**: profile, cadence, reminders, data control.
- **Layout**: `<main>` `max-width: 860px`, `padding: 34px 32px 60px`, `gap: 20px`.
  Header eyebrow "Account", `<h1>` "Details" 30px/700.
- **Cards** (all `padding: 22px`, `border-radius: 16px`, `border: 1px solid #22223a`,
  `background: #12121c`, `gap: 16px`):
  1. **"You"** — `display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px`. Fields "Name"
     (editable, `color: #e8e6f2`) and "Email" (read-only, `color: #8b88a8`). Field labels:
     JetBrains Mono 10px, `letter-spacing: 0.14em`, uppercase, `#6f6c88`. Inputs: 15px,
     `padding: 13px 15px`, `border-radius: 10px`, `border: 1px solid #2b2b46`, `background: #0e0e17`;
     focus `border-color: #4b3fa8`.
  2. **"Check-in cadence"** — description 13px `#8b88a8`: "How often we ask what you've been working
     on. The streak counts one entry per period." Then
     `display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px` of option buttons
     (`padding: 16px`, `border-radius: 12px`, column, `gap: 6px`, `align-items: flex-start`):
     - Selected: `background: rgba(124,108,255,0.12)`, `border: 1px solid #4b3fa8`.
     - Unselected: `background: #0e0e17`, `border: 1px solid #22223a`. Hover: `border-color: #4b3fa8`.
     - Label 15px/600 `#f5f3ff`; description 13px `#8b88a8`, `text-align: left`, `line-height: 1.45`:
       | Option | Description |
       |---|---|
       | Weekly | A prompt every Friday. Best for a fast-moving role. |
       | Biweekly | Every other Friday. Enough to stay honest. |
       | Monthly | First of the month. Lightest touch. |
     - **Changing cadence resets the chat prompt copy** and updates the header's "Next check-in" value.
  3. **"Reminders"** — two toggle rows, each a button:
     `display: flex; align-items: center; justify-content: space-between; gap: 16px;
     padding: 14px 16px; border-radius: 12px; border: 1px solid #22223a; background: #0e0e17;
     text-align: left`; hover `border-color: #4b3fa8`.
     Label 15px `#f5f3ff` over sub 13px `#8b88a8`.
     - "Email me at check-in" / "To <email>, weekly." (cadence word is live)
     - "Warn me before the streak breaks" / "A nudge the day before the period closes."
     **Switch**: track 42×24, `border-radius: 999px`, `padding: 3px`, `flex-shrink: 0`,
     `display: inline-flex`; on → `background: #7c6cff; justify-content: flex-end`,
     off → `background: #22223a; justify-content: flex-start`. Knob 18×18 circle `#fff`.
     Both default **on**.
  4. **Data card** — `padding: 22px`, `border-radius: 16px`, `border: 1px solid #2b2b46`,
     `background: #0e0e17`, `display: flex; align-items: center; justify-content: space-between;
     gap: 20px`. Left: "Your vault, your data" 15px `#f5f3ff` over "Export every record as JSON,
     or close the account." 13px `#8b88a8`. Right: "Export" (14px, `padding: 11px 16px`,
     `border-radius: 10px`, `border: 1px solid #2b2b46`, `color: #f5f3ff`) and
     "Delete account" (`border: 1px solid #3a2430`, `color: #ff9d9d`; hover `background: #1c1017`).

---

## Interactions & Behavior

**Navigation** — header nav sets `tab`. "Open the full timeline →" on Home → Timeline.
"Save <n> to vault" on Import → Timeline. Submitting from the Home composer → Log (with activity hidden).

**Sending a message** (both composers, and the "Quiet week" chip):
1. Trim input; abort if empty.
2. Append a `user` message, switch to Log, set `expanded = true`, clear the input.
3. After **620ms**, append a `proposal` message. This simulated latency stands in for the real
   API call — replace with the actual request and show a proper pending state.
4. Message area auto-scrolls to the bottom.

**Proposal derivation** (prototype heuristics — production should use the existing backend extraction):
- **Title**: first sentence of the message, whitespace-collapsed, truncated to 78 chars with "…",
  first letter capitalized.
- **Kind**, by keyword match on lowercased text, first hit wins:
  `certif|passed|exam|credential` → CERTIFICATION · `award|recogni|promot` → AWARD ·
  `shipped|built|launch|pipeline|app|migrat` → PROJECT · else → MILESTONE.
- **Body**: the message; if under 120 chars, it is suffixed with
  " Logged during the <cadence> check-in."

**Saving a proposal** ("Save to vault"):
- Marks that proposal `saved`, assigns the next record number (zero-padded to 3), swaps the buttons
  for the green confirmation line.
- Appends a `note` message with the new deposit count and streak.
- Prepends the new record to the entry list — so Home's stat cards, "Latest in the vault",
  "Where the weight is" bars, the Timeline list, and the sidebar's "Logged since Friday" all update
  immediately. **Everything reads from one source of truth; nothing is duplicated per screen.**

**Activity toggle** — flips `expanded`; sidebar unmounts, main column narrows to 1080px, message area
animates 400px → 580px over 320ms, and the view re-scrolls to the bottom.

**Chips** — four seed the input (focus should follow); "Quiet week" sends immediately. The chat's chip row
hides once the conversation exceeds 2 messages.

**Timeline** — filters narrow the list by kind and the selection clamps to the filtered range.
Row click sets the selection; the detail panel is sticky at `top: 90px`.

**Import** — rows toggle selection; the counter and commit-button label track the count.

**Keyboard** — Enter submits in both chat/composer inputs.

**Transitions** — message-area height 0.32s ease; message entry `rise` 0.28s ease.
No other animation. Hover changes are instantaneous (no declared transition).

**Responsive** — the prototype is designed for **≥1280px desktop**. The header nav shrinks and scrolls
horizontally (scrollbar hidden) below that. Tablet/mobile layouts were **not** designed: the
two-column rows on Home, Log, and Timeline will need to stack, and the Timeline detail panel will need to
become a drawer or separate route. Confirm breakpoints before building.

## State Management
Single view-level state object; no external store needed.

| State | Type | Purpose |
|---|---|---|
| `tab` | `'home'｜'log'｜'timeline'｜'resumes'｜'import'｜'details'` | active view |
| `draft` | string | shared composer text (Home + chat) |
| `expanded` | boolean | Log: activity sidebar hidden when true |
| `msgs` | message[] | conversation; `null` = derive the cadence-based opening prompt |
| `added` | entry[] | records created this session, prepended to the base list |
| `nextNo` | number | next record number (014 in the prototype) |
| `selected` | number | Timeline row index (clamped to the filtered list) |
| `filter` | string | Timeline kind filter |
| `cadence` | `'Weekly'｜'Biweekly'｜'Monthly'` | drives prompt copy, next check-in, reminder sub-text |
| `target` | string | résumé generator input |
| `importOff` | Record<string, boolean> | deselected import rows (default = all selected) |
| `emailOn`, `streakAlertOn` | boolean | reminder switches |

**Message shape**: `{ id, type: 'prompt'｜'user'｜'proposal'｜'note', ... }` —
`prompt` adds `text, sub`; `user` adds `text`; `note` adds `text`;
`proposal` adds `lead, kind, when, title, body, saved, no?`.

**Entry shape**: `{ no, kind, title, org, date, year, short, body, logged, used }`
(`date` = "20 JUL 2026", `short` = "JUL 26", `year` = "2026").

**Data needs**: entry list (with kind + dates), per-period entry counts for the year grid and streak,
category counts, résumé list, and a gap-analysis string for "Where the weight is".
The three Home stat sub-lines ("entries since 2022", "up from 2 in Q2", résumé name) and the
gap-analysis line are hardcoded in the prototype — derive them server-side.

## Design Tokens

**Colors**
| Token | Value | Use |
|---|---|---|
| bg | `#0b0b12` | page background |
| surface | `#12121c` | cards, panels, header fill |
| surface-sunken | `#0e0e17` | inputs, inner previews, dropzone, year dividers |
| surface-raised | `#16162a` | selected/hover rows, prompt & proposal bubbles |
| border | `#22223a` | card borders |
| border-strong | `#2b2b46` | inputs, secondary buttons |
| border-subtle | `#1c1c2c` | internal dividers |
| border-dashed | `#33335a` | dropzone, unchecked boxes |
| border-active | `#4b3fa8` | focus + hover + selected borders |
| border-selected | `#3a3468` | selected import row |
| text-primary | `#f5f3ff` | headings, key values |
| text-body | `#e8e6f2` | body, input text |
| text-secondary | `#a8a4c0` | supporting prose |
| text-muted | `#8b88a8` | labels, meta |
| text-faint | `#6f6c88` | eyebrows, placeholders, timestamps |
| accent | `#7c6cff` | primary accent, switches, selection |
| accent-light | `#9d7bff` | gradient end |
| accent-lighter | `#b98cff` | logo gradient end |
| accent-text | `#cbbcff` | links, active nav, badges |
| accent-hover | `#e3d9ff` | link hover |
| accent-wash | `rgba(124,108,255,0.16)` | badge fill, icon tile |
| accent-wash-soft | `rgba(124,108,255,0.14)` | active nav/filter fill |
| accent-wash-faint | `rgba(124,108,255,0.12)` | selected cadence card |
| accent-wash-note | `rgba(124,108,255,0.08)` | note bubble |
| success | `#8ad6b0` | saved confirmation |
| danger | `#ff9d9d` | delete text |
| danger-border | `#3a2430` / `#4a2b3a` | delete borders |
| danger-wash | `#1c1017` | delete hover |
| scroll-thumb | `#22223a` | scrollbar |

**Gradients**
- Primary button / logo: `linear-gradient(145deg, #7c6cff, #9d7bff)` (logo ends `#b98cff`)
- User bubble: `linear-gradient(145deg, #6b5cf0, #8d74ff)`
- Bar fill: `linear-gradient(90deg, #5a45c4, #a58cff)`
- Streak bar: `linear-gradient(180deg, #7c6cff, #5a45c4)`
- Heatmap ramp: `#1a1a2c`, `#3b2f7a`, `#5a45c4`, `#7c6cff`, `#a58cff`

**Typography**
- **UI face: Figtree** (Google Fonts), weights 400/500/600/700 — used for *everything* except numerics
  and small caps labels. This was chosen deliberately over Jost, Poppins, Outfit and Work Sans: a soft
  grotesque with rounded terminals. **Do not reintroduce a serif accent face anywhere.**
- **Mono face: JetBrains Mono**, weights 400/500/700 — big numerals, dates, record numbers, and all
  uppercase micro-labels.
- Scale: `<h1>` 32px/700 (Home) · 30px/700 (other views) · `<h2>` 26px/700 ·
  chat prompt 21px/500 · card title 16–17px/600 · body 15–16px/400 ·
  meta 13–14px · micro-label 10–11px mono.
- Letter-spacing: `-0.03em` big mono numerals · `-0.02em` h1/h2 · `-0.01em` titles/wordmark ·
  `0.08em` streak label · `0.12em` badges/filters · `0.14em` eyebrows ·
  `0.16em` panel/divider labels.
- Line-height: 1.12 h2 · 1.35 chat prompt · 1.45–1.5 body · 1.6 long prose.

**Spacing** — 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 22, 24, 26, 30, 32, 34, 44, 60px.
Page padding `34px 32px 60px`; card padding 18/20/22px; section gap 20–22px; card grid gap 12px.

**Radii** — 2/3px micro bars · 5–6px badges & checkboxes · 7px logo · 8–9px small buttons & nav ·
10px inputs & secondary buttons · 12px inputs, chips-as-cards, toggle rows ·
14px stat cards & inner previews · 16px cards · 18px chat panel ·
20px bubbles (with a 6px "tail" corner) · 999px pills.

**Shadows** — none in the final design (surfaces are separated by border + fill).
Header uses `backdrop-filter: blur(14px)` over an 88%-opaque fill.

**Widths** — 1280px (Home, Log default, Timeline) · 1100px (Résumés) · 1080px (Log, activity hidden) ·
860px (Import, Details) · 320px activity sidebar.

## Assets
**None.** No images, icons, or icon fonts. Every glyph is a Unicode character in text —
"↑" (send, upload), "→" (timeline link), "✓" (checkbox, saved), "⤢" is no longer used.
The logo is a CSS gradient square; the avatar is a CSS circle with initials.
The two fonts load from Google Fonts:
`https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap`
If icons are wanted in production, substitute whatever icon library the codebase already uses —
do not hand-author SVG.

## Files

> **Renamed on intake (2026-08-07).** The bundle was unzipped at the repo root as
> `design_handoff_career_vault_redesign/` with spaces in the filenames; it now lives at
> `docs/design/v1.1-redesign/` with kebab-cased names, matching how the repo organises docs.
> Original names are given below so this file still matches what Claude Design produced.

- **`career-vault.dc.html`** (was `Career Vault.dc.html`) — the approved design. All six views, all
  interactions. **This is the reference.**
- `current-ui.dc.html` (was `Current UI.dc.html`) — the existing app rebuilt from `frontend/src`,
  for before/after comparison.
- `redesign-concepts.dc.html` (was `Redesign Concepts.dc.html`) — the four original concepts
  (1a Ledger, 1b Momentum, 1c Vault, 1d Companion). Kept for provenance: the final design is
  1b + 1d's chips and chat feel.
- `support.js` — the design tool's runtime. **Not part of the design; do not port.**
  *Not present in the delivered bundle — the zip contained only the three HTML files and this
  README. Nothing depends on it, since the prototypes are read for values, not executed.*

These files carry markup in a design-tool dialect (`<x-dc>`, `{{ }}` holes, `<sc-for>`, `<sc-if>`).
Read them for structure and exact values; the logic block at the bottom of each file holds the
state machine and the computed styles. Open `Career Vault.dc.html` in a browser to interact with it.

## Mapping to the existing codebase
| Design view | Existing files to modify |
|---|---|
| Shell, header, nav | `frontend/src/App.tsx`, `App.css`, `index.css` |
| Log | `frontend/src/chat/Chat.tsx`, `chat.css`, `chat/ProposalCard.tsx` |
| Home | new — dashboard view; reuse `entries/` data hooks |
| Timeline | `frontend/src/entries/Dashboard.tsx`, `EntryCard.tsx`, `entries.css` |
| Résumés | `frontend/src/resume/Resume.tsx`, `resume.css` |
| Import | `frontend/src/upload/Upload.tsx`, `upload.css` |
| Details | `frontend/src/settings/Settings.tsx`, `settings.css` |

**Home is the only genuinely new view.** It needs aggregate endpoints (period counts for the streak and
year grid, category counts, gap analysis) that the current API likely does not expose — scope that first.
The Log view is the largest rewrite of an existing screen: the proposal card gains the record preview
treatment and the "Save to vault" wording, and the check-in prompt, chips, and activity sidebar are new.
