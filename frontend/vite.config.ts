/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // No `globals: true` — tests import describe/it/expect/vi from 'vitest' explicitly, so
    // tsconfig's `types` array needs no extra entry for `tsc -b` to typecheck them.
    restoreMocks: true,
    unstubGlobals: true,
    // Vitest stubs CSS imports by default, which makes `index.css?inline` resolve to an empty
    // string. `theme-tokens.test.ts` reads that file to prove the two light-theme blocks stay in
    // sync (ADR-044 amendment), so it needs the real text. Scoped to this one file rather than
    // enabled globally: no other test asserts on stylesheets, and processing every import would be
    // cost with no reader. The alternative — `node:fs` — would drag `@types/node` into
    // `tsconfig.app.json`, which would let application code import `fs` and still typecheck.
    // NB: no `$` anchor — the module id carries the `?inline` query, so `/index\.css$/` matches
    // nothing and silently yields an empty string.
    css: { include: [/index\.css/] },
  },
})
