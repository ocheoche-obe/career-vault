import { describe, expect, it } from "vitest";
import { resumeToPlainText } from "./resumeText";

/**
 * B-022 — the copyable plain-text rendering.
 *
 * The assertions that matter are the *absences*: a résumé built from a thin corpus legitimately has
 * no projects and no certifications, and a formatter that emits bare headings for them makes the
 * résumé look broken rather than the history look sparse.
 */

const FULL = {
  summary: "Cloud engineer with a serverless focus.",
  skills: ["AWS", "Python", "DynamoDB"],
  experience: [
    {
      title: "Senior Engineer",
      employer: "Acme",
      dates: "2022 – Present",
      bullets: ["Cut spend 40%", "Shipped an agent"],
    },
  ],
  projects: [{ name: "CareerVault", description: "Career tracker", bullets: ["Built it"] }],
  education: [{ degree: "BSc", institution: "A University", dates: "2018", details: ["First class"] }],
  certs: [{ name: "AWS SAA", issuer: "Amazon", date: "2026-03-14" }],
};

describe("rendering a résumé as plain text", () => {
  it("renders every section with its bullets", () => {
    const text = resumeToPlainText(FULL);

    expect(text).toContain("SUMMARY");
    expect(text).toContain("Cloud engineer with a serverless focus.");
    expect(text).toContain("SKILLS\nAWS, Python, DynamoDB");
    expect(text).toContain("Senior Engineer — Acme (2022 – Present)");
    expect(text).toContain("- Cut spend 40%");
    expect(text).toContain("CareerVault — Career tracker");
    expect(text).toContain("BSc — A University (2018)");
    expect(text).toContain("AWS SAA — Amazon — 2026-03-14");
  });

  it("omits sections that have no content rather than emitting a bare heading", () => {
    const text = resumeToPlainText({ summary: "Just a summary." });

    expect(text).toContain("SUMMARY");
    for (const heading of ["SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS"]) {
      expect(text).not.toContain(heading);
    }
  });

  it("leaves no dangling separator when a field is missing", () => {
    // The tell-tale of a template that assumed a field: "Senior Engineer — " with nothing after it.
    const text = resumeToPlainText({
      experience: [{ title: "Senior Engineer", bullets: ["Did a thing"] }],
    });

    expect(text).toContain("Senior Engineer");
    expect(text).not.toContain("Senior Engineer —");
    expect(text).not.toContain("()");
  });

  it("drops empty and whitespace-only bullets", () => {
    const text = resumeToPlainText({
      experience: [{ title: "Role", employer: "Co", bullets: ["Real", "   ", ""] }],
    });

    expect(text).toContain("- Real");
    expect(text.match(/^- /gm)).toHaveLength(1);
  });

  it("returns an empty string for a missing document", () => {
    // A completed run always has one, but an ADR-046 backfilled record could in principle not —
    // and the copy affordance must simply not render rather than throw.
    expect(resumeToPlainText(undefined)).toBe("");
    expect(resumeToPlainText({})).toBe("");
  });

  it("does not end with trailing blank lines", () => {
    // Pasted into a résumé, trailing whitespace becomes someone else's formatting problem.
    expect(resumeToPlainText(FULL)).toBe(resumeToPlainText(FULL).trimEnd());
  });
});
