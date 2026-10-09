# Changelog - drama-song-ad-factory (Skill 75)

All notable changes to this skill are documented here. The version of
record is `skill-version.txt` (kept in agreement with the `SKILL.md`
frontmatter `version:` field).

---

## Unreleased - FU-U6: Suno request limits, fail closed, measured last

- U15i (docs in lockstep with the template system; last unit of the U15 set): `SKILL.md` gains the "Prompt templates" section (data under `references/prompt-templates/`, the assembler `scripts/core/prompt_templates/`, the H3 band 5,000-6,800 with hard max 7,000, the prompt receipt, `PROMPT_NOT_TEMPLATED`, the `prompt_compliance` gate) and the Suno recipe and lip-sync bullets now point at it. `references/choice-card-spec.md` 3.1 names `references/prompt-templates/length-classes.json` as the ONE length table (its list equals the table's keys) and 3.3 points at `looks/` and `modes/`. `references/style-bibles/realism-cinematic.md` keeps the recipe as the source of the `realism` mode, moves the Chanel identity into a "worked example" heading, deletes the nine "(Restated for emphasis.)" duplicate blocks, and states the camera as per shot. `QC.md` carries the bands, the receipt, `PROMPT_NOT_TEMPLATED` and the required `prompt_compliance` record. ONB SOP `DS-5`/`DS-6` point at the same files. New doc test `prompt_templates/test_docs_u15i.py` (fails on the base tree: no "Prompt templates" section, the restated duplicates still present, the card's 3.3 with no `looks/`).


- U15h (length classes, product seconds and lanes in ONE table; prompt compliance at final QC): `references/prompt-templates/length-classes.json` is CORRECTED so every row equals the code (`length_formula.plan`, `lipsync_clips.budget`, `shot_planner.plan_generation_count` = ceil(D/4), lanes via `lane_planner` when the module is on the tree, the 10-15% product band). The U15a port had drifted at 180/300/600 s (spoken share 16.9/10.1/5.0% before U15d's CTA scale landed; rows now 22.5%) and at 600 s the song plan is `1 base + 3 extends`. `prompt_templates.length_class(L)` is the one reader: it computes the row and raises `PROMPT_LENGTH_CLASS_DRIFT` naming each drifted field, so a stale table can never be read silently. `length_formula.class_check`, `lipsync_clips.class_check` and `shot_planner.class_check` cross-check their own module against the table (never a second formula). `qc_gate` requires a `prompt_compliance` record at final QC: `prompt_compliance_rows`/`prompt_compliance_record` build one row per paid ledger job matched to its receipt (logical_key+attempt_id, else request_digest, else prompt_sha256; REFUSE/TRIM receipts never count), and `evaluate(..., ledger_jobs=[...])` requires the check. `check_product_seconds` proves the shot plan's product seconds fall inside 10-15% of D. New `prompt_templates/test_length_classes_u15h.py`.

- U15b (H3 assembler, band of record 5,000-6,800): `prompt_templates.assemble_h3/check/expand/receipt` build every MiniMax H3 prompt from the template layers plus the shot spec's facts, guard the owner band (under 5,000 = FLAG then `H3_THIN_SPEC`, never padding; over 6,800 = TRIM; over 7,000 = REFUSE `H3_OVER_HARD_MAX`), and write a prompt receipt (sha256 + template version + section char map). The six golden specs assemble to 5,578-6,740. `shot_planner.prompt_spec_for` writes the facts (`shot["prompt_spec"]`); `kie_dispatch` refuses `PROMPT_NOT_TEMPLATED` when the prompt's sha256 has no receipt or the receipt says REFUSE/TRIM, and re-measures the final payload cap just before spend. The video prompt path carries no square-bracket markers and no generic `[MOTION]` line (`bible.compile_visual_prompt(video=True)`, the three style bibles' `compile_prompt(video=True)`); `assert_compiled` accepts a matching receipt. New `shot-types/villain.json` carries the U16 villain guidance into the assembler. `music_styles` soul-ballad base text ends with a period.

- New `scripts/core/prompt_limits.py`: one limit table read from the catalogs (`68-kie-audio/models.json` suno-generate: lyrics 5000, style 1000, title 80, duration 10-360; `67-kie-video/models.json` vendor caps per model), plus a skill-75 override table for what the catalogs lack (`negativeTags` 1000 and `kling/ai-avatar-standard` 2500, both stamped UNVERIFIED with source URL and the free docs re-read step). `check_request(model, request)` measures EVERY text field of the FINAL payload and refuses over-cap with `PROMPT_OVER_CAP: field, chars, cap, source, status`; it never truncates.
- `music_director.build_generate_request` now measures the payload AFTER `ending_qc.with_clean_ending` appends the ending to the style (the E.2 order-of-mutation hole: a 1000-char style passed the old guard, the ending pushed it to 1054, and the final style was never re-measured).
- `suno_recipe.build_request` measures its payload too; `song_dispatch.run_takes` compares the request duration with the G9 headroom (`words_fit.max_suno_duration(plan)`) as the plan default allows, while a patch/short duration is still refused.
- Gate registered in `shared-utils/kie_prompt_gates.json`; the shared enforcer is called ceiling-only through the module (the 80 percent floor must not apply: the 67 house floor of 5000 sits above Kling's 2500 hard cap).
- New test `music_director/test_prompt_limits_u6.py` (fails on the base tree: no `prompt_limits` module, 5001-char lyrics, a 1054-char final style and an 81-char title all built).

## v2.9.1 - 2026-10-09 - Batch MGB008: W-G-007-amend, W-G-002-amend

- Delivery checklist consumes the amended receipt fields (W-G-007-amend); kept-take tags merged with the calibrated verdict gate.
- Delivery-named tag grammar in lyric_structure (W-G-002-amend).

## v2.9.0 - 2026-10-08 - Batch MGB007: LSC001: one consolidated lip-sync change (LPG001 + LSL001 + LSR001)

No version bump. Replaces onboarding #1697, #1698, #1699 (999-setup #72, #73, #86), which overlapped and partly contradicted each other.
- **Sync gate = `sync_check` (LSL001, calibrated on real controls).** `lip_gate.judge` maps SYNCED / WEAK / NOT_SYNCED to PASS / ACCEPT_WITH_FLAG / FAIL, a sung line that is WEAK or NOT_SYNCED to UNDETERMINED (held for a person, no paid redo), UNMEASURABLE never a pass. LSR001's `event_sync` moved to `lip_gate/event_sync.py` as an ADVISORY measure: recorded in the row as `advisory_event_sync`, never gating (its thresholds were synthetic-only; `calibrate_events.py` prints its real-control table, see the PR body).
- **Picture gate = `picture_gate` (LPG001, calibrated, enforced in the dispatcher).** `image_gate.check_image` no longer has close-up thresholds of its own: `picture_gate.check_numbers` judges face count, face height, roll, yaw, jawOpen, smile, teeth and sharpness; `image_gate` adds only size (720x1280, 9:16), occlusion, mouth shadow, light, background, same character and provenance. ONE rule set.
- **LSR001 non-gate improvements kept:** `lipsync_clips.choose_window`, `MAX_TRIES = 2`, `count_jobs`, `check_try_limit`, cost default `attempts=2`; `lip_gate.kling_prompt` ("sings" / "says"); the padded cut (0.30 s lead-in, 0.20 s tail) is the default input of try 1; try 2 only on a hard defect and only with a changed input (`retry_input`); `KEPT_BEST_OF_2` receipt rows with flag and mouth-strip path; `qc_check` accepts them and rejects more than 2 jobs; every paid submit through `load_governor.kie_request`; QC.md H4, QC checklist items 8 and 11 (keep-best carve-out), `delivery_checklist` Q8 aligned to the sync_check verdicts.
- **InfiniTalk:** the A/B third job is removed from the code. Every doc mention now says manual backup only, not on by default. `kling/ai-avatar-standard` is THE lip-sync model.
- Tests: `test_lip_gate_h2.py`, `test_image_gate.py`, `test_delivery_checklist.py`, `test_lipsync_closeup.py` updated; `test_event_sync.py` (advisory), `test_choose_window.py`, `test_lipsync_clips.py`, `test_sync_check.py`, `test_picture_gate_lpg001.py` kept.

## v2.9.0 (included) - LPG001 / LPG002 / LPG003 - lip-sync picture gate enforced in the dispatcher

Owner order (Trevor, 2026-10-08). No version bump. Two close-ups (30-Day Reset: face 28%, smile 0.62; Perfect Daughter: face 34%, teeth, roll -7.8) were never measured before paid Kling lip-sync.
- `lip_gate/picture_gate.py` + `picture_measure.py`: real mediapipe measurement, sha256 receipt (`<dir>/.lipgate/<sha256>.json`), one free crop, at most 2 paid regenerations through `kie_dispatch` (ledger cap, `load_governor.kie_request`), upload bound to the measured bytes. Same files, constants block and test as the 999-setup copy.
- LPG003 loosened the rules (Trevor: "loosen the checks so it's not as strict"): PASS / ACCEPT_WITH_FLAG / FAIL. FAIL only for face count not 1, face under 20%, |roll| over 20, |yaw| over 0.25, jawOpen over 0.30, sharpness under 60. Smile, teeth, small face, mild tilt are flags, never a paid regeneration. Calibrated so every Trevor-approved Kiesett version 2 and LeAnne Dolce picture passes or flags.
- LPG003 F14: `kling/ai-avatar-standard` (the locked lip-sync model) no longer hits `MODEL_NOT_ON_MENU`; it passes the F14 video lock and goes to the picture gate.
- `kie_dispatch.dispatch` hard-blocks lip-sync models without a PASS or ACCEPT_WITH_FLAG receipt (`LIPSYNC_PICTURE_NOT_GATED`).
- `lip_gate/install_face_model.py` + PREREQS entries + INSTALL step 2b: mediapipe and Google's `face_landmarker.task` (pinned sha256) ship with the skill; a missing/corrupt model refuses and names the install command.
- Test: `lip_gate/test_picture_gate_lpg001.py`.

## v2.8.5 - 2026-10-08 - G4-WIRE: target engine on Trevor's 5/10 band, wired into music_director + retake_manager

G4's engine was on main but (a) its accept line was the single 5-point grace with a
keep-the-closest-with-a-warning endgame, which G11 (Trevor order 12:30, consolidated order
1240 item 3) replaces, and (b) nothing called it. Skill bump v2.8.4 to v2.8.5.

- `core/target_engine`: `score()` now returns `worst_pts` and a `band`
  (ACCEPT / FLAG / REDO) judged by `spoken_share.judge_gap` -- one constants module, no
  second band. `steer()`: within 5 points = ACCEPT; past 5 up to 10 = ACCEPT_WITH_FLAG with
  the flag written into the receipt; after the bounded rounds past 10 = REDO with the closest
  take's measurements attached (REPLACES keep-the-closest-with-a-warning; the engine still
  never raises and never cancels -- REDO means regenerate). New exports: `VERDICT_FLAG`,
  `VERDICT_REDO`, `ACCEPT_PTS`, `FLAG_PTS`, `BAND_*`, `band_for_gap()`.
- Call path (order 1150 names music_director + retake_manager): `music_director.select_best`
  takes optional `target_metrics`/`targets` and judges the winning take through the engine
  (receipt block `target`: verdict / band / worst_pts / flags). `retake_manager.plan` takes
  optional `target_gap_pts` and rejects an in-band retake with `TARGET_IN_BAND` (within 5
  accept, 5-10 flag, past 10 the retake proceeds).
- Tests: `test_target_engine.py` proves accept/flag/redo at 5 / 6 / 10 / 14 points (both
  boundaries), all-spoken reject-and-regenerate to REDO, closest-of-N, single-source band
  constants, and both call paths; suite green with `HOME=$(mktemp -d)`.

## v2.8.4 - 2026-10-08 - Batch MGB005: song recipe v2, load governor, G5, G9, H10, G2, H3-TEST

One batch release of nine units. #1653 CIO002 run each check once per commit (push main-only, per-PR concurrency, 93 fast guards folded); #1678 G5 honest receipts (measured sung/spoken/rap/no-voice, target, gap, every take); #1681 song recipe v2, song length formula and song dispatcher; #1684 G9 words-fit preflight before spend and Suno duration with 15% headroom; #1685 H10 each line's voice must fit the character on screen; #1687 H3-TEST fps policy (30 fps master, Kling pass-through, per-segment duplicate gate); #1688 KIE rate limit reference; #1689 G2 the builder enforces the lint it ships; #1690 load governor (machine-wide heavy-job gate, bounded ffmpeg, stage cleanup, KIE pacing). Integration: the song dispatcher sends every generation through the load governor (new requests use the 20 per 10 s bucket, a 429 is resubmitted).

## v2.8.3 - 2026-10-08 - Batch MGB004: F3, G8, G1, F16, W4-PROOF, doubled lip-sync, user model choice, orchestrate-only

One batch release of eight units (#1674 F3 lipsync_cuts, #1675 G8 audio shares, #1676 user model choice, #1677 orchestrate-only and no silent failure, #1679 F16 video model gate, #1680 W4-PROOF, #1682 G1 delivery map, #1683 doubled lip-sync and image gate). Entries below are each unit's own notes. Skill 75 is now v2.8.3.

### Doubled lip-sync and the lip-sync image gate (#1683)

Owner order (Trevor, 2026-10-08). No version bump in this unit.

- **Doubled lip-sync, more pieces not longer ones.** A 60 s ad carries 6-8 clips of 4-6 s
  (30-40 s in all, was 15-20 s), scaled linearly with ad length, no clip over 6 s. One source:
  new `core/lipsync_clips.py` (the operator's length-formula module is not on main; swap
  `scale()` when it lands). `shot_planner/face_speaks.py` (band, planner: every sung hook, the
  spoken opener and closing first, each cut to 6 s) and `final_assembler/lipsync_coverage.py`
  (E6 floor: 50% of runtime, 6 clips per 60 s) follow it; the old 15-20 s plan now FAILS.
- **Spend.** `lipsync_clips.check_budget` refuses loudly past the cap, unknown price or unknown
  cap; the price card refuses a clip over 6 s (`LIPSYNC_CLIP_OVER_CAP`); price-menu snapshot and
  every doc that held 15-20 s updated.
- **Lip-sync image gate** `lip_sync/lip_gate/image_gate.py`: runs on every source picture before
  any paid job (`run_gate` now requires `source_image` and `image_check`); measurable checks
  (size, 9:16, face-box share 30-45%, frontal pose, mouth open ratio, occlusion, light, shadow,
  background, same character, sharpness, provenance); unmeasured = refused. Prompt template
  `closeup_prompt()` makes the picture this way.
- Tests: `test_lipsync_clips.py`, `lip_gate/test_image_gate.py`, `extensions/test_lipsync_cap.py`;
  H2, H4, E6 tests updated to the doubled numbers.

## v2.8.2 - 2026-10-08 - G3b: sung detector v2

The sung detector no longer reads gap-free speech as sung (unit #1666). Skill bump v2.8.1 to v2.8.2.

## v2.8.1 - 2026-10-08 - Batch MGB002: LPC001, BND001, W-G-003 (G3), SPK001

One combined release of four units (#1654, #1655, #1656, #1659), one skill bump from v2.8.0 to v2.8.1. Each unit's own entry follows.

### Lip-sync close-up in every reference set (LPC001)

Same change as 999-setup drama-song-ad-factory 2.7.13. Owner order (Trevor, 2026-10-08): every
character gets a close-up where the lips can clearly be seen, because the lip-sync step works
best from it.

- `catalog_calculator.image_plan`: reference set is 7 per character (3 angles, 3 expressions,
  1 `lipsync-closeup`); image count and cost estimate include it.
- `lip_gate.run_gate(source_image=)`: Kling avatar attempts and the InfiniTalk A/B use the
  close-up as source image by default. `lip_gate.check_reference_set`: a set with no close-up,
  or one whose mouth is not clear, fails.
- SKILL.md rule; test `lip_sync/lip_gate/test_lipsync_closeup.py` (mocked, $0);
  `catalog_calculator/test_image_plan_i3.py` updated.

### SPK001: spoken share cut to 20-25%, singing judged against voice time (builds on BND001 / #1655)

Trevor, 2026-10-08: "Okay, let's go to your recommendation that cut it to about 20-25%." Why: Suno turns spoken lyric lines into long talking, and the old targets did not add up (spoken 35-40% of runtime plus a music-only intro and end card left at most about 50% for singing, never the 55-60% goal). Six chapter songs came back 15-30% sung.

- `core/spoken_share` (the one G10 constants set): `SPOKEN_TARGET_PCT` 45 -> 22.5 (band 20-25); redo edges `SPOKEN_MIN_PCT` / `SPOKEN_MAX_PCT` 12.5 / 32.5 (target -/+ 10, reporting only, no absolute floor); `SUNG_TARGET_PCT` = 77.5 (75-80), now a share of VOICE time, sung / (sung + spoken): a music-only intro, gaps and the end card never count against it. New `sung_of_voice_pct`, `check_sung_of_voice`, `LYRIC_SPOKEN_WORD_PCT` = (15, 18), `spoken_word_budget`, `check_spoken_word_budget`; `check_plan` also judges sung-of-voice.
- `final_assembler/sung_vocal_guard`: sung coverage is sung / (sung + spoken) from the 12.4 timing map (`spoken_section_ids` names the spoken sections); default target 77.5. Only other hard reject stays: no sung stretch of 6 s.
- `lyric_writer.spoken_word_budget`: spoken lines budgeted at about 15-18% of the lyric words. `suno_recipe.score_take` judges sung-of-voice and passes the spoken-share flag through. `music_styles`, the `spoken_share_card_docs` card line and docs wording, the `intake_book` spoken-share menu range, `target_engine` notes, SKILL.md, the choice-card spec and the QC checklist carry the new numbers.
- Trevor's band on both numbers: within 5 accept, 5 to 10 accept with a flag, over 10 redo. Hard reject only: no sung stretch of 6 s.
- Tests: spoken 22% accept / 31% flag / 37% redo; sung of voice 76% accept / 69% flag / 60% redo; a 10 s intro plus 5 s end card is not penalized. Same rule in 999-setup drama-song-ad-factory 2.7.17.


### BND001: sung share judged only by Trevor's band; H6 first real singing 15% (supersedes #1637)

Trevor, 2026-10-08: "It's not an absolute 55% or 20% ... within about 5 percentage points" and "We always want to try to be within 5% of the goal. Once you get past 5%, 5% to 7% gets a flag. Once you get past 10%, it's got to be redone." Batch #1652 had kept a hard 55% sung floor (E7-AMEND); that contradicted him.

- `final_assembler/sung_vocal_guard`: `MIN_SUNG_COVERAGE` (the 55% hard floor) and the `min_coverage` / `goal` arguments are removed. Sung share is judged ONLY against the ad's own sung target (`target=`, or `sung_target` / `sung_target_pct` on the choice card, default `spoken_share.SUNG_TARGET_PCT`): within 5 points accept, over 5 up to 10 accept with a flag, over 10 redo (`SUNG_COVERAGE_LOW`). The only other hard reject stays H8's: no sung stretch of 6 s (`VOCAL_MISSING`).
- `core/spoken_share`: one G10 constants block holds the target and band numbers (`ACCEPT_PTS`, `FLAG_PTS`, `FIRST_SUNG_TARGET_PCT`, `SUNG_TARGET_PCT`, `NO_REAL_SINGING_STRETCH_S`).
- H6 (#1637) merged with H8: `check_first_sung` measures the first real singing (first sung stretch of 6 s or more) as a share of runtime against the 15% target with the same band (accept 10-20%); `FIRST_SUNG_WITHIN_SECONDS` is retired. Adds `steer_first_sung`, `segments_from_sung_stretches`, `lyric_writer.steer_opening`, and the card and docs wording.
- Tests: 50 vs target 60 flag, 48 vs 60 redo, 57 vs 60 accept, no floor, no 6 s sung stretch redo, first sung 18% accept / 22% flag / 27% redo.

### W-G-003 (G3) calibrated sung detector

- Added `scripts/core/singing_detector/` (detector, `__init__`, self-test): measures sung seconds per second and per line from the isolated vocal stem (pitch stability, voicing continuity, note alignment; ffmpeg + numpy, no ASR, no spend, Part D load guard). Every share it returns carries `source: measured` and is never computed from section labels. Calibrated against the reference fixtures (bsw sung lines, O3 spoken lines). Test: `scripts/core/singing_detector/test_singing_detector.py`.

## v2.8.0 - 2026-10-08 - Batch MGB001: Part H (H1-H5, H8, H9, H7, H11-H14), Part I (I1-I8), G4/G6/G12, E7-AMEND

One combined release of every unit below (each unit's own entry follows, unchanged except one heading level deeper). The H6 unit (#1637) is held out of this batch: it conflicts with H8 (#1635) in `spoken_share` and ships separately.

<!-- #1627 -->
### #1627: v2.6.1 - 2026-10-08 - H14 song files in every delivery

- Added `delivery_variants/song_files.py`: builds the full mastered mix as MP3 320 kbps + WAV named after the ad (plus the instrumental pair when one exists), lists them in `delivery-receipt.json` and `README.md`, and `check_song_files` fails a delivery missing any of them. New `song_files` QC check in `qc_gate` and `qc-schema.json`. Test: `scripts/core/delivery_variants/test_song_files_h14.py`.

<!-- #1628 -->
### #1628: [v2.6.1] - 2026-10-08 - Part H H11: delivery checklist Q8-Q11

The final QC gate 4 delivery checklist (G7, check `delivery_checklist`) grows
from 7 to 11 measured questions: Q8 lip-sync measured (offset <= 0.05 s,
correlation >= 0.55 and >= 0.25 above the wrong-audio control, no frozen face
> 0.75 s), Q9 first-sung % of runtime (goal 15%), Q10 pictures match words
(shot / Suno time / line / match, no slow-motion above 1.15x), Q11 every
numeric goal judged by Trevor's band (within 5 accept; over 5 to 10 accept
WITH a flag shown in the receipt; over 10 REDO, never keep the closest). Q2
uses the same band. No new gate or framework.

<!-- #1629 -->
### #1629: [v2.6.2] - 2026-10-08 - Part H H2 measured lip-sync gate

- New `scripts/core/lip_sync/lip_gate/`: every lip-sync clip is measured
  against the FINAL MIX envelope. PASS needs |offset| <= 0.05 s, correlation
  >= 0.55 AND >= 0.25 above a wrong-audio control, no frozen face > 0.75 s.
  Below it: regenerate once with better input (single clean line, front-facing
  tight crop, still image), then InfiniTalk only through a one-time single-line
  A/B that keeps whichever measures better; still failing = `FAIL_REPLACE`.
  Numbers ride the receipt row; `qc_check` fails a missing or failed row.
- Test: `lip_sync/lip_gate/test_lip_gate_h2.py` (shifted clip fails, good clip
  passes, A/B once per run). Assembler/Q8 wiring is H11's.

<!-- #1630 -->
### #1630: [v2.6.1] - 2026-10-08 - Part H H13: cross-fades vs words

`first_word_s` per segment shrinks the fade into a lip-sync clip to end >= 0.1 s before its first word; gates FADE_COVERS_FIRST_WORD and LONG_GAP_CUTAWAY (inner gap > 0.5 s must be held on one lip-sync clip). Test `scripts/core/final_assembler/test_fade_words_h13.py`.

<!-- #1631 -->
### #1631: [v2.6.1] - 2026-10-08 - Part H H12: no hand-written pipeline scripts

- New `scripts/core/final_assembler/master_provenance.py`: the assembler receipt
  now carries `produced_by` (module `final_assembler.assembler`) and
  `master_sha256`; `check_master_provenance(run_dir, master)` FAILS a run whose
  master has no matching skill receipt, or whose run folder holds a script that
  calls ffmpeg or writes captions itself (the Kiesett `edit/final.py` case).
  `master_provenance_qc_record` emits the `final_edit` record for `qc_gate`.
- Test: `scripts/core/final_assembler/test_master_provenance_h12.py`.

<!-- #1632 -->
### #1632: [v2.6.1] - 2026-10-08 - Part H H1 lip-sync stem offset

- New `scripts/core/lip_sync/stem_offset/`: `measure_offset` (envelope
  cross-correlation, offset > 0 = the vocal stem runs LATE vs the full mix;
  Kiesett measured +0.066 s) and `cut_plan` (cut the stem at mix word start +
  offset minus lead-in; place the clip at the line's real Suno start minus
  the lead-in, never re-timed).
- `final_assembler.validate_lipsync_placement` (gate `LIPSYNC_RETIMED`): a
  lip-sync segment carrying `lip_lead_s` must sit within one frame of its
  line start minus that lead. Runs in `assemble()` after the E5 atomic gate.
- Tests: `lip_sync/stem_offset/test_stem_offset_h1.py`,
  `final_assembler/test_lipsync_placement_h1.py`.

<!-- #1633 -->
### #1633: [v2.6.1] - 2026-10-08 - Part H H5: pictures match the words

- New `scripts/core/shot_planner/timestamp_plan.py`: `plan_from_timestamps` (shots from REAL Suno timestamps; planned timings refused), `match_table` / `pictures_match_gate` (shot / time / line / match, `PICTURE_LINE_MISMATCH`), `check_stretch` (no slow motion above 1.15x, `SLOWMO_OVER_LIMIT`).
- Assembler `h5_gates`: blocks both before any render; the receipt carries the stretch rows and the match table.
- INSTRUCTIONS.md: stage order is audio, timestamps, shot plan, pictures.
- Test: `python3 scripts/core/shot_planner/test_timestamp_plan_h5.py`.

<!-- #1634 -->
### #1634: [v2.6.1] - 2026-10-08 - H9 readable intake card

- New `scripts/core/choice_card/intake_card/`: builds the six intake questions
  (length, music style, video style, video model, spend limit, storyboard
  approval) as one block per question, one numbered option per line,
  RECOMMENDED marked, blank line between questions, a closing "how to answer"
  line. Plain text so no sender strips line breaks; split between questions
  under Telegram's limit; exact `openclaw message send` argv and Bot API body.
- `factory.py card` prints the raw card (Claude Code chat) or send payloads.
- Intake and book `question_message` now use the same layout (they were a
  single `"\n".join`, no blank lines).
- Test: `choice_card/intake_card/test_intake_card_h9.py`.

<!-- #1635 -->
### #1635: [v2.6.1] - 2026-10-08 - H8: one singing rule, one tolerance band

- The only hard reject when singing was chosen is "no real singing" (no
  6-second sung stretch). Constant `NO_REAL_SINGING_STRETCH_S` lives in
  `scripts/core/spoken_share/spoken_share.py` (the Part G constants module)
  and is read by the plan check, the sung-vocal guard and the lip-sync check.
- Every share, first-sung, length and lip-sync-seconds goal uses Trevor's
  band (`ACCEPT_PTS=5`, `FLAG_PTS=10`): within 5 accept, over 5 up to 10
  accept WITH A FLAG in the receipt, over 10 REDO (never keep the closest).
  `check_share`, `check_first_sung`, `check_plan`, `sung_vocal_guard` and
  `lipsync_coverage` return `flags` for the receipt.
- Flagged outputs: share verdict `FLAG` (accepted); a flagged lip-sync or
  sung-coverage result passes and carries the flag text.

<!-- #1636 -->
### #1636: [v2.6.3] - 2026-10-08 - Part H H4 every speaking face is a lip-sync clip + coverage target

- New `scripts/core/shot_planner/face_speaks.py`: `check_face_speaks` lists
  every shot where a face is visibly speaking (shot / time / line / lip-sync)
  and fails `FACE_SPEAKS_NO_LIPSYNC` for any that is not a lip-sync clip of
  that character's own line (`LIPSYNC_WRONG_FACE` for a lip-sync clip whose
  speaker is not on screen). Back of head, hands, another character or an
  off-screen narrator are the allowed alternatives.
- `plan_lipsync_lines` picks enough own-face lines to reach the lip-sync
  target (15-20 s in a 60-90 s ad, scaled by runtime, with the 5-point
  grace); `check_coverage_band` is the QC measurement
  (`LIPSYNC_COVERAGE_BELOW_BAND`). Part E E6 floors are unchanged.
- Assembler: `face_speaks_gate` runs when timeline `lines` carry `speaker`;
  segments then declare `faces_on_screen` (and `speaking_faces`), a missing
  declaration fails closed `FACE_DATA_MISSING`.
- Test: `shot_planner/test_face_speaks_h4.py` (Kiesett S01/S02/S08 flagged,
  planner reaches the target, band measured, assembler gate).

<!-- #1638 -->
### #1638: [v2.6.4] - 2026-10-08 - Part H H7: captions use the approved words + protected names

Kiesett's Stop Stale ad captioned "the house went still" for "Stale": the lyric
sheet itself said "still" (136 Suno requests), Suno sang it, the caption copied
the sheet. Fixed at the source.

### Added
- `scripts/core/protected_names.py` (+ `test_protected_names_h7.py`): sheet BUILD
  gate, sung-take words check, sheet-text captions timed from Suno timestamps,
  caption QC. Codes `PROTECTED_NAME_CHANGED`, `PACKET_LINE_REWRITTEN`,
  `PROTECTED_NAME_SUNG_WRONG`, `CAPTION_MISMATCH`, `CAPTION_SOURCE_NOT_SHEET`.

### Changed
- `lyric_writer.validate_lyrics`: brief `packet_lines` + protected names reject a changed name or rewritten packet line.
- `music_director.build_generate_request(..., protected=)`: no Suno request from a bad sheet.
- `music_qc.check_song_qc(..., protected=)`: a take that sang a protected name wrong FAILS.
- `delivery_variants.checks.check_captions(..., protected=, text_source=)`: speech-to-text source or any mismatch FAILS.
- `QC.md` / `SKILL.md`: H7 gate row and rule.

<!-- #1642 -->
### #1642: [v2.6.1] - 2026-10-08 - G12 Suno song recipe is the default for every Suno style

- New `scripts/core/suno_recipe/` (module + tests): one gate every Suno
  style goes through. Style text carries the sung/spoken map, the lyric sheet
  needs a repeated sung hook built from the client's own words, singing starts
  early (15% of runtime target, 5/10 band), and a take is judged only from
  measured segments, never labels.
- `music_director.build_generate_request` takes `style_id` and `client_text`
  and refuses a raw Suno style prompt that skipped the recipe.
- Only the Velvet Voiceover id (`velvet_voiceover`) is exempt.
- `SKILL.md` and `references/choice-card-spec.md` gain the "Suno song recipe" section.

<!-- #1643 -->
### #1643: [2.6.1] - 2026-10-08 - Part I I5: clean endings, never "drops off a cliff"

- New `scripts/core/ending_qc/`: `with_clean_ending` adds an `[Outro]` section, a final
  `[Resolve on final chord]` tag and "natural resolved ending" style words to every sung
  song request (`music_director.build_generate_request`); `check_ending` measures the last
  2 s of the master (audio level must decay, last word not cut, picture fades to the end
  card, end card 4-5 s and finished by target length minus 2 s).
- Done-when test: `python3 scripts/core/ending_qc/test_ending_qc.py` (abrupt cut fails,
  resolved ending passes).

<!-- #1644 -->
### #1644: [2.6.1] - 2026-10-08 - Part I I2 scenes must match the song and the faces

- New `scripts/core/scene_match/`: each shot carries line, meaning, place and action, and face
  emotion at storyboard time (`check_cards`); after clips exist, sampled frames are checked
  against them (`qc_scene_match`). A scene that is off-topic, or a smiling face under a pain
  line, fails, and only the failing shots are regenerated. A shot with no sampled frames never
  passes unseen. Test: `python3 scripts/core/scene_match/test_scene_match_i2.py`.
- Includes `scripts/core/face_emotion/` (Part G G6) which it builds on.
- `SKILL.md` gains the "Scenes must match the song and the faces" section.

<!-- #1645 -->
### #1645: [v2.6.2] - 2026-10-08 - Part I I6 character library

- New `scripts/core/character_library/`: after a character is approved, one question ("Do you want to save <character> to your character library so you can reuse them in future ads?"), then a name; saves reference images, description and voice notes under the client's own data folder; later cards list "Use a saved character?".
- `factory.py character` subcommand (ask, save, list, use, card); `card --client-dir` adds the saved-character question where the H9 intake card exists.
- Test: `scripts/core/character_library/test_character_library_i6.py` (save + reuse round trip).

<!-- #1646 -->
### #1646: [v2.6.1] - 2026-10-08 - I3 storyboard pictures

- Per main character the planner now lists a reference set (front, three-quarter,
  side, plus neutral, sad-tired and happy-relieved faces) and one keyframe picture
  per shot per shape, all before any video. Same image model as before.
- The cost estimate counts these pictures (Skill 74 price, no local rates) and the
  choice card shows an Images line with the added reference-picture cost.
- Up to 6 main characters; none or more fails closed. Test:
  `catalog_calculator/test_image_plan_i3.py`.

<!-- #1647 -->
### #1647: [v2.6.6] - 2026-10-08 - I7 one question at a time

- `intake_card.conversation(replies)` and `factory.py card --step --reply ...`:
  the intake is a conversation. Each message holds one question, a
  one-sentence why, numbered options one per line, the RECOMMENDED option with
  its reason; then it waits. After the sixth answer, a recap and a request for
  "yes"; a line number reopens just that question. Same code in claude-nine
  and OpenClaw (Telegram: `--format openclaw-json`).
- Test: `choice_card/intake_card/test_intake_step_i7.py`.

### #1647: [v2.6.1] - 2026-10-08 - H9 readable intake card

- New `scripts/core/choice_card/intake_card/`: builds the six intake questions
  (length, music style, video style, video model, spend limit, storyboard
  approval) as one block per question, one numbered option per line,
  RECOMMENDED marked, blank line between questions, a closing "how to answer"
  line. Plain text so no sender strips line breaks; split between questions
  under Telegram's limit; exact `openclaw message send` argv and Bot API body.
- `factory.py card` prints the raw card (Claude Code chat) or send payloads.
- Intake and book `question_message` now use the same layout (they were a
  single `"\n".join`, no blank lines).
- Test: `choice_card/intake_card/test_intake_card_h9.py`.

<!-- #1648 -->
### #1648: [v2.6.5] - 2026-10-08 - Part I I1: captions spell-checked; exact website asked and kept

The client's website was misspelled in the captions ("wakeuphappysis.com").

### Added
- `protected_names.check_spelling`: every caption word must be a real word
  (bundled `english_words.txt.gz` plus simple endings) or a protected word
  (names, brands, the client's website). An unknown word fails QC
  (`CAPTION_MISSPELLED`) with the word shown. Wired into
  `delivery_variants.checks.check_captions`.
- `protected_names.check_website`: the exact address must appear verbatim in the
  lyrics, captions and end card (`WEBSITE_NOT_VERBATIM`).
- Intake asks "What is the exact website address you want people to go to?" when
  the ad sends people to a website; stored as `website` and as a protected word.
- Test: `scripts/core/test_caption_spelling_i1.py`.


### #1648: [v2.6.4] - 2026-10-08 - Part H H7: captions use the approved words + protected names

Kiesett's Stop Stale ad captioned "the house went still" for "Stale": the lyric
sheet itself said "still" (136 Suno requests), Suno sang it, the caption copied
the sheet. Fixed at the source.

### Added
- `scripts/core/protected_names.py` (+ `test_protected_names_h7.py`): sheet BUILD
  gate, sung-take words check, sheet-text captions timed from Suno timestamps,
  caption QC. Codes `PROTECTED_NAME_CHANGED`, `PACKET_LINE_REWRITTEN`,
  `PROTECTED_NAME_SUNG_WRONG`, `CAPTION_MISMATCH`, `CAPTION_SOURCE_NOT_SHEET`.

### Changed
- `lyric_writer.validate_lyrics`: brief `packet_lines` + protected names reject a changed name or rewritten packet line.
- `music_director.build_generate_request(..., protected=)`: no Suno request from a bad sheet.
- `music_qc.check_song_qc(..., protected=)`: a take that sang a protected name wrong FAILS.
- `delivery_variants.checks.check_captions(..., protected=, text_source=)`: speech-to-text source or any mismatch FAILS.
- `QC.md` / `SKILL.md`: H7 gate row and rule.

<!-- #1650 -->
### #1650: [v2.6.7] - 2026-10-08 - I8 sung hook and repeat formula

- New `scripts/core/sung_hook/` (module + tests). Every sung style gets ONE
  hook (4-10 words, client's own words, protected names exact), sung
  `clamp(1 + floor(L / 25), 2, 12)` times (L = delivered seconds). First hook
  by 15% of runtime, last at 90%, rest evenly spaced.
- `suno_recipe.check_lyric_sheet` / `prepare` / `guard_request` take
  `length_s` and enforce the exact count; `music_director.build_generate_request`
  passes it through. `suno_recipe.hook_target` returns 0 for the exempt
  Velvet Voiceover style.
- `suno_recipe.score_take` measures how many hooks were actually sung (Suno
  aligned words + detector segments): count met = accept, one short = accept
  with a flag, two or more short = regenerate. The receipt carries hook text,
  target, measured count and times.
- `SKILL.md` gains the "Sung hook" section.

### #1650: [v2.6.1] - 2026-10-08 - G12 Suno song recipe is the default for every Suno style

- New `scripts/core/suno_recipe/` (module + tests): one gate every Suno
  style goes through. Style text carries the sung/spoken map, the lyric sheet
  needs a repeated sung hook built from the client's own words, singing starts
  early (15% of runtime target, 5/10 band), and a take is judged only from
  measured segments, never labels.
- `music_director.build_generate_request` takes `style_id` and `client_text`
  and refuses a raw Suno style prompt that skipped the recipe.
- Only the Velvet Voiceover id (`velvet_voiceover`) is exempt.
- `SKILL.md` and `references/choice-card-spec.md` gain the "Suno song recipe" section.

<!-- #1651 -->
### #1651: [v2.6.1] - 2026-10-08 - Part I I4: masters end 2 seconds early

- New `scripts/core/master_length/`: a chosen length L delivers a master of at
  most L-2 seconds (60 to 58, 30 to 28, 90 to 88, 120 to 118). Hard maximum,
  not a band. Song, shot plan and end card are planned to L-2; QC (`final_edit`
  record, reason `MASTER_TOO_LONG`) fails any longer master.
- Intake summary now carries `master_max_s`.
- Enforcement (repair): `qc_gate.evaluate(..., master={chosen_length_s, measured_s})`
  is mandatory whenever `final_edit` is required (CLI `--chosen-length-s`,
  `--master-s`); a 62 s master on a 60 s video fails `MASTER_TOO_LONG`, a missing
  master is `MASTER_LENGTH_MISSING`. `final_assembler.assemble(chosen_length_s=)`
  (or timeline key `chosen_length_s`) refuses an over-long plan, an end card that
  starts at or after L-2, and an over-long rendered file, before spend where it
  can. `shot_planner.bind_plan(chosen_length_s=)` rejects a song or shot past L-2
  (`SONG_PAST_MASTER_END`, `SHOT_PAST_MASTER_END`).

---

## v2.6.1 - 2026-10-08 - H14 song files in every delivery

- Added `delivery_variants/song_files.py`: builds the full mastered mix as MP3 320 kbps + WAV named after the ad (plus the instrumental pair when one exists), lists them in `delivery-receipt.json` and `README.md`, and `check_song_files` fails a delivery missing any of them. New `song_files` QC check in `qc_gate` and `qc-schema.json`. Test: `scripts/core/delivery_variants/test_song_files_h14.py`.


## [Unreleased] - 2026-10-07 - v2 BUILD-OUT packaged into this copy

Regenerated `scripts/core/` from the canonical build core — 120 files, tree sha256 `351575f76825de6df4bfd2c7520dcc9ed06631e5f3a040a5f246149fabe735e7` (both copies byte-identical).

Packaging unit `BO-PKG2-U2` regenerated `scripts/core/` from the canonical
build core (`<build>/core/`) so this copy carries the version 2 BUILD-OUT
outputs, byte-identical to the Claude-Nine / Claude Code copy; entrypoint,
exit map and the 14 production modules unchanged.

### Added (BUILD-OUT owned outputs, whole modules)
- `audio_c3/extend/`, `audio_c3/voice_packs/`, `batch_mode/`,
  `catalog_calculator/extensions/`, `choice_card/looks/`, `intake_book/`,
  `kie_dispatch/unknown_resolution/`, `shot_planner/speaker_check/`,
  `style_bibles/canvas_to_3d/`, `style_bibles/canvas_to_life/`
- import closure those modules need to load: `audio_c3/voice_casting.py`,
  `choice_card/stl_voice_guard/`, `lip_sync/narrator_rule/`, `music_styles/`,
  `qc_voice_match/` (root package only), `spoken_share/`, `style_bibles/hybrid/`,
  `style_defaults/`, `voice_velvet_echo/`

### Changed
- `SKILL.md` exit-map note: removed the dead build-tree test path
  (`tests/distribution-parity/run_parity.sh`), plan G5 packaging step.

### Not shipped here, on record
- `core/docs_rename_velvet_voiceover/` — build-tree sweep tool carrying
  operator absolute paths; build tooling, never client skill code.
- `core/lip_sync/kling_first/`, `core/qc_voice_match/octave_guard/` — not yet
  present in build core (unit outputs still in their lanes).
- `core/kie_dispatch/kie_dispatch.py` — packaging owned by unit `A2-R2-U2`,
  whose canonical module is under fix; shipped only from the fixed core.

`version:` stays `v2.3.0`: the release bump belongs to the V2-W4 ship lane.


## [v2.4.3] - 2026-10-07 - audio-fix wave D36-D38: no-echo rule, spoken-share band, reverb-tail QC, pitch ban, Sketch-to-Life voice guard

### Added
- `scripts/core/audio_c3/no_echo/` - every Suno request (song and voice-pack) stamps dry close-microphone vocals plus the seven negative tags and refuses spacious / cinematic / choir in spoken parts (D22a).
- `scripts/core/smp/no_echo/` - the same no-echo rule on the Skill 35 weekly drama-song request.
- `scripts/core/qc_reverb_tail/` - QC measures the reverb tail after each spoken line; a ringing line fails QC (D22a).
- `scripts/core/qc_voice_match/pitch_ban/` - pitch ban guard for voice-match QC.
- `scripts/core/spoken_share/` - spoken share retarget: target 45 percent, band 40-55, rap counts as spoken, first sung line within about 10 seconds (D15).
- `scripts/core/spoken_share_card_docs/` - card and docs lines carrying that spoken-share rule.
- `scripts/core/smp/spoken_share/` - the same spoken-share rule on the Skill 35 planner wave (D15).
- `scripts/core/choice_card/stl_voice_guard/` - Sketch to Life is always All Suno; Velvet Voiceover is refused for that look (D25).

## [v2.4.2] - 2026-10-07 - fix: style bible compiler routes its prompt cap through the one KIE enforcer

### Fixed
- `scripts/core/product_style_bible/bible.py` imports `shared-utils/kie_prompt_enforcer.py` and calls `KPE.check(...)` (kind verbatim, ceiling only) on every compiled prompt, as the KIE prompt enforcer guard (rule 12) requires of a declared gate module. The cap values (20000 sunburst, 25000 legacy) and compile behavior are unchanged.

## [v2.4.1] - 2026-10-07 - docs: PACKAGING-DECISION wording

### Fixed
- `PACKAGING-DECISION.md` no longer cites the retired legacy updater path literally (single-update-skills-entrypoint guard, section C). No behavior change.

## [v2.3.0] - 2026-10-07 - docs: directive 2.1 document set landed

### Added
- `INSTRUCTIONS.md` - operating instructions: the mandatory TYP gate, the
  eleven build-directive section 25 runtime steps, the shared
  intake/preflight controls and section 24.3 intake rules, exit-code
  envelope contract, section 17 QC non-negotiables, and the skill's
  never-do list.
- `EXAMPLES.md` - twelve verified examples using only the implemented
  entrypoint (`scripts/core/intake_preflight/factory.py`) and the repo's
  shipped `check-skill-prereqs.sh` / `qc-prereqs-json.sh`; every shown
  outcome was executed and captured (intake ok/waiting/rejected, resume
  ok/parked, preflight pass/tool-unavailable/credential-missing/
  approval-missing/approval-expired/reference-outside, checker rc 0/2/3,
  lint PASS on 24 PREREQS.json files).
- `QC.md` - install-time rubric (10 points, gate 8.5), file/version and
  credential checks, control-layer smoke, 9-question knowledge check,
  and the campaign QC gate checklist mapped to build-directive sections
  17.1-17.9 with anti-patterns.
- `INSTALL.md` - first install (`install.sh` one-liner / checkout),
  update (`update-skills.sh`), canonical credential paths, helper-skill
  install law (section 2.4), verification steps, run-storage root,
  version bookkeeping and rollback via installer backups.
- `CORE_UPDATES.md` - surgical allowlist (AGENTS.md / TOOLS.md /
  MEMORY.md) with exact text blocks; core persona files never touched.
- `PREREQS.json` - executable prerequisite mirror per INSTALL-CONTRACT
  Rule 16: skills 01/02/07/24/25/27/30/46/66/67/68/74 (folder form),
  KIE_API_KEY (required), FISH_AUDIO_API_KEY (optional), python3 and
  ffmpeg binaries, faster-whisper advisory note; every required `satisfy`
  names the action, canonical secrets path and config command.

### Changed
- `DEPENDENCY-MANIFEST.md` - helper dependency table now carries version
  + git tree hash per helper pinned at source commit
  `cc2e595f1de87c1411dfb44e9542f0017f3b5acc` (2026-10-07), cross-linked
  to `PREREQS.json` as the executable mirror. Scaffold notes for
  release-time pins (W5-02) are preserved.

---

## [v2.3.0] - 2026-10-06 - feat: OpenClaw distribution (W3-02)

- Initial Skill 75 folder: `SKILL.md` (route boundaries, control
  entrypoint contract, section 24.3 intake rules, paid-generation
  boundaries, department wiring), `scripts/core/` shared canonical core
  (state_store, artifact_graph, spend_ledger, job_recovery, contracts,
  acceptance-profile, intake_preflight, qc_gate, timing_guard),
  `DEPENDENCY-MANIFEST.md`, `THIRD_PARTY_NOTICES.md`,
  `skill-version.txt` = v2.3.0. Exit-table correction and CI guard
  repairs followed the same day (commits `2dd07e409`..`37a6926c8`).

---

Format follows `46-kie-callback-relay/CHANGELOG.md`: newest first,
`## [version] - date - type: summary`, sections `### Added` /
`### Changed` / `### Fixed` / `### Tests`.
