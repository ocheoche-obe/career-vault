import { useCallback, useEffect, useState } from "react";
import { MAX_TARGET_CHARS, getResumeRun, startResumeRun, type RunStatus } from "../lib/api";
import "./resume.css";

/**
 * Tailored résumé generation (FR-5.1/5.3/5.4) over the ADR-037 async job contract.
 *
 * A run is ~3 minutes — far past API Gateway's 29s ceiling — so this view never awaits a résumé.
 * It starts a job, gets a `run_id` back, and polls until the job reports a terminal status. Three
 * consequences shape the code below:
 *
 * 1. **The run_id outlives the component.** A run costs ~$0.31 and keeps going server-side whether
 *    or not anyone is watching, so the id is parked in sessionStorage: a reload or an accidental
 *    tab switch re-attaches to the same run instead of orphaning it and paying twice.
 * 2. **The preview is an iframe `src`, not a fetch.** The data bucket's CORS allows PUT only (it
 *    was written for the slice-5 upload), and an iframe navigation isn't subject to CORS — so the
 *    presigned HTML renders against the bucket exactly as deployed.
 * 3. **Failures are rendered, not mapped.** The backend already turns each internal `detail` code
 *    into a user-facing sentence, so there is no second copy of that vocabulary here.
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
  | { phase: "generating"; runId: string; startedAt: number }
  | { phase: "done"; run: Extract<RunStatus, { status: "completed" }> }
  | { phase: "failed"; message: string }
  | { phase: "abandoned"; runId: string };

export function Resume({ idToken }: { idToken: string }) {
  // Read once, at mount: if a run was in flight when the tab reloaded, re-attach to it.
  const [restored] = useState(loadActiveRun);
  const [target, setTarget] = useState(restored?.target ?? "");
  const [stage, setStage] = useState<Stage>(() =>
    restored ? { phase: "generating", runId: restored.runId, startedAt: restored.startedAt } : { phase: "idle" },
  );
  const [elapsed, setElapsed] = useState(0);
  const [starting, setStarting] = useState(false);

  const generating = stage.phase === "generating";

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
        if (result.status === "completed") return settle({ phase: "done", run: result });
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
  }, [generating, stage, idToken]);

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

  // --- generating ---------------------------------------------------------------------------------
  if (stage.phase === "generating") {
    return (
      <section className="resume">
        <div className="resume-panel">
          <h2>Building your résumé…</h2>
          <p className="resume-lead">
            The agent is reading your history, drafting, critiquing its own draft, and revising. This
            usually takes about three minutes — you can leave this tab and come back.
          </p>
          <div className="resume-progress" role="status" aria-live="polite">
            <span className="resume-spinner" aria-hidden="true" />
            <span>{formatElapsed(elapsed)} elapsed</span>
          </div>
          <p className="resume-runid">Run {stage.runId}</p>
        </div>
      </section>
    );
  }

  // --- completed ----------------------------------------------------------------------------------
  if (stage.phase === "done") {
    const { run } = stage;
    return (
      <section className="resume resume-wide">
        <div className="resume-result-head">
          <h2>Your tailored résumé</h2>
          <div className="resume-actions">
            {/* Cross-origin, so the save-to-disk comes from the presigned Content-Disposition,
                not from a `download` attribute (browsers ignore that across origins). */}
            <a className="button" href={run.pdfUrl} target="_blank" rel="noopener noreferrer">
              Download PDF
            </a>
            <button className="secondary" onClick={() => void start(target)} disabled={starting}>
              {starting ? "Starting…" : "Regenerate"}
            </button>
            <button className="secondary" onClick={reset}>
              New target
            </button>
          </div>
        </div>

        <p className="resume-meta">
          {run.retrievedCount != null && <span>{run.retrievedCount} entries used</span>}
          {run.critiqueVerdict && <span>critique: {run.critiqueVerdict}</span>}
          {run.tokens != null && <span>{run.tokens.toLocaleString()} tokens</span>}
          {run.costUsd != null && <span>${run.costUsd.toFixed(2)}</span>}
        </p>

        <iframe
          className="resume-preview"
          title="Résumé preview"
          src={run.htmlUrl}
          sandbox=""
        />
      </section>
    );
  }

  // --- idle / failed / abandoned ------------------------------------------------------------------
  return (
    <section className="resume">
      <div className="resume-panel">
        <h2>Generate a tailored résumé</h2>
        <p className="resume-lead">
          Paste the job description you&apos;re targeting (or just name the role). The agent picks the
          most relevant items from your logged history — it only uses what you&apos;ve actually
          recorded.
        </p>

        <textarea
          className="resume-target"
          value={target}
          maxLength={MAX_TARGET_CHARS}
          placeholder="Paste a job description, or e.g. “Senior Solutions Architect, AWS partner, focus on data platforms”"
          onChange={(e) => setTarget(e.target.value)}
        />

        {stage.phase === "failed" && (
          <div className="resume-note error">
            <p>{stage.message}</p>
          </div>
        )}

        {stage.phase === "abandoned" && (
          <div className="resume-note error">
            <p>
              Run {stage.runId} is taking longer than expected, so we stopped watching it. It may
              still finish — try generating again if it doesn&apos;t.
            </p>
          </div>
        )}

        <div className="resume-actions">
          <button onClick={() => void start(target)} disabled={starting || !target.trim()}>
            {starting ? "Starting…" : "Generate résumé"}
          </button>
        </div>
      </div>
    </section>
  );
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}
