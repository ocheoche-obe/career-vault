import { describe, expect, it } from "vitest";

// Getting the stylesheet's text here has three dead ends worth recording, because each fails
// *silently* rather than loudly:
//   - `fileURLToPath(import.meta.url)` throws — under Vite's transform that URL is http, not file.
//   - `?raw` resolves to an **empty string**; Vite's CSS plugin claims the request first.
//   - `node:fs` works but needs `@types/node` in `tsconfig.app.json`, which would let application
//     code import `fs` and still pass `tsc -b`.
// `?inline` returns the real text, but only because `vite.config.ts` enables CSS processing for
// this one file — Vitest stubs CSS by default. The empty-string failures are why the size guard is
// the first test below: every other assertion here passes vacuously on a zero-length file.
import css from "../index.css?inline";

/**
 * The light palette is declared **twice** in `index.css` — once under
 * `@media (prefers-color-scheme: light)` for "System", and once under `:root[data-theme="light"]`
 * for an explicit choice. This test is the price of that duplication, and the reason it is allowed.
 *
 * Why the duplication exists at all (ADR-044 amendment): merging the two requires `light-dark()`,
 * which accepts only colours, while five tokens are whole `linear-gradient(…)` strings. Adopting it
 * would convert most tokens and leave the gradients on the old mechanism — two mechanisms in the one
 * file whose entire rule is that colour is defined in exactly one place.
 *
 * Why it needs a test rather than a comment: a palette tweak applied to one block and not the other
 * desyncs the toggle from the system default, and the *system* path is the one nobody clicks to
 * check. The failure is silent, cosmetic, and lands in the half of the matrix that gets less
 * attention. A comment asking people to remember is not a control.
 */

const SYSTEM_LIGHT = ':root:not([data-theme="dark"]) {';
const EXPLICIT_LIGHT = ':root[data-theme="light"] {';

/**
 * Pull the `--token: value;` declarations out of the block opened by `opener`.
 *
 * Throws rather than asserting: this runs inside test bodies, but a helper that calls `expect()` is
 * unusable at module scope, and a missing block is a bug in the *test's* assumptions either way.
 */
function tokensIn(opener: string): Map<string, string> {
  const start = css.indexOf(opener);
  if (start === -1) throw new Error(`block not found in index.css: ${opener}`);

  // Walk braces from the opener so a nested rule cannot end the block early.
  let depth = 0;
  let end = start;
  for (let i = css.indexOf("{", start); i < css.length; i++) {
    if (css[i] === "{") depth++;
    else if (css[i] === "}" && --depth === 0) {
      end = i;
      break;
    }
  }

  const tokens = new Map<string, string>();
  for (const [, name, value] of css.slice(start, end).matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    tokens.set(name, value.trim());
  }
  return tokens;
}

describe("the two light-theme declarations", () => {
  it("both actually parsed (guards against the test silently passing on empty sets)", () => {
    // Without this, a selector rename would make both sides empty and every assertion below vacuous
    // — the test would go green at exactly the moment it stopped testing anything.
    expect(tokensIn(SYSTEM_LIGHT).size).toBeGreaterThan(30);
    expect(tokensIn(EXPLICIT_LIGHT).size).toBeGreaterThan(30);
  });

  it("declare exactly the same token names", () => {
    expect([...tokensIn(EXPLICIT_LIGHT).keys()].sort()).toEqual([...tokensIn(SYSTEM_LIGHT).keys()].sort());
  });

  it("declare exactly the same values", () => {
    const explicitLight = tokensIn(EXPLICIT_LIGHT);
    for (const [name, value] of tokensIn(SYSTEM_LIGHT)) {
      expect(explicitLight.get(name), `${name} differs between the two light blocks`).toBe(value);
    }
  });
});

describe("theme mechanics", () => {
  it("guards the media query so an explicit dark choice survives a light OS setting", () => {
    // Drop the `:not(...)` and a user who picked Dark on a light-mode laptop gets light anyway.
    expect(css).toContain(':root:not([data-theme="dark"])');
  });

  it("pins color-scheme for both explicit choices", () => {
    // ADR-044 already records that dropping `color-scheme` gives white scrollbars on a dark page.
    // An explicit override reintroduces the same bug if the property keeps reporting `dark light`.
    expect(tokensIn(EXPLICIT_LIGHT).size).toBeGreaterThan(0);
    expect(css).toMatch(/:root\[data-theme="light"\][\s\S]*?color-scheme:\s*light/);
    expect(css).toMatch(/:root\[data-theme="dark"\][\s\S]*?color-scheme:\s*dark/);
  });

  it("keeps every theme-invariant swatch token out of the light blocks", () => {
    // The swatches preview what each option *gives you*, so they must not change with the active
    // theme — redefining one in a light block would make the previews agree with the current theme
    // instead of describing the choice. Matched by prefix rather than by name so a swatch token
    // added later is covered automatically; naming them individually is how the next one gets missed.
    const swatches = [...css.matchAll(/(--swatch-[\w-]+)\s*:/g)].map(([, name]) => name);
    expect(new Set(swatches).size).toBeGreaterThanOrEqual(4);

    for (const block of [tokensIn(SYSTEM_LIGHT), tokensIn(EXPLICIT_LIGHT)]) {
      for (const token of swatches) {
        expect(block.has(token), `${token} must not be redefined per-theme`).toBe(false);
      }
    }
  });
});
