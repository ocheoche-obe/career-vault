import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Timeline } from "./Timeline";
import { stubFetch } from "../test/http";
import type { Entry } from "../lib/api";

/**
 * The Timeline (v1.1 slice 2).
 *
 * The interesting assertions are about *derivation*, not layout: which filters exist, what order
 * records come in, and which designed elements were deliberately left out rather than faked. Each
 * one encodes a decision that would otherwise survive only as a comment.
 */

function entry(over: Partial<Entry> = {}): Entry {
  return {
    entry_id: `id-${Math.random()}`,
    entry_type: "JOB",
    title: "A role",
    content: "Did things.",
    event_date: "2025-06-01",
    created_at: "2025-06-02T10:00:00Z",
    ...over,
  } as Entry;
}

const CORPUS: Entry[] = [
  entry({ entry_id: "j1", entry_type: "JOB", title: "Senior Associate", employer: "KPMG US", event_date: "2025-05-19", created_at: "2025-05-20T10:00:00Z" }),
  entry({ entry_id: "c1", entry_type: "CERT", title: "AZ-900", issuer: "Microsoft", event_date: "2026-03-14", created_at: "2026-07-21T10:00:00Z" }),
  entry({ entry_id: "e1", entry_type: "EDUCATION", title: "BSc Computing", institution: "A University", event_date: "2013-06-01", created_at: "2024-01-01T10:00:00Z" }),
];

function renderTimeline(entries: Entry[] | null = CORPUS) {
  const onChanged = vi.fn();
  render(<Timeline idToken="tok" entries={entries} onChanged={onChanged} />);
  return { onChanged, user: userEvent.setup() };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("filters (deviation from the handoff)", () => {
  it("offers only the types actually present, not the design's fixed five", () => {
    // The handoff names All/Roles/Projects/Milestones/Certifications. The model has eight types and
    // the live corpus has EDUCATION rows, which a fixed list would silently hide.
    stubFetch({ status: 200, body: {} });
    renderTimeline();

    const group = screen.getByRole("group", { name: /filter by type/i });
    expect(within(group).getByRole("button", { name: "All" })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "Education" })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "Roles" })).toBeInTheDocument();
    // Nothing offered for a type with no records.
    expect(within(group).queryByRole("button", { name: "Projects" })).not.toBeInTheDocument();
  });

  it("narrows the list to the chosen type", async () => {
    stubFetch({ status: 200, body: {} });
    const { user } = renderTimeline();

    await user.click(screen.getByRole("button", { name: "Certifications" }));

    expect(screen.getByRole("button", { name: /AZ-900/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Senior Associate/ })).not.toBeInTheDocument();
  });
});

describe("ordering", () => {
  it("orders by when things happened, not when they were logged", () => {
    // AZ-900 has the newest `created_at` but a 2026 `event_date`; BSc is 2013. A timeline of a
    // career is ordered by event, which is the opposite field from the one the streak uses.
    stubFetch({ status: 200, body: {} });
    renderTimeline();

    const titles = screen
      .getAllByRole("button")
      .map((b) => b.textContent ?? "")
      .filter((t) => /AZ-900|Senior Associate|BSc Computing/.test(t));

    expect(titles[0]).toContain("AZ-900");
    expect(titles[titles.length - 1]).toContain("BSc Computing");
  });

  it("groups the list under year dividers", () => {
    stubFetch({ status: 200, body: {} });
    renderTimeline();

    for (const year of ["2026", "2025", "2013"]) {
      expect(screen.getByText(year)).toBeInTheDocument();
    }
  });
});

describe("the detail panel", () => {
  it("numbers records by deposit order, not by row position", () => {
    // BSc was logged first (2024), so it is Record 001 even though it sits last in the list.
    stubFetch({ status: 200, body: {} });
    renderTimeline();

    // AZ-900 is selected by default (first row) and was logged third.
    expect(screen.getByText("Record 003")).toBeInTheDocument();
  });

  it("shows the logged date, and does not claim a source it has no field for", () => {
    stubFetch({ status: 200, body: {} });
    renderTimeline();

    expect(screen.getByText("Logged")).toBeInTheDocument();
    expect(screen.getByText("21 Jul 2026")).toBeInTheDocument();
    // The handoff writes "20 Jul 2026, from chat". `Entry` records no source, so the claim is
    // omitted rather than invented (B-015 precedent).
    expect(screen.queryByText(/from chat/i)).not.toBeInTheDocument();
  });

  it("omits 'Used in — N résumés', which has no data source (B-028)", () => {
    stubFetch({ status: 200, body: {} });
    renderTimeline();

    expect(screen.queryByText(/used in/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/résumé/i)).not.toBeInTheDocument();
  });

  it("formats event_date rather than printing the raw ISO string", () => {
    stubFetch({ status: 200, body: {} });
    renderTimeline();

    expect(screen.getByText(/Microsoft · 14 Mar 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/2026-03-14/)).not.toBeInTheDocument();
  });

  it("switching records abandons a half-finished edit rather than carrying it across", async () => {
    stubFetch({ status: 200, body: {} });
    const { user } = renderTimeline();

    await user.click(screen.getByRole("button", { name: /^edit$/i }));
    expect(screen.getByDisplayValue("AZ-900")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Senior Associate/ }));

    // Back to a read-only panel showing the newly selected record.
    expect(screen.queryByDisplayValue("AZ-900")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
  });
});

describe("states", () => {
  it("says the vault is empty rather than rendering an empty frame", () => {
    stubFetch({ status: 200, body: {} });
    renderTimeline([]);

    expect(screen.getByText(/your vault is empty/i)).toBeInTheDocument();
  });

  it("distinguishes loading from empty", () => {
    stubFetch({ status: 200, body: {} });
    renderTimeline(null);

    expect(screen.getByText(/loading your vault/i)).toBeInTheDocument();
    expect(screen.queryByText(/your vault is empty/i)).not.toBeInTheDocument();
  });

  it("reports a failed load as an alert instead of looking empty", () => {
    stubFetch({ status: 200, body: {} });
    render(<Timeline idToken="tok" entries={null} loadError />);

    expect(screen.getByRole("alert")).toHaveTextContent(/could not load/i);
  });
});

/** Regressions from the v1.1 slice 2 code review. */
describe("slice 2 review regressions", () => {
  it("a deleted record leaves the list immediately, not after the refetch", async () => {
    // The row survived in `rows` until `GET /entries` returned (~3.6s cold), so the selection fell
    // back onto the record that had just been deleted and the panel offered Edit/Delete on it.
    vi.spyOn(window, "confirm").mockReturnValue(true);
    stubFetch({ status: 200, body: { deleted: "c1" } });
    const { onChanged, user } = renderTimeline();

    expect(screen.getByRole("button", { name: /AZ-900/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^delete$/i }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    // Gone from the list even though the parent has not re-supplied `entries`.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /AZ-900/ })).not.toBeInTheDocument(),
    );
  });

  it("an edited title shows immediately rather than reverting until the refetch", async () => {
    stubFetch({ status: 200, body: { entry: { ...CORPUS[1], title: "AZ-900 (renewed)" } } });
    const { user } = renderTimeline();

    await user.click(screen.getByRole("button", { name: /^edit$/i }));
    const title = screen.getByDisplayValue("AZ-900");
    await user.clear(title);
    await user.type(title, "AZ-900 (renewed)");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByRole("button", { name: /AZ-900 \(renewed\)/ })).toBeInTheDocument();
  });

  it("falls back to All when the active filter's last record is deleted", async () => {
    // Otherwise: a populated vault, an empty list, and no chip marked active — with nothing on
    // screen to say a filter was still applied.
    vi.spyOn(window, "confirm").mockReturnValue(true);
    stubFetch({ status: 200, body: { deleted: "c1" } });
    const { user } = renderTimeline();

    await user.click(screen.getByRole("button", { name: "Certifications" }));
    expect(screen.getByRole("button", { name: "Certifications" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await user.click(screen.getByRole("button", { name: /^delete$/i }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true"),
    );
    expect(screen.queryByText(/nothing of that type yet/i)).not.toBeInTheDocument();
  });
});
