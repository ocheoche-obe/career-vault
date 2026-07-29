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
  },
})
