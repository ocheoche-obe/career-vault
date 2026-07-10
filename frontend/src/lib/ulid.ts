/**
 * Minimal client-side ULID generator (ADR-032).
 *
 * The client names each chat turn with a ULID and reuses it verbatim on retry — that reuse is
 * what makes a retried turn idempotent server-side. 26 chars of Crockford base32: a 48-bit
 * millisecond timestamp (10 chars) followed by 80 random bits (16 chars). Self-contained rather
 * than a dependency; the server independently validates the format.
 */

const CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

export function ulid(now: number = Date.now()): string {
  let time = "";
  let t = now;
  for (let i = 0; i < 10; i++) {
    time = CROCKFORD[t % 32] + time;
    t = Math.floor(t / 32);
  }

  // 256 is divisible by 32, so byte % 32 is uniform.
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let rand = "";
  for (const byte of bytes) rand += CROCKFORD[byte % 32];

  return time + rand;
}
