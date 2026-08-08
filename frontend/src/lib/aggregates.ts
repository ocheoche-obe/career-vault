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

/**
 * The year-activity grid.
 *
 * The handoff specifies 130 cells laid out column-major as 26 columns × 5 rows, with a month axis
 * every two months — which makes each column a fortnight and each cell ~2.8 days of a 364-day
 * window. That is an odd bucket size semantically, but it is what produces the intended visual, and
 * at this corpus size a bucket holds 0 or 1 entries either way.
 *
 * Returns intensity steps 0–4, oldest first, mapping onto `--heat-0` … `--heat-4`.
 */
export function yearGrid(entries: Entry[], now: Date = new Date(), cells = 130): number[] {
  const windowDays = 364;
  const bucketMs = (windowDays * DAY_MS) / cells;
  const start = now.getTime() - windowDays * DAY_MS;

  const counts = new Array<number>(cells).fill(0);
  for (const entry of entries) {
    const at = loggedAt(entry);
    if (!at) continue;
    const offset = at.getTime() - start;
    if (offset < 0) continue;
    const bucket = Math.min(cells - 1, Math.floor(offset / bucketMs));
    counts[bucket] += 1;
  }

  const max = Math.max(...counts, 0);
  if (max === 0) return counts.map(() => 0);
  // Four filled steps above "none"; a bucket with any activity never reads as empty.
  return counts.map((c) => (c === 0 ? 0 : Math.min(4, Math.ceil((c / max) * 4))));
}

/** The six months labelling the grid axis, every other month across the window. */
export function gridMonthLabels(now: Date = new Date()): string[] {
  const labels: string[] = [];
  for (let i = 12; i > 0; i -= 2) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - i + 1, 1));
    labels.push(d.toLocaleString("en-US", { month: "short", timeZone: "UTC" }).toUpperCase());
  }
  return labels;
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
  grid: number[];
  monthLabels: string[];
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
    monthLabels: gridMonthLabels(now),
    latest,
  };
}
