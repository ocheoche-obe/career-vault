/**
 * Voice capture — the `DictationProvider` seam and its Web Speech implementation (ADR-014).
 *
 * Two things are separated here on purpose, and the separation is the point of the module:
 *
 *  - **The contract** (`DictationProvider`) is what the composers talk to. It is deliberately small
 *    and says nothing about streaming, restarts, or vendor prefixes.
 *  - **The implementation** (`webSpeechProvider`) is where every Web Speech quirk is absorbed. None
 *    of them leak into the contract. ADR-014 amendment 2 records why that matters: the browser API
 *    is inconsistent *where it is supported*, not merely absent in Firefox, so the thing most likely
 *    to be replaced is exactly this file.
 *
 * `onInterim` is optional because that is what lets a second provider satisfy the same contract
 * (ADR-014 amendment 1). Web Speech streams partial results as you speak; a buffer-then-POST cloud
 * API returns one final transcript and simply never calls it. A *required* streaming callback would
 * force such a provider to fake partial results, which is how a seam stops being a seam.
 *
 * **This module never sends anything.** It produces text; the composer decides what to do with it.
 * Dictation filling the field but never POSTing is a decision (ADR-014 amendment 2), not an
 * accident of layering — an unreviewed transcript costs money and pollutes the corpus.
 *
 * Cost: **$0**. Recognition happens in the browser. Nothing here touches AWS.
 */

/** Why dictation stopped, when it stopped for a reason the user needs to know about. */
export type DictationErrorCode =
  | "permission-denied"
  | "no-microphone"
  | "network"
  | "unavailable"
  | "unknown";

export interface DictationCallbacks {
  /**
   * The complete final transcript since `start()` — not a delta.
   *
   * Emitting the whole thing is what makes this immune to the API re-firing a result that was
   * already final: the consumer replaces rather than appends, so a duplicate produces an identical
   * string instead of doubled text. A delta-based contract would push that bug into every consumer.
   */
  onTranscript(transcript: string): void;

  /**
   * Optional. The final transcript plus the not-yet-settled tail, for live feedback while speaking.
   *
   * A provider that cannot stream never calls this, and the consumer must still be correct — treat
   * it as a preview that may never arrive, never as the source of the committed text.
   */
  onInterim?(preview: string): void;

  /** Fatal problems only. Silence timeouts are handled internally and are not errors. */
  onError(code: DictationErrorCode): void;

  /** Fires exactly once per session, however the session ended. */
  onEnd(): void;
}

export interface DictationSession {
  /** Idempotent. Safe to call after the session has already ended. */
  stop(): void;
}

export interface DictationProvider {
  /** Checked at render time to decide whether a mic is offered at all. */
  readonly isSupported: boolean;
  start(callbacks: DictationCallbacks): DictationSession;
}

/*
 * `lib.dom` (TypeScript 6) types `SpeechRecognitionEvent`, `SpeechRecognitionErrorEvent` and the
 * `SpeechRecognitionErrorCode` union, but **not** the recognizer itself — presumably because it is
 * still vendor-prefixed in shipping browsers. So only the missing piece is declared here; the event
 * types are the built-in ones. Hand-rolling those too would risk drifting from the real shapes.
 */
interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  }
}

/**
 * Resolved lazily rather than at module load: the app decides whether to show a mic when it renders,
 * and a module-load snapshot would also make this untestable without module-registry games.
 */
export function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

/**
 * Join transcript fragments into readable text.
 *
 * Fragments arrive inconsistently spaced — Chrome commonly prefixes a leading space on results after
 * the first, Safari commonly does not — so concatenating raw produces either `"I shippedthe thing"`
 * or `"I shipped  the thing"` depending on the browser. Normalising here is cheaper than asking
 * every consumer to tidy up text it did not produce.
 */
export function joinTranscript(fragments: readonly string[]): string {
  return fragments
    .map((fragment) => fragment.trim())
    .filter((fragment) => fragment.length > 0)
    .join(" ");
}

/**
 * Map the API's error codes to the small set a user can act on.
 *
 * `no-speech` and `aborted` are absent deliberately and handled by the caller: the first is the
 * silence timeout (normal, triggers a restart) and the second is what `stop()` itself produces.
 * Surfacing either as an error would put "something went wrong" in front of a user who merely
 * paused, or who pressed the stop button.
 */
function toDictationError(code: SpeechRecognitionErrorCode): DictationErrorCode {
  switch (code) {
    case "not-allowed":
    case "service-not-allowed":
      return "permission-denied";
    case "audio-capture":
      return "no-microphone";
    case "network":
      return "network";
    case "language-not-supported":
    case "phrases-not-supported":
      return "unavailable";
    default:
      return "unknown";
  }
}

/**
 * How many times recognition may end *without producing any speech* before we give up.
 *
 * The restart loop exists because continuous mode stops on a silence timeout the page cannot
 * configure. That is fine when the user is thinking mid-sentence, and a hot loop when the microphone
 * is dead in a way that fires `end` without ever firing `error` — which is a real state, not a
 * hypothetical one. Three keeps a natural pause comfortable while bounding the failure.
 */
const MAX_SILENT_RESTARTS = 3;

export const webSpeechProvider: DictationProvider = {
  get isSupported(): boolean {
    return getSpeechRecognitionCtor() !== null;
  },

  start(callbacks: DictationCallbacks): DictationSession {
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) {
      // Defensive: the mic is not rendered when unsupported, so reaching here means a caller skipped
      // the check. Report and end rather than throwing — a composer must stay usable for typing.
      callbacks.onError("unavailable");
      callbacks.onEnd();
      return { stop: () => {} };
    }

    const recognition = new Ctor();
    recognition.continuous = true;
    recognition.interimResults = true;
    // Match the user's browser rather than hard-coding en-US: getting this wrong degrades accuracy
    // badly for accented and non-English speech, which is precisely the audience typing is worst for.
    recognition.lang = navigator.language || "en-US";

    /** Finals from *previous* recognition sessions. `results` resets when we restart after silence. */
    let committed = "";
    /** Finals from the current session, indexed by result index so a re-fired final overwrites. */
    let sessionFinals: string[] = [];
    let stopped = false;
    let fatal = false;
    let ended = false;
    let silentRestarts = 0;
    /**
     * The transcript as of the last time it actually grew.
     *
     * The give-up counter resets on *new speech*, not on "a transcript exists". Those look the same
     * until the user has said one word: after that, `committed` is non-empty for the rest of the
     * session, so a check like `if (settled)` is true on every subsequent event — and any stray
     * result from background noise would reset the counter and keep the microphone live
     * indefinitely. Comparing against the previous value is what makes the bound mean something.
     */
    let lastSettled = "";

    const finish = () => {
      if (ended) return;
      ended = true;
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      callbacks.onEnd();
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interimTail = "";

      // Iterate the whole list rather than from `event.resultIndex`. The spec says `resultIndex` is
      // the lowest changed index, but writing each final to its own slot is correct under either
      // reading and stays correct when a browser re-reports an index it already settled.
      for (let i = 0; i < event.results.length; i += 1) {
        const result = event.results[i];
        const text = result[0]?.transcript ?? "";
        if (result.isFinal) {
          sessionFinals[i] = text;
        } else {
          interimTail = interimTail ? `${interimTail} ${text.trim()}` : text.trim();
        }
      }

      const settled = joinTranscript([committed, ...sessionFinals]);
      if (settled !== lastSettled) {
        lastSettled = settled;
        silentRestarts = 0;
      }

      callbacks.onTranscript(settled);
      callbacks.onInterim?.(joinTranscript([settled, interimTail]));
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      // `aborted` is what our own `stop()` produces, and `no-speech` is the silence timeout. Neither
      // is a failure; both are followed by `end`, which is where they get handled.
      if (event.error === "aborted" || event.error === "no-speech") return;
      fatal = true;
      callbacks.onError(toDictationError(event.error));
    };

    recognition.onend = () => {
      if (stopped || fatal) {
        finish();
        return;
      }

      // A silence timeout, not a request to stop. Roll this session's finals into `committed` before
      // restarting, because the new session's `results` list starts empty.
      committed = joinTranscript([committed, ...sessionFinals]);
      sessionFinals = [];

      silentRestarts += 1;
      if (silentRestarts > MAX_SILENT_RESTARTS) {
        finish();
        return;
      }

      try {
        recognition.start();
      } catch {
        // Restart refused (commonly `InvalidStateError` when the previous session has not fully torn
        // down). Ending cleanly is better than retrying into the same wall — the user still has every
        // word captured so far, and can press the mic again.
        finish();
      }
    };

    try {
      recognition.start();
    } catch {
      callbacks.onError("unknown");
      finish();
      return { stop: () => {} };
    }

    return {
      stop() {
        if (stopped || ended) return;
        stopped = true;
        // `stop()`, not `abort()`: it lets the API settle any in-flight utterance into a final result
        // first, so the last thing said before pressing stop is not silently dropped.
        recognition.stop();
      },
    };
  },
};
