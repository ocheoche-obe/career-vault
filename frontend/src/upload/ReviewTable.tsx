import { useMemo, useState } from "react";
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
 * The select-all review table for a parsed resume (ADR-035). A resume yields 5–20 candidates, so
 * the user reviews them as a checklist — unchecking junk, expanding a row to edit — and saves the
 * kept rows in one action. Each save goes through the existing `POST /entries` (confirmEntry), so
 * embedding, §3.1.4 idempotency, and the ADR-033 duplicate check are all reused unchanged. A 409
 * "possible duplicate" is surfaced per-row with a "Save anyway" override, exactly as the chat
 * ProposalCard does.
 */

type RowStatus =
  | { phase: "pending" }
  | { phase: "saving" }
  | { phase: "saved"; duplicate: boolean }
  | { phase: "duplicate"; matches: DuplicateMatch[] }
  | { phase: "invalid"; errors: FieldError[] }
  | { phase: "failed"; message: string };

type Row = {
  candidate: EntryCandidate;
  fields: Record<string, string>;
  checked: boolean;
  expanded: boolean;
  status: RowStatus;
};

/**
 * A row the bulk "Save N" action will process: fresh, or a prior attempt that can be retried
 * as-is. A `duplicate` row is deliberately excluded — it needs the explicit per-row "Save anyway"
 * (acknowledging the ADR-033 warning) — and a `saved` row is done. Keeping this predicate the
 * single source of truth for the count, the select-all, and the save loop stops the button from
 * promising to save rows it won't touch.
 */
const isBulkSavable = (row: Row) =>
  row.status.phase === "pending" || row.status.phase === "failed" || row.status.phase === "invalid";

function initialRows(candidates: EntryCandidate[]): Row[] {
  return candidates.map((candidate) => ({
    candidate,
    fields: editableFields(candidate),
    checked: true,
    expanded: false,
    status: { phase: "pending" },
  }));
}

export function ReviewTable({
  idToken,
  candidates,
  dropped,
  onDone,
  onSaved,
}: {
  idToken: string;
  candidates: EntryCandidate[];
  dropped: number;
  onDone: () => void;
  /** Fired after a batch lands so the shell re-reads entries and every derived number stays true. */
  onSaved?: () => void;
}) {
  const [rows, setRows] = useState<Row[]>(() => initialRows(candidates));
  const [busy, setBusy] = useState(false);

  const patch = (entryId: string, update: (row: Row) => Row) =>
    setRows((prev) => prev.map((r) => (r.candidate.entry_id === entryId ? update(r) : r)));

  const savedCount = useMemo(() => rows.filter((r) => r.status.phase === "saved").length, [rows]);
  const selectedCount = useMemo(
    () => rows.filter((r) => r.checked && isBulkSavable(r)).length,
    [rows],
  );
  const bulkSavableCount = useMemo(() => rows.filter(isBulkSavable).length, [rows]);
  const allSelected = bulkSavableCount > 0 && selectedCount === bulkSavableCount;

  const toggleAll = (checked: boolean) =>
    setRows((prev) => prev.map((r) => (isBulkSavable(r) ? { ...r, checked } : r)));

  /** Save one row through confirmEntry; `acknowledge` overrides a possible-duplicate warning. */
  const saveRow = async (row: Row, acknowledge: boolean): Promise<void> => {
    patch(row.candidate.entry_id, (r) => ({ ...r, status: { phase: "saving" } }));
    const edited = mergeEdits(row.candidate, row.fields) as EntryCandidate;

    let result: ConfirmResult;
    try {
      result = await confirmEntry(idToken, edited, { acknowledge });
    } catch {
      patch(row.candidate.entry_id, (r) => ({
        ...r,
        status: { phase: "failed", message: "Network error — not saved." },
      }));
      return;
    }

    patch(row.candidate.entry_id, (r) => {
      if (result.status === "invalid") return { ...r, expanded: true, status: { phase: "invalid", errors: result.errors } };
      if (result.status === "possible_duplicate")
        return { ...r, expanded: true, status: { phase: "duplicate", matches: result.duplicates } };
      if (result.status === "failed") return { ...r, status: { phase: "failed", message: result.message } };
      // created | duplicate → saved; drop it from the selection so a re-save can't double-run it.
      return { ...r, checked: false, expanded: false, status: { phase: "saved", duplicate: result.status === "duplicate" } };
    });

    // Fired here rather than only in `saveSelected` so the per-row "Save anyway" duplicate override
    // also refreshes the shell. It persists an entry like any other save, but it is reachable
    // without ever pressing the bulk button — and "Done" (the other path out) is not even rendered
    // while rows remain savable, so the user could navigate away with the record written and every
    // derived number in the app still showing the pre-import corpus.
    if (result.status === "created" || result.status === "duplicate") onSaved?.();
  };

  const saveSelected = async () => {
    setBusy(true);
    // Snapshot the rows to save; the user can't edit while busy, so each row's fields are stable
    // for the duration. Sequential (not parallel) keeps the downstream career_crud calls gentle.
    const targets = rows.filter((r) => r.checked && isBulkSavable(r));
    for (const target of targets) {
      await saveRow(target, false);
    }
    setBusy(false);
  };

  return (
    <section className="card review" aria-labelledby="review-heading">
      <div className="card-head">
        <h2 id="review-heading">
          {rows.length} {rows.length === 1 ? "record" : "records"} found
        </h2>
        <p className="micro review-count">
          {selectedCount} selected
          {savedCount > 0 && ` · ${savedCount} saved`}
        </p>
      </div>

      <p className="muted">
        Uncheck anything you don&apos;t want, edit a row to fix it, then save.
        {dropped > 0 && ` ${dropped} couldn't be parsed cleanly and were skipped.`}
      </p>

      {/* §A11 — a batch save is a long silent operation otherwise. */}
      <p className="sr-only" role="status">
        {busy ? "Saving records" : savedCount > 0 ? `${savedCount} records saved` : ""}
      </p>

      <ul className="review-rows">
        {rows.map((row) => (
          <ReviewRowView
            key={row.candidate.entry_id}
            row={row}
            busy={busy}
            onToggleChecked={() =>
              patch(row.candidate.entry_id, (r) => ({ ...r, checked: !r.checked }))
            }
            onToggleExpanded={() =>
              patch(row.candidate.entry_id, (r) => ({ ...r, expanded: !r.expanded }))
            }
            onSetFields={(updater) =>
              patch(row.candidate.entry_id, (r) => ({ ...r, fields: updater(r.fields) }))
            }
            onSaveAnyway={() => void saveRow({ ...row }, true)}
          />
        ))}
      </ul>

      <div className="review-actions">
        {bulkSavableCount > 0 && (
          <button
            className="btn-primary"
            onClick={() => void saveSelected()}
            disabled={busy || selectedCount === 0}
          >
            {busy ? "Saving…" : `Save ${selectedCount} to vault`}
          </button>
        )}
        <label className="review-selectall">
          <input
            type="checkbox"
            checked={allSelected}
            disabled={busy || bulkSavableCount === 0}
            onChange={(e) => toggleAll(e.target.checked)}
          />
          Select all
        </label>
        {bulkSavableCount === 0 && (
          <button className="btn-quiet" onClick={onDone}>
            Done
          </button>
        )}
      </div>
    </section>
  );
}

function ReviewRowView({
  row,
  busy,
  onToggleChecked,
  onToggleExpanded,
  onSetFields,
  onSaveAnyway,
}: {
  row: Row;
  busy: boolean;
  onToggleChecked: () => void;
  onToggleExpanded: () => void;
  onSetFields: (updater: (prev: Record<string, string>) => Record<string, string>) => void;
  onSaveAnyway: () => void;
}) {
  const { candidate, fields, status } = row;
  const title = fields.title ?? candidate.title;
  const saved = status.phase === "saved";
  // The checkbox only drives the bulk "Save N"; a duplicate/saved row isn't part of that (a
  // duplicate is actioned by its own "Save anyway"), so its checkbox is inert.
  const checkboxDisabled = busy || !isBulkSavable(row);

  return (
    <li className={`review-row${saved ? " saved" : ""}${row.checked ? " selected" : ""}`}>
      <div className="review-row-head">
        {/* The label wraps the checkbox *and* the text, so the whole row toggles selection while
            the control keeps native checkbox semantics — a <button> containing a checkbox, which
            is how the handoff draws it, is invalid nesting and announces as neither. */}
        <label className="row-select">
          <input
            type="checkbox"
            checked={row.checked}
            disabled={checkboxDisabled}
            onChange={onToggleChecked}
          />
          <span className="checkbox" aria-hidden="true" />
          <span className="row-text">
            <span className="row-title">{title || "(untitled)"}</span>
            <span className="row-meta">
              <span className="badge small">{candidate.entry_type}</span>
              {typeof candidate.event_date === "string" && candidate.event_date}
            </span>
          </span>
        </label>
        <StatusPill status={status} />
        <button
          className="row-edit micro"
          onClick={onToggleExpanded}
          disabled={busy || saved}
          aria-expanded={row.expanded}
        >
          {row.expanded ? "Close" : "Edit"}
        </button>
      </div>

      {status.phase === "duplicate" && (
        <div className="review-dup">
          <p className="dup-lead">Similar to something already in your vault:</p>
          <ul className="dup-list">
            {status.matches.map((m) => (
              <li key={m.entry_id}>
                <span className="badge small">{m.entry_type}</span> {m.title}
                <span className="dup-score"> · {Math.round(m.similarity * 100)}% similar</span>
              </li>
            ))}
          </ul>
          <button className="btn-quiet" onClick={onSaveAnyway} disabled={busy}>
            Save anyway
          </button>
        </div>
      )}

      {status.phase === "failed" && <p className="field-error">{status.message}</p>}

      {row.expanded && !saved && (
        <div className="review-row-edit">
          <EntryFields
            fields={fields}
            setFields={onSetFields}
            errors={status.phase === "invalid" ? status.errors : []}
            disabled={busy || status.phase === "saving"}
          />
        </div>
      )}
    </li>
  );
}

function StatusPill({ status }: { status: RowStatus }) {
  switch (status.phase) {
    case "saving":
      return <span className="pill">Saving…</span>;
    case "saved":
      return <span className="pill ok">{status.duplicate ? "Already saved" : "Saved"}</span>;
    case "duplicate":
      return <span className="pill warn">Possible duplicate</span>;
    case "invalid":
      return <span className="pill warn">Needs a fix</span>;
    case "failed":
      return <span className="pill err">Failed</span>;
    default:
      return null;
  }
}
