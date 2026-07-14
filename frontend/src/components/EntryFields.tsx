import type { FieldError } from "../lib/api";

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
    errors.filter((e) => e.field === key).map((e) => e.error);

  return (
    <div className="entry-fields">
      {Object.keys(fields).map((key) => (
        <label key={key}>
          <span className="field-name">{key.replaceAll("_", " ")}</span>
          {key === "content" ? (
            <textarea
              value={fields[key]}
              rows={3}
              disabled={disabled}
              onChange={(e) => setFields((f) => ({ ...f, [key]: e.target.value }))}
            />
          ) : (
            <input
              value={fields[key]}
              disabled={disabled}
              onChange={(e) => setFields((f) => ({ ...f, [key]: e.target.value }))}
            />
          )}
          {errorsFor(key).map((msg) => (
            <span key={msg} className="field-error">{msg}</span>
          ))}
        </label>
      ))}
    </div>
  );
}
