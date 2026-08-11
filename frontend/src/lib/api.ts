/**
 * Typed client for the chat + entry endpoints (Sections 3.1, 3.1.3–3.1.5, ADR-033).
 *
 * `POST /chat` is Phase A (parse turn) — it never persists, only proposes or clarifies.
 * `POST /entries` is Phase B (confirm) — the reviewed candidate, carrying the `entry_id` minted at
 * propose time, which is what makes confirm idempotent (Section 3.1.4). Slice 3 adds the rest of
 * the entry lifecycle: `GET /entries` (dashboard), `PUT /entries/{id}` (edit), `DELETE` (remove).
 */

import { apiBaseUrl } from "../auth/oidcConfig";

/** A proposed entry: the typed fields vary by entry_type; entry_id travels with it. */
export type EntryCandidate = {
  entry_type: string;
  title: string;
  content: string;
  entry_id: string;
  [key: string]: unknown;
};

/** A persisted entry as returned by GET /entries (embedding stripped server-side). */
export type Entry = {
  entry_id: string;
  entry_type: string;
  title: string;
  content: string;
  event_date?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
};

/** What grounded an answer, so the user can check it against their own entries (ADR-038). */
export type AnswerSource = {
  entry_id: string;
  entry_type: string;
  title: string;
  score: number;
};

export type ChatResponse =
  | { kind: "clarification"; question: string; reason?: string; session_id: string }
  | { kind: "parse_candidate"; candidate: EntryCandidate; session_id: string }
  | { kind: "answer"; answer: string; sources: AnswerSource[]; session_id: string }
  | { kind: "error"; message: string; session_id: string };

export type FieldError = { field: string; error: string };

/** One near-duplicate surfaced by the ADR-033 check at confirm time. */
export type DuplicateMatch = {
  entry_id: string;
  entry_type: string;
  title: string;
  similarity: number;
};

/** Outcome of a confirm, mapped from the 201/200/409/422/500 contract (Section 3.1.5). */
export type ConfirmResult =
  | { status: "created" | "duplicate"; entry: Record<string, unknown> }
  | { status: "possible_duplicate"; entryId: string; duplicates: DuplicateMatch[] }
  | { status: "invalid"; errors: FieldError[] }
  | { status: "failed"; message: string };

/** Outcome of an edit (PUT /entries/{id}). */
export type UpdateResult =
  | { status: "updated"; entry: Record<string, unknown> }
  | { status: "invalid"; errors: FieldError[] }
  | { status: "notfound" }
  | { status: "failed"; message: string };

function authHeaders(idToken: string): HeadersInit {
  return { "Content-Type": "application/json", Authorization: `Bearer ${idToken}` };
}

async function jsonOf(res: Response): Promise<Record<string, unknown>> {
  return (await res.json().catch(() => ({}))) as Record<string, unknown>;
}

export async function postChat(
  idToken: string,
  body: { message: string; session_id?: string; client_message_id: string },
): Promise<ChatResponse> {
  const res = await fetch(`${apiBaseUrl}/chat`, {
    method: "POST",
    headers: authHeaders(idToken),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST /chat → ${res.status}`);
  return (await res.json()) as ChatResponse;
}

/**
 * Confirm an entry. Pass `{ acknowledge: true }` to save past a `possible_duplicate` warning —
 * the same `entry_id` is reused, so an acknowledged save stays idempotent (Section 3.1.4).
 */
export async function confirmEntry(
  idToken: string,
  candidate: EntryCandidate,
  opts: { acknowledge?: boolean } = {},
): Promise<ConfirmResult> {
  const body = opts.acknowledge ? { ...candidate, acknowledge_duplicate: true } : candidate;
  const res = await fetch(`${apiBaseUrl}/entries`, {
    method: "POST",
    headers: authHeaders(idToken),
    body: JSON.stringify(body),
  });
  const b = await jsonOf(res);
  if (res.status === 201) return { status: "created", entry: b.entry as Record<string, unknown> };
  if (res.status === 200) return { status: "duplicate", entry: b.entry as Record<string, unknown> };
  if (res.status === 409) {
    return {
      status: "possible_duplicate",
      entryId: b.entry_id as string,
      duplicates: (b.possible_duplicates as DuplicateMatch[]) ?? [],
    };
  }
  if (res.status === 422) return { status: "invalid", errors: (b.errors as FieldError[]) ?? [] };
  return { status: "failed", message: (b.message as string) ?? `POST /entries → ${res.status}` };
}

export async function listEntries(idToken: string): Promise<Entry[]> {
  const res = await fetch(`${apiBaseUrl}/entries`, { headers: authHeaders(idToken) });
  if (!res.ok) throw new Error(`GET /entries → ${res.status}`);
  const b = await jsonOf(res);
  return (b.entries as Entry[]) ?? [];
}

export async function updateEntry(
  idToken: string,
  entryId: string,
  fields: Record<string, unknown>,
): Promise<UpdateResult> {
  const res = await fetch(`${apiBaseUrl}/entries/${encodeURIComponent(entryId)}`, {
    method: "PUT",
    headers: authHeaders(idToken),
    body: JSON.stringify(fields),
  });
  const b = await jsonOf(res);
  if (res.status === 200) return { status: "updated", entry: b.entry as Record<string, unknown> };
  if (res.status === 422) return { status: "invalid", errors: (b.errors as FieldError[]) ?? [] };
  if (res.status === 404) return { status: "notfound" };
  return { status: "failed", message: (b.message as string) ?? `PUT /entries → ${res.status}` };
}

/** Hard delete (ADR-027). Returns true on success; a 404 (already gone) also resolves the intent. */
export async function deleteEntry(idToken: string, entryId: string): Promise<boolean> {
  const res = await fetch(`${apiBaseUrl}/entries/${encodeURIComponent(entryId)}`, {
    method: "DELETE",
    headers: authHeaders(idToken),
  });
  return res.status === 200 || res.status === 404;
}

/**
 * Resume upload bootstrap (ADR-035). Three steps, all synchronous:
 *   1. presignUpload — POST /uploads/presign → a short-lived S3 PUT URL scoped to the user's prefix
 *   2. putFileToS3   — the browser uploads the file straight to S3 (off the compute plane)
 *   3. parseUpload   — POST /uploads/parse → entry candidates (parse-only: no embed, no write)
 * Each returned candidate is then saved through confirmEntry, exactly like a chat proposal.
 */

/** The presigned target for a browser→S3 PUT. `contentType` must be echoed on the PUT. */
export type PresignedUpload = { url: string; key: string; contentType: string };

export type ParseResult =
  | { status: "ok"; candidates: EntryCandidate[]; dropped: number; charCount: number; parseMs: number }
  | { status: "failed"; message: string };

/** Map an upload extension to the content type the presign route expects. */
export function contentTypeForFilename(filename: string): string | null {
  const ext = filename.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return "application/pdf";
  if (ext === "docx") return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  return null;
}

export async function presignUpload(
  idToken: string,
  body: { filename: string; content_type: string },
): Promise<PresignedUpload> {
  const res = await fetch(`${apiBaseUrl}/uploads/presign`, {
    method: "POST",
    headers: authHeaders(idToken),
    body: JSON.stringify(body),
  });
  const b = await jsonOf(res);
  if (!res.ok) throw new Error((b.message as string) ?? `POST /uploads/presign → ${res.status}`);
  return { url: b.url as string, key: b.key as string, contentType: b.content_type as string };
}

/** PUT the raw file to the presigned URL. The Content-Type must match what was signed. */
export async function putFileToS3(upload: PresignedUpload, file: File): Promise<void> {
  const res = await fetch(upload.url, {
    method: "PUT",
    headers: { "Content-Type": upload.contentType },
    body: file,
  });
  if (!res.ok) throw new Error(`Upload to S3 failed → ${res.status}`);
}

export async function parseUpload(idToken: string, key: string): Promise<ParseResult> {
  const res = await fetch(`${apiBaseUrl}/uploads/parse`, {
    method: "POST",
    headers: authHeaders(idToken),
    body: JSON.stringify({ key }),
  });
  const b = await jsonOf(res);
  if (res.status === 200) {
    return {
      status: "ok",
      candidates: (b.candidates as EntryCandidate[]) ?? [],
      dropped: (b.dropped as number) ?? 0,
      charCount: (b.char_count as number) ?? 0,
      parseMs: (b.parse_ms as number) ?? 0,
    };
  }
  return { status: "failed", message: (b.message as string) ?? `POST /uploads/parse → ${res.status}` };
}

/**
 * Résumé generation (slice 6b, FR-5.3/5.4) — the ADR-037 async job contract.
 *
 * A run takes ~3 minutes, well past API Gateway's 29s ceiling, so generation is never a single
 * request: `POST /resumes/generate` returns `202 {run_id}` and kicks off a worker, then
 * `GET /resumes/{run_id}` is polled until it reports `completed` or `failed`. Both URLs on a
 * completed run are freshly presigned per poll (1h TTL), so they are read at use time, not cached.
 */

/** The backend's own character ceiling on `target` — mirrored to fail fast before a round trip. */
export const MAX_TARGET_CHARS = 20_000;

export type StartRunResult =
  | { status: "started"; runId: string }
  | { status: "failed"; message: string };

/**
 * The structured résumé the agent produced (B-022).
 *
 * Returned on a completed poll so bullets can be copied as plain text. Formatting stays client-side
 * — the API returns data, not a rendering, which is ADR-045's derive-don't-endpoint rule applied
 * again. Every field is optional because a résumé for a thin corpus legitimately omits sections.
 */
export type ResumeDocument = {
  summary?: string;
  skills?: string[];
  experience?: { title?: string; employer?: string; dates?: string; bullets?: string[] }[];
  projects?: { name?: string; description?: string; bullets?: string[] }[];
  education?: { degree?: string; institution?: string; dates?: string; details?: string[] }[];
  certs?: { name?: string; issuer?: string; date?: string }[];
};

/** A poll result. `failed` carries the backend's already-friendly message — render it as-is. */
export type RunStatus =
  | { status: "pending"; runId: string }
  | {
      status: "completed";
      runId: string;
      htmlUrl: string;
      pdfUrl: string;
      critiqueVerdict?: string;
      retrievedCount?: number;
      costUsd?: number;
      tokens?: number;
      /** B-007 — wall-clock seconds the run took. Absent on records backfilled by ADR-046. */
      elapsedSeconds?: number;
      document?: ResumeDocument;
    }
  | { status: "failed"; runId: string; message: string }
  | { status: "notfound"; runId: string };

/** One row of résumé history (ADR-046). Projected server-side — no target text, no document. */
export type ResumeSummary = {
  runId: string;
  createdAt: string;
  targetTitle: string;
  entryCount: number;
  status: string;
};

/**
 * `GET /resumes` — the user's résumé history, newest first (ADR-046).
 *
 * Returns `[]` rather than throwing on failure: history is a secondary panel beside the generator,
 * and a list that cannot load must not stop someone building a new résumé. The caller distinguishes
 * "empty" from "broken" via the thrown-free `ok` flag.
 */
export async function listResumes(idToken: string): Promise<{ ok: boolean; resumes: ResumeSummary[] }> {
  const res = await fetch(`${apiBaseUrl}/resumes`, { headers: authHeaders(idToken) });
  if (!res.ok) return { ok: false, resumes: [] };
  const b = await jsonOf(res);
  const rows = Array.isArray(b.resumes) ? (b.resumes as Record<string, unknown>[]) : [];
  return {
    ok: true,
    resumes: rows.map((r) => ({
      runId: String(r.run_id ?? ""),
      createdAt: String(r.created_at ?? ""),
      targetTitle: String(r.target_title ?? "Untitled target"),
      entryCount: Number(r.entry_count ?? 0),
      status: String(r.status ?? "completed"),
    })),
  };
}

/**
 * `DELETE /resumes/{run_id}` — remove a résumé, its run trace and its S3 artifacts (ADR-046).
 *
 * `404` counts as success for the same reason `deleteEntry` treats it that way: the caller asked
 * for the résumé to be gone, and it is. Racing two deletes should not surface an error.
 */
export async function deleteResume(idToken: string, runId: string): Promise<boolean> {
  const res = await fetch(`${apiBaseUrl}/resumes/${encodeURIComponent(runId)}`, {
    method: "DELETE",
    headers: authHeaders(idToken),
  });
  return res.status === 200 || res.status === 404;
}

export async function startResumeRun(idToken: string, target: string): Promise<StartRunResult> {
  const res = await fetch(`${apiBaseUrl}/resumes/generate`, {
    method: "POST",
    headers: authHeaders(idToken),
    body: JSON.stringify({ target }),
  });
  const b = await jsonOf(res);
  if (res.status === 202) return { status: "started", runId: b.run_id as string };
  return {
    status: "failed",
    message: (b.message as string) ?? `POST /resumes/generate → ${res.status}`,
  };
}

export async function getResumeRun(idToken: string, runId: string): Promise<RunStatus> {
  const res = await fetch(`${apiBaseUrl}/resumes/${encodeURIComponent(runId)}`, {
    headers: authHeaders(idToken),
  });
  if (res.status === 404) return { status: "notfound", runId };
  const b = await jsonOf(res);
  if (!res.ok) {
    return { status: "failed", runId, message: (b.message as string) ?? `GET /resumes → ${res.status}` };
  }
  if (b.status === "completed") {
    return {
      status: "completed",
      runId,
      htmlUrl: b.html_url as string,
      pdfUrl: b.pdf_url as string,
      critiqueVerdict: b.critique_verdict as string | undefined,
      retrievedCount: b.retrieved_count as number | undefined,
      costUsd: b.cost_usd as number | undefined,
      tokens: b.tokens as number | undefined,
      elapsedSeconds: b.elapsed_seconds as number | undefined,
      document: b.document as ResumeDocument | undefined,
    };
  }
  if (b.status === "failed") {
    return {
      status: "failed",
      runId,
      message: (b.message as string) ?? "Couldn't generate a résumé — please try again.",
    };
  }
  return { status: "pending", runId };
}

// --- Profile / settings (B-008: the résumé identity header) -------------------------------

/** Check-in cadences (FR-4.1). `weekly` is the default and what an absent value means. */
export const CHECKIN_CADENCES = ["weekly", "biweekly", "monthly", "quarterly"] as const;
export type CheckinCadence = (typeof CHECKIN_CADENCES)[number];

export type CheckinSettings = {
  checkin_cadence?: CheckinCadence;
  checkin_paused?: boolean;
  preferred_template_id?: string | null;
};

/** The PROFILE singleton as `GET /settings` returns it. */
export type Profile = {
  email: string;
  name?: string | null;
  location?: string | null;
  phone?: string | null;
  aspirational_goal?: string | null;
  summary?: string | null;
  skills?: string[];
  portfolio_links?: Record<string, string>;
  /** Absent on every PROFILE written before slice 8 — treat missing as the defaults. */
  settings?: CheckinSettings;
  next_checkin_at?: string | null;
  last_checkin_sent_at?: string | null;
};

/**
 * The user-editable subset. `email` is deliberately absent — the server takes it from the JWT,
 * and so are `next_checkin_at` / `last_checkin_sent_at` / the bounce counters, which are
 * server-owned scheduling state (a client that could postpone its own check-in could steer a
 * scheduled job from a request body).
 *
 * `settings` is a *partial*: send only the sub-fields being changed. The backend merges them one
 * document path at a time (ADR-040), so sending `{ checkin_paused: true }` alone leaves the
 * stored cadence intact — sending the whole object back would work too, but relying on that would
 * make a stale local copy able to overwrite a change made elsewhere.
 */
export type ProfileUpdate = {
  name?: string | null;
  location?: string | null;
  phone?: string | null;
  aspirational_goal?: string | null;
  settings?: CheckinSettings;
};

export type SaveProfileResult =
  | { status: "saved"; profile: Profile }
  | { status: "invalid"; errors: FieldError[] }
  | { status: "failed"; message: string };

export async function getSettings(idToken: string): Promise<Profile> {
  const res = await fetch(`${apiBaseUrl}/settings`, { headers: authHeaders(idToken) });
  if (!res.ok) throw new Error(`GET /settings → ${res.status}`);
  return (await res.json()) as Profile;
}

export async function putSettings(idToken: string, body: ProfileUpdate): Promise<SaveProfileResult> {
  const res = await fetch(`${apiBaseUrl}/settings`, {
    method: "PUT",
    headers: authHeaders(idToken),
    body: JSON.stringify(body),
  });
  const payload = await jsonOf(res);
  if (res.ok) return { status: "saved", profile: payload as unknown as Profile };
  if (res.status === 400 && Array.isArray(payload.errors)) {
    return { status: "invalid", errors: payload.errors as FieldError[] };
  }
  return { status: "failed", message: (payload.message as string) ?? `PUT /settings → ${res.status}` };
}
