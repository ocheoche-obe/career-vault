import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getSpeechRecognitionCtor,
  joinTranscript,
  webSpeechProvider,
  type DictationCallbacks,
} from "./dictation";

/**
 * A stand-in for the browser's recognizer.
 *
 * Deliberately a real object with real state rather than a bag of `vi.fn()`s: every test below turns
 * on *sequences* — a final arriving twice, an end that means "silence" versus one that means
 * "stopped" — and a mock that forgets what it was told cannot distinguish those. `stop()` fires
 * `end` synchronously because that is what the API does, and the ordering is exactly what the
 * restart logic keys off.
 */
class FakeRecognition {
  continuous = false;
  interimResults = false;
  lang = "";
  onresult: ((event: SpeechRecognitionEvent) => void) | null = null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null = null;
  onend: (() => void) | null = null;

  startCount = 0;
  stopCount = 0;
  /** Set by a test to make `start()` throw, modelling a refused restart. */
  failNextStart = false;

  static last: FakeRecognition | null = null;

  constructor() {
    FakeRecognition.last = this;
  }

  start(): void {
    if (this.failNextStart) throw new Error("InvalidStateError");
    this.startCount += 1;
  }

  stop(): void {
    this.stopCount += 1;
    this.onend?.();
  }

  abort(): void {}

  /** Drive a `result` event. Each entry becomes one `SpeechRecognitionResult`. */
  emit(entries: { text: string; isFinal: boolean }[], resultIndex = 0): void {
    const results = entries.map((entry) =>
      Object.assign([{ transcript: entry.text, confidence: 1 }], { isFinal: entry.isFinal }),
    );
    this.onresult?.({
      resultIndex,
      results: Object.assign(results, { item: (i: number) => results[i] }),
    } as unknown as SpeechRecognitionEvent);
  }

  fail(error: SpeechRecognitionErrorCode): void {
    this.onerror?.({ error } as SpeechRecognitionErrorEvent);
  }

  /** An `end` the app did not ask for — the silence timeout. */
  timeout(): void {
    this.onend?.();
  }
}

function install(): typeof FakeRecognition {
  FakeRecognition.last = null;
  window.SpeechRecognition = FakeRecognition as unknown as typeof window.SpeechRecognition;
  return FakeRecognition;
}

function current(): FakeRecognition {
  const instance = FakeRecognition.last;
  if (!instance) throw new Error("no recognizer was constructed");
  return instance;
}

/** Callback set with everything spied, so each test asserts on the parts it cares about. */
function spyCallbacks(): DictationCallbacks & {
  onTranscript: ReturnType<typeof vi.fn>;
  onInterim: ReturnType<typeof vi.fn>;
  onError: ReturnType<typeof vi.fn>;
  onEnd: ReturnType<typeof vi.fn>;
} {
  return {
    onTranscript: vi.fn<(transcript: string) => void>(),
    onInterim: vi.fn<(preview: string) => void>(),
    onError: vi.fn<(code: string) => void>(),
    onEnd: vi.fn<() => void>(),
  };
}

/** The last string handed to a spy — the transcript "as it now stands". */
function latest(spy: ReturnType<typeof vi.fn>): string | undefined {
  const call = spy.mock.calls.at(-1);
  return call?.[0] as string | undefined;
}

afterEach(() => {
  delete window.SpeechRecognition;
  delete window.webkitSpeechRecognition;
});

describe("joinTranscript", () => {
  it("normalises the inconsistent spacing browsers attach to fragments", () => {
    // Chrome commonly leads with a space on later fragments; Safari commonly does not. Raw
    // concatenation therefore produces either doubled spaces or none, depending on the browser.
    expect(joinTranscript(["I shipped", " the thing"])).toBe("I shipped the thing");
    expect(joinTranscript(["I shipped", "the thing"])).toBe("I shipped the thing");
  });

  it("drops empty fragments rather than emitting the gaps as spaces", () => {
    expect(joinTranscript(["", "hello", "   ", "world"])).toBe("hello world");
    expect(joinTranscript([])).toBe("");
  });
});

describe("feature detection", () => {
  it("reports unsupported when the browser exposes no recognizer", () => {
    expect(getSpeechRecognitionCtor()).toBeNull();
    expect(webSpeechProvider.isSupported).toBe(false);
  });

  it("accepts the webkit-prefixed constructor, which is what Safari ships", () => {
    window.webkitSpeechRecognition =
      FakeRecognition as unknown as typeof window.webkitSpeechRecognition;
    expect(webSpeechProvider.isSupported).toBe(true);
  });

  it("re-reads the global, so support is not frozen at module load", () => {
    expect(webSpeechProvider.isSupported).toBe(false);
    install();
    expect(webSpeechProvider.isSupported).toBe(true);
  });
});

describe("transcription", () => {
  it("configures continuous recognition with interim results", () => {
    install();
    webSpeechProvider.start(spyCallbacks());
    // Without `continuous` the API stops at the first pause, which defeats dictating a paragraph.
    expect(current().continuous).toBe(true);
    expect(current().interimResults).toBe(true);
  });

  it("emits the whole transcript so far, not the delta", () => {
    install();
    const callbacks = spyCallbacks();
    webSpeechProvider.start(callbacks);

    current().emit([{ text: "I shipped the parser", isFinal: true }]);
    current().emit([
      { text: "I shipped the parser", isFinal: true },
      { text: "and it went live", isFinal: true },
    ]);

    expect(latest(callbacks.onTranscript)).toBe("I shipped the parser and it went live");
  });

  it("does not double text when a settled result is reported again", () => {
    install();
    const callbacks = spyCallbacks();
    webSpeechProvider.start(callbacks);

    // The same final, re-fired at the same index — a documented Web Speech quirk and the reason the
    // contract emits a full transcript rather than deltas.
    current().emit([{ text: "promoted to senior", isFinal: true }]);
    current().emit([{ text: "promoted to senior", isFinal: true }]);

    expect(latest(callbacks.onTranscript)).toBe("promoted to senior");
  });

  it("keeps interim text out of the committed transcript", () => {
    install();
    const callbacks = spyCallbacks();
    webSpeechProvider.start(callbacks);

    current().emit([
      { text: "I passed", isFinal: true },
      { text: "the exam", isFinal: false },
    ]);

    // The committed transcript is what reaches the composer; the preview is only ever a preview.
    expect(latest(callbacks.onTranscript)).toBe("I passed");
    expect(latest(callbacks.onInterim)).toBe("I passed the exam");
  });

  it("works when the consumer supplies no onInterim", () => {
    install();
    const callbacks: DictationCallbacks = {
      onTranscript: vi.fn<(transcript: string) => void>(),
      onError: vi.fn<(code: string) => void>(),
      onEnd: vi.fn<() => void>(),
    };
    webSpeechProvider.start(callbacks);

    // The whole point of `onInterim` being optional (ADR-014 amendment 1): a provider or a consumer
    // that ignores streaming must not crash the one that does not.
    expect(() => current().emit([{ text: "hello", isFinal: false }])).not.toThrow();
    expect(callbacks.onTranscript).toHaveBeenCalledWith("");
  });
});

describe("the silence timeout", () => {
  it("restarts and carries the transcript across the restart", () => {
    install();
    const callbacks = spyCallbacks();
    webSpeechProvider.start(callbacks);

    current().emit([{ text: "I led the migration", isFinal: true }]);
    current().timeout();

    // A restart, not an end: the user paused mid-thought.
    expect(current().startCount).toBe(2);
    expect(callbacks.onEnd).not.toHaveBeenCalled();

    // The new session's results list starts empty, so anything already said must have been banked.
    current().emit([{ text: "over two quarters", isFinal: true }]);
    expect(latest(callbacks.onTranscript)).toBe("I led the migration over two quarters");
  });

  it("gives up after repeated restarts that capture nothing", () => {
    install();
    const callbacks = spyCallbacks();
    webSpeechProvider.start(callbacks);

    // Models a microphone that is dead in a way that fires `end` but never `error` — without the
    // bound this is a hot loop that restarts recognition forever.
    for (let i = 0; i < 6; i += 1) current().timeout();

    expect(callbacks.onEnd).toHaveBeenCalledTimes(1);
    expect(current().startCount).toBeLessThanOrEqual(4);
  });

  it("resets the give-up counter when speech is actually captured", () => {
    install();
    const callbacks = spyCallbacks();
    webSpeechProvider.start(callbacks);

    // Two long pauses, then speech, then two more. A counter that never reset would end the session
    // on a user who simply thinks between sentences.
    current().timeout();
    current().timeout();
    current().emit([{ text: "I mentored two engineers", isFinal: true }]);
    current().timeout();
    current().timeout();

    expect(callbacks.onEnd).not.toHaveBeenCalled();
  });

  it("ends cleanly when the browser refuses the restart", () => {
    install();
    const callbacks = spyCallbacks();
    webSpeechProvider.start(callbacks);

    current().emit([{ text: "shipped it", isFinal: true }]);
    current().failNextStart = true;
    current().timeout();

    // Retrying into the same wall would spin; the user keeps every word and can press the mic again.
    expect(callbacks.onEnd).toHaveBeenCalledTimes(1);
    expect(callbacks.onError).not.toHaveBeenCalled();
  });
});

describe("stopping", () => {
  it("ends the session exactly once", () => {
    install();
    const callbacks = spyCallbacks();
    const session = webSpeechProvider.start(callbacks);

    session.stop();

    expect(current().stopCount).toBe(1);
    expect(callbacks.onEnd).toHaveBeenCalledTimes(1);
  });

  it("is idempotent", () => {
    install();
    const callbacks = spyCallbacks();
    const session = webSpeechProvider.start(callbacks);

    session.stop();
    session.stop();
    session.stop();

    expect(callbacks.onEnd).toHaveBeenCalledTimes(1);
    expect(current().stopCount).toBe(1);
  });

  it("does not call into a recognizer whose session already ended", () => {
    install();
    const callbacks = spyCallbacks();
    const session = webSpeechProvider.start(callbacks);

    current().fail("not-allowed");
    current().timeout();
    session.stop();

    // A React component stopping dictation on unmount, after a fatal error already ended it. The
    // real API throws `InvalidStateError` when stopped twice, so the session must remember it is
    // over rather than forwarding the call.
    expect(current().stopCount).toBe(0);
    expect(callbacks.onEnd).toHaveBeenCalledTimes(1);
  });

  it("ignores results and ends that arrive after the session is over", () => {
    install();
    const callbacks = spyCallbacks();
    const session = webSpeechProvider.start(callbacks);

    current().emit([{ text: "I ran the workshop", isFinal: true }]);
    session.stop();
    callbacks.onTranscript.mockClear();

    // A final result landing after `end` is a real Web Speech quirk. It must not reach the composer:
    // the user has stopped dictating and may already be editing the text.
    current().emit([{ text: "stray tail", isFinal: true }]);
    current().timeout();

    expect(callbacks.onTranscript).not.toHaveBeenCalled();
    expect(callbacks.onEnd).toHaveBeenCalledTimes(1);
  });

  it("does not restart after the user stops", () => {
    install();
    const callbacks = spyCallbacks();
    const session = webSpeechProvider.start(callbacks);

    session.stop();

    // One `start`, from the initial call. A restart here would leave the microphone live after the
    // user asked for it to be off — the worst available bug in a voice feature.
    expect(current().startCount).toBe(1);
  });
});

describe("errors", () => {
  it("reports a denied microphone and does not restart", () => {
    install();
    const callbacks = spyCallbacks();
    webSpeechProvider.start(callbacks);

    current().fail("not-allowed");
    current().timeout();

    expect(callbacks.onError).toHaveBeenCalledWith("permission-denied");
    expect(callbacks.onEnd).toHaveBeenCalledTimes(1);
    expect(current().startCount).toBe(1);
  });

  it.each([
    ["service-not-allowed", "permission-denied"],
    ["audio-capture", "no-microphone"],
    ["network", "network"],
    ["language-not-supported", "unavailable"],
    ["bad-grammar", "unknown"],
  ])("maps %s to %s", (raw, expected) => {
    install();
    const callbacks = spyCallbacks();
    webSpeechProvider.start(callbacks);

    current().fail(raw as SpeechRecognitionErrorCode);

    expect(callbacks.onError).toHaveBeenCalledWith(expected);
  });

  it.each(["no-speech", "aborted"])("treats %s as normal, not as a failure", (raw) => {
    install();
    const callbacks = spyCallbacks();
    webSpeechProvider.start(callbacks);

    current().fail(raw as SpeechRecognitionErrorCode);

    // `no-speech` is the silence timeout and `aborted` is what our own stop produces. Surfacing
    // either would put an error in front of a user who merely paused, or who pressed stop.
    expect(callbacks.onError).not.toHaveBeenCalled();
  });

  it("survives a recognizer that refuses to start at all", () => {
    install();
    const callbacks = spyCallbacks();
    FakeRecognition.prototype.start = function start() {
      throw new Error("InvalidStateError");
    };

    const session = webSpeechProvider.start(callbacks);

    expect(callbacks.onError).toHaveBeenCalledWith("unknown");
    expect(callbacks.onEnd).toHaveBeenCalledTimes(1);
    expect(() => session.stop()).not.toThrow();

    FakeRecognition.prototype.start = function start(this: FakeRecognition) {
      if (this.failNextStart) throw new Error("InvalidStateError");
      this.startCount += 1;
    };
  });

  it("reports unavailable rather than throwing when started without support", () => {
    const callbacks = spyCallbacks();

    // Defensive path: the mic is not rendered when unsupported, so this means a caller skipped the
    // check. A composer must stay usable for typing regardless.
    const session = webSpeechProvider.start(callbacks);

    expect(callbacks.onError).toHaveBeenCalledWith("unavailable");
    expect(callbacks.onEnd).toHaveBeenCalledTimes(1);
    expect(() => session.stop()).not.toThrow();
  });
});
