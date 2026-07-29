import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthContextProps } from "react-oidc-context";

/**
 * The render smoke test (slice 4 flag, closed in slice 9).
 *
 * Before this, the frontend CI job was typecheck + build + lint — none of which execute a single
 * component, so a green pipeline did not prove the app renders at all. The plan doc calls that out
 * as the reason not to enable auto-merge on frontend Dependabot PRs: a hollow gate plus auto-merge
 * is how a broken build ships silently. This is the minimum that makes the gate real — the shell
 * mounts, and each of the four auth states lands where ADR-025 says it should.
 */

const mockAuth = vi.fn<() => Partial<AuthContextProps>>();
vi.mock("react-oidc-context", () => ({ useAuth: () => mockAuth() }));

// The child views each fetch on mount; the shell's routing is what is under test, not their
// contents. Stubbed to keep this a smoke test rather than an accidental integration test.
vi.mock("./chat/Chat", () => ({ Chat: () => <div>chat-view</div> }));
vi.mock("./upload/Upload", () => ({ Upload: () => <div>upload-view</div> }));
vi.mock("./entries/Dashboard", () => ({ Dashboard: () => <div>entries-view</div> }));
vi.mock("./resume/Resume", () => ({ Resume: () => <div>resume-view</div> }));
vi.mock("./settings/Settings", () => ({ Settings: () => <div>settings-view</div> }));

const App = (await import("./App")).default;

const AUTHED: Partial<AuthContextProps> = {
  isLoading: false,
  isAuthenticated: true,
  user: {
    id_token: "tok",
    profile: { email: "dev@example.com", sub: "user-sub-1" },
  } as AuthContextProps["user"],
};

beforeEach(() => mockAuth.mockReset());

describe("auth states (ADR-025)", () => {
  it("shows a loading state while the OIDC library resolves the session", () => {
    mockAuth.mockReturnValue({ isLoading: true });
    render(<App />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("surfaces an auth error rather than rendering an empty shell", () => {
    // react-oidc-context surfaces an ErrorContext, not a bare Error — it carries a `source`.
    const error = Object.assign(new Error("bad state param"), { source: "unknown" as const });
    mockAuth.mockReturnValue({ isLoading: false, error });
    render(<App />);
    expect(screen.getByText(/auth error: bad state param/i)).toBeInTheDocument();
  });

  it("offers sign-in when unauthenticated, and shows no app chrome", () => {
    mockAuth.mockReturnValue({ isLoading: false, isAuthenticated: false });
    render(<App />);
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
    // The nav must not leak to a signed-out user.
    expect(screen.queryByRole("button", { name: /entries/i })).not.toBeInTheDocument();
  });

  it("renders the authed shell with all five views reachable", () => {
    mockAuth.mockReturnValue(AUTHED);
    render(<App />);

    expect(screen.getByRole("heading", { name: "CareerVault" })).toBeInTheDocument();
    expect(screen.getByText("dev@example.com")).toBeInTheDocument();
    // Exact names, not regexes: /résumé/i matches both "Upload résumé" and "Résumé".
    for (const name of ["Chat", "Upload résumé", "Entries", "Résumé", "Details"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    // Chat is the landing view.
    expect(screen.getByText("chat-view")).toBeInTheDocument();
  });

  it("falls back to a re-sign-in prompt when authenticated without an id_token", () => {
    // Authenticated but tokenless is the state that would otherwise render a view with
    // `idToken={undefined}` and fail on the first API call instead of here.
    mockAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      user: { profile: { email: "dev@example.com" } } as AuthContextProps["user"],
    });
    render(<App />);
    expect(screen.getByText(/no token/i)).toBeInTheDocument();
    expect(screen.queryByText("chat-view")).not.toBeInTheDocument();
  });
});
