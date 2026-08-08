import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Settings } from "./Settings";
import { stubFetch } from "../test/http";
import type { Entry } from "../lib/api";

/**
 * Details (v1.1 slice 2).
 *
 * Two categories worth pinning. The **absences** — three designed controls with nothing behind them
 * — because "we decided not to build this" is invisible in the code and reads as an oversight to
 * the next person; a test states it. And the **JSON export**, which is the one genuinely new feature
 * in this slice.
 */

const PROFILE = {
  email: "dev@example.com",
  name: "Ada Lovelace",
  location: "London",
  phone: null,
  aspirational_goal: null,
  settings: { checkin_cadence: "weekly", checkin_paused: false },
  next_checkin_at: null,
  last_checkin_sent_at: null,
};

const ENTRIES = [
  { entry_id: "a", entry_type: "CERT", title: "AZ-900", content: "x" },
  { entry_id: "b", entry_type: "JOB", title: "A role", content: "y" },
] as Entry[];

function renderDetails(entries: Entry[] | null = ENTRIES) {
  stubFetch({ status: 200, body: PROFILE });
  render(<Settings idToken="tok" entries={entries} />);
  return userEvent.setup();
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("deliberate absences (B-015 precedent)", () => {
  it("does not ship a streak-break reminder toggle with nothing behind it (B-033)", async () => {
    renderDetails();
    await screen.findByRole("heading", { name: /reminders/i });

    // The design shows this switch defaulting to on. There is no settings field and no second
    // scheduled send, so a switch that persisted but sent nothing would be fabricated functionality.
    expect(screen.queryByText(/warn me before the streak breaks/i)).not.toBeInTheDocument();
  });

  it("does not offer account deletion (B-034)", async () => {
    renderDetails();
    await screen.findByRole("heading", { name: /your vault, your data/i });

    expect(screen.queryByRole("button", { name: /delete account/i })).not.toBeInTheDocument();
  });

  it("describes the cadence by the interval the scheduler actually uses", async () => {
    renderDetails();
    await screen.findByRole("heading", { name: /check-in cadence/i });

    // The handoff says "a prompt every Friday". `CADENCE_DAYS` paces sends N days from the last
    // one via a daily run — it is not day-anchored, so that copy would promise what the backend
    // cannot deliver.
    expect(screen.getByText(/every 7 days/i)).toBeInTheDocument();
    expect(screen.queryByText(/friday/i)).not.toBeInTheDocument();
  });

  it("offers every cadence the model supports, not the design's three", async () => {
    renderDetails();
    await screen.findByRole("heading", { name: /check-in cadence/i });

    // Anchored: an unanchored /Weekly/ also matches "Biweekly" and finds two elements.
    for (const label of ["Weekly", "Biweekly", "Monthly", "Quarterly"]) {
      expect(screen.getByRole("radio", { name: new RegExp(`^${label}`) })).toBeInTheDocument();
    }
  });
});

describe("JSON export", () => {
  it("downloads every record as a JSON blob without calling the server", async () => {
    // Typed via the generic rather than a bare `vi.fn(() => …)`: without a declared parameter the
    // mock's call tuple is `[]`, and reading `calls[0][0]` fails `tsc -b` — which the test runner
    // does not run. (An unused `_blob` argument would type it too, but trips no-unused-vars.)
    const createObjectURL = vi.fn<(blob: Blob) => string>(() => "blob:fake");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);

    const user = renderDetails();
    const button = await screen.findByRole("button", { name: /export/i });
    await user.click(button);

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    // The blob is released rather than pinned for the life of the document.
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake");

    const blob = createObjectURL.mock.calls[0][0];
    expect(blob.type).toBe("application/json");
    const payload = JSON.parse(await blob.text());
    expect(payload.count).toBe(2);
    expect(payload.entries.map((e: Entry) => e.title)).toEqual(["AZ-900", "A role"]);
    expect(payload.exported_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it("is disabled when there is nothing to export", async () => {
    renderDetails([]);
    expect(await screen.findByRole("button", { name: /export/i })).toBeDisabled();
  });
});

describe("accessibility (audit §A10)", () => {
  it("has its h1 while still loading, not only once the profile lands", () => {
    // Found by measuring the live page mid-fetch. The early return skipped the header, so the view
    // had no heading at all for the duration — invisible to any check that runs after load.
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    render(<Settings idToken="tok" entries={ENTRIES} />);

    expect(screen.getByRole("heading", { level: 1, name: "Details" })).toBeInTheDocument();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("keeps its h1 when the profile fails to load", async () => {
    stubFetch({ networkError: true });
    render(<Settings idToken="tok" entries={ENTRIES} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't load/i);
    expect(screen.getByRole("heading", { level: 1, name: "Details" })).toBeInTheDocument();
  });

  it("has exactly one h1", async () => {
    renderDetails();
    await screen.findByRole("heading", { name: /your vault, your data/i });

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});

describe("saving", () => {
  it("sends the cadence chosen by button, and reports the result", async () => {
    stubFetch({ status: 200, body: PROFILE }, { status: 200, body: { profile: PROFILE } });
    render(<Settings idToken="tok" entries={ENTRIES} />);
    const user = userEvent.setup();

    await screen.findByRole("heading", { name: /check-in cadence/i });
    await user.click(screen.getByRole("radio", { name: /monthly/i }));
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    // §A11 — the outcome is announced, not just coloured.
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/saved/i));
  });

  it("the reminders switch maps onto checkin_paused, inverted", async () => {
    const calls = stubFetch(
      { status: 200, body: PROFILE },
      { status: 200, body: { profile: PROFILE } },
    );
    render(<Settings idToken="tok" entries={ENTRIES} />);
    const user = userEvent.setup();

    const toggle = await screen.findByRole("switch", { name: /email me at check-in/i });
    expect(toggle).toHaveAttribute("aria-checked", "true");

    await user.click(toggle);
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(calls.length).toBe(2));
    expect(calls[1].body).toMatchObject({ settings: { checkin_paused: true } });
  });

  it("keeps email read-only — it comes from the JWT, not a form field", async () => {
    renderDetails();
    const email = await screen.findByDisplayValue("dev@example.com");
    expect(email).toBeDisabled();
  });
});

/** Regressions from the v1.1 slice 2 code review. */
describe("slice 2 review regressions", () => {
  it("tells the shell to re-read the profile after a save", async () => {
    // Without this the cadence chosen here never reached App's state: the header streak pill,
    // Home's aggregates and the Log's "Weekly check-in" title all kept computing against the old
    // cadence until a full page reload. The entry-writing views got this; settings was missed.
    stubFetch({ status: 200, body: PROFILE }, { status: 200, body: { profile: PROFILE } });
    const onSaved = vi.fn();
    render(<Settings idToken="tok" entries={ENTRIES} onSaved={onSaved} />);
    const user = userEvent.setup();

    await screen.findByRole("heading", { name: /check-in cadence/i });
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  });

  it("does not call back when the save failed", async () => {
    stubFetch({ status: 200, body: PROFILE }, { status: 500, body: { message: "nope" } });
    const onSaved = vi.fn();
    render(<Settings idToken="tok" entries={ENTRIES} onSaved={onSaved} />);
    const user = userEvent.setup();

    await screen.findByRole("heading", { name: /check-in cadence/i });
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("the cadence radiogroup is one tab stop and responds to arrow keys", async () => {
    // Buttons give none of the radiogroup keyboard contract for free; the <select> this replaced
    // had all of it natively, so without a roving tabindex this was a net a11y regression.
    renderDetails();
    await screen.findByRole("heading", { name: /check-in cadence/i });

    const radios = screen.getAllByRole("radio");
    expect(radios.filter((r) => r.getAttribute("tabindex") === "0")).toHaveLength(1);
    expect(screen.getByRole("radio", { name: /^Weekly/ })).toHaveAttribute("tabindex", "0");

    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: /^Weekly/ }));
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: /^Biweekly/ })).toHaveAttribute("aria-checked", "true");

    await user.keyboard("{End}");
    expect(screen.getByRole("radio", { name: /^Quarterly/ })).toHaveAttribute("aria-checked", "true");

    await user.keyboard("{Home}");
    expect(screen.getByRole("radio", { name: /^Weekly/ })).toHaveAttribute("aria-checked", "true");
  });

  it("the switch takes its name from the visible label, not a duplicated aria-label", async () => {
    // A duplicated aria-label leaves the announced and rendered names as two strings maintained
    // independently, and shrinks the hit target to the 42px track.
    renderDetails();
    const toggle = await screen.findByRole("switch", { name: /email me at check-in/i });

    expect(toggle).not.toHaveAttribute("aria-label");
    expect(toggle).toHaveAttribute("aria-labelledby", "email-toggle-label");
    // The sub-line is the only place the destination address and cadence are stated.
    expect(toggle).toHaveAttribute("aria-describedby", "email-toggle-sub");
  });

  it("pausing keeps the cadence control focusable rather than dropping it from the tab order", async () => {
    renderDetails();
    const toggle = await screen.findByRole("switch", { name: /email me at check-in/i });
    const user = userEvent.setup();

    await user.click(toggle);

    // `aria-disabled`, not `disabled`: still reachable and readable, and inert.
    const weekly = screen.getByRole("radio", { name: /^Weekly/ });
    expect(weekly).toHaveAttribute("aria-disabled", "true");
    expect(weekly).not.toBeDisabled();
    expect(screen.getByText(/cadence is fixed while check-ins are paused/i)).toBeInTheDocument();
  });

  it("appends the download anchor and revokes the blob on a later task", async () => {
    // Revoking synchronously after click() on a detached anchor works in Chrome but is not
    // specified — Firefox and WebKit queue the download and can find the URL already dead.
    const createObjectURL = vi.fn<(blob: Blob) => string>(() => "blob:fake");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    // Both facts are captured at the instant of the click — asserting them afterwards would be
    // meaningless, since awaiting `user.click` already drains the timer that defers the revoke.
    let attachedAtClick = false;
    let revokedAtClick = false;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      attachedAtClick = document.body.contains(this);
      revokedAtClick = revokeObjectURL.mock.calls.length > 0;
    });

    const user = renderDetails();
    await user.click(await screen.findByRole("button", { name: /export/i }));

    expect(attachedAtClick).toBe(true);
    expect(revokedAtClick).toBe(false);
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake"));
    // Cleaned up rather than left in the document.
    expect(document.querySelector("a[download]")).toBeNull();
  });
});
