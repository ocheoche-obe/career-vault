import { useState } from 'react'
import { useAuth } from 'react-oidc-context'
import { buildLogoutUrl } from './auth/oidcConfig'
import { Chat } from './chat/Chat'
import { Dashboard } from './entries/Dashboard'
import { Upload } from './upload/Upload'
import { Resume } from './resume/Resume'
import './App.css'
import './entries/entries.css'

/**
 * Authed shell (ADR-025). Four views behind Cognito auth: the ingestion Chat (FR-2), the resume
 * Upload bootstrap (ADR-013/ADR-035), the entries Dashboard (FR-3.2/3.3), and Résumé generation
 * (FR-5, the ADR-037 async job). Entries persist only after the user confirms — a proposal card in
 * chat, or a row in the upload review table.
 */
type View = 'chat' | 'upload' | 'entries' | 'resume'

function App() {
  const auth = useAuth()
  const [view, setView] = useState<View>('chat')

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

  const idToken = auth.user?.id_token

  return (
    <main>
      <header className="app-header">
        <h1>CareerVault</h1>
        <div className="app-header-user">
          <span>{auth.user?.profile.email ?? auth.user?.profile.sub}</span>
          <button onClick={signOut}>Sign out</button>
        </div>
      </header>

      <nav className="view-nav">
        <button className={view === 'chat' ? 'active' : ''} onClick={() => setView('chat')}>Chat</button>
        <button className={view === 'upload' ? 'active' : ''} onClick={() => setView('upload')}>Upload résumé</button>
        <button className={view === 'entries' ? 'active' : ''} onClick={() => setView('entries')}>Entries</button>
        <button className={view === 'resume' ? 'active' : ''} onClick={() => setView('resume')}>Résumé</button>
      </nav>

      {idToken ? (
        view === 'chat' ? (
          <Chat idToken={idToken} />
        ) : view === 'upload' ? (
          <Upload idToken={idToken} />
        ) : view === 'resume' ? (
          <Resume idToken={idToken} />
        ) : (
          <Dashboard idToken={idToken} />
        )
      ) : (
        <p>No token — sign in again.</p>
      )}
    </main>
  )
}

export default App
