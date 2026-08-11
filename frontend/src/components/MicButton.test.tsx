import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { MicButton } from "./MicButton";
import type { DictationCallbacks, DictationProvider } from "../lib/dictation";

/**
 * A provider the test drives directly.
 *
 * The point of `DictationProvider` being an interface (ADR-014 amendment 1) is that a consumer can
 * be tested without a browser speech engine — so these tests exercise the real component against a
 * second implementation of the contract, which is also the closest thing to proof the seam works.
 */
function fakeProvider(supported = true) {
  let callbacks: DictationCallbacks | null = null;
  const stop = vi.fn();

  const provider: DictationProvider = {
    get isSupported() {
      return supported;
    },
    start(cb) {
      callbacks = cb;
      return { stop };
    },
  };

  return {
    provider,
    stop,
    get started() {
      return callbacks !== null;
    },
    transcript(text: string) {
      act(() => callbacks?.onTranscript(text));
    },
    interim(text: string) {
      act(() => callbacks?.onInterim?.(text));
    },
    fail(code: Parameters<DictationCallbacks["onError"]>[0]) {
      act(() => callbacks?.onError(code));
    },
    end() {
      act(() => callbacks?.onEnd());
    },
  };
}

/** A composer stand-in, so `value`/`onChange` round-trip the way the real ones do. */
function Harness({
  provider,
  initial = "",
  maxLength,
  onSubmit,
}: {
  provider: DictationProvider;
  initial?: string;
  maxLength?: number;
  onSubmit?: React.FormEventHandler<HTMLFormElement>;
}) {
  const [value, setValue] = useState(initial);
  return (
    <form onSubmit={onSubmit}>
      <label htmlFor="field">What did you accomplish?</label>
      <textarea id="field" value={value} onChange={(e) => setValue(e.target.value)} />
      <MicButton value={value} onChange={setValue} maxLength={maxLength} provider={provider} />
    </form>
  );
}

const field = () => screen.getByLabelText("What did you accomplish?");

describe("browser support", () => {
  it("renders nothing at all when dictation is unsupported", () => {
    const { provider } = fakeProvider(false);
    render(<Harness provider={provider} />);

    // Not a disabled button and not a tooltip (ADR-014 amendment 2): typing already works, so an
    // absent control is better than one that exists only to be refused.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText(/dictat/i)).not.toBeInTheDocument();
  });

  it("offers the control when the browser supports it", () => {
    const { provider } = fakeProvider();
    render(<Harness provider={provider} />);

    expect(screen.getByRole("button", { name: "Dictate your entry" })).toBeInTheDocument();
  });
});

describe("dictating", () => {
  it("puts the transcript in the field", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    fake.transcript("I shipped the résumé agent");

    expect(field()).toHaveValue("I shipped the résumé agent");
  });

  it("never submits the form", async () => {
    const fake = fakeProvider();
    const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
    render(<Harness provider={fake.provider} onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    fake.transcript("promoted to staff engineer");
    fake.end();

    // The decision in ADR-014 amendment 2, asserted rather than inspected: dictation fills the
    // field and the user submits deliberately. A `<button>` defaulting to type="submit" inside a
    // form is exactly how this would regress.
    expect(onSubmit).not.toHaveBeenCalled();
    expect(field()).toHaveValue("promoted to staff engineer");
  });

  it("appends to text the user already typed", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} initial="I shipped" />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    fake.transcript("the parser rewrite");

    expect(field()).toHaveValue("I shipped the parser rewrite");
  });

  it("replaces the preview rather than accumulating it", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    fake.interim("I led");
    fake.interim("I led the");
    fake.interim("I led the migration");
    fake.transcript("I led the migration");

    // Each emission is the whole transcript, so composing from a fixed base is what keeps this from
    // becoming "I led I led the I led the migration".
    expect(field()).toHaveValue("I led the migration");
  });

  it("starts from the current text on a second dictation, not the original", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    fake.transcript("First sentence.");
    await userEvent.click(screen.getByRole("button", { name: "Stop dictation" }));

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    fake.transcript("Second sentence.");

    expect(field()).toHaveValue("First sentence. Second sentence.");
  });

  it("respects the composer's character cap", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} maxLength={10} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    fake.transcript("a transcript far longer than the cap");

    // The cap mirrors the backend's; letting speech overrun it would trade a caught-here problem
    // for a 4xx the user cannot explain.
    expect(field()).toHaveValue("a transcri");
  });
});

describe("recording state", () => {
  it("toggles the button between start and stop", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} />);

    const button = screen.getByRole("button", { name: "Dictate your entry" });
    expect(button).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(button);

    expect(screen.getByRole("button", { name: "Stop dictation" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("announces that the microphone is live", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));

    // A colour change alone tells a screen-reader user nothing about whether the mic is on — the
    // one piece of state a voice feature must never leave ambiguous.
    expect(screen.getByRole("status")).toHaveTextContent(/listening/i);
  });

  it("discloses that audio leaves the device, while it is leaving", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));

    // Web Speech is not on-device in Chrome or Safari (ADR-014 correction). The user is holding a
    // corpus of employers and project detail; an undisclosed third-party data flow is the defect,
    // and the honest place to say so is the moment the microphone is live.
    expect(screen.getByRole("status")).toHaveTextContent(/sent to your browser's speech service/i);
  });

  it("does not show the disclosure when nothing is being captured", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} />);

    expect(screen.queryByText(/speech service/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    fake.end();

    expect(screen.queryByText(/speech service/i)).not.toBeInTheDocument();
  });

  it("stops the session when the user presses stop", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    await userEvent.click(screen.getByRole("button", { name: "Stop dictation" }));

    expect(fake.stop).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Dictate your entry" })).toBeInTheDocument();
  });

  it("returns to idle when the session ends on its own", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    fake.end();

    // Web Speech gives up after repeated silence. The button must follow, or it claims to be
    // recording when nothing is listening.
    expect(screen.getByRole("button", { name: "Dictate your entry" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("stops listening when the composer unmounts", async () => {
    const fake = fakeProvider();
    const { unmount } = render(<Harness provider={fake.provider} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    unmount();

    // A recognizer left running after the view is gone is a privacy problem, not just a leak.
    expect(fake.stop).toHaveBeenCalled();
  });
});

describe("failures", () => {
  it("explains a blocked microphone and keeps typing available", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    fake.fail("permission-denied");
    fake.end();

    expect(screen.getByRole("status")).toHaveTextContent(/microphone access is blocked/i);
    await userEvent.type(field(), "typed instead");
    expect(field()).toHaveValue("typed instead");
  });

  it.each([
    ["no-microphone", /no microphone found/i],
    ["network", /needs a connection/i],
    ["unavailable", /isn't available in this browser/i],
    ["unknown", /stopped unexpectedly/i],
  ] as const)("reports %s", async (code, expected) => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    fake.fail(code);

    expect(screen.getByRole("status")).toHaveTextContent(expected);
  });

  it("clears a stale error when dictation is retried", async () => {
    const fake = fakeProvider();
    render(<Harness provider={fake.provider} />);

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));
    fake.fail("permission-denied");
    fake.end();

    await userEvent.click(screen.getByRole("button", { name: "Dictate your entry" }));

    // A permission the user has since granted should not leave the old complaint on screen.
    expect(screen.getByRole("status")).not.toHaveTextContent(/blocked/i);
  });
});
