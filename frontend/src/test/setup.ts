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
