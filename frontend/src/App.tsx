// App.css is imported FIRST, above the view components, and the order is load-bearing.
//
// Vite emits CSS in module-graph order, so a stylesheet imported by a child component lands in the
// bundle *before* one imported here below it. That inverts the cascade everyone expects: App.css's
// shared `.card { flex-direction: column }` was winning over `settings.css`'s
// `.data-card { flex-direction: row }` at equal specificity purely because it came later, and the
// card silently rendered as a centred column. Importing the shared layer first restores
// tokens -> shell/shared -> feature, so a view stylesheet can override a shared primitive by saying
// so rather than by out-specifying it.
import './App.css'
import { useEffect, useState } from 'react'
import { useAuth } from 'react-oidc-context'
import { buildLogoutUrl } from './auth/oidcConfig'
import { Chat } from './chat/Chat'
import { Timeline } from './entries/Timeline'
import { Upload } from './upload/Upload'
import { Resume } from './resume/Resume'
import { Settings } from './settings/Settings'
import { Home } from './home/Home'
import { listEntries, getSettings, type Entry } from './lib/api'
import { computeStreak, CADENCE_NOUN, type Cadence } from './lib/aggregates'

/**
 * Authed shell (ADR-025), rebuilt for the v1.1 redesign.
 *
 * Six views behind Cognito auth: Home (new — derived aggregates per ADR-045), Log (FR-2 ingestion
 * plus FR-6.1 Q&A), Timeline (FR-3.2/3.3), Résumés (FR-5, the ADR-037 async job), Import
 * (ADR-013/ADR-035) and Details (the profile identity printed on a generated résumé, B-008).
 *
 * Structure matters as much as styling here. Pre-redesign audit §A1 found `<header>` nested inside
 * `<main>`, which silently costs the banner landmark — `<nav>` keeps its role anywhere, `<header>`
 * only earns `banner` when scoped to the body. Header and nav are now siblings of `<main>`, there is
 * a skip link, the active tab carries `aria-current`, and the wordmark is no longer an `<h1>` so
 * each view can own the page's single heading (§A10).
 *
 * Entries are fetched once here rather than per-view: Home derives every aggregate it shows from
 * that one list, which is what keeps the handoff's "everything reads from one source of truth"
 * property true rather than aspirational.
 */
type View = 'home' | 'log' | 'timeline' | 'resumes' | 'import' | 'details'

const NAV: { id: View; label: string }[] = [
  { id: 'home', label: 'Home' },
  { id: 'log', label: 'Log' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'resumes', label: 'Résumés' },
  { id: 'import', label: 'Import' },
  { id: 'details', label: 'Details' },
]

function initials(email?: string, name?: string | null): string {
  const source = (name || email || '').trim()
  if (!source) return '··'
  const parts = source.split(/[\s.@_-]+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return source.slice(0, 2).toUpperCase()
}

function App() {
  const auth = useAuth()
  const [view, setView] = useState<View>('home')
  const [entries, setEntries] = useState<Entry[] | null>(null)
  const [cadence, setCadence] = useState<Cadence>('weekly')
  const [profileName, setProfileName] = useState<string | null>(null)
  const [loadError, setLoadError] = useState(false)
  // Carries Home's one-line composer text across to Log so the hand-off does not lose it.
  const [logDraft, setLogDraft] = useState('')
  // Bumped when returning to Home, to re-derive its aggregates against anything saved elsewhere.
  const [dataVersion, setDataVersion] = useState(0)

  const idToken = auth.user?.id_token

  /**
   * Re-read the entry list. Called when a view *writes* an entry, so every derived number in the
   * shell and in the sibling views (header streak, Log's sidebar and status row, Home's stats) stops
   * being stale the moment a save lands rather than at the next navigation.
   */
  const refresh = () => setDataVersion((v) => v + 1)

  /**
   * Nav is routed through here rather than raw `setView` so two pieces of cross-view state stay
   * correct: the composer hand-off is consumed exactly once, and Home re-reads entries on arrival.
   */
  const navigate = (next: View) => {
    // Home's numbers are derived from the entry list, so a save made in Log or Import would leave
    // the stats, streak, heatmap and header pill stale until a full reload. Refetching on arrival
    // is the cheap fix: Home is where the data is *read*, never where it is mutated. Entries are
    // not cleared first, so this updates in place instead of flashing a loading state.
    if (next === 'home') setDataVersion((v) => v + 1)
    // A sent message must not reappear prefilled the next time Log is opened.
    if (view === 'log' && next !== 'log') setLogDraft('')
    setView(next)
  }

  // One fetch for the shell and Home: Home derives every aggregate it shows from this single list,
  // which is what makes the handoff's "everything reads from one source of truth" property real
  // rather than aspirational.
  //
  // `allSettled` rather than `all` because the two calls fail independently — a missing PROFILE is
  // an ordinary state for a new user (it is exactly what B-008 traced), and it must not blank out
  // the entry list. The cancellation guard keeps a slow response from a previous token writing
  // state after it has been superseded.
  useEffect(() => {
    if (!idToken) return
    let cancelled = false

    void (async () => {
      const [rows, profile] = await Promise.allSettled([listEntries(idToken), getSettings(idToken)])
      if (cancelled) return

      if (rows.status === 'fulfilled') {
        setEntries(rows.value)
        setLoadError(false)
      } else {
        // Without this the list stays `null` forever and Home renders "Loading…" indefinitely — a
        // failure that looks identical to a slow network and reports nothing to anyone.
        console.error('Failed to load entries', rows.reason)
        setLoadError(true)
      }

      if (profile.status === 'fulfilled') {
        const value = (profile.value as { settings?: { checkin_cadence?: string } }).settings
          ?.checkin_cadence
        if (value && value in CADENCE_NOUN) setCadence(value as Cadence)
        setProfileName((profile.value as { name?: string | null }).name ?? null)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [idToken, dataVersion])

  if (auth.isLoading) {
    return (
      <main className="app-state" aria-busy="true">
        <p>Loading…</p>
      </main>
    )
  }

  if (auth.error) {
    return (
      <main className="app-state">
        <h1>Something went wrong</h1>
        <p role="alert">Auth error: {auth.error.message}</p>
      </main>
    )
  }

  if (!auth.isAuthenticated) {
    return (
      <main className="app-state app-signin">
        <h1>CareerVault</h1>
        <p>Your career, on the record. Log what you achieve while it is fresh.</p>
        <button className="btn-primary" onClick={() => void auth.signinRedirect()}>
          Sign in
        </button>
      </main>
    )
  }

  const signOut = () => {
    // Clear the local session, then redirect through Cognito's Hosted UI logout.
    void auth.removeUser()
    window.location.href = buildLogoutUrl()
  }

  const email = auth.user?.profile.email
  const streak = computeStreak(entries ?? [], cadence)
  const noun = CADENCE_NOUN[cadence]

  return (
    <>
      <a className="skip-link" href="#view">
        Skip to content
      </a>

      <header className="app-header">
        <div className="app-header-inner">
          {/* Wordmark only. The handoff's gradient square was a placeholder for a logo that does
              not exist; a meaningless mark reads worse than none. The slot is here when there is
              something real to put in it (B-031). */}
          <div className="brand">
            <span className="wordmark">CareerVault</span>
          </div>

          <nav className="view-nav" aria-label="Views">
            {NAV.map((item) => (
              <button
                key={item.id}
                type="button"
                className={view === item.id ? 'active' : ''}
                aria-current={view === item.id ? 'page' : undefined}
                onClick={() => navigate(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>

          <div className="header-end">
            <p className="streak-pill">
              <span className="sparkline" aria-hidden="true">
                {streak.recent.map((hit, i) => (
                  <span key={i} className={hit ? 'bar hit' : 'bar'} />
                ))}
              </span>
              <span className="streak-label">
                {streak.current > 0 ? `${streak.current}-${noun} streak` : 'No streak yet'}
              </span>
            </p>
            <details className="account">
              <summary aria-label={`Account menu for ${email ?? 'your account'}`}>
                <span className="avatar" aria-hidden="true">
                  {initials(email, profileName)}
                </span>
              </summary>
              <div className="account-menu">
                <p className="account-email">{email}</p>
                <button type="button" onClick={signOut}>
                  Sign out
                </button>
              </div>
            </details>
          </div>
        </div>
      </header>

      <main id="view" tabIndex={-1}>
        {!idToken ? (
          <p role="alert">No token — sign in again.</p>
        ) : view === 'home' ? (
          <Home
            entries={entries}
            cadence={cadence}
            name={profileName}
            loadError={loadError}
            onNavigate={navigate}
            onDraft={setLogDraft}
          />
        ) : view === 'log' ? (
          <Chat
            idToken={idToken}
            initialDraft={logDraft}
            entries={entries}
            cadence={cadence}
            onEntrySaved={refresh}
          />
        ) : view === 'timeline' ? (
          <Timeline
            idToken={idToken}
            entries={entries}
            loadError={loadError}
            onChanged={refresh}
          />
        ) : view === 'import' ? (
          <Upload idToken={idToken} onImported={refresh} />
        ) : view === 'details' ? (
          <Settings idToken={idToken} entries={entries} onSaved={refresh} />
        ) : (
          // TEMPORARY wrapper, and now down to its last occupant. Résumés has no container of its
          // own — it relied on the old `main`'s flex centering and padding, which the redesign
          // removed. It is blocked on B-028 (no résumé list endpoint; RESUMERUN TTL'd at 30 days),
          // so slice 3 rebuilds it and deletes this wrapper along with the final shim alias.
          <div className="legacy-view">
            <Resume idToken={idToken} />
          </div>
        )}
      </main>
    </>
  )
}

export default App
