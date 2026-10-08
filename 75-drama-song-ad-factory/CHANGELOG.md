# Changelog - drama-song-ad-factory (Skill 75)

All notable changes to this skill are documented here. The version of
record is `skill-version.txt` (kept in agreement with the `SKILL.md`
frontmatter `version:` field).

---

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
