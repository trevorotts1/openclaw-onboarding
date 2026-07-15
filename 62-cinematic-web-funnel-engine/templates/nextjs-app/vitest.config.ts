import path from "node:path";
import { defineConfig } from "vitest/config";

/**
 * vitest.config.ts — build unit U16 (P12-CRM conversion layer). Mirrors the
 * `@/*` -> `./*` path alias already declared in tsconfig.json so tests can
 * import site modules (`@/components/...`, `@/lib/...`, `@/app/...`)
 * exactly the way the application code does.
 *
 * `environment: "node"` is intentional and sufficient: this suite covers
 * pure logic (conversion-map parsing, the webhook relay, the
 * /api/conversion-event route handler) using the Web-standard
 * Request/Response globals Node itself provides — no DOM/jsdom is needed
 * here. Component-level DOM tests belong to a later unit if/when this
 * project adopts a browser test environment; Playwright already covers
 * real-browser behavior per spec Section 19.3.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
