import { useAuth } from 'react-oidc-context'
import { buildLogoutUrl } from './auth/oidcConfig'
import { Chat } from './chat/Chat'
import './App.css'

/**
 * Slice 2b UI: the ingestion chat (FR-2) behind Cognito auth. Sign in via Hosted UI with
 * OAuth2 Authorization Code + PKCE (ADR-025), then converse — entries persist only after the
 * user confirms a proposal card. The entries dashboard arrives in slice 3.
 */
function App() {
  const auth = useAuth()

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
      <header className="app-header">
        <h1>CareerVault</h1>
        <div className="app-header-user">
          <span>{auth.user?.profile.email ?? auth.user?.profile.sub}</span>
          <button onClick={signOut}>Sign out</button>
        </div>
      </header>
      {auth.user?.id_token ? <Chat idToken={auth.user.id_token} /> : <p>No token — sign in again.</p>}
    </main>
  )
}

export default App
