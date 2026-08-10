import { beforeEach, describe, expect, it, vi } from "vitest";

// `?raw`, not `node:fs` — see the note in theme-tokens.test.ts.
import indexHtml from "../../index.html?raw";
import { applyThemeChoice, readThemeChoice, THEME_CHOICES, THEME_STORAGE_KEY } from "./theme";

/**
 * Theme selection (ADR-044 amendment).
 *
 * The tests that matter most here are not the happy paths — they are the three states that look
 * identical in a screenshot and behave differently: "system" as a *stored choice*, an explicit
 * choice surviving a contrary OS setting, and storage being unavailable entirely.
 */

beforeEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  vi.unstubAllGlobals();
});

describe("reading the stored choice", () => {
  it("defaults to system when nothing is stored", () => {
    expect(readThemeChoice()).toBe("system");
  });

  it("round-trips each choice", () => {
    for (const choice of THEME_CHOICES) {
      applyThemeChoice(choice);
      expect(readThemeChoice()).toBe(choice);
    }
  });

  it("falls back to system when the stored value is garbage", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "solarized");
    expect(readThemeChoice()).toBe("system");
  });

  it("falls back to system when localStorage throws", () => {
    // Safari private mode throws on access rather than returning null. A theme preference must
    // never be the reason the app fails to start.
    vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(readThemeChoice()).toBe("system");
  });

  it("still applies the theme when the write throws", () => {
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceeded");
    });
    applyThemeChoice("light");
    // It cannot persist, but refusing to change the theme at all would be the worse failure.
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});

describe("applying a choice to the document", () => {
  it("writes the attribute for an explicit choice", () => {
    applyThemeChoice("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("REMOVES the attribute for system rather than writing data-theme=system", () => {
    // The whole mechanism: the media query in index.css takes over precisely when the attribute is
    // absent. Writing `data-theme="system"` would match no CSS rule and silently pin the palette to
    // whatever bare `:root` declares, so a user on System would stop following their OS.
    applyThemeChoice("dark");
    applyThemeChoice("system");
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(document.documentElement.getAttribute("data-theme")).toBeNull();
  });
});

describe("agreement with the pre-paint script", () => {
  it("uses the same storage key as the inline script in index.html", () => {
    // These are two independent implementations of the same rule — one in the bundle, one that must
    // run before it. If they disagree on the key, the pre-paint script silently stops working and
    // the only symptom is a flash of the wrong theme on load, which no other test would catch.
    expect(indexHtml).toContain(THEME_STORAGE_KEY);
  });

  it("only ever writes light or dark as an attribute, never system", () => {
    const script = indexHtml.slice(indexHtml.indexOf("<script>"), indexHtml.indexOf("</script>"));
    expect(script).toMatch(/=== ?"light"/);
    expect(script).toMatch(/=== ?"dark"/);
    expect(script).not.toContain('"system"');
  });
});
