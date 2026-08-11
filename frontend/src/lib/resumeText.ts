import type { ResumeDocument } from "./api";

/**
 * Render a generated résumé as plain text (B-022).
 *
 * FR-5.3 offers three outputs — copyable bullets, an HTML preview, and a PDF — and slice 6 shipped
 * the last two. Someone who already maintains a résumé and just wants the tailored bullets had to
 * read them off an iframe or a PDF. This is the missing third: the data was already structured, so
 * this is an affordance over what exists, not new generation.
 *
 * Formatting lives client-side rather than behind an endpoint, matching ADR-045 — the API returns
 * the document, and turning it into text is deterministic arithmetic over data already in hand.
 *
 * Every section is optional and every empty one is dropped rather than emitted as a bare heading: a
 * résumé built from a thin corpus legitimately has no projects, and "PROJECTS" followed by nothing
 * reads as a bug in the résumé rather than an absence in the history.
 */
export function resumeToPlainText(doc: ResumeDocument | undefined): string {
  if (!doc) return "";
  const out: string[] = [];

  const section = (heading: string, lines: string[]) => {
    if (lines.length === 0) return;
    if (out.length) out.push("");
    out.push(heading, ...lines);
  };

  if (doc.summary?.trim()) section("SUMMARY", [doc.summary.trim()]);

  const skills = (doc.skills ?? []).filter((s) => s?.trim());
  if (skills.length) section("SKILLS", [skills.join(", ")]);

  const experience: string[] = [];
  for (const role of doc.experience ?? []) {
    // "Title — Employer (dates)", with each part dropped if absent rather than leaving punctuation
    // stranded. A dangling em dash is the tell-tale of a template that assumed a field.
    const title = [role.title, role.employer].filter(Boolean).join(" — ");
    const head = role.dates ? `${title} (${role.dates})` : title;
    if (head) experience.push(head);
    for (const bullet of role.bullets ?? []) if (bullet?.trim()) experience.push(`- ${bullet.trim()}`);
    if (head || (role.bullets ?? []).length) experience.push("");
  }
  section("EXPERIENCE", trimTrailingBlank(experience));

  const projects: string[] = [];
  for (const project of doc.projects ?? []) {
    const head = [project.name, project.description].filter(Boolean).join(" — ");
    if (head) projects.push(head);
    for (const bullet of project.bullets ?? []) if (bullet?.trim()) projects.push(`- ${bullet.trim()}`);
    if (head || (project.bullets ?? []).length) projects.push("");
  }
  section("PROJECTS", trimTrailingBlank(projects));

  const education: string[] = [];
  for (const item of doc.education ?? []) {
    const head = [item.degree, item.institution].filter(Boolean).join(" — ");
    // Gated like experience and projects above: an entry carrying only `dates` would otherwise emit
    // a stranded " (2018)", which `.filter(Boolean)` cannot catch because it is a non-empty string.
    if (head) education.push(item.dates ? `${head} (${item.dates})` : head);
    for (const detail of item.details ?? []) if (detail?.trim()) education.push(`- ${detail.trim()}`);
  }
  section("EDUCATION", education.filter(Boolean));

  const certs = (doc.certs ?? [])
    .map((c) => [c.name, c.issuer, c.date].filter(Boolean).join(" — "))
    .filter(Boolean);
  section("CERTIFICATIONS", certs);

  return out.join("\n");
}

function trimTrailingBlank(lines: string[]): string[] {
  while (lines.length && lines[lines.length - 1] === "") lines.pop();
  return lines;
}
