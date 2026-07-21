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
 * Resume upload bootstrap (FR-2 via ADR-013 / ADR-035). The user picks a PDF/DOCX; the browser
 * presigns, uploads straight to S3, then asks the parse route for entry candidates — which land in
 * the select-all ReviewTable to confirm through the normal `POST /entries` path.
 *
 * The whole flow is synchronous request/response (ADR-035): start simple, and only reach for an
 * async job shape if real parse latency ever demands it.
 */

const MAX_FILE_MB = 10;

type Stage =
  | { phase: "idle" }
  | { phase: "uploading"; filename: string }
  | { phase: "parsing"; filename: string }
  | { phase: "review"; candidates: EntryCandidate[]; dropped: number }
  | { phase: "empty" }
  | { phase: "error"; message: string };

export function Upload({ idToken }: { idToken: string }) {
  const [stage, setStage] = useState<Stage>({ phase: "idle" });
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
      const presigned = await presignUpload(idToken, { filename: file.name, content_type: contentType });
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
      setStage({ phase: "error", message: err instanceof Error ? err.message : "Something went wrong." });
    }
  };

  if (stage.phase === "review") {
    return (
      <ReviewTable
        idToken={idToken}
        candidates={stage.candidates}
        dropped={stage.dropped}
        onDone={reset}
      />
    );
  }

  const working = stage.phase === "uploading" || stage.phase === "parsing";

  return (
    <section className="upload">
      <div className="upload-drop">
        <h2>Import from a resume</h2>
        <p className="upload-lead">
          Upload a PDF or DOCX and we&apos;ll pull out your roles, projects, certifications, and more
          for you to review — nothing is saved until you confirm.
        </p>

        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx"
          disabled={working}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void onFile(file);
          }}
        />

        {stage.phase === "uploading" && <p className="upload-status">Uploading {stage.filename}…</p>}
        {stage.phase === "parsing" && <p className="upload-status">Reading {stage.filename}…</p>}

        {stage.phase === "empty" && (
          <div className="upload-note">
            <p>We couldn&apos;t find anything recordable in that file.</p>
            <button className="secondary" onClick={reset}>Try another file</button>
          </div>
        )}

        {stage.phase === "error" && (
          <div className="upload-note error">
            <p>{stage.message}</p>
            <button className="secondary" onClick={reset}>Try again</button>
          </div>
        )}
      </div>
    </section>
  );
}
