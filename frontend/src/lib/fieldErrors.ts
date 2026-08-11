/**
 * Matching server validation errors to the fields a card renders.
 *
 * Lives in `lib` rather than beside `EntryFields` because both the field grid and the proposal
 * card's catch-all line must use the *same* rule — if they disagree, an error is either reported
 * twice or not at all.
 */

/**
 * Match a server error to a field, tolerating the model prefix Pydantic puts in front of it.
 *
 * `career_crud` builds each error's `field` by joining the whole Pydantic `loc` tuple, and the entry
 * schema is a discriminated union — so a bad `start_date` on a PROJECT arrives as
 * `"PROJECT.start_date"`, which never equals the client's `start_date` key. The effect was that the
 * card said "fix the highlighted fields" and then highlighted nothing, because the only errors it
 * could match were ones that happened to carry no prefix.
 *
 * Comparing the last segment fixes it without changing the API contract, and keeps the genuinely
 * unknown-field case working: an error naming something absent from the card still matches nothing
 * and is reported in full by the catch-all.
 */
export function fieldMatches(errorField: string, key: string): boolean {
  return errorField === key || errorField.split(".").at(-1) === key;
}

/** The schema's date fields all end `_date` and are Pydantic `date`, i.e. ISO `YYYY-MM-DD`. */
export function isDateField(key: string): boolean {
  return key.endsWith("_date");
}

/** The format shown as a hint and a placeholder, and the one the backend actually accepts. */
export const DATE_FORMAT_HINT = "YYYY-MM-DD";
