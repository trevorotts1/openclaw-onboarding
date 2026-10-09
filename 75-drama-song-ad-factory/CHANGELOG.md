# Changelog - drama-song-ad-factory (Skill 75)

All notable changes to this skill are documented here. The version of
record is `skill-version.txt` (kept in agreement with the `SKILL.md`
frontmatter `version:` field).

---

## v2.9.15 - 2026-10-09 - Batch PKG v27.1.0 roll-up: the complete delivery package, no blur fill, storyboard picture budget, camera vocabulary, two-strike gate

Released as one batch with onboarding v27.1.0. Units: FU-DEL-01 three audio versions and note; FU-DEL-02 character bible PDF and image bible; FU-DEL-03 script PDF; FU-DEL-04 storyboard grid PDF; FU-DEL-05 video twice, captioned and clean; FU-DEL-06 60 and 90 second clips; FU-DEL-07 ready-to-post kit; FU-DEL-08 cover image; FU-DEL-09 lyric sheet PDF; FU-DEL-10 caption file; FU-DEL-11 character images; FU-DEL-12 welcome sheet and package list; FU-DEL-13 delivery folder contract and the 12-item hard gate; PKG-05 (DEL-14) crop-in full height, refusal gates, proof suite and docs; PKG-06 (DEL-15) storyboard picture counts, price surfaces and proof; PKG-07 (DEL-16) camera vocabulary, shot planner rules, signature presets and proof; PKG-08 (DEL-17) two-strike shared module, wiring into six skills, fake-skill proof.

## v2.9.15 (included) - FU-DEL-11: character images as separate full-resolution delivery files

- New `scripts/core/character_images/` package: every character picture reaches the delivery folder as its OWN full-resolution file (`11-character-<slug>-<view>.<ext>` — close-up, side profile, three-quarter, full standing), byte-for-byte `shutil.copyfile` from an existing `character_library` record. No generation, no crop, no resize, no re-encode, no contact sheet; the page screenshots are untouched.
- View selection, in order of trust: an explicit `views` mapping on the record, else the whole view words in the reference file's own name (`close-up.png`, `side.png`, `three-quarter.png`, `standing.png`, `lipsync-closeup.png`). One file never claims two views.
- Fail closed: a missing view names exactly the missing views and leaves the delivery folder untouched (the whole plan is computed before any write); the same for NO_CHARACTERS, SOURCE_MISSING, BAD_IMAGE and DUPLICATE_SLUG. Receipt rows carry source basename + bytes, never an absolute path.
- New `test_character_images_del11.py` (14 unit tests). Shared `scripts/core/character_images/` is byte-identical to the 999-setup copy (v2.7.39).

## v2.9.15 (included) - FU-DEL-09: the lyric sheet PDF

- New `scripts/core/lyric_sheet/`: the run's approved `creative/script.json` rendered into the delivery folder as `09 - Lyric Sheet.pdf`. Section headings come from the song's own tags (one break per block, song order), the approved title and lines print verbatim, and nothing on the page is under 12 pt. Bright page: white paper, near-black ink, gold eyebrow and rule, footer on every page.
- Stdlib-only PDF writer (this core is stdlib-only), deterministic bytes: no date, no random id, same approved sheet renders identical.
- Refuses fail-closed: `MONEY_ON_PAGE` (chrome wording), `TOOL_NAME_ON_PAGE` (a tool or model name reaching the page), `SCRIPT_MISSING` / `SCRIPT_UNREADABLE` / `EMPTY_SHEET`. A lyrics-only run reuses `lyric_writer.lyric_structure.parse_sheet`, so both approved inputs give the same section structure.
- 17 unit tests in `test_lyric_sheet.py` (size floor, section order, pagination, wrap maths, refusal paths, delivery-folder write, CLI exit codes).

## v2.9.15 (included) - DEL-10: caption file (.srt) in the delivery folder

- New `delivery_variants/caption_srt.py`: a finished run exports its caption file into the delivery folder as `10 - Captions.srt` (slot `FILE_NUMBER`, one constant to renumber), built from the measured caption cues by `captions_burn.build_srt` — the same builder the caption burn uses, so the exported file and the burned captions cannot drift. No measured cues is a refusal receipt and NO file (F18: no clock is ever invented); the text is parsed back before it is written, so what lands is valid SRT by construction. `check_captions_srt` / `python3 scripts/core/delivery_variants/caption_srt.py check <dir>` fails a missing, empty or broken file (exit 5). `delivery_variants` exports `export_captions_srt` / `check_captions_srt` / `parse_srt` / `srt_file_name`. Test: `scripts/core/delivery_variants/test_caption_srt_del10.py` (22 tests over fixture `fixtures/caption_srt_del10.json`: generic sample sheet, measured word timings, golden SRT bytes; structure re-checked by the test's own parser). Docs: `references/stage-runbook.md` + the QC.md checklist. Version: onboarding `skill-version.txt` + SKILL.md frontmatter v2.9.13 -> v2.9.14 (G3 gates a skill-content change on that bump); the 999 copy bumps its own VERSION train 2.7.38 -> 2.7.39 with its SKILL.md frontmatter (its CI has no such gate, but its parity-contract re-sync procedure requires the bump).

## v2.9.15 (included) - DEL-12 welcome sheet + the canonical delivery package list

- New `scripts/core/delivery_package/`: `package_items.py` holds `PACKAGE_ITEMS` / `PACKAGE_FILES` -- the canonical numbered file-name list for all 12 package items (01..12, 20 files), the single shared constant the client-facing page and the delivery gate both read.
- `welcome_sheet.py` renders that constant into the one-page client WELCOME SHEET PDF: title, gold rule, every file with its number badge and one sentence on what it is for. Stdlib PDF 1.4 writer (base-14 Helvetica, no third-party library, no network), deterministic bytes, 13 pt body type, hard 12 pt floor.
- `delivery_checklist` re-exports the constant and gains `missing_package_files(delivery_dir)`, so the gate reads ONE list instead of keeping a second copy beside the printed page.
- New `scripts/core/delivery_package/test_welcome_sheet_del12.py` (11 tests): one page, all 20 names and 12 numbers present, no type below 12 pt, no client/model/tool name, no price or income claim, byte-identical rebuild, checklist shares the same object.

## v2.9.15 (included) - FU-DEL-13 delivery folder contract (Q12 gate)

- `scripts/core/delivery_package/`: the client delivery folder contract -- 12 numbered package items, exact file names, and what "opens" means per kind (PDF header, SRT cue block, non-empty media, image directory). `packaging.package_run(run_dir, out_dir)` is the one packaging call: it discovers each item's `produce_delivery()` component, writes the canonical numbered files, and verifies the folder. Fail closed: `COMPONENT_MISSING` (naming every item still owed, before any write), `COMPONENT_FAILED`, `PACKAGE_INCOMPLETE`.
- `delivery_checklist` gains Q12 `PACKAGE_COMPLETE` (`CHECKLIST_PACKAGE_INCOMPLETE`): the receipt names the delivery folder and Q12 reads it -- all 12 items present and opening, one missing item fails the run and is named. The gate is hard; the 11 human checklist questions are unchanged.
- New `test_delivery_package_e2e.py`: one fixture run through the packaging entry point. While a sibling DEL-01..DEL-12 producer is not in the branch base it SKIPs with the full list of items still owed (never a fabricated green); a raising producer or a folder that does not verify still fails. `QC.md` records the package-items line.
- Shared core byte-identical to the 999 copy (2.7.39).

## v2.9.15 (included) - DEL-08: one cover image (thumbnail) per delivery folder

- New `scripts/core/delivery_variants/cover_image.py`: at the end of the run, build the ONE cover image into the delivery folder — frame from the approved storyboard stills (`storyboard/stills.json`, gated by `approval_runner.gate_open`, face-visible shot first), title from the approved script (`creative/script.json`, brief title as fallback, never invented). One ffmpeg pass through `load_governor.run_ffmpeg` writes `<safe ad name>-cover.png` (default 1280x720, 16:9), title inside the title-safe inset via `drawtext=textfile=` with `expansion=none` (data, never filter syntax). A build whose ffmpeg has no drawtext refuses `COVER_DRAWTEXT_UNAVAILABLE`.
- `check_cover_image` is the delivery QC gate (measured IHDR pixels, matching sha256, README listing; the row's own claim never passes). `qc_gate` gains the `cover_image` check; the stage runbook gains the run row. Exactly one cover thumbnail per delivery folder.
- CI fixes: local runner variable renamed off the bare `launch(` token the agent-browser headless-only guard false-positives on (no Playwright in this module); `skill-version.txt` bumped with the content change per G3.

## v2.9.15 (included) - FU-DEL-05: the delivery folder ships the video twice — captioned and clean

- New `scripts/core/delivery_variants/video_delivery.py`: one delivery folder per run carries TWO numbered files — `1 - <Ad> - Ad (captioned).mp4` and `2 - <Ad> - Ad (clean, no captions).mp4`. Both are rendered from the ONE caption site (`final_assembler/captions_burn`): the captioned cut burns that plan, the clean cut is the same plan with `style.enabled` False, so neither variant invents its own words or look.
- Nothing is called delivered until `delivery_audio.check_delivery_audio()` has passed it (AAC-LC, 48 kHz, faststart, not silent). A refused file is deleted and the step raises `DELIVERY_AUDIO_REFUSED`, fail closed — a half-delivered pair is never handed over.
- `check_video_delivery()` is the QC row (PASS / FAIL / UNAVAILABLE, same contract as `song_files`) and `write_video_docs()` lists both files in `delivery-receipt.json` and `README.md`. The caption SRT rides in the receipt, not as a third file (DEL-10 ships it).
- `qc_gate` now requires `video_delivery` on the delivery gate; `final_assembler/captions_burn` grew the off plan the clean cut renders. New `references/stage-runbook.md` note.
- `skill-version.txt` and SKILL.md frontmatter: v2.9.15. Shared `scripts/core` stays byte-identical to the 999-setup copy.

## v2.9.15 (included) - DEL-07 ready-to-post kit

- `scripts/core/ready_post_kit/` builds the READY-TO-POST KIT a client posts from: `07 - Ready-to-Post Kit.pdf` plus the same kit as `07 - Ready-to-Post Kit.json`, written into the ad's delivery folder. It carries which version to post where (every delivered file plus the cutdowns `clip_cutdown.clips_for(length)` schedules), the link (brief aliases -> a URL in the offer -> the `Banner link` line `batch_zip` publishes), a caption and suggested hashtags for YouTube, Instagram, TikTok and Facebook, and the YouTube block done properly: title <= 100 characters, description with the link and hashtags, tags <= 500 characters, counts shown. Bright page, every glyph >= 12 pt (enforced in the layout as `KIT_FONT_FLOOR` and read back out of the finished PDF by the test). Reuses `clip_cutdown`, `batch_zip`, `delivery_checklist`, `character_library`, the storyboard gate, the script-approval record, the card answers and the approved caption words; never re-implements them. Fail closed by name: `KIT_NO_LINK`, `KIT_STORYBOARD_NOT_APPROVED`, `KIT_NO_SCRIPT`, `KIT_DELIVERY_RECEIPT_MISSING`, `KIT_CHECKLIST_FAILED` (a measured "no"), `KIT_BANNED_TEXT` (a tool or model name, a dollar amount or an income promise anywhere in the copy -- client-facing wording stays generic). Contract: `references/ready-post-kit.md`; proof: `scripts/core/ready_post_kit/test_ready_post_kit.py` (19 cases).

## v2.9.15 (included) - FU-DEL-06: the 60/90 second clips land in the delivery folder

- New `scripts/core/delivery_clips/`: the 3, 5 and 10 minute ads ship their TWO clip files inside the client's delivery folder with clear numbered names (`6 - 60-second clip.mp4`, `6 - 90-second clip.mp4`, item 6 of the delivery package; both files share the slot, DEL-13 owns the full list).
- Reuse only: windows come from `clip_cutdown.plan_clips`, cuts from `run_clips`, and `delivery_audio.check_delivery_audio()` gates every delivered clip AFTER the rename — a refused clip raises `CLIPS_AUDIO_REFUSED`, is deleted, and is never listed. Receipt and README are merged the way `delivery_variants.song_files` does (never a clobber).
- `check_clips` is the fail-closed QC answer (PASS/FAIL/UNAVAILABLE): a promised clip missing, unlisted in `delivery-receipt.json` or `README.md`, or failing the audio gate is a FAIL naming the file; 60 s and 90 s ads owe none. CLI `--check` exits 5 on anything but PASS.
- New test `scripts/core/delivery_clips/test_delivery_clips_del06.py` (20 tests): file names, cut points on whole lines with the sung hook kept, the gate on every file, receipt/README merge, fail-closed paths. `references/stage-runbook.md` and `references/choice-card-spec.md` gain the FU-DEL-06 paragraph/bullet (byte-identical with the 999 copy).

## v2.9.15 (included) - DEL-01: three audio versions + plain-English note in the delivery folder

- The delivery folder now ships the song three clearly-labelled ways, all from EXISTING pipeline output (the finished mix, the instrumental the run made, the vocal stem saved for every take; nothing re-synthesised): `delivery_variants.build_audio_versions(mix, delivery_dir, instrumental, vocal_stem)` encodes `01 - Full Song.mp3`, `02 - Instrumental.mp3` and `03 - Voice Only.mp3` (MP3 320 kbps each) and writes `00 - About These Audio Files.txt`, the short plain-English note on how the three differ; `write_version_docs` lists them in `delivery-receipt.json` and `README.md` (merge, never clobber). Every source is required -- a missing mix, instrumental or vocal stem raises `ValueError`, never a two-version delivery dressed up as three.
- `check_audio_versions` / `python3 scripts/core/delivery_variants/song_files.py check-versions <dir>` fails a missing version, a missing note, or anything unlisted in the receipt or README (exit 5). The check is registered as `audio_versions` in `qc_gate.CHECKS` so the delivery gate can require it. `delivery_variants` exports `build_audio_versions` / `check_audio_versions` / `write_version_docs` / `version_note_text` / `expected_version_files` / `version_file_name` / `DELIVERY_VERSIONS` / `VERSION_NOTE_NAME`.
- Test: `scripts/core/delivery_variants/test_audio_versions_del01.py` (13 tests: the three numbered MP3s and note, fail-closed on a missing/empty source, the note is plain English with no model/tool names or dollar amounts, one table drives labels/note/QC so they cannot drift, missing file/unlisted/rewrite-once/bitrate/duration/receipt-shape, and the `qc_gate.CHECKS` registration). Skill version v2.9.14.

## v2.9.15 (included)

- **PKG-07-U2 (DEL-16): shot-planner rules ship as `scripts/shot_planner/`.** The camera vocabulary every shot brief carries (establishing wide through insert and detail; eye/low/high/bird's-eye/dutch angles; static through crane moves; 24/35/50/85 mm lenses; aperture wide open to stopped down) plus the DEL-16 rules, enforced for music and for dialogue or narration alike: one camera move per clip and four-to-six-second clips; whip pans and fast orbits only as an edit transition between two clips; text and logos in post; "shallow depth of field" in prompts, never an f-stop number; the shot-length ladder from about eight seconds for extreme wides down to about two and a half for extreme close-ups; medium-shot dominance; close-ups at most thirty-five percent; at most two identical framings in a row; every scene opens on an establishing wide; five shot types and three angles from two minutes up; lens and aperture matched to emotion; coverage spans master/medium/close-up/reverse/insert/cutaway with the 180-degree rule, eyelines, scene geometry, shot-reverse-shot, motivated moves, rack focus, depth of field, lighting choice and screen-direction continuity. Every pacing percentage is labeled a planning range, not a measured standard. New `test_del16_rules.py` (positive + negative case per rule, three content modes); CLI `vocabulary`/`plan`/`check` on the control envelope.

## v2.9.13 - 2026-10-09 - Batch MGB023 follow-up 2 (no more silent ads)

- Delivery audio gate on EVERY path that hands the client a video: the final assembler (already), the 60 and 90 second clip cutdowns (`clip_cutdown.run_clips`, a refused clip is deleted), the batch zip (captioned ad and clean master) and the delivery checklist. Each one calls `delivery_audio.check_delivery_audio()` and fails closed.
- `check_delivery_audio()` now enforces what the order says: AAC-LC, 48 kHz, moov before mdat (faststart), and not silent. New codes `DELIVERY_AUDIO_NOT_48K` and `DELIVERY_NOT_FASTSTART`; new `require_delivery_audio()` raises `DeliveryAudioRefused`.
- `clip_cutdown.build_argv` used a bare `-c:a aac`; it now uses `AUDIO_OUT_ARGS` + `FASTSTART_ARGS`.
- New `test_delivery_gate_paths.py` (one MP3-audio refusal test per delivery path) (shared core is now byte-identical to the 999 copy v2.7.38; `delivery_fixture.py` removed, tests build their own fixtures).

## v2.9.12 - 2026-10-09 - Batch MGB022 follow-up

- FU-AAC-FINAL-MUX (#1785) plus the question-count wording fix: the intake card closing example ("1, 1, ...") is now built from the real question list (9, or 10 with a saved character) and the docstrings, help text and choice-card-spec say nine. New test `test_closing_example_answer_count_matches_question_count`.

## v2.9.11 - 2026-10-09 - Batch MGB021 roll-up

- FU-U3, FU-RNBFLOW-SONG, FU-HOOK-PLACEMENT, FU-U11, U15g, FU-ONE-SPEND-QUESTION, FU-STYLE-QUESTIONS, FU-VIDEO-MODEL-CHOICES, FU-STORYBOARD-SHOWS-BOTH, FU-SONG-APPROVAL, FU-SCRIPT-APPROVAL, FU-CLIENT-GUIDE, FU-AI-MODELS-QUESTION and FU-TEST-TMP-ISOLATION land together. The intake card is AI MODELS, LENGTH, MUSIC STYLE, VIDEO STYLE, VIDEO MODEL, BUDGET, STORYBOARD APPROVAL, SONG APPROVAL, SCRIPT APPROVAL (nine questions; ten with a saved character, which sits second).
- Integration fixes: the video model price follows the LENGTH answer by question id (not position); song-choices requests carry the style and hook plan to the judge; the client's own lines are checked before the recipe guard.

## Unreleased

- **U12: docs in lockstep with the code.** SKILL.md gains the tag-grammar /
  style-plan / voice-tag / per-style-band bullets in the Suno recipe, the
  "Request and prompt limits" section, the early-captions paragraph (with
  FU-U9 named as NOT built) and the book-orientation bullets (FU-U11, open
  branch); QC.md gains one section; the onboarding SOP DS-2/4/5/6/7/9 is
  brought to the same facts (DS-4 step 5 now says 6 to 8 clips of 4 to 6
  seconds); `references/choice-card-spec.md` gains 2.3 (options come from the
  registry; the fit card FU-U4 is not built) and the machine-checked
  "Offered lengths (seconds): 60, 90, 120, 180, 300, 600." line. SKILL.md
  closes with a "Sections marked TODO" block naming FU-U3, FU-U4, FU-U9 and
  FU-U11 as the sections to refresh when those land. New test
  `scripts/core/prompt_templates/test_docs_u12.py`.

## Unreleased - FU-U4: client lines are a contract; the STOP card lists only real options

- Client lines are a contract: concept mode requires `packet_lines` (`PACKET_REQUIRED_IN_CONCEPT_MODE`) in `lyric_writer` and `music_director`, and a missing client line is refused NAMING its id instead of being invented. New `choice_card/intake_card` fit card plus `factory` card `--fit` (exit 2, one row per style), registry-only options (no option invented at the card), an intake mode flag, and intake notices for sfx, echo voice, length-not-offered and fps. The STOP card lists only options the registry actually offers. Spec `references/choice-card-spec.md` section 2.3. New test `scripts/core/choice_card/intake_card/test_fit_card_u4.py`.

## Unreleased - FU-U3: bands per music style; rap is its own delivery; silence is not speech

- Per-style bands under the SAME locked 5/10 band: `spoken_share.STYLE_TARGETS` holds Soul Ballad and Soul Rise at exactly 22.5 runtime spoken / 77.5 sung-of-voice; R&B Flow's target is the documented default flagged as a TREVOR-DECISION ITEM in plan 18 section 9 item 1 -- the share planned from the approved sheet (the U2 plan's word counts at the style's measured rates), not a new number invented here -- and sung-of-voice on a rap sheet is recorded, not gated (hook content, not a planned share); the 6 s sung stretch and the hook count stay hard. `measure_share(segments, style_id=...)` reports rap separately for a rap style and counts plain spoken against its target; `segments_from_sung_stretches(voiced=)` turns music-only time into a fourth delivery `none` that counts in runtime and never in voice time (a music-only gap no longer counts as spoken); the rap-versus-speech split is measured word timestamps x the sheet's delivery labels, recorded as basis `aligned`, never `measured`. `song_dispatch.judge_take` / `run_takes` and `suno_recipe.score_take` carry `style_id` (+ `plan`) through validate and judge. New test `scripts/core/spoken_share/test_style_bands_u3.py` with the g1b segment fixture from SONG-RECEIPT (fails on the base tree: `voiced=` did not exist).

## v2.9.9 - 2026-10-09 - FU-SAVED-CHARACTER-QUESTION

- The saved-character intake question now reads "Do you want to create a new character for this ad, or use one you've used before?" with "You have N character(s) saved with us." and numbered options: "Create a new character (recommended)" first, then "Use <Name> - <description>" for each saved character. With no saved characters nothing is asked; one line says a new character will be created and saved for next time. Same recap ("Character: new" / "Character: <Name> (saved)") and same effect of each answer. Test: `character_library/test_saved_character_question.py`.

## v2.9.9 - 2026-10-09 - FU-LENGTH-CLIPS: clearer length question; 3 minutes now comes with 60s and 90s clips

- New `core/clip_cutdown`: the 3, 5 and 10 minute ads cut an automatic 60-second and 90-second clip (whole lines, at most L-2 s, hook placement kept, never into the end card; FFmpeg only, free). Before this the card promised clips for 5 and 10 minutes but no code cut them.
- The LENGTH question is now a full question ("How long do you want your ad to be? ...") with numbered options that say what the client gets; 3 minutes now comes with the clips; the recap reads "Length: 3 minutes + 60s and 90s clips". The Clips card row lists clips for 3 minutes and says they are included in the price.
- Docs (SKILL.md, INSTRUCTIONS.md, choice-card-spec.md, price-menu.md, stage-runbook.md) now agree with the code.

## v2.9.9 - 2026-10-09 - FU-INTRO-MESSAGE

- Every new interactive run opens with a short one-time intro of what the factory makes, sent as its own message before question 1 (`factory.py card --step --run-state-file`); never on resume, recap, batch or CLI-only paths.

---
## v2.9.10 - 2026-10-09 - FU-HOOK-PLACEMENT + FU-RNBFLOW-SONG

- **FU-HOOK-PLACEMENT: the hook is the payoff, never the opener** (Trevor 2026-10-09: "THE HOOK HAS TO MAKE SENSE AND BE PLACED CORRECTLY"). New `core/sung_hook/hook_placement.py`. (1) Build-up, always on: before the first hook the sheet carries a verse, plus a pre-chorus/build where the style's section plan has one and the length plan has pre-choruses; checked in `suno_recipe.prepare`/`build_request`, `guard_request` and `check_payload`. (2) Story sense, always on: the `hook_plan` (`{"true_at_beat": beat}`, shape in SKILL.md) names the U16 beat where the hook's words become true (never the opening beat); the gate MEASURES each hook block's planned position (words before it at the style's rates, as a share of the sheet, mapped onto the arc) and fails a first hook before that beat, whatever beats a plan claims (`plan_for` writes the measured beats as a receipt). The count is `hook_placement.hook_target`: `sung_hook.hook_count` for the length, reduced to what fits after that beat starts. `music_director.build_generate_request(true_at_beat=...)` emits the plan and carries it as `_hook_plan`; `song_dispatch.run_takes` moves it into the judge's plan and never sends it to KIE. (3) After Suno, always on: `song_dispatch.judge_take` gate `hook_placement` fails a take where Suno added hook blocks, moved a hook earlier, sang the first hook inside the build-up window or before the beat's start second. (4) No gate switches itself off: a missing style, length, sheet, `hook_plan` or `true_at_beat` is a FAIL reading `UNMEASURED: <field>`. (5) The Suno style text says "Sing the sections in the order written; the song never opens with the hook: build up through the verse first". `sung_hook.measure` strips Suno's inline section headers before reading words. Replays: v1 sheet with its honest plan (true at the turn) FAILS (first hook at 16% of the song; 6 hooks where 3 fit); a built-up sheet with its first hook about a quarter in, true at the turn, FAILS; v2 sheet FAILS (hook before any verse); v2 take g2a FAILS (9 hook blocks against 6, added at 13.6 s, 46.3 s, 94.8 s; first hook at 8.9 s inside the 17.7 s window); v1 take FAILS at the turn (first hook sung at 23.8 s, the turn starts at 84.6 s).
- **FU-RNBFLOW-SONG: every sheet and returned song held to its music style's own definition** (new `core/song_contract`): every chorus is the hook plus at least one other real line; the sung sections the length plan calls for are present (R&B Flow's verses are rap); the planned sung share of voice is a per-style floor (Soul Ballad and Soul Rise 77.5%, so a Soul sheet may be almost all sung; R&B Flow the share its own length plan holds after its rap budget); rap blocks are cued "rhythmic rap on the beat", never conversational; an upbeat style never asks for "slow"; a spoken outro says "no melody". Run by `suno_recipe.guard_request`, `song_dispatch.validate_request` and gate `song_contract` in `judge_take`.
- **Golden sheets**: all six pass `guard_request` (recipe + hook placement + contract), `song_contract` and `music_director.build_generate_request` at their delivered length: every Hook block carries a second real line, R&B Flow rap cues say "rhythmic rap on the beat", no "slow" in an R&B Flow sung block. Each names the beat where its hook ("You can rest and still rise") pays off, `the_turn` when the book arrives (60 s: `lowest_point`, since two hooks cannot fit after the turn starts), carries `hook_target` hooks (2/2/3/4/6/11 at 60/90/120/180/300/600 s) with the build-up and the product passage before the first hook, fits its delivered length, and FAILS the story-beat check if its first hook is moved up. `song_contract/test_song_contract.py` and `sung_hook/test_no_skip_and_goldens.py` run all six.
- **No gate switches itself off, and the director measures every style by its own rule**: `guard_request` with no `style_id` refuses a sheet with sung or rap sections (`UNMEASURED: style_id`); `check_payload` with no `music_style` is `UNMEASURED: music_style`; `check_returned`/`judge_take` FAIL a `true_at_beat` that is not a beat or is the opening beat, as `check_story` does. The director's words-fit check holds the sung share to the style's own floor (`words_fit.style_sung_target_pct`, the one copy `song_contract.sung_target` reads), and its spelling check reads a held vowel ("re-est", "lo-ook", "mi-ine") as its word while real misspellings are still refused; "n't" contractions join the dictionary extras.
- **FU-U11: book printed pages, the plan hash, the card block and the excerpt seam.** `book_shot.check_pages` / `check_pages_sequence` add the calibrated printed-vs-white page test (`BOOK_BLANK_PAGES`): a page of real body text has no empty grid cell, a white page does (both re-measured from the shipped fixture generator: printed ink 0.1640 with 0 empty cells, white ink 0.0031 with 40 of 48; a page carrying only a caption line sits in the same empty-cell band by design and needs its own fixture to reproduce), and more than one blank page among the sampled open frames fails. `plan_spec` / `plan_sha256` / `plan_card_rows` hash the approved plan and render the card rows; the prompt wording itself lives in the `references/prompt-templates/models/minimax-h3.json` fragments `PRINTED_PAGES`, `BOOK_CLOSED` and `BOOK_OPEN_MOTION`, read by `prompt_templates` (U15b) — this unit authors no prompt wording, it MEASURES the rendered frames. `kie_dispatch.book_shot_refusal` now ACTIVATES the plan-hash requirement U10 shipped dormant — a book video job with no `book_plan_sha256`, or one whose hash does not match the approved plan, is refused `BOOK_PLAN_NOT_APPROVED`. `intake_book` takes an OPTIONAL `excerpt_lines` (client-supplied only, max 3, provenance "provided", spelling-checked with the caption gate's dictionary; it adds no question). Both card faces carry the Book shots APPROVAL BLOCK — approvals and notices only, never a new choice. The excerpt reaches the render as DATA through the single named U9 hook `final_assembler.captions_burn.overlay_excerpt`; no second burn module and no OCR binding was added, and while U9's artifact is absent the call site reports PENDING rather than burning. New test `scripts/core/book_shot/test_book_pages_d1.py` proves all four D1 cases (white fails / printed passes, no-plan refused, changed plan refused until re-approved, excerpt never in the video prompt).
## v2.9.9 - 2026-10-09 - FU-VIDEO-MODEL-CHOICES: four video models, each with a price for your chosen length

- The VIDEO MODEL intake question now lists four models with H3 first and RECOMMENDED: MiniMax H3, Seedance 2.5, Seedance 2.0 Mini, Google Veo 3.1. Each line carries one plain descriptor and "about $X" for the length the client already chose (same formula as the card: video + one keyframe per shot + one song, +20% redo allowance). The recap reads `Video model: Seedance 2.5 - about $68.40`. Seedance is ByteDance's video model (Seedream is image only). Seedance 2.0 Fast is not offered (clip range unconfirmed, not on the price menu); Mini is the lite tier.
- One price for the question and the final card: `card_render.price_envelope` prices the chosen model from the rates table at the resolution the factory renders (H3 768P, Seedance 2.5 720p, Mini 720p, Veo 3.1 Fast 720p), with keyframes, character reference pictures, the song and the 20% redo allowance; the question quotes that exact total. Skill 74 `price` (highest tier) is unchanged for other skills.
- The client's pick is stored in run state at intake (`intake_card.conversation(..., state_store, run_id)`), read by the card's Video model row and by `kie_dispatch`, which submits that model's provider id and resolution (`video_models.request_for_run`, `apply_locked_choice`).
- One rates table with source URL and date: `scripts/core/choice_card/video_models/video_model_rates.json`.
- `prompt_limits.MARKET_ALIASES`: the market id `veo-3-1` is held to the dedicated `veo3_fast` catalog entry; before this, a Veo 3.1 dispatch refused `PROMPT_LIMIT_NO_CATALOG`.
- New test `scripts/core/choice_card/video_models/test_video_models.py` (13 checks: question = card total for 4 models x 60 s / 3 min, pick -> card row and payload, payload tests run through `kie_dispatch.dispatch` with a fake Skill 74; zero paid calls).
## v2.9.9 - 2026-10-09 - Storyboard approval shows each shot's card and its still

- FU-STORYBOARD-SHOWS-BOTH: new `storyboard_director/approval_package.py` builds the approval message with the written card and the still image for every shot, in order; stills come before approval and video after it; approve opens the video gate; a shot edit regenerates and re-sends only that shot. Documented in SKILL.md, choice-card-spec.md and stage-runbook.md.
- Wired into the live run: `storyboard_director/approval_runner.py:run` (via `factory.py storyboard`) sends the message plus each still through `openclaw message send`, records the video stage WAITING_APPROVAL, applies GO / `shot N: change ...`, auto-approves on No, and `factory.py next` withholds the video command until approved. End-to-end test: `test_approval_runner.py`.
## v2.9.9 - 2026-10-09 - FU-SONG-APPROVAL: hear and pick the song before any video

- New intake question 7 of 7, SONG APPROVAL ("Do you want to hear and pick the song before any video is made?"). The card, recap and "number of a line to change it" carry it; the count is now 7 (8 with the saved-character question).
- On Yes the song stage makes three arrangement variants of the same lyric sheet in parallel (`scripts/core/song_choices/`, data table `variants.json`), each judged by `song_dispatch`, a failed one regenerated once then reported; delivered as `SONG-CHOICES/N - LABEL (description).mp3` with title tags and `README.txt`.
- The gate: `factory.py next` and `kie_dispatch` refuse picture timing, image, video and lip-sync work with `SONG_PICK_MISSING` until the client's pick is recorded; a missing or changed pick never defaults. On No nothing changes.
- The card price adds the two extra song generations (`Song picks` row).
- Tests: `song_choices/test_song_choices_fu_song.py`; the H9 and I6 card tests move to 7 and 8.
- Wiring: the confirmed recap writes the SONG APPROVAL answer to the run (`intake_card.conversation(..., run_dir=)` / `factory.py card --step --run-dir` -> `song_choices.record_card_answer`), so Yes turns the gate on without a manual step; a recap change replaces it, a resume keeps it once versions exist. `deliver_choices(..., target=)` / `send_choices` send the message plus the three files in order through `openclaw_send_argv` (`--media`, same `openclaw message send` path as the card). Tests: `song_choices/test_song_wire_fu_song2.py`.

---
## v2.9.10 - 2026-10-09 - FU-SCRIPT-APPROVAL (wired)

- New card question SCRIPT APPROVAL (last question): the client can read and approve the story and song lyrics before the song is made. Yes sends the script and pauses before any song generation; edits are applied, re-checked and re-sent; missing approval fails closed (`SCRIPT_NOT_APPROVED`) in `kie_dispatch.dispatch` and `song_dispatch.run_takes`. No: unchanged.
- Wired, nothing is called by hand: `factory.py next` runs `script_approval.stage.run_stage` when `music` is next and the card answer is Yes (checks, `request_approval`, send through `openclaw message send` or back to the chat, run recorded as waiting, outcome `waiting`). New `factory.py script-reply` carries the client's answer (`approve` or an edit that is re-checked and re-sent). Resume stays waiting and never re-sends a delivered script. The dispatch gates read the record from the run folder (`record_near`, `run_dir=`).
- New `scripts/core/script_approval/` with `test_script_approval.py` and `test_script_wiring.py`.
## v2.9.9 - 2026-10-09 - Client guide

- FU-CLIENT-GUIDE: added references/CLIENT-GUIDE.md (opening, checklist, every question with examples and prep). Docs only.
## v2.9.9 - 2026-10-09 - FU-AI-MODELS-QUESTION

- New first intake question, AI MODELS: which AI builds the video and which checks the work. OpenRouter is recommended (faster), Ollama is allowed, unknown names are refused politely, and the checker must differ from the builder.
- Honest scope: the run still uses the session's own model. The answer is recorded as `ai_models` in the approved intake summary, as a preference for the operator.
- The card now has seven questions (eight with a saved character, which comes second). Tests: `choice_card/intake_card/test_ai_models.py`; card-count checks in `test_intake_card_h9.py`, `test_intake_step_i7.py`, `test_character_library_i6.py` updated.

## v2.9.10 - 2026-10-09 - FU-AAC-FINAL-MUX

- Every delivered video is AAC-LC 48 kHz 256k with +faststart (QuickTime played MP3-in-MP4 silent): new core/delivery_audio.py shared argv constants plus a delivery gate (refuses non-aac or silent audio) wired into final_assembler.assemble and delivery_checklist.delivery_battery(video_path=).

---

## v2.9.8 - 2026-10-09 - Batch MGB018 roll-up

- FU-PARITY: shared files aligned with 999 (v2.7.28 test fixes, delivery_checklist blank lines).
- sfx-f4: the U15 fail-first guards no longer call sys.exit at module level, so one failing guard cannot raise INTERNALERROR across the whole test tree.
- `prompt_templates.book_fragments(spec, st, frag)` is the ONE wording home for a book prompt: it reads `BOOK_CLOSED`, `BOOK_OPEN_MOTION` and `PRINTED_PAGES` from `models/minimax-h3.json` and returns the `book`/`pages` sections both assemblers (`assemble_h3`, `assemble_kling_video`) `.update()`. A shot type that declares `required_blocks_when_book` (product-book) now REFUSES `BOOK_FRAGMENTS_REQUIRED` when the spec does not carry the block, when `book=` is a value the assembler does not know (`closed`/`open` only) or when an open book has no `pages: texture` block — previously such a spec assembled with NO contract wording and PASSed the band. Non-book shot types are untouched.
- Kling no longer scales or trims the fixed `book`/`pages` fragments (`section_scale` 0.38 and `_KLING_TRIM_ORDER` cut the U10 contract sentences in half; design `never_trim` lists `book` and `pages`). The fragments now arrive whole on the Kling path.
- New test `scripts/core/prompt_templates/test_prompt_book_fragments_u15g.py` (26 checks; the (a) refusal checks fail on the base tree).

## v2.9.7 - 2026-10-09 - load-governor test no longer sleeps

- `test_load_governor.py` resets the poll limiter after the fake-clock poll checks. They left it near 1003 s, so the later real-clock polls slept until the machine had been up that long (about 464 s on a fresh CI runner). No check was weakened.

## v2.9.6 - 2026-10-09 - Batch MGB015 roll-up

One version for the MGB015 units: FU-U2 (style-aware length plan), FU-U8 (captions caught early), FU-U15i (docs in lockstep with the prompt). FU-U2 x the scaled CTA cap: a rap style keeps the fixed OUTRO_MAX_WORDS cap and the unspent allowance becomes the rap budget (matches 999 v2.7.29).

### FU-U2: style-aware length plan and words fit

- Style-aware length plan and words fit: `length_formula.plan(L, spoken_share_pct=None, style_id=None)` gives a rap style (R&B Flow, from the style's own `deliveries` in `core/music_styles`) a rap budget for the verses by splitting the D15 spoken-STYLE allowance with the [Intro]/[Outro] spoken block caps, at the calibrated `core/words_fit` rate, and returns `words {spoken, rap, sung}` plus `rap_s`; `words_fit.STYLE_RATES` is keyed by STYLE ID with `rates_for()` normalizing through `music_styles.style()` and `CARD_LENGTHS_S` now re-exports `music_styles.OFFERED_LENGTHS_S` (one copy, gain 120 s); `music_director.build_generate_request` passes `style_id` into `words_fit.preflight_sheet` and `suno_recipe.check_lyric_sheet` passes it into `plan`; Soul Ballad and Soul Rise plans are BYTE-IDENTICAL (65 words at L=60). New test `scripts/core/length_formula/test_style_plan_u2.py`.
### FU-U8: captions caught early (display spellings, intake, the sheet, on-screen text, grammar flags)

- Every string that reaches the screen is now caught before a paid call: `_tokens()` maps U+2019/U+2018 and NFKC-normalises ("could’ve" is one word, not "could"+"ve"); the new `display_text()` turns performance spelling into the caption ("Girl, I got you-u" burns as "Girl, I got you", a wordless vocalise makes no cue) and `build_captions`/`check_captions` use it; `check_lyrics_spelling` refuses a misspelled lyric word with `LYRIC_MISSPELLED` inside `music_director.build_generate_request` BEFORE the recipe guard and any payload; `check_confusables` FLAGS the two confusions a token proves wrong (never a fix); `intake.client_typo_question` sends a client typo BACK AS ONE QUESTION ("Your storyboard says 'kitchan'...") and never rewrites the client's words; `kie_dispatch.onscreen_text_refusal` refuses `ONSCREEN_TEXT_NOT_CHECKED` a keyframe/video whose on-screen text is not in the checked receipt; and `qc_gate` requires a `spelling_grammar` record at the Script stage (new `required_checks`, schema enum, contract updated). New test `scripts/core/test_captions_early_u8.py` (24 checks; 18 fail on the base tree).

## v2.9.5 - 2026-10-09 - Batch MGB012 roll-up

One version for the MGB012 units: FU-U1 (pytest-clean rap-aware tag grammar test), FU-U7 (video/avatar prompt caps at the caller), FU-U15e (Kling avatar template), FU-U15d (Suno V6 templates per style and per length), FU-U15b (H3 assembler and the 5,000-6,800 band), FU-U15f (Kling as the card's video model), U15h (length classes, product seconds, lanes in one table; prompt compliance), and FU-U5 (voice tags come from the cast). Merge notes: suno_recipe is the union of FU-U1's tag grammar and rap rule with FU-U15d's data-driven styles; bible.compile_visual_prompt keeps FU-U10's own-motion kinds on the image path next to U15b's video path; qc_gate.evaluate takes both campaign_type and ledger_jobs. Entries follow.

- FU-U1: `test_tag_grammar_u1.py` is now pytest-clean. `test_b_lyric_gate_counts_rap_in_the_budget` took the sheet as a required argument, so under pytest it ran standalone with no sheet and errored `fixture 'sheet' not found`. It now defaults to `None` and builds the sheet from the fixture itself; a parse failure still fails the check loudly (never a skip). Script mode is unchanged.

- FU-U15d: Suno V6 templates per style and per length (references/prompt-templates/music/*.json, models/suno-v6.json); suno_recipe reads style lead, cues and gender words from data, not constants; no-voice sections render as a tag only; caps are measured last.

- FU-U15e: Kling avatar template (prompt_templates.assemble_kling_avatar / check_kling_avatar): who from the look's mode, three sentences, one emotion.

- Caller-side guards in `kie_dispatch.dispatch`: the FINAL video/avatar payload is measured against the U6 table (`prompt_limits.check_request`) before any other gate, so an over-cap prompt is refused `PROMPT_OVER_CAP` (field, chars, cap, source, status; never truncated) and a paid video/avatar job on an install without the table refuses `PROMPT_LIMIT_UNAVAILABLE`; nothing is reserved, nothing reaches Skill 74, and the ok receipt carries the measured `prompt_caps` rows. Table gains only what the catalogs lack for video: Hailuo family prefix 2,000, `kling-2.6/image-to-video` 2,500, and the Kling 2.5 Turbo `negative_prompt` 2,500 the catalog does not declare. New test `kie_dispatch/test_prompt_cap_u7.py` (fails on the base tree; 5/5 after).


- U15b (H3 assembler, band of record 5,000-6,800): `prompt_templates.assemble_h3/check/expand/receipt` build every MiniMax H3 prompt from the template layers plus the shot spec's facts, guard the owner band (under 5,000 = FLAG then `H3_THIN_SPEC`, never padding; over 6,800 = TRIM; over 7,000 = REFUSE `H3_OVER_HARD_MAX`), and write a prompt receipt (sha256 + template version + section char map). The six golden specs assemble to 5,578-6,740. `shot_planner.prompt_spec_for` writes the facts (`shot["prompt_spec"]`); `kie_dispatch` refuses `PROMPT_NOT_TEMPLATED` when the prompt's sha256 has no receipt or the receipt says REFUSE/TRIM, and re-measures the final payload cap just before spend. The video prompt path carries no square-bracket markers and no generic `[MOTION]` line (`bible.compile_visual_prompt(video=True)`, the three style bibles' `compile_prompt(video=True)`); `assert_compiled` accepts a matching receipt. New `shot-types/villain.json` carries the U16 villain guidance into the assembler. `music_styles` soul-ballad base text ends with a period.

- U15f (Kling as the card's video model, design 3.5): `prompt_templates.assemble_kling_video` builds a Kling prompt in H3's section order scaled by `models/kling-video.json`'s `section_scale` (0.38, per-section budgets `kling_section_limits()` derived from H3's own table, never a second one), aims it into the manifest band (1,800-2,500; hard max 3,072 omni VERIFIED, 2,500 for 3.0/video UNVERIFIED, 2,500 for 2.5 turbo VERIFIED), and differs from H3 in exactly the three ways the design names: the camera is PLAIN WORDS after the subject's motion (no bracket group anywhere), the look is the mode's `kling_block`, and the negatives STAY IN the prompt (no `negative_prompt` field). `check_kling` refuses `KLING_BRACKET_SYNTAX`, `KLING_OVER_HARD_MAX`, banned phrases, duplicate sentences and run-on 8-grams, and flags under-floor `KLING_BELOW_FLOOR`; `band_cap` prints each cap's VERIFIED/UNVERIFIED provenance and never promotes one. The six golden specs re-assembled for `kling-3.0-omni/image-to-video` land at 1,842-2,183, PASS. New test `scripts/core/prompt_templates/test_prompt_templates_u15f.py` (fails on the base tree: no `assemble_kling_video`).

- U15i (docs in lockstep with the template system; last unit of the U15 set): `SKILL.md` gains the "Prompt templates" section (data under `references/prompt-templates/`, the assembler `scripts/core/prompt_templates/`, the H3 band 5,000-6,800 with hard max 7,000, the prompt receipt, `PROMPT_NOT_TEMPLATED`, the `prompt_compliance` gate) and the Suno recipe and lip-sync bullets now point at it. `references/choice-card-spec.md` 3.1 names `references/prompt-templates/length-classes.json` as the ONE length table (its list equals the table's keys) and 3.3 points at `looks/` and `modes/`. `references/style-bibles/realism-cinematic.md` keeps the recipe as the source of the `realism` mode, moves the Chanel identity into a "worked example" heading, deletes the nine "(Restated for emphasis.)" duplicate blocks, and states the camera as per shot. `QC.md` carries the bands, the receipt, `PROMPT_NOT_TEMPLATED` and the required `prompt_compliance` record. ONB SOP `DS-5`/`DS-6` point at the same files. New doc test `prompt_templates/test_docs_u15i.py` (fails on the base tree: no "Prompt templates" section, the restated duplicates still present, the card's 3.3 with no `looks/`).


- U15h (length classes, product seconds and lanes in ONE table; prompt compliance at final QC): `references/prompt-templates/length-classes.json` is CORRECTED so every row equals the code (`length_formula.plan`, `lipsync_clips.budget`, `shot_planner.plan_generation_count` = ceil(D/4), lanes via `lane_planner` when the module is on the tree, the 10-15% product band). The U15a port had drifted at 180/300/600 s (spoken share 16.9/10.1/5.0% before U15d's CTA scale landed; rows now 22.5%) and at 600 s the song plan is `1 base + 3 extends`. `prompt_templates.length_class(L)` is the one reader: it computes the row and raises `PROMPT_LENGTH_CLASS_DRIFT` naming each drifted field, so a stale table can never be read silently. `length_formula.class_check`, `lipsync_clips.class_check` and `shot_planner.class_check` cross-check their own module against the table (never a second formula). `qc_gate` requires a `prompt_compliance` record at final QC: `prompt_compliance_rows`/`prompt_compliance_record` build one row per paid ledger job matched to its receipt (logical_key+attempt_id, else request_digest, else prompt_sha256; REFUSE/TRIM receipts never count), and `evaluate(..., ledger_jobs=[...])` requires the check. `check_product_seconds` proves the shot plan's product seconds fall inside 10-15% of D. New `prompt_templates/test_length_classes_u15h.py`.

- **FU-U5: voice tags come from the cast.** `suno_recipe.check_voice_tags(sheet_text, cast_genders)` refuses a sheet whose voice tag gender disagrees with the cast record (`VOICE_TAG_MISMATCH`, naming both sides) and refuses a character tag whose gender cannot be checked at all (`VOICE_TAG_UNCHECKED`, fail closed); `suno_recipe.guard_request` takes `cast_genders=` and refuses at that seam, and `protected_names.cast_genders(brief)` builds the map from `brief.characters[].gender`. Brackets that name no cast character ([Hook], [Intro], [End]) are never judged; no cast record means the check is off, exactly as today. 2026-10-08 One-Check Chanel as the LIVE cast record has it (the 2026-10-08 voice recast, CAST.md): the BOX COWORKER bracket tagged "Female voice" against a cast that says man is now refused; the desk neighbour "Female" and the manager "Male" tags match the live cast and pass. The plan unit row's own acceptance is also asserted on the pre-recast (plan-time) cast, where the desk neighbour tagged "Female" against a cast that says man is refused. All Suno is unchanged: one `vocal_gender`, same KIE params, no new voice option. Test: `scripts/core/suno_recipe/test_voice_tags_u5.py` (5 of 6 blocks fail on the base tree: no `parse_voice_tags` / `check_voice_tags`, `guard_request` has no `cast_genders`).
## v2.9.4 - 2026-10-09 - Batch MGB010 roll-up

One version for the MGB010 units: TESTHYG-75 (skill 75 tests pytest-collectable and green in one process), FU-U14 (song mp3 part of every deliverable), FU-U10 (book orientation contract), FU-U6 (Suno request limits, fail closed), FU-U15a (template data layer), FU-U16 (story doctrine: villain, pain, rise), U15c (owner prompt band) and qc-kie-docs-host (F14 scanner exempts the docs host only). FU-U1 (rap-aware tag grammar) was held out: its test_tag_grammar_u1.py is not pytest-clean. Entries follow.

## v2.9.3 - 2026-10-09 - Batch MGB009 roll-up

One version for four units that each carried v2.9.2: W-G-003-amend (singing detector aligned to Appendix A), W-G-008 (parallel minute-lanes for ads 120 s and up), W-F-U2 (whole-track retakes only, PARTIAL_SUNO_JOB gate) and FU-U13 (story arc rule and product-connection target). Their entries follow unchanged.

## v2.9.2 - 2026-10-09 - W-G-008: parallel minute-lanes for ads 120 s and up

Owner order (Trevor, 2026-10-08): "this type of intelligence should be built
into skill 75 for all video 2 minutes and up". Reference run wf_9134d15e-b8e
(the fixer split a 3-minute ad into parallel minute-lanes).
- **`scripts/core/lane_planner.py` (new).** Below 120 s of song NOTHING
  changes: one lane, today's flow. At 120 s and up, `plan_lanes(shots,
  song_length_s)` cuts the shot list into N = ceil(L / 60) lanes of about 60 s,
  every cut ON a shot boundary (a shot is never split; an unreachable boundary
  fails closed `LANE_BOUNDARY_INSIDE_SHOT`). Shared steps run ONCE before the
  split (`SHARED_STEPS_BEFORE`: song, song-checker, plan-shot-list, character,
  closeup-picture-gate); each lane makes its own stills, motion clips and
  lip-sync segments AT THE SAME TIME, on the same character, through the
  picture gate, at most 2 lip-sync jobs per segment then the best take, with
  mouth strips. Fan-in runs ONCE after the lanes (`SHARED_STEPS_AFTER`): one
  edit over the full song, one independent checker for the whole ad (hard
  audio-length rule, captions = lyrics, face through the call to action), one
  repair.
- **`SharedGovernor` (one governor across all lanes).** At most 20 NEW
  generation requests per rolling 10 s in total; per-lane share floor(18 / N)
  (3 lanes -> 6 each); every submit rides `load_governor.kie_request`, so a 429
  is backed off and RESUBMITTED, never dropped. Heavy local jobs (ffmpeg) stay
  at most 2 at once across all lanes through the EXISTING machine-wide gate
  (`load_governor.heavy_slot`, re-exported as `lane_planner.heavy_slot`) -- no
  second limiter.
- **Resume and reuse.** `classify_tag(db_path, run_id, logical_key, ...)`
  reads the run's spend ledger: a tag already in the ledger is POLLED, never
  resubmitted; a finished file is REUSED, so a re-run never pays twice; every
  lane plans against the ONE ledger run, so spend stays under the run cap
  across all lanes together.
- Tests: `scripts/core/test_lane_planner.py` (180 s -> 3 lanes on shot
  boundaries; 90 s -> 1 lane; shared governor <= 20 per 10 s across 3 lanes on
  a fake clock with a 429 resubmitted; a ledger-known tag is polled, a
  finished file reused). Boundary battery: 119 stays 1, 120 splits, 179 stays
  3, 180 stays 3.
- Docs: SKILL.md "Parallel minute-lanes" section; the pipeline SOP
  (`23-ai-workforce-blueprint/templates/role-library/video/sops/SOP--drama-song-ad-pipeline.md`
  DS-7 step 6) + `_index.json` content manifest restamp.

## v2.9.2 - 2026-10-08 - FU-U13: story arc rule + product-connection target

Trevor's order: never forget to connect the product to the story, and spend at
least 10-15% of the time connecting the dots to the product and promoting it -
a target, not a hard cap.

- Story arc rule in the lyric/script and shot-plan stages: struggle -> what
  changed -> the product is why -> get the product. The product is named and
  connected in the lyrics AND on screen (cover, title, link), never only on an
  end card.
- `length_formula.plan_product_connection(plan, shots, lyric_lines)`: totals
  product-tagged lyric lines and product-tagged shots, returns seconds and
  percent of runtime, PASS/FLAG against the 10-15% band, plus the spoken-word
  and struggle-motion-shot requirements. The plan carries it as
  `product_connection`; the choice card shows the seconds and percent.
- `delivery_checklist.measure_product_connection(shots, lyrics, runtime_s)`:
  measures the delivered run, reports row `PRODUCT_CONNECTION` in the
  receipt/checklist output with the measured seconds and percent. Outside the
  band is FLAG, never a blocker by itself, never a repair directive.
- Docs: SKILL.md, references/choice-card-spec.md, references/stage-runbook.md,
  QC.md, and the onboarding-only SOP
  (23-ai-workforce-blueprint/.../SOP--drama-song-ad-pipeline.md).
- Test: `scripts/core/length_formula/test_story_arc_u13.py`.
## v2.9.4 (included) - FU-U6: Suno request limits, fail closed, measured last

- New `scripts/core/prompt_limits.py`: one limit table read from the catalogs (`68-kie-audio/models.json` suno-generate: lyrics 5000, style 1000, title 80, duration 10-360; `67-kie-video/models.json` vendor caps per model), plus a skill-75 override table for what the catalogs lack (`negativeTags` 1000 and `kling/ai-avatar-standard` 2500, both stamped UNVERIFIED with source URL and the free docs re-read step). `check_request(model, request)` measures EVERY text field of the FINAL payload and refuses over-cap with `PROMPT_OVER_CAP: field, chars, cap, source, status`; it never truncates.
- `music_director.build_generate_request` now measures the payload AFTER `ending_qc.with_clean_ending` appends the ending to the style (the E.2 order-of-mutation hole: a 1000-char style passed the old guard, the ending pushed it to 1054, and the final style was never re-measured).
- `suno_recipe.build_request` measures its payload too; `song_dispatch.run_takes` compares the request duration with the G9 headroom (`words_fit.max_suno_duration(plan)`) as the plan default allows, while a patch/short duration is still refused.
- Gate registered in `shared-utils/kie_prompt_gates.json`; the shared enforcer is called ceiling-only through the module (the 80 percent floor must not apply: the 67 house floor of 5000 sits above Kling's 2500 hard cap).
- New test `music_director/test_prompt_limits_u6.py` (fails on the base tree: no `prompt_limits` module, 5001-char lyrics, a 1054-char final style and an 81-char title all built).
## v2.9.4 (included) - qc-kie-docs-host: F14 scanner exempts the docs host only

- `scripts/qc-no-direct-kie.sh`: the endpoint pattern `(https?://)?(api\.)?kie\.ai` matched a bare `docs.kie.ai` host, so the KIE documentation provenance URLs in `scripts/core/prompt_limits.py` (added by FU-U6) were reported as direct-KIE calls and the check exited 2 on a clean tree. The scan now extracts each host occurrence (`grep -oE`) and drops exactly the `docs.kie.ai` host — the exemption is decided per OCCURRENCE, so a line carrying both a docs URL and a real api URL still fails on the api record (a line-level `grep -v` would discard the whole line and let the real call escape). Every other host still bites: `api.kie.ai`, any other subdomain including ones nobody has thought of yet, and bare `kie.ai`. No filename exemption: a real direct call added to `prompt_limits.py` later is still caught.
- New test `scripts/core/kie_dispatch/test_qc_docs_host.py` (fails on the base tree: the docs fixture exits 2). Covers the docs citation passing, the api call still failing by name, the mixed one-line docs+api case failing per occurrence, unknown subdomains and bare `kie.ai` failing, and the real core tree staying clean. Existing `test_model_lock_f14.py::test_qc_no_direct_kie` regression stays green.

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
