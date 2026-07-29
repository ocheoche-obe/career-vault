import { vi } from "vitest";

/**
 * A `fetch` stub for component tests.
 *
 * Components are tested against the *real* `lib/api` with only the network faked, rather than
 * against a mocked api module. Two reasons, one by design and one forced:
 *
 * - By design: the status-code mapping in `lib/api` (Section 3.1.5 — 201/200/409/422/500 →
 *   `ConfirmResult`) is part of the behavior worth locking, and a mocked api module skips straight
 *   past it. Stubbing at the network boundary also means assertions can check the actual request
 *   body, which is the thing the backend contract is written in.
 * - Forced: a `vi.fn()` that returns a rejected promise trips Vitest's spy settlement tracking. The
 *   derived chain it attaches to observe the result goes unhandled and fails the test even when the
 *   component's own `catch` fires correctly, which makes every error-path test unwritable that way.
 *   A plain async function has no such tracking.
 */

export type StubbedRequest = {
  url: string;
  method: string;
  body: Record<string, unknown> | undefined;
};

export type StubResponse =
  | { status: number; body?: unknown }
  /** Simulates a dead network — `fetch` itself rejecting, not an error status. */
  | { networkError: true };

/**
 * Install a `fetch` stub that answers with `queue` in order, repeating the last entry once the
 * queue is exhausted. Returns the live array of requests it received.
 *
 * Repeating rather than throwing on exhaustion is deliberate: an unexpected extra call should fail
 * an explicit count assertion with a readable message, not surface as an inscrutable rejection.
 */
export function stubFetch(...queue: StubResponse[]): StubbedRequest[] {
  const calls: StubbedRequest[] = [];

  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const raw = init?.body;
    calls.push({
      url: String(input),
      method: init?.method ?? "GET",
      body: typeof raw === "string" ? (JSON.parse(raw) as Record<string, unknown>) : undefined,
    });

    const next = queue[Math.min(calls.length - 1, queue.length - 1)];
    if (!next) throw new Error("stubFetch called with no responses queued");
    if ("networkError" in next) throw new TypeError("Failed to fetch");

    // 204/205/304 are null-body statuses — the Response constructor throws if given one, and the
    // resulting failure names the helper rather than the test that asked for it.
    const nullBody = next.status === 204 || next.status === 205 || next.status === 304;
    return new Response(nullBody ? null : JSON.stringify(next.body ?? {}), {
      status: next.status,
      headers: { "Content-Type": "application/json" },
    });
  });

  return calls;
}
