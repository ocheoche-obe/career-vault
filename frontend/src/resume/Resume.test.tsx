import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Resume } from "./Resume";
import { stubFetch } from "../test/http";

/**
 * Résumés (v1.1 slice 3).
 *
 * The view had no component tests before this slice. Three things are pinned here beyond the happy
 * path: the **history list** and its badges (ADR-046), the **omissions** the design asked for and
 * the system cannot honestly supply, and the **copy** affordance (B-022) including its degraded
 * path when the clipboard is unavailable.
 */

const HISTORY = {
  resumes: [
    { run_id: "01JB", created_at: "2026-07-28T15:33:16Z", target_title: "Anthropic", entry_count: 13, status: "completed" },
    { run_id: "01JA", created_at: "2026-07-22T00:04:23Z", target_title: "Senior Cloud Architect", entry_count: 11, status: "completed" },
  ],
};

/**
 * The vault, which is a *different* number from either history row's `entry_count` — deliberately.
 * `entry_count` is how many entries one run retrieved; the generator copy is about how many exist.
 */
const VAULT = Array.from({ length: 27 }, (_, i) => ({ entry_id: `e${i}`, entry_type: "JOB" })) as never;

const COMPLETED_RUN = {
  status: "completed",
  run_id: "01JB",
  html_url: "https://s3.example/resume.html",
  pdf_url: "https://s3.example/resume.pdf",
  critique_verdict: "PASS",
  retrieved_count: 13,
  tokens: 20455,
  cost_usd: 0.116,
  elapsed_seconds: 74,
  document: {
    summary: "Cloud engineer.",
    experience: [{ title: "Engineer", employer: "Acme", bullets: ["Cut spend 40%"] }],
  },
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("résumé history (ADR-046)", () => {
  it("lists past résumés newest-first with their real metadata", async () => {
    stubFetch({ status: 200, body: HISTORY });
    render(<Resume idToken="tok" entries={VAULT} />);

    const cards = await screen.findAllByRole("heading", { level: 3 });
    expect(cards.map((c) => c.textContent)).toEqual(["Anthropic", "Senior Cloud Architect"]);
    expect(screen.getByText(/13 records drawn/)).toBeInTheDocument();
  });

  it("formats the build date in UTC", async () => {
    // The slice-2 lesson: `created_at` is UTC-anchored, and formatting it locally renders the
    // previous evening for anyone west of Greenwich — "27 Jul" for a résumé built on the 28th.
    stubFetch({ status: 200, body: HISTORY });
    render(<Resume idToken="tok" entries={VAULT} />);

    await screen.findByText("Anthropic");
    const meta = document.querySelector(".history-meta")!;
    expect(meta.textContent).toContain("Built 28 Jul 2026");
  });

  it("badges only the newest as Latest, and never as Sent or Draft", async () => {
    // ADR-045: the handoff specifies Latest/Sent/Draft/New. There is no send path (ADR-015 is
    // in-app download only) and no draft state, so two of those four badges describe features that
    // do not exist and are omitted rather than faked.
    stubFetch({ status: 200, body: HISTORY });
    render(<Resume idToken="tok" entries={VAULT} />);

    await screen.findByText("Anthropic");
    expect(screen.getAllByText("Latest")).toHaveLength(1);
    expect(screen.queryByText("Sent")).not.toBeInTheDocument();
    expect(screen.queryByText("Draft")).not.toBeInTheDocument();
  });

  it("says the résumés are kept when there are none yet", async () => {
    stubFetch({ status: 200, body: { resumes: [] } });
    render(<Resume idToken="tok" entries={VAULT} />);

    expect(await screen.findByText(/Nothing here yet/)).toBeInTheDocument();
  });

  it("says the list failed rather than claiming there are none", async () => {
    // `listResumes` resolves `{ ok: false, resumes: [] }` on a non-2xx rather than throwing, so a
    // component that reads only `resumes` renders the empty state — telling someone with a dozen
    // résumés that they have none. The distinction matters most to the user most likely to panic.
    stubFetch({ status: 500, body: { message: "nope" } });
    render(<Resume idToken="tok" entries={VAULT} />);

    expect(await screen.findByText(/Couldn't load your résumés/)).toBeInTheDocument();
    expect(screen.queryByText(/Nothing here yet/)).not.toBeInTheDocument();
  });

  it("still lets you generate when history fails to load", async () => {
    // History is a secondary panel. A list that cannot load must not block the primary action.
    stubFetch({ networkError: true });
    render(<Resume idToken="tok" entries={VAULT} />);

    await waitFor(() => expect(screen.getByText(/Couldn't load your résumés/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Generate" })).toBeInTheDocument();
  });

  it("counts the vault, not the last run's retrieved subset", async () => {
    // The generator copy said "Pulls the {n} records in your vault" while `n` came from the newest
    // history row's `entry_count` — the entries *that run selected for its target*. With 27 entries
    // and a newest run that retrieved 13, it told the user their vault held 13. A wrong number
    // presented authoritatively is the ADR-045 / B-015 failure mode, not a rounding detail.
    stubFetch({ status: 200, body: HISTORY });
    render(<Resume idToken="tok" entries={VAULT} />);

    expect(await screen.findByText(/Pulls the 27 records in your vault/)).toBeInTheDocument();
    expect(screen.queryByText(/Pulls the 13 records/)).not.toBeInTheDocument();
  });

  it("omits the count entirely while the vault is still loading", async () => {
    stubFetch({ status: 200, body: HISTORY });
    render(<Resume idToken="tok" entries={null} />);

    expect(await screen.findByText(/Pulls the records in your vault/)).toBeInTheDocument();
  });

  it("opens a past résumé from its View button", async () => {
    stubFetch({ status: 200, body: HISTORY }, { status: 200, body: COMPLETED_RUN });
    render(<Resume idToken="tok" entries={VAULT} />);
    const user = userEvent.setup();

    const card = (await screen.findByRole("heading", { level: 3, name: "Anthropic" })).closest("li")!;
    await user.click(within(card).getByRole("button", { name: "View" }));

    expect(await screen.findByRole("heading", { name: /your tailored résumé/i })).toBeInTheDocument();
  });
});

describe("a completed run", () => {
  async function showCompleted() {
    stubFetch({ status: 200, body: HISTORY }, { status: 200, body: COMPLETED_RUN });
    render(<Resume idToken="tok" entries={VAULT} />);
    const user = userEvent.setup();
    const card = (await screen.findByRole("heading", { level: 3, name: "Anthropic" })).closest("li")!;
    await user.click(within(card).getByRole("button", { name: "View" }));
    await screen.findByRole("heading", { name: /your tailored résumé/i });
    return user;
  }

  it("reports elapsed time in the metadata row (B-007)", async () => {
    // The counter used to exist only while generating, so the number vanished at exactly the moment
    // you would compare two runs.
    await showCompleted();
    expect(screen.getByText("1m 14s")).toBeInTheDocument();
  });

  it("copies the résumé as plain text (B-022)", async () => {
    const user = await showCompleted();

    // Installed *after* `showCompleted`, because `userEvent.setup()` replaces
    // `navigator.clipboard` with a stub of its own — defining this first means user-event
    // silently overwrites it and the assertion fails with "called 0 times".
    // Typed via the generic rather than a declared parameter: the call tuple has to be `[string]`
    // for `calls[0][0]` to typecheck, and an unused parameter would trip lint.
    const writeText = vi.fn<(text: string) => Promise<void>>(async () => {});
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });

    await user.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = writeText.mock.calls[0][0];
    expect(copied).toContain("Cut spend 40%");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("still shows the text when the clipboard is blocked", async () => {
    // Clipboard access is permission-gated and absent over plain http. The text is rendered in a
    // readonly (not disabled) textarea precisely so a failure degrades to "select it yourself".
    const user = await showCompleted();

    // After setup, for the same reason as above — otherwise user-event's working stub answers and
    // the copy succeeds, which is the opposite of what this test exists to check.
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async () => {
          throw new Error("denied");
        },
      },
    });

    await user.click(screen.getByRole("button", { name: "Copy" }));

    const textarea = screen.getByLabelText(/plain text/i) as HTMLTextAreaElement;
    expect(textarea.value).toContain("Cut spend 40%");
    expect(textarea).not.toBeDisabled();
    expect(screen.queryByRole("button", { name: "Copied" })).not.toBeInTheDocument();
  });

  it("does not offer Regenerate on a résumé opened from history", async () => {
    // Regenerate reruns whatever is in the target textarea. For a history-opened résumé that is
    // either empty or an unrelated job description — and neither the list projection nor the poll
    // payload carries the original `target_text`, so there is nothing to regenerate *from*. The
    // button would spend $0.11-$0.35 of Sonnet against the wrong target while showing the old one.
    await showCompleted();

    expect(screen.queryByRole("button", { name: "Regenerate" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New target" })).toBeInTheDocument();
  });

  it("keeps the plain-text panel open when Copy is clicked", async () => {
    // The button sits inside <summary>, so without preventDefault the click also toggles the
    // disclosure — copying the text and hiding it in one gesture, which additionally hides the
    // select-it-yourself fallback that exists for a blocked clipboard.
    const user = await showCompleted();
    const details = document.querySelector("details.result-text") as HTMLDetailsElement;
    details.open = true;

    await user.click(screen.getByRole("button", { name: "Copy" }));

    expect(details.open).toBe(true);
  });

  it("downloads the PDF cross-origin without a download attribute", async () => {
    // Browsers ignore `download` across origins, so save-to-disk comes from the presigned
    // Content-Disposition instead. An added `download` here would be cargo cult.
    await showCompleted();
    const link = screen.getByRole("link", { name: /download pdf/i });
    expect(link).toHaveAttribute("href", COMPLETED_RUN.pdf_url);
    expect(link).not.toHaveAttribute("download");
  });
});

describe("starting a run", () => {
  it("refuses to start with an empty target", async () => {
    stubFetch({ status: 200, body: { resumes: [] } });
    render(<Resume idToken="tok" entries={VAULT} />);
    await screen.findByText(/Nothing here yet/);

    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
  });

  it("announces the long wait in a live region (§A11)", async () => {
    stubFetch(
      { status: 200, body: { resumes: [] } },
      { status: 202, body: { run_id: "01JNEW", status: "pending" } },
      { status: 200, body: { status: "pending", run_id: "01JNEW" } },
    );
    render(<Resume idToken="tok" entries={VAULT} />);
    const user = userEvent.setup();

    await screen.findByText(/Nothing here yet/);
    await user.type(screen.getByLabelText(/target role/i), "Staff SRE");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(/building your résumé/i);
  });
});

describe("accessibility", () => {
  it("has exactly one h1", async () => {
    stubFetch({ status: 200, body: HISTORY });
    render(<Resume idToken="tok" entries={VAULT} />);
    await screen.findByText("Anthropic");

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Résumés");
  });

  it("gives the target field a real accessible name, not a placeholder (§A3)", async () => {
    stubFetch({ status: 200, body: HISTORY });
    render(<Resume idToken="tok" entries={VAULT} />);
    await screen.findByText("Anthropic");

    expect(screen.getByLabelText(/target role or job description/i)).toBeInTheDocument();
  });
});

describe("deleting a résumé (ADR-046 amendment)", () => {
  it("asks for confirmation naming the résumé, and does nothing if declined", async () => {
    // ADR-027's safety net. Naming the target matters because every card's button says "Delete" —
    // a bare "Are you sure?" is dismissible on autopilot without registering which one.
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const calls = stubFetch({ status: 200, body: HISTORY });
    render(<Resume idToken="tok" entries={VAULT} />);
    const user = userEvent.setup();

    const card = (await screen.findByRole("heading", { level: 3, name: "Anthropic" })).closest("li")!;
    await user.click(within(card).getByRole("button", { name: /delete the résumé for Anthropic/i }));

    expect(confirmSpy.mock.calls[0][0]).toContain("Anthropic");
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    expect(screen.getByRole("heading", { level: 3, name: "Anthropic" })).toBeInTheDocument();
  });

  it("removes the card once confirmed", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const calls = stubFetch(
      { status: 200, body: HISTORY },
      { status: 200, body: { run_id: "01JB", deleted: true } },
      { status: 200, body: { resumes: HISTORY.resumes.slice(1) } },
    );
    render(<Resume idToken="tok" entries={VAULT} />);
    const user = userEvent.setup();

    const card = (await screen.findByRole("heading", { level: 3, name: "Anthropic" })).closest("li")!;
    await user.click(within(card).getByRole("button", { name: /delete the résumé for Anthropic/i }));

    await waitFor(() =>
      expect(screen.queryByRole("heading", { level: 3, name: "Anthropic" })).not.toBeInTheDocument(),
    );
    const del = calls.find((c) => c.method === "DELETE");
    expect(del?.url).toContain("/resumes/01JB");
    // The surviving résumé is untouched.
    expect(screen.getByRole("heading", { level: 3, name: "Senior Cloud Architect" })).toBeInTheDocument();
  });

  it("gives each card's delete button a distinct accessible name, even for same-day duplicates", async () => {
    // Without an aria-label every button is announced identically as "Delete". The first fix added
    // the *date*, and a fixture with differing dates said it worked — but the real vault holds two
    // résumés both titled "Databricks", built four minutes apart on the SAME afternoon, and the
    // live page still collapsed them to one name. This fixture is that case, not a kinder one.
    stubFetch({
      status: 200,
      body: {
        resumes: [
          { run_id: "01JD1", created_at: "2026-07-28T15:45:47Z", target_title: "Databricks", entry_count: 13, status: "completed" },
          { run_id: "01JD2", created_at: "2026-07-28T15:49:59Z", target_title: "Databricks", entry_count: 13, status: "completed" },
        ],
      },
    });
    render(<Resume idToken="tok" entries={VAULT} />);
    await screen.findAllByText("Databricks");

    const names = screen
      .getAllByRole("button", { name: /^Delete the résumé for/ })
      .map((b) => b.getAttribute("aria-label"));
    expect(names).toHaveLength(2);
    expect(new Set(names).size).toBe(2);
    expect(names[0]).toContain("28 Jul 2026 at 15:45");
    expect(names[1]).toContain("28 Jul 2026 at 15:49");
  });

  it("closes the open résumé when it is the one deleted", async () => {
    // Its presigned URLs now point at objects that no longer exist, so leaving it on screen offers
    // a Download that 404s — the slice-2 Timeline finding in a new place.
    vi.spyOn(window, "confirm").mockReturnValue(true);
    stubFetch(
      { status: 200, body: HISTORY },
      { status: 200, body: COMPLETED_RUN },
      { status: 200, body: { run_id: "01JB", deleted: true } },
      { status: 200, body: { resumes: HISTORY.resumes.slice(1) } },
    );
    render(<Resume idToken="tok" entries={VAULT} />);
    const user = userEvent.setup();

    const card = (await screen.findByRole("heading", { level: 3, name: "Anthropic" })).closest("li")!;
    await user.click(within(card).getByRole("button", { name: "View" }));
    await screen.findByRole("heading", { name: /your tailored résumé/i });

    await user.click(screen.getByRole("button", { name: /delete the résumé for Anthropic/i }));

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: /your tailored résumé/i })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Generate" })).toBeInTheDocument();
  });

  it("keeps the card and reports the problem when the delete fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    stubFetch({ status: 200, body: HISTORY }, { status: 500, body: { message: "nope" } });
    render(<Resume idToken="tok" entries={VAULT} />);
    const user = userEvent.setup();

    const card = (await screen.findByRole("heading", { level: 3, name: "Anthropic" })).closest("li")!;
    await user.click(within(card).getByRole("button", { name: /delete the résumé for Anthropic/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't delete/i);
    // Optimistically removing it here would tell the user something false.
    expect(screen.getByRole("heading", { level: 3, name: "Anthropic" })).toBeInTheDocument();
  });
});
