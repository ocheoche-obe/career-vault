import { useState } from "react";
import { deleteEntry, updateEntry, type Entry, type FieldError } from "../lib/api";
import { editableFields, mergeEdits } from "../lib/entryFields";
import { EntryFields } from "../components/EntryFields";

/**
 * The Timeline's detail panel (FR-3.3) — one selected record, read-only until "Edit" opens the
 * generic field grid (the same component the propose flow uses). Saves via PUT; re-embedding only
 * when text changed is the server's concern (ADR-024 note). "Delete" is a hard delete gated by a UI
 * confirm (ADR-027).
 *
 * Was `EntryCard` before the v1.1 redesign, when the Timeline was a list of expandable cards. The
 * edit/delete state machine is unchanged and deliberately so: it encodes a real slice-3 regression
 * (a success path that updated the data and left the button reading "Saving…" forever), which its
 * tests still pin.
 *
 * One designed row is absent rather than faked: "Used in — 1 résumé" needs résumé history, and there
 * is no list endpoint (B-028). The "Logged" row shows the date only — the design's ", from chat"
 * provenance has no field behind it, since `Entry` records no source.
 */

type Mode =
  | { phase: "view" }
  | { phase: "editing"; errors: FieldError[] }
  | { phase: "saving" }
  | { phase: "deleting" }
  | { phase: "error"; message: string };

// Fields worth surfacing in the sub-line, in a sensible order, if present.
const SUMMARY_ORDER = ["employer", "issuer", "institution", "organization", "degree"];

const LOGGED_DATE = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

function summaryLine(entry: Entry): string {
  const parts = SUMMARY_ORDER.map((k) => entry[k]).filter(
    (v): v is string => typeof v === "string" && v.length > 0,
  );
  return parts.join(" · ");
}

/** `Intl.format` throws a RangeError on an Invalid Date, which would blank the whole view. */
function loggedOn(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : LOGGED_DATE.format(parsed);
}

/**
 * `event_date` is a plain `YYYY-MM-DD` calendar date, not an instant. Pinned to UTC on both parse
 * and format: `new Date("2026-03-14")` is midnight UTC, so formatting it locally renders 13 Mar for
 * anyone west of Greenwich — a certification would appear to have been earned the day before.
 */
const EVENT_DATE = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

function eventOn(value: unknown): string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return typeof value === "string" ? value : "";
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? value : EVENT_DATE.format(parsed);
}

export function EntryDetail({
  idToken,
  entry,
  recordNumber,
  onEdited,
  onDeleted,
}: {
  idToken: string;
  entry: Entry;
  recordNumber?: number;
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
        // Return to view first — the panel keeps its instance (stable key), so without this it
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

  const strip = (
    <div className="detail-strip">
      <span className="micro">
        {recordNumber ? `Record ${String(recordNumber).padStart(3, "0")}` : "Record"}
      </span>
      <span className="micro kind">{entry.entry_type}</span>
    </div>
  );

  if (mode.phase === "editing" || mode.phase === "saving") {
    const busy = mode.phase === "saving";
    return (
      <div className="detail-panel editing">
        {strip}
        <div className="detail-body">
          <EntryFields
            fields={fields}
            setFields={setFields}
            errors={mode.phase === "editing" ? mode.errors : []}
            disabled={busy}
          />
          <div className="detail-actions">
            <button className="btn-quiet" onClick={() => void save()} disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
            <button
              className="btn-quiet subtle"
              onClick={() => setMode({ phase: "view" })}
              disabled={busy}
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    );
  }

  const summary = summaryLine(entry);
  const logged = loggedOn(entry.created_at);
  const busy = mode.phase === "deleting";

  return (
    <div className="detail-panel">
      {strip}
      <div className="detail-body">
        <h2>{entry.title}</h2>
        {(summary || entry.event_date) && (
          <p className="detail-sub">
            {[summary, eventOn(entry.event_date)].filter(Boolean).join(" · ")}
          </p>
        )}
        <p className="detail-content">{entry.content}</p>

        {logged && (
          <dl className="fact-rows">
            <div>
              <dt className="micro">Logged</dt>
              <dd>{logged}</dd>
            </div>
          </dl>
        )}

        {mode.phase === "error" && <p className="field-error">{mode.message}</p>}

        <div className="detail-actions">
          <button className="btn-quiet" onClick={startEdit} disabled={busy}>
            Edit
          </button>
          <button className="btn-quiet danger" onClick={() => void remove()} disabled={busy}>
            {busy ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
