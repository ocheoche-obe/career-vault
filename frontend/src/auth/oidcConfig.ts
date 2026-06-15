import type { AuthProviderProps } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";

/**
 * OIDC configuration for Cognito Hosted UI via OAuth2 Authorization Code + PKCE (ADR-025 / ADR-029).
 *
 * `authority` is the Cognito User Pool issuer URL — react-oidc-context discovers the authorize /
 * token / jwks endpoints from its `/.well-known/openid-configuration`. PKCE is on by default for
 * the `code` response type, so no client secret is needed (the SPA client has none).
 *
 * Values come from Vite env vars, populated from the SAM stack Outputs (see `.env.example`).
 */
const authority = import.meta.env.VITE_COGNITO_AUTHORITY as string;
const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID as string;
const redirectUri = import.meta.env.VITE_REDIRECT_URI as string;

export const cognitoDomain = import.meta.env.VITE_COGNITO_DOMAIN as string;
export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL as string;

export const oidcConfig: AuthProviderProps = {
  authority,
  client_id: clientId,
  redirect_uri: redirectUri,
  response_type: "code",
  scope: "openid email profile",
  // Persist tokens across reloads; survives the dev-server hot reload.
  userStore: new WebStorageStateStore({ store: window.localStorage }),
  // Strip the ?code=...&state=... query params from the URL after a successful sign-in.
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};

/**
 * Build the Cognito Hosted UI logout URL. Cognito has no OIDC end-session endpoint, so we hit its
 * `/logout` with the client id + a registered logout URI (must match a LogoutURL on the client).
 */
export function buildLogoutUrl(): string {
  const params = new URLSearchParams({
    client_id: clientId,
    logout_uri: redirectUri,
  });
  return `https://${cognitoDomain}/logout?${params.toString()}`;
}
