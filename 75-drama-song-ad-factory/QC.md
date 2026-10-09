# QC Checklist: Drama Song Ad Factory (Skill 75)

## FU-U16 story doctrine: villain, pain, rise

> "People don't care about the hero until they meet the villain." - Trevor Otts

These are not music videos: compelling true stories; the pain AND the rise.
Check on every run:

- The story plan names its VILLAIN (person or not a person: cancer, debt, a
  layoff, a lie, burnout, fear, the inner critic, a system).
- The villain has its OWN shots tagged `villain` (or `villain_visibility`
  outside `none`) - `length_formula.plan_villain_doctrine` fails CLOSED (never
  a pass) when no villain is named or the villain has no shot. Those two are
  the only hard cases.
- Pain share of runtime inside the 20-35% target band; outside is a FLAG in
  the receipt with the measured seconds, never a block.
- The `VILLAIN_DOCTRINE` row (`delivery_checklist.measure_villain_doctrine`)
  reports villain shots, villain screen seconds, pain seconds, rise seconds.
  Evidence only: it never joins repair_scope.
- The rise is earned: pain gets real screen time, the turn names the product
  as the key, the rise is never rushed.

## Prompt templates, bands and the prompt_compliance gate (U15i)

The docs and the code must agree on what a paid prompt is. This section is the
QC side of the template system (design file 20, section 8); the data and the
assembler are in `references/prompt-templates/` and
`scripts/core/prompt_templates/prompt_templates.py`.

- **MiniMax H3 band (Trevor, 2026-10-08): 5,000-6,800 characters**, hard max
  7,000. Under 5,000 = FLAG `H3_BELOW_FLOOR` then expand from the spec's own
  facts (never padding), and `H3_THIN_SPEC` when the spec has no facts left;
  over 6,800 = TRIM in the documented priority order; over 7,000 = REFUSE
  `H3_OVER_HARD_MAX` before any spend. `prompt_templates.check()` returns the
  band verdict; nothing is ever truncated.
- **Prompt receipt.** Every assembled payload returns a receipt
  (`prompt_sha256`, the template version, the per-section character map, the
  band verdict and the caps with their status). A paid job whose prompt hash
  has no matching receipt, or whose receipt says REFUSE or TRIM, is refused
  `PROMPT_NOT_TEMPLATED` by `kie_dispatch` before the ledger. This is the same
  pattern as `LIPSYNC_PICTURE_NOT_GATED`.
- **`prompt_compliance` is REQUIRED at final QC.** `qc_gate` builds one row per
  paid ledger job matched to its receipt (`prompt_compliance_rows` /
  `prompt_compliance_record`) and the final gate refuses a stage when the
  record is missing: a paid prompt with no receipt never passes.
- **One length table.** `references/prompt-templates/length-classes.json` is
  the only table; `prompt_templates.length_class(L)` raises
  `PROMPT_LENGTH_CLASS_DRIFT` naming each drifted field, so a stale table can
  never be read silently. The card's 3.1 list equals that table's keys.
- **No padding, by checker.** No repeated sentence of 40 characters or more,
  at most 4% repeated 8-word runs, and none of the banned phrases
  (`Restated for emphasis`, in-prompt `[compiled:`, `[STYLE]`, `[/STYLE]`,
  `[SHOT:`, `[MOTION]`). Square brackets are reserved for the camera command:
  exactly one bracket group, 1-3 moves.

## 1. Purpose
Enables the agent to produce a complete drama-song ad (twelve-stage sung
direct-response story -> storyboard -> clip generation -> assembly ->
delivery) through the shared Python control layer (intake, preflight,
spend ledger, state store, QC gates), with independent per-stage QC against
the build directive's **section 17 evidence gates**. API success is not
quality success: every material stage must carry recorded QC verdicts before
it advances. Standard library only; no credential value is ever printed.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `EXAMPLES.md`, `QC.md`,
      `DEPENDENCY-MANIFEST.md`, `THIRD_PARTY_NOTICES.md`, `skill-version.txt`,
      `references/`, `scripts/core/`, `tests/`.
- [ ] `scripts/core/contracts/` contains `campaign-schema.json`,
      `artifact-schema.json`, `qc-schema.json` and all parse as valid JSON;
      `qc-schema.json` verdict enum is exactly PASS / FAIL / UNAVAILABLE and
      requires `reviewer.identity`, `reviewer.session`, `reviewer.authority`.
- [ ] `scripts/core/acceptance-profile.json` parses, carries
      `profile_version`, and its `verdict_rules` state: UNAVAILABLE values
      list, `cta_unavailable_cannot_pass: true`,
      `aggregate_may_not_erase_critical` (identity, lyrics, offer, claim,
      product_label, cta), `threshold_changes_require_documented_decision: true`.
- [ ] The four implemented CLIs exist and `--help` works:
      `intake_preflight/factory.py` (intake|preflight), `spend_ledger.py`
      (init_run/plan/reserve/mark_unknown/cancel/mark_submitted/
      mark_terminal/reconcile/summary/can_spend/park_run/unpark),
      `qc_gate.py` (evaluate), `job_recovery.py` (ingest_event/
      record_result/recover).
- [ ] `state_store.py`, `timing_guard.py`, `artifact_graph.py`, `cc_sync.py`
      are import libraries (no CLI) - documented as such in EXAMPLES.md.
- [ ] `delivery_verify.py` / `release_check.py` are NOT present and are
      never claimed anywhere in the docs.
- [ ] `skill-version.txt` matches `SKILL.md` frontmatter `version`.
- [ ] No real credential value appears anywhere in the skill files.

## 3. Dependency Checks
- [ ] TYP (Skill 01) and BYUP (Skill 02) installed first (repo law).
- [ ] python3 with standard library only; `shutil.which` used for tool
      presence, `importlib` for module presence - never executing a tool
      during preflight.
- [ ] Provider helper skills (66 image / 67 video / 68 audio / 74 transport)
      are NOT bundled in this folder; a missing helper must surface as
      `tool-unavailable` / `module-unavailable` (exit 1) naming it - never a
      silent substitution and never a weakened check.
- [ ] CC / Command Center connectivity is optional at install; `cc_sync`
      degrades to a durable outbox, never drops board events.

## 4. Functional Checks (run from the skill folder)
- [ ] Thin brief:
      `python3 scripts/core/intake_preflight/factory.py intake --brief '{"offer": "demo offer"}'`
      exits 2, `missing-essentials`, exactly 3 questions in one message.
- [ ] Complete brief exits 0, `complete-brief-zero-questions`, returns a
      16-hex `digest`; `auth_status` is `missing` without an auth object.
- [ ] Injection text in a brief (`ignore all previous instructions`)
      exits 4, `untrusted-injection-blocked`, and does not touch auth.
- [ ] Resume trio: no change -> 0 `resume-no-changes`; budget change -> 3
      `resume-approval-invalidated`; outstanding decision -> 2
      `resume-outstanding-decisions` (questionnaire not re-run).
- [ ] `preflight --root <dir>` with no `--auth-file` exits 4
      `approval-missing`; with auth bound to the digest, credential present
      and tools found, exits 0 `preflight-pass` and `data.checks` shows
      schema/profile/references/storage/disk/tools/credentials all true.
- [ ] Refusal battery: wrong digest -> 4 `approval-out-of-scope`; unknown
      profile -> 4 `delivery-profile-unknown`; missing tool -> 1
      `tool-unavailable`; unset credential -> 4 `credential-missing`
      (presence only, value never echoed); reference outside root -> 4;
      reference missing -> 1; untrusted schema -> 1 `schema-untrusted`.
- [ ] Song files (H14): a delivery folder holds `<ad>.mp3` (320 kbps) and `<ad>.wav` (plus
      `<ad>-instrumental.*` if one exists), all listed in `delivery-receipt.json` and `README.md`;
      `python3 scripts/core/delivery_variants/song_files.py check <dir> <ad>` exits 0, and exits 5 when any song file is missing.
- [ ] Three audio versions (DEL-01): the same delivery folder holds `01 - Full Song.mp3`,
      `02 - Instrumental.mp3` and `03 - Voice Only.mp3` (320 kbps each, from the run's own mix,
      instrumental and vocal stem) plus `00 - About These Audio Files.txt`, the short plain-English
      note on how the three differ; all listed in `delivery-receipt.json` and `README.md`;
      `python3 scripts/core/delivery_variants/song_files.py check-versions <dir>` exits 0, and exits 5
      when a version or the note is missing. A missing source is a refusal, never a two-version delivery.
- [ ] Song mp3 in the deliverable (FU-U14, REQUIRED): the ad folder holds `<Author> - <Title> - Song.mp3`
      (320 kbps, the exact song used, full length; the wav too when one exists) beside the captioned and
      clean-master mp4s. `delivery_checklist.check_song_mp3(<ad_dir>, <ad_audio>, <Title>, <Author>)` returns
      PASS rows `SONG_MP3_FILE` / `SONG_MP3_DURATION` / `SONG_MP3_CORRELATION` — duration within 0.1 s of the
      ad's audio and cross-correlation >= 0.95 with it. A missing or mismatched mp3 is a FAIL (fail closed).
      Run: `python3 scripts/core/delivery_checklist/test_song_mp3_u14.py`.
- [ ] Batch zip (FU-U14): a finished book/batch campaign ships one zip per client,
      `batch_zip.build_batch_zip(client, ads, out)` — one folder per author with the captioned ad, the clean
      master and the song mp3 (exactly three files per ad) plus a README listing every file, duration,
      resolution and banner link. A missing file is a `BatchZipError`.
- [ ] Spend ledger: `init_run --ceiling` recorded; `reserve` before
      dispatch; duplicate `reserve` exits 5 `BAD_TRANSITION`;
      `can_spend` past ceiling exits 5 `BUDGET_EXCEEDED`; `park_run` exits 4
      and then `can_spend` exits 5 `RUN_PARKED` until operator `unpark`.
- [ ] `qc_gate.py evaluate` exits 0 only when every required check passes
      with an independent reviewer; see section 5 for the gate matrix.
- [ ] `job_recovery.py`: duplicate event -> `DUPLICATE_EVENT`; out-of-order
      -> `STALE_SEQ`; `recover` returns POLL plans with
      "no job re-dispatched"; unknown run -> exit 1 `NO_SUCH_RUN`.
- [ ] EXAMPLES.md command list contains ONLY these implemented commands.

TODO (U4): FU-U4 adds intake modes (`--brief-file`, `--packet-file`,
`PACKET_REQUIRED_IN_CONCEPT_MODE`); refresh the functional checks above when it
lands.

## 5. Section 17 Evidence Gates (the production QC contract)
Every row below is a directive section 17 gate. Verdicts are recorded as
qc-schema records and enforced by `qc_gate.py evaluate`; the gate is
fail-closed: missing record, UNAVAILABLE, self-review, stale binding or
schema violation all refuse the stage (exit 5).

| Gate | Directive | Required `check` id(s) | What the evidence must show |
|---|---|---|---|
| Creative QC | 17.1 | `creative` | audience specificity, emotional stakes, twelve-stage logic, failed-solution credibility, mentor timing, product reveal timing, objection/doubt, transformation clarity, vindication/callback, CTA quality, factual/claim safety |
| Song QC | 17.2 | `song`, `lyrics` (critical) | all required lyrics present, no omitted sales lines, no meaning-damaging ad-libs, understandable + correct product pronunciation, singer/persona continuity, genre/style and tempo continuity, no clipping, no broken transitions, sufficient master duration |
| Storyboard QC | 17.3 | `storyboard` | lyric match, emotional expression, character reference correctness, wardrobe, location, product timing, composition, visual variety, generatability, adjacent-shot continuity |
| Video QC | 17.4 | `video`, `continuity` | MULTIPLE frames inspected (not frame zero only): correct character, face/body continuity, wardrobe, location, product appearance, physical plausibility, motion coherence, camera intent, no unwanted text, no warped hands/faces/objects, no temporal artifacts, lyric match, start/end continuity, no accidental lip movement in non-speaking shots |
| Final edit QC | 17.5 | `final_edit`, `export`, `timeline`, `audio`, `text_product` (critical) | audio/video duration vs profile, master no longer than chosen length minus 2 seconds (`core/master_length`, reason `MASTER_TOO_LONG`), sync to lyric timing, no gaps/frozen/black frames, no missing assets, caption correctness when enabled, packshot correctness, CTA readability, audio levels, final format/resolution, required aspect ratio, complete manifest/receipts |
| Product connection (FU-U13) | 17.5 | `final_edit`, `delivery` | story arc rule: struggle -> what changed -> the product is why -> get the product; the product is named in the lyrics AND on screen (cover, title, link), never only on an end card. `delivery_checklist.measure_product_connection` reports the measured seconds and percent of runtime connecting story to product (row `PRODUCT_CONNECTION` in the checklist output). 10-15% of runtime is a TARGET: inside is PASS, outside is FLAG with the measured numbers, never a blocker by itself and never a repair directive. |
| Independent verifier law | 17.6 | all | reviewer identity differs from the maker binding; `reviewer.session` and `reviewer.authority` present; same records re-submitted unchanged cannot pass (`MAKER_SELF_REVIEW` observed exit 5) |
| Targeted repair | 17.7 | failing check only | gate returns `repair_scope` naming only the failed `check_id`s; repair runs with new attempt ids; approved assets stand; repair cost travels through the ledger `repair-cap`, and once the configured budget is spent the run PARKS - never an unbounded retry loop |
| Acceptance profile + UNAVAILABLE | 17.8 | `timing` (profile-bound) | `--profile acceptance-profile.json --expect-profile <version>` matches or the gate refuses `PROFILE_MISMATCH`; UNAVAILABLE on any required check = `UNAVAILABLE_MANDATORY`, never PASS; a `timing` record carries `timing_detail` {sample_ref, confidence, annotation_method} plus median/p95/critical ms against profile thresholds (100/250/100 ms baseline); export 1080p30 H.264+AAC 48 kHz, A/V duration delta <= 1 frame, lyric coverage 100% critical / >= 98% overall, loudness -14 LUFS +/-1 and true peak <= -1 dBTP, CTA hold >= 3 s reviewed at 360 px width; threshold changes require a documented decision before the affected run |
| Claims / narrative integrity | 17.9 | `creative` + `text_product` | factual product claims carry evidence refs from the brief into the QC record; fictional/simulated narrative is distinguished from real testimonials; original assets and provenance preserved; resemblance or third-party spend anecdotes are never reported as effectiveness evidence |
| Protected names + captions (H7) | 17.2, 17.5 | `lyrics`, `song`, `text_product` | the sheet keeps every protected name (character/brand) and every packet line verbatim (`PROTECTED_NAME_CHANGED`, `PACKET_LINE_REWRITTEN`); no take where a protected name was sung wrong (`PROTECTED_NAME_SUNG_WRONG`); caption text equals the approved sheet word for word and was never speech-to-text (`CAPTION_MISMATCH`, `CAPTION_SOURCE_NOT_SHEET`); "still" for "Stale" fails |

- [ ] Critical checks (`lyrics`, `text_product` by default, overridable via
      `--critical`) produce `critical_failures` on any FAIL/UNAVAILABLE, and
      no aggregate average is ever computed across them.
- [ ] An aggregate may not advance a stage: gate PASS requires EVERY
      required check to carry an independent PASS record.
- [ ] Every production run publishes its `acceptance-profile.json` BEFORE
      generation; a campaign target may deviate only with a documented
      alternative recorded in the profile.

### 5.1 Master provenance (Part H H12)

Run `check_master_provenance(<run folder>, <master>)` from
`final_assembler/master_provenance.py` and record it as the `final_edit`
check. FAIL when the master has no assembler receipt (`produced_by.module`,
`master_sha256`), or any run-folder script calls ffmpeg or writes captions.
Builders call the skill's assembler, lip-sync and caption modules, never
their own scripts.

## 6. Cost / No-Double-Spend Checks (directive 18, enforced with section 17)
- [ ] Every paid submission has a prior `reserve` and a later `reconcile`
      to actual cost, within the run ceiling recorded by the operator.
- [ ] Unknown provider outcome -> `mark_unknown` + `recover`/POLL; a
      resubmission attempt on an uncertain job is a FAIL, not a retry.
- [ ] `summary` reconciles: committed + actual + remaining == ceiling, per
      stage costs present, `run_status` accurate.

## 7. Security Checks
- [ ] No credential value printed, logged, committed or echoed; preflight
      reports presence booleans only (`credentials_present`), and this QC
      checklist itself never greps a secret value into output.
- [ ] No client names or identifying strings anywhere in the skill files
      (repo guard: `scripts/qc-assert-no-client-names.sh` must PASS).
- [ ] No instruction-override text is treated as authorization anywhere in
      the flow (intake rejects it; preflight requires the auth object).

## 8. QC Score
Score this skill from **0 to 10** after running the checks above.
- **10/10**: installation, dependency, functional, section-17 gate, cost and
  security checks all pass with no ambiguity.
- **8-9/10**: core behavior works; one or two non-critical items need cleanup.
- **6-7/10**: basic install exists; a meaningful validation or behavior missing.
- **0-5/10**: missing prerequisites, broken verification, wrong secrets
  handling, or failed functional tests.
- Record final result here:
  - **QC Score:** ____ / 10
  - **Status:** Pass / Needs Fix / Blocked
  - **Notes:** ____________________________________________

## 9. QC Loop Rule
Run at most **5 total QC/fix rounds** for this skill. After each failed
round: record which items failed, apply the smallest fix, re-run only the
failed checks. After the 5th failed round, stop and escalate to the owner.
A maker never signs its own gate: the final verdict for any production
stage comes from an independent reviewer, and this document is never used
to self-approve a run.

## Part H H4: speaking faces and lip-sync coverage

- Run `shot_planner.face_speaks.check_face_speaks(shots, lines)`: it lists every
  shot where a face is visibly speaking (shot / time / line / lip-sync). Any
  speaking face that is not a lip-sync clip of that character's own line fails
  `FACE_SPEAKS_NO_LIPSYNC`; a lip-sync clip whose speaker is not on screen fails
  `LIPSYNC_WRONG_FACE`.
- Run `face_speaks.check_coverage_band(ad_length_s, lipsync_s, lines)`: 30-40 s
  and 6-8 clips of 4-6 s in a 60 s ad (doubled 2026-10-08), scaled linearly with
  length, with a 5-point grace; below the band or under the clip count fails
  `LIPSYNC_COVERAGE_BELOW_BAND`. The planner (`plan_lipsync_lines`) picks the
  lines (every sung hook, the spoken opener and closing first, each cut to 6 s).
- Lip-sync source pictures: every one passes `lip_gate.image_gate` before any
  paid lip-sync job (its close-up numbers are `picture_gate`'s, one rule set); a
  refusal lists every `LIPSYNC_IMAGE_*` reason and a measurement that could not be
  made is a refusal, never a pass.
- LPG001/LPG002/LPG003: the measured close-up gate is enforced IN the dispatcher
  (`kie_dispatch.lipsync_picture_refusal`): any kling/ai-avatar job (or a manual infinitalk job) without a
  PASS or ACCEPT_WITH_FLAG `picture_gate` receipt (sha256 of the exact image, numbers and
  flags recorded), or whose `input.image_url` is not the bound upload of those exact bytes
  (`picture_gate.upload_measured`), is rejected `LIPSYNC_PICTURE_NOT_GATED` before the
  ledger. FAIL = clear problems only: face count not 1, face height < 20% of frame,
  |roll| > 20 deg, |yaw| > 0.25 (side profile), jawOpen > 0.30, sharpness < 60. Smile,
  teeth, a face under 25%, |roll| > 5, |yaw| > 0.12 and sharpness < 100 are FLAGS
  (ACCEPT_WITH_FLAG), never a failure and never a paid regeneration. QC fails a run whose
  close-up receipt is missing or FAIL. mediapipe or the pinned face model missing =
  refused (install: `python3 scripts/core/lip_sync/lip_gate/install_face_model.py`).
- LPG003 F14: the locked lip-sync model `kling/ai-avatar-standard` is not a menu video
  model; `dispatch` lets it past the F14 video lock and holds it to the picture gate
  instead. Every other off-menu video model is still `MODEL_NOT_ON_MENU`.

- Lip-sync sync check (looser, sung-aware, LSL002): `lip_gate.measure_file` / `judge`
  run the validated `sync_check` measurement (mouth vs voice, lag +-10 frames, clip cut
  to the audio length, chance test by rolls, repeated-hook lines dropped, corr floor
  0.40, margin floor 0). SYNCED = PASS; WEAK = ACCEPT_WITH_FLAG (used, flag in the
  receipt row); NOT_SYNCED = FAIL on a spoken line; on a SUNG line WEAK and NOT_SYNCED
  are UNDETERMINED: held for a person to look at a mouth strip, no automatic paid
  redo. UNMEASURABLE and UNDETERMINED fail `lip_gate.qc_check` until a person writes
  `person_verdict: PASS` on the row. Controls: `lip_sync/lip_gate/calibrate_sync.py`.
  `lip_gate/event_sync.py` is ADVISORY (`advisory_event_sync` in the row), never gating.
- Two-try rule (Trevor 2026-10-08): at most 2 paid `kling/ai-avatar-standard` jobs per
  segment, every name variant counted; try 2 only on a person's call (a defects file or
  `person_verdict` "DEFECT") with a changed input, never on a checker verdict; then the
  best take is kept with a `KEPT_BEST_OF_2 (tN)` receipt row, its numbers, flag and
  mouth-strip path. `lip_gate.qc_check` accepts such a flagged row and rejects a
  segment with more than 2 jobs. InfiniTalk is a manual backup only, never automatic.
- Lip-sync process (LSP001, Trevor approved 2026-10-08), what QC checks: (1) reuse first:
  a segment with a usable take on disk has no new paid job in the ledger; (2) a sung line
  the checker cannot confirm is tagged `KEPT_BEST (UNDETERMINED, sung)`, a borderline
  spoken line is kept and flagged; (3) every UNDETERMINED or flagged row carries a
  mouth-strip path (`<delivery folder>/mouth-strips/<segment>.png`) and the receipt lists
  them for a person; (4) every second paid job traces to a person-marked defect, a
  changed input and fewer than 2 prior jobs; (5) clips are trimmed to audio length, placed
  at the Suno time corrected by the stem offset, lanczos-upscaled to 1080x1920, conformed
  by dropping frames (no minterpolate) through `load_governor`; (6) rows list the take
  kept, jobs used (n of 2), verdict and numbers, flag and strip path, and
  `lip_gate.qc_check` accepts `KEPT_BEST` and flagged rows that carry a strip path.

## Clean ending (I5)

The last 2 s of the master must not stop abruptly: audio level decays, the last sung word
is not cut, the picture fades to the end card, and the end card (4-5 s) ends by target
length minus 2 s. Check: `scripts/core/ending_qc/` (`check_ending`).

## I1: caption spelling and website

Every caption word must be a real word or a protected word (names, brands, the
client's website). An unknown word fails with the word shown
(`CAPTION_MISSPELLED`). When the ad sends people to a website, intake asks for
the exact address; it is stored as a protected word and must appear verbatim in
the lyrics, captions and end card (`WEBSITE_NOT_VERBATIM`).

## H10 voice fits the character on screen (Part H)

Run `qc_voice_match/line_voice_fit.py` (`enforce`) before assembly. Each line is measured inside the vocal stem (median pitch of its voiced frames) against the declared voice band of the character whose face is shown. Distance outside the band, as a percent of the nearest edge: up to 5 accept; over 5 up to 10 accept with a flag in the receipt; over 10 is `VOICE_FACE_MISMATCH` and that take is regenerated (never keep the closest). The receipt carries `median_hz`, `band_hz`, `deviation_pct` and every attempt per line. A line still failing after the regeneration rounds rejects the run.

## Lyric sheet, request limits, captions and books (U12; what main checks)

TODO (U3, U9): refresh the band bullet and the caption bullet below when FU-U3 (per-style spoken bands) and FU-U9 (burned-caption readback) land.

- **One tag grammar.** The sheet is parsed once (`suno_recipe`); a lyric line under an unclassifiable tag is `UNTAGGED_LYRIC_LINES`. Rap is counted in the word budget and allowed only for a rap style (R&B Flow). A character tag whose gender disagrees with the cast record is `VOICE_TAG_MISMATCH`; one that cannot be checked is `VOICE_TAG_UNCHECKED`.
- **Request limits.** `PROMPT_OVER_CAP` (field, characters, cap, source, status) for Suno lyrics 5,000, style 1,000 (measured after the ending is appended), title 80, `negativeTags` 1,000 (UNVERIFIED), and for every video and avatar prompt at dispatch; `PROMPT_LIMIT_UNAVAILABLE` when a paid job has no limit table. Nothing is truncated.
- **Captions early.** `LYRIC_MISSPELLED` before any Suno payload; `ONSCREEN_TEXT_NOT_CHECKED` before any keyframe or video; the Script gate requires a `spelling_grammar` record. Captions burn the display spelling ("Girl, I got you"), not the performance spelling ("you-u").
- **Captions at the end: UNMEASURED on main.** Reading the burned text back off the frames (FU-U9) is not built. Report delivery caption text as checked against the approved sheet only.
- **Book campaigns.** The shots stage requires a PASS `book_orientation` record (`BOOK_MIRRORED`, `BOOK_COVER_NOT_FRONT`, `BOOK_SPINE_WRONG_SIDE`, `BOOK_WRONG_DIRECTION`, `BOOK_NO_MOTION`; UNAVAILABLE never advances; the checker must pass its calibration pair). `BOOK_SHOT_NOT_CONTRACTED` for a book video job with no start frame from the cover file. FU-U11 (open branch) adds `BOOK_BLANK_PAGES` and `BOOK_PLAN_NOT_APPROVED`; refresh this line when it lands.
- **Per-style spoken bands.** FU-U3 (open pull request) judges R&B Flow against its planned share and counts music-only time as neither sung nor spoken; Soul Ballad and Soul Rise stay at 22.5 / 77.5. The 5/10 band and the 6 s sung stretch do not change.
