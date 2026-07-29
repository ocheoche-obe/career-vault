import { useEffect, useState } from "react";
import { getSettings, putSettings, type FieldError, type Profile } from "../lib/api";
import "./settings.css";

/**
 * Your details — the identity that goes on a generated résumé (backlog B-008).
 *
 * This view exists because of a concrete failure: résumés rendered the literal word "Résumé"
 * where a name should be. The chain was that `resume.html.j2` reads `contact.name or
 * contact.email`, the PROFILE item had neither field, and no PROFILE item existed at all — because
 * nothing in the app could write one. Cognito could not fill the gap either: the user pool holds
 * only `email`, `email_verified` and `sub`, with no name attribute anywhere.
 *
 * `email` is intentionally read-only here. It comes from the Cognito JWT on every write, so the
 * identity printed on a résumé traces back to an authenticated claim rather than to a form field.
 * The backend rejects an `email` in the body outright rather than ignoring it.
 *
 * Slice 8 adds check-in cadence and pause to this same view and the same `PUT /settings` route.
 */
export function Settings({ idToken }: { idToken: string }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [phone, setPhone] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSettings(idToken)
      .then((p) => {
        if (cancelled) return;
        setProfile(p);
        setName(p.name ?? "");
        setLocation(p.location ?? "");
        setPhone(p.phone ?? "");
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
    });
    setSaving(false);
    if (result.status === "saved") {
      setProfile(result.profile);
      setSaved(true);
    } else if (result.status === "invalid") {
      setErrors(result.errors);
    } else {
      setSaveError(result.message);
    }
  };

  if (loadError) return <section className="settings"><p className="settings-error">{loadError}</p></section>;
  if (!profile) return <section className="settings"><p>Loading…</p></section>;

  const hasName = Boolean(name.trim());

  return (
    <section className="settings">
      <h2>Your details</h2>
      <p className="settings-intro">
        These appear at the top of every résumé you generate. Nothing here is sent to the AI model
        — the header is rendered directly from what you enter.
      </p>

      {!hasName && (
        <p className="settings-warning">
          Without a name, your résumé header falls back to your email address.
        </p>
      )}

      <label>
        <span>Full name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Oche Obe" maxLength={120} />
      </label>

      <label>
        <span>Email</span>
        <input value={profile.email} readOnly disabled />
        <small>From your sign-in — not editable here.</small>
      </label>

      <label>
        <span>Location</span>
        <input
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="Seattle, WA"
          maxLength={120}
        />
      </label>

      <label>
        <span>Phone</span>
        <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Optional" maxLength={40} />
      </label>

      {errors.length > 0 && (
        <ul className="settings-error">
          {errors.map((e) => (
            <li key={e.field}>
              {e.field}: {e.error}
            </li>
          ))}
        </ul>
      )}
      {saveError && <p className="settings-error">{saveError}</p>}

      <div className="settings-actions">
        <button onClick={() => void save()} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        {saved && <span className="settings-saved">Saved</span>}
      </div>
    </section>
  );
}
