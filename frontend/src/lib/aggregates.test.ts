import { describe, expect, it } from "vitest";
import {
  categoryCounts,
  computeStreak,
  deriveHomeStats,
  periodIndex,
  yearGrid,
} from "./aggregates";
import type { Entry } from "./api";

/**
 * ADR-045 defines "streak" in prose. These tests are what make that definition falsifiable — every
 * one of them corresponds to a sentence in the ADR that would otherwise be an opinion.
 */

let seq = 0;
function entry(createdAt: string, overrides: Partial<Entry> = {}): Entry {
  seq += 1;
  return {
    entry_id: `e${seq}`,
    entry_type: "PROJECT",
    title: `Entry ${seq}`,
    content: "",
    created_at: createdAt,
    ...overrides,
  };
}

// A Thursday, mid-ISO-week, so "the current period" is unambiguously unfinished.
const NOW = new Date("2026-08-06T12:00:00Z");
const DAY = 86_400_000;
const daysBefore = (n: number) => new Date(NOW.getTime() - n * DAY).toISOString();

describe("periodIndex", () => {
  it("puts a Monday and the following Sunday in the same weekly period", () => {
    const monday = new Date("2026-08-03T00:00:00Z");
    const sunday = new Date("2026-08-09T23:59:59Z");
    expect(periodIndex(monday, "weekly")).toBe(periodIndex(sunday, "weekly"));
  });

  it("separates adjacent weeks by exactly one", () => {
    const thisWeek = periodIndex(new Date("2026-08-06T00:00:00Z"), "weekly");
    const lastWeek = periodIndex(new Date("2026-07-30T00:00:00Z"), "weekly");
    expect(thisWeek - lastWeek).toBe(1);
  });

  it("supports quarterly, which the design's three cadence options omit but the backend has", () => {
    const q3 = periodIndex(new Date("2026-08-06T00:00:00Z"), "quarterly");
    const q2 = periodIndex(new Date("2026-05-06T00:00:00Z"), "quarterly");
    expect(q3 - q2).toBe(1);
    // Same quarter, two months apart.
    expect(periodIndex(new Date("2026-07-01T00:00:00Z"), "quarterly")).toBe(q3);
  });
});

describe("computeStreak", () => {
  it("is zero for an empty corpus", () => {
    expect(computeStreak([], "weekly", NOW).current).toBe(0);
  });

  it("counts consecutive weeks back from the current one", () => {
    const entries = [entry(daysBefore(0)), entry(daysBefore(7)), entry(daysBefore(14))];
    expect(computeStreak(entries, "weekly", NOW).current).toBe(3);
  });

  it("does NOT break the streak when the current period is merely unfinished", () => {
    // The single most consequential rule in ADR-045: without it, every user's streak reads zero
    // every Monday morning until they log something.
    const entries = [entry(daysBefore(7)), entry(daysBefore(14))];
    expect(computeStreak(entries, "weekly", NOW).current).toBe(2);
  });

  it("breaks on a genuinely skipped period", () => {
    // Logged three weeks ago and last week, but the week between is empty.
    const entries = [entry(daysBefore(7)), entry(daysBefore(21))];
    expect(computeStreak(entries, "weekly", NOW).current).toBe(1);
  });

  it("counts created_at and never event_date", () => {
    // A backfilled 2019 role must not extend a 2026 streak — that would invert what the metric
    // measures, from "the habit of logging" to "how long your career is".
    const backfilled = [
      entry(daysBefore(0), { event_date: "2019-03-01" }),
      entry(daysBefore(400), { event_date: "2026-08-01" }),
    ];
    expect(computeStreak(backfilled, "weekly", NOW).current).toBe(1);
  });

  it("counts several entries in one period as one period", () => {
    const entries = [entry(daysBefore(7)), entry(daysBefore(8)), entry(daysBefore(9))];
    expect(computeStreak(entries, "weekly", NOW).current).toBe(1);
  });

  it("reports the longest historical run independently of the current one", () => {
    // A four-week run last year, then a gap, then one recent week.
    const entries = [
      entry(daysBefore(0)),
      entry(daysBefore(70)),
      entry(daysBefore(77)),
      entry(daysBefore(84)),
      entry(daysBefore(91)),
    ];
    const streak = computeStreak(entries, "weekly", NOW);
    expect(streak.current).toBe(1);
    expect(streak.longest).toBe(4);
  });

  it("returns the recent window oldest-first with the current period last", () => {
    const streak = computeStreak([entry(daysBefore(0))], "weekly", NOW, 4);
    expect(streak.recent).toEqual([false, false, false, true]);
  });

  it("scales the period to the cadence", () => {
    // Two entries 30 days apart are two separate months, but a single quarter.
    const entries = [entry(daysBefore(0)), entry(daysBefore(30))];
    expect(computeStreak(entries, "monthly", NOW).current).toBe(2);
    expect(computeStreak(entries, "quarterly", NOW).current).toBe(1);
  });

  it("ignores entries with no created_at rather than throwing", () => {
    const entries = [entry(daysBefore(0)), { ...entry(daysBefore(7)), created_at: undefined }];
    expect(computeStreak(entries, "weekly", NOW).current).toBe(1);
  });
});

describe("categoryCounts", () => {
  it("surfaces every type present, not just the design's fixed five", () => {
    // The handoff hard-codes Roles/Projects/Milestones/Certifications/Awards, but the data model has
    // eight types — rendering only five would silently hide real entries.
    const entries = [
      entry(daysBefore(1), { entry_type: "EDUCATION" }),
      entry(daysBefore(2), { entry_type: "JOB" }),
      entry(daysBefore(3), { entry_type: "JOB" }),
    ];
    const counts = categoryCounts(entries);
    expect(counts).toEqual([
      { type: "JOB", label: "Roles", count: 2 },
      { type: "EDUCATION", label: "Education", count: 1 },
    ]);
  });

  it("is empty for an empty corpus", () => {
    expect(categoryCounts([])).toEqual([]);
  });
});

describe("yearGrid", () => {
  it("returns the full cell count with everything empty for no entries", () => {
    const grid = yearGrid([], NOW);
    expect(grid).toHaveLength(130);
    expect(grid.every((step) => step === 0)).toBe(true);
  });

  it("gives any bucket with activity a non-zero step", () => {
    // A bucket holding a single entry must never render as "none" — at this corpus size almost
    // every non-empty bucket holds exactly one.
    const grid = yearGrid([entry(daysBefore(5))], NOW);
    expect(grid.filter((step) => step > 0)).toHaveLength(1);
    expect(Math.max(...grid)).toBe(4);
  });

  it("drops entries older than the window rather than clamping them into the first bucket", () => {
    expect(yearGrid([entry(daysBefore(900))], NOW).every((s) => s === 0)).toBe(true);
  });
});

describe("deriveHomeStats", () => {
  it("counts the current quarter separately from the previous one", () => {
    const stats = deriveHomeStats([entry(daysBefore(1)), entry(daysBefore(120))], "weekly", NOW);
    expect(stats.total).toBe(2);
    expect(stats.thisQuarter).toBe(1);
    expect(stats.lastQuarter).toBe(1);
  });

  it("takes 'entries since' from event_date — the one place that field is the right one", () => {
    // The streak measures logging; "since" describes when the career history starts.
    const stats = deriveHomeStats(
      [entry(daysBefore(1), { event_date: "2019-06-01" })],
      "weekly",
      NOW,
    );
    expect(stats.sinceYear).toBe(2019);
  });

  it("returns the four most recent entries, newest first", () => {
    const entries = [1, 2, 3, 4, 5].map((n) => entry(daysBefore(n)));
    const latest = deriveHomeStats(entries, "weekly", NOW).latest;
    expect(latest).toHaveLength(4);
    expect(latest[0].created_at).toBe(daysBefore(1));
  });

  it("survives an empty corpus without NaN or throwing", () => {
    const stats = deriveHomeStats([], "weekly", NOW);
    expect(stats.total).toBe(0);
    expect(stats.sinceYear).toBeNull();
    expect(stats.streak.current).toBe(0);
    expect(stats.categories).toEqual([]);
  });
});
