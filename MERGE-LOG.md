# MERGE-LOG — openclaw-onboarding · integrate-resume-20260902-onboarding
Wave: resume 2026-09-02/03 · Merge writer: [opus] R-MERGE-onboarding · Base: smoke1-baseline-20260902 (HEAD a29a4cbc2 pre-merge snapshot)

## 1. Diffs collected (60 wave diffs, 12 dirs R-B01..R-B08, R-F01..R-F04)

All 60 target openclaw-onboarding (presentations module vendored in onboarding repo; CC-repo hypothesis disproved — every diff path resolves under this repo). 11 were zero-hunk no-ops. Applied in ascending fix-number order with per-diff status capture; conflicts resolved keeping the higher fix number.

## 2. Conflicts resolved (12 UU + 6 marker-remnant files) — rule: higher fix number wins

| File | Resolution |
|---|---|
| presentation-canonical-entry.sh | kept ours (SCRIPTS_DIR) + theirs FIX59/60 content |
| presentation_job/__main__.py (x4 hunks) | kept ours FIX105 (528-line phase executor) |
| presentation_job/model_router.py | combined: theirs FIX114 plausible-key check + ours FIX17a indent |
| representation-casting-director.md / presenters-speech-writer.md | ours FIX87 + restamp |
| typography docs (x2) / _index.json (x6) | ours FIX87 + restamp |
| scripts/notify.sh | ours FIX64 (nested bundle-dir notify) |
| universal-sops SOP-SLIDE-05 / WORKERS-TUNING-EXAMPLE | ours 62-phase doctrine |
| MANIFEST-SOURCE.txt / PIPELINE-MANIFEST.json | auto-resolved (v63) |
| Mid-run incident | `git reset --merge` unstaged prior resolutions; worktree recovered via stash+replay. Deterministic replay: restore modified files to HEAD, re-apply 60 diffs fix-ascending, resolve per rule, add after each. Result: 13 OK, 31 conflict-resolved, 5 no-op-verified, 6 empty, 5 no-hunk. |

## 3. No-op / pre-landed verification (hunks could not apply; fix content verified present on disk)

- FIX 16 (R-B01-B5): phase_verifiers.py:796 — image-grounding-steward + casting-director switch
- FIX 48 (R-B02-B5): presentation_job/board.py
- FIX 49 (R-B03-B1): presentation-watchdog.plist.template
- FIX 59 (R-B03-B2): presentation-canonical-entry.sh + tests/test_resolve_intake.py
- FIX 60 (R-B03-B3): presentation-canonical-entry.sh
- FIX 1-bundleDir (R-H01 PRIOR-B1, landed via F-wave): build_deck.py:11066 (bundle_dir param) + :11144 (manifest bundleDir write)
- Doc/bak-path diffs (B03-B5, B07-B1/B3, F01-B2, F02-B1/B3/B4/B5, F03-B1/B3/B5): bak-path hunks excluded; live-path fix text verified

## 4. Files changed (90 vs pre-merge snapshot HEAD)
- `23-ai-workforce-blueprint/scripts/presentations-drift-gates.sh`
- `23-ai-workforce-blueprint/templates/role-library/presentations/00-START-HERE.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/DEPARTMENT-COUNTS-CANONICAL.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/attention-content-strategist.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/brand-steward.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/capacity-reliability-engineer.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/deep-research-specialist-presentations.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/delivery-concierge.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/devils-advocate-presentations.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/director-of-presentations.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/healer-presentations.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/hook-strategist.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/media-librarian-ghl-updater.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/offer-price-strategist.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/pptx-assembly-specialist.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/presenter-coach.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/presenters-guide-specialist.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/presenters-speech-writer.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/qc-specialist-prompt-presentations.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/qc-specialist-signature-presentations.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/representation-casting-director.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/retired-doctrine-patterns.json`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/CANONICAL-RENDERER-PIN.sha256`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/_skill48_ghl_media.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_webinar_video.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/doctrine_residual_check.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/ghl_media_upload.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-canonical-entry.sh`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-deps.json`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-watchdog.plist.template`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-watchdog.sh`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/__main__.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/capacity.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/checkpoint.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/credit_preflight.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/deliverables.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/dispatcher.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/execution_plan.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/launcher.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/manifest.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/model_catalog.json`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/model_router.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/ocr_verify.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/phases.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/research_web.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/scanners.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/workingset.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentations-drift-gates.sh`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/process_reaper.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/run_signature_deck.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/self_audit.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/speech_build_harness.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/synthesize_full_speech.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_client_step_count.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_dispatcher_autospawn.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_fix36_doc_code_reconcile.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_scanners_negation.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_wave_contract_three_seams.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/vsl_builder.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/webinar_timing.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/signature-presentation-architect.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/slide-copywriter.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/slide-image-creator.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/slide-submitter.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/sops/SOP-DESIGN-01-CREATIVE-TYPOGRAPHY-GUIDE.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/sops/SOP-DESIGN-02-PURE-TYPOGRAPHY-HOOK-SLIDES.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/sops/SOP-SLIDE-01-ONE-BIG-IDEA-PER-SLIDE.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/sops/SOP-SLIDE-02-AUDIENCE-FACING-ONLY.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/sops/SOP-SLIDE-03-HOOK-DOCTRINE.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/sops/SOP-SLIDE-04-DECK-DENSITY-AND-PACING.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/sops/brand-steward-sops.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/sops/slide-image-creator-sops.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/sops/typography-architect-sops.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/test_retired_roles.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/typography-architect.md`
- `51-signature-presentation/scripts/sacred-structure-hashes.json`
- `install.sh`
- `universal-sops/_content-manifest.json`
- `universal-sops/presentation-slide-craft/MANIFEST-SOURCE.txt`
- `universal-sops/presentation-slide-craft/MASTER-QC-AUTOFAIL-RULESET.md`
- `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json`
- `universal-sops/presentation-slide-craft/SOP-SLIDE-01-ONE-BIG-IDEA-PER-SLIDE.md`
- `universal-sops/presentation-slide-craft/SOP-SLIDE-02-AUDIENCE-FACING-ONLY.md`
- `universal-sops/presentation-slide-craft/SOP-SLIDE-03-HOOK-DOCTRINE.md`
- `universal-sops/presentation-slide-craft/SOP-SLIDE-04-DECK-DENSITY-AND-PACING.md`
- `universal-sops/presentation-slide-craft/SOP-SLIDE-05-PROCESS-MANIFEST.md`
- `universal-sops/presentation-slide-craft/WORKERS-TUNING-EXAMPLE.md`
- `working/checkpoints/read_slice_truncations.json`


## 5. Syntax gates (pre-test)

- python3 py_compile: all merged .py pass (build_deck.py, __main__.py, phases.py, dispatcher.py, model_router.py, phase_verifiers.py + 22 others)
- bash -n: presentation-canonical-entry.sh, presentations-drift-gates.sh (x2) pass
- JSON parse: PIPELINE-MANIFEST.json, model_catalog.json, presentation-deps.json, _content-manifest.json, sacred-structure-hashes.json, read_slice_truncations.json pass
- Conflict markers: 0 in live tree (grep ^<<<<<<< HEAD = 0 repo-wide, .bak excluded)
- Unmerged index entries: 0

## 6. Test summary

Command: `python3 -m pytest 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests -q`
Result: **91 failed, 1559 passed, 2 skipped** in 948.57s (15:48). Full suite: 1652 tests collected.

Prior baseline (pre-merge snapshot HEAD a29a4cbc2, same box, same day): 91 failed / 1559 passed / 2 skipped in 976.80s — **identical counts**. The merge neither regressed nor repaired the suite; failures are pre-existing wave state, not merge damage.

Failure clusters (naming the fix per brief step 5; NOT fixed by merge writer beyond conflict resolution):

| Fix | Failures | Note |
|---|---|---|
| FIX 103 (deck-size floors) | 8 | test_fix103_deck_size_floors.py — floor-literal scanners |
| FIX 36 (doc/code reconcile + intake-depth + registry parity + phase count + GHL folder) | 37 | test_fix36_* family |
| FIX 92 (closeout gates) | 9 | test_fix92_closeout_gates.py — image-grounding/casting verdict gates |
| FIX 112 (missing producers) | 3 | style-preview spec fanout |
| FIX 17 (verifier import fail-closed) | 5 | |
| FIX 28 (design producer) | 5 | |
| FIX 37 (poller counter) | 1 | |
| FIX 14/18 (agent env / tool schema preflight) | 2 | |
| engine_client_report phase counts | 15 | 36-phase canonical count assertions |
| zz_cand27_regentry.py | 16 | candidate/scratch module |
| Other singles (supervisor, sweep, qc_aggregate, poll_cap, persona_governance, heal, manifest_assert, role_workspace_symlinks, …) | 48 | scattered |

Per brief step 5 these go to the council with their fix numbers; no code "fixing" beyond conflict resolution was done by the merge writer.

## 7. Not applied — excluded by brief

- R-G01..G03 (14 diffs): round-4 repair wave, own train per brief ("Wave-1 work is ALREADY COMMITTED on the base branch; apply only the resume diffs" — G-wave = separate council track R-B/R-G)
- R-B05-B1.mychanges.diff, R-B06-B3.runfacts.diff, R-F01-B2.{main,reaper,tests,watchdog}.diff: companion-part diffs, folded into their parent fix's replay
- council.json (untracked, from council agents): left untracked, not committed

## 8. Disposition

Branch integrate-resume-20260902-onboarding committed locally. NOT pushed, NOT merged to main — council judges first per brief.
