import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Upload } from "./Upload";
import { stubFetch } from "../test/http";

/**
 * Import (v1.1 slice 2) — specifically audit §A9.
 *
 * The file input previously had no accessible name at all: a screen reader announced "button" with
 * nothing to say what it was for. That is invisible to every other check, which is why it survived
 * from slice 5 to here, and why it is worth a test rather than a comment.
 */

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("accessibility (audit §A9)", () => {
  it("the file input has an accessible name", () => {
    stubFetch({ status: 200, body: {} });
    render(<Upload idToken="tok" />);

    const input = screen.getByLabelText(/drop a pdf or docx here/i);
    expect(input).toHaveAttribute("type", "file");
  });

  it("the input stays focusable — hidden by clipping, not by display:none", () => {
    stubFetch({ status: 200, body: {} });
    const { container } = render(<Upload idToken="tok" />);

    const input = container.querySelector('input[type="file"]');
    expect(input).not.toBeNull();
    // `display: none` or `hidden` would remove it from the tab order and from the a11y tree
    // entirely, trading one barrier for another.
    expect(input).not.toHaveAttribute("hidden");
    expect(input?.className).toContain("sr-only");
  });

  it("accepts only the formats the parser supports", () => {
    stubFetch({ status: 200, body: {} });
    render(<Upload idToken="tok" />);

    expect(screen.getByLabelText(/drop a pdf or docx here/i)).toHaveAttribute("accept", ".pdf,.docx");
  });
});

describe("rejections happen before any upload", () => {
  it("refuses a non-PDF/DOCX without calling the server", async () => {
    const calls = stubFetch({ status: 200, body: {} });
    render(<Upload idToken="tok" />);

    const input = screen.getByLabelText(/drop a pdf or docx here/i) as HTMLInputElement;
    const file = new File(["x"], "notes.txt", { type: "text/plain" });
    Object.defineProperty(input, "files", { value: [file] });
    input.dispatchEvent(new Event("change", { bubbles: true }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/pdf or docx/i);
    expect(calls).toHaveLength(0);
  });
});
