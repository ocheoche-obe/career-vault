import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ProposalCard } from "./ProposalCard";
import { stubFetch } from "../test/http";
import type { EntryCandidate } from "../lib/api";

/**
 * State-machine tests for the Phase B confirm gate (FR-2.3, ADR-033).
 *
 * These exist because the card's bugs are *state* bugs, not render bugs: each failure mode ends with
 * the UI sitting in a phase that does not match what the server actually did, and typecheck + build
 * — the only frontend gate CI had before slice 9 — cannot see any of it. The slice-3 stuck-"Saving"
 * bug is the motivating example.
 *
 * Only the network is faked, so `lib/api`'s status-code mapping is under test too.
 */

const CANDIDATE: EntryCandidate = {
  entry_type: "CERT",
  title: "AWS Solutions Architect Associate",
  content: "Passed the SAA-C03 exam.",
  entry_id: "01JQ0000000000000000000000",
  issuer: "Amazon Web Services",
};

const DUPLICATE = {
  entry_id: "01JQ1111111111111111111111",
  entry_type: "CERT",
  title: "AWS SAA",
  similarity: 0.93,
};

function renderCard() {
  const onSaved = vi.fn();
  render(<ProposalCard idToken="tok" candidate={CANDIDATE} onSaved={onSaved} />);
  return { onSaved, user: userEvent.setup() };
}

const confirmButton = () => screen.getByRole("button", { name: /confirm & save/i });

describe("the happy path", () => {
  it("saves, reports the entry upward, and stops offering to save again", async () => {
    stubFetch({ status: 201, body: { entry: {} } });
    const { onSaved, user } = renderCard();

    await user.click(confirmButton());

    expect(await screen.findByText(/^Saved/)).toBeInTheDocument();
    expect(onSaved).toHaveBeenCalledWith("CERT", CANDIDATE.title);
    // The confirm button is gone in the saved phase, so a second save cannot be triggered.
    expect(screen.queryByRole("button", { name: /confirm & save/i })).not.toBeInTheDocument();
  });

  it("renders an idempotent re-confirm as 'Already saved', not as a duplicate warning", async () => {
    // Section 3.1.4: the same entry_id coming back 200 rather than 201 is success. The user must
    // not be asked to resolve anything.
    stubFetch({ status: 200, body: { entry: {} } });
    const { user } = renderCard();

    await user.click(confirmButton());

    expect(await screen.findByText(/already saved/i)).toBeInTheDocument();
    expect(screen.queryByText(/looks similar/i)).not.toBeInTheDocument();
  });
});

describe("the 409 possible-duplicate path", () => {
  it("shows the matches and saves nothing until the user overrides", async () => {
    stubFetch({
      status: 409,
      body: { entry_id: CANDIDATE.entry_id, possible_duplicates: [DUPLICATE] },
    });
    const { onSaved, user } = renderCard();

    await user.click(confirmButton());

    expect(await screen.findByText(/looks similar/i)).toBeInTheDocument();
    expect(screen.getByText(/93% similar/)).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("'Save anyway' retries with acknowledge_duplicate, which is what clears the block", async () => {
    const calls = stubFetch(
      { status: 409, body: { entry_id: CANDIDATE.entry_id, possible_duplicates: [DUPLICATE] } },
      { status: 201, body: { entry: {} } },
    );
    const { onSaved, user } = renderCard();

    await user.click(confirmButton());
    await user.click(await screen.findByRole("button", { name: /save anyway/i }));

    expect(await screen.findByText(/^Saved/)).toBeInTheDocument();
    expect(onSaved).toHaveBeenCalledTimes(1);

    // The override rides on the flag, not on the retry itself — a bare retry would loop back into
    // the same 409. Asserted on the wire body, which is where the backend contract lives.
    expect(calls).toHaveLength(2);
    expect(calls[0].body).not.toHaveProperty("acknowledge_duplicate");
    expect(calls[1].body).toMatchObject({
      acknowledge_duplicate: true,
      entry_id: CANDIDATE.entry_id, // same SK — an acknowledged save stays idempotent
    });
  });

  it("'Keep editing' returns to the form without saving", async () => {
    const calls = stubFetch({
      status: 409,
      body: { entry_id: CANDIDATE.entry_id, possible_duplicates: [DUPLICATE] },
    });
    const { onSaved, user } = renderCard();

    await user.click(confirmButton());
    await user.click(await screen.findByRole("button", { name: /keep editing/i }));

    expect(confirmButton()).toBeEnabled();
    expect(onSaved).not.toHaveBeenCalled();
    expect(calls).toHaveLength(1);
  });
});

describe("failure modes leave the card usable", () => {
  // The regression class this file exists for: any path that enters phase "saving" and never leaves
  // strands the user on a disabled "Saving…" button with no error and no way forward.
  it("a 422 re-enables the button and surfaces the field error", async () => {
    stubFetch({ status: 422, body: { errors: [{ field: "event_date", error: "must be ISO-8601" }] } });
    const { user } = renderCard();

    await user.click(confirmButton());

    await waitFor(() => expect(confirmButton()).toBeEnabled());
    expect(screen.getByText(/fix the highlighted fields/i)).toBeInTheDocument();
  });

  it("a 500 re-enables the button and shows the server message", async () => {
    stubFetch({ status: 500, body: { message: "Bedrock unavailable" } });
    const { onSaved, user } = renderCard();

    await user.click(confirmButton());

    expect(await screen.findByText("Bedrock unavailable")).toBeInTheDocument();
    await waitFor(() => expect(confirmButton()).toBeEnabled());
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("a dead network does not strand the card on 'Saving…'", async () => {
    stubFetch({ networkError: true });
    const { onSaved, user } = renderCard();

    await user.click(confirmButton());

    expect(await screen.findByText(/network error/i)).toBeInTheDocument();
    await waitFor(() => expect(confirmButton()).toBeEnabled());
    expect(screen.queryByRole("button", { name: /saving/i })).not.toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });
});

describe("edits made in the card", () => {
  it("are sent to the server and reported upward, not merely displayed", async () => {
    const calls = stubFetch({ status: 201, body: { entry: {} } });
    const { onSaved, user } = renderCard();

    const titleInput = screen.getByDisplayValue(CANDIDATE.title);
    await user.clear(titleInput);
    await user.type(titleInput, "AWS SAA (renewed)");
    await user.click(confirmButton());

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toMatchObject({
      entry_id: CANDIDATE.entry_id, // unchanged — idempotency depends on it
      title: "AWS SAA (renewed)",
    });
    expect(onSaved).toHaveBeenCalledWith("CERT", "AWS SAA (renewed)");
  });
});
