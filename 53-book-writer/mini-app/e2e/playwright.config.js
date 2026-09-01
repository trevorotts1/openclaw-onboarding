// ============================================================================
// Book Writer mini-app — U18 Playwright e2e config (headless, offline)
// ----------------------------------------------------------------------------
// Fully headless: no headed runs, no interactive browsers, no popups. Tests
// run against the local stub Worker (harness/server.mjs) started by the global
// setup. A real client feed is NEVER contacted — the stub GHL endpoint is the
// only transport, and it only ever sees the two FICTITIOUS clients (alpha/beta).
//
// No Anthropic ids, no real creds/hosts, no {{...}} placeholders anywhere.
// ============================================================================
import { defineConfig } from '@playwright/test';

const PORT = 9780;
const BASE_URL = process.env.E2E_BASE_URL || `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI
    ? [['line'], ['html', { open: 'never' }]]
    : [['line']],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    locale: 'en-US',
    colorScheme: 'light',
    // A fake mic/camera so the recorder's granted-permission path works
    // headless WITHOUT an OS media device or a popup. The permission gate is
    // still exercised: the denied test stubs getUserMedia to reject.
    launchOptions: {
      args: [
        '--use-fake-device-for-media-stream',
        '--use-fake-ui-for-media-stream',
        '--autoplay-policy=no-user-gesture-required',
      ],
    },
  },
  globalSetup: './harness/global-setup.mjs',
});
