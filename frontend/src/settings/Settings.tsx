import { useEffect, useState } from "react";
import {
  CHECKIN_CADENCES,
  getSettings,
  putSettings,
  type CheckinCadence,
  type Entry,
  type FieldError,
  type Profile,
} from "../lib/api";
import "./settings.css";

/**
 * Details — the identity that goes on a generated résumé (backlog B-008), check-in preferences
 * (FR-4.6, slice 8), and data control. Rebuilt for the v1.1 redesign.
 *
 * This view exists because of a concrete failure: résumés rendered the literal word "Résumé" where a
 * name should be. The chain was that `resume.html.j2` reads `contact.name or contact.email`, the
 * PROFILE item had neither field, and no PROFILE item existed at all — because nothing in the app
 * could write one. Cognito could not fill the gap either: the user pool holds only `email`,
 * `email_verified` and `sub`, with no name attribute anywhere.
 *
 * `email` is intentionally read-only. It comes from the Cognito JWT on every write, so the identity
 * printed on a résumé traces back to an authenticated claim rather than to a form field. The backend
 * rejects an `email` in the body outright rather than ignoring it.
 *
 * Three designed controls are **absent rather than faked**, per the B-015 precedent:
 *
 *   - "Warn me before the streak breaks" (**B-033**) — no settings field and no second scheduled
 *     send exist. Shipping the switch alone was considered and rejected: a toggle that persists but
 *     sends nothing is fabricated functionality.
 *   - "Delete account" (**B-034**) — a real destructive flow across Cognito, DynamoDB and S3.
 *   - The cadence copy is rewritten. The handoff says "a prompt every Friday"; the scheduler is not
 *     day-anchored at all — `CADENCE_DAYS` paces sends N days from the last one (7/14/30/91), via a
 *     daily run. Describing a weekday the system does not honour would be a promise the backend
 *     cannot keep.
 */

/** Mirrors `CADENCE_DAYS` in the backend's `profile.py` — the interval each option actually means. */
const CADENCE_COPY: Record<CheckinCadence, { label: string; description: string }> = {
  weekly: { label: "Weekly", description: "Every 7 days. Best for a fast-moving role." },
  biweekly: { label: "Biweekly", description: "Every 14 days. Enough to stay honest." },
  monthly: { label: "Monthly", description: "Every 30 days. Lightest touch." },
  quarterly: { label: "Quarterly", description: "Every 91 days. A periodic sweep." },
};

/** Render a stored UTC timestamp in the reader's own zone, or null if it isn't usable. */
function formatWhen(value: string | null | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? null
    : parsed.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}

/**
 * Describe the next send.
 *
 * `next_checkin_at` is written *only* by the check-in run, never by this form — it is server-owned
 * scheduling state, so the API rejects it in a request body. That means it is legitimately absent
 * until the first check-in goes out, and an earlier version of this component rendered that as
 * "Next check-in: —" immediately after a save. Technically accurate, and it reads exactly like the
 * save silently failed. Say what absent actually means instead.
 */
function nextCheckinLabel(next: string | null | undefined): string {
  const when = formatWhen(next);
  return when ? `Next check-in: ${when}` : "Next check-in: with the next daily run";
}

/**
 * A switch whose *visible* text is its accessible name.
 *
 * Deliberately not an `aria-label` duplicating the words next to it: that leaves the announced name
 * and the rendered name as two strings maintained independently, and it shrinks the hit target to
 * the 42px track. `aria-labelledby`/`aria-describedby` point at the real elements, so clicking the
 * label toggles the control and the sub-line (the only place the destination address and cadence
 * are stated) is announced with it.
 */
function Switch({
  checked,
  labelId,
  describedById,
  onChange,
}: {
  checked: boolean;
  labelId: string;
  describedById?: string;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-labelledby={labelId}
      aria-describedby={describedById}
      className="switch"
      onClick={() => onChange(!checked)}
    >
      <span className="knob" aria-hidden="true" />
    </button>
  );
}

/**
 * The cadence picker's keyboard contract.
 *
 * A `role="radiogroup"` of `role="radio"` buttons must behave like the native `<select>` it
 * replaced, and buttons give none of that for free: without this the group put four stops in the tab
 * order instead of one and Arrow/Home/End did nothing — a net accessibility regression in the slice
 * whose purpose is closing accessibility findings. Roving tabindex plus arrow-key selection is the
 * WAI-ARIA radiogroup pattern.
 */
function useRovingRadio<T extends string>(options: readonly T[], value: T, onChange: (v: T) => void) {
  return (event: React.KeyboardEvent) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
    const index = options.indexOf(value);

    let next: T | undefined;
    if (step) next = options[(index + step + options.length) % options.length];
    else if (event.key === "Home") next = options[0];
    else if (event.key === "End") next = options[options.length - 1];
    if (!next) return;

    event.preventDefault();
    onChange(next);
    // Selection follows focus in this pattern, so focus has to move with it.
    const group = (event.currentTarget as HTMLElement).closest('[role="radiogroup"]');
    group?.querySelectorAll<HTMLElement>('[role="radio"]')[options.indexOf(next)]?.focus();
  };
}

export function Settings({
  idToken,
  entries,
  onSaved,
}: {
  idToken: string;
  entries?: Entry[] | null;
  /**
   * Fired after a successful save so the shell re-reads the profile.
   *
   * Without it the cadence chosen here never reached App's `cadence` state, so the header streak
   * pill, Home's aggregates and the Log's "Weekly check-in" title all kept computing against the
   * old cadence until a full page reload — the same staleness the entry-writing views fixed with
   * `onEntrySaved`/`onImported`/`onChanged`, with the settings half missed.
   */
  onSaved?: () => void;
}) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [phone, setPhone] = useState("");
  const [goal, setGoal] = useState("");
  // Absent settings mean the defaults, not an error: no PROFILE written before slice 8 has them.
  const [cadence, setCadence] = useState<CheckinCadence>("weekly");
  const [paused, setPaused] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);
  const onCadenceKeyDown = useRovingRadio(CHECKIN_CADENCES, cadence, (next) => {
    if (!paused) setCadence(next);
  });

  useEffect(() => {
    let cancelled = false;
    getSettings(idToken)
      .then((p) => {
        if (cancelled) return;
        setProfile(p);
        setName(p.name ?? "");
        setLocation(p.location ?? "");
        setPhone(p.phone ?? "");
        setGoal(p.aspirational_goal ?? "");
        setCadence(p.settings?.checkin_cadence ?? "weekly");
        setPaused(p.settings?.checkin_paused ?? false);
      })
      .catch(() => !cancelled && setLoadError("Couldn't load your details."));
    return () => {
      cancelled = true;
    };
  }, [idToken]);

  const save = async () => {
    setSaving(true);
    setSaved(false);
    setErrors([]);
    setSaveError(null);
    // Empty string means "clear this field", which the API expresses as an explicit null —
    // omitting the key would instead mean "leave it alone" (the route is a partial update).
    const result = await putSettings(idToken, {
      name: name.trim() || null,
      location: location.trim() || null,
      phone: phone.trim() || null,
      aspirational_goal: goal.trim() || null,
      settings: { checkin_cadence: cadence, checkin_paused: paused },
    });
    setSaving(false);
    if (result.status === "saved") {
      setProfile(result.profile);
      setSaved(true);
      onSaved?.();
    } else if (result.status === "invalid") {
      setErrors(result.errors);
    } else {
      setSaveError(result.message);
    }
  };

  /**
   * Export every record as JSON.
   *
   * Client-side over the list the shell already holds — ADR-045's pattern again (derive in the
   * browser rather than add an endpoint), and it inherits that ADR's revisit trigger, B-029. There
   * is no matching import; the asymmetry is logged as B-035 rather than left to be discovered.
   */
  const exportJson = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      count: entries?.length ?? 0,
      entries: entries ?? [],
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `careervault-export-${new Date().toISOString().slice(0, 10)}.json`;
    // Appended before clicking and revoked on a later task. Synchronous revoke works in Chrome but
    // is not specified: Firefox and WebKit queue the download of a detached anchor, so tearing the
    // blob URL down in the same task can leave it fetching a dead URL — the user clicks Export and
    // silently gets nothing, with no error surfaced anywhere.
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  /**
   * The header renders in every state, including loading and error.
   *
   * §A10 asks for exactly one `<h1>` per view — and "per view" includes the seconds before the
   * profile arrives. Returning early without it left the page with *no* heading during the fetch,
   * which is a real gap rather than a transient cosmetic one: a screen-reader user navigating by
   * heading has nothing to land on, and the failure is invisible to any check that runs after the
   * data loads. Found by measuring the live page mid-load, not by reading the code.
   */
  const header = (
    <div>
      <p className="eyebrow">Account</p>
      <h1>Details</h1>
    </div>
  );

  if (loadError) {
    return (
      <div className="view details">
        {header}
        <p className="muted" role="alert">
          {loadError}
        </p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="view details">
        {header}
        <p className="muted">Loading…</p>
      </div>
    );
  }

  const hasName = Boolean(name.trim());
  const exportable = (entries?.length ?? 0) > 0;

  return (
    <div className="view details">
      {header}

      <section className="card" aria-labelledby="you-heading">
        <h2 id="you-heading">You</h2>
        <p className="muted">
          These appear at the top of every résumé you generate. Nothing here is sent to the AI model
          — the header is rendered directly from what you enter.
        </p>

        {!hasName && (
          <p className="notice">
            Without a name, your résumé header falls back to your email address.
          </p>
        )}

        <div className="field-grid">
          <label className="field">
            <span className="micro">Name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Ada Lovelace"
              maxLength={120}
            />
          </label>

          <label className="field">
            <span className="micro">Email</span>
            <input value={profile.email} readOnly disabled />
            <small>From your sign-in — not editable here.</small>
          </label>

          <label className="field">
            <span className="micro">Location</span>
            <input
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. City, State"
              maxLength={120}
            />
          </label>

          <label className="field">
            <span className="micro">Phone</span>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Optional"
              maxLength={40}
            />
          </label>
        </div>
      </section>

      <section className="card" aria-labelledby="cadence-heading">
        <h2 id="cadence-heading">Check-in cadence</h2>
        <p className="muted">
          How often we ask what you&apos;ve been working on. The streak counts one entry per period.
        </p>

        <div className="cadence-grid" role="radiogroup" aria-labelledby="cadence-heading">
          {CHECKIN_CADENCES.map((option) => (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={cadence === option}
              // Roving tabindex: the group is one tab stop, arrows move within it.
              tabIndex={cadence === option ? 0 : -1}
              className={`cadence-option${cadence === option ? " selected" : ""}`}
              // `aria-disabled`, not `disabled`: a disabled button leaves the tab order entirely,
              // so a keyboard user pausing check-ins would find the control had vanished with no
              // announcement. This keeps it focusable and readable, and inert.
              aria-disabled={paused || undefined}
              onKeyDown={onCadenceKeyDown}
              onClick={() => !paused && setCadence(option)}
            >
              <span className="cadence-label">{CADENCE_COPY[option].label}</span>
              <span className="cadence-desc">{CADENCE_COPY[option].description}</span>
            </button>
          ))}
        </div>
        {paused && (
          <p className="muted">Cadence is fixed while check-ins are paused.</p>
        )}

        <label className="field">
          <span className="micro">Career goal</span>
          <input
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="e.g. Solutions Architect"
            maxLength={300}
          />
          <small>
            Used to tailor your check-ins when you haven&apos;t logged anything recently. Leave blank
            to skip that.
          </small>
        </label>
      </section>

      <section className="card" aria-labelledby="reminders-heading">
        <h2 id="reminders-heading">Reminders</h2>

        <div className="toggle-row">
          <span className="toggle-text">
            <span className="toggle-label" id="email-toggle-label">
              Email me at check-in
            </span>
            <span className="toggle-sub" id="email-toggle-sub">
              {paused
                ? "Paused — your schedule is kept, and unpausing picks up where it left off."
                : `To ${profile.email}, ${CADENCE_COPY[cadence].label.toLowerCase()}.`}
            </span>
          </span>
          <Switch
            checked={!paused}
            labelId="email-toggle-label"
            describedById="email-toggle-sub"
            onChange={(next) => setPaused(!next)}
          />
        </div>

        <p className="muted">
          {paused ? "Paused — no check-ins will be sent." : nextCheckinLabel(profile.next_checkin_at)}
          {formatWhen(profile.last_checkin_sent_at) &&
            ` · Last sent: ${formatWhen(profile.last_checkin_sent_at)}`}
        </p>
        {!paused && (
          <p className="muted">
            Changing how often takes effect from the next check-in onward — it doesn&apos;t
            reschedule one that&apos;s already due.
          </p>
        )}
      </section>

      {errors.length > 0 && (
        <ul className="field-error" role="alert">
          {errors.map((e) => (
            <li key={e.field}>
              {e.field}: {e.error}
            </li>
          ))}
        </ul>
      )}
      {saveError && (
        <p className="field-error" role="alert">
          {saveError}
        </p>
      )}

      <div className="save-row">
        <button className="btn-primary" onClick={() => void save()} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        {/* §A11 — the save result was previously announced to nobody. */}
        <span className="save-flag" role="status">
          {saved ? "Saved" : ""}
        </span>
      </div>

      <section className="card data-card" aria-labelledby="data-heading">
        <span className="data-text">
          <h2 id="data-heading">Your vault, your data</h2>
          <p className="muted">
            {exportable
              ? `Export all ${entries?.length} records as JSON — everything the app holds, in a file you keep.`
              : "Nothing to export yet."}
          </p>
        </span>
        <button className="btn-quiet" onClick={exportJson} disabled={!exportable}>
          Export
        </button>
      </section>
    </div>
  );
}
