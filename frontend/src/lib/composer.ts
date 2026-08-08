/**
 * Shared between the two composers — Home's one-liner and the Log's conversation input.
 *
 * These lived in both files as copies. That is fine until it isn't: `MAX_MESSAGE_CHARS` mirrors the
 * backend's per-message cap, so two copies means a backend change silently leaves one composer
 * accepting text the API will reject; and two chip arrays drift apart on the first tweak to either.
 */

/** Mirrors the backend's per-message cap, so an over-long paste is caught here, not by a 4xx. */
export const MAX_MESSAGE_CHARS = 4000;

/** Chips seed the composer rather than sending, so the user still edits before anything goes out. */
export const CHIPS: { label: string; seed: string }[] = [
  { label: "Shipped something", seed: "I shipped " },
  { label: "Got recognized", seed: "I was recognized for " },
  { label: "Presented or taught", seed: "I presented " },
  { label: "Learned a skill", seed: "I learned " },
];

/** The Log offers one more than Home: by then the user is in the view where asking makes sense. */
export const LOG_CHIPS: { label: string; seed: string }[] = [
  ...CHIPS,
  { label: "Ask about my history", seed: "How many " },
];

/** ISO-8601 week number, used by both views' date eyebrow. */
export function isoWeek(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7);
}
