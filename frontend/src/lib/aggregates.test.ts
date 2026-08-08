import { describe, expect, it } from "vitest";
import {
  categoryCounts,
  computeStreak,
  deriveHomeStats,
  formatEventDate,
  orgOf,
  periodIndex,
  periodStart,
  relativeSince,
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
  it("is a full year of days as 53 week-columns × 7 day rows", () => {
    const grid = yearGrid([], NOW);
    expect(grid.columns).toBe(53);
    expect(grid.cells).toHaveLength(53 * 7);
    expect(grid.cells.every((c) => c.step === 0)).toBe(true);
  });

  it("gives any day with activity a non-zero step", () => {
    // A day holding a single entry must never render as "none" — at this corpus size almost every
    // non-empty day holds exactly one.
    const grid = yearGrid([entry(daysBefore(5))], NOW);
    const lit = grid.cells.filter((c) => c.step > 0);
    expect(lit).toHaveLength(1);
    expect(lit[0].step).toBe(4);
  });

  it("groups several entries logged on one day into a single cell", () => {
    const sameDay = [entry(daysBefore(5)), entry(daysBefore(5)), entry(daysBefore(5))];
    const lit = yearGrid(sameDay, NOW).cells.filter((c) => c.step > 0);
    expect(lit).toHaveLength(1);
    expect(lit[0].count).toBe(3);
  });

  it("drops entries older than the window rather than clamping them into the first cell", () => {
    expect(yearGrid([entry(daysBefore(900))], NOW).cells.every((c) => c.step === 0)).toBe(true);
  });

  it("puts each row on a fixed weekday, which is what makes a check-in cadence visible", () => {
    // Column-major fill: cells 0-6 are the first week, and row N is the same weekday every column.
    const { cells } = yearGrid([], NOW);
    const firstColumnDay = new Date(cells[0].date).getUTCDay();
    const secondColumnDay = new Date(cells[7].date).getUTCDay();
    expect(firstColumnDay).toBe(1); // Monday
    expect(secondColumnDay).toBe(1);
  });

  it("marks days after today as future so they render invisible instead of empty", () => {
    // NOW is a Thursday, so the current week's Fri/Sat/Sun are future — real days, not absences.
    const { cells } = yearGrid([], NOW);
    const future = cells.filter((c) => c.future);
    expect(future).toHaveLength(3);
    expect(cells[cells.length - 1].future).toBe(true);
  });

  it("labels months at the column their month begins in, not at even intervals", () => {
    const { months } = yearGrid([], NOW);
    // A 53-week window spans 12-13 month boundaries.
    expect(months.length).toBeGreaterThanOrEqual(12);
    expect(months.every((m) => m.column >= 1 && m.column <= 53)).toBe(true);
    // Columns strictly increase — a label out of order would mean a mislabelled axis.
    const columns = months.map((m) => m.column);
    expect([...columns].sort((a, b) => a - b)).toEqual(columns);
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

/**
 * Regressions from the v1.1 slice 2 code review.
 *
 * Every one of these passed a full green suite before the fix, which is the point: the existing
 * tests exercised these functions only at values that happened to sit away from the boundary.
 */
describe("periodStart / periodIndex agreement (slice 2 review)", () => {
  it.each(["weekly", "biweekly", "monthly", "quarterly"] as const)(
    "%s: the start of a period is inside that same period",
    (cadence) => {
      // The invariant the biweekly bug broke. A week *index* cannot be converted back to a
      // timestamp by multiplying by WEEK_MS — the Unix epoch is a Thursday, so every multiple
      // lands on a Thursday. The old code returned a start four days early, i.e. in the
      // *previous* fortnight, so this equality failed by one.
      for (let offset = 0; offset < 40; offset += 1) {
        const d = new Date(Date.UTC(2026, 0, 1 + offset * 3));
        expect(periodIndex(periodStart(d, cadence), cadence)).toBe(periodIndex(d, cadence));
      }
    },
  );

  it("weekly and biweekly periods start on a Monday", () => {
    for (let offset = 0; offset < 40; offset += 1) {
      const d = new Date(Date.UTC(2026, 0, 1 + offset * 3));
      expect(periodStart(d, "weekly").getUTCDay()).toBe(1);
      // Was a Thursday — and rendered as "Logged since Thursday" in the Log sidebar.
      expect(periodStart(d, "biweekly").getUTCDay()).toBe(1);
    }
  });

  it("a biweekly period starts no more than 13 days back and never in the future", () => {
    const d = new Date("2026-08-08T12:00:00Z");
    const delta = d.getTime() - periodStart(d, "biweekly").getTime();
    expect(delta).toBeGreaterThanOrEqual(0);
    expect(delta).toBeLessThan(14 * 86_400_000);
  });
});

describe("relativeSince counts calendar days (slice 2 review)", () => {
  it("an entry logged yesterday evening is not 'today'", () => {
    // Elapsed time is 10 hours, so `floor(elapsed / 24h)` was 0 and the Log opened with
    // "You logged X today" for something logged the day before — the exact misstatement the
    // function exists to prevent.
    const from = new Date("2026-08-07T23:00:00Z");
    const now = new Date("2026-08-08T09:00:00Z");
    expect(relativeSince(from, now)).toBe("a day");
  });

  it("still returns null for something logged earlier the same day", () => {
    expect(relativeSince(new Date("2026-08-08T01:00:00Z"), new Date("2026-08-08T23:00:00Z"))).toBeNull();
  });

  it("boundaries do not depend on the time of day something was logged", () => {
    // 6d23h and 7d1h both fall on the same calendar-day count, so they must read alike.
    const now = new Date("2026-08-08T12:00:00Z");
    expect(relativeSince(new Date("2026-08-01T13:00:00Z"), now)).toBe("a week");
    expect(relativeSince(new Date("2026-08-01T11:00:00Z"), now)).toBe("a week");
  });
});

describe("orgOf (slice 2 review)", () => {
  it("finds the employer on a JOB, which the Log sidebar was missing", () => {
    // The sidebar checked only `organization`/`issuer`, so a role rendered the literal "JOB".
    expect(orgOf({ entry_type: "JOB", employer: "KPMG US" } as never)).toBe("KPMG US");
    expect(orgOf({ entry_type: "EDUCATION", institution: "A University" } as never)).toBe("A University");
    expect(orgOf({ entry_type: "CERT", issuer: "Microsoft" } as never)).toBe("Microsoft");
    expect(orgOf({ entry_type: "MILESTONE" } as never)).toBe("");
  });
});

describe("formatEventDate (slice 2 review)", () => {
  it("formats a calendar date in UTC, not the reader's zone", () => {
    // `new Date("2026-03-14")` is midnight UTC; formatting locally renders 13 Mar west of
    // Greenwich, so a certification appears earned the day before it was.
    expect(formatEventDate("2026-03-14", { year: "numeric" })).toBe("14 Mar 2026");
  });

  it("passes through anything that is not a full calendar date", () => {
    // The backend permits partial dates; mangling them into "Invalid Date" would be worse.
    expect(formatEventDate("2026-03")).toBe("2026-03");
    expect(formatEventDate(undefined)).toBe("");
  });
});
