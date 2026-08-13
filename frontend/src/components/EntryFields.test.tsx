import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EntryFields } from "./EntryFields";
import { fieldMatches } from "../lib/fieldErrors";

/**
 * The field grid's job beyond rendering inputs: say what format a value must take *before* it is
 * rejected, and mark the field an error names. Both were missing — surfaced by Oche typing
 * "August 3, 2026" into a date field and getting a rejection that named neither the format nor,
 * visibly, the field.
 */

function renderFields(fields: Record<string, string>, errors: { field: string; error: string }[] = []) {
  render(<EntryFields fields={fields} setFields={vi.fn()} errors={errors} disabled={false} />);
}

describe("fieldMatches", () => {
  it("matches a bare field name", () => {
    expect(fieldMatches("start_date", "start_date")).toBe(true);
  });

  it("matches through the discriminated-union model prefix Pydantic emits", () => {
    expect(fieldMatches("PROJECT.start_date", "start_date")).toBe(true);
    expect(fieldMatches("CERT.issued_date", "issued_date")).toBe(true);
  });

  it("does not match a different field that merely shares a prefix", () => {
    expect(fieldMatches("PROJECT.start_date", "end_date")).toBe(false);
    expect(fieldMatches("PROJECT.start_date", "PROJECT")).toBe(false);
  });
});

describe("format hints", () => {
  it("states the accepted date format up front", () => {
    renderFields({ title: "XRM", start_date: "" });

    // Pydantic accepts ISO dates only, and its rejection ("invalid character in year") says what is
    // wrong without ever saying what would be right.
    expect(screen.getByText("YYYY-MM-DD")).toBeInTheDocument();
    expect(screen.getByLabelText(/start date/i)).toHaveAttribute("placeholder", "YYYY-MM-DD");
  });

  it("ties the hint to the input for assistive tech", () => {
    renderFields({ start_date: "" });

    expect(screen.getByLabelText(/start date/i)).toHaveAttribute("aria-describedby", "start_date-hint");
  });

  it("does not put a date hint on fields that are not dates", () => {
    renderFields({ title: "XRM", issuer: "KPMG" });

    expect(screen.queryByText("YYYY-MM-DD")).not.toBeInTheDocument();
  });
});

describe("highlighting", () => {
  it("marks the field a prefixed error names", () => {
    renderFields({ title: "XRM", start_date: "August 3, 2026" }, [
      { field: "PROJECT.start_date", error: "Input should be a valid date" },
    ]);

    expect(screen.getByLabelText(/start date/i)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText(/title/i)).not.toHaveAttribute("aria-invalid");
  });

  it("shows the error inline against its own field", () => {
    renderFields({ start_date: "August 3, 2026" }, [
      { field: "PROJECT.start_date", error: "Input should be a valid date" },
    ]);

    expect(screen.getByText("Input should be a valid date")).toBeInTheDocument();
  });

  it("leaves every field unmarked when there are no errors", () => {
    renderFields({ title: "XRM", start_date: "2026-08-03" });

    // `aria-invalid="false"` would announce "not invalid" on every field of a clean form, so the
    // attribute is omitted entirely rather than set to false.
    expect(screen.getByLabelText(/start date/i)).not.toHaveAttribute("aria-invalid");
  });
});

describe("regression guards", () => {
  it("renders content as a textarea and everything else as an input", () => {
    renderFields({ title: "XRM", content: "Built the review matcher." });

    expect(screen.getByLabelText(/content/i).tagName).toBe("TEXTAREA");
    expect(screen.getByLabelText(/title/i).tagName).toBe("INPUT");
  });

  it("keeps rendering when a field is disabled", () => {
    render(<EntryFields fields={{ title: "XRM" }} setFields={vi.fn()} errors={[]} disabled />);

    expect(screen.getByLabelText(/title/i)).toBeDisabled();
  });
});
