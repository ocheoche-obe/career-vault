/**
 * Home's derived aggregates (ADR-045).
 *
 * Everything Home displays is computed here from the `GET /entries` response the view already
 * fetches — no new endpoint, no schema change, $0 added cost. Promotion to a server-side aggregate
 * is tracked as B-029 with an explicit trigger; the shapes returned here are designed not to change
 * when that happens.
 *
 * Pure functions taking an explicit `now`, so every branch is testable without faking the clock.
 */

import type { Entry } from "./api";

export type Cadence = "weekly" | "biweekly" | "monthly" | "quarterly";

/** Matches `CADENCE_DAYS` in the backend's `checkin_schedule.py` — the same cadence set FR-4.1 uses. */
export const CADENCE_NOUN: Record<Cadence, string> = {
  weekly: "week",
  biweekly: "fortnight",
  monthly: "month",
  quarterly: "quarter",
};

const DAY_MS = 86_400_000;
const WEEK_MS = 7 * DAY_MS;

/** UTC midnight of the Monday beginning the ISO week that contains `d`. */
function mondayOf(d: Date): number {
  const midnight = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  const dayOfWeek = new Date(midnight).getUTCDay() || 7; // Mon=1 … Sun=7
  return midnight - (dayOfWeek - 1) * DAY_MS;
}

/**
 * A monotonically increasing integer identifying the cadence period containing `d`.
 *
 * Anchored to the calendar rather than to "now" (ADR-045): a rolling window measured back from the
 * current instant would make a user's streak drift day to day with no action on their part. Integer
 * indices are what let the streak walk backwards one period at a time.
 */
export function periodIndex(d: Date, cadence: Cadence): number {
  switch (cadence) {
    case "weekly":
      return Math.floor(mondayOf(d) / WEEK_MS);
    case "biweekly":
      return Math.floor(Math.floor(mondayOf(d) / WEEK_MS) / 2);
    case "monthly":
      return d.getUTCFullYear() * 12 + d.getUTCMonth();
    case "quarterly":
      return d.getUTCFullYear() * 4 + Math.floor(d.getUTCMonth() / 3);
  }
}

/** `created_at` as a Date, or null when absent/unparseable. Never `event_date` — see below. */
function loggedAt(entry: Entry): Date | null {
  if (!entry.created_at) return null;
  const d = new Date(entry.created_at);
  return Number.isNaN(d.getTime()) ? null : d;
}

export type StreakResult = {
  /** Consecutive completed periods, counting back from the current one. */
  current: number;
  /** Longest such run anywhere in the history. */
  longest: number;
  /** Most recent `count` periods, oldest first — `true` where at least one entry was logged. */
  recent: boolean[];
};

/**
 * The streak, per ADR-045.
 *
 * Three decisions live in this function and each changes the number:
 *
 * 1. **`created_at`, never `event_date`.** A streak measures the *habit of logging*. Counting event
 *    dates would let a user backfill a 2019 job and extend a 2026 streak, inverting the metric.
 * 2. **The current period cannot break the streak until it ends.** An unfinished period with no
 *    entry is neutral, not a miss — otherwise every streak would read zero every Monday morning.
 * 3. **Periods are calendar-anchored** via `periodIndex`.
 */
export function computeStreak(
  entries: Entry[],
  cadence: Cadence,
  now: Date = new Date(),
  recentCount = 8,
): StreakResult {
  const logged = new Set<number>();
  for (const entry of entries) {
    const at = loggedAt(entry);
    if (at) logged.add(periodIndex(at, cadence));
  }

  const currentPeriod = periodIndex(now, cadence);

  // Start at the current period only if it already has an entry; otherwise start at the previous
  // one, which is what keeps an unfinished period neutral rather than breaking the run.
  let cursor = logged.has(currentPeriod) ? currentPeriod : currentPeriod - 1;
  let current = 0;
  while (logged.has(cursor)) {
    current += 1;
    cursor -= 1;
  }

  let longest = 0;
  let run = 0;
  let previous: number | null = null;
  for (const period of [...logged].sort((a, b) => a - b)) {
    run = previous !== null && period === previous + 1 ? run + 1 : 1;
    longest = Math.max(longest, run);
    previous = period;
  }

  const recent: boolean[] = [];
  for (let i = recentCount - 1; i >= 0; i -= 1) {
    recent.push(logged.has(currentPeriod - i));
  }

  return { current, longest, recent };
}

export type GridCell = {
  /** Intensity 0–4, mapping onto `--heat-0` … `--heat-4`. */
  step: number;
  /** ISO date (UTC) this cell represents — also its tooltip. */
  date: string;
  count: number;
  /** Days after today in the current, partial week. Rendered invisible, as GitHub does. */
  future: boolean;
};

export type YearGrid = {
  cells: GridCell[];
  columns: number;
  /** Month labels with the grid column each one starts at (1-based, for `grid-column`). */
  months: { label: string; column: number }[];
};

const GRID_WEEKS = 53;

/**
 * The year-activity grid — one cell per day, columns are ISO weeks, rows are day-of-week.
 *
 * **This deviates from the handoff deliberately.** It specified 130 cells as 26 columns × 5 rows,
 * which works out to ~2.8-day buckets and, at the card's real width, renders as a small dense block
 * occupying about a third of the card with the rest empty. Confirmed with Oche 2026-08-07: the
 * handoff is conceptual, and where an element does not work it should be amended rather than
 * reproduced faithfully.
 *
 * A day/week/day-of-week grid is the well-understood form (GitHub's contribution graph), it fills
 * the card width honestly at any size, and it earns a property the fortnight buckets could not: a
 * user who checks in every Friday produces a clean horizontal band, so the chart *shows the
 * cadence*, which is the entire point of Home.
 */
export function yearGrid(entries: Entry[], now: Date = new Date()): YearGrid {
  const counts = new Map<string, number>();
  for (const entry of entries) {
    const at = loggedAt(entry);
    if (!at) continue;
    const key = new Date(
      Date.UTC(at.getUTCFullYear(), at.getUTCMonth(), at.getUTCDate()),
    ).toISOString();
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  // Anchor to the Monday of the current week so the last column is the in-progress one, then step
  // back 52 weeks — 53 columns inclusive, which is what covers a full year at any start date.
  const lastMonday = mondayOf(now);
  const start = lastMonday - (GRID_WEEKS - 1) * WEEK_MS;
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());

  const cells: GridCell[] = [];
  const months: { label: string; column: number }[] = [];
  let previousMonth = -1;

  for (let column = 0; column < GRID_WEEKS; column += 1) {
    for (let row = 0; row < 7; row += 1) {
      const time = start + column * WEEK_MS + row * DAY_MS;
      const date = new Date(time);
      const key = date.toISOString();
      const count = counts.get(key) ?? 0;
      cells.push({ step: 0, date: key.slice(0, 10), count, future: time > today });

      // A month is labelled at the column containing its first Monday, so the label sits above the
      // week the month actually begins in rather than at an evenly-spaced guess.
      if (row === 0) {
        const month = date.getUTCMonth();
        if (month !== previousMonth) {
          previousMonth = month;
          months.push({
            label: date.toLocaleString("en-US", { month: "short", timeZone: "UTC" }).toUpperCase(),
            column: column + 1,
          });
        }
      }
    }
  }

  const max = Math.max(...cells.map((c) => c.count), 0);
  if (max > 0) {
    for (const cell of cells) {
      // Four filled steps above "none": a day with any activity never renders as empty.
      cell.step = cell.count === 0 ? 0 : Math.min(4, Math.ceil((cell.count / max) * 4));
    }
  }

  // Drop the first label if it would collide with the second — a window starting mid-month leaves
  // its first column only a week or two wide.
  if (months.length > 1 && months[1].column - months[0].column < 3) months.shift();

  return { cells, columns: GRID_WEEKS, months };
}

/**
 * Human labels for entry types.
 *
 * The handoff fixes five categories (Roles, Projects, Milestones, Certifications, Awards) but the
 * data model has eight. Rendering only five would silently hide real entries — the live corpus has
 * EDUCATION rows that would vanish — so every type actually present is shown instead. Deviation
 * recorded in ADR-045's "what cannot be derived is not faked" clause.
 */
export const TYPE_LABEL: Record<string, string> = {
  JOB: "Roles",
  PROJECT: "Projects",
  MILESTONE: "Milestones",
  CERT: "Certifications",
  AWARD: "Awards",
  EDUCATION: "Education",
  VOLUNTEER: "Volunteering",
  HOBBY: "Interests",
};

export type CategoryCount = { type: string; label: string; count: number };

/** Every entry type with at least one entry, most-populated first. */
export function categoryCounts(entries: Entry[]): CategoryCount[] {
  const counts = new Map<string, number>();
  for (const entry of entries) {
    const type = (entry.entry_type || "").toUpperCase();
    if (!type) continue;
    counts.set(type, (counts.get(type) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([type, count]) => ({ type, label: TYPE_LABEL[type] ?? type, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

function quarterOf(d: Date): number {
  return d.getUTCFullYear() * 4 + Math.floor(d.getUTCMonth() / 3);
}

export type HomeStats = {
  total: number;
  sinceYear: number | null;
  thisQuarter: number;
  lastQuarter: number;
  streak: StreakResult;
  categories: CategoryCount[];
  grid: YearGrid;
  latest: Entry[];
};

/** Everything Home renders, from one pass over the entry list. */
export function deriveHomeStats(
  entries: Entry[],
  cadence: Cadence,
  now: Date = new Date(),
): HomeStats {
  const currentQuarter = quarterOf(now);

  let thisQuarter = 0;
  let lastQuarter = 0;
  let earliest: number | null = null;

  for (const entry of entries) {
    const at = loggedAt(entry);
    if (!at) continue;
    const q = quarterOf(at);
    if (q === currentQuarter) thisQuarter += 1;
    if (q === currentQuarter - 1) lastQuarter += 1;

    // "entries since <year>" reads as when the *career history* starts, so it uses event_date where
    // one exists — the only place in this module that is the right field to reach for.
    const eventYear = entry.event_date ? new Date(entry.event_date).getUTCFullYear() : at.getUTCFullYear();
    if (!Number.isNaN(eventYear) && (earliest === null || eventYear < earliest)) earliest = eventYear;
  }

  const latest = [...entries]
    .filter((e) => e.created_at)
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
    .slice(0, 4);

  return {
    total: entries.length,
    sinceYear: earliest,
    thisQuarter,
    lastQuarter,
    streak: computeStreak(entries, cadence, now),
    categories: categoryCounts(entries),
    grid: yearGrid(entries, now),
    latest,
  };
}
