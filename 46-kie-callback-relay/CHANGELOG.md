# Changelog - kie-callback-relay

All notable changes to this skill are documented here.

---

## [v1.1.2] - July 21, 2026

### Fixed
- **ONB-46-001 (BLOCKER) — the Kie recordInfo FALLBACK wrote a permanent `done`
  marker with ZERO downloadable URLs.** `_kieRecordInfoFallback` hard-coded
  `status: 'done'` on `state === 'success'` no matter how many result URLs
  survived the host allowlist, while the callback-KV path ~90 lines above already
  refused exactly that (fix 35). A generation run that produced nothing was
  permanently recorded as complete, and because the marker is durable the resume
  path counted the slide as finished forever after.
- **The rule now has ONE implementation.** Both resolution paths call the new
  `KieKvPoller._resolveOutcome(rawUrls, code, taskId, source)`; neither branch
  decides the status itself, so they cannot diverge again. A provider "success"
  with zero allowlisted URLs is `failed` with a LOUD, distinctly tagged
  `console.error` (`EMPTY-RESULT` when nothing was carried, `ALLOWLIST-MISMATCH`
  when URLs were carried but all dropped) — never a silent skip, never `done`.
- **`kie-slide-submitter.js` — the same single-rule treatment for "is this slide
  really done?".** The fresh-wait path and the resume/already-resolved path both
  call the new `_reconcileDoneStatus(status, localPath, slideId)`, so a marker
  left on disk by a pre-fix poller (`done` with no file) is reconciled to `failed`
  instead of re-entering a run as a success.

### Tests
- `test/security.test.mjs` — six new sections: fallback success with zero URLs
  (marker on disk asserted NOT `done`), fallback with only non-allowlisted URLs,
  fallback with a real URL still resolving `done`, the KV path still resolving a
  real URL as `done`, `_resolveOutcome` unit cases (including `undefined` URLs),
  and a source-level assertion that BOTH call sites delegate and exactly one
  executable `status: 'done'` literal exists — inside `_resolveOutcome`.
  57 assertions pass; 10 of them fail against the pre-fix tree.

---

## [v1.1.0] - July 5, 2026

Security-hardening + reliability pass (merge-train T-46, fixes FIX-S36-31..37).
The Worker was already hardened; this train brings the docs, the box modules, and
the tests up to the same contract, and adds per-client credential derivation.

### Security
- **FIX-S36-31** — Rewrote `SUBMITTER-SOP.md` to the hardened contract (random
  128-bit `submitId`, `s=` callback validator, `h=` per-task-secret HMAC, Bearer
  auth, `X-Kie-Preimage` header). Removed the pre-hardening `&s=<perTaskSecret>`
  URL that leaked the raw secret into Kie's logs; fixed the same URL in
  `07-kie-setup/SKILL.md` and corrected the per-model timeouts.
- **FIX-S36-34** — `box-kv-poller.js` `_validatePerTaskSecret` now requires an
  EXACT `submitId` match (was: any non-empty string), closing the confused-deputy
  gap where a wrong-task result could land on a slide.
- **FIX-S36-36** — Per-client credential derivation. `KIE_CALLBACK_HMAC_KEY` and
  `KVREAD_TOKEN` are now fleet MASTER keys held only by the Worker; each box holds
  `HMAC-SHA256(clientSlug, master)`. One compromised box exposes one client, not
  the fleet. Blast radius disclosed in `SKILL.md`.
- **FIX-S36-37(ii)** — The `perTaskSecret` preimage moved from the `&p=` query
  param to the `X-Kie-Preimage` header on `/kv-read`, so it is no longer captured
  in edge access logs on every 2s poll.

### Fixed
- **FIX-S36-32** — `DEPLOY.md` now provisions all three Worker secrets
  (`KIE_WEBHOOK_HMAC_KEY`, `KIE_CALLBACK_HMAC_KEY`, `KVREAD_TOKEN`) + per-client
  box distribution; the Step-6 smoke test passes the required per-client
  credentials; expected `/healthz` version corrected to `1.1.0`.
- **FIX-S36-33** — Small decks (≤ threshold) skip the KV phase entirely and
  batch-poll Kie `recordInfo` directly instead of burning ~5 min waiting on a
  callback that was never requested. Worker secrets are now optional below the
  threshold (validated lazily in `submitDeck`, not the constructor).
- **FIX-S36-35** — A callback with `code 200` but zero allowlisted result URLs is
  now `failed`/`allowlist-rejected`; a slide counts as `done` only when the file
  actually exists on disk.
- **FIX-S36-37(i)** — Resume dedup: a crash between the createTask POST and its
  response no longer risks a paid double-submit. `_loadRegistryByLabel` prefers the
  row with a non-null `taskId` (else newest `submittedAt`) and marks orphan
  duplicates `superseded`.

### Added
- **FIX-S36-37(iii)** — `test/security.test.mjs`: stubbed-fetch regression suite
  covering signature verify/replay, `/kv-read` 401/403/found, per-client token
  isolation, submitId mismatch, empty-result, and the small-deck path. Wired into
  `qc-kie-callback-relay.sh`.
- `worker/package.json` set to `"type": "module"` (v1.1.0) so the Worker is
  importable by the test suite.

---

## [v1.0.x] - June 2026

- Initial centralized Cloudflare Worker + KV-pull architecture (Candidate B,
  transport B2), with the 2026-06-14 security-hardening pass in `worker/src/index.js`.
