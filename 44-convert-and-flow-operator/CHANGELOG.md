# Changelog — convert-and-flow-operator (Skill 44)

## [1.0.6] - 2026-06-11 — fix: install auto-applies CORE_UPDATES + de-dup wrapper (single source) + CI install-path test

### Fixed (install integrity — root cause of boxes not knowing skill 44 is installed)
- **CORE_UPDATES were never auto-applied by INSTALL.md.** The "Done When" checklist listed
  the sentinel as a requirement, but no Action step actually wrote it. Agents on boxes where
  skill 44 was installed pre-this-fix had no `<!-- skill:44-convert-and-flow-operator:core-update-applied -->`
  in AGENTS.md / TOOLS.md / MEMORY.md, so the agent had no knowledge of Tier 0 and
  fell through to MCP on every GHL op. Added **Action 7** to INSTALL.md: idempotent script
  (guard checks for sentinel first) that appends the exact CORE_UPDATES.md blocks to
  AGENTS.md, TOOLS.md, and MEMORY.md automatically at install time.

### Fixed (wrapper single source — eliminates heredoc drift)
- **INSTALL.md Action 3 re-declared the wrapper as an inline heredoc**, creating a second
  copy of the wrapper logic that could silently diverge from `tools/engine/caf` (exactly how
  the `gohighlevel.main` bug in PR #167 happened: the engine wrapper was correct but the
  heredoc was stale). Action 3 now `cp`s the committed `tools/engine/caf`,
  `tools/engine/convertandflow`, and `tools/engine/ghl` wrappers to `$CAF_DIR/` instead of
  re-writing them inline. Single source — one place to edit wrapper logic, zero drift.

### Added (CI install-path test)
- **`.github/workflows/skill44-install-path.yml`** — new CI job `skill44-install-path` with
  two checks that run on every PR touching `44-convert-and-flow-operator/**`:
  1. `install-path-wrapper-exec` — asserts `tools/engine/caf` exec line is
     `python -m cli_anything.gohighlevel` (not `.main`), and that the `convertandflow`/`ghl`
     wrappers match. Fails on pre-#167 exec line. Guards against entrypoint drift.
  2. `install-path-core-updates-action` — asserts INSTALL.md contains the CORE_UPDATES
     auto-apply action (sentinel grep + `skill:44-convert-and-flow-operator:core-update-applied`
     present in Action 7 block). Fails without this fix.
  The workflow is additive — does not replace `skill44-e2e.yml`.

### QC (qc-convert-and-flow.sh)
- Two new static assertions in Section S:
  - `INSTALL.md contains CORE_UPDATES auto-apply action (Action 7)`
  - `INSTALL.md Action 3 uses cp (single-source wrapper, no inline heredoc)`

## [1.0.5] - 2026-06-11 — fix: INSTALL.md Action-3 heredoc used stale `cli_anything.gohighlevel.main` entrypoint (no `main.py` in engine 2.1.0)

### Fixed (install path)
- **INSTALL.md Action-3 heredoc** exec line corrected from
  `exec "$VENV/bin/python" -m cli_anything.gohighlevel.main "$@"` to
  `exec "$VENV/bin/python" -m cli_anything.gohighlevel "$@"`.
  Engine 2.1.0 (shipped in PR #163) removed `main.py` — the package entry point
  is now `__main__.py` which routes to `gohighlevel_cli:main`. The stale
  `.main` suffix caused `ModuleNotFoundError` on every `caf` invocation on any
  box installed with the 2.1.0 engine via INSTALL.md. The three committed wrapper
  scripts (tools/engine/caf, convertandflow, ghl) were already correct and are
  unchanged.

### Root cause
  Engine CLI was bumped 2.0.0 → 2.1.0 in PR #163; `main.py` was removed but the
  INSTALL.md heredoc was not updated to match. Boxes receiving the 2.1.0 engine
  via the heredoc install path broke silently; boxes that copied the committed
  wrapper scripts (e.g. hand-patched) were unaffected.

## [1.0.4] - 2026-06-11 — fix: retry-once on the transient Firebase token-refresh error for workflow writes

### Fixed (engine `internal/transport.py`)
- **Transient Firebase token-refresh failure now auto-retries ONCE before
  surfacing.** The securetoken refresh exchange can return `None` as a ONE-TIME
  transient (observed live on a managed box) and succeed on the very next call;
  the old code raised `TOKEN_REFRESH_FAILED` on the first `None`, falsely nudging
  the owner to re-grab a token that was still valid. `InternalTransport.get_token()`
  now retries the exchange **exactly once** on a `None` result, and only raises
  `TOKEN_REFRESH_FAILED` if the second attempt also fails. This is one retry, not
  a loop, and is disjoint from the existing request()-level 401/403 retry.

### Preserved (NOT weakened)
- The PR #163 build-path **fail-loud** behaviour is untouched: a downstream HTTP
  error dict (e.g. the 400 `corrupted order` save rejection) is returned UNCHANGED
  by `transport.request()` and never triggers a token-refresh exchange. Only a
  `None` from the securetoken exchange (transient) is retried; only a `None` from
  `_do_request` (401/403 auth signal) drives the separate one-shot `force_refresh`.

### Added
- `tools/engine/tests/test_token_retry.py` (`TestTokenRefreshRetryOnce`):
  - transient failure -> ONE retry -> success (exactly 2 exchange attempts);
  - persistent failure -> `TOKEN_REFRESH_FAILED` surfaced after one retry (exactly
    2 attempts — proves no loop);
  - happy path -> single attempt (never retried);
  - HTTP `_error` dict (400 corrupted-order) -> surfaced unchanged, no refresh
    triggered (guards the PR #163 fail-loud).
  The two retry tests FAIL on pre-1.0.4 transport and PASS after the fix.

## [1.0.3] - 2026-06-11 — fix: `workflows build` now ADDS action ordering and FAILS LOUD on rejected save; opportunities list snake_case params; payments list alias

### Fixed (CRITICAL — engine `workflow_builder.py`)
- **Bug 1a — `workflows build` omitted action ORDERING on the save PUT** (GHL rejected with
  400 `corrupted order`). `CampaignBuilder._create_workflow` now runs `link_steps()` on the
  plan templates ONCE up front and uses that linked copy (carrying `order`/`next`/`parentKey`)
  for the Step-2 first-step link, the Step-3 step-save PUT body, AND the Step-4 sync PUT.
  Previously `link_steps` was defined but never called on the build path, so the very first
  save PUT had zero execution chain and GHL rejected it.
- **Bug 1b — `workflows build` SWALLOWED a non-2xx save and printed `Steps: 0, Errors: 0`
  (false success, exit 0).** A rejected step-save PUT (transport returns
  `{"_error": True, "http_code": 400, ...}`) is now captured as a real error string
  (including HTTP code + message), returned from `_create_workflow`, and appended to
  `stats['errors']` UNCONDITIONALLY (not gated on the workflow-shell id). The CLI
  (`workflows build` / `workflows create` / `workflows create-n8n`) now prints the error
  summary to stderr and exits non-zero whenever `stats['errors']` is non-empty.

### Fixed (engine CLI `gohighlevel_cli.py`)
- **Bug 3 — `opportunities list` 422 from camelCase params.** `GET /opportunities/search`
  now sends snake_case `location_id`/`pipeline_id` (the one search endpoint that diverges
  from the camelCase convention). The create/update BODIES (camelCase) are unchanged.
- **Bug 4 — `payments` had no `list` verb.** Added a thin `payments list` alias that
  forwards to `payments transactions`, so the uniform `<group> list` pattern works.
  Explicit `transactions`/`orders`/`invoices` verbs are unchanged.

### Changed
- Engine CLI version bumped `2.0.0` -> `2.1.0` (behavior change: build applies ordering and
  fails loud on a rejected save).

### Added
- Regression tests `TestBuildFailsLoudAndEmitsOrdering` in
  `tools/engine/tests/test_e2e_unit11.py`:
  - TEST A asserts a rejected step-save exits non-zero with the 400/`corrupted order`
    cause surfaced (guards the exact pre-fix Steps:0/Errors:0/exit-0 false-success shape).
  - TEST B asserts the FIRST (step-save) PUT body carries `order` `[0,1,2]` plus
    `next`/`parentKey` links — proving `link_steps` ran BEFORE the save PUT.
  Both tests FAIL on pre-fix main and PASS after the fix.
- `qc-convert-and-flow.sh` static asserts for the build-path `link_steps`, CLI fail-loud,
  snake_case opportunities params, payments list alias, the regression test, and the
  `convertandflow`/`ghl` wrapper auto-seed parity.

### Hardening (consistency, not a blocker)
- `tools/engine/convertandflow` and `tools/engine/ghl` wrappers now apply the same
  `CAF_ALLOWED_LOCATION_IDS` auto-seed-from-`GHL_LOCATION_ID` logic that `caf` got in 1.0.2,
  so a blank whitelist never silently blocks all writes on any of the three runtime wrappers.
- `INSTALL.md` Action 3 installed wrapper now exports `CAF_ALLOWED_LOCATION_IDS` /
  `CAF_DRAFT_ONLY` / `CAF_DRY_RUN` (the exact names `safety_gate.py` reads) instead of the
  `GHL_`-prefixed names the gate ignores — matching the shipped engine wrappers.

### Not changed (safety gate preserved exactly)
- Fail-closed location whitelist, approval gate, and dry-run refusals (all `sys.exit(1)` on
  `SafetyRefused`). Draft-only default. `STRIP_KEYS`. Transport 401 retry-once / 429 no-retry.

## [1.0.2] - 2026-06-11 — fix: CAF_ALLOWED_LOCATION_IDS auto-seeds from GOHIGHLEVEL_LOCATION_ID at install

### Fixed
- `tools/engine/caf` (engine wrapper): `CAF_ALLOWED_LOCATION_IDS` no longer defaults to
  blank, which silently blocked every write on a fresh single-location install. When neither
  `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` nor `CAF_ALLOWED_LOCATION_IDS` is set, the wrapper now
  seeds the whitelist from `GHL_LOCATION_ID` (i.e. the client's own location) and emits:
  `[caf] Allowed write locations set to <id>; add more in CAF_ALLOWED_LOCATION_IDS`
- `INSTALL.md` Action 3 (installed wrapper written to disk): same auto-seed logic applied
  so the problem cannot re-emerge after a fresh install.
- `INSTALL.md` Action 5 (credential wiring step): now explicitly wires
  `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` via `openclaw config set` to `$GOHIGHLEVEL_LOCATION_ID`
  as the initial value, matching the auto-seed logic.

### Added
- `INSTALL.md` "Note: Write-location whitelist auto-seed" section explaining the behaviour,
  the log line, and how to add additional sub-account IDs for multi-location setups.

### Not changed
- Draft-only default (`GOHIGHLEVEL_DRAFT_ONLY=true`) untouched.
- Approval gate untouched.
- Engine internals untouched.

## [1.0.1] - 2026-06-11 — Chrome extension: switch to load-unpacked (no Chrome Web Store)

### Changed
- Chrome extension delivery method: NOT publishing to the Chrome Web Store.
  Clients load the extension unpacked via chrome://extensions → Developer mode ON →
  "Load unpacked" → select tools/chrome-extension/.
- INSTALL.md: added Action 5b with full load-unpacked steps (get folder, install,
  grab token, store as GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN, reload after edits).
- SKILL.md: added "Chrome Extension: Token Grabber" section documenting the no-web-store
  decision, what the extension does (zero network calls, IndexedDB reader), and the
  tools/chrome-extension/ file manifest.
- tools/chrome-extension/: added as top-level client-facing copy of the extension
  (manifest.json, popup.html, popup.js, icon48.png — identical to the zip the operator
  ships). Skill is now self-contained.

## [1.0.0] - 2026-06-10 — Initial release

### Added
- Full Tier 0 GHL operator: caf/convertandflow/ghl CLI wrapper over the de-branded
  Convert and Flow engine (Jay's zip, stripped of Nextcloud/Blotato, de-branded builders,
  Chrome extension rebranded, UNIVERSAL templates).
- Token-aware routing: PIT for standard ops; Firebase refresh token for workflow writes;
  graceful fall-through to Tier 4 when Firebase token absent.
- Write-safety posture: dry-run, draft-only default (GOHIGHLEVEL_DRAFT_ONLY=true),
  location whitelist, approval gate, ZHC- standing approval.
- Workflow-write data rollback: pre-write snapshot before every mutation; `workflows restore`.
- TRINITY gate: any conversational workflow build auto-invokes skill 38; qc-convert-and-flow.sh
  calls qc-trinity-registry.sh as a hard gate.
- Dependency-first contract from skill 41: refuses to build if dependencies don't exist.
- Engine vendored at tools/engine/ (from skill44-build/engine).
- Platform overlays: platform/mac/ (venv at ~/.openclaw/tools/..., auto-re-grab recipe) +
  platform/vps/ (venv at /data/.openclaw/tools/..., owner-nudge on expired token).
- Client-facing plain-language auto-re-grab disclosure in INSTALL.md (binding transparency).
- qc-convert-and-flow.sh with assertions for all acceptance criteria.
