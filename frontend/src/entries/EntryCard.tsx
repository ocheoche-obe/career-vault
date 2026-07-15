import { useState } from "react";
import { deleteEntry, updateEntry, type Entry, type FieldError } from "../lib/api";
import { editableFields, mergeEdits } from "../lib/entryFields";
import { EntryFields } from "../components/EntryFields";

/**
 * One entry on the dashboard (FR-3.3). Read-only by default; "Edit" opens the generic field grid
 * (same component as the propose flow) and saves via PUT — re-embedding only when text changed is
 * the server's concern (ADR-024 note). "Delete" is a hard delete gated by a UI confirm (ADR-027).
 */

type Mode =
  | { phase: "view" }
  | { phase: "editing"; errors: FieldError[] }
  | { phase: "saving" }
  | { phase: "deleting" }
  | { phase: "error"; message: string };

// Fields worth surfacing in the read-only summary, in a sensible order, if present.
const SUMMARY_ORDER = ["employer", "issuer", "institution", "organization", "degree"];

function summaryLine(entry: Entry): string {
  const parts = SUMMARY_ORDER.map((k) => entry[k]).filter((v): v is string => typeof v === "string" && v.length > 0);
  return parts.join(" · ");
}

export function EntryCard({
  idToken,
  entry,
  onEdited,
  onDeleted,
}: {
  idToken: string;
  entry: Entry;
  onEdited: (updated: Entry) => void;
  onDeleted: (entryId: string) => void;
}) {
  const [mode, setMode] = useState<Mode>({ phase: "view" });
  const [fields, setFields] = useState<Record<string, string>>({});

  const startEdit = () => {
    setFields(editableFields(entry));
    setMode({ phase: "editing", errors: [] });
  };

  const save = async () => {
    setMode({ phase: "saving" });
    const payload = mergeEdits(entry, fields);
    try {
      const result = await updateEntry(idToken, entry.entry_id, payload);
      if (result.status === "updated") {
        // Return to view first — the card keeps its instance (stable key), so without this it
        // would stay stuck on "Saving…" even though the edit succeeded.
        setMode({ phase: "view" });
        return onEdited(result.entry as Entry);
      }
      if (result.status === "invalid") return setMode({ phase: "editing", errors: result.errors });
      if (result.status === "notfound") return onDeleted(entry.entry_id); // already gone elsewhere
      setMode({ phase: "error", message: result.message });
    } catch {
      setMode({ phase: "error", message: "Network error — changes not saved." });
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete "${entry.title}"? This can't be undone.`)) return;
    setMode({ phase: "deleting" });
    try {
      if (await deleteEntry(idToken, entry.entry_id)) return onDeleted(entry.entry_id);
      setMode({ phase: "error", message: "Couldn't delete — try again." });
    } catch {
      setMode({ phase: "error", message: "Network error — not deleted." });
    }
  };

  if (mode.phase === "editing" || mode.phase === "saving") {
    const busy = mode.phase === "saving";
    return (
      <div className="entry-card editing">
        <EntryFields
          fields={fields}
          setFields={setFields}
          errors={mode.phase === "editing" ? mode.errors : []}
          disabled={busy}
        />
        <div className="card-actions">
          <button onClick={() => void save()} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          <button className="secondary" onClick={() => setMode({ phase: "view" })} disabled={busy}>Cancel</button>
        </div>
      </div>
    );
  }

  const summary = summaryLine(entry);
  const busy = mode.phase === "deleting";
  return (
    <div className="entry-card">
      <div className="entry-head">
        <strong className="entry-title">{entry.title}</strong>
        {entry.event_date && <span className="entry-date">{entry.event_date}</span>}
      </div>
      {summary && <p className="entry-summary">{summary}</p>}
      <p className="entry-content">{entry.content}</p>
      {mode.phase === "error" && <p className="field-error">{mode.message}</p>}
      <div className="card-actions">
        <button className="secondary" onClick={startEdit} disabled={busy}>Edit</button>
        <button className="danger" onClick={() => void remove()} disabled={busy}>
          {busy ? "Deleting…" : "Delete"}
        </button>
      </div>
    </div>
  );
}
