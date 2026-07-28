---
name: explain-diff
description: Produce a rich, interactive explainer for a CareerVault code change — a diff, branch, or PR — as a self-contained HTML page with background, intuition, a code walkthrough, and a five-question quiz. Use when the user wants to *understand* a slice rather than review it.
---

# Explain a diff

Teaching artifact, not a review. `/security-review` and `/code-review` judge a change;
this explains it, for a reader who wants to learn how the system actually works. CareerVault
is an AWS-learning vehicle, so this skill exists to close the loop between "Claude wrote a
slice" and "I understand the slice."

Runs as **step 5 of `/wrap-slice`** for every slice, after the docs are current and before the
commit — so the explainer ships in the same PR as the code it explains. It can also be invoked
on its own for any diff, branch, or PR.

## 1. Read before you write

The explanation is only worth the accuracy of its details. Before drafting:

- Read the actual diff (`git diff main...HEAD`, or `gh pr diff <N>`) and then **read the
  changed files in full** — the diff alone hides the surrounding code the reader needs.
- Read the canonical docs the change touches: the ADRs it added (`docs/careervault-adl.md`),
  the architecture sections it implements or corrects (`docs/careervault-architecture.md`),
  and the slice's section in `docs/careervault-plan.md`. **Name the ADR numbers in the
  explanation** — the "why" lives there and the reader should learn to follow that trail.
- Where the slice *corrected* a doc (a live API contradicting the architecture), say so
  explicitly and explain what reality forced. Those corrections are the highest-value
  teaching moments in this project.

## 2. Sections

- **Background** — the existing system this change lands in. Broadly explore surrounding
  code for this. We don't know how much the reader already knows: give a deep background
  for beginners (flag that it's skippable), then a narrow one directly relevant to the change.
  For CareerVault, that usually means the AWS-service shape (what a Lambda layer *is*, what
  an inference profile *is*) before the CareerVault-specific detail.
- **Intuition** — the essence of the change, not the details. Concrete examples with toy
  data. Diagrams liberally.
- **Code** — a high-level walkthrough of the changes, grouped and ordered so it reads as a
  story rather than a file list. Link files as `backend/functions/.../handler.py:120`.
- **Quiz** — five medium-difficulty multiple-choice questions. Hard enough that you must
  have understood the substance to answer; never gotchas. Interactive: clicking an option
  tells the reader whether they were right.

Where it fits naturally, include the **cross-cloud parallel** the ADL uses (the Azure/GCP
equivalent) — it's how this project builds transferable intuition.

## 3. Render with `render.py` — do not hand-write HTML

The CSS, quiz JavaScript, and page scaffolding are identical every time; regenerating ~250
lines of boilerplate per invocation wastes tokens and drifts in quality. Write a small JSON
content spec and render it:

```bash
python3 .claude/skills/explain-diff/render.py <spec.json>
```

Output defaults to `docs/explanations/YYYY-MM-DD-<slug>.html` (version-controlled — these
explainers are part of the project's learning record and get committed with the slice).
Run `python3 .claude/skills/explain-diff/render.py --help` for the exact JSON schema.

Write the spec to the scratchpad, not the repo — only the rendered HTML is committed.

- Section `html` fields are **raw HTML you write directly**. Use `<pre>` for code blocks
  (already `white-space: pre-wrap`), `.diagram` / `.flow` / `.box` / `.box.fail` divs for
  flow diagrams, `.callout` for key definitions and edge cases, plain `<table>` for
  comparisons.
- Quiz option order is randomized by the renderer. List options in whatever order reads
  naturally; don't hand-shuffle.
- **No ASCII diagrams** — use the renderer's HTML diagram classes.
- Pick a small number of diagram families and reuse them throughout: a simplified view of
  the UI for frontend changes, and a component/data-flow diagram *with example data* for
  backend changes. For CareerVault the recurring one is
  `Browser → CloudFront/API GW → Lambda → {DynamoDB, S3, Bedrock}`.
- Write with the clarity and flow of Martin Kleppmann — engaging, classic style, smooth
  transitions between sections.

## 4. Optionally publish as an Artifact

`--fragment` emits the page without the `<!doctype>`/`<head>`/`<body>` wrapper, which is what
the `Artifact` tool expects. Offer this when the user wants a shareable link rather than a
local file; the local `docs/explanations/` copy is still the canonical one.

```bash
python3 .claude/skills/explain-diff/render.py <spec.json> --fragment -o <scratchpad>/page.html
```

## Provenance

Recipe by Geoffrey Litt (gist `a29df1b5f9865506e8952488eac3d524`); the `render.py` renderer
and the JSON-spec split are from Ankit Gupta's fork (gist `8e808d387799de4e9839bc393f8e6405`).
The upstream gist also ships an `explain-diff-notion` variant that writes to a Notion page via
the Notion MCP server — not adopted here, since this project has no Notion MCP configured and
the HTML lands in the repo alongside the code it explains.
