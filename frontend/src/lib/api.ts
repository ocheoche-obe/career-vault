/**
 * Typed client for the two chat-slice endpoints (Section 3.1).
 *
 * `POST /chat` is Phase A (parse turn) — it never persists an entry, only proposes one or asks
 * a clarifying question. `POST /entries` is Phase B (confirm) — the reviewed candidate, carrying
 * the `entry_id` minted at propose time, which is what makes confirm idempotent (Section 3.1.4).
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

export type ChatResponse =
  | { kind: "clarification"; question: string; reason?: string; session_id: string }
  | { kind: "parse_candidate"; candidate: EntryCandidate; session_id: string }
  | { kind: "error"; message: string; session_id: string };

export type FieldError = { field: string; error: string };

/** Outcome of a confirm, mapped from the 201/200/422/500 contract (Section 3.1.5). */
export type ConfirmResult =
  | { status: "created" | "duplicate"; entry: Record<string, unknown> }
  | { status: "invalid"; errors: FieldError[] }
  | { status: "failed"; message: string };

async function postJson(idToken: string, path: string, body: unknown): Promise<Response> {
  return fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${idToken}`,
    },
    body: JSON.stringify(body),
  });
}

export async function postChat(
  idToken: string,
  body: { message: string; session_id?: string; client_message_id: string },
): Promise<ChatResponse> {
  const res = await postJson(idToken, "/chat", body);
  if (!res.ok) throw new Error(`POST /chat → ${res.status}`);
  return (await res.json()) as ChatResponse;
}

export async function confirmEntry(idToken: string, candidate: EntryCandidate): Promise<ConfirmResult> {
  const res = await postJson(idToken, "/entries", candidate);
  const body = await res.json().catch(() => ({}));
  if (res.status === 201) return { status: "created", entry: body.entry };
  if (res.status === 200) return { status: "duplicate", entry: body.entry };
  if (res.status === 422) return { status: "invalid", errors: body.errors ?? [] };
  return { status: "failed", message: body.message ?? `POST /entries → ${res.status}` };
}
