# Changelog - ghl-install-pages

All notable changes to this skill wrapper are documented here.

---

## [v19.62.0] - 2026-07-18 - U24 (B-U10) rebuild: sweep_base false-alarm fix, real cron installer, broken doc snippet

> Note: `skill-version.txt` (v20.0.69) is repo-locked (rolled by
> `scripts/bump-version.sh` at release, but ALSO bumped standalone here per CI
> G3 — see `scripts/check-version-drift.py`); this CHANGELOG number is 06's
> independent per-skill log.

Rebuild of the U24/B-U10 archival-rail fixes (previously PR #595, which no
longer merged cleanly against main after `fc9e636e` (2026-07-15) re-landed
this same area with a different installer design). Re-implements the same
three fixes against that CURRENT design rather than against `fc9e636e`'s
predecessor:

### Fixed
- **`SweepReport.all_clean()` false alarm.** A box that has never run a
  Skill-6 build (no evidence base directory yet) is `applicable: False` —
  "nothing to sweep," not a problem. `all_clean()` used to AND that flag into
  the result (`self.applicable and all(...)`), so `applicable=False` made
  `all_clean()` return `False` too — every fleet box that had never built
  anything would alarm "ATTENTION NEEDED" on its very first scheduled sweep.
  Fixed: `all_clean()` now treats a non-applicable sweep as clean. Regression:
  `tests/test_ghl_github_reconcile.py::TestSweepBase::
  test_missing_base_dir_is_not_an_alarm` asserts `all_clean() is True` on a
  missing base dir (previously asserted the buggy `False` — the test itself
  carried the bug and is corrected here, mutation-proof against the fix being
  reverted).
- **`scripts/install-github-archive-reconcile-cron.sh` missing `--no-deliver`.**
  The installer registered its nightly maintenance sweep via `openclaw cron
  add` without `--no-deliver`, so the CLI's default "announce" delivery mode
  would fan a routine internal sweep out as a client-facing notification
  every night. Fixed to match the sibling installer's already-correct pattern
  (`scripts/install-page-inventory-lifecycle-cron.sh`, U31/B-U17) and the
  documented FIX-XC-08a precedent (`37-zhc-closeout/scripts/
  install-closeout-resume-cron.sh:85-90`). Regression:
  `tests/test_github_archive_maintenance_schedule.py::
  TestInstallerAgainstFakeOpenclawCli::test_registers_with_no_deliver_flag`.
- **SKILL.md broken paste-ready cron snippet.** The Reconciliation section's
  hand-typed `openclaw cron create ... --schedule ...` example used a CLI
  flag (`--schedule`) that does not exist (the real flag, for `openclaw cron
  add`, is `--cron` — same FIX-XC-08a precedent above) and omitted
  `--no-deliver`. Removed the hand-typed snippet entirely in favor of
  pointing at the tested installer (`bash scripts/install-github-archive-
  reconcile-cron.sh`), which is proven end-to-end against a fake CLI rather
  than copy-pasted prose.

## [v19.61.0] - 2026-07-16 - GK-27/U89: relationship lattice pointer + citation tripwire

> Note: `skill-version.txt` is repo-locked (rolled by `scripts/bump-version.sh` at
> release); this CHANGELOG number is 06's independent per-skill log (see
> `scripts/check-version-drift.py`). This unit does not touch `skill-version.txt`.

### Added
- **Relationship lattice pointer + citation tripwire.** SKILL.md gained a one-line pointer to the new `docs/CONTENT-CONVERSATION-LATTICE.md` (the canonical Skill 6/44/35/38/3 content↔conversation relationship map). `qc-ghl-install-pages.sh` now asserts that pointer is present AND that this skill's own owned edges — the funnel_matcher tooling backing Gap C, the "Full-Funnel Pipeline Integration (Skill 44 seam)" heading, and the four-file browser build-rail set — still cite real, unchanged ground truth (`docs/tools/check_lattice_citation.py`, drift tripwire; fail-first proof in `docs/tools/test_check_lattice_citation.py`). No code/behavior change to page building itself.

## [v19.60.0] - 2026-07-14 - U22/B-U8: guards + fixtures + operator-box block proof for the persona-unification block

> Note: `skill-version.txt` is repo-locked (rolled by `scripts/bump-version.sh` at
> release); this CHANGELOG number is 06's independent per-skill log (see
> `scripts/check-version-drift.py`).

### Added
- **`scripts/prove_skill6_block_u22.py`** (new) — the ONE end-to-end operator-box
  fixture proof run for the whole Skill-6 persona-unification block (master
  spec crosswalk B/B-U8). Chains B-U1 (`persona_bundle_ladder`) -> B-U2
  (`funnel_matcher.instantiate_pages` per-page blend directives) -> B-U3
  (`copy_persona_blend_seam` copy-stage log) -> B-U5 (`fab_qc` D4 bundle-aware
  grounding, loaded via the real `load_inputs_from_evidence` disk path) -> B-U6
  (declared-vs-used voice equality) against one fixture funnel, plus a legacy
  no-bundle control run proven byte-identical to an in-memory golden baseline.
  Honestly reports B-U4/U18 (`copy_craft_pool`) and B-U7/U21 (ingest parity) as
  NOT-YET-LANDED per the ledger, rather than fabricating their behavior.
- **`tests/test_prove_skill6_block_u22.py`** (new) — pytest/CI wrapper for the
  above.
- 3 new dispatcher-integration-level tests in `tests/test_v2_dispatcher.py`
  (`TestPersonaBundleAcquisition`) closing the CC-rung / local-rung /
  standalone-degradation gaps in the threaded/cc/local/absent x confirm-state
  matrix (the 4 pre-existing tests covered threaded confirmed/pending + absent
  + a raising ladder only).

### Changed
- **`../scripts/guard-fab-qc-gate.sh`** gained a bundle-receipt schema check
  (asserts `persona_bundle_ladder.resolve_persona_bundle()`'s receipt carries
  all 10 required fields; mutation-self-tested) and a forward-compatible
  `copy_craft_pool` WARN hook for D5/U18 (intentionally non-blocking until
  U18 lands — U18's own PR must upgrade this to a hard check).
- **`../.github/workflows/funnel-automation-libraries-guard.yml`** — wired
  `persona_bundle_ladder.py`, `cc_board.py`,
  `49-signature-funnel/scripts/copy_persona_blend_seam.py` (+ its own
  long-unwired `test_copy_persona_blend_seam.py`), and the two new U22 files
  above into the CI path triggers and pytest/selftest steps. None of these
  had ever triggered any CI job before this change — a pre-existing gap
  this unit closes, not introduces.

## [v19.59.0] - 2026-07-13 - VERCEL_EMBED now archives to GitHub, non-blocking, with a reconciliation sweep

> Note: `skill-version.txt` is repo-locked (rolled by `scripts/bump-version.sh` at
> release); this CHANGELOG number is 06's independent per-skill log (see
> `scripts/check-version-drift.py`).

### Changed
- **`tools/ghl_vercel.py::run_pipeline`** now writes an F6 `vercel_deploy` receipt
  (`ghl_receipts`) and, when `evidence_root=` is passed, kicks off non-blocking
  GitHub archival AFTER the Vercel deploy is live and `assert_embeddable` has
  passed — satisfying the operator's standing rule that a page's source code
  must ALWAYS also live in a GitHub repo, never Vercel-only. This is fully
  additive: `evidence_root` is optional and a caller that omits it (all prior
  callers/tests) behaves exactly as before. `VercelEmbedReceipt` gained a
  `github_archive` field reporting the archive attempt's status.
- **`SKILL.md`** (§ "Phase-5 Method Decision Table") and **`INSTRUCTIONS.md`**
  no longer say the VERCEL_EMBED path is "NOT GitHub" — both now document the
  Vercel-deploy-plus-non-blocking-GitHub-archive shape and point at the two new
  tools below. `v2-autonomous-build-sop.md`'s VERCEL end-to-end flow gained
  step 7 documenting the same non-blocking archive hook.
- **root `CREDENTIALS.md`**: `GH_TOKEN`/`GITHUB_TOKEN` is now also listed as
  OPTIONAL for Skill 6 (archival only — never a build blocker).

### Added
- **`tools/ghl_github_archive.py`** (new) — the non-blocking GitHub archival
  module. Stages the generated `index.html`/`vercel.json` to a stable path
  under the run's evidence root (survives the original, possibly ephemeral,
  `project_dir`), then fires a DETACHED subprocess (new session — survives the
  parent process exiting) that pushes them to a per-page GitHub repo (name
  deterministic from `project_name` + `marker`, so a re-deploy always updates
  its OWN repo and can never touch an unrelated one) and writes an F6
  `vercel_github_archive` receipt (`created`/`reused`/`failed`) when it
  finishes. Every failure mode (no `GH_TOKEN`/`GITHUB_TOKEN`, GitHub API error,
  network error, subprocess spawn failure) is caught and recorded — NEVER
  raised into the Vercel pipeline. All GitHub REST calls are behind an
  injectable `requester` seam (same style as `ghl_vercel.py`'s), and the
  subprocess spawn is behind an injectable `popen` seam, so tests are
  mock-only (no live GitHub call, no real subprocess).
- **`tools/ghl_github_reconcile.py`** (new) — the reconciliation sweep. Lists
  every `vercel_deploy` receipt under an evidence root, confirms each has a
  verified `vercel_github_archive` receipt, and (`--retry`) re-runs the archive
  job from its staged source for any that don't, or FLAGS the page if no
  staged source remains (never fabricates source). CLI:
  `python3 tools/ghl_github_reconcile.py --evidence-root <dir> --retry [--json]`
  (exit 0 = every page's code is confirmed in GitHub, exit 1 = attention
  needed). Deliberately scoped to a single evidence root per run — not a
  fleet-wide crawler/daemon; wiring it into a periodic gate is an operator
  decision.
- **`tests/test_ghl_github_archive.py`** (18 cases) + **`tests/test_ghl_github_reconcile.py`**
  (11 cases) — mock-only, no live GitHub/network/subprocess. `tests/test_ghl_vercel.py`
  gained a `TestRunPipelineGithubArchival` class (4 cases) proving: archival is
  skipped when `evidence_root` is omitted (backward compatible); the deploy
  receipt + archive call fire when it's given; an exploding `archive_async`
  never propagates out of `run_pipeline` (the Vercel deploy's own success is
  unaffected); and archival is NEVER attempted when the Vercel gate itself
  fails first.

### Not yet built (explicitly out of scope this unit — operator decision open)
- Automatic fleet-wide discovery of every run-evidence root on a box (the
  reconciliation sweep takes an explicit `--evidence-root`; it does not crawl
  `skill6-fix/v2-*/` itself).
- Wiring `ghl_github_reconcile.py` into a cron / periodic fleet gate.
- Org-owned (vs personal-account-owned) archive repos — `repo_owner` can be
  passed explicitly, but auto-resolution only queries `GET /user` (the token's
  own account), not an org.

---

## [v19.58.1] - 2026-07-12 - P3-08 Gap A: GATED Automations (workflow) builder implemented

> Note: `skill-version.txt` is repo-locked (rolled by `scripts/bump-version.sh` at
> release); this CHANGELOG number is 06's independent per-skill log (see
> `scripts/check-version-drift.py`).

### Added
- **`tools/ghl_workflow_builder.py` — the Skill 6 GATED, MANAGED Automations (workflow) builder.** This is the Tier-4 workflow-BUILD backstop Skill 44 routes to when the Firebase token is unread/misconfigured (Gap A). It drives the GoHighLevel Automations UI (name + trigger + action) through the ONE `browser_manager.sh` singleton gateway — one session, lock=1, TTL, guaranteed teardown, reaper backstop — and NEVER spawns agent-browser directly. It resolves its steps from the new `automations_builder_gates` registry in `tools/gates.json`; if a required gate is absent it raises `MissingGateError` rather than freehand-navigate ("NO invented CSS is shipped as fact"). Reads back and returns the built workflow id; a save with no readable id is a loud `WorkflowBuildError`, never a silent partial success.
- **`tools/gates.json` → `automations_builder_gates`.** 12-step gate registry for the Automations builder. Steps ship `status: runtime` (accessibility role/name find hints resolved against the live DOM), `_capture_status: pending_live_capture` — the harness is complete now; the live-captured selectors are the operator-box follow-on.
- **`tools/SELECTORS-LIVE-automations.md`.** Human-readable companion documenting the gates, the two-phase runtime→captured discipline, and the live-capture follow-on procedure.
- **`tests/test_ghl_workflow_builder.py`.** Fail-first proof: a token-unset build drives the gated path, quotes the built workflow id, and asserts zero-orphan teardown (teardown runs exactly once, even on a mid-build exception); missing-gate refusal; no-id-readback loudness; managed-gateway-never-agent-browser. `python3 tools/ghl_workflow_builder.py --selftest` is the runnable CLI proof.

---

## [Unreleased] - 2026-07-12 - P3-04 residuals: iframe failure taxonomy + weekly iframe-survival check

Branch **fix/skill6-residuals**, off `origin/main` (v19.58.0). Closes the two
P3-04 (c) items whose deliverables land inside THIS skill (item 4: iframe
failure taxonomy + weekly iframe-survival check; the unmanaged-spawn guard
widening (item 1) and the per-box conformance probe (item 5) are repo-level
(`scripts/`), not skill-06 content, and get their own changelog coverage —
`41-build-with-ai-playbook/CHANGELOG.md` for the guard-adjacent
`06-verify-agent-browser.sh` rewrite). Additive; no existing public call
signature changed.

- **Iframe failure taxonomy (P3-04 c4).** `ghl_iframe_drag.py` gains
  `classify_board_reason()` / `board_note()`, mapping every `IframeDragError`
  code into `cc_board.py`'s existing 6-value taxonomy (`SELECTOR-MISS` /
  `VERIFY-FAIL` — never a 7th value), prefixed at position 0 and tagged with
  the cross-origin frame the failure happened inside — iframe problems now
  post a diagnosable board card instead of a generic
  `Build exception: RuntimeError: STOP (survey iframe-drag:<code>)` stall.
  `ghl_survey_builder.py` and `ghl_form_builder.py` carry the classified
  reason through their existing `StopAndReport`/dict-return contracts.
  New `tests/test_iframe_failure_taxonomy.py` (13 tests). Tool version bumps:
  `IFRAME_DRAG_VERSION` v1.3.0 → v1.4.0, `SURVEY_BUILDER_VERSION` v1.5.0 →
  v1.5.1, `FORM_BUILDER_VERSION` v0.1.0 → v0.1.1.
- **Weekly iframe-survival check (P3-04 c4, fix-loop).** New
  `run_iframe_survival_check()` / `--iframe-survival` CLI wired into the
  existing selector-canary machinery (`tools/ghl_selector_canary.py`) —
  read-only, dependency-injected (a caller-supplied `page_fetcher`; no
  network of its own, same discipline as `run_canary()`), checking that a
  set of PUBLISHED pages/surveys/forms still embed their cross-origin
  (`*.leadconnectorhq.com`) iframe (2026-06-27 probe: GHL preview does not
  strip it — this makes that proof CONTINUOUS instead of a one-time
  snapshot). A stripped iframe reuses the SAME `VERIFY-FAIL` cc_board
  taxonomy value (never a 7th). New `tools/iframe-survival-targets.json`
  (ships EMPTY — no client URLs belong in this repo; the operator populates
  real published-page URLs per box before the weekly cron run means
  anything). New `tests/test_iframe_survival_canary.py` (12 tests).
  `CANARY_VERSION` v1.0.0 → v1.1.0.
- **`06-ghl-install-pages/skill-version.txt` intentionally NOT bumped here.**
  Per `scripts/bump-version.sh`'s own "G3-on-06 GAP FIX" comment, this file
  is release-time-owned — it tracks the repo `/version` (`vX.Y.Z`, currently
  `v19.58.0`, matching this branch's parent), not an independent per-skill
  semver, and is rolled ONLY by `bump-version.sh` inside a `chore(release)`
  commit (confirmed: it is not one of the 11 markers `bump-version.sh
  --check` verifies). It will pick up the next repo version automatically
  at the next release commit, same as every prior 06 feature branch's
  observed history (`browser_manager.sh`/`.py` version bumps, this file
  untouched until the following `chore(release)` commit).

---

## [v19.21.0] - 2026-07-10 - Skill-6 SURVEY-builder hardening (Fable review)

Branch **skill6-survey-builder-hardening** (off `skill6-community-course-live-ready`).
Ships the outstanding survey-builder fixes from the Fable review (the repo hardening
the two podcast surveys were built with as a one-off, but which never landed in the
builder itself). Builder **v1.3.0 → v1.4.0**; skill **v19.20.1 → v19.21.0** (next minor
after origin/main — the Fable plan's proposed v19.18.0 was already consumed). Additive;
`build_survey`'s public signature is unchanged (new behaviour is task-key gated).

- **NAV FIX (real 2026-07-10 breakage).** `ghl_survey_builder._p2_navigate_create` no
  longer clicks a left-rail **"Sites"** item that does not exist on this GHL build.
  It now `$router.push`es to `/v2/location/<LOC>/survey-builder/main` (the survey LIST)
  and creates via a native `.click()` on the ref-less **"Add survey"** button through
  the `ghl_ab_executor` find→native resolver (REUSED, not reimplemented) — there is NO
  "Create new survey" modal on this build. The survey id is captured from the builder
  iframe `.src` (`/survey-builder-v2/<id>`, shape-gated). Idempotent reuse: an existing
  row titled exactly `survey_name`, or the empty "Survey 0" shell, is opened in place
  (no duplicate).
- **BUILD-FROM-MAIN GUARD.** New preflight `P4:builder_convergence_capable` HARD-STOPs a
  `converge_slide` / `owner_slide` build on a stale (pre-main) checkout that lacks the
  Area-5.1 convergence primitive — making the silent "convergence-less, unsubmittable
  survey" failure LOUD (`_assert_convergence_capable`, semver-compared).
- **CROSS-ORIGIN-IFRAME DRAG PLAYBOOK — now IN the skill.** New
  `tools/ghl_iframe_dragdrop.py` (reusable tab-click + coordinate-drag ladder, the
  generalized version of the survey bring-up `synth_drag.js` one-off) + new skill-root
  `TECHNIQUES-cross-origin-iframe-dragdrop.md` (detection → 5-rung ladder → capture-gated
  write → pitfalls) + `SKILL.md` pointers. Other iframe-canvas builders reuse it.
- **SMOKE-TEST-FIRST + CAPTURE-GATED REST FALLBACK.** `build_survey` gains a
  `build_method` switch (`browser` default | `rest`). The browser lane now smoke-tests a
  SINGLE tile-drag (`_p2_smoke_test_drag`) and proves it landed via the iframe-aware
  snapshot delta BEFORE the full run — a CLI "✓ Done" that placed nothing is reported
  honestly as a wall. On a wall it falls back to the **capture-gated** REST lane
  (`tools/ghl_survey_rest.py` + `_rest_lane_build`): the save origin/path/verb are
  derived ONLY from a recorded `routing/survey-save-capture.json` receipt (preflight
  `P5:rest_write_proven`) — no hardcoded save endpoint exists, so the lane can never
  blind-POST; a read-back `verify_roundtrip` gates "done".
- **Tests.** New `tests/test_survey_builder_hardening.py` (nav fix, convergence guard,
  smoke-test logic, rest capture-gate, version lockstep) + extended
  `ghl_survey_builder._selftest` / `ghl_iframe_dragdrop._selftest` /
  `ghl_survey_rest._selftest`. Full offline battery green.

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

## [v18.1.12] - 2026-07-08 - F4 remove-control TIERED acquisition — the §6 `role=link 'Remove field'` claim is CONTRADICTED live; rebuild around the evidenced icon-pill mechanism + rich failure diagnostics (the 3×-failed `STOP@F4.delete:Phone` root-cause fix)

**THE ROOT CAUSE (finally evidence-pinned, not another timing tweak).** Three
consecutive live runs failed at `F4.delete:Phone` — attempt #6 (v18.1.9),
attempt #7 (`skill6-attempt7-20260707-222852`), and the v18.1.11 verify run
(`skill6-live-verify-20260708-040836`, HEAD 07d5c453). The v18.1.11 run's own
diagnostics are decisive: after the select-click AND **13 genuine
park-away/re-hover cycles**, BOTH documented forms attached **ZERO** nodes for
the whole 15s budget — `'role=link:Remove field': 0 attached match(es);
'role~=link:Remove field': 0 attached match(es)`. That is NOT hover timing
(v18.1.10's poll/re-stimulation worked exactly as built and proved the point):
**the SELECTORS-LIVE-form.md §6 lock itself is wrong against the live UI.**
The link claim was captured ONCE (2026-07-02) and its raw snapshot was never
retained; it has never been reproduced since. Cross-evidence for the REAL
mechanism: the training video (CLICK-MAP Step 8: "Delete a field = select it →
**trash icon** (top-right of the selected field's blue bar)"; Step 15: a
dropped field "auto-selects (blue outline + **gear/trash icons**)"), the
2026-07-02 capture's own screenshot `008-field-selected.png` (a SELECTED
field's blue pill at its top-right with two ICON-ONLY controls), and GHL
help/community docs ("hover over the field until you see the delete or trash
icon, then click the delete icon"). The per-field controls are therefore in
the §5-documented icon-only class (Naive-UI buttons with NO accessible
name/aria-label/testid) — invisible to EVERY role+name query, which is exactly
what three live runs measured.

**THE REDESIGN (`ghl_iframe_drag` v1.3.0 — tiered acquisition, evidence-first):**

- **Tier 1 — documented specs (unchanged):** `role=link:Remove field` exact +
  the `role~=` lock form still scan first and still win when they attach (§6
  downgraded to conf 4, kept in case the names return).
- **Tier 2 — broad accessible-name scan:** role link/button whose name matches
  `/remove|delete|trash/i`.
- **Tier 3 — attribute scan:** `[aria-label]`/`[title]` containing
  remove/delete/trash (case-insensitive CSS attr match).
  Tiers 2–3 are GATED to the field's top-right **CONTROL ZONE** (geometry from
  the capture screenshot) so a deletion-ish control elsewhere (settings panel,
  dialog) can never be wrong-target clicked.
- **Tier 4 — LAST-RESORT geometric icon-pill ladder** (deadline expired,
  select-click done): a JS census enumerates every small visible clickable
  (`a`/`button`/`[role]`/`svg`) whose center sits in the control zone, with
  per-candidate rejection reasons; accepted candidates are clicked
  RIGHTMOST-FIRST with a REAL pointer (trash sits right of gear on the pill),
  each click individually verified by the count-decrease proof before trying
  the next (max 3; a wrong click hits the benign gear/settings).
- **Selection stimulation widened (the never-actually-SELECTED hypothesis):**
  after 2 fruitless re-hover cycles, ONE real-pointer click lands on the field
  WRAPPER/label strip just above the anchor — the pill provably renders on a
  *selected* field, and clicking the inner input may not register as
  selection. Receipted as `wrapper_click_done`.
- **A 4th failure must explain itself:** `remove-link-not-found` now carries
  `IframeDragError.details` — per-strategy attached/visible counts, the FULL
  geometric census (accepted + rejected-with-reasons), a capped whole-frame
  ARIA snapshot, and the stimulation trace. `ghl_form_builder` persists it as
  `routing/f4-remove-diag-<field>.json` AND captures a failure-moment
  screenshot (`f4-delete-FAILED-<field>`) showing whether the field was even
  selected. Count-decrease proof, idempotent already-absent no-op, and every
  fail-closed code are unchanged; nothing ever fakes a delete.

**Honest docs:** SELECTORS-LIVE-form.md §6 now records the contradiction
(3 live runs, 0 attached, dates), the evidence chain for the icon-pill
mechanism, the tiered doctrine, and re-OPENS CLICK-MAP Ambiguity #4 pending
live census evidence.

**Proof:** `ghl_iframe_drag --selftest` PASS (new 13g: broad name-scan finds a
0-attached-doc-spec control and refuses out-of-zone candidates; 13h: failure
details carry the full strategy census + stimulation + geometric/aria slots)
and `--live-selftest` PASS against a REAL headless Chromium — the fixture now
carries a field whose per-field controls are an icon-only gear+trash pill (NO
name, NO href, NO title — the evidenced live pattern): new case (j) proves the
geometric ladder censuses the pill, real-pointer clicks the RIGHTMOST icon,
and count-verifies the removal. `ghl_form_builder --selftest` PASS;
`ghl_survey_builder --selftest` PASS. Full skill-6 pytest **1169 passed / 15
skipped** (was 1152 — +17 regression locks in
`tests/test_ghl_f4_remove_redesign.py`: name-scan drift + case-insensitive
regex; attr-scan by title/aria-label; out-of-zone deletion controls NEVER
clicked; doc spec still wins over broad tiers; already-absent keeps idempotent
semantics; geometric rightmost-first + count proof; wrong-first-click ladder
fallback; no geometric click without a select-click; wrapper-click fires
exactly once and reveals; failure details census/aria/strategy-counts +
JSON-serializable; unevaluable census degrades honestly; details attribute
contract; deletion-name regex scope; details threading through StopAndReport;
diag receipt + failure screenshot persisted; success path unchanged;
unwritable receipt never masks the STOP). Guards: no-secret-printing PASS,
no-client-names PASS (structural), no-telegram-chat-id-leak PASS,
skill-frontmatter-version PASS, skill-version-newline PASS, version-drift OK.
(Honesty note: earlier entries cite a "no-anthropic-runtime" guard as a
skill-6 gate — the only script by that name in this repo is skill-58-scoped
and does not apply here; it was NOT run as a skill-6 gate for this release.)

**Live status: NOT yet live-proven.** This is the best-evidenced attempt, not
a claim of certainty — the pill's true DOM shape is still unobserved. If a 4th
live attempt fails, `routing/f4-remove-diag-phone.json` + the failure
screenshot will finally show exactly what sits near the selected field's
top-right, and §6 gets locked from that census.

## [v18.1.13] - 2026-07-08 - Pipeline builder PL1.land: poll-with-deadline + rich diagnostics (the first-live-run STOP)

**WHY:** tonight's first live test of the pipeline auto-create walk
authenticated, router-pushed to the real Opportunities▸Pipelines route, and
confirmed ZERO iframes on the surface — but STOPped honestly at `PL1.land`:
no control matching `/Create\s+[Nn]ew\s+[Pp]ipeline/` was visible. Code
inspection found the landing check waited only for the generic word
"Pipeline" (satisfied instantly by the page's own header, regardless of
whether the create control had hydrated), then took **exactly one**
`_snapshot()` and regex-searched that single opaque result — the identical
single-shot-race bug class the sibling `ghl_form_builder.py` already killed
(v18.1.2's `_wait_text_polling`, v18.1.11's `_reveal_row_actions` hover-poll).

**RESEARCH (2026-07-08, help.gohighlevel.com + help.leadconnectorhq.com,
re-fetched — see `SELECTORS-LIVE-pipeline.md` §7 for full citations):** the
button text itself is still documented as "Create new pipeline"/"Create New
Pipeline" — unchanged. GHL's own material confirms the Pipelines screen
"now uses the HighRise design system" (a newer frontend, opt-in via Labs),
consistent with a render race rather than label drift. No source documents
menu-nesting or plan/limit gating for this control. Diagnosis: render race
is the best-evidenced hypothesis; NOT independently confirmed live.

**THE CHANGE (`ghl_pipeline_builder.py`, v0.1.0 → v0.2.0):**

- `_poll_for_create_pipeline_label()`: polls `_snapshot()` + the create-label
  match on our own monotonic deadline — same poll-with-deadline doctrine as
  `ghl_form_builder._wait_text_polling` / `_capture_form_id` / this file's
  own `_save_and_verify` leaf-count poll. Never trusts one opaque snapshot.
- `_diagnose_missing_create_control()`: on a genuine miss, lists every
  distinct 'pipeline'-mentioning text window actually seen (deduped,
  capped), flags any UNCONFIRMED alternate-wording hint (`+ Add Pipeline`,
  `+ New Pipeline`, `Add Pipeline`, `New Pipeline` — evidence only, never
  auto-clicked) and any possible plan/limit-gating text — a second failure
  now explains exactly what was found and why, never a bare "not found".
- `_land_on_pipelines()` STOP message names the poll window and folds in the
  rich diagnostic alongside the existing `_capture_entry_diag` evidence.

**Coverage:** 8 new hermetic pytest cases in
`tests/test_ghl_pipeline_builder.py::TestLandingPoll` (render-race recovery,
clean deadline give-up, zero-budget single-attempt guarantee, rich-diagnostic
STOP text, and the diagnostic helper's empty/no-mention/limit-gating paths) +
selftest sections 5b/5c. Full suite: zero regressions. Still NOT live-locked:
`SELECTORS-LIVE-pipeline.md` remains RESEARCH-SEEDED (§7 records this run's
evidence and the honest caveat that the render-race diagnosis is not
independently confirmed); the next live run is a separate step.

---

## [v18.1.14] - 2026-07-08 - Pipeline builder EXACT-NAME mode (the Anthology Engine integration contract)

> Renumbered v18.1.12 -> v18.1.14 at merge time: two parallel branches (the F4 remove-control
> rebuild, and this pipeline-builder EXACT-NAME work) independently claimed v18.1.12 for
> DIFFERENT changes, and v18.1.13 was already taken by PL1.land. Both entries are preserved;
> this one takes the next free patch number. No content was dropped.

**WHY:** the Anthology Engine (Skill 59) needs its standard pipeline created
with the BYTE-EXACT contract name `"Anthology Engine"` — its
`anthology_registry.py provision-pipeline` binds the created pipeline BY NAME
through the read API (`GET /opportunities/pipelines`) afterwards. The
builder's default applies the fleet `ZHC ` container prefix
(`ensure_zhc_name`), which would rename the pipeline to
`"ZHC Anthology Engine"` and silently break that find-by-name bind.

**THE CHANGE (`ghl_pipeline_builder.py`):**

- **`--exact-name` / `task["exact_name"]`**: the pipeline name is used
  byte-exact — no ZHC prefix. The plan records `exact_name` and the preflight
  swaps `PL-P2:zhc_pipeline_name` for `PL-P2:exact_pipeline_name` (non-empty
  name, hard). The DEFAULT path is unchanged: no flag → ZHC prefix exactly as
  before.
- Skill 59's `provision_pipeline` now invokes this builder (subprocess, fixed
  argv, `--no-dry-run --exact-name`) when the standard pipeline is absent,
  then re-reads the pipelines through the API and binds ONLY what that read
  surface shows — the builder's own success claim is never trusted.
- Coverage: selftest section 1b (byte-exact name, recorded mode, preflight
  pass/refuse-empty) + 6 new hermetic pytest cases in
  `tests/test_ghl_pipeline_builder.py::TestExactNameMode` (plan, preflight,
  CLI wiring, default-path regression). Still NOT live-locked:
  `SELECTORS-LIVE-pipeline.md` remains RESEARCH-SEEDED; the first live run is
  a separate step.

---

## [v18.1.11] - 2026-07-08 - Forms-list row-'Actions' acquisition is the SAME hover-reveal POLL as F4 (cleanup could silently fail to delete) + F-P9 interpreter/Playwright preflight (a live attempt can never be burned on an environment mistake)

**BUG 1 — the Forms-list row 'Actions' button has the SAME hover-reveal
timing as the F4 per-field remove control** (proactively found in tonight's
live-cleanup evidence: exactly ONE matched row title, ZERO 'Actions' buttons
attached — the control does not EXIST in the DOM until the row is hovered).
`_delete_form` made a SINGLE `_eval_actions_button_count` peek and correctly
refused to click (fail-closed, good) — but that means cleanup silently fails
to delete a form whenever the reveal needs a hover, the exact class of bug
v18.1.10 killed inside the builder iframe.

**THE FIX (`ghl_form_builder` — the v18.1.10 doctrine applied to the list
surface):**

- **Hover-then-POLL, never one peek.** `_reveal_row_actions` hovers the
  matched row title (`find text <t> hover` — a REAL Playwright pointer move)
  and polls a monotonic deadline (12s / 0.5s cadence); misses RE-FIRE the
  reveal every 2s by PARKING the pointer at the viewport origin and
  re-entering the row (`mouseenter` only fires on a real re-entry). Hermetic
  data:-page probe: 0 visible 'Actions' buttons before the hover, 1 after;
  parking hid it again.
- **Attached-vs-visible evidence + nearest-row disambiguation.**
  `_ACTIONS_PROBE_JS` measures, in ONE pass, the ATTACHED count, the VISIBLE
  count (non-zero client rect, not `visibility:hidden`), and the viewport
  center of the visible button NEAREST the matched row's title leaf. With
  exactly ONE attached button the §3 locked role-exact anchor is clicked as
  before; with SEVERAL (partial-name matches in the filtered list) the
  nearest one is clicked with a REAL pointer click (`mouse move/down/up`) —
  hermetic probe proved `find role button click --name Actions --exact`
  resolves the FIRST DOM match, which can be a HIDDEN 0×0 button from the
  WRONG row, and still returns rc=0 with NO click delivered (a silent
  wrong-target no-op). Title ambiguity (several rows with the SAME title)
  still fails closed.
- **Fail-closed + diagnosable.** A control that never reveals within the
  deadline refuses to click ANYTHING and reports attached/visible counts plus
  the hover-cycle count; probe-unevaluable (-1) is UNKNOWN, never zero. The
  receipt gains `actions_buttons_attached` / `actions_hover_cycles` /
  `actions_click_method`.

**BUG 2 — wrong-interpreter live harness (F-P9 preflight).** Tonight's live
harness resolved `python3` to a Homebrew python3.14 WITHOUT Playwright instead
of the interpreter Playwright is installed under; the miss would only surface
DEEP in a live walk (F3/F4 ride Playwright-over-CDP) as an opaque
`playwright-unavailable` AFTER a real form existed. `_run_preflight` now takes
`live=` (wired `live=not dry_run` in `build_form`) and HARD-stops a live run
when Playwright is not importable under `sys.executable`, naming the
interpreter and spelling out the fix (`<python3> -m pip install playwright &&
<python3> -m playwright install chromium`, plus the bare-`pip`-belongs-to-a-
different-python trap); dry-run/THINK records it as a soft WARNING and keeps
working. INSTALL.md Step 1 now pins `python3 -m pip` / `python3 -m playwright`
(never bare `pip`/`playwright`) and documents the PATH-shadowing trap.

**Proof:** hermetic E2E against a REAL headless Chromium via the REAL
agent-browser CLI (fixture rows with CSS hover-revealed 'Actions' buttons):
pre-hover probe 3 attached / 0 visible → reveal poll → nearest-coordinate
real-pointer click landed on the CORRECT row (`window.__clicked` receipt) and
opened its menu. `ghl_form_builder --selftest` PASS under BOTH a
Playwright-bearing and the pytest interpreter. Full skill-6 pytest
**1152 passed / 15 skipped** (was 1131 — +21 regression locks: re-hover-only
reveal is found and clicked; never-appearing control fails closed with NO
click and the stimulation proven tried; unknown probe never counts as
revealed; nearest-coordinate click on multi-row reveal + its no-coordinates
and failed-click fail-closed paths; role-exact rc-check; reveal receipt
fields; hover/park/mouse CLI verb shapes; probe JSON parse fail-closed; probe
JS geometry doctrine; F-P9 live hard-stop incl. module-absent, actionable
message content, dry-run softness, `build_form` wiring both ways, and
live-stop-before-any-browser). Guards: no-secret-printing PASS,
no-client-names PASS, no-telegram-chat-id-leak PASS, no-anthropic-runtime
PASS, version-drift OK.

---

## [v18.1.10] - 2026-07-08 - F4 remove-control acquisition is a POLL with hover/select re-stimulation + the documented lock-form name fallback (the live attempt-#6 `STOP@F4.delete:Phone` fix)

**THE LIVE BUG (attempt #6 against a real account).** Auth, F1/F2 form
creation, and the F3 rename all landed (now live-proven); F4 then STOPped at
`F4.delete:Phone` — the Phone field's documented anchor resolved, was hovered
and click-selected, but `role=link:'Remove field'` "never became visible
within 15000ms (TimeoutError)". Root cause, two coupled defects in
`drive_remove_canvas_field` (ghl_iframe_drag v1.2.0) — the SAME classes the
earlier form-id/F2-modal and F2-'Create' fixes killed elsewhere:

1. **One opaque wait, no re-stimulation.** The §6 lock says the per-field
   controls are **hover/selected-revealed**, but after the single hover+click
   the code made ONE `_resolve_visible` call whose slow path is
   `first.wait_for(visible)` — bound to the FIRST DOM match, with nothing
   re-firing the reveal for the whole 15s. The builder only re-renders the
   control on a REAL `mouseenter`, and the pointer never left the field after
   the select-click, so nothing could ever appear (hovering an already-hovered
   point is a browser no-op).
2. **Stricter-than-the-lock name matching.** SELECTORS-LIVE-form.md §6 records
   the affordance as `getByRole('link', { name: 'Remove field' })` — WITHOUT
   `exact`, i.e. Playwright-DEFAULT case-insensitive substring matching.
   v1.2.0 hardened the spec to `exact=True`; a live accessible name drifting
   by case/suffix then attaches ZERO nodes for the entire budget — precisely
   the observed TimeoutError shape.

**THE FIX (`ghl_iframe_drag` v1.2.1 — nothing Phone-specific):**

- **Poll-with-deadline + hover/select re-stimulation.** The remove-control
  acquisition is now a monotonic-deadline POLL (0.25s cadence): every pass
  scans ALL attached matches for a VISIBLE one; the first miss CLICK-SELECTS
  the field exactly once (a control already revealed by hover alone is used
  WITHOUT the click — least canvas disturbance); later misses RE-FIRE the
  hover on a 1s cadence by PARKING the pointer off the field and re-entering
  it (`mouseenter` only fires on a real re-entry).
- **Documented lock-form fallback.** New locator spec `role~=<role>:<name>`
  (Playwright-default name matching — the LITERAL §6 lock form). Every poll
  pass scans the exact spec first, then `role~=link:Remove field`
  (`REMOVE_FIELD_LINK_LOCK_SPEC`); the exact form wins when both attach (the
  v18.1.4 collision discipline stands).
- **Nearest-control pick.** When SEVERAL remove controls are visible at once
  (one per canvas field), the one NEAREST the target field's own bounding box
  is clicked — never the DOM-first one, which belongs to a KEEP field and
  would only fail at the count proof AFTER deleting the wrong field.
- **Decisive honest failure.** `remove-link-not-found` now carries per-spec
  attached-match diagnostics plus the stimulation trace (select-click done,
  N re-hover cycles) so the next live run pins any residual mismatch in one
  read. The receipt gains `remove_link_matched` / `select_clicked` /
  `hover_cycles`. Count-decrease removal proof and the idempotent
  already-absent no-op are unchanged; nothing ever fakes a delete.

**Proof:** `ghl_iframe_drag --selftest` PASS (spec dispatch incl. `role~=` +
new checks 13e/13f: hover-reveal-without-click, lock-form fallback) and
`--live-selftest` PASS (real headless Chromium; the fixture now carries a
field whose control appears ONLY on a re-entry hover AFTER selection — new
case (i) proves the park-away + re-hover cycle against a real browser).
`ghl_form_builder --selftest` PASS; `ghl_survey_builder --selftest` PASS.
Full skill-6 pytest **1131 passed / 15 skipped** (was 1125 — +6 regression
locks: `role~=` grammar, hover-reveal-needs-no-select-click, re-hover-cycle
reveal, lock-form name fallback, never-appearing control fails closed with
diagnostics + stimulation proven tried, nearest-control pick). Guards:
no-secret-printing PASS, no-client-names PASS, no-telegram-chat-id-leak PASS,
no-anthropic-runtime PASS.

---

## [v18.1.9] - 2026-07-08 - F4 default-field reconciliation is REAL + the F5 drop target is role-scoped and visible-match robust (the live attempt-#5 `iframe-drag:target-not-found` fix)

**THE LIVE BUG (attempt #5 against a real account, evidence bundle
`live-attempt-5-evidence/`).** Auth, F1/F2 form creation, and the F3 rename all
landed; the F5 field drag then STOPped at `iframe-drag:target-not-found` — the
drop target `text=Submit` "was not found/visible" inside the builder iframe for
the full 15s (TimeoutError) while the run's own screenshots show the builder
open and healthy. Root cause, two coupled defects:

1. **`text=Submit` is AMBIGUOUS inside the iframe.** The Quick-Add panel carries
   its own **'Submit' CATEGORY header + 'Submit' tile** (SELECTORS-LIVE-form.md
   §8, visible in shot `005-f3-renamed.png`) alongside the canvas Submit
   button, and `drive_drag` bound the target with a blind
   `get_by_text(...).first` — first-in-DOM match. That match never became
   visible, so the visible-wait burned the whole budget and failed "honestly"
   at the wrong element — the SAME class of defect as the v18.1.4 F2 'Create'
   collision, now on the drop side.
2. **F4 default-field reconciliation was a warn-and-keep STUB.** GHL's
   Start-from-Scratch template pre-seeds the canvas (First Name, Last Name,
   Phone, Email, the Terms & Conditions consent block — §6); the plan says
   `default_fields_delete: [Phone, Terms & Conditions]` and the click list
   emits real `delete_field` steps, but the walk just warned
   "kept defaults for the minimal run" (the run's own warnings prove it). The
   kept defaults (a) would have shipped a DUPLICATE Phone once F5 dragged the
   plan's Phone tile in (spec violation), (b) make the kept 'Phone' canvas
   label collide with the 'Phone' Quick-Add tile as a drag SOURCE text, and
   (c) stretch the canvas so Submit sits below the viewport fold.

**THE FIX (nothing Submit- or Phone-specific):**

- **`ghl_iframe_drag` v1.2.0 — visible-match resolution.** Source AND target
  resolution now scans ALL matches of a spec in DOM order and binds the FIRST
  VISIBLE one (`_resolve_visible`; wait-then-rescan fallback preserved for
  slow-rendering, unambiguous specs). An all-hidden target still fails closed
  as `target-not-found` — now carrying attached-match diagnostics
  ("N attached match(es), none visible") and a `target_matches` receipt field.
- **New documented locator specs:** `role=<role>:<name>` →
  `get_by_role(..., exact=True)` and `placeholder=<text>` →
  `get_by_placeholder(...)`. The FORM builder's drop anchors are now SPEC
  pairs: **`role=button:Submit`** (§5, conf 9 — the locked canvas landmark)
  with the §6 placeholder anchors as fallbacks; `_perform_iframe_drag` passes
  the spec VERBATIM (the old unconditional `text=` wrapping was the ambiguity).
  `_canvas_drop_anchor` always returns a spec (advisory-snapshot doctrine —
  the frame-scoped resolve is the authoritative fail-closed gate).
- **F4 reconciliation is REAL and fail-closed.** New shared primitive
  `drive_remove_canvas_field`/`remove_canvas_field`: select the canvas field by
  its DOCUMENTED anchor (§6 placeholders; the consent block by its consent
  paragraph text) → click the per-field **`role=link 'Remove field'`** control
  (§6, conf 8) → prove the removal by a **COUNT-DECREASE** of the field's own
  anchor (mirror of the v1.1.1 count-delta placement proof). 0 matches = a
  truthful idempotent already-absent no-op (safe re-runs). The walk's F4 branch
  now calls it per `delete_field` step — BEFORE any F5 drag — and a genuine
  miss STOPs at the honest `F4.delete:<name>` / `F4.anchor:<name>` step
  (never invented CSS, never a form shipped with fields the plan excluded).
  The SURVEY builder has no default-field surface (blank first slide) — it
  inherits the visible-match target robustness through the shared primitive.
- **Hermetic-suite isolation completed (`tests/test_parallel_saves.py`).** The
  four fake-location batch harnesses (`test0caploc` / `test0failureloc` /
  `test0concurrencyloc` / `test0maxsessionloc`) now pass
  `BM_DURABLE_ROOT_OVERRIDE=""` like the v18.1.8 singleton harnesses — a fake
  HOME alone does NOT protect a box where `/data/.openclaw` exists (checked
  FIRST by `_bm_durable_root`), so a suite run there wrote real
  `agent-browser-test0*.count` breaker state into the box's durable park dir.

**Proof:** `ghl_iframe_drag --selftest` PASS (new checks 12-13: ambiguous
hidden-first 'Submit' resolves to the visible landmark + all-hidden still fails
closed with diagnostics; remove-field happy/absent/no-link/no-drop paths);
`--live-selftest` PASS against a real headless Chromium whose fixture now
carries a hidden first-in-DOM 'Submit' node, a real `role=button` Submit, and a
removable default field with a 'Remove field' link (cases a/c/f re-prove the
ambiguity fix live; new g/h prove the role-scoped target + the F4 remove flow
end-to-end, including idempotent re-run). `ghl_form_builder --selftest` PASS
(drop spec locked to `role=button:Submit`; F4 walk deletes via the two
documented §6 anchors in order BEFORE the drag; a remove miss STOPs at
F4.delete and never drags). Full skill-6 pytest: **1125 passed / 15 skipped**
(+16 new regression locks, zero regressions; the box's real durable park dir is
byte-identical after a full suite run). Guards: no-secret-printing PASS,
no-client-names PASS, no-anthropic-runtime PASS.

---

## [v18.1.8] - 2026-07-07 - COUNT-DELTA placement proof + the suite can never PARK a real box again (two defects the final review pass caught)

**1. Drag verification was trivially satisfiable for Quick-Add tiles.** The
in-frame `verify_text` equals the TILE's own label — which already matches
BEFORE the drag (object-field search rows too) — so a FAILED drop would have
verified as placed; and with the top-frame snapshot re-check demoted to a
warning in v18.1.5, nothing downstream would have caught it. `drive_drag`
(v1.1.1) now reads the PRE-drag match count as a baseline and the placement
proof is `count > baseline` (`_verify_placed(min_count=pre+1)`); the receipt
carries `verify_pre_count`, and `not-placed` names the baseline. Proven
hermetically AND against a real headless Chromium (live-selftest case (f):
a SECOND drag of the same tile must push 'State placed' from 1 → 2).

**2. The hermetic suite was PARKING the operator's real box.** The
teardown-abort test simulates aborts for the fake location `abortloc`, but the
v14.1.5 durable-breaker change moved park state to the box's REAL
`.openclaw/workspace/.park` — so every full-suite run appended a real abort
count until the circuit-breaker tripped and wrote the box-level
`workforce-build.parked` (observed live 2026-07-07 on the operator box; the
marker read `location=abortloc` — pure test provenance; the three abortloc
artifacts were removed, pre-existing park files untouched). Fix:
`browser_manager.sh:_bm_durable_root` honors an explicit
`BM_DURABLE_ROOT_OVERRIDE` (set-even-if-empty semantics; production callers
never set it), the two bash harnesses in
`tests/test_browser_manager_singleton.py` pass override='' + a fake HOME so
breaker/park state stays in the ephemeral lockdir, and NEW regression locks
prove BOTH directions: ephemeral isolation (state lands in the lockdir, no
durable `.openclaw` appears under HOME) AND preserved durable semantics (an
explicit override root receives the state).

Full skill-6 pytest: **1109 passed / 15 skipped**; the durable park dir is
byte-identical after a full suite run. `--selftest` + `--live-selftest` PASS.

---

## [v18.1.7] - 2026-07-07 - Survey Phase-B rename wiring LOCKED + targeted mutation-kill evidence for the v18.1.5/v18.1.6 wave

- NEW hermetic locks in `tests/test_ghl_iframe_drag.py`: the SURVEY builder's
  Phase-B rename must route through the frame-scoped
  `set_inline_title` (survey iframe selector + `re:^Survey \d+$` pattern
  specs, url_marker `survey-builder`), and a missing primitive / missing CDP /
  failed rename are all honest STOPs — a survey can never proceed
  default-named (the same silent-failure class the FORM builder hit live
  2026-07-07).
- MUTATION-KILL PROOF for the wave's load-bearing lines (each mutation flipped
  ONE line; the suite had to fail): source-scroll removal, hint-miss swallow,
  editable-gate bypass, exactly-one-row gate bypass, post<=0-as-gone, save
  rows<0 gate, rename-always-true — **7/7 KILLED**, working tree byte-restored
  after each run.
- Full skill-6 pytest: **1106 passed / 15 skipped** (+2).

---

## [v18.1.6] - 2026-07-07 - PIPELINE (+stages) CREATION via BROWSER CONTROL — new `ghl_pipeline_builder.py` (no public API exists for this surface)

Operator-ratified boundary (2026-07-07): GHL exposes NO public API to CREATE a
pipeline or CREATE/EDIT pipeline stages — confirmed the same night against
GHL's real v2 AND v3 OpenAPI specs. The only public surface is the read-only
`GET /opportunities/pipelines` (Skill 44 `caf opportunities pipelines`), and
Skill 44 was audited to have NO pipeline-creation capability of any kind
(API or browser). Pipeline/stage creation is therefore UI-only and now ships
as a Skill-6 browser walk. Custom FIELDS stay on the proven Skill-44 API path
(explicitly out of scope per the same ratification); opportunity CRUD stays on
Skill 44's `caf opportunities …` API.

New `tools/ghl_pipeline_builder.py` (v0.1.0):

- **THINK layer**: ZHC-prefixed pipeline name (fleet container convention),
  stage normalization that STRIPS manual Won/Lost (GHL auto-creates the
  terminal stages — a manual duplicate would corrupt win/loss semantics),
  preflight, and a dry-run click list (PL1–PL7) that spells out the Skill-44
  id-capture handoff for post-build opportunity wiring.
- **DO layer**: REUSES the form builder's proven primitives (one implementation
  of the v18.1.3 text-verb doctrine, v18.1.4 role+exact clicks, v18.1.1+
  poll-with-deadline waits, the token-only seed rail, and the v18.1.5
  walk_state + leaf-count positive-verification machinery) — locked by a
  source-level test that forbids forked copies.
- **RUNTIME-BOUND anchors**: the flow is docs-seeded (official HighLevel
  support portal, researched 2026-07-07: Opportunities ▸ Pipelines →
  "Create new pipeline" → Pipeline Name → per-stage "Add stage" → Save), and
  GHL's own docs disagree on the button's capitalization — so labels are bound
  by PATTERN from the live snapshot and clicked role=button + --exact on the
  string the page ACTUALLY shows. Documented in NEW
  `tools/SELECTORS-LIVE-pipeline.md`, honestly marked RESEARCH-SEEDED (NOT
  live-locked) until the first live run captures real anchors.
- **POSITIVE verification everywhere**: the typed pipeline name and every typed
  stage must RENDER (STOP otherwise); the saved pipeline must appear in the
  RENDERED Pipelines list (leaf-text count ≥ 1) or `PL6.verify` STOPs — never
  an unverified 'created'.
- **Fail-closed cleanup** (`_delete_pipeline`): present→delete→absent proof.
  Requires EXACTLY ONE rendered row for the ZHC test name; the whole-pipeline
  delete flow is UNDOCUMENTED (runtime-capture), so it only ever clicks a
  delete affordance it can COUNT to exactly one on screen — ambiguous or
  unlocatable affordances are an honest not-deleted + OPERATOR REVIEW flag,
  never a blind click on a real account. Unknown counts (-1) never read as
  gone. Auto-runs after a STOP that may have left a partial pipeline behind.

Files: NEW `tools/ghl_pipeline_builder.py`, NEW `tools/SELECTORS-LIVE-pipeline.md`,
NEW `tests/test_ghl_pipeline_builder.py` (28 cases), SKILL.md inventory.
Proof: `ghl_pipeline_builder.py --selftest` PASS; full skill-6 pytest
**1104 passed / 15 skipped** (was 1076 — +28, zero regressions).

---

## [v18.1.5] - 2026-07-07 - F5 BELOW-THE-FOLD LOCATE + F3 FRAME-SCOPED RENAME + POSITIVE-VERIFY CLEANUP — the three defects live attempt #4 exposed, fixed at their shared root (the cross-origin iframe reach seam)

Live attempt #4 (the furthest run yet — past auth, the Forms list, the create
modal, INTO the real builder) exposed three distinct defects. All three are
fixed through the SAME proven frame-scoped Playwright-over-CDP seam
(`ghl_iframe_drag`, now v1.1.0), hermetically proven (dep-free selftest + a
real-Playwright cross-origin fixture + pytest), with zero regressions
(1076 passed / 15 skipped, up from 1035).

**1. `F5.locate:City` — a Quick-Add tile below the panel fold was a false STOP.**
The Quick-Add panel is a scrollable column of category sections
(SELECTORS-LIVE-form.md §8); `City` sits under `Address`, below the fold, so it
was absent from the top-frame a11y snapshot and the old snapshot-gate STOPped a
tile that was 100% reachable. General fix for ANY field in ANY category (never a
City-only patch):

- `ghl_iframe_drag.drive_drag` now scrolls BOTH the source tile and the drop
  target into view (Playwright `scroll_into_view_if_needed`, actionability-aware,
  no-op when already visible — playwright.dev/python, verified) BEFORE reading
  bounding boxes, and reads the boxes AFTER all scrolls.
- New `source_scroll_hint` parameter: when the source misses directly, the hint
  (the tile's CATEGORY header text from `QUICK_ADD_TAXONOMY`) is scrolled into
  view FIRST to reveal its section, then the source is retried. Fail-closed codes
  `scroll-hint-not-found` / `source-not-found` keep a genuinely absent tile an
  honest STOP.
- `ghl_form_builder._place_quick_add_field` passes each field's
  `quick_add_category` as the hint automatically and demotes the top-frame
  snapshot to ADVISORY (the frame-scoped locate is authoritative — it has real
  access to the cross-origin frame); a frame-scoped locate miss maps back to the
  honest `F5.locate:<tile>` step. The post-drag top-frame snapshot re-check at
  F5/F6 is likewise demoted to recorded evidence — the in-frame `verify_text`
  gate (which raises `not-placed`) is the authoritative placement proof.

**2. F3 rename silently failed → a REAL form left default-named ("Form 55").**
The title is an in-iframe inline-edit surface; the old top-frame
`dblclick <xpath>` + `keyboard type` walk could never reach it (same cross-origin
constraint as the drags) and was treated as cosmetic. Fix:

- New `ghl_iframe_drag.set_inline_title` / `read_inline_title`: pattern-locate
  the title (`re:^Form\s*\d+$` — the default number is unknowable), click (then
  double-click) into edit mode with a VERIFIED editable-focus check (fail-closed
  `title-not-editable` — typing into a non-editor is now impossible), select-all
  (`ControlOrMeta+A`, per-platform fallbacks) + type + Enter, then VERIFY the new
  text inside the iframe (`title-not-set` otherwise). Proven against a real
  click-to-edit input inside a genuine cross-origin fixture (--live-selftest).
- `ghl_form_builder._rename_form_title` (replaces `_try_rename`): renames via the
  primitive and — success OR failure — records the title the form ACTUALLY
  carries (`actual_title`, read back from the iframe) so cleanup targets the real
  name, never an assumption. Idempotent (an already-renamed form reads back as
  the target → renamed).
- The walk's F3 is now FAIL-CLOSED by default (`rename_required`, plan-carried):
  a build never proceeds on an unlabeled container; even on STOP the actual title
  is recorded for cleanup. The SURVEY builder's Phase B rename
  (`_p2_rename_survey`) rides the same primitive (`re:^Survey\s*\d+$`).

**3. Cleanup claimed "no form was created" while a real form sat live.**
Two compounding defects: (a) `_walk_click_list` captured the form id into a LOCAL
thrown away when a later step raised StopAndReport, so cleanup saw no id; (b)
`_delete_form` ignored every click rc and inferred success from a name-match
absence — with the rename silently failed, the search for the intended name found
nothing and "no residue" was fabricated. Fix:

- New caller-owned `walk_state` dict: `form_id` / `actual_title` are recorded AT
  CAPTURE TIME and survive the exception path; `_live_build`'s cleanup uses them.
- `_delete_form` overhauled to a POSITIVE present→delete→absent proof: search the
  ACTUAL title first, count RENDERED leaf-text matches via top-frame eval (the
  search textbox echoing the query can never satisfy the check — input values are
  not textContent), require EXACTLY ONE matching row title AND EXACTLY ONE
  visible row `Actions` button (never risk the wrong row), rc-check every click
  (row `Actions` role-button, `Delete` role-MENUITEM exact — new
  `_click_menuitem`, dialog `Delete` role-button exact per SELECTORS §3), then
  POLL the re-searched list to ZERO matches. Anything unverifiable returns
  `deleted=False` + evidence; unknown counts (-1) NEVER read as gone.
- New `_verify_no_residue` for the no-form-id path: positively proves the
  intended name is absent from the RENDERED list (leaf-count 0), actually deletes
  a row if one is found, and flags `possible_unnamed_orphan` LOUDLY when the walk
  stopped between the create-confirm and the id capture (a default-named form
  cannot be safely auto-deleted by name — operator review required).

Files: `tools/ghl_iframe_drag.py` (v1.1.0), `tools/ghl_form_builder.py`,
`tools/ghl_survey_builder.py`, `references/iframe-drag-capability.md`,
`tests/test_ghl_iframe_drag.py` (+13 cases), NEW
`tests/test_ghl_form_rename_and_cleanup.py` (27 cases),
`tests/test_ghl_text_verb_cli_shapes.py` (rename lock modernized).

---

## [v18.1.4] - 2026-07-07 - F2 MODAL-CONFIRM DISAMBIGUATION: the 'Create' confirm click now targets role=button + EXACT accessible name — a substring click resolves to the WRONG element when three 'Create'-text elements coexist

The next defect in the F2 chain, live-evidenced the same day and UNDER the
v18.1.1–v18.1.3 fixes (all of which remain correct and in place — the
create-modal now provably OPENS; this fix is about confirming it). With the
'Create new form' modal open, THREE separate on-screen elements contain the
text 'Create' simultaneously:

1. the page header's '+ Create form' button, sitting BEHIND the modal overlay;
2. the modal's own title text, 'Create new form';
3. the blue confirmation button labeled exactly 'Create'.

The confirm step emitted `find text Create click` — a SUBSTRING match that
resolves to the FIRST DOM-order hit, which is NOT the confirm button. Live
evidence: the click returned rc=0 (it landed — on the wrong element), the SPA
never navigated off `/form-builder/main`, no `form-builder-v2` iframe ever
mounted, and the v18.1.1 id-capture poll correctly timed out and STOPPED
honestly instead of faking success.

Proven hermetically on the same locator engine agent-browser 0.27.0 wraps
(collision-fixture probe, no live-account contact):

- text substring `Create` → **3 matches**; first DOM-order = the header
  '+ Create form' button (the wrong element);
- role=button + name `Create` + exact → **exactly 1 match** — the modal
  confirm; clicking it fired the confirm handler;
- role=button + name `Create` WITHOUT exact → still **2 matches** (substring
  pulls the header button back in) — `--exact` is REQUIRED, not decoration.

Changes:

- `tools/ghl_form_builder.py` — new `_click_button(session, name)` primitive
  emitting `find role button click --name <name> --exact` (flags per
  `agent-browser find --help`, 0.27.0 — the `gates.json` pin). This is
  SELECTORS-LIVE-form.md §4's LOCKED anchor for the modal confirm,
  `getByRole('button', { name: 'Create' })` (confidence 9.5), expressed
  through the CLI. Role=button excludes the modal title (not a button);
  `--exact` excludes the header button ('Create form' ≠ 'Create'
  byte-for-byte) — exactly one candidate can match.
- The F2 confirm step now uses `_click_button` and CHECKS its rc: with the
  modal proven open (still gated on 'Start from Scratch'), an exact-name miss
  is structural, so the walk STOPs at a new honest gate `F2.confirm` with
  live page-state evidence — instead of polling the id capture for a
  navigation that can never happen.
- `_click`'s docstring now carries the substring/first-DOM-order ambiguity
  warning so future call sites don't reintroduce the pattern on collision-
  prone chrome text.
- Tests (`tests/test_ghl_form_builder_capture.py` — new
  `TestWalkF2ConfirmDisambiguation`; `tests/test_ghl_text_verb_cli_shapes.py`
  — CLI-shape + source-lock additions): a collision fixture models all three
  'Create'-text elements at the `_ab` seam with the probe-proven resolution
  semantics (a loose text click "succeeds" rc=0 but does NOT navigate; only
  the role+exact click enters the builder route). The walk-level regression
  proves the confirm step captures the form id amid the collision and NEVER
  emits the ambiguous `find text Create click`; an rc≠0 confirm STOPs at
  `F2.confirm` without touching the capture poll; and a source-level lock
  keeps the ambiguous substring-Create emission from ever coming back. All
  key new tests FAIL on the pre-fix code (mutation-checked against 78ca1ae0).
- KNOWN LATENT TWIN (out of scope here, documented for the next operator):
  `tools/ghl_survey_builder.py` P1 Step 6 clicks 'Create' via the same
  substring helper inside the Create-folder dialog (page shows a
  'Create folder' button at the same time). Same collision class; fix the
  same way when that walk is next touched.

Version bump v18.1.3 -> v18.1.4 (skill-version.txt + SKILL.md frontmatter +
CHANGELOG in lockstep).

---

## [v18.1.3] - 2026-07-07 - TEXT-VERB ROOT-CAUSE FIX: bare `click`/`fill`/`wait` positionals are CSS SELECTORS, not text matches — every text interaction now uses the CLI's real text verbs

The deeper bug UNDER the v18.1.1/v18.1.2 fixes (both of which remain correct
and in place): per agent-browser 0.27.0's own `--help` for each verb, a BARE
positional on `click` / `fill` / `wait` / `dblclick` / `type` is a CSS
selector / XPath / `@ref` — NEVER a text match. Proven hermetically on a
`data:` URL with no live-account contact:

- `wait -- "Start from Scratch"` with that exact text visibly present →
  rc=1 timeout; `wait --text "Start from Scratch"` → rc=0.
- `click "Create form"` on a button with that exact label → rc=1
  "Element not found"; `find text "Create form" click` → rc=0.

So every live run failed at the SAME step (F2, "Create form") because the
click NEVER actually happened — the walk only reached F1 because F1 navigates
via a router-push `eval`, not a text click. Every text-based `_click` /
`_fill` / `_wait_text` / `_type` / `_dblclick` call in the WHOLE walk (forms
AND surveys) was affected.

Changes (fix lives in the SHARED HELPERS so every caller is corrected at once
and future call sites can't reintroduce the bug):

- `tools/ghl_form_builder.py` — `_wait_text` now emits `wait --text <text>`
  (substring match); `_click` emits `find text <target> click`; `_fill` emits
  `find label <x> fill <v>` with a `find placeholder <x> fill <v>` fallback
  (GHL search boxes like "Search by Name" are placeholder-identified), rc
  semantics preserved (rc==0 iff a fill landed). `_try_rename` binds the
  inline title via an XPath text-node match (new quote-safe `_xpath_text`;
  `dblclick` has no text mode and `find` has no dblclick action) and types
  through `keyboard type <text>` (types into the FOCUSED element — bare
  `type <text>` parsed the text as a selector).
- `tools/ghl_survey_builder.py` — same fix for its own `_wait` / `_click` /
  `_fill` / `_type` / `_dblclick` helpers, and the five raw
  `_run_cmd(session, "click", ...)` call sites (dialog Create, inter,
  Paragraph, 2x gear) now route through the fixed `_click`.
- SECOND compounding defect fixed in both glue layers (`_ab` / `_run_cmd`):
  `ghl_builder.browser_cmd` joins args into ONE string with a plain
  `' '.join` and the glue re-splits it with `shlex.split`, so an unquoted
  multi-word arg ("Create form", "Search by Name", a JS eval payload, a
  screenshot path with spaces) silently SHATTERED into separate CLI tokens.
  Every arg is now `shlex.quote`d before the join and survives the round-trip
  as exactly ONE argv token; bare flags (`-i`, `--text`) are unchanged.
- `tools/ghl_iframe_drag.py` audited: NOT affected (pure Playwright over CDP;
  zero agent-browser CLI subprocess calls).
- Retry/poll logic from v18.1.1/v18.1.2 (`_wait_text_polling`,
  `_capture_form_id` poll-with-deadline, the rc-checked F2 modal gate) is
  UNCHANGED — those fixes gated a click that never landed; now it lands.
- `--selftest` placement checks updated to the corrected `find label ... fill`
  shape + a new regression lock: any BARE `click`/`fill`/`wait --` emission
  in the placement path is a selftest FAILURE.
- NEW `tests/test_ghl_text_verb_cli_shapes.py` (20 tests): verifies the ACTUAL
  argv built by each helper (real `browser_cmd` join inside the hermetic
  emitter-only `browser_session()` bracket, `subprocess.run` seam recorded) —
  wait/click/fill/type/dblclick shapes, one-token quoting of multi-word text,
  label→placeholder fill fallback + honest double-miss rc, XPath text-literal
  quote-safety, and source-level locks against the bare forms returning.

Suite: 1029 passed (was 1009), 15 skipped. Both module selftests PASS.
Version bump v18.1.2 -> v18.1.3 (triple-equality drift gate OK).

## [v18.1.2] - 2026-07-07 - F2 create-modal wait FIX: poll-with-deadline (the v18.1.1 gate worked; the wait under it didn't get its budget)

Fixes the F2 create-modal wait itself. A second live run (2026-07-07, same
client account, AFTER v18.1.1 shipped) still stopped honestly at
`STOP@F2.modal` — the v18.1.1 rc-checked gate worked EXACTLY as designed (it
is not the bug) — but diagnosis of the wait it gates found the wait never got
the budget its own `timeout=` argument implies:

- `_wait_text(session, text, timeout=N)` shells out to a single
  `agent-browser wait -- <text>` call. Per `agent-browser --help` there is no
  generic per-call `--timeout` CLI flag — the Python `timeout=N` kwarg is ONLY
  the `subprocess.run` kill-switch. The wait duration `agent-browser` itself
  actually uses is its own `AGENT_BROWSER_DEFAULT_TIMEOUT` (default 25000ms),
  entirely outside this file's control.
- F2's modal wait passed `timeout=20` — SHORTER than agent-browser's own 25s
  default — so the Python watchdog could silently force-kill the wait
  subprocess up to 5s BEFORE agent-browser's own native wait would have
  elapsed, on exactly the step (a cross-origin SPA modal transition) most
  likely to need the full window on a slow, form-heavy real account. (F1's
  forms-list wait, by contrast, used `timeout=25` — matching the native
  default — and passed live both times.)

Changes (`tools/ghl_form_builder.py`):

- **New `_wait_text_polling(session, text, timeout_s=20.0)`**: polls short,
  bounded `_wait_text` sub-calls (4s each, 0.5s pace) against OUR OWN
  monotonic deadline — same poll-with-deadline doctrine as `_capture_form_id`
  (v18.1.1) — instead of trusting one opaque single-shot call to honor a
  budget it never actually receives from agent-browser.
- F2's create-modal wait (both the initial wait and the one-retry wait) now
  calls `_wait_text_polling` instead of a raw `_wait_text`. The rc-checked
  gate, the one-click retry, and the honest `StopAndReport("F2.modal", ...)`
  with page-state evidence (v18.1.1) are UNCHANGED — only the wait underneath
  is now a real poll.
- The `_wait_text` calls for F1 (`Create form`) and the Save-wait evidence
  read after `Create` are left as-is: F1's is not gating and already matched
  agent-browser's native default; the Save-wait is explicitly evidence-only
  (`_capture_form_id`'s poll is the authoritative entered-the-builder check).

Tests (`tests/test_ghl_form_builder_capture.py`, +8): `_wait_text_polling`
rides through early misses to a later success; returns cleanly (bounded,
never hangs) at the deadline; zero-budget keeps single-shot semantics; every
sub-call gets a real positive int timeout; None-sentinel defaults read the
module constants at call time; shipped 20s/4s/0.5s window locked; walk-level
regression proving a late-rendering modal (misses twice, hits on the third
poll) now succeeds on the FIRST `Create form` click with no click-retry
needed — the exact scenario the pre-fix single-shot wait could not ride out.
Suite: 1009 passed, 15 skipped (was 1001/15 before this fix).

## [v18.1.1] - 2026-07-07 - form-id capture FIX: poll-with-deadline + honest F2 modal/create gates (pre-existing bug blocking live verification of the iframe-drag fix)

Fixes the PRE-EXISTING `_capture_form_id` failure (untouched by the v18.1.0
iframe-drag commit) that stopped a live form build at `STOP@F2.create` BEFORE the
drag step the v18.1.0 fix targets could ever run. Live evidence (2026-07-07, a
slow, form-heavy client account on a fleet VPS box):

- The run's `f2-create-modal` screenshot was **byte-identical** (same md5) to the
  `f1-forms-list` screenshot — the Create-new-form modal NEVER opened — yet the
  walk blundered on because the `_click`/`_wait_text` return codes at F2 were
  ignored, and the miss finally surfaced two steps later as a misleading
  `F2.create` "could not read the form id" report.
- Even on the happy path, `_capture_form_id` was a **single-shot** eval: the SPA
  flips to `/form-builder-v2/<id>` and mounts the builder iframe ASYNCHRONOUSLY
  after the modal `Create` click, so one read raced the mount and returned ''.

Changes (`tools/ghl_form_builder.py`):

- **`_capture_form_id` now POLLS on a monotonic deadline** (default 15s budget,
  0.5s pause — module constants `_FORM_ID_CAPTURE_TIMEOUT_S` /
  `_FORM_ID_CAPTURE_POLL_S`; same poll pattern as `ghl_iframe_drag._verify_placed`,
  never a fixed sleep). Returns the id as soon as ONE attempt clears the
  server-side shape gate (`[A-Za-z0-9]{15,30}` fullmatch, unchanged, enforced per
  attempt); returns '' CLEANLY at the deadline (bounded — never hangs); always
  makes at least one attempt.
- **F2 modal gate**: the `Start from Scratch` wait rc is now CHECKED; one retry
  click, then an HONEST `StopAndReport("F2.modal", ...)` instead of blundering
  into Create/capture blind.
- **Evidence-bearing STOPs**: both F2 STOP reports now attach live page-state
  (`_capture_entry_diag`: top-frame path + up-to-6 truncated iframe srcs — the two
  surfaces the capture JS reads) plus the Save-wait rc and the poll budget, so the
  next operator sees WHERE the browser actually was.

Tests (`tests/test_ghl_form_builder_capture.py`, +10): poll rides through
late-mounting iframe srcs; deadline return is clean and bounded (never hangs);
zero-budget keeps single-shot semantics; shape gate enforced per attempt;
None-sentinel defaults read the module constants at call time; shipped window
locked at 15s/0.5s; walk-level F2 gates (modal fail-fast after one retry, retry
success proceeds, walk uses the polling capture, capture-miss STOP carries the
page-state evidence). Suite: 1001 passed, 15 skipped.

## [v18.1.0] - 2026-07-07 - cross-origin iframe drag FIX: shared frame-scoped coordinate-drag primitive (forms + surveys)

Fix branch **fix/skill6-ghl-form-iframe-drag**. Fixes the real bug where field
placement in the GHL FORM (and SURVEY) builder could never complete because the
builder renders inside a **cross-origin iframe** and `agent-browser` 0.27.0 cannot
LOCATE a non-interactive drag-source tile across that boundary (its `frame` verb
only re-scopes the read-only a11y snapshot; `eval`/`find`/`drag` still bind to the
top frame — verified live, SELECTORS-LIVE-form.md §7, and re-verified against a
two-origin fixture during this fix). There is NO GoHighLevel/LeadConnector REST API
that creates or edits a form's field schema (public v1/v2 are read-only for form
definitions — confirmed), so the fix does NOT go through an API.

- **NEW `tools/ghl_iframe_drag.py`** — a SHARED, reusable, builder-AGNOSTIC
  frame-scoped coordinate-drag primitive. Any Skill-6 script can import
  `coordinate_drag(cdp_url, *, iframe_selector, source, target, verify_text, ...)`.
  Architecture (hybrid): agent-browser stays the PRIMARY engine (Firebase-token
  login injection, navigation, clicks); Playwright attaches to the SAME
  already-logged-in Chromium over that session's CDP endpoint (`get cdp-url` →
  `connect_over_cdp`) and performs ONLY the drag — one browser, one login, zero
  duplicate auth. It resolves the tile's TRUE page coordinates with a frame-scoped
  `frame_locator(...).bounding_box()` (works across the cross-origin boundary), then
  drives a RAW interpolated-pointer drag (>= 20 moves per gates.json; a single
  down→up does not trip GHL's drag sensor), which works whether the builder uses
  native HTML5 DnD or a custom mousedown dragger. Headless (D6): live path uses
  agent-browser's already-headless Chromium; the self-test browser uses
  `launch_persistent_context(headless=True)` — never a bare `launch()`. FAIL-CLOSED:
  `IframeDragError` on any unlocatable source/target, null box, or unverified
  placement — never fakes success. Self-tests: `--selftest` (dep-free structural)
  and `--live-selftest` (real Playwright vs a local cross-origin fixture, headless).
- **`tools/ghl_form_builder.py`** — the F5 (Quick-Add) and F6 (Add-Object-Fields)
  drag steps now route through the frame-scoped seam `_perform_iframe_drag(...)`
  instead of the top-frame-only `_ab(session, "drag", ...)` (which could not reach
  the tile). The existing STOP-and-report fail-closed behavior is preserved. Offline
  self-test updated to prove the drag routes through the seam (not a top-frame drag).
- **`tools/ghl_survey_builder.py`** — same fix wired into `_p2_pull_object_fields`
  (same cross-origin builder host `survey-builder-v2`).
- **NEW `tests/test_ghl_iframe_drag.py`** — 13-case regression suite (hermetic mocks
  + Playwright-gated real cross-origin proof, skipped cleanly when Playwright absent).
- **NEW `references/iframe-drag-capability.md`** — documents the capability, the
  audit of other Skill-6 iframe surfaces (page/funnel Code-element drag noted as a
  ready-to-wire follow-on; page/funnel CONTENT stays REST via `ghl_rest_canvas.py`),
  and the smoke-test labeling convention (`TEST - OpenClaw Skill6 Verification - DO
  NOT USE`, deleted at end of run).
- **QC** — `qc-ghl-install-pages.sh` asserts the primitive parses + passes its
  dep-free self-test, with a warn-only LIVE self-test (needs Playwright).
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
