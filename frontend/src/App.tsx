import { useEffect, useState } from 'react'
import { useAuth } from 'react-oidc-context'
import { apiBaseUrl, buildLogoutUrl } from './auth/oidcConfig'
import './App.css'

/**
 * First-slice UI: a single page that shows "Sign in" before auth and the GET /settings JSON
 * after auth. Auth is OAuth2 Authorization Code + PKCE against Cognito Hosted UI (ADR-025).
 */
function App() {
  const auth = useAuth()
  const [settings, setSettings] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)

  // Fetch GET /settings once authenticated, using the Cognito ID token as the bearer.
  useEffect(() => {
    if (!auth.isAuthenticated || !auth.user) return
    setError(null)
    fetch(`${apiBaseUrl}/settings`, {
      headers: { Authorization: `Bearer ${auth.user.id_token}` },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`GET /settings → ${res.status}`)
        return res.json()
      })
      .then(setSettings)
      .catch((e) => setError(String(e)))
  }, [auth.isAuthenticated, auth.user])

  if (auth.isLoading) return <main><p>Loading…</p></main>
  if (auth.error) return <main><p>Auth error: {auth.error.message}</p></main>

  if (!auth.isAuthenticated) {
    return (
      <main>
        <h1>CareerVault</h1>
        <button onClick={() => void auth.signinRedirect()}>Sign in</button>
      </main>
    )
  }

  const signOut = () => {
    // Clear the local session, then redirect through Cognito's Hosted UI logout.
    void auth.removeUser()
    window.location.href = buildLogoutUrl()
  }

  return (
    <main>
      <h1>CareerVault</h1>
      <p>Signed in as {auth.user?.profile.email ?? auth.user?.profile.sub}</p>
      <button onClick={signOut}>Sign out</button>
      <h2>GET /settings</h2>
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      <pre>{settings ? JSON.stringify(settings, null, 2) : 'Loading settings…'}</pre>
    </main>
  )
}

export default App
