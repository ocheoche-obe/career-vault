import { useRef, useState } from "react";
import {
  contentTypeForFilename,
  parseUpload,
  presignUpload,
  putFileToS3,
  type EntryCandidate,
} from "../lib/api";
import { ReviewTable } from "./ReviewTable";
import "./upload.css";

/**
 * Import — the one-time backfill (FR-2 via ADR-013 / ADR-035). The user drops a PDF/DOCX; the
 * browser presigns, uploads straight to S3, then asks the parse route for entry candidates, which
 * land in the select-all review list to confirm through the normal `POST /entries` path.
 *
 * The whole flow is synchronous request/response (ADR-035): start simple, and only reach for an
 * async job shape if real parse latency ever demands it.
 *
 * ACCESSIBILITY §A9 — the file input previously had no accessible name at all: a screen reader
 * announced "button" with nothing to say what it was for. The dropzone is now a `<label>` wrapping a
 * visually-hidden (not `display: none`, which would make it unfocusable) input, so the control keeps
 * real file-input semantics and keyboard behaviour while the whole panel is the click target. The
 * focus ring is driven off `:focus-within` on the label, since the input itself is not visible.
 */

const MAX_FILE_MB = 10;

type Stage =
  | { phase: "idle" }
  | { phase: "uploading"; filename: string }
  | { phase: "parsing"; filename: string }
  | { phase: "review"; candidates: EntryCandidate[]; dropped: number }
  | { phase: "empty" }
  | { phase: "error"; message: string };

export function Upload({ idToken, onImported }: { idToken: string; onImported?: () => void }) {
  const [stage, setStage] = useState<Stage>({ phase: "idle" });
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setStage({ phase: "idle" });
    if (inputRef.current) inputRef.current.value = "";
  };

  const onFile = async (file: File) => {
    const contentType = contentTypeForFilename(file.name);
    if (!contentType) {
      setStage({ phase: "error", message: "Please choose a PDF or DOCX file." });
      return;
    }
    if (file.size > MAX_FILE_MB * 1024 * 1024) {
      setStage({ phase: "error", message: `That file is over ${MAX_FILE_MB} MB.` });
      return;
    }

    setStage({ phase: "uploading", filename: file.name });
    try {
      const presigned = await presignUpload(idToken, {
        filename: file.name,
        content_type: contentType,
      });
      await putFileToS3(presigned, file);

      setStage({ phase: "parsing", filename: file.name });
      const result = await parseUpload(idToken, presigned.key);
      if (result.status === "failed") {
        setStage({ phase: "error", message: result.message });
        return;
      }
      if (result.candidates.length === 0) {
        setStage({ phase: "empty" });
        return;
      }
      setStage({ phase: "review", candidates: result.candidates, dropped: result.dropped });
    } catch (err) {
      setStage({
        phase: "error",
        message: err instanceof Error ? err.message : "Something went wrong.",
      });
    }
  };

  const working = stage.phase === "uploading" || stage.phase === "parsing";

  return (
    <div className="view import">
      <div>
        <p className="eyebrow">One-time backfill</p>
        <h1>Import a résumé</h1>
      </div>
      <p className="import-lead">
        Start the vault with what you already have. We read the file, split it into records, and let
        you keep the ones worth keeping — nothing is saved until you confirm.
      </p>

      {stage.phase === "review" ? (
        <ReviewTable
          idToken={idToken}
          candidates={stage.candidates}
          dropped={stage.dropped}
          onDone={() => {
            reset();
            onImported?.();
          }}
          onSaved={onImported}
        />
      ) : (
        <>
          <label
            className={`dropzone${dragging ? " dragging" : ""}${working ? " working" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              if (!working) setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              if (working) return;
              const file = e.dataTransfer.files?.[0];
              if (file) void onFile(file);
            }}
          >
            <input
              ref={inputRef}
              className="sr-only"
              type="file"
              accept=".pdf,.docx"
              disabled={working}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void onFile(file);
              }}
            />
            <span className="drop-icon" aria-hidden="true">
              ↑
            </span>
            <span className="drop-primary">
              {working ? "Working…" : "Drop a PDF or DOCX here"}
            </span>
            <span className="drop-status">
              {stage.phase === "uploading"
                ? `Uploading ${stage.filename}…`
                : stage.phase === "parsing"
                  ? `Reading ${stage.filename}…`
                  : `or choose a file · up to ${MAX_FILE_MB} MB`}
            </span>
          </label>

          {/* §A11 — upload and parse are slow and entirely silent otherwise. */}
          <p className="sr-only" role="status">
            {stage.phase === "uploading"
              ? `Uploading ${stage.filename}`
              : stage.phase === "parsing"
                ? `Reading ${stage.filename}`
                : ""}
          </p>

          {stage.phase === "empty" && (
            <div className="card import-note">
              <p>We couldn&apos;t find anything recordable in that file.</p>
              <button className="btn-quiet" onClick={reset}>
                Try another file
              </button>
            </div>
          )}

          {stage.phase === "error" && (
            <div className="card import-note error" role="alert">
              <p className="field-error">{stage.message}</p>
              <button className="btn-quiet" onClick={reset}>
                Try again
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
