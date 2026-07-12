import { useEffect, useRef, useState } from "react";
import { postChat, type EntryCandidate } from "../lib/api";
import { ulid } from "../lib/ulid";
import { ProposalCard } from "./ProposalCard";
import "./chat.css";

/**
 * The ingestion conversation (FR-2, Section 3.1 Phase A): free-form message in; a clarifying
 * question or a reviewable entry proposal out. Nothing persists as an entry until the user
 * confirms on the ProposalCard.
 *
 * Retry story (ADR-032): each send mints a `client_message_id` ULID that is reused verbatim on
 * retry, so a retried turn never duplicates in CONVO history or replayed prompts. `session_id`
 * arrives with the first response and is echoed on every later turn.
 */

type Turn =
  | { id: string; role: "user"; text: string; failed?: boolean }
  | { id: string; role: "assistant"; text: string; isError?: boolean }
  | { id: string; role: "proposal"; candidate: EntryCandidate };

const MAX_MESSAGE_CHARS = 4000;

export function Chat({ idToken }: { idToken: string }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const sessionIdRef = useRef<string | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns]);

  const send = async (text: string, clientMessageId: string) => {
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
  };

  const submit = () => {
    const text = draft.trim();
    if (!text || sending) return;
    setDraft("");
    void send(text, ulid());
  };

  const onSaved = (entryType: string, title: string) => {
    setTurns((prev) => [
      ...prev,
      { id: ulid(), role: "assistant", text: `${entryType} “${title}” is in your vault. What else happened?` },
    ]);
  };

  return (
    <section className="chat">
      <div className="chat-scroll" ref={scrollRef}>
        {turns.length === 0 && (
          <p className="chat-hint">
            Tell me something that happened in your career — a project, a cert, an award, a new
            role — and I'll turn it into a vault entry for your review.
          </p>
        )}
        {turns.map((turn) => {
          if (turn.role === "proposal") {
            return (
              <div key={turn.id} className="bubble-row assistant">
                <ProposalCard idToken={idToken} candidate={turn.candidate} onSaved={onSaved} />
              </div>
            );
          }
          return (
            <div key={turn.id} className={`bubble-row ${turn.role}`}>
              <div className={`bubble ${turn.role === "assistant" && turn.isError ? "error" : ""}`}>
                {turn.text}
                {turn.role === "user" && turn.failed && (
                  <button
                    className="retry"
                    disabled={sending}
                    onClick={() => void send(turn.text, turn.id)}
                  >
                    Retry
                  </button>
                )}
              </div>
            </div>
          );
        })}
        {sending && <div className="bubble-row assistant"><div className="bubble typing">…</div></div>}
      </div>
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <textarea
          value={draft}
          maxLength={MAX_MESSAGE_CHARS}
          placeholder="What did you accomplish?"
          rows={2}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button type="submit" disabled={sending || !draft.trim()}>Send</button>
      </form>
    </section>
  );
}
