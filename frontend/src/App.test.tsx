import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthContextProps } from "react-oidc-context";
import { stubFetch } from "./test/http";

/**
 * The render smoke test (slice 4 flag, closed in slice 9; rebuilt for the v1.1 redesign).
 *
 * Before this, the frontend CI job was typecheck + build + lint — none of which execute a single
 * component, so a green pipeline did not prove the app renders at all. This is the minimum that
 * makes the gate real: the shell mounts, each auth state lands where ADR-025 says it should, and
 * every nav item routes to the view it names.
 *
 * The redesign added a second job for this file. The pre-redesign audit found accessibility defects
 * that were invisible to every existing test because they are *structural* — a `<header>` inside
 * `<main>` silently loses its banner landmark, and a nav that conveys the active tab by CSS class
 * alone is indistinguishable from one that does not. Those are now asserted, so they cannot regress
 * back in during the remaining view rewrites.
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
vi.mock("./home/Home", () => ({ Home: () => <div>home-view</div> }));

const App = (await import("./App")).default;

const AUTHED: Partial<AuthContextProps> = {
  isLoading: false,
  isAuthenticated: true,
  user: {
    id_token: "tok",
    profile: { email: "dev@example.com", sub: "user-sub-1" },
  } as AuthContextProps["user"],
};

/** The shell fetches entries + settings on mount; both answer empty so no view depends on data. */
function stubShellFetches() {
  stubFetch({ status: 200, body: { entries: [] } }, { status: 200, body: {} });
}

beforeEach(() => {
  mockAuth.mockReset();
  stubShellFetches();
});

afterEach(() => vi.unstubAllGlobals());

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
    expect(screen.queryByRole("button", { name: "Timeline" })).not.toBeInTheDocument();
  });

  it("renders the authed shell and lands on Home", async () => {
    mockAuth.mockReturnValue(AUTHED);
    render(<App />);

    // Exact names, not regexes: /résumé/i would match both "Résumés" and nothing else now, but the
    // exact-name habit is what caught the old "Upload résumé" vs "Résumé" collision.
    for (const name of ["Home", "Log", "Timeline", "Résumés", "Import", "Details"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(await screen.findByText("home-view")).toBeInTheDocument();
  });

  it.each([
    ["Log", "chat-view"],
    ["Import", "upload-view"],
    ["Timeline", "entries-view"],
    ["Résumés", "resume-view"],
    ["Details", "settings-view"],
    ["Home", "home-view"],
  ])("clicking %s renders %s", async (button, view) => {
    // Asserting the buttons *exist* is not the same as asserting they route correctly. App.tsx
    // dispatches through a nested ternary whose final else is Dashboard, so any unmatched value
    // silently lands on Timeline — swapping two setView arguments would leave a presence-only test
    // completely green while the app navigated to the wrong screen.
    mockAuth.mockReturnValue(AUTHED);
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: button }));

    expect(await screen.findByText(view)).toBeInTheDocument();
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
    expect(screen.queryByText("home-view")).not.toBeInTheDocument();
  });
});

describe("shell accessibility (pre-redesign audit §A1, §A2, §A10)", () => {
  beforeEach(() => mockAuth.mockReturnValue(AUTHED));

  it("exposes a banner landmark — the old shell nested <header> in <main> and silently lost it", () => {
    render(<App />);
    // `<header>` only earns the banner role when it is NOT a descendant of <main>. This assertion
    // fails the moment someone moves it back inside, which is exactly how the defect arose.
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Views" })).toBeInTheDocument();
  });

  it("marks the active tab with aria-current, not just a CSS class", () => {
    render(<App />);
    // The old nav conveyed the active view by className alone, so no assistive tech could tell
    // which of six tabs was current — and no test could tell either.
    expect(screen.getByRole("button", { name: "Home" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Timeline" })).not.toHaveAttribute("aria-current");
  });

  it("moves aria-current with the selection", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Timeline" }));

    expect(screen.getByRole("button", { name: "Timeline" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Home" })).not.toHaveAttribute("aria-current");
  });

  it("does not render the wordmark as a heading, so each view can own the page's only h1", () => {
    render(<App />);
    // The wordmark used to be the app's single <h1>, which left every view without one. Once views
    // carry their own titles, leaving it as a heading would ship two <h1>s per page.
    expect(screen.queryByRole("heading", { name: "CareerVault" })).not.toBeInTheDocument();
    expect(screen.getByText("CareerVault")).toBeInTheDocument();
  });

  it("keeps sign-out reachable even though the design omits it", async () => {
    render(<App />);
    // The handoff shows a bare avatar with no sign-out anywhere. Losing it to visual fidelity would
    // be a functional regression, so it lives in an account disclosure behind the avatar.
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
    expect(screen.getByText("dev@example.com")).toBeInTheDocument();
  });
});
