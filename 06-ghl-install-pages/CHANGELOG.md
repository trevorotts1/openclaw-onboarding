# Changelog - ghl-install-pages

All notable changes to this skill wrapper are documented here.

---

## [Unreleased] - 2026-07-10 - Command Center / Kanban tightenings (Skill-6 Bulletproof U9 §7)

Branch **skill6-bulletproof-build-cckanban** (off skill6-bulletproof-build). Unit **U9**
of the Skill-6 Browser-Control Bulletproof spec. Tightens how every browser build reports
to the Command Center board — one card through `review`, QC scores emitted into the card
payload, machine-parsable failure taxonomy, and lock-wait visibility. All additive and
FAIL-SOFT (a board outage never blocks a build); no existing public call signature changed.

- **§7.1 Multiple deliverables per build.** `cc_board.BuildPhaseDriver` gains
  `deliverable(url, meta)` (non-terminal, repeatable — register a preview URL, an embed
  snippet path, a survey/community URL) and `review()` (the single terminal move to
  `review`). `artifact()` is retained unchanged as the one-shot `deliverable()+review()`
  convenience so existing callers (survey builder) are byte-compatible.
- **§7.2 QC score emission into the card.** New `cc_board.post_qc_score(task_id, score,
  gate, passed, scorecard_path)` posts a `completed` activity `QC: <score>/10 — <gate>
  [PASS|FAIL]` with the score/gate/verdict/scorecard-path in the activity **metadata** — the
  single source the CC QC sweep reads to promote `review → done` (no re-scoring drift).
  `BuildPhaseDriver.qc(...)` is the driver-level shortcut (allowed AFTER `review()`, since QC
  runs on the review column). `qc-built-form.sh` and `qc-built-funnel.sh` now emit their
  verdict to the card when `CC_TASK_ID` is exported (opt-in, fail-soft): the render gate maps
  PASS→10.0 / FAIL→0.0; the funnel gate reads the real 0–10 `score` from a read-only FAB
  re-score and takes the PASS/FAIL from the composite exit code. New `cc_board.py --emit-qc`
  CLI backs both gates.
- **§7.3 Failure taxonomy on the card.** `BuildPhaseDriver.fail(reason=...)` prefixes the
  `blocked`/`backlog` note with one of `AUTH-STOP | SELECTOR-MISS | RATE-LIMIT |
  TOKEN-CONTEXT | PARKED | VERIFY-FAIL` (new `_CC_BLOCK_REASONS`) and attaches a
  `block_reason` metadata field, so the board is queryable for fleet-wide failure patterns. A
  reason outside the taxonomy is logged and the note posted un-prefixed (never a fabricated
  category).
- **§7.4 Queue visibility.** New `cc_board.post_queue_wait(task_id, holder_session)` (and
  `BuildPhaseDriver.queued(...)`) parks a card at `pending_dispatch` naming the session that
  holds the box-wide browser singleton lock, so a wait is visible, not mysterious.
- **Tests.** New `tests/test_cc_u9_tightenings.py` (recorder-based, zero network) asserts the
  exact wire payloads for all four tightenings; `cc_board.py --u9-selftest` mirrors it as a
  dependency-free rung folded into `--selftest`. `_CC_BLOCK_REASONS` and the `done`-hard-block
  are drift-guarded. Producer/consumer contract unchanged: CC ≥ v4.52.0 (now v5.0.0).

---

## [v17.0.35] - 2026-07-05 - copy-fidelity gate flipped opt-in → opt-out + FAB-QC fires on engine-routed builds (FIX-COPY-02, T-w1-copy-fidelity)

Train **T-w1-copy-fidelity** (Wave-1). Fix ID: **FIX-COPY-02**. The two "real" copy gates were no-ops
exactly where the flagship copy ships. Both are now binding by default.

- **FIX-COPY-02(a) — FAB-QC now fires on engine-routed builds.** `tools/funnel_engine_selector.py`:
  a `ROUTE_TO_ENGINE` decision now writes `routing/match-decision.json`
  (`flex_decision:"ROUTE_TO_ENGINE"`, `template_path` → the engine's structure JSON), the receipt the
  FAB producer keys on. `tools/v2_dispatcher.py` `_emit_fab_artifact` is now engine-aware: on the
  engine route it echoes the engine `copy_ledger.json` into `build/fab-artifact.json` so the shared
  `≥ 8.5` FAB-QC copy-substance overlay RUNS (was `ran:False` — a silent skip) on the flagship
  Signature-Funnel / Sales-Page products. `shared-utils/fab_artifact.py`: new
  `build_funnel_artifact_from_copy_ledger()` normaliser that echoes the real per-section copy.
- **FIX-COPY-02(b) — copy-fidelity render gate flipped OPT-IN → OPT-OUT.** `tools/ghl_verify.py`:
  `_required_copy_tokens` now falls back to the run's conventional APPROVED copy (`routing/copy.md` /
  `copy.md` / an engine `copy_ledger.json`) when a page carries no explicit `copy_tokens`/
  `copy_md_path`, so every verified page is copy-fidelity-gated by default. A page opts out with
  `copy_fidelity:false`; a run with no approved copy on disk resolves no tokens (marker-only callers
  unaffected). New `extract_copy_tokens_from_ledger()` handles the engine ledger shape.
  `tools/ghl_builder.py`: `emit_rest_save_plan` gained a `copy_md_path` arg it stamps on the
  `verify_preview` step + plan (explicit per-page copy provenance).
- Full `tools/tests/` suite green (961 passed / 15 skipped); `tests/unit/fab-artifact.test.py` green.

## [v17.0.34] - 2026-07-05 — feat(image rail): DIU style-card block 8 + optional per-entry aspect_ratio (T-w1-06-ghl-rail)

Wave-1 train T-w1-06-ghl-rail — FIX-XC-02c, FIX-XC-05c, FIX-IMG-03. All additive; unset inputs
reproduce prior behavior byte-for-byte.

### FIX-XC-02c — optional DIU style card governs the page's imagery (Brand-Style block 8)
- `tools/ghl_image_stage.py`: a `page_spec` may now carry an OPTIONAL `style_card_id` (a registered
  Skill 45 `FN-…` card). New `_resolve_style_card_block()` resolves it via DIU Workflow B — INDEX.md
  lookup → card file → `### LONG` tier — and embeds that text VERBATIM as the Brand-Style portion of
  **block 8** in every derived section prompt (and appends it to explicit pre-authored prompts). The
  block-4 Signature Grade Block is unchanged. Resolution is FAIL-LOUD: a set-but-unresolvable id
  (no library / not registered / missing card / no LONG tier) raises `ImagePipelineError` rather than
  silently shipping off-brand art. Library located via `DIU_LIBRARY_DIR` override or sibling/`~/.openclaw`
  candidates. Unset `style_card_id` ⇒ exact prior behavior.
- Cross-skill (additive data/doc): Skill 45 `library/INDEX.md` gains the `FN-` funnel/landing/website
  category + prefix and a new `library/funnel-page-designs/_RULES.md`; Skill 49 intake gains optional
  Q18 `q18_style_card_id` + PROMPT 7 / MASTERDOC §4 block-8 notes; Skill 56 intake schema gains optional
  `style_card_id` + a PROMPT-SEAMS image Brand-Style seam.

### FIX-IMG-03 — per-entry aspect_ratio / resolution (no more silently-forced 16:9)
- `tools/ghl_media.py::build_prompts_json`: carries an OPTIONAL per-spec `aspect_ratio` / `resolution`
  straight through into `prompts.json`. `presentation-render/kie_generate.py` (the REUSED generator) now
  reads `slide.get("aspect_ratio", ASPECT_RATIO)` / `slide.get("resolution", RESOLUTION)` — a section's
  mandated ratio (e.g. 49 Section 12 → 3:4) is honored; entries without the keys render exactly as before.

### FIX-XC-05c — Skill-6 rail contract parity test
- New `tests/test_cc_rail_contract.py`: mirrors `test_cc_contract.py` for the rail's `cc_board.py`
  (producer terminates at `review`, `done` hard-blocked on both `move_task`/`update_status`, enum parity,
  deterministic ingest routing, disabled-board no-op) **plus** the front-door/nonce entry discipline of
  `ghl_gate.py` (a hand-written / wrong-writer / nonce-less / MOCK / missing-evidence verdict can never
  pass the gate; only a real writer+nonce+consistent PASS returns 0). 17 tests, stdlib+pytest, zero network.

---
## [v17.0.29] - 2026-07-05 - test(fab-qc): re-author passing-path fixtures for the new lengthClass floors (T-funnel-copy-engine)

- **FIX-XC-04a (consumer)** — `tests/test_v2_dispatcher.py`: the shared `shared-utils/fab_qc.py` D2
  gate now enforces lengthClass-keyed floors (body slots ≥40 words; page-level lengthClass floors).
  Re-authored the two passing-path golden hero copies (`_write_fab_evidence` non-placeholder hero and
  `TestFabArtifactProducer` real_copy) to genuinely clear the 40-word body floor, so the gate tests
  assert the new behavior instead of the old flat 4-word floor. No shipped-behavior change in this
  wrapper; test-fixture depth only.

---

## Version tracking

As of v17.0.4, `SKILL.md` `metadata.version` is rolled automatically by `bump-version.sh` in lockstep with the repository `/version`. The nested skill version now tracks the repo version by design (not a separate content version). The gate deliberately skips validation on this nested `metadata.version` since `bump-version.sh` step-12 keeps it current.

---

## [v17.0.28] - 2026-07-05 — fix(Copy routing): wire has_copy → P2-COPY mini-epic + deeper intake

### FIX-COPY-01 — a standalone "write it for me" page/website now reaches a copywriter
`tools/v2_dispatcher.py::_run_intake` (via the new `_open_copy_dependency`) detects the intake
`has_copy == "write it for me"` answer with no APPROVED `copy.md` and opens a 3-card mini-epic
(`p1-spec → p2-copy → p4-build`): it posts a **P2-COPY** card routed to the **marketing** department
(the Conversion Copywriter, per SOP-07 Step 3), flags the build task `waiting_on_dependency`, and writes
`routing/copy-dependency.json`. `dispatch_one` HOLDS the build (new `STATE_WAITING`, builder never called)
until an APPROVED `copy.md` exists — closing the "build session model improvises copy inline" hole (the
single largest copy-quality lever). Fail-soft: the board card is visibility-only; the local
`waiting_on_dependency` receipt is the binding gate. Funnels are unaffected (`has_copy` is page-only).

- `tools/cc_board.py::ingest_task` gained additive `department_slug` / `source` overrides so a P2-COPY
  card can pin to `marketing` (selftest case added).
- `v2-autonomous-build-sop.md`: new **P2.5** section documents the routing + the SOP-07 Step-1
  intent-signal amendment ("landing page" / "website" / "sales page" are copy-authoring intents).
- Tests: `tests/test_v2_dispatcher.py::TestCopyDependency` (held-waiting, proceeds-when-approved,
  I-have-copy, funnel-never-triggers).

### FIX-COPY-04(i) — intake now captures copy depth + traffic source
`tools/intake_interview.py`: two shared copy-context questions (`traffic_source`, `copy_depth`) are
appended to the funnel + page question sets (still within `MAX_QUESTIONS=7`) and threaded into the
funnel-spec / P2 brief scaffold. Selftest fixture updated for the new fields.

---

## [v17.0.27] - 2026-07-05 — fix(image delivery rail): 8-block brand prompts, PNG sanity, rendered-<img> gate, media adapters

Wave-0 merge-train **T-06-ghl-delivery-rail** (fix IDs FIX-XC-03c, FIX-XC-04f, FIX-IMG-01, FIX-IMG-08, FIX-IMG-09).

### Fixed — the "un-fakeable" rendered-`<img>` gate now exists (FIX-XC-03c)
`ghl_verify.verify_page` loads `<run_dir>/images/manifest.json`, filters records by `used_on_page_id`, and asserts each `cdn_url` literally appears in the fetched rendered DOM (raw HTML, not tag-stripped). A missing image folds into `render_errors` → `PASS:False` (no override) and is stamped on the raw record as `missing_images`. `assert_consistent` adds Invariant 6 (a `missing_images` row can never be `PASS`) as the summary-layer mirror. Opt-in: fires only when a success manifest targets the page. The live-path HTML-repair retry re-folds the gate against the repaired DOM so a clean preview repair can't mask a still-missing image.

### Fixed — Skill-6 no longer fabricates a ~200-char generic hero prompt (FIX-XC-04f)
`ghl_image_stage._derive_copy_specs` now emits ONE spec per major page **section** (not a single hero), each a full 8-block prompt (order from 49 MASTERDOC §4) whose block-4 Grade Block is templated from the intake brand colors. Copy context cap raised 300 → 2,000 chars. `ghl_media.build_prompts_json` gained `enforce_floor` + `PROMPT_CHAR_FLOOR = 1500` (measured on prompt content, before the pin) raising `ValueError`; the paid path (`run_image_pipeline`) always enforces it, so a weak prompt can never reach a paid Kie call.

### Fixed — deterministic image sanity + bounded regeneration (FIX-IMG-01)
`ghl_image_stage.run_image_pipeline` runs a deterministic PNG sanity stage between generate and upload: IHDR-dimension vs resolution-class floor, resolution-scaled byte floor (≥150 KB for 2K), and near-zero decompressed-IDAT color-entropy rejection. A failing slot is regenerated ≤2 times, then hard-FAILs with the slot id. No network, no model.

### Fixed — KIE subprocess timeout scales with prompt count (FIX-IMG-08)
`ghl_media.generate_images` computes `timeout = max(1800, 300 + 120 * n_prompts)` (from prompts.json length); `KIE_SUBPROCESS_TIMEOUT` still overrides. The computed cap is logged into the run's `asset-cdn.log` evidence and returned in the result. This stops large image sets from being killed mid-run with paid images orphaned.

### Fixed — prompt/QC bundle (FIX-IMG-09)
(i) Skill 47 `kie_image.py` now forwards the accepted-but-dropped `negative_prompt` in-prompt (`Do not include: …`) for gpt-image-2. (ii) `ghl_media.build_prompts_json` appends the English/Latin **spelling** pin only to `text_bearing` specs; photographic specs get a **no-text** pin (`TEXT_ABSENT_PIN`) instead of being invited to render lettering. (iii) `qc-built-funnel.sh` media-delivery pre-gate upgraded WARN → FAIL when `images/manifest.json` is present but the rendered/preview evidence has no `<img>` referencing a manifest CDN URL, and when no media-folder receipt is present (WARN kept for image-less/legacy evidence). (iv) Added a repo lint (`scripts/qc-assert-skill-version-newline.sh` + workflow) that every `skill-version.txt` ends with a trailing newline, and repaired the two offenders (`32`, `56`) that could concat into a corrupt version token.

---

## [v17.0.7] - 2026-07-03 — fix(audit): Skill-6 form-id hardening + iframe regression tests

### Fixed — Skill-6 form-id server-side re-validation (P1-5 remainder)
`_capture_form_id` now re-validates the captured id against a conservative shape (`re.fullmatch(r'[A-Za-z0-9]{15,30}')`) and returns `""` on mismatch; never trusts raw cross-origin results. `_screenshot` now logs previously-swallowed exceptions (control flow unchanged, best-effort). Negative test cases added to `tests/test_ghl_form_builder_capture.py` (11/11 pytest).

---

## [v17.0.4] - 2026-07-03 — fix(audit): SKILL.md frontmatter-version drift + repo-wide gate + Skill-6 iframe regression tests

### Fixed — SKILL.md frontmatter-version drift
Skill 6's nested `metadata.version` was v16.2.14 while repo was v16.12.0+. `bump-version.sh` now rolls `SKILL.md` `metadata.version` in step-12, keeping it synced with `/version`. New CI gate `.github/workflows/skill-frontmatter-version-guard.yml` ensures top-level `SKILL.md` frontmatter `version:` matches `skill-version.txt`.

### Added — Skill-6 iframe-capture regression test
NEW `tests/test_ghl_form_builder_capture.py` (11 hermetic pytest cases) locks in the v17.0.2 cross-origin iframe form-id fix and `_ensure_agent_browser_path` prepend/idempotency guard.

---

## [v17.0.2] - 2026-07-03 — fix(skill-6): cross-origin builder-iframe form-id capture + agent-browser PATH resilience

### Fixed — form-id capture from cross-origin builder iframe
`_capture_form_id` read the top-frame `location.pathname` (always empty for forms). Now enumerates `document.querySelectorAll('iframe')`, reads `.src` attribute (parent-readable even cross-origin), and returns first `/form-builder-v2/<id>` match. Falls back to top-frame pathname, then `""`. Node-verified across all four branches.

### Fixed — agent-browser PATH resilience
Added `_ensure_agent_browser_path(env)` — prepends `~/.npm-global/bin` to `env['PATH']` only if missing, preventing subprocess spawn failure when PATH is clobbered by `~/.openclaw/secrets/.env`. Wired into 3 subprocess sites (`_ab`, `_seed_session`, `_close_session`). Never reads secrets file.

---

## [v16.12.0] - 2026-07-03 — feat(skill-6): GHL Form Builder — browser-driven forms + field placement

### Added — GHL Form Builder capability
New `tools/ghl_form_builder.py` — two-layer form builder (SMART plan layer emits click list; DUMB agent-browser layer executes). Field placement FULLY IMPLEMENTED: F5 Quick-Add standard fields + F6 Add-Object-Fields (`zhc_` prefixed custom fields pre-created by Skill 44). Snapshot-and-bind approach locates fields by visible text, drags them onto canvas (no invented CSS selectors), binds property panel. Custom-field KEYS/TAGS `zhc_`-prefixed; object NAMES carry `ZHC ` prefix via shared `ghl_builder.ensure_zhc_prefix`. Selftest green, live selector map locked in `SELECTORS-LIVE-form.md`. Delivery-rail MIX intact: forms/surveys → browser-clicker; funnels/pages → REST-canvas; fields/tags → Skill-44 API.

### Added — form routing and QC gate
`v2_dispatcher.py` routes form requests; new `qc-built-form.sh` gate. 23 role-library door lines added across crm/customer-support/marketing/sales/web-development.

---

## [v16.2.15] - 2026-07-01 — fix(skill6): DoD4+DoD5 hardening — intake think-for-me branch activated; update_status 'done' parity guard

### Fixed — DoD4: intake think-for-me branch now receives an executor (`tools/v2_dispatcher.py`)
`dispatch_one` called `_run_intake(task, evidence_root)` with no `executor` argument. `_run_think_for_me_branch` inside `intake_interview` exits immediately with `_skip_reason="no_executor"` when `executor is None`, silently skipping the proposed-structure path for every UNSURE / HANDS_OFF user. A `make_stub_executor()` instance (offline, deterministic, model-sovereign — no Anthropic) is now created from `_model_router` at dispatch entry and passed as `executor=_intake_executor` to `_run_intake`, threading through `run_interview` → `_run_think_for_me_branch` → `model_router.select(executor, role="reasoning", …)`. Normal ≤7-question path behavior is unchanged.

### Fixed — DoD5: `update_status('done')` parity guard (`tools/cc_board.py`)
`move_task()` hard-blocked `status=='done'` but the legacy `update_status()` listed 'done' in `_CC_STATUS_VALUES` with no matching guard, leaving a QC-bypass hole. An identical HARD-BLOCK is now added immediately after the enum-validation check in `update_status()`. Any call with `status_norm=='done'` logs the "producer must never post 'done' directly" message and returns `False`. `_status_selftest()` gains check #8 asserting this offline.

### Tests
- `TestIntakeExecutorWiring` (3 tests, `tests/test_v2_dispatcher.py`): verifies `dispatch_one` passes non-None executor; baseline no-executor skip; stub-executor non-skip with receipt.
- `test_update_status_done_is_blocked` (`tests/test_cc_board_status.py`): parity guard returns `False`.
- `test_network_error_fail_soft` adjusted to use 'blocked' (not 'done') to continue testing actual network-error fail-soft.

### Files changed
- `tools/v2_dispatcher.py`
- `tools/cc_board.py`
- `tests/test_v2_dispatcher.py`
- `tests/test_cc_board_status.py`
- `skill-version.txt` → v16.2.15 (rolled by bump-version.sh)

---

## [v16.2.14] - 2026-07-01 — feat(skill6): model_router wired end-to-end, ghl_survey_builder + intake_interview shipped, Command Center step-visibility + done-skip fix, 11-alias terminology unification, version-drift reconcile

### Fixed — version-drift triple-equality reconcile
- `skill-version.txt` had advanced to v16.2.13 via four repo-wide lockstep bumps (v16.2.10 GHL credential/caf hardening across 14 skills, v16.2.11 updater content-gate hardening, v16.2.12 skill-41 executor-model fix, v16.2.13 updater SIGPIPE/pipefail fix) — none of which touched this skill's `SKILL.md` or this `CHANGELOG.md`, leaving the triple-equality gate (`skill-version.txt` == `SKILL.md` frontmatter == CHANGELOG top) RED at v16.2.13 / v16.2.9 / v16.2.9. Reconciled the single version of record to **v16.2.14** across all three.

### Added — GHL survey builder (`tools/ghl_survey_builder.py`, new)
- New two-part browser-controlled survey pipeline. Part 1 creates the Contact custom-field folder and every required custom field via the app shell. Part 2 assembles the survey in `survey-builder-v2` — welcome slide, Add-Object-Fields (answers bind to `{{contact.<key>}}`), conditional-logic jump-to rules, required-field toggles, a Quick-Add contact-capture slide with a plain Terms & Conditions checkbox, save, Integrate, and survey-URL capture. `--dry-run` (default) writes the plan + field-map + ordered click list WITHOUT touching GHL; flips to live only after an end-to-end verified run. Glue-only — every write goes through `ghl_builder.browser_cmd` → agent-browser; the module never mutates GoHighLevel state directly. Owns `routing/survey-plan.json`, `routing/survey-field-map.json`, `routing/survey-preflight.json`, `shots/`.

### Added — Shared adaptive intake interview (`tools/intake_interview.py`, new)
- New `run_interview(task, ask_fn, *, executor=None, env=None)` — a ≤7-question adaptive intake that sits at Wiring-Map Step 1 (Request → Intake), feeding Step 2 (Persona) and Step 3 (Think). Silently skips any question already answerable from the task. "Think for me" branch: triggered by an UNSURE intent or a user "you decide" answer; calls `model_router.select(executor, role='reasoning', env=env)` (falls back to a role-blind call against a pre-Workstream-A `model_router`), proposes a lightweight structure (slide/page count, elements, conditional-logic stubs, capture fields), and holds for a single confirmation question before proceeding. Never selects an Anthropic model — the executor is the caller's own model_router-backed callable. Wired into `v2_dispatcher.py` as Step 1 (`_run_intake`, runs before STEP 0 / the builder) and persists `routing/intake-receipt.json`.

### Changed — `model_router.py` wired end-to-end (`tools/v2_dispatcher.py`, `tools/ghl_verify.py`)
- `v2_dispatcher.py` now resolves a role-keyed model receipt for every runtime role at dispatch entry (Wiring-Map Step 3 — THINK → model_router), using the stub executor and persisting a receipt per role.
- `ghl_verify.py` gains two designated model-router seam functions: `select_html_repair_model()` (role=`html`, for the code-block repair-and-retry path) and `select_qc_model()` (role=`qc`, vision QC over screenshots + DOM — the only role that never falls back past MiniMax M3 to DeepSeek, since DeepSeek has no confirmed vision capability). Both return `{}` (never raise) when `model_router` is unavailable.
- This closes the "remaining enforcement step" flagged in the v16.2.9 entry below ("Wiring the router into `ghl_verify`'s fix-loop / selector-recovery... flagged, not done here").

### Added — Command Center step-visibility + done-skip fix (`tools/cc_board.py`)
- `_CC_STATUS_VALUES` expanded from the 6-value subset to the full 10-value `TaskStatus` enum (`backlog`, `inbox`, `planning`, `pending_dispatch`, `assigned`, `in_progress`, `review`, `testing`, `blocked`, `done`).
- New `move_task(task_id, status, note=None)` — transitions the Kanban card (Bearer + HMAC, same signing contract as `ingest_task`). **Done-skip fix**: any call with `status='done'` is HARD-BLOCKED (logged, returns `False`) — the only path to `done` is the Command Center's own QC gate (`runQCOnReview`, PASS ≥ 8.5) promoting a card from `review`. Builders can never self-certify a card done.
- New `post_activity(task_id, activity_type, message, metadata=None)` — posts one granular entry (`spawned`/`updated`/`completed`/`file_created`/`status_changed`) to the card's activity feed; this is the step-visibility primitive — a caller posts `post_activity('updated', 'Step k/N: …')` after every material build step so progress is visible on the board in real time, not just at phase boundaries.
- New `register_deliverable(task_id, url, meta=None)` — attaches the built artifact URL (e.g. the live survey link) to the card.
- New `BuildPhaseDriver` class sequences the full lifecycle for any future caller: `start()` → `step()` (auto-starts if needed) → `artifact()` (registers the deliverable, moves to `review`, NEVER `done`) or `fail(human_required=...)` (→ `backlog` retryable or `blocked` human-required). `ghl_survey_builder.py`'s own fail-soft board wrappers already call `move_task`/`post_activity`/`register_deliverable` directly (via a `getattr` guard) for its survey flow, independent of the `BuildPhaseDriver` class.
- All new functions are FAIL-SOFT (never raise; a `False`/no-op return never blocks the build) and best-effort against an older `cc_board.py`.
- `ingest_task` also learns `job_type='survey'|'form'|'quiz'` → `department_slug='web-development'`, `source='survey'` (Option 1, zero-migration; a dedicated `surveys` department is a documented fast-follow).

### Changed — Unified GHL 11-alias terminology (`tools/ghl_ecosystem.py`, `tools/ghl_media.py`)
- `PIT_ENV_CANDIDATES` (`ghl_ecosystem.py`) and `_PIT_ENV_NAMES` (`ghl_media.py`) both expanded from a 3-4-name candidate list to the full canonical 11-alias LOCATION-PIT set documented in `TERMINOLOGY.md` (`GOHIGHLEVEL_API_KEY` preferred, plus `GHL_API_KEY`, `GHL_PIT`, `GHL_TOKEN`, `GHL_PRIVATE_INTEGRATION_TOKEN`, `PRIVATE_INTEGRATION_TOKEN`, `GHL_PRIVATE_TOKEN`, `PIT_TOKEN`, `GHL_PIT_TOKEN`, `GOHIGHLEVEL_LOCATION_PIT`, `GHL_LOCATION_PIT`; `ghl_ecosystem.py` retains `CAF_API_KEY` as a 12th Skill-44-engine backward-compat alias). Every resolver across the five GHL skills now scans the same 11 names in the same order before raising "not found." This closes the class of credential-resolution crash-loop where a box's location PIT was stored under an alias absent from an older, shorter candidate list — the resolver fail-loud'd on a token that was actually present under an unrecognized name. See `SKILL.md`'s PIT-aliases banner and `TERMINOLOGY.md` for the full set.

### Changed — Unified GHL 11-alias LOCATION-PIT resolver across all five GHL skills (05/29/36/44)
- **Skill 05** (`05-ghl-setup`): `docs/` reference pages and the setup-phase preflight script updated to list all 11 canonical alias names; the preflight credential walk now scans the same ordered 11-name candidate list that the runtime resolvers use (was a shorter informal list that silently skipped aliases).
- **Skill 29** (`29-ghl-convert-and-flow`): `EXAMPLES.md`, `INSTALL.md`, and `QC.md` env-var tables expanded to all 11 alias names; the QC script's credential-present check now walks all 11 in order (was a 3-name subset check that produced a false GENUINELY-ABSENT result when the box's Location PIT was stored under any alias outside those three names).
- **Skill 36** (`36-ghl-mcp-setup`): `SKILL.md` gains a PIT-aliases banner (same style as Skill 06's banner) so any agent consulting the MCP-setup skill is exposed to the full 11-name set; range-based counts in the existing env-var section updated from the former 4-name shortlist to the canonical 11.
- **Skill 44** (`44-convert-and-flow-operator`): `_get_token()` (the engine's internal credential resolver) expanded from a 3-name scan to all 11; `wire-ghl-env.sh` now exports all 11 alias names (was 4); the engine wrapper resolvers (caf engine / automation builder entry points) broadened to the same 11-alias candidate list, closing the gap where an operator's Location PIT stored under an alias outside the old 4-name set caused a `CredentialNotFound` even though the token was present in the environment.

### Added — Markdown banned-token CI guard (`.github/workflows/qc-static.yml`)
- New step **"No banned model tokens in GHL skill markdown prose"** scans all `*.md` files under `05-ghl-setup/`, `06-ghl-install-pages/`, `29-ghl-convert-and-flow/`, `36-ghl-mcp-setup/`, `44-convert-and-flow-operator/`, and `docs/` for four violation classes: **(a)** the MiniMax M2 hyphenated slug form — any occurrence fails the build with no exclusions; **(b)** the bare `(MiniMax|minimax) M2` token on lines that do NOT contain explicit ban or purge language (`banned`, `PURGED`, `purge`, `do not`, `never use`, `must not`, `supersede`, `removed the stale`) — this exclusion ensures the ban assertion does not self-trip on lines that name M2 only to forbid it; **(c)** Anthropic model identifier patterns (Claude ids, anthropic-namespaced provider paths) on lines without explicit `forbidden`/`rejected`/`never`/`banned` phrasing; **(d)** a bare `\bkimi\b` token (case-insensitive) on lines that carry none of the qualified provider forms (`ollama/kimi`, `openrouter/kimi`, `openrouter/moonshotai/kimi`, `kimi-k2.6:cloud`). Any violation fails the build without a manual override. False-positive exclusions apply only to classes (b) and (c); classes (a) and (d) have no exclusions.

### Tests
- `tests/test_model_router.py`: extended with `TestRoleRung1`, `TestOllamaCloudFirst`, `TestM2Purge`, `TestExecutionFallback`, `TestGeminiLastRung`, `TestModelSovereignty`, `TestThinkingEffort`, `TestEnvOverrides`, and `TestKimiSlugHygiene` — covers all five roles (`content`/`html`/`code`/`reasoning`/`funnel`/`execution`/`qc`), the MiniMax M2 purge, `ollama/kimi-k2.6:cloud` / `openrouter/moonshotai/kimi-k2.6` slug hygiene (never bare, never a typo), and Anthropic sovereignty.

---

## [v16.2.9] - 2026-06-30 — fix(skill6): version-drift reconcile, NON-ANTHROPIC model doctrine + probe-gated ladder, Kanban status transitions, GoHighLevel cred canonicalization, no-GitHub docs

### Fixed — version-drift triple-equality (P0-1)
- Reconciled the single version of record to **v16.2.9** across `skill-version.txt`, `SKILL.md` frontmatter, and this CHANGELOG top (was v16.2.8 / 14.28.1 / v14.28.1 — the QC `check-version-drift.py` gate was RED). `tools/browser_manager.sh` + `tools/browser_manager.py` version markers rolled to v16.2.9 in lockstep (the B1 gate only checks the headless-lock floor, so the bump is safe).

### Changed — CLIENT-PROVIDER model doctrine, NEVER Anthropic (scrub)
- `ghl-browser-builder-full.md` §1.3 rewritten off the Anthropic Opus/Sonnet/Haiku fleet doctrine onto the binding client-provider policy: **browser-control + tool-calls + QC → MiniMax 3** (PRIMARY, probe-gated), **reasoning → DeepSeek v4 pro / GLM 5.2**, **page/HTML content → GLM 5.2**; **Ollama Cloud preferred, OpenRouter backup; thinking = HIGH; NEVER Anthropic** on a client box. Mechanical glue is now described as model-agnostic.
- `tools/ghl_builder.py` docstring: "Haiku-class mechanical work" → "mechanical-tier work (model-agnostic, client's configured/default model)". (`ghl-install-pages-full.md` §10 STEP 3 already pointed at `ollama/deepseek-v4-pro:cloud` / OpenRouter "never Anthropic" — left as the compliant defensive guard.)

### Added — probe-gated NON-ANTHROPIC model fallback ladder (`tools/model_router.py`, P0-2)
- New self-contained `model_router.py`: role-aware ladders (the initial description cited a flat 6-rung ladder with a now-purged execution fallback; execution rung-2 is DeepSeek v4 pro, superseding that rung). Current role ladders — **content**: Kimi 2.6 (`kimi-k2.6:cloud` via Ollama Cloud → `openrouter/moonshotai/kimi-k2.6`) → Gemini 3.5 Flash last rung; **html/code**: GLM 5.2 (`glm-5.2:cloud` via Ollama Cloud → OpenRouter `z-ai/glm-5.2`) → Gemini 3.5 Flash; **reasoning/funnel**: GLM 5.2 then DeepSeek v4 pro (Ollama Cloud first), then the same pair via OpenRouter → Gemini 3.5 Flash; **execution**: MiniMax M3 (Ollama Cloud, probe-gated) → DeepSeek v4 pro (Ollama Cloud) → MiniMax M3 (OpenRouter, probe-gated) → DeepSeek v4 pro (OpenRouter) → Gemini 3.5 Flash last rung. Every ladder is Ollama-Cloud-first → OpenRouter equivalent → Gemini 3.5 Flash last rung. Execution rungs 1 and 3 (MiniMax M3 via Ollama Cloud and OpenRouter) are PROBE-GATED (the probe DEMANDS a real tool-call/JSON return — catches MiniMax's plausible-non-tool text). On a runtime fail: one backoff retry then advance; 429/timeout = advance. HARD GUARD `assert_no_anthropic` refuses any Anthropic id; `assert_ollama_cloud_ready` enforces the `:cloud` + `ollama.com` baseUrl trap. `--selftest` is offline (stub executor); live calls only via an injected executor. Receipt (`routing/model-ladder.json`) is written OUTSIDE the skill dir.
- NOTE: only the DeepSeek slug is repo-documented; MiniMax/GLM provider slugs follow the documented conventions, carry `slug_confidence:"confirm"`, are env-overridable (`MODEL_ROUTER_*`), and FAIL-SAFE through the probe-gate. Wiring the router into `ghl_verify`'s fix-loop / selector-recovery is the remaining enforcement step (flagged, not done here).

### Added — Kanban status transitions (`tools/cc_board.py` + `tools/v2_dispatcher.py`, P0-3 producer half)
- `cc_board.update_status(task_id, status, *, note)` + `update_status_for_state(task_id, dispatch_state)` move a card across the board (in_progress / review / blocked / done). Same FAIL-SOFT + Bearer + HMAC parity as `ingest_task`; status validated against the CC `TaskStatus` enum. The exact CC route is NOT yet confirmed in `trevorotts1/blackceo-command-center`, so the caller defaults to `POST /api/tasks/{id}/status` (documented `/api/tasks/<id>/...` family) and is overridable via `CC_STATUS_METHOD` / `CC_STATUS_PATH_TEMPLATE` — a 404 fail-softs. **CONSUMER ENDPOINT MUST BE CONFIRMED/ADDED IN THE COMMAND-CENTER REPO.**
- `v2_dispatcher.dispatch_one` now mirrors every state write to the board (fail-soft, guard-imported): dispatched/building → in_progress, verified → review, FAILED → blocked. A board outage never blocks the build; `--selftest` still prints SELFTEST PASS.

### Changed — GoHighLevel credential canonicalization
- `tools/ghl_auth_fallback.py` multi-location selection now prefers the canonical `GOHIGHLEVEL_LOCATION_ID` and falls back to the legacy `GHL_LOCATION_ID` (operator error strings updated to surface the canonical name).
- `tools/ghl_ecosystem.py` `PIT_ENV_CANDIDATES` reordered to prefer the canonical `GOHIGHLEVEL_API_KEY` over the legacy `GHL_API_KEY` / engine `CAF_API_KEY` — now consistent with `ghl_media.py`. The `ghl_media.py` PIT + location paths already preferred the canonical names.
- (The `browser_manager` session/breaker namespace deliberately keeps `GHL_LOCATION_ID` — it is a session LABEL, not an auth credential, and is covered by the python↔shell singleton-naming contract test.)

### Fixed — docs (P1-3 / P2-3)
- `SKILL.md` + `INSTRUCTIONS.md`: state plainly that the VERCEL_EMBED path is a **DIRECT Vercel API upload — NOT GitHub** (`ghl_vercel.py` base64-uploads straight to the deployments API; no git/PR). Added the "run evidence lives OUTSIDE the skill dir" rule and the cross-repo board contract version note.
- `tools/ghl_method.py` docstring: stale "defaultSettings.colors" → "general.general.colors" (the key that actually exists; prevents re-introducing the HTTP-500).

### Tests
- New `tests/test_cc_board_status.py` (update_status guards, state mapping, transport via monkeypatched POST, full backlog→in_progress→review lifecycle) and `tests/test_model_router.py` (ladder shape, no-Anthropic guard, Ollama Cloud invariants, probe-gate + failover). All green.

---

## [v14.28.1] - 2026-06-28 — chore(skill6): version bump in lockstep with listings fix (no skill6 changes)

No functional changes to this skill. Version bumped in lockstep with the repo
release (v14.28.1 listings-real-estate-only fix in Skill 23) to keep the
triple-equality gate (skill-version.txt == SKILL.md frontmatter == CHANGELOG top)
green. The browser-manager markers are rolled by bump-version.sh as a side
effect of every repo release.

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
