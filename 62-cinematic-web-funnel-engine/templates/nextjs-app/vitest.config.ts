import fs from "node:fs";
import path from "node:path";
import { defineConfig } from "vitest/config";

/**
 * vitest.config.ts — build unit U16 (P12-CRM conversion layer). Mirrors the
 * `@/*` -> `./*` path alias already declared in tsconfig.json so tests can
 * import site modules (`@/components/...`, `@/lib/...`, `@/app/...`)
 * exactly the way the application code does.
 *
 * `@/components` is resolved separately from the rest of `@/*`: build_site.py
 * materializes a generated site by copying this template to `site_dir/` and
 * copying the sibling `templates/components/` tree into `site_dir/components`
 * (scripts/build_site.py `materialize_template`), so in a *materialized*
 * site `@/components` and `@/lib`/`@/app` share the same root. In this
 * template's own worktree, though, `templates/components/` is a sibling of
 * `templates/nextjs-app/`, not nested inside it — so `npm test` here must
 * point `@/components` one level up. Pick whichever location actually has
 * the components so the same config file works unmodified in both the raw
 * template (this worktree) and every materialized site it produces.
 *
 * `environment: "node"` is intentional and sufficient: this suite covers
 * pure logic (conversion-map parsing, the webhook relay, the
 * /api/conversion-event route handler) using the Web-standard
 * Request/Response globals Node itself provides — no DOM/jsdom is needed
 * here. Component-level DOM tests belong to a later unit if/when this
 * project adopts a browser test environment; Playwright already covers
 * real-browser behavior per spec Section 19.3.
 */
const localComponentsDir = path.resolve(__dirname, "components");
const siblingComponentsDir = path.resolve(__dirname, "..", "components");
const componentsDir = fs.existsSync(localComponentsDir) ? localComponentsDir : siblingComponentsDir;

export default defineConfig({
  resolve: {
    alias: [
      { find: "@/components", replacement: componentsDir },
      { find: "@", replacement: path.resolve(__dirname, ".") },
    ],
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
