import type { FieldError } from "../lib/api";
import { DATE_FORMAT_HINT, fieldMatches, isDateField } from "../lib/fieldErrors";

/**
 * The generic field grid shared by the propose and edit flows. Renders one labelled input per
 * editable field (a textarea for `content`), with inline 422 errors from the server. Field
 * identity/typing is the server's job — this component only knows "string in, string out".
 */

export function EntryFields({
  fields,
  setFields,
  errors,
  disabled,
}: {
  fields: Record<string, string>;
  setFields: (updater: (prev: Record<string, string>) => Record<string, string>) => void;
  errors: FieldError[];
  disabled: boolean;
}) {
  const errorsFor = (key: string): string[] =>
    errors.filter((e) => fieldMatches(e.field, key)).map((e) => e.error);

  return (
    <div className="entry-fields">
      {Object.keys(fields).map((key) => {
        const fieldErrors = errorsFor(key);
        const invalid = fieldErrors.length > 0;
        const hintId = isDateField(key) ? `${key}-hint` : undefined;

        return (
          <label key={key} className={invalid ? "invalid" : undefined}>
            <span className="field-head">
              <span className="field-name">{key.replaceAll("_", " ")}</span>
              {/*
                The accepted format, stated up front rather than only after a rejection. Pydantic
                accepts ISO dates, so "August 3, 2026" fails with "invalid character in year" — a
                message that says what is wrong and never what would be right.
              */}
              {hintId && (
                <span className="field-hint" id={hintId}>
                  {DATE_FORMAT_HINT}
                </span>
              )}
            </span>
            {key === "content" ? (
              <textarea
                value={fields[key]}
                rows={3}
                disabled={disabled}
                aria-invalid={invalid || undefined}
                onChange={(e) => setFields((f) => ({ ...f, [key]: e.target.value }))}
              />
            ) : (
              <input
                value={fields[key]}
                disabled={disabled}
                aria-invalid={invalid || undefined}
                aria-describedby={hintId}
                placeholder={isDateField(key) ? DATE_FORMAT_HINT : undefined}
                onChange={(e) => setFields((f) => ({ ...f, [key]: e.target.value }))}
              />
            )}
            {fieldErrors.map((msg) => (
              <span key={msg} className="field-error">
                {msg}
              </span>
            ))}
          </label>
        );
      })}
    </div>
  );
}
