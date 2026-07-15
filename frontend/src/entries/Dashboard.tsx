import { useCallback, useEffect, useState } from "react";
import { listEntries, type Entry } from "../lib/api";
import { EntryCard } from "./EntryCard";
import "./entries.css";

/**
 * The entries dashboard (FR-3.2): everything the user has logged, grouped by type and ordered
 * newest-first within each group. Sorting/grouping is client-side per Section 2.5 — the backend
 * returns the full set (AP-10) and React arranges it. Edit/delete (FR-3.3) live on each card.
 */

// Canonical display order (Section 2.7); only non-empty groups are shown.
const TYPE_ORDER = ["JOB", "PROJECT", "MILESTONE", "CERT", "AWARD", "EDUCATION", "VOLUNTEER", "HOBBY"];

const TYPE_LABELS: Record<string, string> = {
  JOB: "Jobs",
  PROJECT: "Projects",
  MILESTONE: "Milestones",
  CERT: "Certifications",
  AWARD: "Awards",
  EDUCATION: "Education",
  VOLUNTEER: "Volunteering",
  HOBBY: "Hobbies",
};

function groupByType(entries: Entry[]): [string, Entry[]][] {
  const byType = new Map<string, Entry[]>();
  for (const entry of entries) {
    const list = byType.get(entry.entry_type) ?? [];
    list.push(entry);
    byType.set(entry.entry_type, list);
  }
  // Newest-first within each group; event_date is always present on a persisted entry.
  for (const list of byType.values()) {
    list.sort((a, b) => (b.event_date ?? "").localeCompare(a.event_date ?? ""));
  }
  const known = TYPE_ORDER.filter((t) => byType.has(t)).map((t) => [t, byType.get(t)!] as [string, Entry[]]);
  const unknown = [...byType.keys()].filter((t) => !TYPE_ORDER.includes(t)).map((t) => [t, byType.get(t)!] as [string, Entry[]]);
  return [...known, ...unknown];
}

export function Dashboard({ idToken }: { idToken: string }) {
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    setRefreshing(true);
    try {
      setEntries(await listEntries(idToken));
    } catch {
      setError("Couldn't load your entries. Try again.");
    } finally {
      setRefreshing(false);
    }
  }, [idToken]);

  // Initial fetch on mount. Kept out of `load` so no setState fires synchronously inside the
  // effect body (react-hooks/set-state-in-effect); the `active` flag drops a late response that
  // resolves after unmount.
  useEffect(() => {
    let active = true;
    listEntries(idToken)
      .then((data) => { if (active) setEntries(data); })
      .catch(() => { if (active) setError("Couldn't load your entries. Try again."); });
    return () => {
      active = false;
    };
  }, [idToken]);

  const onDeleted = (entryId: string) =>
    setEntries((prev) => (prev ? prev.filter((e) => e.entry_id !== entryId) : prev));

  const onEdited = (updated: Entry) =>
    setEntries((prev) => (prev ? prev.map((e) => (e.entry_id === updated.entry_id ? updated : e)) : prev));

  if (error) {
    return (
      <section className="dashboard">
        <p className="dashboard-error">{error} <button onClick={() => void load()}>Retry</button></p>
      </section>
    );
  }

  if (entries === null) {
    return <section className="dashboard"><p className="dashboard-hint">Loading your vault…</p></section>;
  }

  if (entries.length === 0) {
    return (
      <section className="dashboard">
        <p className="dashboard-hint">
          Your vault is empty. Head to Chat and tell me about a project, cert, award, or role —
          your entries will show up here.
        </p>
      </section>
    );
  }

  return (
    <section className="dashboard">
      <div className="dashboard-head">
        <span className="dashboard-count">{entries.length} {entries.length === 1 ? "entry" : "entries"}</span>
        <button className="secondary" onClick={() => void load()} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      {groupByType(entries).map(([type, group]) => (
        <div key={type} className="entry-group">
          <h2>{TYPE_LABELS[type] ?? type} <span className="group-count">{group.length}</span></h2>
          {group.map((entry) => (
            <EntryCard key={entry.entry_id} idToken={idToken} entry={entry} onEdited={onEdited} onDeleted={onDeleted} />
          ))}
        </div>
      ))}
    </section>
  );
}
