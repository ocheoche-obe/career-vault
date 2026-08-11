// Vitest setup, loaded before every test file.
//
// Lives under `src/` deliberately: `tsconfig.app.json` includes only `src`, so putting it here is
// what makes the jest-dom matcher type augmentation below visible to `tsc -b`. Moved to the project
// root it would still work at runtime and silently stop typechecking.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// RTL's auto-cleanup only registers when a global `afterEach` exists, and this project runs Vitest
// without `globals: true` — so unmounting is wired explicitly rather than assumed.
afterEach(cleanup);

// `localStorage` polyfill.
//
// This environment's jsdom exposes none — `window.localStorage` and `globalThis.localStorage` are
// both `undefined` — while Node 22 separately warns that its own experimental implementation is
// unavailable without `--localstorage-file`. Every real browser has it, so the app is right to use
// it directly (ADR-044 amendment stores the theme preference there); it is the test environment
// that is impoverished, and this is the smallest honest way to close the gap.
//
// Deliberately a real working store rather than a `vi.fn()` stub: tests assert round-trips
// (write then read back), which a mock returning `undefined` would pass for the wrong reason.
if (typeof window.localStorage === "undefined") {
  let store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, String(value)),
      removeItem: (key: string) => void store.delete(key),
      clear: () => void (store = new Map()),
      key: (index: number) => [...store.keys()][index] ?? null,
      get length() {
        return store.size;
      },
    },
  });
}
