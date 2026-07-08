// anthology-intake.mjs -- Node-loadable hook transform for the Anthology Engine
// (Skill 59) inbound intake route /hooks/anthology-intake.
//
// WHY THIS IS A .mjs AND NOT A .py (W5.3 canary fix):
// The OpenClaw 2026.6.11 gateway loads hooks.*.transform.module via
//   await import(pathToFileURL(modulePath))          // dist/hooks module-loader
// i.e. a Node ESM dynamic import. A Python file passed to import() throws
// ERR_UNKNOWN_FILE_EXTENSION -- a .py CANNOT be a hook transform. So the
// deterministic dispatch is a Node shim (this file) that SHELLS OUT to the
// sibling intake_router.py, which owns all of S0 (parse, secret defense-in-depth,
// tenant check, dedup, sole-writer upsert, Exceptions capture, detached stage).
//
// CONTRACT (verified against the dist/hooks-*.js hook-mapping applier):
//   const override = await (await loadTransform(mapping.transform))(ctx);
//   if (override === null) return { ok: true, action: null, skipped: true };
// Returning null => the gateway ACKNOWLEDGES the request with NO agent/model turn
// (deterministic, client-silent doctrine; untrusted form content is never
// interpreted as instructions). The gateway has ALREADY authenticated the Bearer
// token (hooks.token) before this transform runs, so intake_router.py runs in its
// default verify_if_present mode (no body-borne secret; the gateway is the primary
// enforcer, the router the independent defense-in-depth check).
//
// FAIL-CLOSED: intake_router.py acknowledges under 2s and spawns the slow stage job
// detached. Exit 0 (routed / idempotent no-op), 2 (secret refusal) and 3 (captured
// to Exceptions with a typed reason) are all TERMINAL -> ack (return null). Exit 4
// (ledger unreachable / concurrent in-flight; RETRYABLE) and any spawn failure or
// timeout are NOT terminal -> THROW so the gateway returns non-2xx and Convert and
// Flow re-delivers; a submission is NEVER silently dropped (SPEC S0 cardinal
// guarantee). No secret value is ever read or printed here.

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

// Absolute path to intake_router.py. Resolution order:
//   1. ANTHOLOGY_INTAKE_ROUTER (explicit absolute path)
//   2. ANTHOLOGY_SCRIPTS_DIR/intake_router.py
//   3. the absolute path baked in by provision-anthology-client.sh at install time
function resolveRouter() {
  const explicit = (process.env.ANTHOLOGY_INTAKE_ROUTER || "").trim();
  if (explicit && existsSync(explicit)) return explicit;
  const scriptsDir = (process.env.ANTHOLOGY_SCRIPTS_DIR || "").trim();
  if (scriptsDir) {
    const p = path.join(scriptsDir, "intake_router.py");
    if (existsSync(p)) return p;
  }
  return "__ANTHOLOGY_INTAKE_ROUTER__";
}

export function transform(ctx) {
  const payload = (ctx && ctx.payload && typeof ctx.payload === "object") ? ctx.payload : {};
  const router = resolveRouter();
  if (!existsSync(router)) {
    // A provisioning defect: re-delivery will not fix it, but ACKing would silently
    // drop the submission. Fail closed so the operator sees a non-2xx.
    throw new Error("anthology intake_router.py not found (transform cannot dispatch)");
  }
  const py = (process.env.ANTHOLOGY_PYTHON || "python3").trim() || "python3";
  const res = spawnSync(py, [router], {
    input: JSON.stringify(payload),          // the gateway transform pipes the form JSON on stdin
    encoding: "utf8",
    timeout: 18000,                          // under the mapping timeoutSeconds transport ceiling
    stdio: ["pipe", "pipe", "pipe"],
  });
  if (res.error || res.status === null || typeof res.status !== "number") {
    // spawn failure or timeout -> retryable, never a false success.
    throw new Error("anthology intake dispatch failed: " + (res.error ? res.error.message : "no exit status"));
  }
  if (res.status === 4) {
    // EX_LEDGER: retryable. Throw so the webhook re-delivers (claim already released).
    throw new Error("anthology intake ledger unreachable (retryable)");
  }
  // Exit 0 / 2 / 3 are terminal: acknowledge with no agent turn.
  return null;
}

export default transform;
