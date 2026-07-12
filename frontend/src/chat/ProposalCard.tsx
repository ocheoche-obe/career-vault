import { useState } from "react";
import { confirmEntry, type ConfirmResult, type EntryCandidate, type FieldError } from "../lib/api";

/**
 * The Phase B confirm gate (FR-2.3): the user reviews — and may edit — the candidate before
 * anything is persisted. Fields render generically from the candidate's own keys, so all eight
 * entry types work without per-type forms; the server's discriminated union remains the single
 * source of truth (ADR-022), and its 422 field errors render inline here.
 */

// Keys the user shouldn't edit: identity/type are fixed at propose time.
const READONLY_KEYS = new Set(["entry_id", "entry_type"]);

type CardState =
  | { phase: "review" }
  | { phase: "saving" }
  | { phase: "saved"; duplicate: boolean }
  | { phase: "invalid"; errors: FieldError[] }
  | { phase: "failed"; message: string };

function toInputValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  return value == null ? "" : String(value);
}

function fromInputValue(original: unknown, edited: string): unknown {
  if (Array.isArray(original)) {
    return edited.split(",").map((s) => s.trim()).filter(Boolean);
  }
  if (typeof original === "number") {
    const n = Number(edited);
    return Number.isNaN(n) ? edited : n;
  }
  return edited;
}

export function ProposalCard({
  idToken,
  candidate,
  onSaved,
}: {
  idToken: string;
  candidate: EntryCandidate;
  onSaved: (entryType: string, title: string) => void;
}) {
  const [fields, setFields] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const [key, value] of Object.entries(candidate)) {
      if (!READONLY_KEYS.has(key)) initial[key] = toInputValue(value);
    }
    return initial;
  });
  const [state, setState] = useState<CardState>({ phase: "review" });

  const errorsFor = (key: string): string[] =>
    state.phase === "invalid" ? state.errors.filter((e) => e.field === key).map((e) => e.error) : [];

  const confirm = async () => {
    setState({ phase: "saving" });
    const edited: EntryCandidate = { ...candidate };
    for (const [key, value] of Object.entries(fields)) {
      edited[key] = fromInputValue(candidate[key], value);
    }

    let result: ConfirmResult;
    try {
      // entry_id rides along unchanged — a re-confirm (double click, retry) lands on the same
      // SK and comes back 200 instead of duplicating (Section 3.1.4).
      result = await confirmEntry(idToken, edited);
    } catch {
      setState({ phase: "failed", message: "Network error — your entry was not saved. Try again." });
      return;
    }

    if (result.status === "invalid") {
      setState({ phase: "invalid", errors: result.errors });
      return;
    }
    if (result.status === "failed") {
      setState({ phase: "failed", message: result.message });
      return;
    }
    setState({ phase: "saved", duplicate: result.status === "duplicate" });
    onSaved(candidate.entry_type, fields.title ?? candidate.title);
  };

  if (state.phase === "saved") {
    return (
      <div className="proposal-card saved">
        <span className="badge">{candidate.entry_type}</span>
        <p>
          {state.duplicate ? "Already saved" : "Saved"}: <strong>{fields.title ?? candidate.title}</strong>
        </p>
      </div>
    );
  }

  const busy = state.phase === "saving";
  return (
    <div className="proposal-card">
      <span className="badge">{candidate.entry_type}</span>
      <div className="proposal-fields">
        {Object.keys(fields).map((key) => (
          <label key={key}>
            <span className="field-name">{key.replaceAll("_", " ")}</span>
            {key === "content" ? (
              <textarea
                value={fields[key]}
                rows={3}
                disabled={busy}
                onChange={(e) => setFields((f) => ({ ...f, [key]: e.target.value }))}
              />
            ) : (
              <input
                value={fields[key]}
                disabled={busy}
                onChange={(e) => setFields((f) => ({ ...f, [key]: e.target.value }))}
              />
            )}
            {errorsFor(key).map((msg) => (
              <span key={msg} className="field-error">{msg}</span>
            ))}
          </label>
        ))}
      </div>
      {state.phase === "invalid" && (
        <p className="field-error">
          Fix the highlighted fields and confirm again.
          {/* Errors on fields we don't render inline (e.g. the type discriminator) still surface. */}
          {state.errors
            .filter((e) => !(e.field in fields))
            .map((e) => ` ${e.field}: ${e.error}.`)
            .join("")}
        </p>
      )}
      {state.phase === "failed" && <p className="field-error">{state.message}</p>}
      <button onClick={() => void confirm()} disabled={busy}>
        {busy ? "Saving…" : "Confirm & save"}
      </button>
    </div>
  );
}
