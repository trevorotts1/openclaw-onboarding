# Changelog - kie-callback-relay

All notable changes to this skill are documented here.

---

## [v2.0.2] - 2026-10-05 - fix: read the real KIE Market result shape (resultJson.resultUrls) and the Suno audio shape

### Fixed
- Result parsing defect. The Worker (`worker/src/index.js` `extractResultUrls`) read only `data.info.result_urls`, `resultImageUrl` and `originImageUrl`; the box poller (`box-kv-poller.js` `_extractResultJsonUrls`) read only `images[].url`, `resultImageUrl` and `result_urls`. Neither read the live Market success shape documented in the KIE contract and in skills 07, 66 and 67: `data.resultJson` is a JSON STRING `{"resultUrls":[...]}` and `data.response` is the parsed copy. A genuine Market success could therefore be recorded `failed` (EMPTY-RESULT). Both sides now accept `response.resultUrls`, the parsed `resultJson.resultUrls`, Suno `response.data[].audio_url` (callbacks: `data.data[].audio_url`) and the existing `images:[{url}]` and legacy `info.result_urls` shapes, de-duplicated.
- The poller also re-derives URLs from the callback `rawData` when an older Worker returned `resultUrls: []`, so the box fix works even before the Worker is redeployed.
- Result-host allowlist: added `file.aiquickdraw.com` (the Veo 4K callback result host in the 07 first-party reference). `tempfile.redpandaai.co`, `tempfile.aiquickdraw.com`, `tempfileb.aiquickdraw.com` and `static.aiquickdraw.com` were already present. Matching is unchanged (exact host or true subdomain); a look-alike such as `file.aiquickdraw.com.evil.com` and bare `redpandaai.co` stay rejected. Suno audio hosts are NOT confirmed; if one is rejected the loud `ALLOWLIST-MISMATCH` log fires and the operator sets `KIE_RESULT_HOSTS`.
- Version drift: `SKILL.md` frontmatter said 1.1.4 and `skill-version.txt` v2.0.1, so this skill's own QC script failed on the version gate (a real drift, not a stale check). `SKILL.md` now has top-level `version: v2.0.2`; Worker `/healthz` and `worker/package.json` now report 2.0.2 (they said 1.1.0), `SUBMITTER-SOP.md` and `DEPLOY.md` follow. A redeployed Worker is now provable by its `/healthz` version. Live probe 2026-10-05 (known-good and fake-path controls): GET /api/v1/chat/credit, POST /api/v1/jobs/createTask, GET /api/v1/models and GET /api/v1/veo/record-info answered; /api/v1/account/balance, /api/v1/user/credits, /api/v1/jobs/create and /api/v1/veo/task returned HTTP 404.

### Tests
- `test/security.test.mjs`: 67 assertions before, 86 after (19 new). New fixtures use the real Market shape (resultJson string, response copy, each alone), the Suno `response.data[].audio_url` shape, KV-path recovery from `rawData`, Worker `/cb` extraction (Market, Suno, legacy), and strict-allowlist cases. 12 of the new assertions fail against the pre-fix code. `qc-kie-callback-relay.sh` now passes (was FAIL: 1 gate).

### OWNER ACTION REQUIRED
- The Worker code changed (`worker/src/index.js`). It must be REDEPLOYED to Cloudflare by the owner (`cd 46-kie-callback-relay/worker && npx wrangler deploy --name kie-callback-relay`, see `DEPLOY.md`). This change set did NOT deploy it. Until then boxes still work through the box-side recovery above, and `/healthz` keeps reporting 1.1.0.
- Risk level: MEDIUM for the Worker (live edge code), LOW for the box poller.

---

## [2.0.0] - July 21, 2026

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

## [v2.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
