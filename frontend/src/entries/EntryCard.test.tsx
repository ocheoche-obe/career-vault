import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EntryCard } from "./EntryCard";
import { stubFetch } from "../test/http";
import type { Entry } from "../lib/api";

/**
 * Edit and delete on a dashboard card (FR-3.3, ADR-027).
 *
 * The card keeps its React instance across a save because the list gives it a stable key, so every
 * exit from the "saving" phase has to be written explicitly — the slice-3 bug was a success path
 * that updated the data and left the button reading "Saving…" forever. That is the regression these
 * tests are for, and it is invisible to typecheck, build, and lint alike.
 */

const ENTRY: Entry = {
  entry_id: "01JQ0000000000000000000000",
  entry_type: "CERT",
  title: "AWS Solutions Architect Associate",
  content: "Passed the SAA-C03 exam.",
  issuer: "Amazon Web Services",
  event_date: "2026-03-14",
} as Entry;

function renderCard() {
  const onEdited = vi.fn();
  const onDeleted = vi.fn();
  render(<EntryCard idToken="tok" entry={ENTRY} onEdited={onEdited} onDeleted={onDeleted} />);
  return { onEdited, onDeleted, user: userEvent.setup() };
}

const editButton = () => screen.getByRole("button", { name: /^edit$/i });
const deleteButton = () => screen.getByRole("button", { name: /^delete$/i });
const saveButton = () => screen.getByRole("button", { name: /^save$/i });

afterEach(() => vi.restoreAllMocks());

describe("editing", () => {
  it("returns to view mode after a successful save — not stuck on 'Saving…'", async () => {
    // The slice-3 regression, stated as a test.
    stubFetch({ status: 200, body: { entry: { ...ENTRY, title: "AWS SAA (renewed)" } } });
    const { onEdited, user } = renderCard();

    await user.click(editButton());
    const titleInput = screen.getByDisplayValue(ENTRY.title);
    await user.clear(titleInput);
    await user.type(titleInput, "AWS SAA (renewed)");
    await user.click(saveButton());

    await waitFor(() => expect(onEdited).toHaveBeenCalled());
    // Back in view mode: the Edit button is showing again and no "Saving…" remains anywhere.
    expect(await screen.findByRole("button", { name: /^edit$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /saving/i })).not.toBeInTheDocument();
    expect(onEdited).toHaveBeenCalledWith(expect.objectContaining({ title: "AWS SAA (renewed)" }));
  });

  it("sends the edited fields on the wire", async () => {
    const calls = stubFetch({ status: 200, body: { entry: ENTRY } });
    const { user } = renderCard();

    await user.click(editButton());
    const titleInput = screen.getByDisplayValue(ENTRY.title);
    await user.clear(titleInput);
    await user.type(titleInput, "Renamed");
    await user.click(saveButton());

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].method).toBe("PUT");
    expect(calls[0].url).toContain(ENTRY.entry_id);
    expect(calls[0].body).toMatchObject({ title: "Renamed" });
  });

  it("a 422 keeps the form open and editable rather than dropping the user's work", async () => {
    stubFetch({ status: 422, body: { errors: [{ field: "event_date", error: "must be ISO-8601" }] } });
    const { onEdited, user } = renderCard();

    await user.click(editButton());
    await user.click(saveButton());

    await waitFor(() => expect(saveButton()).toBeEnabled());
    expect(screen.getByDisplayValue(ENTRY.title)).toBeInTheDocument();
    expect(onEdited).not.toHaveBeenCalled();
  });

  it("a 404 reports the entry as deleted elsewhere instead of hanging", async () => {
    stubFetch({ status: 404, body: {} });
    const { onDeleted, user } = renderCard();

    await user.click(editButton());
    await user.click(saveButton());

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(ENTRY.entry_id));
  });

  it("a dead network surfaces an error and leaves the card usable", async () => {
    stubFetch({ networkError: true });
    const { onEdited, user } = renderCard();

    await user.click(editButton());
    await user.click(saveButton());

    expect(await screen.findByText(/network error/i)).toBeInTheDocument();
    expect(onEdited).not.toHaveBeenCalled();
  });

  it("Cancel discards the edit without calling the server", async () => {
    const calls = stubFetch({ status: 200, body: { entry: ENTRY } });
    const { onEdited, user } = renderCard();

    await user.click(editButton());
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(editButton()).toBeInTheDocument();
    expect(calls).toHaveLength(0);
    expect(onEdited).not.toHaveBeenCalled();
  });
});

describe("deleting", () => {
  it("does nothing at all when the confirm is dismissed (ADR-027)", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const calls = stubFetch({ status: 200, body: { deleted: ENTRY.entry_id } });
    const { onDeleted, user } = renderCard();

    await user.click(deleteButton());

    expect(calls).toHaveLength(0);
    expect(onDeleted).not.toHaveBeenCalled();
    expect(deleteButton()).toBeEnabled();
  });

  it("deletes and reports upward once confirmed", async () => {
    // 200 with a {deleted} body is what career_crud actually returns (handler.py:244) — not 204.
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const calls = stubFetch({ status: 200, body: { deleted: ENTRY.entry_id } });
    const { onDeleted, user } = renderCard();

    await user.click(deleteButton());

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(ENTRY.entry_id));
    expect(calls[0].method).toBe("DELETE");
    expect(calls[0].url).toContain(ENTRY.entry_id);
  });

  it("a failed delete leaves the card in place with an error", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    stubFetch({ status: 500, body: {} });
    const { onDeleted, user } = renderCard();

    await user.click(deleteButton());

    expect(await screen.findByText(/couldn't delete/i)).toBeInTheDocument();
    expect(onDeleted).not.toHaveBeenCalled();
    await waitFor(() => expect(deleteButton()).toBeEnabled());
  });
});
