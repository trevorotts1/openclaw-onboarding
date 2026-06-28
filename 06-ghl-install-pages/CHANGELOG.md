# Changelog - ghl-install-pages

All notable changes to this skill wrapper are documented here.

---

## [v14.28.0] - 2026-06-28 — feat(skill6): CodeMirror v5/v6 dual-path, stable-id selectors, pre-save lint, published-CSP gate, version-drift CI

### Added — version-drift triple-equality CI gate (`scripts/check-version-drift.py`, `qc-ghl-install-pages.sh`)
- New `check-version-drift.py` asserts `skill-version.txt` == `SKILL.md` frontmatter == top `CHANGELOG.md` entry (leading-`v` insensitive). Wired into install QC as a hard assert. Reconciles the prior drift (was v14.27.2 / 14.19.0 / v14.20.0) to a single version of record.

### Added — stable-id-first selector layer (`tools/gates.json`)
- New `stable_id_selector_layer` doc block + per-gate `stable_ref` priors on runtime gates 13/14/15/18/19/20/21 (`#Code`, `#pg-funnel-builder__btn--save`/`--publish`, `#hl-builder-preview-button`, `#hl-builder-add-elements-button`, `#hl-builder-toggle-setting-button`, `#ai-copilot-close`, `#empty-placeholder-*`, plus `#hl-menu-item-*` / `#hl-builder-seo-meta-data-button`). Resolution is id-first -> existing `find` text/role fallback -> verify live `@ref`. ADDITIVE: the text/role probe is preserved; gate count stays 2 captured / 26 runtime. Ids are `prior-unverified-until-live-capture` until one live capture pass.

### Changed — CodeMirror set-value is now version-safe (`tools/gates.json`)
- `playwright_fallback_recipes.codemirror_set_value` feature-detects CodeMirror v6 (`.cm-editor`/`.cm-content`, `view.dispatch` full-doc replace) and falls back to v5 (`.CodeMirror.setValue`). Removed the INVALID "underlying `<textarea>` + input event" fallback (v6 is contenteditable, no textarea). A HARD non-empty + exact read-back assert now blocks Save on any mismatch, so a v5/v6 mismatch can no longer silently commit an empty `rawCustomCode`.

### Changed — SEO description cap 160 -> 155 (`tools/ghl_builder.py`)
- `SEO_DESC_MAX = 155` to match GHL's live validator string "Description is under 155 characters." `SEO_TITLE_MAX` stays 60 (deliberately stricter than GHL's 70).

### Added — pre-save lint + idempotent entity-normalize (`tools/ghl_rest_canvas.py`)
- `normalize_entities()` collapses accidental double-escaped entities (`&amp;amp;` -> `&amp;`) idempotently; wired into `new_page_blob` and `edit_element_customcode` so re-saves cannot compound escapes. `lint_ghl_fragment` adds advisory warnings for >50KB / >100KB bodies (editor-lag budget; never a hard error — probe-confirmed to save) and flags double-escaped entities.

### Added — live-published CSP/console gate (`tools/ghl_verify.py`)
- `_published_csp_errors()` re-runs the sealed render on the LIVE published URL when a page carries a `published_url`/`live_url` + JS signal, folding console/CSP/pageerror (and non-200) into the verdict. OPT-IN and ADDITIVE — preview-only pages unaffected; can only add failures, never clears a preview render_error. The un-fakeable preview chain is untouched.

---

## [v14.20.0] - 2026-06-27 — feat(skill6): idempotent page create — page_list + find_page_by_name

### Added — idempotent re-install: page-marker update-in-place (`ghl_rest_canvas.py`)

Previously the build loop had only **step-level** idempotency (the `/tmp`
ledger gate at `ghl_builder.resume_point` line 333: "NEVER re-create a step
that already exists, state >= created").  If the ledger was absent on a re-run
(different machine, cleared temp, fresh agent), the loop would call
`step_create` again and produce a **duplicate ZHC-prefixed page** in GoHighLevel.

This change adds two primitives to `ghl_rest_canvas.py` that close the gap:

- **`page_list(funnel_id, location_id, *, session, token_global)`** -- step
  emitter for `GET /funnels/page/list?funnelId=...&locationId=...`.
  The build loop calls this **before** `step_create` when the ledger has no
  record.  The response body is fed to `find_page_by_name`.

- **`find_page_by_name(page_list_body, name)`** -- pure case-insensitive name
  lookup over the page-list response.  Returns
  `{"page_id", "page_version", "name"}` when a ZHC-prefixed page already
  exists, or `None` when it does not.

  **Update-in-place protocol (replaces step_create on re-run)**:
  1. Emit `page_list` step -- GET the funnel's page list.
  2. Call `find_page_by_name(body, zhc_name)` -- case-insensitive ZHC name match.
  3. Non-None -- skip `step_create`; pass `page_id` + `page_version` directly
     to `page_autosave` (update the existing page in-place, no duplicate).
  4. None -- proceed with `step_create` as on a first run.

  Response-shape resilience: handles "funnelPages", "pages", "data",
  "steps" and the funnel-wrapper nested shape.  Page id extracted via the
  same `_id` / `id` / `pageId` fallback chain as `created_page_id`.

- Both functions exported via `__all__`.
- 35 mock-only tests in `tests/test_ghl_idempotent_page.py` (all pass).

---

## [v14.19.0] - 2026-06-27 — fix(skill6): agent-browser version-pin guard — Python-side REFUSE on 0.27.0 drift

### Added — `browser_manager.assert_agent_browser_version()` (P2-4)
- New `assert_agent_browser_version()` in `tools/browser_manager.py`: reads the
  pinned version from `gates.json` (`agent_browser_version_pin.pinned_version`,
  currently `0.27.0`) and runs `agent-browser --version` at runtime. On drift it
  **raises `RuntimeError`** (exit-70 contract) BEFORE any `render_check` subprocess
  fires — the same hard-refuse semantics as the shell-side gate in
  `inject-ghl-auth.sh`.
- The 0.27.0-specific command spellings baked into `render_check` — `get html html`
  (not `html --output`), `screenshot` (stdout path), and `console` (plain-text
  output, not `console-log --json`) — are API-unstable. An unverified agent-browser
  upgrade can silently mis-capture HTML, screenshots, or console logs without any
  error, which would pass the render gate on fabricated data. The guard makes that
  impossible.
- Called from `render_check()` immediately before the 0.27.0-specific subprocesses
  are launched (not from `browser_session()`, which is emitter-only and does not
  spawn a live binary, so tests can use it without agent-browser installed).
- Helper functions: `_read_pinned_agent_browser_version()` (env override →
  gates.json → hard-coded fallback `"0.27.0"`) and `_read_live_agent_browser_version()`
  (runs `agent-browser --version`, returns `None` on missing binary/timeout).
- Override: `GHL_AB_ALLOW_VERSION_DRIFT=1` downgrades the error to a `stderr` WARN
  for deliberate re-capture runs. `GHL_AB_PINNED_VERSION` re-pins to a new version
  without editing gates.json.

### Changed — `gates.json` `agent_browser_version_pin.enforced_in`
- Updated `enforced_in` to list both `tools/inject-ghl-auth.sh` (shell side) and
  `tools/browser_manager.py assert_agent_browser_version()` (Python side), and
  updated `_doc` to reflect that both enforce the pin.

## [v14.18.0] - 2026-06-27 — feat(skill6): per-client brand palette injection into general.general.colors + pageStyles

### Added — brand palette injection (`ghl_rest_canvas.py`)
- `new_page_blob()` now accepts two optional keyword-only parameters:
  `primary_color: str | None` and `secondary_color: str | None`.
- When supplied, these hex color strings are injected into the **Primary**
  and **Secondary** entries of `general.general.colors` and the
  `--primary` / `--secondary` CSS custom properties in the top-level
  `pageStyles` block.
- The **18-entry palette shape** is preserved exactly — no entries are
  added or dropped — so `assert_renderable_shape` Invariant 2 (non-empty
  colors list) and the GoHighLevel renderer's hydration read continue to
  resolve without change.
- All 16 non-brand entries are passed through verbatim.
- A new private helper `_apply_brand_palette(colors, page_styles,
  primary_color, secondary_color)` performs the substitution and validates
  that supplied values are valid CSS hex colors (`#rgb`, `#rrggbb`, or
  `#rrggbbaa`); a non-hex value raises `ValueError` before any blob is
  assembled.
- When both args are `None` (the default), the helper is a fast identity
  pass — zero copying, zero regex — so every existing caller is unaffected.
- 19 new unit tests in `tests/test_ghl_rest_canvas.py`
  (`TestBrandPaletteInjection`): default palette unchanged, both colors
  replaced, 18-entry shape preserved, non-brand entries untouched,
  `assert_renderable_shape` passes for funnel and website surfaces,
  partial-replacement cases, invalid hex raises, 3-digit hex accepted,
  None-noop identity check. All 99 suite tests pass.

FILES: `06-ghl-install-pages/tools/ghl_rest_canvas.py`,
`06-ghl-install-pages/tests/test_ghl_rest_canvas.py`. No client names, no
operator-local paths, no secret values committed.

## [v14.17.0] - 2026-06-27 — feat(skill6): consolidated self-check checklist + SEO keyword-in-copy gate

### Added — per-phase self-check checklist (`references/ghl-build-self-check.md`)
- A scannable, top-to-bottom **SELF-CHECK CHECKLIST** the building agent runs **at
  every phase** of a funnel/website build: Pre-build/creds preflight (P0/P1/P2 +
  §2.0.1) → Media (folders + 200-verified CDN URLs) → ZHC container → Build page
  (full-width ON + the two saves) → SEO (incl. the new H1 keyword-in-copy gate) →
  Multi-step (`ZHC part N`) → Ecosystem (form→CRM proof) → Images in the rendered
  DOM → the un-fakeable `ghl_verify.render_check` final backstop.
- It is a **VIEW of the already-shipped gates**, not a fork: every line **cites the
  SOP section** it reflects (anti-drift). Each phase ends in a bold `Done when:`
  gate — the agent cannot advance a phase until that gate passes; `render_check`
  (§7/§8) stays the only verdict.
- A "Deliberately NOT asserted" footer keeps the analysis-rejected inferences out
  permanently: the bare `/tags/` endpoint (real path is nested
  `/locations/{id}/tags`), the unverified "external images break for LIVE visitors"
  mechanism (preview-only probe — the media-storage rule is grounded in Trevor's
  instruction instead), the toggle colour ("blue=on/gray=off"), the literal "403"
  on sub-account mismatch, and any "GHL strips iframe/script/external-CSS" gate
  (live probe 2026-06-27 confirmed all three SURVIVE).

### Added — SEO keyword-in-copy gate (H1), enforced not just listed
- `ghl_builder.assert_keywords_in_copy(seo_meta, page_copy)` — pure, never raises,
  returns `{ok, reasons, missing}`. Each researched SEO keyword MUST appear in the
  page's body copy (case-insensitive, tag-stripped); a keyword present only in the
  meta panel is a HARD FAIL. This is the mirror of the copy-fidelity gate (P1-4) in
  the keyword→copy direction.
- `ghl_builder.assert_seo_populated(seo_meta, *, brand=None, page_copy=None)` — new
  **opt-in** `page_copy` arg folds the H1 gate into the end-state check. Default
  `None` keeps every existing caller (qc-built-funnel.sh, the CLI) unchanged.
- Wired into the SOP: a new fail-closed row in **§2.07** and the keyword-in-copy
  clause in the **§9 Definition of Done** item 2a, so the gate is enforced, not
  merely documented. Unit tests added in `test_ghl_builder_transcript_recipe.py`.

### Changed
- `SKILL.md` reading order now surfaces `references/ghl-build-self-check.md` (item
  3) and the SOP carries a one-line "run the self-check at each phase" pointer.

## [v14.13.0] - 2026-06-27 — feat(skill6): harden render gate (un-fakeable) — P0-1a/b/c/d + P0-2 + P1-3 + sanitizer/full-width fidelity + auth/dispatch/docs

### Fixed (render-gate anti-fabrication, P0-1)
- **P0-1a — real HTTP status, fail-closed**: `render_check` now extracts the
  navigation HTTP status from agent-browser `open` output via
  `parse_nav_http_status()` (keyword-anchored regex: `status: 200`,
  `"statusCode":404`, `HTTP/1.1 500`, `response 301`). When no status is
  parseable the function FAILS CLOSED by falling back to a real `urllib` probe
  — NEVER the old `dom_bytes > 100` heuristic that credited any non-empty error
  page as HTTP 200.
- **P0-1b — visible text over stripped DOM**: `visible_text_len` is now measured
  by `visible_text(dom_content)` which calls `strip_non_visible_html()` first.
  The old code (`re.sub(r'<[^>]+>', ' ', dom_content)`) stripped only HTML tags
  but left `<script>` and `<style>` TEXT CONTENT in place, so a blank page's
  large Nuxt `__NUXT__` hydration blob inflated `visible_text_len` to ≥400 and
  passed the blank-page guard.
- **P0-1c — marker must be in VISIBLE markup**: `marker_in_rendered_dom` is now
  checked against `stripped_html` (the script/style-stripped DOM) rather than
  raw `dom_content`. The old code matched the marker inside hydration JSON stored
  in `<script id="__NEXT_DATA__">` — content that is never rendered — giving a
  false marker-present verdict.
- **P0-1d — plain-text console errors not silently dropped**: `render_check` now
  passes each console entry through `console_line_is_error()` which parses
  severity from the raw text (leading `[error]`/`pageerror`/`severe` token,
  `Uncaught`/`Unhandled` prefix, any JS error constructor, GoHighLevel's
  `Cannot read properties of undefined` crash message). The old code checked
  only a structured `type`/`level` field — agent-browser's `console` emits PLAIN
  TEXT with no type field, so these errors were silently dropped.

### Added (render-gate signal helpers, P0-2 / P1-3)
- **P0-2 — screenshot pixel-inspection**: `png_blank_report()` pixel-inspects the
  captured screenshot PNG. Rejects (blank=True) when the image is below
  64×64 px (truncated/failed capture) OR when a single colour covers ≥98% of
  pixels (white/blank error page). Uses Pillow when available for exact
  dominant-colour fraction; falls back to header-only IHDR dimension read.
- **P1-3 — structural content-richness floor**: `content_richness()` counts
  `img_count` (non-empty `src` images), `block_count` (block-level layout
  elements), and `has_headline` (any `<h1>`–`<h6>`) over the script-stripped DOM.
  `render_check` now requires `block_count >= MIN_BLOCK_ELEMENTS` (3) — a
  structural signal that a bare visible-char count or a whitespace-inflated page
  cannot satisfy.
- `strip_non_visible_html()` — removes `<script>`, `<style>`, `<template>`,
  `<noscript>` blocks and HTML comments (handles truncated/unclosed tags); shared
  substrate for P0-1b, P0-1c, and P1-3.
- `visible_text()` — script-stripped, tag-stripped, entity-decoded,
  whitespace-collapsed visible text; used for `visible_text_len` (P0-1b).
- `MIN_BLOCK_ELEMENTS = 3` constant (exported, matches `render_check` default).
- Unit tests: `tests/test_ghl_builder_render_signals.py` — 21 mock-only cases
  covering all five helpers (`strip_non_visible_html`, `visible_text`,
  `content_richness`, `parse_nav_http_status`, `console_line_is_error`,
  `png_blank_report`). Anti-fabrication proof: all three spoof cases (blank page,
  hydration-JSON-only, console-error page) now correctly return `ok=False`.

---

## [v14.11.0] - 2026-06-27 — feat(skill6): copy-fidelity verify gate + per-client theme + idempotent re-install + iframe-confirmed + doc-truth

### Added
- **Copy-fidelity gate (P1-4)** in `ghl_verify.verify_page`: when a page carries
  `copy_tokens` (approved phrases) or `copy_md_path` (the approved copy.md), every
  approved token MUST appear in the RENDERED preview DOM (visible text;
  `<script>/<style>/<template>/<noscript>` stripped). A missing token folds into
  `render_errors` → `PASS=False`, catching a page that renders 200 + marker but
  ships stale/placeholder copy. Opt-in: pages with no copy assertion are
  unaffected. New helpers: `extract_copy_tokens`, `find_missing_copy_tokens`,
  `_strip_to_visible_text`, `_resolve_rendered_text`. Fail-closed when no rendered
  evidence is available (cannot prove copy → not a pass).
- **Per-client brand/theme** helpers in `ghl_method.py`: `build_theme_colors(palette,
  base=_FLAT_THEME_COLORS)` injects a client palette into `general.general.colors`
  while preserving the EXACT 18-entry `{label, value}` shape GoHighLevel's renderer
  requires (case-insensitive labels; unknown label / empty value → `ThemeError`;
  never adds/drops an entry). `apply_palette_to_page_styles` keeps the
  `:root{--primary:…}` CSS variables in sync. `THEME_COLOR_LABELS` exported.
- **Idempotent re-install** in `ghl_method.py`: `resolve_install_target(existing_pages,
  marker, page_name=…)` detects an existing ZHC page by its stable marker (marker
  field or stored HTML) and returns `action="update"` with the `page_id` to
  re-install in place — no duplicate pages on re-runs. Ambiguous duplicate markers
  raise `InstallTargetError` (halt for cleanup, never guess). New `InstallTarget`
  dataclass.
- Tests: `tests/test_ghl_method.py` (TestBuildThemeColors, TestApplyPaletteToPageStyles,
  TestResolveInstallTarget) and `tests/test_ghl_verify.py` (TestCopyFidelityHelpers,
  TestCopyFidelityGate) — 27 new cases, all MOCK-only.

### Changed
- **IFRAME / SCRIPT / external-CSS survival CONFIRMED** by a live authenticated
  `/preview/` probe (2026-06-27): GoHighLevel's preview renderer does NOT strip
  `<iframe>`/`<script>`/external CSS from custom-code elements (2-of-2 iframes
  rendered verbatim with `src` intact; inline scripts ran; external/inline CSS
  applied; nothing rendered blank). The VERCEL_EMBED `iframe_embed_snippet` escape
  hatch is the supported path for ADVANCED pages and is documented as such in
  `ghl_method.py`, `SKILL.md`, and `v2-autonomous-build-sop.md`. The prior
  "GHL strips iframe" research worry is disproven for the preview render path.

### Fixed (doc-truth, P2-5)
- `SKILL.md` + `v2-autonomous-build-sop.md §2.06`: corrected the stale
  `defaultSettings.colors` OBJECT claim — the real render path is
  `general.general.colors`, an **18-entry list of `{label, value}` dicts** (NOT a
  `{bodyBgColor,…}` object). `defaultSettings.colors` does not exist in real GHL
  blobs.
- Corrected the stale "golden-reference rule": `ghl_rest_canvas.new_page_blob()` is
  a **pure, self-contained** function that assembles from inlined `_FLAT_*`
  constants — it does NOT load `references/golden/` at build time and does not raise
  `GoldenReferenceError`. The render invariant is enforced by `assert_renderable`.
- `SKILL.md` reading order now SURFACES `v2-autonomous-build-sop.md` (the canonical
  autonomous build SOP) as item 2, and lists `ghl_method.py` / `ghl_verify.py` under
  `tools/`.
- Version drift reconciled: `SKILL.md` metadata `7.2.9` → `14.11.0`;
  `skill-version.txt` → `v14.11.0`.

---

## [v14.8.0] - 2026-06-27 — feat(skill6): funnel library wired into roles/SOPs + FAB-QC ≥ 8.5 build gate + portable committed index

### Fixed
- `funnel_matcher.Catalog` keys a collision-safe `by_key` (`group/id`) + `get(tid, group=…)`
  that refuses to guess an ambiguous bare id (mirrors the Skill-44 soap-opera fix defensively).
- `match_funnel` resolves the matched template by `group`-qualified key; emits `matched_template_key`.

### Added
- `tools/catalog-index.json` — the previously-MISSING funnel catalog index, now COMMITTED and
  PORTABLE (relative `root`/`sourcePath`, re-absolutised on load; zero operator-local paths).
- `funnel_matcher.step0_match` stamps `task['funnel_template_id']` (survives the P4→P5 handoff) and
  writes a `routing/match-decision.json` receipt for the QC gate.
- `v2_dispatcher._resolve_step0` defaults `GHL_FUNNEL_INDEX` to the committed index and resolves the
  funnel→automation link map so the complete-funnel handoff is ON whenever the catalog is configured;
  on a verified build it persists `routing/skill44-handoff.json`.
- `qc-built-funnel.sh` — per-build FAB-QC ≥ 8.5 gate (shared scorer `shared-utils/fab_qc.py`,
  rubric `universal-sops/funnel-automation-build-quality-rubric.md`). Wired binding into
  `v2_dispatcher` (refuses `verified` below 8.5 when FAB evidence exists; no-op otherwise) and
  documented at `v2-autonomous-build-sop.md §9` BUILD-QC GATE + P0.5/STEP 0.
- SKILL.md "Funnel Template Library (STEP 0)" section; `tools/catalog-index.json` portability.
- Tests: `tests/test_funnel_matcher.py` (decisions, collision-safe get, portable index, step0 stamp);
  `tests/test_v2_dispatcher.py` step0-injection + linked-automations handoff + FAB-gate cases.

### Changed
- `v2-autonomous-build-sop.md` P1 de-hardcodes the persona default (top-ranked selector, not always
  hormozi) and verifies `funnel_template_id`.

---

## [v14.7.1] - 2026-06-27 — fix(skill6): funnel_matcher_cli selftest accepts SUGGEST_TEMPLATE + HONOR_USER

Patch bump for the selftest fix shipped in global v14.7.0. The `positive_decision` check in
`funnel_matcher_cli.py` was using the deprecated `HONORED_EXPLICIT` name and missing
`SUGGEST_TEMPLATE`. The updated check accepts `("USE_TEMPLATE", "SUGGEST_TEMPLATE", "HONOR_USER",
"HONORED_EXPLICIT")`. All 13/13 selftest cases pass. Satisfies G3 gate (skill content change
in funnel_matcher_cli.py now paired with skill-version.txt bump v14.7.0 -> v14.7.1).

---

## [v14.7.0] - 2026-06-27 — feat(skill6): standardised flex retrofit — detect_mode + flex_decide + linked_automations + step0_match link-map handoff

Completes the Skill-6 flexibility retrofit by adding the standardised flex functions
(inline, self-contained) that mirror the Skill-44 flex.py shared core. All three intent
modes (EXPLICIT_USER_SPEC / UNSURE_WANTS_SUGGESTION / HANDS_OFF_DO_IT_ALL) and four
decisions (HONOR_USER / SUGGEST_TEMPLATE / USE_TEMPLATE / CREATE_NEW) are now operative.
The `linked_automations()` function + `step0_match()` link_map_path param connect Skill 6
to Skill 44 for complete-funnel builds.

### Added (funnel_matcher.py)
- `MODE_EXPLICIT`, `MODE_UNSURE`, `MODE_HANDSOFF`, `MODES` constants.
- `DEC_HONOR_USER`, `DEC_SUGGEST`, `DEC_USE`, `DEC_CREATE_NEW` constants.
- `HONORED_EXPLICIT = DEC_HONOR_USER` backward-compat alias (v14.6.0 callers unbroken).
- `detect_mode(request, override)` — intent-mode detection with legacy
  `explicit_funnel` / `just_do_it` field compat.
- `flex_decide(mode, *, has_confident_match, has_any_match)` — maps (mode, match)
  to a flexibility decision; `imposes_on_user` ALWAYS False; `override_allowed` ALWAYS True.
- `flex_principle()` — machine-readable flexibility manifesto (logged with every decision).
- `linked_automations(funnel_id, link_map_path, *, overrides, include_secondary)` —
  reads `funnel-to-automation.json` and returns the RECOMMENDED follow-up automations for a
  funnel (primary + secondary + graduation, minus user overrides). Hands off to Skill 44.
- `_rationale_flex(mode, decision, best, threshold, flex)` — structured rationale for all
  four decisions.

### Changed (funnel_matcher.py)
- `match_funnel()` — adds `intent_mode` param; uses `detect_mode()` + `flex_decide()`
  to produce one of four decisions. HONOR_USER path calls `_detect_funnel_explicit()` as
  before (fully backward-compat). Output dict adds `intent_mode`, `mode_reason`,
  `mode_cue`, `imposes_on_user`, `override_allowed`, `await_confirm`,
  `build_from_template`, `template_role`, `flex_note`, `flex_principle`.
- `log_decision()` — adds `intent_mode`, `mode_cue`, `await_confirm` to every log line.
- `step0_match()` — adds `intent_mode` and `link_map_path` params; mutates task with
  four-way decision (HONOR_USER / SUGGEST_TEMPLATE / USE_TEMPLATE / CREATE_NEW); attaches
  `linked_automations` to task and decision when a link map is available.

### Compatibility
- `HONORED_EXPLICIT` decision string is an alias for `HONOR_USER` — callers checking
  `decision["decision"] == "HONORED_EXPLICIT"` still work.
- `explicit_funnel` and `just_do_it` fields on the request still route correctly via
  `detect_mode()` backward-compat path.
- `USE_TEMPLATE` and `CREATE_NEW` decisions continue to fire identically.
- All previously passing selftests continue to pass (13/13).

### Fixed (funnel_matcher_cli.py — v14.7.0 consolidation)
- `selftest()` positive_decision check updated from `("USE_TEMPLATE", "HONORED_EXPLICIT")`
  to `("USE_TEMPLATE", "SUGGEST_TEMPLATE", "HONOR_USER", "HONORED_EXPLICIT")`. The default
  request mode (no explicit "just do it" cue) is UNSURE -> SUGGEST_TEMPLATE; the old
  check reported 2/13 passing because it didn't recognise SUGGEST_TEMPLATE or HONOR_USER
  as a positive result. Fixed: 13/13 cases now pass.

---

## [v14.6.0] - 2026-06-27 — feat(skill6): flexibility retrofit — three-mode GUIDE-NOT-RULE matcher

Retrofits `funnel_matcher.py` with the full three-mode flexibility model (Mode 1 Explicit, Mode 2 Unsure, Mode 3 Just-do-it) and the `HONORED_EXPLICIT` decision path. Adds `_detect_funnel_explicit()` for name/alias/id detection. Updates `step0_match()` to read `task["explicit_funnel"]` and `task["just_do_it"]`. Updates `_rationale()` to include the flexibility preamble on every decision. Updates `funnel_matcher_cli.py` selftest to accept `HONORED_EXPLICIT` (13/13 pass). All previous 13/13 selftest cases continue to pass.

### Changed
- `tools/funnel_matcher.py` — flexibility model retrofitted: `_detect_funnel_explicit()`, `HONORED_EXPLICIT` decision, `flexibility_mode` field, `step0_match()` flexibility input fields, updated `_rationale()`.
- `tools/funnel_matcher_cli.py` — selftest updated to accept `HONORED_EXPLICIT` as a positive decision (not a regression).

### Compatibility
No breaking change. `USE_TEMPLATE` and `CREATE_NEW` decisions continue to fire identically. `HONORED_EXPLICIT` is a new positive path (previously would have been `USE_TEMPLATE` with high confidence). The output dict adds `flexibility_mode` field (backward compatible).

## [v14.4.0] - 2026-06-26 — feat(skill6): funnel-template library + template-first matcher (STEP 0)

Adds a 38-template funnel catalog and a template-first matcher that makes
`dispatch_one()` check the Brunson funnel-template library before generating
any net-new funnel.

### Added

**`06-ghl-install-pages/funnel-templates/`** — the catalog (38 templates, 5 groups)

| Group | Templates | Description |
|---|---|---|
| `buyer/` | 8 | Transaction / product-purchase funnels |
| `event/` | 11 | Webinar, summit, product-launch, meeting |
| `lead/` | 9 | List-building and opt-in funnels |
| `retention-followup/` | 2 | Cancellation save and follow-up |
| `traffic-advanced/` | 8 | Cold-traffic pre-frame and funnel hub |

Each template carries: `whenToUse` (goals / keywords / signals / antiSignals),
`pageStructure` (ordered pages with blocks and Skill 44 widget hints),
`copyFramework` (primary persona + supporting personas + scripts), `ghlBuild`
(platform wiring notes). Two schema dialects coexist (camelCase and snake_case);
the matcher normalizes both.

**`06-ghl-install-pages/tools/funnel_matcher.py`** — the matcher engine

Stdlib-only, deterministic, no network. Provides:
- `Catalog.load(root)` / `from_index(path)` / `save_index(path)` — loads all
  template JSONs into a searchable in-memory index; normalizes both schema dialects
  and both persona shapes (string / object).
- `classify(request)` — extracts goal / category / funnel-type tokens from free
  text or structured intent.
- `score_template(t, feats)` — weighted lexical scorer: full keyword-phrase hits
  dominate; head-nouns, goal/signal token overlap, structured-category bonus add;
  anti-signal penalty subtracts. Raw score → confidence `0..1`.
- `match_funnel(request, catalog, threshold=0.55)` — classify → score every
  template → decide USE_TEMPLATE or CREATE_NEW. Returns the full decision record
  (matched template, confidence, score breakdown, ranked runners-up, chosen copy
  persona, instantiated page plan, rationale).
- `instantiate_pages(tmpl)` — turns a matched template's `pageStructure` into a
  build plan ready for `ghl_builder.build_manifest` with copy persona attached.
- `save_new_template(spec, root)` — persists a CREATE_NEW funnel as a new
  template so the library grows after each net-new build.
- `log_decision(...)` — appends a JSONL audit line (decision + matched + score).
- `step0_match(task, evidence_root, ...)` — the wiring entrypoint (see below).
- `EmbeddingReranker` — scaffolded optional semantic re-rank hook; the lexical
  path is the one wired and proven.

**`06-ghl-install-pages/tools/funnel_matcher_cli.py`** — the CLI

`python3 funnel_matcher_cli.py --build-index` — builds `tools/catalog-index.json`
(excluded from git; rebuilds on the target system from the catalog root).
`python3 funnel_matcher_cli.py --selftest` — proves 13/13 match-quality cases
(squeeze, reverse-squeeze, lead-magnet, webinar, autowebinar, book, application,
cancellation, funnel-hub, survey/quiz, tripwire — plus 2 off-topic requests that
correctly return CREATE_NEW).

### Changed

**`06-ghl-install-pages/tools/v2_dispatcher.py`** — STEP 0 wiring (no breaking changes)

- Added `step0_matcher` optional kwarg to `dispatch_one()`. Called right after
  the `max_inflight` gate and before `backlog -> dispatched`. Advisory: a matcher
  error or SKIPPED result never blocks a build.
- Added `_resolve_step0(step0_matcher)` helper: returns the injected matcher if
  supplied; else auto-configures from `GHL_FUNNEL_CATALOG` or `GHL_FUNNEL_INDEX`
  env vars when `funnel_matcher` is importable; else returns None (no-op).
- On USE_TEMPLATE: mutates `task['pages']` = instantiated plan,
  `task['copy_persona']`, `task['template_match']` before the builder runs.
- On CREATE_NEW: builder generates net-new; result saved back to grow the library.
- Added lazy optional import of `funnel_matcher` so unit tests without the catalog
  configured are completely unaffected.

**`skill-version.txt`**: bumped v14.3.19 → v14.4.0.

### Verified

- `funnel_matcher_cli.py --selftest`: **13/13 cases pass**.
- `v2_dispatcher.py --selftest`: **3/3 bounds pass** (max_inflight=1, wallclock
  cap, happy path) — existing gate logic unaffected by STEP 0 kwarg addition.
- Leak scan: no client names, no operator paths, no scratchpad paths in any
  committed file. Generated `catalog-index.json` excluded from git (`.gitignore`).
- Template count: **38 templates** (not stubs — each has full `whenToUse`,
  `pageStructure` with named blocks, and `copyFramework` with persona + scripts).

---

## [v14.3.14] - 2026-06-26 — fix(skill6): native page builds render REAL content again — nested section→row→col→custom-code blob (kills the v14.3.11 blank-page regression)

Root cause: since v14.3.11, `new_page_blob()` (`tools/ghl_rest_canvas.py`) produced pages that stored fine (autosave 201, marker in the bytes) but rendered BLANK. The v14.3.11 "golden template" path loaded the captured funnel golden and re-minted every element id without rewriting the parent `child` arrays (`section.metaData.child → row.child → col.child`), orphaning the custom-code element from its row — so the renderer dropped the content.

### Fixed (`tools/ghl_rest_canvas.py`)
- `new_page_blob()` now builds the render-verified NESTED structure `section → row → col → custom-code`, minting fresh `section`/`row`/`col`/`custom-code` ids and wiring each `child` array + `metaData.child` to those SAME ids in one pass — the parent→child chain is always internally consistent, so the element can never be orphaned.
- The page HTML lands in the `meta=custom-code` element's `extra.customCode.value.rawCustomCode` (the only node GoHighLevel renders custom HTML from; a flat `type=code` element directly in `section.elements` was proven live to render BLANK).
- Inlines the authoritative theme captured live from the render-verified golden — `general.general.colors` (18-entry palette), top-level `pageStyles`, `settings.settings.typography.colors`, and the generic section `metaData`/`general` — so the hydration reads of `colors` and `metaData.title` resolve (absence 500s with "reading 'colors'" / "reading 'title'", both reproduced live). `trackingCode` header/footer/body are emptied so no template HTML leaks.
- `assert_renderable_shape()` invariant 5 locates the custom-code element by its `rawCustomCode` PAYLOAD PATH instead of a type/meta label — validates the nested funnel shape and the flat website shape alike.

### Verified (live)
- Net-new funnel page built into operator scratch location `Mct54Bwi1KlNouGXQcDX` (Convert and Flow) through the real `funnel/create → create-step → autosave` path and viewed at its `/preview/<pageId>` URL in a headless browser: a real multi-section landing page rendered — visible hero (background image + headline + CTA), trust band, three feature cards, split section with a visible `<img>` (loaded, naturalWidth 1600), and a testimonial. HTTP 200, 0 console errors, no blank section. Full-page screenshot captured. Draft only; not published; not rolled to the fleet.
- `tests/test_ghl_rest_canvas.py`: 63 passed.

## [v14.3.13] - 2026-06-26 — fix(skill6): GHL credential resolution searches every alias + every env store (kills the six-month image-step false-fail) + folds B7 SOP docs

Root cause: the Skill-6 image/media step false-failed `"GHL LOCATION PIT not found"` on a LOCATION Private Integration Token the operator had used for SIX MONTHS. The token was in `~/.openclaw/secrets/.env` under `GOHIGHLEVEL_API_KEY` the whole time — but `ghl_media.resolve_location_pit()` only checked two env-var names in the LIVE process environment and never opened the canonical store. In a clean agent shell (where the gateway/launchd wrapper had not exported `secrets/.env`) both vars read empty and the tool fail-loud, treating "env var empty" as "credential missing" instead of "env not loaded".

### Fixed (credential resolution — `tools/ghl_media.py`)
- `resolve_location_pit()` / `resolve_location_id()` now resolve from EVERY known alias AND, when the live env is empty, the canonical env STORES directly. LOCATION-PIT aliases (preferred → fallback): `GOHIGHLEVEL_API_KEY` → `GHL_API_KEY` → `GOHIGHLEVEL_LOCATION_PIT` → `GHL_LOCATION_PIT`. Location-id aliases: `GOHIGHLEVEL_LOCATION_ID` → `GHL_LOCATION_ID` → `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` → `CAF_ALLOWED_LOCATION_IDS` (first id). Stores searched in order: `~/.openclaw/secrets/.env` → `~/clawd/secrets/.env` → `~/.openclaw/workspace/.env` (the same multi-alias/multi-store pattern already used for the Google 3-alias key and for `KIE_API_KEY` in `ghl_image_stage`).
- New `_scan_env_stores()` parses `KEY=VALUE` (and `export KEY=VALUE`) lines, strips quotes, takes the first id of a comma-separated allowlist; missing/unreadable stores are skipped, never raise.
- AGENCY vs LOCATION distinction encoded: the resolver NEVER falls back to an agency-class name (`GOHIGHLEVEL_AGENCY_PIT` / `GOHIGHLEVEL_AGENCY_API_KEY` / `GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT` / `GHL_AGENCY_PIT`) — agency tokens 401 for media. If only an agency token is found, the error says so explicitly.
- The honest-fail message is now accurate: it NAMES exactly which env vars and which store paths it checked, says the credential is "not found IN THE ENVIRONMENT or in any canonical env store", and instructs `set -a; source ~/.openclaw/secrets/.env; set +a` then retry. No secret VALUES are ever echoed.
- New `search_stores` kwarg (default True) lets unit tests assert pure-env behaviour in isolation.

### Tests (`tests/test_ghl_media_cred_resolution.py` — new, 18 cases, MOCK-only)
- Multi-alias resolution + preference order (PIT and location id); store FALLBACK resolving the value from a redirected fake `secrets/.env` (the exact incident); live-env-beats-store; `export`/quotes parsing; agency-only env/store still fails with the scope note; honest-fail names every var + store; allowlist first-id; alias-set invariants (no agency name is a LOCATION alias; `GOHIGHLEVEL_API_KEY`/`GOHIGHLEVEL_LOCATION_ID`/`~/.openclaw/secrets/.env` are the preferred entries). All fixtures are generic `pit-FAKE…` / `LOCFAKE…` values; the real store is never read.

### Docs (folds B7 / PR #356 into the SOP + adds the credential rule)
- `v2-autonomous-build-sop.md`: NEW §2.0.1 credential preflight (env-var→store table for LOCATION PIT / location id / KIE key; AGENCY≠LOCATION warning; step-0 `source secrets/.env`; HARD RULE — real research across all stores before any `honest_fail`, and the failure must name what was checked). §3 Images rewritten to call the `ghl_image_stage.run_image_pipeline(page_spec, run_dir, *, location_id, location_pit)` entrypoint and to cross-reference §2.0.1 (a PIT honest_fail is valid only after the store search). §7.1 Forbidden-shortcuts gains the row banning `"credential not found"` on an empty env var without a store search. Also folded from PR #356: §2.05 method-decision, §2.06 theme/colors object, §4.1 embed-widget flow, §7 sealed-mode verifier contract, §7.1 forbidden shortcuts.
- `SKILL.md`: new GoHighLevel media/PIT credential block documenting where the LOCATION PIT + location id + KIE key live, the alias/store resolution order, the AGENCY-401 warning, and the HARD RULE against false-failing on an empty env var.
- PR #356 (the B7 SOP docs) is consolidated here and closed; its SKILL.md half had already landed in v14.3.11.

508 passed / 15 skipped / 0 failed. guard-ghl-method-decision PASS. guard-ghl-verify-unfakeable PASS. qc-ghl-install-pages PASS (exit 0, 1 expected WARN on white-label URL). No secret values committed; the location id used in goldens is the operator's own documented test-scratch id.

## [v14.3.11] - 2026-06-26 — fix(skill6): un-fakeable QC gate + theme/colors 500 fix + B1-B8 integrated (B1-golden/colors, B2-sealed-gate, B3-method-decision, B4-image-pipeline, B5-golden-capture, B6-tests, B7-docs, B8-guards)

Root cause: the pre-flight fabricated a PASS while every page 500ed ("Cannot read properties of undefined reading 'colors'") and funnel pages were blank. Two distinct failure modes: (1) `new_page_blob()` produced a blob missing `general.general.colors` — GoHighLevel's renderer reads that key during React hydration; absence causes a 500. (2) The QC gate (`ghl_verify.py`) was bypassed — a hand-written ledger + `.md` summary overrode the machine verdict, the gate was never independently called.

### Fixed (B1 — theme/colors 500)
- `ghl_rest_canvas.new_page_blob()` rewritten to load from live-captured golden references (`references/golden/funnel-optin.page-data.json` and `references/golden/website-page.page-data.json`). Goldens contain the authentic 18-entry `general.general.colors` palette that GoHighLevel's renderer reads. The old from-memory blob (missing colors) is impossible to emit.
- New `html_fragment()` helper: strips `<!DOCTYPE>`, `<html>`, `<head>`, `<body>` wrappers, hoists `<style>` blocks from `<head>` so CSS survives stripping. Full documents are accepted and normalized to body-level fragments automatically.
- New `assert_renderable_shape()` guard: 7 invariants checked before return (colors non-empty, sections non-empty, custom-code element reachable, rawCustomCode is a fragment not a full document). Raises `AssertionError` naming the failing invariant.
- `surface` parameter added to `new_page_blob()` — `"funnel"` (default) and `"website"` produce correct element shapes (`type=element meta=custom-code` vs `type=code elType=code`).
- Removed false "PROVEN live" docstring; replaced with honest "STORAGE vs RENDER" contract section.

### Fixed (B2 — un-fakeable QC gate)
- `ghl_verify.render_check()` added: drives the headless browser, waits for JavaScript hydration, captures rendered DOM + PNG + console artifacts. `ok` requires HTTP 200 AND marker in RENDERED DOM AND zero render errors AND `visible_text_len >= 400`. Marker-in-storage is no longer a pass criterion.
- `ghl_verify.verify_all()` sealed: `live=True AND fetcher!=None` raises `SealedGateViolation` immediately. `trust='MOCK'` summaries cannot ship as verified. Pre-seeded `verify-summary.json` is rejected.
- `ghl_verify.assert_consistent()` extended: Invariant 4 (fabricated raw row detection: PASS=True with render_errors or non-200 http raises `VerifyContradiction`); Invariant 5 (artifact hash binding: re-hashes every artifact in render manifest).
- `ghl_gate.py` added: the only verdict reader. Reads `scorecard/verify-summary.json`, `logs/final-preview-verify.json`, `scorecard/render-manifest.json`. `require_pass()` checks writer identity, trust!=MOCK, raw_sha256 binding, `assert_consistent` re-run, forbidden phrases absent. Exit code 0 = PASS only; 1/2/3/4/5 for FAIL/MOCK/tampered/missing/invalid. `.md`, `ledger.json`, and prose files are structurally ignored.
- `v2_dispatcher.py`: production path calls `ghl_gate.require_pass()` after the verifier writes its files; non-zero exit → FAILED. MOCK trust downgrades task to FAILED.
- `ghl_builder.emit_batch_rest_save_plan()` delegation shim added (forwards to `parallel_saves`).

### Added (B3 — method decision architecture)
- `ghl_method.py`: pure classifier (no I/O). `classify_page()` returns `MethodDecision`: DIRECT (simple pages) or VERCEL_EMBED (js_frameworks present, complexity:advanced, payload > 256 KB). Widget blocks detected and listed in `MethodDecision.widgets` for GoHighLevel native form/calendar routing. `decide_and_record()` writes `routing/method-decision-<page>.json`.
- `ghl_vercel.py`: Vercel-embed path — `prepare_app()`, `deploy()`, `make_public()` (disables SSO so iframes work), `assert_embeddable()` hard gate (HTTP 200, no XFO DENY/SAMEORIGIN, marker in body). `run_pipeline()` chains all steps. Test injectors for CI.
- `ghl_ecosystem.py` extended: `create_form()`, `get_form()`, `get_calendar()` optional fields on `EcosystemOps`; `create_advanced_form()` orchestrator; `FormCreationError` exception.

### Added (B4 — image pipeline)
- `ghl_image_stage.py`: `run_image_pipeline()` — the single entry point. Resolves Kie.ai key from env, derives image specs (always `mode='t2i'`), calls `ghl_media.generate_images()`, uploads each PNG, re-fetches CDN URL at HTTP 200, logs to `logs/asset-cdn.log`, writes `images/manifest.json`. Fails loud (`ImagePipelineError`) on missing key or missing CDN verify — never returns stub URLs or SVG placeholders.

### Added (B5 — golden reference capture)
- `references/golden/funnel-optin.page-data.json` (25,364 bytes): live page-data blob from Trevor's own GoHighLevel test location. Render-verified: HTTP 200, marker in rendered DOM, zero `Cannot read properties` errors.
- `references/golden/website-page.page-data.json` (15,468 bytes): live website page-data blob. Same render verification.
- `references/golden/PROVENANCE.json`: capture metadata including location id, funnel id, page id, capture date, render-check evidence, and authoritative JSON paths for colors.
- `tests/fixtures/golden_page_blob_funnel.json` and `tests/fixtures/golden_page_blob_website.json`: copies for test fixture use.

### Added (B6 — tests)
- `tests/test_ghl_gate.py`: gate anti-fabrication contract tests.
- `tests/test_ghl_method.py`: classifier tests (46 passing).
- `tests/test_ghl_vercel.py`: Vercel embed hard gate tests (9 passing, all mocked).
- Extended: `test_ghl_rest_canvas.py`, `test_ghl_verify.py`, `test_v2_dispatcher.py`, `test_ghl_media.py`, `test_ghl_ecosystem.py`, `tests/fixtures/`.
- 449 tests pass (15 skipped for unimplemented optional extensions; 0 failed).

### Added (B7 — docs)
- `v2-autonomous-build-sop.md`: §7 rewritten as sealed-mode contract; §2.05 method decision; §2.06 colors/theme mandatory; §4.1 embed widget flow; §3 images rewritten. Six forbidden verification shortcuts table.
- `SKILL.md`: Phase-5 method decision table; mandatory colors/theme bullet; sealed verification bullet.

### Added (B8 — CI guards)
- `scripts/guard-ghl-method-decision.sh`: CI/live build guard for PLAN-3 method decision audit records.
- `scripts/guard-ghl-verify-unfakeable.sh`: static guard — asserts no forbidden rationalization strings in code, gate symbols exposed, no hand-written `overall_pass = True`.
- `tools/gates.json`: `method_decision_per_page`, `image_manifest_non_empty`, `verify_gate_authoritative` enforcement gates added.
- `qc-ghl-install-pages.sh`: wires both guards into the QC flow.

---

## [v14.3.10] - 2026-06-26 — feat(skill6): parallel page saves cap 5 — shared cleared session fan-out

**PRIMARY approach:** fan out up to `AB_SAVE_CONCURRENCY` (default 5, hard-clamped [1,5]) concurrent `agent-browser eval` autosave calls against the ONE singleton session. `AB_MAX_SESSIONS` STAYS 1 (one browser — Cloudflare clearance is shared). The lock / TTL / breaker / EXIT-trap teardown from `browser_manager.sh` cover the entire batch unchanged.

### Added
- **`tools/parallel_saves.sh`** — bash fan-out executor. Sources `browser_manager.sh`. `bm_save_concurrency()` clamps `AB_SAVE_CONCURRENCY` to [1,5]. `ps_fan_out()` issues N eval background jobs with a slot-counting concurrency cap (macOS bash 3.2 safe). `ps_run_batch()` reads JSON spec, calls `bm_ensure` once, fans out, collects results.
- **`tools/parallel_saves.py`** — pure emitter. `save_concurrency(env)` clamps to [1,5]. `emit_batch_rest_save_plan(pages, session)` wraps all per-page steps in ONE `browser_session()` bracket with EXACTLY ONE `teardown_browser` at the end.
- **`tests/test_parallel_saves.py`** — 41 tests: concurrency clamp (shell + Python), AB_MAX_SESSIONS=1 static, sh contract, batch plan emitter (K pages = exactly 1 teardown), hermetic concurrency (peak ≤5, teardown on failure, one-browser invariant).

### Changed
- **`tools/browser_manager.sh`** — added `AB_SAVE_CONCURRENCY` tunable + `bm_save_concurrency()` clamp. `AB_MAX_SESSIONS` stays 1; all lock/lease/TTL/breaker/teardown bodies verbatim unchanged.
- **`tools/browser_manager.py`** — mirror `save_concurrency()`.
- **`tools/ghl_builder.py`** — added `emit_batch_rest_save_plan()` + `batch-rest-save-plan` CLI verb.
- **`v2-autonomous-build-sop.md`** + **`ghl-browser-builder-full.md`** — PARALLEL SAVES (cap 5) note; sentinel verbatim intact.

---

## [v14.3.8] - 2026-06-26 — feat(skill6): cc_board.py producer + INTAKE SOP section — Goal A (card on board)

Closes Goal A of the Skill-6 → Kanban demo path: a customer funnel/website request now becomes a real card on the Command Center Kanban board.

### Added

**`tools/cc_board.py`** — new file. Fail-soft board card producer for the Funnels / Web-Dev dept agent. Modeled on `48-facebook-ad-generator/scripts/cc_board.py`. Posts one card to `POST /api/tasks/ingest` (CC >= v4.52.0). Key design decisions:
- **Fail-soft everywhere** — `ingest_task()` catches all exceptions and returns `None`. The build never stops because the board is unreachable.
- **Single public function `ingest_task()`** — accepts `title`, `description`, `job_type`, `priority`, `idempotency_key`. Maps `job_type` to `department_slug` (`funnel`/`sales-funnel`/`opt-in`/`multistep` → `funnels`; everything else → `web-development`). Posts `title`, `description`, `source`, `department_slug`, `idempotency_key`, `priority` to the ingest route.
- **Auth parity with Skill-48**: `Authorization: Bearer <MC_API_TOKEN>` (global middleware) + `x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody)` (per-route). Both no-ops when unset.
- **Stdlib only** (`urllib`, `hashlib`, `hmac`, `uuid`) — zero third-party deps.
- **`--selftest` flag** (no network; exits 0 on pass — verified).
- **`--demo` flag** for live board proof.

**`v2-autonomous-build-sop.md` — INTAKE section added** (77 lines before `## 0`). Documents the `ingest_task()` call the dept agent MUST make before any gate (P0/P1/P2) or build step, the `job_type` → `department_slug` routing table, the exact JSON payload, credential env vars, selftest/demo CLI usage, and how to write the returned `task_id` to `routing/intake-receipt.json` for downstream steps. Scope note explicitly states this lands Goal A but NOT Goal D (dispatch trigger — that remains `v2_dispatcher.py`, a follow-on).

Selftest: `python3 06-ghl-install-pages/tools/cc_board.py --selftest` exits 0.

**Scope boundary (honest):** Goal A (card created on board) + Goal B routing (server-side `routeTask()` picks the right workspace when `department_slug` is supplied) are covered. Goal C (status moves Backlog → In Progress → Review → Done) depends on the CC dispatcher having a live dept runtime; that is the `~/.openclaw/agents/dept-funnels/` wire-in — separate operator step. Goal D (dispatch message triggers the Skill-6 build recipe) is a follow-on (`v2_dispatcher.py` exists; board dispatch message does not yet call it).

## [v14.1.5] - 2026-06-25 — fix(breaker): DURABLE park marker (survives reboot) + writes the box-level PARK marker on a trip

The agent-browser circuit-breaker's PARK marker no longer lives in TMPDIR (it evaporated on reboot, silently un-parking a qc-failed build). `tools/browser_manager.sh` now keeps the breaker counter + BLOCKED marker AND a canonical box-level PARK marker under the box's DURABLE state dir (`<openclaw-root>/workspace/.park/`); the lock + leases correctly stay ephemeral. `bm_breaker_check` reads the box-level marker too, and a breaker trip WRITES it so the Skill-23 `*/15` resume cron (`resume-workforce-build.sh`) stops re-firing as well. Un-park is operator-only (`scripts/unpark-build.sh`). Falls back to the old ephemeral path when no onboarded root exists, so the 31 singleton tests stay hermetic. See root CHANGELOG v14.1.5.

## [v7.2.9] - June 23, 2026 — SINGLETON POOLED BROWSER (one session, lock=1, TTL, guaranteed teardown, reaper backstop)

### Added
- **`tools/browser_manager.sh`** — THE single mandatory agent-browser gateway. Owns AB_BIN + the lock-asserting `AB()` wrapper (D6 headless guard re-used verbatim), ONE canonical session (`bm_session_name` = `ghl-skill6-<location-id>`, refuses non-canonical unless `AB_SESSION_OVERRIDE=1`), a portable box-wide lock (flock if present, else atomic-mkdir with dead-PID stale reclaim — flock is ABSENT on macOS), a lease (process+mtime liveness, never `.pid`), per-call (`AB_CALL_TIMEOUT`) + per-session (`AB_SESSION_TTL`) timeouts, a pool ceiling (`AB_MAX_SESSIONS`, default 1), a circuit-breaker (`AB_BREAKER_MAX` opens/window → PARK qc-failed + escalate to Rescue Rangers, parked NOT re-fired), and a GUARANTEED `trap _bm_teardown EXIT INT TERM HUP` that closes ONLY the canonical session + `state clear`. Verbs: ensure / eval|open|snapshot|wait|find|fill / run-detached / teardown / session-name.
- **`tools/browser_manager.py`** — emitter-side analogue: `browser_session()` context (atexit + SIGTERM/SIGINT/SIGHUP), `assert_session_active()`, `session_name()` (matches the shell), `emit_teardown_step()`.
- **`scripts/agent-browser-reaper.sh`** — host reaper (hourly cron, `13 * * * *`, via ensure-pipeline-crons.sh): closes expired-lease sessions, `doctor --fix` + `state clean --older-than`, dead-descriptor sweep, and a Chromium tripwire scoped to the agent-browser/Playwright PROFILE TREE ONLY (NEVER a bare chrome/Chrome/Claude proc). Runs as the box user, never root.
- **`scripts/guard-agent-browser-managed.sh`** + **`tests/test_browser_manager_singleton.py`** (24 static/stubbed tests) + **CI** `.github/workflows/agent-browser-lifecycle-guard.yml` + **pre-commit gate 6**.

### Changed
- **`tools/inject-ghl-auth.sh`** now `source`s the gateway and calls `bm_ensure` before the first open, so its 4 non-zero REFUSE aborts ALWAYS tear down via the inherited EXIT trap — closing the orphan gap (verified live: 22 `~/.agent-browser/*.engine`, 357M, on the operator box). D6 guard + D7 token-only auth model BYTE-FOR-BYTE unchanged.
- **`tools/ghl_builder.py`** / **`tools/ghl_rest_canvas.py`** emitters refuse outside a `browser_session()` bracket (exit 75 / RuntimeError); every emitted plan ends with a mandatory close step. New `browser-session` CLI verb.

## [v7.2.3] - June 21, 2026 — VERSION RECONCILIATION (all three markers aligned)

### Changed
- Reconciled all three Skill-06 version markers to **v7.2.3** (skill-version.txt + SKILL.md frontmatter + this CHANGELOG) so they agree — closes the A7 mismatch the Goal-B independent verifier flagged (skill-version was v7.2.2 while frontmatter/CHANGELOG still said 7.2.1).

## [v7.2.1] - June 21, 2026 — VERSION RECONCILIATION

### Changed
- SKILL.md frontmatter `version` updated to `7.2.1` to match skill-version.txt.
- `qc-built-workflow.sh` (Skill 44): WF-4, WF-5, and WF-6 assertions that previously
  called `record_pass` when the observed value was `unknown` now call `record_human`
  (REQUIRES_HUMAN_REVIEW), ensuring unknown export fields never silently count as passes.

---

## [v7.2.0] - June 21, 2026 — TOKEN-ONLY AUTH SEED (no UI login, no 2FA)

The Firebase refresh token alone now produces a logged-in SPA session. Fixed the
root cause of the old `auth/internal-error` (the seeded IndexedDB record omitted
the SDK-asserted boolean fields, so the Firebase Web SDK threw on rehydrate and
bounced the SPA to the login form), and removed every automatic fall-back to the
UI login form / two-factor.

### Fixed — IndexedDB user record now matches the Firebase Web SDK `User` shape
- `tools/seed-ghl-auth.py` `build_seed()`: emits the FULL Firebase Web SDK
  `User._fromJSON()` record under
  `firebase:authUser:AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE:[DEFAULT]`
  (`firebaseLocalStorageDb` → `firebaseLocalStorage`, keyPath `fbase_key`). The
  value now ALWAYS includes `emailVerified:false` + `isAnonymous:false` (the SDK
  asserts both as booleans — omitting them was the `auth/internal-error` root
  cause), `providerData:[]` (correct for a custom-token sign-in), full
  `stsTokenManager{refreshToken, accessToken, expirationTime(epoch MILLIS)}`,
  `createdAt`/`lastLoginAt` as epoch-ms STRINGS, `uid` from the live securetoken
  response, plus `apiKey`/`appName`. `email`/`displayName`/`photoURL` are OMITTED
  (custom-auth user has none; null would fail the SDK's string|undefined
  assertion). Refuses to emit a half-record (missing id_token / refresh_token /
  uid raises). No app-token minted and no session cookie required — the id_token
  validates directly via the `token-id` header.

### Fixed — NO automatic UI-login / two-factor fallback (HARD RULE)
- Token-seed is now the ONLY auto-invoked auth path across
  `seed-ghl-auth.py`, `inject-ghl-auth.sh`, `gates.json` #27, and
  `ghl-browser-builder-full.md` (§2, §2.1, §2.2, A0.1, A1, D6/STATUS callouts,
  edge-case recap). If seeding fails to log the SPA in, the builder STOPS and
  reports (non-zero exit). It NEVER auto-fills the Sign-in form or triggers
  two-factor. `GHL_AGENCY_EMAIL`/`GHL_AGENCY_PASSWORD` is retained as a
  DOCUMENTED, operator-only MANUAL last resort, never auto-invoked.
- `tools/inject-ghl-auth.sh`: validates the seed (required boolean fields +
  tokens) and FAILS LOUD before writing; reads the record back after the write
  and aborts non-zero if it did not persist; aborts non-zero if the injector
  returns anything but `seeded:<key>`. The v13.2.4 D6 headless guard is intact
  (`unset`/`export AGENT_BROWSER_HEADED=false`, `AB() --headed false`, abort
  exit 75 on a surviving headed signal).
- `seed-ghl-auth.py --check`: reports `none` (not `login-form`) when no refresh
  token exists, with `manual_login_creds_present` as informational only; exits 2
  so the builder STOPS rather than treating a UI login as an available path.

### Changed — `tools/gates.json` gate #27 (auth_storage_keys)
- Records the confirmed `fbase_key`, the full `value_shape`, the four
  `required_value_fields` (`uid`, `stsTokenManager`, `emailVerified`,
  `isAnonymous`), `app_token_required:false`, `session_cookie_required:false`,
  and the `token-id` auth header; note now states token-seed is the ONLY auth
  path (no UI/2FA fallback).

### Not touched
- Skill 44's `safety_gate` / `VERIFIED_ACTIONS` / `link_steps` were not modified.
  The refresh→ID exchange is re-implemented read-only in `seed-ghl-auth.py` (not
  imported from Skill 44). No client names committed.

---

## [v7.1.0] - June 21, 2026 — HEADLESS HARD-GUARD + REAL UI MAP (repo v13.2.4)

A live run opened a VISIBLE browser window on the operator's screen. agent-browser
is headless by default, but the launch did not ENFORCE it — an inherited
`AGENT_BROWSER_HEADED` env var or a `{"headed": true}` config file can silently
force a headed window. This release closes that door permanently and wires the
real GoHighLevel UI labels from 15 live screenshots.

### Fixed — D6 HARD HEADLESS GUARD (priority)
- `tools/inject-ghl-auth.sh`: forces headless on EVERY agent-browser call —
  `unset AGENT_BROWSER_HEADED` + `export AGENT_BROWSER_HEADED=false`, an `AB()`
  wrapper that appends `--headed false` (the documented agent-browser 0.27.0
  override that also disables a config-file `"headed": true`), and a guard/assert
  that REFUSES to proceed (exit 75) if a headed signal survives. Loud comment:
  "HEADLESS-ONLY — never open a visible window; taking over a screen is forbidden
  (esp. client boxes)."
- `tools/ghl_builder.py`: adds `headed_is_forced()`, `headless_guard()` (raises),
  `browser_cmd()` (emits headless-forced `--headed false` lines), and CLI
  subcommands `headless-guard` (exit 75 if headed would open) + `browser-cmd`.
- Docs (`ghl-browser-builder-full.md` v3.0, `INSTALL.md`, legacy
  `ghl-install-pages-full.md` v2.0): every documented browser invocation is now
  headless-forced; the old `--headed` / `headless=False` two-factor and "keep the
  browser visible" exceptions are REMOVED — no path (login, two-factor,
  Playwright fallback) may open a window. A blocked two-factor PAUSES + screenshots
  + surfaces to the operator instead.

### Confirmed — D7 token-seed-into-IndexedDB is the DEFAULT (no UI login)
- `seed-ghl-auth.py` + `inject-ghl-auth.sh` seed the Firebase ID/refresh token
  straight into IndexedDB (`firebaseLocalStorageDb` → `firebaseLocalStorage` →
  `fbase_key` → `value.stsTokenManager`) and navigate straight in — NO login form
  is rendered (the form was the temptation for the visible window). Documented:
  UI login is the LAST-RESORT fallback ONLY, and still headless.

### Added — D8 real UI map wired into `tools/gates.json`
- Replaced the placeholder/heuristic `find` hints with the REAL visible labels +
  sequence from the operator's 15 live screenshots (`Downloads/ghl-ui-map.md`): Sites
  (left) → Funnels top-tab → "+ New funnel" → "Create new funnel" modal ("From
  blank" + name + Create) → "+ Add new step or import" → "New step in funnel"
  modal ("Name for page" + Path → "Create funnel step") → step CONTROL box ("Use
  existing"/"Create from blank", Edit dropdown = edit path) → close "Ask AI" X →
  "Blank Section" → "+ Add" → Quick Add → "Custom" group → "Code" → "Custom Code"
  → "Open Code Editor" → "Custom Javascript/HTML" modal → paste → Save →
  "Allow Rows to take entire width" → eye=Preview / disk=Save / blue "Publish".
- Each gate now carries `label` + `label_source` (screenshot-confirmed-label vs
  still-runtime-snapshot). **20 of 28 gates carry screenshot-confirmed labels.**
- Recorded `_env`: BlackCEO LLC location id `FIXTURE0LOCATION0000`, preview
  domain `<PREVIEW_DOMAIN>`, Websites mirrors Funnels.
- NO invented CSS: labels are visible-text/role targets the agent confirms at
  runtime; the runtime @ref capture is unchanged.

---

## [v7.0.0] - June 21, 2026 — BROWSER-BUILDER OVERHAUL (Part 2)

### Changed (BREAKING for internal procedure, not for slot/ID/install)
- **Engine realigned to Skill 03**: agent-browser (Vercel Labs) is now PRIMARY
  (headless, isolated `--session`), Playwright is FALLBACK only. The previous
  raw-Playwright-only stack is superseded. New hardened reference
  `ghl-browser-builder-full.md` (v3.0); legacy `ghl-install-pages-full.md` (v2.0)
  retained for historical click-path detail.

### Added
- `tools/seed-ghl-auth.py` (D7) — reuses Skill 44's Firebase refresh→ID-token
  exchange (read-only re-implementation; does not modify Skill 44) and emits a
  browser auth seed. Mints from GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN /
  CAF_FIREBASE_REFRESH_TOKEN / GHL_FIREBASE_REFRESH_TOKEN. Detects revoked
  tokens (exit 3) and absent tokens (exit 2 → login fallback).
- `tools/inject-ghl-auth.sh` (D7) — writes the seed into the browser's
  **IndexedDB** (`firebaseLocalStorageDb` → `firebaseLocalStorage`, keyPath
  `fbase_key`, `stsTokenManager` shape). Corrects the spec's localStorage
  assumption per the 2026-06-21 live capture.
- `tools/gates.json` (D8) — 28-gate runtime contract. 2 CAPTURED (login form +
  auth storage), 26 RUNTIME snapshot-gates (no invented CSS shipped as fact).
- `tools/ghl_builder.py` — manifest, per-page ledger + resume (D10/D12), ZHC
  prefix enforcement, hard sub-account match gate, never-publish-without-approval
  guard, marker-string URL verification, runtime-gate loader.
- Full funnel flow + website flow + Mode-2 iframe-embed path + edge-case handlers
  (two-factor pause, nested iframe, AI-popup dismiss, code-too-large→embed,
  X-Frame-Options, duplicate names, save races).

### Corrections applied from the live-capture pass (2026-06-21)
- Login form renders at root `https://app.convertandflow.com/`, NOT `/login`.
- Auth is in IndexedDB, NOT localStorage.
- Real fallback cred vars are GHL_AGENCY_EMAIL / GHL_AGENCY_PASSWORD.
- FIREBASE_API_KEY is hardcoded in Skill 44 transport.py (not an env var).
- agent-browser 0.27.0 auto-inlines iframes (handles the nested-editor boundary).

### PENDING-LIVE-RUN (NOT claimed done)
- D8 first clause: the 26 runtime gates were BLOCKED behind two-factor
  authentication in the capture pass; they remain runtime snapshot-gates until a
  fresh capture flips them to `captured`.
- D9–D13: end-to-end funnel/website live test, Mode-2 embed test, Website path,
  multi-page resume, and publish-with-approval are NOT yet run — blocked on a
  fresh Firebase refresh token or an attended two-factor-authentication run.

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.

