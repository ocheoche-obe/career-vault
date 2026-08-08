import { useMemo, useState } from "react";
import type { Entry } from "../lib/api";
import { TYPE_LABEL, formatEventDate, orgOf } from "../lib/aggregates";
import { EntryDetail } from "./EntryDetail";
import "./entries.css";

/**
 * The Timeline (FR-3.2 / FR-3.3) — the vault itself: every record, newest first, with a sticky
 * detail panel for the selected one.
 *
 * Entries come from the shell rather than a fetch of its own (they did before the redesign). One
 * fetch feeds Home's aggregates, the Log sidebar and this view, so a save made anywhere is reflected
 * everywhere without three components racing to re-read the same list.
 *
 * Two deviations from the handoff, both recorded:
 *
 *   - **Filters are derived, not fixed.** The design names five (All, Roles, Projects, Milestones,
 *     Certifications); the data model has eight types, and the live corpus contains EDUCATION rows
 *     that a fixed list would silently hide. Only types actually present are offered — the same call
 *     ADR-045 made for Home's category weights, for the same reason.
 *   - **Sorted by `event_date`, not `created_at`.** A timeline of a career is ordered by when things
 *     *happened*; the streak and the Log sidebar use `created_at` because those measure the habit of
 *     logging. The two fields answer different questions and this view wants the first.
 */

const UNDATED = "Undated";

/**
 * Local edits and deletes not yet reflected in the shell's list, tagged with the `entries` array
 * they were layered onto so a refetch can retire them without an effect.
 */
type Overlay = {
  source: Entry[] | null | undefined;
  edited: Map<string, Entry>;
  deleted: Set<string>;
};

const emptyOverlay = (source: Entry[] | null | undefined): Overlay => ({
  source,
  edited: new Map(),
  deleted: new Set(),
});

/** `event_date` is `YYYY-MM-DD`, so the year is a slice — no Date parsing, no timezone to get wrong. */
function yearOf(entry: Entry): string {
  const date = typeof entry.event_date === "string" ? entry.event_date : "";
  return /^\d{4}/.test(date) ? date.slice(0, 4) : UNDATED;
}

/** Day + month only; the year is already carried by the divider above the row. */
function rowDate(entry: Entry): string {
  const value = typeof entry.event_date === "string" ? entry.event_date : "";
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? formatEventDate(value) : "";
}

export function Timeline({
  idToken,
  entries,
  loadError = false,
  onChanged,
}: {
  idToken: string;
  entries: Entry[] | null;
  loadError?: boolean;
  onChanged?: () => void;
}) {
  const [filter, setFilter] = useState("ALL");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  /**
   * Edits and deletes are applied locally as well as refetched.
   *
   * The shell owns the entry list, so the only signal back is `onChanged()` — a `GET /entries` that
   * the slice's own measurements put at ~3.6s cold. Waiting for it meant a rename stayed invisible
   * for that whole window, and a delete was worse: the row survived in the list, so the selection
   * fell back onto the record that had just been deleted and the panel offered Edit and Delete on
   * something that no longer existed. If the refetch fails, the shell keeps the old array and this
   * overlay is the only thing that stays correct.
   */
  const [overlay, setOverlay] = useState<Overlay>(() => emptyOverlay(entries));

  /**
   * Fresh server data supersedes the overlay wholesale — keeping it would re-apply an edit on top
   * of a list that already contains it, and mask a write that actually failed server-side.
   *
   * Expired *during render* by comparing the `entries` identity it was built against, rather than
   * reset from an effect. An effect would fire a second render pass on every refetch, and would
   * leave one paint showing the stale overlay on top of already-fresh data.
   */
  const active = overlay.source === entries ? overlay : emptyOverlay(entries);

  const rows = useMemo(
    () =>
      (entries ?? [])
        .filter((e) => !active.deleted.has(e.entry_id))
        .map((e) => active.edited.get(e.entry_id) ?? e),
    [entries, active],
  );

  /**
   * "Record N" counts deposit order — the Nth thing logged — so it reads with the vault metaphor
   * rather than being a row index that changes as filters are applied. Computed over the whole
   * corpus, not the filtered view, for exactly that reason.
   *
   * Caveat worth knowing: deleting an entry renumbers everything logged after it. Acceptable for a
   * display label; it would not be acceptable as anything anyone cites or bookmarks.
   */
  const recordNumbers = useMemo(() => {
    const byDeposit = [...rows]
      .filter((e) => e.created_at)
      .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
    const map = new Map<string, number>();
    byDeposit.forEach((entry, i) => map.set(entry.entry_id, i + 1));
    return map;
  }, [rows]);

  const filters = useMemo(() => {
    const present = new Set(rows.map((e) => String(e.entry_type || "").toUpperCase()));
    return [
      { id: "ALL", label: "All" },
      ...[...present]
        .filter(Boolean)
        .map((type) => ({ id: type, label: TYPE_LABEL[type] ?? type }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    ];
  }, [rows]);

  /**
   * Fall back to "All" when the selected filter's type no longer exists.
   *
   * Deleting the last record of a type removes its chip but left `filter` pointing at it: the view
   * then showed a populated vault, an empty list, and no chip marked active — with nothing on
   * screen to explain that a filter was still applied.
   *
   * Derived rather than corrected from an effect: there is no second state to keep in sync, so no
   * render can ever observe the invalid value, and `filter` stays a record of what the user
   * actually chose (re-adding a CERT restores their Certifications filter rather than silently
   * having reset it).
   */
  const activeFilter = filters.some((f) => f.id === filter) ? filter : "ALL";

  const sorted = useMemo(() => {
    const visible =
      activeFilter === "ALL"
        ? rows
        : rows.filter((e) => String(e.entry_type || "").toUpperCase() === activeFilter);
    // Undated entries sort last: an empty string would otherwise sort before every real date.
    return [...visible].sort((a, b) => {
      const av = typeof a.event_date === "string" ? a.event_date : "";
      const bv = typeof b.event_date === "string" ? b.event_date : "";
      if (!av && !bv) return String(a.title).localeCompare(String(b.title));
      if (!av) return 1;
      if (!bv) return -1;
      return bv.localeCompare(av);
    });
  }, [rows, activeFilter]);

  const years = useMemo(() => {
    const all = rows
      .map(yearOf)
      .filter((y) => y !== UNDATED)
      .sort();
    return all.length ? { first: all[0], last: all[all.length - 1] } : null;
  }, [rows]);

  const selected = sorted.find((e) => e.entry_id === selectedId) ?? sorted[0] ?? null;

  const loading = entries === null && !loadError;

  const onDeleted = (entryId: string) => {
    setOverlay({ ...active, deleted: new Set(active.deleted).add(entryId) });
    if (selectedId === entryId) setSelectedId(null);
    onChanged?.();
  };

  const onEdited = (updated: Entry) => {
    setOverlay({ ...active, edited: new Map(active.edited).set(updated.entry_id, updated) });
    onChanged?.();
  };

  return (
    <div className="view timeline">
      <div className="view-head">
        <div>
          <p className="eyebrow">
            {loading
              ? "Loading"
              : `${rows.length} ${rows.length === 1 ? "record" : "records"}${
                  years ? ` · ${years.first}${years.last !== years.first ? ` — ${years.last}` : ""}` : ""
                }`}
          </p>
          <h1>Timeline</h1>
        </div>

        {filters.length > 1 && (
          <div className="filters" role="group" aria-label="Filter by type">
            {filters.map((option) => (
              <button
                key={option.id}
                type="button"
                className={`micro filter${activeFilter === option.id ? " active" : ""}`}
                aria-pressed={activeFilter === option.id}
                onClick={() => setFilter(option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {loadError ? (
        <p className="muted" role="alert">
          Could not load your entries. Refresh to try again.
        </p>
      ) : loading ? (
        <p className="muted">Loading your vault…</p>
      ) : rows.length === 0 ? (
        <p className="muted">
          Your vault is empty. Head to Log and tell me about a project, cert, award or role — records
          show up here.
        </p>
      ) : (
        <div className="timeline-grid">
          <div className="record-list">
            {sorted.length === 0 ? (
              <p className="muted list-empty">Nothing of that type yet.</p>
            ) : (
              sorted.map((entry, i) => {
                const year = yearOf(entry);
                const showDivider = i === 0 || yearOf(sorted[i - 1]) !== year;
                const org = orgOf(entry);
                return (
                  <div key={entry.entry_id}>
                    {showDivider && <p className="year-divider micro">{year}</p>}
                    <button
                      type="button"
                      className={`record-row${
                        selected?.entry_id === entry.entry_id ? " selected" : ""
                      }`}
                      aria-current={selected?.entry_id === entry.entry_id ? "true" : undefined}
                      onClick={() => setSelectedId(entry.entry_id)}
                    >
                      <span className="record-meta">
                        <span className="badge small">{entry.entry_type}</span>
                        <span className="record-date">{rowDate(entry)}</span>
                      </span>
                      <span className="record-title">{entry.title}</span>
                      {org && <span className="record-org">{org}</span>}
                    </button>
                  </div>
                );
              })
            )}
          </div>

          {selected && (
            <div className="detail-column">
              <EntryDetail
                // Keyed by entry so selecting a different record resets the panel's edit state
                // rather than carrying one record's half-finished edit onto another.
                key={selected.entry_id}
                idToken={idToken}
                entry={selected}
                recordNumber={recordNumbers.get(selected.entry_id)}
                onEdited={onEdited}
                onDeleted={onDeleted}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
