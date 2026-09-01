// ============================================================================
// Book Writer mini-app — U18 Playwright global setup
// ----------------------------------------------------------------------------
// Boots the offline stub Worker (harness/server.mjs) before the suite runs and
// tears it down after. Nothing here touches a real host or credentials; the
// stub GHL endpoint is the only transport, and it only ever sees the two
// fictitious clients.
// ============================================================================

import { start, stop } from './server.mjs';

export default async function globalSetup() {
  const { server, port } = await start();
  // Store the port for the server instance so teardown can close it.
  globalThis.__E2E_SERVER__ = server;
  globalThis.__E2E_PORT__ = port;
}

export async function globalTeardown() {
  if (globalThis.__E2E_SERVER__) {
    await stop();
  }
}
