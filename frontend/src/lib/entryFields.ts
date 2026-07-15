/**
 * Shared entry-field helpers used by both the propose flow (ProposalCard) and the edit flow
 * (EntryEditForm). All eight entry types render generically from their own keys, so there are no
 * per-type forms — the server's discriminated union stays the single source of truth (ADR-022).
 */

/** Attributes the frontend must never render as editable or echo back to the API on edit. */
const SYSTEM_KEYS = new Set([
  "PK",
  "SK",
  "entity_type",
  "embedding",
  "embedding_model",
  "created_at",
  "updated_at",
  "similarity",
]);

/** Shown for context but not editable: identity and the type discriminator are fixed. */
export const READONLY_KEYS = new Set(["entry_id", "entry_type"]);

export function toInputValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  return value == null ? "" : String(value);
}

export function fromInputValue(original: unknown, edited: string): unknown {
  if (Array.isArray(original)) {
    return edited.split(",").map((s) => s.trim()).filter(Boolean);
  }
  if (typeof original === "number") {
    const n = Number(edited);
    return Number.isNaN(n) ? edited : n;
  }
  return edited;
}

/** The editable subset of an entry/candidate, as string inputs keyed by field name. */
export function editableFields(entry: Record<string, unknown>): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const [key, value] of Object.entries(entry)) {
    if (SYSTEM_KEYS.has(key) || READONLY_KEYS.has(key)) continue;
    fields[key] = toInputValue(value);
  }
  return fields;
}

/**
 * Re-assemble a payload for the API: the original entry minus system attributes (which would trip
 * the server's `extra="forbid"`), with the user's edits applied over it. `entry_type` is kept for
 * the discriminator; `entry_id` rides along where present (the confirm path needs it, the edit
 * path's handler ignores it in favour of the URL).
 */
export function mergeEdits(
  entry: Record<string, unknown>,
  fields: Record<string, string>,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(entry)) {
    if (SYSTEM_KEYS.has(key)) continue;
    payload[key] = value;
  }
  for (const [key, value] of Object.entries(fields)) {
    payload[key] = fromInputValue(entry[key], value);
  }
  return payload;
}
