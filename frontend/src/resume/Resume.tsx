import { useCallback, useEffect, useState } from "react";
import {
  MAX_TARGET_CHARS,
  deleteResume,
  getResumeRun,
  listResumes,
  startResumeRun,
  type Entry,
  type ResumeDocument,
  type ResumeSummary,
  type RunStatus,
} from "../lib/api";
import { formatEventDate } from "../lib/aggregates";
import { resumeToPlainText } from "../lib/resumeText";
import "./resume.css";

/**
 * Résumés — generate a tailored résumé, and see the ones you have already built.
 *
 * Rebuilt for the v1.1 redesign (handoff §4) on the slice-1 token layer, and the last view to leave
 * the `.legacy-view` wrapper (B-036).
 *
 * Generation runs over the ADR-037 async job contract. A run is ~3 minutes — far past API Gateway's
 * 29s ceiling — so this view never awaits a résumé: it starts a job, gets a `run_id`, and polls
 * until terminal. Three consequences shape the code below:
 *
 * 1. **The run_id outlives the component.** A run costs ~$0.31 and keeps going server-side whether
 *    or not anyone is watching, so the id is parked in sessionStorage: a reload or an accidental
 *    tab switch re-attaches to the same run instead of orphaning it and paying twice.
 * 2. **The preview is an iframe `src`, not a fetch.** The data bucket's CORS allows PUT only (it
 *    was written for the slice-5 upload), and an iframe navigation isn't subject to CORS — so the
 *    presigned HTML renders against the bucket exactly as deployed.
 * 3. **Failures are rendered, not mapped.** The backend already turns each internal `detail` code
 *    into a user-facing sentence, so there is no second copy of that vocabulary here.
 *
 * History comes from `GET /resumes` (ADR-046). Two design elements are deliberately **not** built,
 * per ADR-045's omit-rather-than-fabricate rule: the **Sent** and **Draft** status badges, which
 * have no referent anywhere in the system (there is no send path — ADR-015 is in-app download only
 * — and no draft state). Only *Latest* and *New* are derivable, so only those ship.
 */

/** Poll cadence. The run takes ~176s; 3s keeps the elapsed counter honest without hammering. */
const POLL_INTERVAL_MS = 3_000;

/**
 * When to stop watching. The agent self-terminates at a 240s wall-clock budget and the Lambda is
 * capped at 300s, so anything past ~330s means the worker died without writing a terminal status —
 * the item would stay `pending` forever and polling it would never end.
 */
const POLL_CEILING_MS = 330_000;

const STORAGE_KEY = "careervault.resumeRun";

type ActiveRun = { runId: string; startedAt: number; target: string };

function loadActiveRun(): ActiveRun | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ActiveRun>;
    if (typeof parsed.runId !== "string" || typeof parsed.startedAt !== "number") return null;
    return { runId: parsed.runId, startedAt: parsed.startedAt, target: parsed.target ?? "" };
  } catch {
    return null; // Storage disabled or the value got mangled — just start fresh.
  }
}

function saveActiveRun(run: ActiveRun | null) {
  try {
    if (run) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(run));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // sessionStorage unavailable (private mode, blocked cookies): polling still works in-memory,
    // it just won't survive a reload. Not worth failing the run over.
  }
}

type Stage =
  | { phase: "idle" }
  /**
   * `draft` is the Phase-3 résumé, published mid-run by the agent (ADR-037 amendment). The stage
   * stays `generating` while it is showing: polling must continue, the elapsed counter must keep
   * running, and the run can still end as `failed`. Showing a draft is not a promise of success.
   */
  | { phase: "generating"; runId: string; startedAt: number; draft?: ResumeDocument }
  /**
   * `fromHistory` marks a résumé opened from a past row rather than just generated. It gates
   * **Regenerate**, which reruns `target` — the textarea's contents, which for a history-opened
   * résumé is either empty or a completely different job description. Neither the list projection
   * nor the poll payload returns the original `target_text`, so there is nothing to regenerate
   * *from*, and offering the button spends $0.11–$0.35 of Sonnet on the wrong target.
   */
  | { phase: "done"; run: Extract<RunStatus, { status: "completed" }>; fromHistory?: boolean }
  | { phase: "failed"; message: string }
  | { phase: "abandoned"; runId: string };

export function Resume({ idToken, entries }: { idToken: string; entries: Entry[] | null }) {
  // Read once, at mount: if a run was in flight when the tab reloaded, re-attach to it.
  const [restored] = useState(loadActiveRun);
  const [target, setTarget] = useState(restored?.target ?? "");
  const [stage, setStage] = useState<Stage>(() =>
    restored ? { phase: "generating", runId: restored.runId, startedAt: restored.startedAt } : { phase: "idle" },
  );
  const [elapsed, setElapsed] = useState(0);
  const [starting, setStarting] = useState(false);
  const [history, setHistory] = useState<ResumeSummary[] | null>(null);
  const [historyError, setHistoryError] = useState(false);
  const [freshRunId, setFreshRunId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const generating = stage.phase === "generating";

  // --- résumé history (ADR-046) -------------------------------------------------------------------
  /**
   * Refetch after something invalidates the list — a run completing, or a record being deleted.
   * A failure here leaves the previously-loaded rows in place: a stale list the user can still act
   * on beats blanking the panel over a network blip.
   */
  const refreshHistory = useCallback(async () => {
    try {
      // `ok` has to be read, not just `resumes`: a failed call resolves with an empty list, so
      // ignoring the flag renders "Nothing here yet" — telling the user they have no résumés when
      // the request simply failed.
      const { ok, resumes } = await listResumes(idToken);
      if (ok) setHistory(resumes);
      setHistoryError(!ok);
    } catch {
      setHistoryError(true);
    }
  }, [idToken]);

  // The mount load is spelled out rather than delegating to refreshHistory so it can be cancelled
  // if the view unmounts mid-flight, and so no setState runs synchronously in an effect body.
  useEffect(() => {
    let cancelled = false;
    listResumes(idToken)
      .then(({ ok, resumes }) => {
        if (cancelled) return;
        if (ok) setHistory(resumes);
        else setHistoryError(true);
      })
      .catch(() => !cancelled && setHistoryError(true));
    return () => {
      cancelled = true;
    };
  }, [idToken]);

  // --- poll the active run to a terminal status ---------------------------------------------------
  useEffect(() => {
    if (!generating) return;
    const { runId, startedAt } = stage;
    let cancelled = false;
    let timer: number | undefined;

    const settle = (next: Stage) => {
      if (cancelled) return;
      saveActiveRun(null);
      setStage(next);
    };

    const poll = async () => {
      if (cancelled) return;
      if (Date.now() - startedAt > POLL_CEILING_MS) {
        settle({ phase: "abandoned", runId });
        return;
      }
      try {
        const result = await getResumeRun(idToken, runId);
        if (cancelled) return;
        if (result.status === "completed") {
          settle({ phase: "done", run: result });
          // A completed run has just written its history record, so the list is now stale.
          setFreshRunId(runId);
          void refreshHistory();
          return;
        }
        if (result.status === "draftReady") {
          // Deliberately not `settle` — that clears the saved active run and stops the watch. This
          // is a progress update inside the same stage, so the poll loop below keeps going.
          if (!cancelled && result.document) {
            setStage((current) =>
              current.phase === "generating" ? { ...current, draft: result.document } : current,
            );
          }
        }
        if (result.status === "failed") return settle({ phase: "failed", message: result.message });
        if (result.status === "notfound") {
          // The run record is gone (expired trace, or a stale id from an older session).
          return settle({ phase: "failed", message: "That résumé run has expired. Generate a new one." });
        }
      } catch {
        // A transient network blip shouldn't kill a 3-minute watch — keep polling until the ceiling.
      }
      if (!cancelled) timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [generating, stage, idToken, refreshHistory]);

  // --- elapsed counter (progress feedback across a ~3-minute wait) --------------------------------
  useEffect(() => {
    if (stage.phase !== "generating") return;
    const { startedAt } = stage;
    const tick = () => setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    tick();
    const id = window.setInterval(tick, 1_000);
    return () => window.clearInterval(id);
  }, [stage]);

  const start = useCallback(
    async (targetText: string) => {
      // A double-click would start two independent runs at ~$0.31 each against a $5/month ceiling,
      // and the second run_id would overwrite the first in storage — orphaning a run nobody can
      // collect. The POST is quick but not instant, so the guard has to cover the in-flight window;
      // `starting` also disables the buttons, this just closes the race behind them.
      if (starting) return;

      const trimmed = targetText.trim();
      if (!trimmed) {
        setStage({ phase: "failed", message: "Paste a job description or name a target role first." });
        return;
      }
      if (trimmed.length > MAX_TARGET_CHARS) {
        setStage({
          phase: "failed",
          message: `That job description is too long (${MAX_TARGET_CHARS.toLocaleString()} character max).`,
        });
        return;
      }

      const startedAt = Date.now();
      setElapsed(0);
      setStarting(true);
      try {
        const result = await startResumeRun(idToken, trimmed);
        if (result.status === "failed") {
          setStage({ phase: "failed", message: result.message });
          return;
        }
        saveActiveRun({ runId: result.runId, startedAt, target: trimmed });
        setStage({ phase: "generating", runId: result.runId, startedAt });
      } finally {
        setStarting(false);
      }
    },
    [idToken, starting],
  );

  const reset = () => {
    saveActiveRun(null);
    setStage({ phase: "idle" });
  };

  const openRun = useCallback(
    async (runId: string) => {
      try {
        const result = await getResumeRun(idToken, runId);
        if (result.status === "completed") setStage({ phase: "done", run: result, fromHistory: true });
        else if (result.status === "notfound") {
          setStage({ phase: "failed", message: "That résumé is no longer available." });
        } else if (result.status === "failed") setStage({ phase: "failed", message: result.message });
      } catch {
        // Without this the rejection escapes to the window and View is simply a dead button.
        setStage({ phase: "failed", message: "Couldn't open that résumé — please try again." });
      }
    },
    [idToken],
  );

  const removeRun = useCallback(
    async (row: ResumeSummary) => {
      // ADR-027's confirm, and the copy names the résumé so the dialog cannot be dismissed on
      // autopilot without registering *which* one is about to go.
      if (!window.confirm(`Delete the résumé for "${row.targetTitle}"? This can't be undone.`)) return;

      setDeleting(row.runId);
      try {
        if (!(await deleteResume(idToken, row.runId))) {
          setStage({ phase: "failed", message: "Couldn't delete that résumé — please try again." });
          return;
        }
        // Optimistic removal, then a re-read. Slice 2's review found the reverse of this on
        // Timeline: a deleted record stayed on screen offering actions that no longer worked.
        setHistory((rows) => (rows ?? []).filter((r) => r.runId !== row.runId));
        // If the deleted résumé is the one on screen, its presigned URLs now point at nothing.
        setStage((current) =>
          current.phase === "done" && current.run.runId === row.runId ? { phase: "idle" } : current,
        );
        void refreshHistory();
      } catch {
        setStage({ phase: "failed", message: "Network error — that résumé was not deleted." });
      } finally {
        setDeleting(null);
      }
    },
    [idToken, refreshHistory],
  );

  return (
    <div className="view resumes">
      <div className="view-head">
        <div>
          <p className="eyebrow">Drawn from your vault</p>
          <h1>Résumés</h1>
        </div>
      </div>

      {stage.phase === "done" ? (
        <ResumeResult
          run={stage.run}
          starting={starting}
          onRegenerate={stage.fromHistory ? null : () => void start(target)}
          onNewTarget={reset}
        />
      ) : (
        <Generator
          target={target}
          setTarget={setTarget}
          stage={stage}
          starting={starting}
          elapsed={elapsed}
          entryCount={entries === null ? null : entries.length}
          onGenerate={() => void start(target)}
        />
      )}

      <History
        rows={history}
        failed={historyError}
        freshRunId={freshRunId}
        deleting={deleting}
        onOpen={(id) => void openRun(id)}
        onDelete={(row) => void removeRun(row)}
      />
    </div>
  );
}

/** The generator card, plus whatever the current non-terminal stage has to say. */
function Generator({
  target,
  setTarget,
  stage,
  starting,
  elapsed,
  entryCount,
  onGenerate,
}: {
  target: string;
  setTarget: (v: string) => void;
  stage: Stage;
  starting: boolean;
  elapsed: number;
  entryCount: number | null;
  onGenerate: () => void;
}) {
  const generating = stage.phase === "generating";

  return (
    <section className="card generator" aria-labelledby="generate-heading">
      <h2 id="generate-heading">Draw a new one</h2>

      <textarea
        id="resume-target"
        className="generator-input"
        value={target}
        maxLength={MAX_TARGET_CHARS}
        disabled={generating}
        aria-label="Target role or job description"
        placeholder="Target role — e.g. Senior AI Solutions Manager"
        onChange={(e) => setTarget(e.target.value)}
      />

      <div className="generator-row">
        <button className="btn-primary" onClick={onGenerate} disabled={starting || generating || !target.trim()}>
          {starting ? "Starting…" : "Generate"}
        </button>
        <p className="generator-help">
          {/* The designed copy is "Pulls the <n> records in your vault and ranks them against the
              target." `n` is the size of the vault, which only `GET /entries` knows — the shell
              already has it, so it is passed down. It is emphatically *not* a past run's
              `entry_count`: that is how many entries the agent *retrieved* for one target, a subset
              that changes with every unrelated run. Presenting it as the vault total would be a
              fabricated statistic of exactly the kind ADR-045 rules out. Omitted while entries are
              still loading, rather than guessed. */}
          {entryCount
            ? `Pulls the ${entryCount} records in your vault and ranks them against the target.`
            : "Pulls the records in your vault and ranks them against the target."}
        </p>
      </div>

      {/* §A11 — the long-running state is announced, not just animated. */}
      <div className="generator-status" role="status" aria-live="polite">
        {generating && (
          <>
            <span className="spinner" aria-hidden="true" />
            <span>
              Building your résumé — {formatElapsed(elapsed)} elapsed. This usually takes about three
              minutes; you can leave this tab and come back.
            </span>
          </>
        )}
      </div>

      {generating && stage.draft && (
        <div className="generator-draft">
          {/* Labelled unambiguously as work in progress. The agent is still critiquing and may
              rewrite any of this, so presenting it as the résumé would be a lie the next poll
              exposes — and the run can still fail from here. */}
          <p className="generator-draft-label">
            First draft — still being reviewed, and it will change.
          </p>
          {stage.draft.summary && <p className="generator-draft-summary">{stage.draft.summary}</p>}
          {stage.draft.experience?.slice(0, 3).map((role, index) => (
            <div key={`${role.employer}-${index}`} className="generator-draft-role">
              <p className="generator-draft-role-title">
                {role.title}
                {role.employer ? ` · ${role.employer}` : ""}
              </p>
              <ul>
                {role.bullets?.slice(0, 3).map((bullet, bulletIndex) => (
                  <li key={bulletIndex}>{bullet}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {stage.phase === "failed" && (
        <p className="generator-error" role="alert">
          {stage.message}
        </p>
      )}

      {stage.phase === "abandoned" && (
        <p className="generator-error" role="alert">
          Run {stage.runId} is taking longer than expected, so we stopped watching it. It may still
          finish — try generating again if it doesn&apos;t.
        </p>
      )}
    </section>
  );
}

/** A completed run: actions, the metadata row, copyable bullets (B-022), and the preview. */
function ResumeResult({
  run,
  starting,
  onRegenerate,
  onNewTarget,
}: {
  run: Extract<RunStatus, { status: "completed" }>;
  starting: boolean;
  /** `null` for a résumé opened from history — see `Stage.fromHistory`. */
  onRegenerate: (() => void) | null;
  onNewTarget: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const plainText = resumeToPlainText(run.document);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(plainText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2_000);
    } catch {
      // Clipboard is permission-gated and unavailable over plain http. The textarea below holds the
      // same text and is selectable, so a failure degrades to "select it yourself" rather than
      // losing the content — which is why the text is rendered rather than only copied.
      setCopied(false);
    }
  };

  return (
    <section className="card result" aria-labelledby="result-heading">
      <div className="result-head">
        <h2 id="result-heading">Your tailored résumé</h2>
        <div className="result-actions">
          {/* Cross-origin, so the save-to-disk comes from the presigned Content-Disposition,
              not from a `download` attribute (browsers ignore that across origins). */}
          <a className="btn-primary" href={run.pdfUrl} target="_blank" rel="noopener noreferrer">
            Download PDF
          </a>
          {onRegenerate ? (
            <button className="btn-quiet" onClick={onRegenerate} disabled={starting}>
              {starting ? "Starting…" : "Regenerate"}
            </button>
          ) : null}
          <button className="btn-quiet" onClick={onNewTarget}>
            New target
          </button>
        </div>
      </div>

      <p className="result-meta">
        {run.retrievedCount != null && <span>{run.retrievedCount} records drawn</span>}
        {run.elapsedSeconds != null && <span>{formatElapsed(Math.round(run.elapsedSeconds))}</span>}
        {run.critiqueVerdict && <span>critique: {run.critiqueVerdict}</span>}
        {run.tokens != null && <span>{run.tokens.toLocaleString()} tokens</span>}
        {run.costUsd != null && <span>${run.costUsd.toFixed(2)}</span>}
      </p>

      {plainText && (
        <details className="result-text">
          <summary>
            Plain text
            {/* The button lives inside `<summary>`, so a click on it also reaches the summary's
                activation behaviour and toggles the disclosure shut — copying the text and hiding
                it in the same gesture, which also hides the select-it-yourself fallback when the
                clipboard is blocked. `preventDefault` stops the toggle; `stopPropagation` keeps the
                click from bubbling to the summary at all. */}
            <button
              className="btn-quiet copy-button"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                void copy();
              }}
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </summary>
          {/* Read-only rather than disabled: a disabled textarea is not selectable, which would
              remove the fallback for a blocked clipboard. */}
          <textarea className="result-plaintext" readOnly value={plainText} aria-label="Résumé as plain text" />
        </details>
      )}

      <iframe className="result-preview" title="Résumé preview" src={run.htmlUrl} sandbox="" />
    </section>
  );
}

/** Past résumés (ADR-046). */
function History({
  rows,
  failed,
  freshRunId,
  deleting,
  onOpen,
  onDelete,
}: {
  rows: ResumeSummary[] | null;
  failed: boolean;
  freshRunId: string | null;
  deleting: string | null;
  onOpen: (runId: string) => void;
  onDelete: (row: ResumeSummary) => void;
}) {
  return (
    <section className="history" aria-labelledby="history-heading">
      <h2 id="history-heading">Past résumés</h2>

      <div aria-live="polite">
        {rows === null && failed ? (
          // Without this the panel sits on "Loading…" forever when the list call fails.
          <p className="muted">Couldn't load your résumés. Reload the page to try again.</p>
        ) : rows === null ? (
          <p className="muted">Loading your résumés…</p>
        ) : rows.length === 0 ? (
          <p className="muted">
            Nothing here yet. The résumés you generate will collect here — they are kept, not
            expired.
          </p>
        ) : (
          <ul className="history-grid">
            {rows.map((row, index) => (
              <li key={row.runId} className="card history-card">
                <div className="history-title-row">
                  <h3>{row.targetTitle}</h3>
                  {/* Only badges with a referent (ADR-045). "Sent" and "Draft" from the handoff
                      describe features that do not exist, so they are omitted rather than faked. */}
                  {row.runId === freshRunId ? (
                    <span className="badge">New</span>
                  ) : index === 0 ? (
                    <span className="badge">Latest</span>
                  ) : null}
                </div>
                <p className="history-meta">
                  Built {formatBuiltDate(row.createdAt)} · {row.entryCount} records drawn
                </p>
                <div className="history-actions">
                  <button className="btn-quiet" onClick={() => onOpen(row.runId)} disabled={deleting === row.runId}>
                    View
                  </button>
                  <button
                    className="btn-quiet danger"
                    onClick={() => onDelete(row)}
                    disabled={deleting === row.runId}
                    // The visible label is just "Delete" on every card, so without this every
                    // button in the grid has the same accessible name and a screen-reader user
                    // cannot tell which résumé they are about to destroy. It carries the date
                    // *and time* because neither the title nor the day is unique: the real vault
                    // holds two résumés both titled "Databricks", built four minutes apart on the
                    // same afternoon. A run takes ~3 minutes, so minute precision is enough.
                    aria-label={`Delete the résumé for ${row.targetTitle}, built ${formatBuiltStamp(row.createdAt)}`}
                  >
                    {deleting === row.runId ? "Deleting…" : "Delete"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}

/**
 * "28 Jul 2026" from a stored ISO timestamp.
 *
 * Reuses `formatEventDate` rather than reaching for `toLocaleDateString` again — that helper
 * already pins `timeZone: "UTC"` and `en-GB`, which is both the slice-2 fix (a UTC-anchored date
 * formatted locally renders the previous evening west of Greenwich) and the day-first order the
 * handoff specifies. It accepts a calendar date, and the first ten characters of a UTC ISO
 * timestamp *are* that date, so no re-parsing is needed.
 */
function formatBuiltDate(iso: string): string {
  return formatEventDate(iso.slice(0, 10), { year: "numeric" }) || "an unknown date";
}

/**
 * "28 Jul 2026 at 15:45" — the date plus a UTC time, for accessible names only.
 *
 * The card itself shows the date alone, which is what the design asks for and what a sighted user
 * disambiguates visually by position. A screen-reader user has neither, so the delete button's name
 * has to be unique on its own: title and day both repeat in practice.
 *
 * UTC to match `formatBuiltDate` — a label that said 16:45 while the card said a different day
 * would be worse than one that is simply consistent.
 */
function formatBuiltStamp(iso: string): string {
  const time = /T(\d{2}):(\d{2})/.exec(iso);
  const date = formatBuiltDate(iso);
  return time ? `${date} at ${time[1]}:${time[2]}` : date;
}
