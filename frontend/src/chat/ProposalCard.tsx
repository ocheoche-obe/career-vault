import { useState } from "react";
import {
  confirmEntry,
  type ConfirmResult,
  type DuplicateMatch,
  type EntryCandidate,
  type FieldError,
} from "../lib/api";
import { editableFields, mergeEdits } from "../lib/entryFields";
import { EntryFields } from "../components/EntryFields";

/**
 * The Phase B confirm gate (FR-2.3): the user reviews — and may edit — the candidate before
 * anything is persisted. Fields render generically (ADR-022), and the server's 422 field errors
 * render inline. A 409 "possible duplicate" (ADR-033) is surfaced as a soft warning the user can
 * override with "Save anyway", which re-confirms with the acknowledge flag.
 */

type CardState =
  | { phase: "review" }
  | { phase: "saving" }
  | { phase: "duplicate"; matches: DuplicateMatch[] }
  | { phase: "saved"; duplicate: boolean }
  | { phase: "invalid"; errors: FieldError[] }
  | { phase: "failed"; message: string };

export function ProposalCard({
  idToken,
  candidate,
  onSaved,
}: {
  idToken: string;
  candidate: EntryCandidate;
  onSaved: (entryType: string, title: string) => void;
}) {
  const [fields, setFields] = useState<Record<string, string>>(() => editableFields(candidate));
  const [state, setState] = useState<CardState>({ phase: "review" });

  const confirm = async (acknowledge = false) => {
    setState({ phase: "saving" });
    // entry_id rides along unchanged — a re-confirm (double click, retry) lands on the same SK
    // and comes back 200 instead of duplicating (Section 3.1.4).
    const edited = mergeEdits(candidate, fields) as EntryCandidate;

    let result: ConfirmResult;
    try {
      result = await confirmEntry(idToken, edited, { acknowledge });
    } catch {
      setState({ phase: "failed", message: "Network error — your entry was not saved. Try again." });
      return;
    }

    if (result.status === "invalid") return setState({ phase: "invalid", errors: result.errors });
    if (result.status === "possible_duplicate") {
      return setState({ phase: "duplicate", matches: result.duplicates });
    }
    if (result.status === "failed") return setState({ phase: "failed", message: result.message });

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

  if (state.phase === "duplicate") {
    return (
      <div className="proposal-card duplicate-warning">
        <span className="badge">{candidate.entry_type}</span>
        <p className="dup-lead">This looks similar to something already in your vault:</p>
        <ul className="dup-list">
          {state.matches.map((m) => (
            <li key={m.entry_id}>
              <span className="badge small">{m.entry_type}</span> {m.title}
              <span className="dup-score"> · {Math.round(m.similarity * 100)}% similar</span>
            </li>
          ))}
        </ul>
        <div className="card-actions">
          <button onClick={() => void confirm(true)}>Save anyway</button>
          <button className="secondary" onClick={() => setState({ phase: "review" })}>
            Keep editing
          </button>
        </div>
      </div>
    );
  }

  const busy = state.phase === "saving";
  return (
    <div className="proposal-card">
      <span className="badge">{candidate.entry_type}</span>
      <EntryFields
        fields={fields}
        setFields={setFields}
        errors={state.phase === "invalid" ? state.errors : []}
        disabled={busy}
      />
      {state.phase === "invalid" && (
        <p className="field-error">
          Fix the highlighted fields and confirm again.
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
