/**
 * Theme selection — Light / Dark / System (ADR-044 amendment).
 *
 * The *palette* is settled in `index.css`; this module only decides which of the two applies. Three
 * things here are load-bearing and easy to get subtly wrong:
 *
 *  1. **"System" is a stored choice, not the absence of one.** It is represented by *removing* the
 *     `data-theme` attribute, which is what hands control back to `@media (prefers-color-scheme)`.
 *     Collapsing "unset" and "follow the system" into one state is the bug that leaves a user who
 *     picked Dark with no way back to following their OS.
 *  2. **First paint is handled elsewhere.** The inline script in `index.html` applies the stored
 *     theme before the bundle loads. This module must agree with it exactly — same key, same values,
 *     same "only light/dark are written as attributes" rule.
 *  3. **The OS can change while the app is open.** A user on System at sunset expects the app to
 *     follow, so the media query is *subscribed to*, not merely read once.
 *
 * Preference is per device (`localStorage`), not on the PROFILE: a server round-trip cannot beat the
 * first frame, and "dark on my laptop, light on my phone" is a legitimate configuration rather than
 * a sync failure. Costs $0 and adds no endpoint. See the ADR for the full reasoning.
 */

export type ThemeChoice = "light" | "dark" | "system";

/** Must match the key used by the pre-paint script in `index.html`. Asserted in `theme.test.ts`. */
export const THEME_STORAGE_KEY = "careervault:theme";

export const THEME_CHOICES: readonly ThemeChoice[] = ["light", "dark", "system"] as const;

function isThemeChoice(value: unknown): value is ThemeChoice {
  return value === "light" || value === "dark" || value === "system";
}

/**
 * Read the stored preference, defaulting to `"system"`.
 *
 * Every failure mode collapses to `"system"` on purpose — absent, corrupted, or unreadable (Safari
 * private mode throws on `localStorage` access rather than returning null). A theme preference must
 * never be the reason the app fails to start.
 *
 * `window.localStorage`, not the bare global: Node 22 exposes its own experimental `localStorage`
 * that shadows jsdom's under Vitest, so the unqualified name resolves to an unusable object in tests.
 */
export function readThemeChoice(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemeChoice(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

/**
 * Apply a choice to the document, and persist it.
 *
 * `"system"` removes the attribute rather than writing `data-theme="system"`, because the CSS has no
 * such state — the media query takes over precisely when the attribute is absent.
 */
export function applyThemeChoice(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = choice;
  }

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch {
    // Storage unavailable: the theme still applies for this session, it just will not persist.
    // Silently degrading beats refusing to change the theme at all.
  }
}

/*
 * `resolveTheme` and `watchSystemTheme` used to live here — helpers for reporting which theme is
 * *in force* when the choice is "System". Both were removed at slice-3 wrap: nothing rendered a
 * resolved theme, so their only production caller was an effect that did nothing, and their tests
 * covered code the app never ran. The repaint on an OS change comes from the CSS media query alone
 * and needs no JavaScript. Reintroduce them with the consumer that needs them, not before.
 */
