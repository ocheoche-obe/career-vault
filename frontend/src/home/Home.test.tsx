import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Home } from "./Home";
import type { Entry } from "../lib/api";

/**
 * Home is a pure props component — every number it shows is derived by `lib/aggregates`, which has
 * its own suite. What is tested here is the part aggregates cannot cover: the four states Home can
 * be in (loading, error, empty, populated) and the places where a bad value from the API would
 * otherwise take the whole app down.
 *
 * Most of these correspond to findings from the slice-1 code review, so each one is a regression
 * test for a bug that actually shipped into the branch.
 */

let seq = 0;
function entry(overrides: Partial<Entry> = {}): Entry {
  seq += 1;
  return {
    entry_id: `e${seq}`,
    entry_type: "PROJECT",
    title: `Entry ${seq}`,
    content: "",
    created_at: "2026-08-01T10:00:00Z",
    ...overrides,
  };
}

const props = {
  cadence: "weekly" as const,
  name: "Oche Obe",
  onNavigate: vi.fn(),
};

describe("Home states", () => {
  it("shows a loading state while entries are still null", () => {
    render(<Home {...props} entries={null} />);
    // Both data cards say it — assert on all of them rather than pretending there is one.
    expect(screen.getAllByText(/loading…/i).length).toBeGreaterThan(0);
  });

  it("surfaces an error instead of loading forever when the fetch failed", () => {
    // The bug this locks: `entries` stays null on a failed GET, so Home rendered "Loading…"
    // indefinitely — indistinguishable from a slow network, and reported to nobody.
    render(<Home {...props} entries={null} loadError />);
    expect(screen.getByText(/could not load your entries/i)).toBeInTheDocument();
    expect(screen.queryByText(/loading…/i)).not.toBeInTheDocument();
  });

  it("shows an empty state, not an error, for a user with no entries yet", () => {
    render(<Home {...props} entries={[]} />);
    // The full sentence, so this matches the Latest-in-the-vault card specifically and not the
    // stat sub-line, which says the same three words.
    expect(screen.getByText(/nothing logged yet\. the composer above/i)).toBeInTheDocument();
    expect(screen.queryByText(/could not load/i)).not.toBeInTheDocument();
  });

  it("does not claim 'nothing logged yet' while still loading", () => {
    // A user with 40 entries briefly read "nothing logged yet" during the fetch, because the stat
    // sub-lines were derived from an empty array rather than gated on the loading state.
    render(<Home {...props} entries={null} />);
    expect(screen.queryByText(/nothing logged yet/i)).not.toBeInTheDocument();
  });

  it("renders the latest entries once loaded", () => {
    render(<Home {...props} entries={[entry({ title: "Shipped the resume agent" })]} />);
    expect(screen.getByText("Shipped the resume agent")).toBeInTheDocument();
  });
});

describe("Home resilience", () => {
  it("survives an unparseable created_at instead of blanking the app", () => {
    // `Intl.DateTimeFormat.format` throws a RangeError on an Invalid Date. There is no error
    // boundary above Home, so an unformattable date would white-screen the entire app.
    expect(() =>
      render(<Home {...props} entries={[entry({ created_at: "not-a-date" })]} />),
    ).not.toThrow();
    expect(screen.getByText(/entry \d+/i)).toBeInTheDocument();
  });

  it("caps the composer at the backend's per-message limit", () => {
    // Chat's textarea has maxLength, but a value set programmatically is not truncated by it — so
    // an over-long paste on Home would sail through and fail server-side with a generic error.
    render(<Home {...props} entries={[]} />);
    expect(screen.getByLabelText(/what did you accomplish/i)).toHaveAttribute("maxlength", "4000");
  });
});

describe("Home navigation", () => {
  it("hands the composer text to Log rather than dropping it", async () => {
    const onNavigate = vi.fn();
    const onDraft = vi.fn();
    const user = userEvent.setup();
    render(<Home {...props} entries={[]} onNavigate={onNavigate} onDraft={onDraft} />);

    await user.type(screen.getByLabelText(/what did you accomplish/i), "I shipped the redesign");
    await user.click(screen.getByRole("button", { name: /start logging/i }));

    expect(onDraft).toHaveBeenCalledWith("I shipped the redesign");
    expect(onNavigate).toHaveBeenCalledWith("log");
  });

  it("navigates to Log without a draft when the composer is empty", async () => {
    const onNavigate = vi.fn();
    const onDraft = vi.fn();
    const user = userEvent.setup();
    render(<Home {...props} entries={[]} onNavigate={onNavigate} onDraft={onDraft} />);

    await user.click(screen.getByRole("button", { name: /start logging/i }));

    expect(onDraft).not.toHaveBeenCalled();
    expect(onNavigate).toHaveBeenCalledWith("log");
  });

  it("seeds the composer from a prompt chip", async () => {
    const user = userEvent.setup();
    render(<Home {...props} entries={[]} />);

    await user.click(screen.getByRole("button", { name: "Shipped something" }));

    expect(screen.getByLabelText(/what did you accomplish/i)).toHaveValue("I shipped ");
  });
});
