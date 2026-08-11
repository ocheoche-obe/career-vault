import { useCallback, useEffect, useRef, useState } from "react";
import {
  joinTranscript,
  webSpeechProvider,
  type DictationErrorCode,
  type DictationProvider,
  type DictationSession,
} from "../lib/dictation";
import "./mic-button.css";

/**
 * The dictation control, shared by both composers (ADR-014 amendment 2).
 *
 * Three behaviours here are decisions rather than implementation detail:
 *
 *  1. **Unsupported browsers get no button at all.** Typing already works and is the default path,
 *     so a hidden control leaves no broken affordance and nothing to explain. ADR-014 records weak
 *     Firefox support as the known case; this is the fallback that makes it a non-event.
 *  2. **Dictation writes to the field and never submits.** This component has no access to a submit
 *     handler, which is the structural version of that guarantee — it cannot send even by mistake.
 *     An unreviewed transcript costs ~$0.006 and puts garbled text in the corpus.
 *  3. **A denied microphone is reported and then forgotten.** The error clears the moment dictation
 *     is retried, because a permission a user has since granted should not leave a stale complaint
 *     on screen.
 */

const ERROR_TEXT: Record<DictationErrorCode, string> = {
  "permission-denied": "Microphone access is blocked. Check your browser's site settings — you can still type.",
  "no-microphone": "No microphone found. You can still type.",
  network: "Dictation needs a connection right now. You can still type.",
  unavailable: "Dictation isn't available in this browser. You can still type.",
  unknown: "Dictation stopped unexpectedly. You can still type.",
};

export interface MicButtonProps {
  /** The composer's current text. Captured when dictation starts, so speech appends to it. */
  value: string;
  /** Called with the full composed text — existing content plus what has been said so far. */
  onChange: (next: string) => void;
  /** Cap mirrored from the composer, so dictation cannot overrun what the field would accept. */
  maxLength?: number;
  disabled?: boolean;
  /** Injectable for tests; production always uses Web Speech (ADR-014). */
  provider?: DictationProvider;
}

export function MicButton({
  value,
  onChange,
  maxLength,
  disabled = false,
  provider = webSpeechProvider,
}: MicButtonProps) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<DictationErrorCode | null>(null);
  const sessionRef = useRef<DictationSession | null>(null);

  /**
   * The composer's text at the moment dictation started.
   *
   * Held in a ref, not state: every transcript recomposes from this base, so it must be the value
   * from *before* speech began. Reading `value` inside the callbacks would feed the component its
   * own output and append each transcript to the last one.
   */
  const baseRef = useRef("");

  /** Latest `onChange`, so the dictation callbacks never close over a stale render's prop. */
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  // Stop the microphone if the composer unmounts mid-sentence. Without this the recognizer keeps
  // listening after the view is gone, which is both a privacy problem and a battery one.
  useEffect(() => {
    return () => sessionRef.current?.stop();
  }, []);

  const compose = useCallback(
    (transcript: string) => {
      const composed = joinTranscript([baseRef.current, transcript]);
      onChangeRef.current(maxLength ? composed.slice(0, maxLength) : composed);
    },
    [maxLength],
  );

  const start = useCallback(() => {
    setError(null);
    baseRef.current = value;
    setRecording(true);

    sessionRef.current = provider.start({
      onTranscript: compose,
      // Interim results go to the field too, so the user watches words appear as they speak rather
      // than facing a box that stays empty until they stop. The committed transcript always wins:
      // it is re-emitted after the preview, so unsettled text is replaced rather than kept.
      onInterim: compose,
      onError: (code) => setError(code),
      onEnd: () => {
        setRecording(false);
        sessionRef.current = null;
      },
    });
  }, [compose, provider, value]);

  const stop = useCallback(() => {
    sessionRef.current?.stop();
    sessionRef.current = null;
    setRecording(false);
  }, []);

  // Feature detection at render, per ADR-014 amendment 2. Nothing renders — not a disabled button,
  // not a tooltip — when the browser cannot do this.
  if (!provider.isSupported) return null;

  /*
   * One wrapper, so the control is a single flex item wherever it is dropped. Both composers lay
   * their row out with flex — Log's is a bordered pill — and a bare status paragraph would become a
   * sibling flex item inside that row, stretching it and, on Log, rendering inside the pill's
   * border. The message is taken out of flow in CSS instead, so it can never disturb either layout.
   */
  return (
    <span className="mic">
      <button
        type="button"
        className={`mic-button${recording ? " recording" : ""}`}
        onClick={recording ? stop : start}
        disabled={disabled}
        aria-pressed={recording}
        aria-label={recording ? "Stop dictation" : "Dictate your entry"}
      >
        {/*
          A drawn microphone rather than a text glyph. `●` read as a disabled status dot when this
          was first put on screen — the control has to *look* like the thing it does, since the
          accessible name is only available to users who are not looking at it.
        */}
        {recording ? (
          <svg className="mic-glyph" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <rect x="6" y="6" width="12" height="12" rx="2.5" fill="currentColor" />
          </svg>
        ) : (
          <svg
            className="mic-glyph"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            focusable="false"
          >
            <rect x="9" y="2" width="6" height="11" rx="3" />
            <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
            <path d="M12 18v3" />
          </svg>
        )}
      </button>

      {/*
        Announced, not merely drawn. A recording indicator that is only a colour change tells a
        screen-reader user nothing about whether the microphone is live — which is the one piece of
        state a voice feature must never leave ambiguous.
      */}
      <span className="mic-status" role="status">
        {error ? (
          ERROR_TEXT[error]
        ) : recording ? (
          <>
            Listening — speak, then press stop to review.
            {/*
              Where the audio goes, said while it is going there.
              Web Speech is *not* on-device in Chrome or Safari: audio is streamed to the browser
              vendor's speech service. ADR-014 chose this API on cost grounds and described it as
              "browser-side", which is true of the API and not of the processing — so a user could
              reasonably assume their speech never leaves the machine. It does, and for a corpus of
              employer names and project detail that is worth one sentence at the moment it matters.
            */}
            <span className="mic-note">
              Audio is sent to your browser's speech service for transcription.
            </span>
          </>
        ) : (
          ""
        )}
      </span>
    </span>
  );
}
