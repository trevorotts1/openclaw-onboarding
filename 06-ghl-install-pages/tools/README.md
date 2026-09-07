# Skill 06 tools/ — index by category

One line per tool: what it is + when to reach for it. Files grouped by role; alphabetical within group. Selector tables live in the `SELECTORS-LIVE-*.md` docs and `selectors-live*.json` at this directory root (see the iframe group for the drag-side constant).

## Auth (token seed + tiered fallback)

- `ghl_auth.py` — the GHL auth orchestrator and single entry point; reach for it first whenever a build needs a logged-in session.
- `ghl_auth_fallback.py` — Tier-2 ONLY home of all GHL login/2FA code; touch only when a gated Tier-2 run is explicitly authorized.
- `ghl_login_browser.py` — Tier-2 only headless browser driver behind the fallback; paired with `ghl_auth_fallback.py`.
- `inject-ghl-auth.sh` — seeds a logged-in GHL session into an agent-browser profile; use after minting a fresh token.
- `seed-ghl-auth.py` — mints a fresh Firebase ID token/refresh seed and writes the session; Day-0 Step 3 verification starts here (`--check`).

## Build (page/funnel/surface builders + routing)

- `funnel_engine_selector.py` — shared STEP-0 engine selector for funnel builds; run it before choosing a build rail.
- `funnel_matcher.py` — template-first funnel matcher; use to pick which `funnel-templates/` layout a request maps to.
- `funnel_matcher_cli.py` — CLI front-end for `funnel_matcher.py` when matching from a shell.
- `ghl_builder.py` — engine-agnostic orchestration helpers (ledger write/verify/may-publish); builders route through it.
- `ghl_community_builder.py` — browser-control builder for GHL communities (groups + channels).
- `ghl_course_builder.py` — browser-control builder for courses in the Memberships area.
- `ghl_form_builder.py` — native GHL form builder (browser drag rail).
- `ghl_pipeline_builder.py` — browser-driven pipeline (opportunities) builder.
- `ghl_rest_canvas.py` — cracked GHL internal-SPA REST surface helpers; additive API lane beside the browser rail.
- `ghl_survey_builder.py` — native GHL survey builder (browser drag rail).
- `ghl_survey_rest.py` — REST lane for survey payloads when the drag rail is not viable.
- `ghl_workflow_builder.py` — gated, managed Automations (workflow) builder.
- `v2_dispatcher.py` — the bounded backlog dispatcher for autonomous funnel/website builds; the build entry point refuses to start without fresh capability JSON.

## Verify (gates, verdicts, receipts)

- `gates.json` — runtime selector-gate registry (captured + snapshot gates); the builder consults it before acting on gated UI nodes.
- `ghl_gate.py` — un-fakeable build-verdict reader; call it to load the verdict that QC asserts on.
- `ghl_verify.py` — the one canonical build-verifier; run it before publishing anything.
- The `qc-*.sh` scripts at the skill root (`qc-ghl-install-pages.sh`, `qc-built-funnel.sh`, `qc-built-form.sh`, `qc-built-community.sh`, `qc-built-course.sh`) — install/build QC gates; run the matching one after every build.

## CC (Command Center board hookup)

- `cc_board.py` — producer-side Command Center board caller (FAIL-SOFT card ingest); call it to post one build card; failure never blocks the build.

## Iframe (drag/drop + survival)

- `fallback-ladder.json` — unified browser→API→MCP attempt-order declaration per build surface; audit drift against it.
- `ghl_iframe_drag.py` — shared frame-scoped coordinate-drag primitive; the `IFRAME_SELECTORS` constant (kind → selector map) lives here.
- `ghl_iframe_dragdrop.py` — cross-origin-iframe drag/drop + ref-less-tab fallbacks; reach for it when the same-origin drag primitive reports a cross-origin canvas.
- `iframe_router.py` — the SINGLE adaptive iframe entrypoint (`route_drag`/`route_click`): picks the AB ladder vs Playwright CDP from the capability receipt (`iframeDrag.available`); multi-iframe ambiguity and a stale `frame_epoch` fail closed — route through it instead of hand-picking a lane.
- `iframe-survival-targets.json` — target list for the weekly iframe-survival probe run by `ghl_selector_drift_probe.py`. Ships EMPTY by design: an empty list is a valid clean run, but a zero-target pass proves nothing (loud-empty WARN in the report); the operator populates real published-page URLs from the operator TEST sub-account on the cron box.

## Capability (probe + browser lifecycle)

- `browser_manager.py` — Python analogue of `browser_manager.sh`, scoped to the same singleton session contract.
- `browser_manager.sh` — source it and call `bm_ensure`: breaker-check → lock → lease → TTL → open, with automatic EXIT-trap teardown; always bracket agent-browser calls with it.
- `ghl_ab_executor.py` — agent-browser 0.27.0 ANCHOR→EXECUTOR resolver; route every builder click/fill through it so Playwright-style anchors become valid `find`/`eval` invocations.
- `capability_probe.py` — SHIPPED (P0-6): probes the host and writes `working/skill6-capability.json` with the selected lane + fallback chain and per-lane availability (booleans only — never secret values); `--reprobe` refreshes the receipt; Day-0 acceptance is `selectedLane != null`.
- `openclaw_browser_adapter.sh` — Lane 2 adapter mapping builder verbs onto `openclaw browser …`; runs ONLY when the probe selected `openclaw_managed_browser` AND `lanes.openclaw_managed_browser.cliWorks` is true (refuses exit 75 otherwise) — NEVER selected by default.
- `cua_last_resort_adapter.sh` — CUA/computer-use last-resort CONTRACT wrapper (never a driver): reads the probe's CUA lane fields and, only behind `GHL_SKILL6_ALLOW_CUA=1` explicit operator opt-in, writes a waiver receipt; nothing launches a browser or drives a pointer.