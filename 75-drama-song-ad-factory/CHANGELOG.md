# Changelog - drama-song-ad-factory (Skill 75)

All notable changes to this skill are documented here. The version of
record is `skill-version.txt` (kept in agreement with the `SKILL.md`
frontmatter `version:` field).

## v2.9.126 - 2026-10-27 - chore(batch-20261027-0211): version stamp for S75-T04

- **Batch 20261027-0211 version stamp, skill 75 v2.9.125 -> v2.9.126.** S75-T04 (`s75/S75-T04-r6-stage` @ `c027f419`) is the only unit in this batch touching skill 75. No skill code changed in this commit; version stamp only.

## v2.9.116 - 2026-10-26 - G3 re-bump: S75-T11, S75-T16, S75-T17, S75-T26, S75-T36 batch

- **G3 re-bump only.** Main advanced its own `skill-version.txt` to v2.9.115,
  the same value this branch had already taken, so after the branch was brought up
  to date with main the bump no longer appeared in the diff against the merge base
  and the G3 guard ("skill content change requires skill-version.txt bump") failed.
  This patch raises the version to one level above main (v2.9.116) so the bump is
  visible to G3. No skill code changed in this commit.

## v2.9.115 - 2026-10-26 - G3 re-bump: S75-T21, S75-T34, S75-T39 batch

- **G3 re-bump only.** Main advanced its own `skill-version.txt` to v2.9.114, the
  same value this branch had already taken, so after the branch was brought up to
  date with main the bump no longer appeared in the diff against the merge base
  and the G3 guard ("skill content change requires skill-version.txt bump") failed.
  This patch raises the version to one level above main so the bump is visible to
  G3. No skill code changed in this commit.

## v2.9.114 - 2026-10-26 - S75-T21, S75-T34, S75-T39 batch

- **S75-T21 — music styles: Pop Rock, Reggaeton and Country Rap recipes.** Three
  style recipes land on the current main (r2), with a deterministic recipe test
  file and the attempt-1 artefact amended with the resolved head. `suno_recipe`
  carries the recipe parameters through to the Suno createTask contract.
- **S75-T34 — supervisor policy adapter.** Detect, stop, isolate, reconcile and
  activate across a bounded policy surface, with 100+ deterministic cases.
- **S75-T39 — one hygiene facet per repository event, never a global sweep.**
  Facet dispatch routes a single event to a single facet, with its own
  deterministic test file.
- The same diff also carries **S75-T16** — the character-library sync protocol
  (ids, bounded retry, revisions, conflicts, offline snapshots) and its 31
  deterministic cases.

## v2.9.114 - 2026-10-25 - Drama-to-Demand upgrades recorded (no behaviour change)

Version pair moved `v2.9.113` -> `v2.9.114` so the release record matches the
code. This release edits only `skill-version.txt`, the `SKILL.md` version field
and the two documents that record behaviour; no product file changed. The
behaviour below already ships in the `v2.9.111`-`v2.9.113` line, which carried
batch version bumps with no changelog entry, so this is the first entry since
`v2.9.110`.

What a client or an operator sees:

- **The card opens by asking what the video is for.** A new run asks one plain
  question per message, starts on that question, offers the budget the client
  already gave in the brief as the recommended option, and reuses a saved
  character by name instead of asking again. No client-facing question uses
  screenwriting or method jargon. A resumed project replays exactly the
  questions it already answered and its approved files are untouched.
- **Three real opening choices, not one tame line.** The reference library
  holds four worked example sets; each shows three genuinely different
  openings for the same business - a different kind of crisis, a different
  question, a different first line - and every candidate spells out the spoken
  first line, the headline, the first thing the viewer sees, the question it
  opens, why that audience cares and how the story connects to the actual
  offer. The strongest for shock, curiosity and relevance is recommended, and a
  counterexample table shows tame openings rejected. Fiction may invent a
  dramatic event again; an invented event is still refused when it would be
  presented as a verified fact about a real person or product.
- **The story may open on the consequence without losing its spine.** The
  twelve beats keep their ids and their true cause-and-effect order; how they
  are told is declared separately, and the script, the performed lines and the
  shots must all agree with the declared order. Every beat still states its
  action, its change, what the viewer now understands, the question it leaves
  open and who carries it.
- **Every musical turn says why and what the viewer hears.** The spoken hook,
  the first singing at the drop, the hero shift and the earned solution hook
  each carry a written reason and the intended audible change (from, to,
  rhythm, emotional direction, vocal). A chorus that arrives before the story
  has earned it is refused.
- **The purpose the client chose decides which rules apply.** A lesson,
  testimonial or sales run is judged by its own purpose's rules and the purpose
  is never guessed from the script's words. Every supported launcher (text,
  telegram-json, openclaw-json, Studio) records the purpose and the planned
  gates in `control/method.json` for a new run.
- **The approved opening actually reaches the film.** The approved opening line
  and the first visible action are carried into the generated scene plan and
  the shot order; an opening image that could be read two ways is refused until
  the intended reading is recorded.
- **Mouth-shape clips stay inside the policy.** 25-30% of the ad length
  targeted, 35% hard maximum, clips 4-6 seconds, never fewer than three, and
  the first 12 seconds clearly articulated. A request that cannot satisfy all
  of that is surfaced, never silently changed.

Provenance: S75X-W1 (opening coaching, opening candidates), S75X-W2
(presentation order, blueprint turns), S75X-W3 (recorded purpose reaches the
story check and every launcher), S75X-W4 (opening scene, blueprint music
request, lip-sync policy). The accepted tests for all four pass on this tree:
`test_opening_flow_default_s75x.py`, `test_presentation_order_u1.py`,
`test_method_plan.py`, `test_factory_card_purpose_w3u2.py`,
`test_stage_purpose.py`, `test_opening_scene_w4.py`,
`test_blueprint_inputs_s75xw4u2.py`, `test_lipsync_clips.py`.

## v2.9.110 - 2026-10-24 - governed production admission

Production entrypoints and paid dispatch require authoritative intake, the
validated canonical predecessor graph and current artifact approval scope.
Manual authorization/four-pick JSON and manually initialized stage rows cannot
grant production admission. Paid requests are rechecked before submission;
offline runner receipts remain explicitly non-authoritative.

Initial research and planning work without future media dependencies or unseen
artifact approvals. Current revision-aware legacy approvals remain supported;
unverified evidence is preserved behind a specific hold. Script/lyrics, song
selection and storyboard package gates retain their intended timing. Question
text, creative dramatization and lip-sync policy are unchanged.

## v2.9.109 - 2026-10-24 - explicit router roles and free run-state handoff

The AI catalog accepts the existing configured deepseek-chain alias literally.
Each confirmed intake binds its own selected builder and checker; repair uses
that checker. Existing bindings and attempt evidence are preserved. Conflicting
or unavailable dispatches refuse instead of selecting another provider or model.
No client's chain members or global model defaults are changed.

Confirmed intake initializes missing canonical stage rows through Store.init_run
without rendering or provider calls. Existing run IDs, stage statuses, approvals
and saved answers remain intact. The pending-stage plan exposes admitted worker
identities separately from proof of an actual call. Router-member execution is
not claimed without supported evidence.

Run-bound card calls use the durable flow even when --step is omitted; explicit
Studio exports and unbound previews retain their existing behavior. The four
legacy CI fixtures now render and confirm individual turns against real store
schemas while preserving script/song approval and delivery-target assertions.

## v2.9.108 - 2026-10-24 - durable intake bound to the exact rendered questions

Intake now persists every raw client answer with its source and exact rendered
question/options before advancing. Separate CLI calls resume the saved question;
unknown options, mismatched or revised menus, and incomplete intake refuse to
advance. Explicitly sourced prior facts can be reused without importing guessed
choices or remapping old menu numbers. Recap confirmation remains separate from
approval of the actual script, complete storyboard, or selected song.

The chosen video provider route is saved in the existing run model lock. Both
ordinary and campaign intake use the canonical six durations, including 120
seconds. Existing question text/order and retained descriptions are preserved;
the authorized Agnes supplement explains both Agnes and KIE.ai, costs and limits.
The Studio question snapshot follows the renderer. Legacy bulk Studio replies
without question provenance fail closed; no service deployment is included.

Focused offline CLI, state, duration, model and approval checks accompany the
change. Existing creative, opening, soundtrack and lip-sync policies are retained.

## v2.9.107 - 2026-10-24 - MiniMax H3 restored as the card's recommended video model

Commit 9f7bb25c3 removed MiniMax H3 from the VIDEO MODEL question on the
claim that "the live catalog never carried MiniMax H3". That claim was
false: `74-kie-live-adapter/references/kie-model-registry.json` carries
`minimax-h3/image-to-video` (8 credits/s = $0.04/s at 768P, 4-15 second
generations), and KIE lists it at `kie.ai/minimax-h3`. The card had been
rendering `1. Hailuo 02 Standard (RECOMMENDED)` with H3 nowhere.

H3 is restored as row 1 with `recommended: true` at its existing registry
rate, and the false `source_note` is corrected. The question order is again
1 MiniMax H3 (RECOMMENDED), 2 Seedance 2.5, 3 Seedance 2.0 Mini, 4 Google
Veo 3.1; Hailuo 02 Standard stays on the price menu, no longer recommended.
No question wording, label, option sentence, length, music style or video
style changed. Goldens follow the data.

## v2.9.106 - 2026-10-23 - optional Studio capability is evaluated before credential demand

The persistent timer (`timer-artifacts/run-timer.sh`) demanded `machine.url` and
`machine.key` in section 4 and only evaluated the optional Studio capability in
section 6b. A chat-only or disabled installation therefore refused every tick
with "this computer is not paired" instead of staying quiet: on Mac box
`rescue-maria-anderson` the launchd job produced 5,326 identical lines /
569,882 bytes before the repair, one every 120 seconds.

The canonical `capability.json` record (`disabled | needs-enrollment | ready |
degraded`, written by `studio_bridge.py`) is now read in a new section 3b, BEFORE
any credential demand:

- `disabled` / `needs-enrollment` -> `exit 0` quietly (one transition line, then
  steady silence), before any credential is demanded.
- `ready` / `degraded` -> fall through to the unchanged credential demand, so an
  enabled-but-broken installation is still REFUSED with exit 2 rather than
  silently skipped. Authentication is not weakened for enabled Studio use.
- No record at all -> `studio_bridge._capability_state`'s canonical answer for
  "no key and no enrolment intent" is `disabled`, so an unpaired box exits 0 in
  total silence and writes nothing: no record, no marker, no key. This closes the
  per-tick failure for a freshly installed chat-only box, not only for one whose
  record already says disabled.

The record is parsed with a JSON reader, not a line regex. A case variant
(`"DISABLED"`, `"READY"`), a duplicate key or a multi-line layout previously
flipped the decision: an uppercase `disabled` on a box with a key fell through to
the credential demand and refused every tick, while an uppercase `ready` with no
key idled instead of refusing. `json.load` now resolves a duplicate key
deterministically and lowercases the value; an unrecognised value fails CLOSED
into the credential demand. Truncated or unreadable files resolve to "no usable
record", which is the canonical `disabled` path when no key is present.

The `capability.disabled` sentinel and `DS_CAPABILITY_DISABLED=1` keep their
existing behaviour. `--ready` is a readiness probe and is never skipped. No
second state mechanism is introduced and no authentication check is removed.

Checks updated to the corrected contract:
`timer-artifacts/checks/test_seam_retention_quiet.py` T3/T4 now assert that an
unpaired box is silent and writes nothing, and T6/T7/T8 were added (capability.json
disabled/needs-enrollment quiet with no credentials; recorded ready still
refused without credentials; `--ready` not skipped; ordinary chat intake
independent of pairing). `timer-artifacts/checks/run_checks.py` check G expects
the quiet skip it always described and now passes.

On the unpatched tree: 7 seam checks fail and check G fails (21/22). On this
release: seam checks 18/18, timer checks 22/22.

This release changes the optional Studio poller only. It does not enrol a
computer, does not generate or rotate a key, and does not alter chat intake,
media generation, approvals or budgets.

## v2.9.98 - 2026-10-23 - lip-sync evidence follows the final delivery

Missing lip-sync markers, speaker/line identities or approved storyboard evidence
now fail closed. The render contract binds included segments to their approved
shots, successful generation receipts and materialized media; Q8 reconciles that
proof with the final export and the delivery package's clean-video hash. Generated
but unused clips cannot satisfy delivery. Existing measured and flagged kept-take
rules and paid-retry approval conditions remain in force.

The existing provider route now has an instrumented audio producer: selected-song
revision and hashes, source upload, separation task, measured offset and executed
cut window are carried into the upload and final export proof. Legacy records
without that operation history fail closed; paid artifacts are preserved.

This release repairs evidence enforcement only. It does not select a new numeric
lip-sync quota, change the duration formula or activate an existing client run.
The revised percentage schedule remains pending a separate policy decision.

## v2.9.93 - 2026-10-22 - batch 8d: spatial subject motion, Skill 75 interrupt-state preservation

1. D3 spatial motion (`scripts/core/shot_planner/motion_score.py`): motion is
   now measured as LOCALISED subject movement on a 48x27 spatial grid, not the
   mean change of per-frame mean luma. Each pair is compared after an affine
   residual that compensates global translation, so a pan over a still scores
   0.000000 (refused) instead of passing; additive and gain-only flashes score
   0.000000. Degenerate (zero-contrast) pairs are excluded BEFORE any co-variance
   division and counted, and a clip whose pairs are all degenerate refuses with
   the typed `CLIP_MOTION_UNMEASURABLE` rather than a silent low-motion score.
   `MOTION_STRUCTURE_MIN = 4.0` refuses spatially uncorrelated noise that clears
   the magnitude gate (sigma-64: subject 0.026224, structure 1.73 -> refused).
   The subject threshold is `MOTION_SUBJECT_LOW = 0.012`, and the ladder flips
   exactly once across it in the shipped fixtures. `frame_diff_score` is still
   emitted, so a 1.0.0 receipt without spatial evidence keeps its documented
   legacy decision; the F12 fail-closed rule (measured sub-threshold refuses
   even with `flagged: false`, `flagged: true` honoured) is unchanged.
   Recorded follow-up, out of scope here: the new residual full-map can raise an
   untyped `IndexError` on spatially uncorrelated noise (MEDIUM, crash not a
   wrong pass; no score is emitted, so the gate cannot admit a clip through it).
2. Installer box state (`update-skills.sh`, `scripts/skill-content-hash.sh`):
   an interrupted Skill 75 run keeps its resume state inside the skill folder,
   which the wholesale remove+copy destroyed on every update. The Skill 75
   box-state allow-list now carries `.checkpoint-pending` and
   `scripts/core/state_store.py.part` across the replace BYTE-IDENTICAL, scoped
   to Skill 75 only (the same relative paths in an unrelated skill are still
   removed), and the A2.5/A3 content gate excludes those paths from the same
   scoped set so the copy site does not abort and withhold the version stamp.
   `tests/unit/updater-preserves-skill75-interrupt-state.test.sh` (261 lines,
   16 assertions) proves the contract, its scoping, the 59-anthology-engine
   regression, the resume-stage read, and both pre-fix negative controls.

## v2.9.92 - 2026-10-22 - batch 8c: real canaries, gate-4 recap, mapping integrity

1. Shared real canaries (`tests/w10-canary/`): the clean-install canary and the
   upgrade-of-an-interrupted-run canary are now ONE composition rather than two
   divergent harnesses. Both drive the REAL distribution installer inside a
   sandbox (stubbed `openclaw`/`curl`, scratch HOME/OC_CONFIG/SKILLS_DIR/
   CLAUDE_CONFIG_DIR, network-free git), and both refuse rather than bless a
   weak tree: a manifest is refused when it is empty, below the skill tree's
   real file count, or missing the `SKILL.md`/`scripts` top level, and the
   loaded-source hook recomputes every digest so a tampered, extra or missing
   file fails. Typed refusals replace silent passes
   (`MANIFEST_MISSING`, `DIGEST_MISMATCH`, `UNPROVABLE_CHANGE`,
   `PRESERVATION_MISSING`, `INSTALL_FAILED`, `INSTALLER_LOCKED`,
   `PROCESS_LOST`, `SOURCE_CHECKOUT_UNRESOLVED`). Receipts name the
   distribution, the pinned source revisions, the manifest and the acceptance
   rows. A11 stays blocked: no paid provider call and no live channel send is
   reachable, and `--allow-paid` / `--allow-live-send` exist only to be
   refused.
2. Gate 4 final recap: one recap (scene / music / cost) plus the operator's
   production Go bound to its digest. The hold sits in front of BOTH video
   handout paths — the Agnes segment jobs and the KIE runbook row — and stays
   shut on a missing Go (`PRODUCTION_GO_MISSING`).
3. Acceptance-row mapping integrity: the receipt mapping verifies each row's
   `mapped_harness`, `mapped_command` and `run_by_hand`, and carries
   `external_repos`, so a row cannot claim evidence a harness does not produce.
4. Re-runnable compatibility proofs for the two behaviours above live under
   `tests/w10-canary/evidence/B8C/` and are executed by QC, not read.

## v2.9.91 - 2026-10-22 - batch 8b: 3x3 candidate matrix, capability-aware dispatch admission

1. 3x3 soundtrack candidate matrix (`song_choices/candidate_matrix.py`): three
   materially different lyric concepts (rows 1-3) x three treatments (columns
   A-C), stable ids **1A-3C**. One concept's three cells share the same lyric
   hash; the three treatment hashes differ. Completeness is SET EQUALITY with
   all nine ids, never `count == 9`. The contract owns build, validate, cost
   plan, selection and recovery only — it never generates audio, prices a
   budget or renders a UI.
2. C2 presence inheritance: every cell's provider style is composed by the SAME
   `suno_recipe.brief_style_text` the legacy three-variant path uses, and
   `variants.json` briefs (including the `revoices_lead` flag folded into
   `treatment_hash`) are reused through `song_choices.variants_for`. A variant
   marked `revoices_lead` therefore keeps its dry/upfront lead presence
   direction in the matrix cells too. The legacy one-concept/three-variant path
   is untouched; a three-option run is never relabelled as nine.
3. Capability-aware model configuration + D30 account-failure wiring at
   `ai_models.admit_dispatch`: an unsupported capability claim is refused with
   `CAPABILITY_UNSUPPORTED`, and a dispatch to an account the shared breaker has
   failed is refused with `ACCOUNT_FAILED`, both as actionable typed results.
   `ai_models.json` is unchanged — no model identity, route, price or lock
   semantics moved.
4. W01-U2 privacy scanner over the incident fixtures: the three roots scan
   clean and the fixtures are genuinely anonymous.

## v2.9.90 - 2026-10-22 - batch 8a: measured 50% contingency, acceptance scenario runners

1. F1/F2 contingency: the planning/retake allowance is now a measured 50% of a
   shot/cue job manifest (was a flat 20%). `budget_contingency.py` is the single
   owner of the rate, the ROUND_HALF_UP cent rule and the envelope math; every
   card, quote, quota and price path reads it. With no manifest naming its
   planned shots and cues the contingency is UNMEASURED (`CONTINGENCY_UNMEASURED`)
   and is surfaced as unmeasured — never silently replaced by a bare percentage.
2. Acceptance scenario runners (tests/w10-canary/scenarios/): A04 versioned
   visibility, A05 character-bible approval, A06 song playable + storyboard
   delivery/resume, A07 opening sync/duration, A09 factory lifecycle outbox, plus
   A02/A03 extensions in multi_run_canary.py. Each runner asserts against the
   tree under test with no live provider, no paid job and no channel send.
3. A06 is deliberately incomplete without a paid artifact: it needs a real
   produced song file via `--audio`. Without it the runner prints BLOCKED_A11
   and exits 4 BY DESIGN — a named blocked acceptance item, never a pass. It
   never fakes the playable-song assertion.

## v2.9.89 - 2026-10-22 - batch 6: F12 motion gate fails closed, H3 native audio

1. F12 motion gate: a measured sub-threshold motion score now FAILS CLOSED
   instead of passing on an unmeasured/neutral score (shot_planner/motion_score).
2. MiniMax H3 native audio: the mixing decision is recorded, a double-audio
   case is detected (model native audio + a separate music track), the model
   contract carries the audio policy, and both the dispatcher and the final
   assembler honour it.
The source-vector pin is NOT part of this release: it lands as its own
micro-batch immediately AFTER batch 6 merges, so the pinned onboarding revision
is a main that actually contains these units.

## v2.9.88 - 2026-10-22 - batch 5: WAL reads, H3 CLI, ledger-minted identity

1. WAL stores read behind a private copy (state_store, run_watch, factory, incl.
   continuation_enqueue) -- a healthy run no longer reports "unable to open
   database file" when the -wal/-shm sidecars cannot be attached.
2. Heartbeat: a COMPLETE stage is never a stall; a run parked on a client answer
   is not expired by the run cap.
3. make_timings passes the take's own audio_path through; qc_no_blur only calls a
   smooth band a fill when it carries a fill signature (repeated rows, a copy of
   the strip below, or a hard step), so smooth scenery is not refused.
4. Dispatch CLI: --state-store reaches the F14 lock, and --prompt-file drops
   exactly one trailing newline so an H3 prompt receipt still matches. MiniMax H3
   (minimax-h3/*) is on the allowlist, in the price menu, and has its own request
   builder (make_h3_request.py). Runbook rows updated.
5. Attempt identity is minted by the ledger: dispatch(attempt_id="") uses the
   committed id for reserve, settle and the overlap receipt -- a retry after a
   failed paid take no longer refuses DUPLICATE_ATTEMPT.
6. `factory.py next` uses the same _song_hold as the music stage, so a recorded
   operator-decision.json opens the acceptance hold in both places (measured
   gates stay FAIL; a relabel-shaped refusal stays absolute).
7. The continuity stage's own reconciler is wired into factory's registry, so a
   run with proven continuity records can leave continuity-bible.
8. Preflight: requirement/manifest/capability refusals now come AFTER the auth and
   choice-card gates (the card answer is authoritative), and a derived KIE
   credential requirement is hard-declared.
9. W10 canary harnesses ship (clean-install, upgrade, multi-run, receipt mapping,
   source vector) with the privacy scanner fixed: a scan root whose own name looks
   like a skip directory is scanned, never silently empty.

NOTE: v2.9.85 - v2.9.87 below shipped from the #2444 fold. Three of their constructs are
superseded by v2.9.88 and are NOT in this tree: attempt identity minted by string suffix
(`_next_attempt_id`), the second acceptance artifact `music/acceptance/qc-risk-acceptance.json`
(`QC_ACCEPTED_RISK`), and the inline `_proven_continuity` reconciler. The ledger-minted
identity, `operator-decision.json` + no-relabel semantics and `character_continuity.stage.register`
replace them. Their other content stands.

## v2.9.87 - 2026-10-22 - smooth scenery is not a gaussian fill

A real master was refused GAUSSIAN_FILL on a dim ceiling: the smooth run was
20.8% of frame height against an 18% floor, while the SAME shot one second
later measured 16.7% and passed. Pixel evidence on the refusal: 391 distinct
rows of 399, row-to-row change continuous (max 0.88 grey levels), no seam at
the band edge (0.77 grey), band present identically in the original 24 fps
clip, and the master's laplacian uniformly HIGHER than the source (lanczos
upscale sharpened, never blurred).

`qc_no_blur` now requires mechanical fill evidence before GAUSSIAN_FILL: a run
of >=3 byte-identical rows, a band that is a near-copy of the adjacent strip,
or a step at the band edge. Smooth content has none of the three and passes;
the shipped blur-fill fixtures still fail. New
`scripts/qc_no_blur/test_smooth_content_not_fill.py` pins both sides
(smooth scene passes, repeated strip and hard step refused); the existing
36-test detector suite still passes.

## v2.9.86 - 2026-10-22 - a client wait is never HEARTBEAT_EXPIRED

A run parked on the client's approval was reported expired once the 3-hour cap
passed, so the watcher told the client the run had run out of time while the
only missing thing was their own reply (seen on a real run: 1,226 minutes,
WAITING_APPROVAL, HEARTBEAT_EXPIRED). The cap now measures the studio's own
delay only: when `legitimate_wait` names a client wait, `expired` stays False
and no HEARTBEAT_EXPIRED is emitted. Stalls are unchanged - silence is still a
stall. Test 12 in `test_run_watch.py` pins it.

## v2.9.85 - 2026-10-22 - rebased on main (no feature regressions in the WAL fixes)

The merge that carried the WAL-safe reads onto main had been resolved by taking
this branch wholesale for four files, which dropped main's newer APIs:
`state_store` lost `read_qc_records`/`DOC_QC_RECORDS` and its typed errors,
`run_watch` lost its supervision/activity model, `lyric_timing` lost main's
loader work, and CI caught it (QC static invariants). This release re-bases
each file on main and re-applies ONLY the branch's own change:

1. `state_store.needs_recovery` uses `_ro_connect` (forced open + private-copy
   fallback) on top of main's full API. `test_state_store_s75w02u4`: 22 groups.
2. `run_watch._ro` same fallback, plus COMPLETE is never a stall; tests 10 and
   11 added to main's suite. `test_run_watch`: ALL PASS.
3. `intake_card.channel_send_argv` stages out-of-allowlist media into
   `<state>/delivery-queue-media` on top of main's builder; a missing file is
   passed through so the sender names the real error.
4. `lyric_timing` reverts to main unchanged - main already carries the lazy
   faster_whisper loader, the `compute_type` keyword and the word-shape
   conversion.

## v2.9.84 - 2026-10-22 - the documented dispatch command can actually pass F14 and the H3 receipt

Two wiring defects made the runbook's own video command impossible to satisfy;
both were found by dry-running the real gates on built H3 requests.

1. `--state-store` ON `dispatch` (`scripts/core/kie_dispatch/kie_dispatch.py`).
   `main()` never passed `state_store`, so `read_locked_model(None, run_id)`
   always returned None and every CLI video dispatch refused
   VIDEO_MODEL_LOCK_MISSING no matter what the run had locked. The flag now
   threads the run's `control/state.sqlite3` into F14.
2. PROMPT FILE NEWLINE (`scripts/core/kie_dispatch/kie_dispatch.py`). A prompt
   file written with one trailing newline changed the bytes an H3 receipt was
   issued over, so `--prompt-file` refused PROMPT_NOT_TEMPLATED on every
   templated job. Reading a prompt file now drops exactly one trailing newline.

Regression: `test_kie_dispatch` 18/18, `test_prompt_cap_u7` 5/5,
`test_model_lock_f14` 9 blocks, `test_make_h3_request` and
`test_model_identity_h3` all pass.

## v2.9.83 - 2026-10-22 - one supported H3 request path

H3 refuses an un-templated prompt (PROMPT_NOT_TEMPLATED), and nothing in the
run path ever called the assembler, so the only way an H3 shot could dispatch
was to substitute another model. Now there is one supported builder.

1. `scripts/core/prompt_templates/make_h3_request.py` - spec + character record
   in, dispatch-ready request out: assembles via `prompt_templates.assemble_h3`,
   measures the model's own band, attaches `prompt_templates.receipt()`, pins
   `model` to a canonical `minimax-h3/*` id, and refuses any other model id
   rather than silently using it. Fixed model id, no padding, no truncation.
2. `scripts/core/prompt_templates/test_make_h3_request.py` - nine assertions on
   the golden fixture: band 5,000-6,800, receipt sha equals the prompt, the cap
   and receipt gates pass, a changed prompt is refused, and a Hailuo id is
   refused (exit 2).
3. `references/stage-runbook.md` - the video row now names the builder and says
   in words: never substitute another model to get a prompt through.

## v2.9.82 - 2026-10-22 - MiniMax H3 is its own model: 7,000 chars, never Hailuo

Owner directive, verbatim: "Don't you ever change the model. I told you H3. I
meant H3." The H3 family was blocked from dispatch entirely: its canonical ids
were missing from the F14 video allowlist, so any card lock of H3 could only be
made to run by substituting a Hailuo 02 id - a different model with a 2,000
char prompt cap. That substitution is now impossible.

1. H3 ON THE MENU (`scripts/core/kie_dispatch/model_lock.py`,
   `references/price-menu.md`). `minimax-h3/image-to-video`,
   `minimax-h3/text-to-video` and the `minimax-h3/*` family are on both the
   static allowlist and the rate table, so `assert_allowed` and the menu drift
   check agree and a H3 lock dispatches as H3.
2. PROMPT BAND UNTOUCHED (`scripts/core/prompt_limits.py` behaviour, no code
   change needed once the id is correct): H3 measures off the 67 catalog entry's
   `vendor_hard_cap_chars` = 7,000; the 2,000 override stays scoped to
   `hailuo/*`. Fixture: 6,800 passes, 7,001 refuses PROMPT_OVER_CAP.
3. PERMANENT GUARD (`scripts/core/kie_dispatch/test_model_identity_h3.py`).
   Twelve assertions pin: both H3 ids allowlisted, price-menu == static
   allowlist, no H3->Hailuo alias anywhere in either module, H3 cap 7000,
   Hailuo cap 2000, and the 6,800/7,001 boundary. Any future edit that aliases
   the families or re-caps H3 fails this test.

## v2.9.81 - 2026-10-22 - factory.py reads a WAL state db whose sidecars are gone

1. RESILIENT READ-ONLY OPEN (`scripts/core/intake_preflight/factory.py`).
   `factory.py next` opened `control/state.sqlite3` with a `mode=ro` URI. The
   store is WAL mode, so with the `-wal`/`-shm` sidecars absent the open raised
   "unable to open database file" and `next` answered `state-unreadable` for a
   perfectly healthy run — the same defect v2.9.79 fixed in `run_watch.py`, in
   the command every agent is told to run first. Both read-only opens now go
   through `_ro_connect`, which retries on a private temp copy and never writes
   the run. `test_factory_next.py`: 35 checks, 0 failures.

## v2.9.80 - 2026-10-22 - a delivered run is never "stalled"

1. NO STALL ON A COMPLETE STAGE (`scripts/core/heartbeat/run_watch.py`).
   After delivery the last stage's `updated_at` ages past 30 minutes, so
   `stall_check` flagged HEARTBEAT_STALLED on a fully delivered run and the
   client message said the run "hit a problem" on every tick after the video
   had already been sent. `stall_check` now returns not-stalled for a COMPLETE
   stage. Covered by test 8 in `scripts/core/heartbeat/test_run_watch.py`.

## v2.9.79 - 2026-10-22 - a WAL state database never reads as "unreadable"

1. RUN_WATCH PRIVATE-COPY FALLBACK (`scripts/core/heartbeat/run_watch.py`).
   The state store is WAL mode. When `control/state.sqlite3` exists but its
   `-wal`/`-shm` sidecars are gone (an orphan-temp sweep, a restore, a copy),
   the `mode=ro` URI open raises SQLITE_CANTOPEN and the envelope emitted
   `HEARTBEAT_STATE_UNREADABLE` — a client-facing "I couldn't read where your
   video is up to" on a perfectly healthy run. `_ro()` now retries by copying
   the db plus whatever sidecars exist into a private temp dir, opening the
   copy with `PRAGMA query_only=ON`, and removing the temp dir at exit. The
   live run is still never written. Covered by test 7 in
   `scripts/core/heartbeat/test_run_watch.py`.

## v2.9.78 - 2026-10-21 - an overshoot flags, the client decides the song

1. QC DURATION OVERSHOOT = FLAG, NOT STOP (master_length, song_dispatch,
   qc_gate, final_assembler). The one rule is `master_length.judge_duration`,
   used by the video master check and the song `length` gate. At or under the
   target passes clean; an overshoot of up to 10 seconds PASSES and records the
   named warning `QC_DURATION_OVERSHOOT` ("62s of 60s — within the 10-second
   allowance"); an overshoot past 10 seconds ALSO passes and records
   `QC_DURATION_OVERSHOOT_SEVERE` with the exact seconds over. Neither stops
   the run; `qc_gate.evaluate` and the assembler emit the warning through
   `loud_failure.warn` and carry it on the receipt. An undershoot is unchanged:
   the song gate keeps the 5/10 band (past 10 points is still FAIL) and the
   video master stays free on the short side.

2. SONG-FAILURE VERDICT BELONGS TO THE CLIENT (song_choices, intake_preflight).
   `one_variant` no longer regenerates a failed take: ONE generation per
   variant, the judge's named concerns on the result, and the paid take kept.
   `deliver_choices` presents every take — accepted ones on the offer surface,
   failed ones in `SONG-CHOICES/FOR-LISTENING/` — and asks the ONE fork
   "Want me to redo all of them, keep one of these three, or generate three new
   options?". The answer is recorded in `song-choices/fork-decision.json`
   (`song_choices.py fork`, or `pick --reply` with words). `factory.py music
   --action complete` WAITS on that answer instead of blocking
   (`SONG_FAILURE_AWAITING_CLIENT`, row WAITING_APPROVAL); `redo_all` /
   `new_three` reopen the row for a client-authorized round, and `keep_one`
   never writes a PASS — the WW-18 / WW-21 measured gates still hold and the
   documented `--operator-decision` route stays the only way to close them.
## v2.9.77 - 2026-10-21 - run keepalive: the client hears from us every 10 minutes

Owner order: once intake is answered and the run starts, the client gets a stage
update every 10 minutes, every pending decision is put in front of them, a stall
is detected and picked back up, and the job hard-stops at 3 hours with a final
summary. No gate is weakened: the keepalive only adds visibility, and the
3-hour cap is a FLAG plus a client-facing wrap-up, never a silent pass.

- NEW `scripts/core/heartbeat/run_watch.py` - one read-only look at a run
  (`control/state.sqlite3` opened `mode=ro`, `control/fork-decisions.json`,
  `control/run-state.json`, `song-choices/`, spend_ledger `runs.created_at`)
  printing one JSON envelope: `run_id`, `stage`, `stage_state`,
  `elapsed_minutes`, `decisions_pending` (intake outstanding + approval gates +
  cost forks still on the safe default "wait", each with its own question and
  options), `stalled`, `loud`, `expired`, `message_for_client`. It never mutates
  a run: stall recovery is the printed `factory.py next --run-dir` command for
  the agent to run. Named codes: `HEARTBEAT_STALLED` (no progress for 30
  minutes, a dead lease or a STALE row), `HEARTBEAT_EXPIRED` (3-hour cap, job not
  COMPLETE), `HEARTBEAT_STATE_UNREADABLE` (loud, exit 1, never a silent pass).
- NEW OpenClaw wiring `timer-artifacts/install-keepalive-cron.sh` - ONE
  idempotent `skill75-keepalive` cron every 10 minutes, silent (`--no-deliver`),
  isolated session, cheap/local model pinned, one agent; exact-name JSON
  presence check (an UNKNOWN list refuses rather than risk a duplicate) and
  tombstone-respecting; prompt = `timer-artifacts/keepalive-cron-prompt.txt`.
  `timer-artifacts/uninstall.sh --apply` removes it and writes the durable
  tombstone so no later install resurrects it.
- INSTRUCTIONS.md + SKILL.md: "Run keepalive (10-minute heartbeat)" section -
  the claude-nine / Claude Code 10-minute loop (the `/loop` skill or a
  self-scheduled wakeup) that speaks `message_for_client` and stops itself at
  3 hours (`expired`, or `--interval-check` exit 10).
- Tests: `scripts/core/heartbeat/test_run_watch.py` (normal stage update,
  decision surfacing, stall, 3-hour expiry, unreadable state, no-mutation proof)
  and `timer-artifacts/checks/test_keepalive_cron.py` (dry-run writes nothing,
  exactly one registration, idempotent second run, tombstone, UNKNOWN list,
  uninstall). Command Center: no change needed - `cc_sync.Outbox` carries only
  create/deliverable/move kinds, the factory stages already post the run's own
  moves, and a read-only watcher must not add board writes.

## v2.9.73 - 2026-10-21 - reliability fixes proven by the Voyage To Virtue run

Every fix below is proven by measured evidence from the Voyage To Virtue run
(13 shots, 65 lip-sync receipts, a 17-20 h stale session); no gate was weakened.

L1.1 - LIP-SYNC GATE CONDITIONAL (final_assembler). Live: a faceless 13x6.67 s
plan — zero lip_sync markers, zero speaker-keyed lines — was refused
LIPSYNC_COVERAGE_SHORT+LIPSYNC_LINES_TOO_FEW. `lipsync_gate` now mirrors
`face_speaks_gate`: a plan declaring no lip-sync work records
{verdict: NOT_APPLICABLE, reason_code: LIPSYNC_NOT_IN_PLAN, ...numbers} on the
receipt and advances; a plan that DECLARES lines keeps the hard gate unchanged
(declared-short still refuses, measured live).

L1.2 - HOLD CLIP TO SLOT (final_assembler). Live: planned 83.17 s from thirteen
6 s clips, render produced 68.70 s (EOF trimming). Inputs are now ffprobed
(readable-or-refuse), and a short source is held with tpad=stop_mode=clone to
its slot then trimmed back to the slot exactly. Measured: a 3.6 s clip in a
6.0 s slot rendered 6.533333 s (was 3.6 s); a 13x5.3 s-in-6.0 s voyage replica
rendered 78.0/78.0 planned with 13/13 holds; longer clips trim byte-for-byte as
before (7.34 s slot from a short source now renders 7.34 s, was 6.0 s).

L1.3 - LANE_SIZE_BROKEN SILENCED (final_assembler). Live: four
`size() missing 2 required positional arguments: 'runtime' and 'provider'`
warnings per assembly. The internal call now invokes
lane_size.size("claude-code","openrouter",units=999) — the same documented call
intake_preflight/factory.py makes — and a normal assembly prints zero
LANE_SIZE_BROKEN warnings (was 2 per dry assemble, 4 in the preflight+build
sequence).

L1.4 - HEADLESS + RECEIPT BESIDE OUTPUT (final_assembler). assemble() is now a
thin wrapper over _assemble() and the receipt is written beside the output on
EVERY non-dry-run outcome, error paths included: a headless CLI
assemble (stdin=devnull, no prompt, no browser) assembles and writes
<output>.receipt.json even on a gate refusal (was: refusal wrote no receipt).

L2 - WW-21 OPERATOR DECISION (song_dispatch, intake_preflight). Live: song
master delivered, summary PASS, stage music FAILED_BLOCKED
ACCEPTANCE_NOT_PROVEN, `music/acceptance/` held five empty dirs across 90 takes,
D5 measured FAIL across four estimators, `_MANUAL_SOURCES` forbids a relabel —
no honest way to close the stage. `factory.py music --action complete
--operator-decision <path>` now accepts a DOCUMENTED decision file recording
{decision: ACCEPTED_RISK, operator, at_utc, gates_not_proven,
measured_evidence_digest, reason}; the digest is CHECKED against the on-disk
measured-evidence records (a fabricated digest is refused, 13 fabrications
tested), the take-level records stay untouched (D5 verdict UNMEASURED kept),
`_MANUAL_SOURCES` stands, and an invalid or missing file writes nothing. A valid
decision measured: state FAILED_BLOCKED -> COMPLETE with the gates-not-proven
list recorded.

L3 - CARD OFFERS ONLY REGISTRY-RESOLVED MODELS (choice_card, style_defaults).
Live: the client's card said "MiniMax H3"; the live KIE registry (218 models)
does not carry it; the run stopped to ask a human at 21:57Z. choice_card's
video-model list is now built from the registry the skill already ships
(resolve/require/lock gated on the live table), the card question is built
fail-closed from require_choices(), and lock_choice refuses to write
video_model_lock for an unresolvable model. Measured: a registry without the
MiniMax entries refuses by name (MiniMax H3 named in the refusal), renders no
lock row, and the end-to-end `card --format text` renders RECOMMENDED pricing
from the live table on the live registry.

L4.1 - RECONCILE FROM ARTIFACTS (intake_preflight). Live: gate.json
approved_at 2026-10-20T21:56:49Z with 13 stills while the storyboard row said
NOT_STARTED, so `next` kept handing back the music command. `next` now
reconciles stage rows from proven artifacts on disk FIRST, through state_store's
version-CAS transitions (owner "reconcile", lease, events) — never a
hand-written sqlite UPDATE. Measured: storyboard NOT_STARTED -> COMPLETE with
13 approved shots and 13 stills found; unproven rows and lease rows are never
seized.

L4.2 - STALE-SESSION GUARD (intake_preflight). Live: sessions ran 17-20 h on
code older than the installed skill; three merged fixes could not reach them.
A process that booted on an older skill-version.txt than the one on disk now
refuses every stage command with SKILL_UPDATED naming both versions (e.g.
installed v2.9.72 > boot v2.9.71). Measured live end-to-end with exit 1.

L4.3 - WAITER TEMPLATE FIXED (references/stage-runbook.md). Live: two shells
spun ~8 h on `while pgrep -f "run_vtv_music.py"`, which matches its own command
line. The documented waiter now anchors on the interpreter with the bracket
trick (`pgrep -f "python.*[r]un_vtv_music\.py"`), never matching the waiter
shell's own pid, with an artifact-based second exit and a self-check command;
a test proves the OLD pattern reproduces the 8 h bug and the NEW one does not.

L4.4 - ATTEMPT CEILING (lip_sync/lip_gate). Live: 65 lip-sync attempts, all FAIL
FACE_COUNT, still retrying. After N=3 consecutive identical structural failures
the gate stops before another paid attempt: {cause: ATTEMPT_CEILING_REACHED,
structural_code: FACE_COUNT, count: 65, ceiling: 3, "no face in these stills —
choose a face-visible format"}.

L4.5 - SAFE-DEFAULT COST FORKS (intake_preflight). A cost/approval fork now
carries a safe DEFAULT bounded by the remaining spend-ledger balance and the
run's declared budget, recorded as a decision in control/fork-decisions.json:
cost 2000 of a 3500 remaining balance -> "proceed"; 999999 -> "wait" naming both
numbers (2000 < 3500 <= budget 5000, all live-measured).

## v2.9.72 - 2026-10-20 - R&B Flow fits, or is refused before stage 3; brief words count

Two defects left over from the stage-3 and music-stage fixes. Both are the same
class: a gate the run cannot satisfy, discovered minutes into a paid run.

R1 - R&B FLOW DEADLOCK. A rap style kept its rap reservation AND its generic
sung budget, so the two missed the style's sung-share floor at 30/45/60 s.
Measured on v2.9.71: `plan(60,'rnb-flow')` = sung 53 + rap 40 ->
`words_fit.preflight` SHARE_OFF_TARGET (63.5% against 72.9% floor); 30 s and
45 s -> WORDS_DO_NOT_FIT. 90/120/180 s were fine. Any client who picked R&B
Flow with a short card hit the same loop the stage-3 fixes removed.
Now `length_formula.plan` sizes the sung allocation against the share the gate
actually checks, at the style's own rates (never raising a word count), so
rnb-flow plans pass `words_fit.preflight` at every length that can hold both
the rap floor and the share floor. A card too short for both is REFUSED up
front by `music_director.build_generate_request` with `STYLE_TOO_SHORT_FOR_RAP`
naming the shortest card that works (70 s for R&B Flow), before the sheet and
before any spend. Soul Ballad, Soul Rise and no-style plans are byte-identical.

R2 - THE CLIENT'S OWN BRIEF WORDS. `lyric_writer.client_word_runs` read only
offer/website/claims/packet_lines, so words the client wrote inside the
research brief's sub-avatar answers ("avatar", "emotional_wound",
"desired_transformation") were treated as invented and refused
line-not-first-person. Those three validated client answers are now exempt
verbatim sources. `sub_avatar.notes` stays excluded: it is the authoring
provenance remark, the one model-written field inside that block.

Not in this release: the drafting-row tolerance still admits a sheet that
`words_fit` would refuse (60 s Soul Ballad: 74.6 words against 58). Tightening
it was measured against the approved 48 s gala sheet (58 words, a real delivery
in 48 s) that `words_fit` itself prices at 61.9 s -- refusing it would reject a
real approved sheet, so the size is a calibration question for the fit rates,
not a tolerance to tighten. Tracked, not shipped.

## v2.9.71 - 2026-10-20 - the music stage runs on a clean install: five walls

v2.9.70 opened the script gate. Both clients then hit the music stage and
stopped there: on a clean install NOT ONE paid music job could be dispatched and
the bare `song_choices.py generate` CLI refused every run. Five defects, each
proven on real client data (Laya Kelley's Voyage To Virtue run, 2026-10-19;
Jennifer Allen's runs of 2026-10-16/17, FAILURE-ANALYSIS-20261017 section 4.5).
Laya's box agent hand-patched five files between 09:56 and 10:25 EDT and her
takes and word timings came back; this release carries the same repairs, with the
tests the patch never had.

1. **The card receipt was never attached to a song job.** `kie_dispatch.
   card_gate_refusal` refuses EVERY paid job whose request carries no
   `card_receipt` (F15), and `song_choices._real_generate` never attached one, so
   every song dispatch -- and every word-timing sub-call -- refused
   CARD_UNANSWERED although the client had answered and the stamped receipt was
   sitting in the run folder. `song_choices._card_receipt` now reads the run's
   OWN record, in order: `control/card-receipt-block.json` (the stamped block),
   `control/card-receipt.json` when it holds an `answers` dict, then
   `control/run-state.json["card_receipt"]`. Nothing found -> nothing attached:
   the gate still refuses and no receipt is ever fabricated. A request that
   already carries its own receipt keeps it. `song_transports.make_timings`
   passes the same receipt to the word-timing step, which forwards it on its own
   paid sub-call.
   *Proof*: Laya's `probe/req.json` -> `CARD_UNANSWERED`; the same request with
   her `probe/card-receipt-block.json` attached -> `None`.
2. **`script_words` was fed the wrong text.** `song_choices.cmd_generate` passed
   `script_words=spec["client_text"]` -- the 247-word market-offer research
   document. `script_words` is a REQUIRED_TAKE_GATE that checks the TAKE sang the
   approved lyric, so every take was asked to sing a sales page: 96 of the 120
   required words were unsingable by any take. The gate is now handed the
   approved sheet's LYRIC LINES only (`_sheet_lyric_words`), falling back to
   `sheet_text`; bracket headers are directions to Suno and are excluded.
   `client_text` stays the hook-vocabulary source in `build_requests`.
   *Proof*: on Laya's sheet the gate wants 55 words and a take singing that
   sheet misses none; against the old `client_text` the same take misses 95.
3. **An empty `callBackUrl` was sent.** `audio_c3.lyric_timing` emitted
   `"callBackUrl": ""` when a track carried no callback, and Skill 74's
   `_cb_check` refuses `""` as bad_request before submit. The key is now OMITTED
   when there is none; a real `callback_url` is still sent.
4. **SYNC createTask models saved zero files (the `kie_dispatch` half).**
   `ai-music-api/timeStamped-lyrics` answers createTask synchronously: the
   payload (with `alignedWords`) is in `data`, there is no taskId and no job to
   poll. `kie_dispatch` synthesized a LOCAL `sync-` id and the save step then
   re-queried that id at KIE, found nothing and saved zero files -- which the
   word-timing stage read as "no words". `kie_dispatch` now writes the submit
   envelope to `sync-info.json` beside the request and passes `--info <file>` to
   the save step for a sync job only; an asynchronous job's save argv is
   unchanged. The Skill 74 side of this defect (the adapter reporting a sync
   payload as `bad_response`, persisting a URL-less payload as
   `<save_dir>/<task>_0.json`, and the `save --info` flag itself) is fixed in
   Skill 74's own lane and ships with it; this skill only supplies the `--info`
   argument and the envelope.
5. **No production transports existed.** `cmd_generate` correctly refuses a
   None `measure`/`save`, but nothing in the tree supplied real ones, so the
   command the runbook hands agents (`song_choices.py generate`) ALWAYS refused
   "the production run needs a real measure transport". New `scripts/core/
   song_transports.py` (stdlib + numpy + ffmpeg, through the skill's own load
   governor) supplies `make_measure` (decoded waveform -> duration, detector
   segments, first sung second, tail RMS, music-under-speech ratio, the three
   pace windows, and the one word-timing step), `make_save` (every paid take
   filed under its variant -- a rejected paid take is evidence), `make_timings`
   and `build_pace_plan`. The `generate` CLI wires them itself; the programmatic
   refusal for None stays exactly as it was.

Evidence (Laya Kelley, Voyage To Virtue): req.json -> CARD_UNANSWERED before the
receipt is attached, None after; her 88 s sheet is satisfiable. Evidence
(Jennifer Allen, 2026-10-16/17): five throwaway `driver_dispatch*.py` files were
written to work around exactly these five walls; none is needed now.

`scripts/core/test_music_clean_install_v2971.py` proves all five here (the real
probe shapes, a synthesized tone measured off disk, and a sync dispatch through
a FAKE Skill 74 runner -- no adapter call is made).



## v2.9.70 - 2026-10-20 - stage-3 script-lyrics deadlock: three gates that contradicted each other

A 60 s / 90 s run sat in script-lyrics for hours and never reached the song:
Laya Kelley's Voyage To Virtue run (about 9 hours, 321 shell calls, 1.84 M
output tokens) and Jennifer Allen's runs (54-minute and 136-minute agents on
the same errors). The agent is told to iterate until every gate passes and
never edit a validator, and three shipped gates could not all pass at once:

1. `lyric_writer` refused every non-CTA line without I/me/my/we
   (`line-not-first-person`) while `suno_recipe.check_hook` REQUIRES the hook
   to be the client's own words. Laya's hook "Virtue isn't something you have /
   it's something you choose" could never pass both. A line that is a
   contiguous run of at least 3 words of the client's own brief text (offer,
   website, claims, packet lines) is now exempt from first-person. Invented
   second-person lines and 2-word fragments still refuse. The comparison
   folds apostrophe variants (a brief pasted from Word carries U+2019 while the
   written lyric usually carries ASCII '), because ``words`` splits the curly
   form ("isn't" is one token, "isn\u2019t" is two) and the client's own line
   then silently refused itself -- the same deadlock by a different route.
   ``words`` and every gate built on it keep their tokenisation.
2. `lyric_writer` `line-multi-idea` fired on ANY period inside a line, so the
   client's website (`VoyageToVirtue.com/journeyofbecoming`, required verbatim
   by `protected_names.check_website`) always failed. A dot inside a word
   (`site.com`, `3.5`) is no longer a sentence break; "I rise. I fall" still
   refuses.
3. `length_formula.plan(L, style_id=...)` priced its word budget at 1.4 spoken /
   1.07 sung words per second, but `words_fit.preflight` (enforced by
   `music_director`) prices Soul Ballad at 1.85 / 1.0 plus 8 s intro/outro, so
   the plan's own budget was refused `WORDS_DO_NOT_FIT` (60 s: 66 words =
   65.7 s against 58 s; 90 s: 95 words = 90.1 s against 88 s). A named style
   that delivers no rap now caps its `words` to what `preflight` admits at that
   style's rates. `plan(L)` with no style is byte-identical (BASE_SHA pins),
   rap styles are untouched.
   Scope, stated plainly: change B caps ONLY the plan the WRITER is handed
   (`length_formula.plan` with `style_id`). `suno_recipe.check_lyric_sheet`'s
   drafting tolerance (10 % + 2) is NOT that gate: it takes the larger of the
   styled plan and the unstyled one, which is byte-for-byte the allowance
   origin/main applied -- for a rap style (the styled plan carries the rap
   words) and for a non-rap style (the unstyled plan is the uncapped total).
   Reading the capped total there refused a real approved 48 s sheet (the gala
   sheet: 58 words against a 46-word cap); reading the unstyled total alone
   refused a rap sheet (123 words against 95, ignoring its 128-word rap plan).
   `words_fit.preflight` remains the one gate that decides whether a sheet FITS.

Doctrine: SKILL.md, INSTRUCTIONS.md and references/stage-runbook.md carry a
stage-3 STOP RULE -- at most 3 validator rounds, then stop, report the exact
gate and ask the client one question; never grid-search, never more than about
10 minutes, never edit a validator during a run.

New check: `scripts/core/length_formula/test_style_budget_fits_v2970.py`
(Soul Ballad and Soul Rise at 30/45/60/90/120/180 s all `WORDS_FIT_OK`).
Updated: `lyric_writer --selftest` (6 new cases), `test_style_plan_u2.py` (the
L60 Soul pins compare everything outside `words`, and the words must fit).

## v2.9.65 - 2026-10-17 - hook plan upstreamed, strict request duration, pace gap closed

The remaining defects from the same 48 s run. Both changes ADD gating; no gate,
threshold or refusal was weakened and no paid call is made by any check.

- `song_dispatch.validate_request` takes `hook_plan` and, when none is passed,
  reads the request's internal `_hook_plan` -- the SAME source the judge reads
  at `run_takes` -- and hands it to `suno_recipe.check_lyric_sheet`. Before
  this the hook-count gate was blind to the plan at the pre-spend seam: a
  request carrying a plan was validated with none.
- `song_choices.build_requests` attaches `_hook_plan` to the request BEFORE
  the pre-spend validation (it used to attach it after, so the pre-spend call
  never saw it). The plan still never reaches KIE: `run_takes` moves it into
  the judge's plan and strips it from the payload.
- `run_takes` now admits ONLY a request duration EQUAL to the plan's delivered
  seconds. The bare 15 percent Suno headroom is refused before any spend
  unless the plan carries the owner's explicit `duration_headroom_approved`,
  and then the override and its record are written into the returned
  `duration` block (`mode: headroom_override`). Nothing trims a raw take before
  judging and the length gate refuses audio over the delivered seconds, so the
  old silent headroom admission bought audio the judge would refuse. The
  headroom FORMULA is unchanged.
- The pace-direction guard from v2.9.64 is now covered by a self-check that
  also proves a removal is caught when the order rides only on the request's
  `_pace_plan`, and that the audio thresholds (0.30 onset share, 3.0 dB) are
  the same numbers.

New check: `scripts/core/song_dispatch/test_remaining_defects_r1_r2_r4.py`.
Updated: `music_director/test_prompt_limits_u6.py` (strict duration + owner
override), `sung_hook/test_three_walls.py` (bare headroom now refused; override
recorded).

## v2.9.64 - 2026-10-17 - hook placement without section headers, pace direction guard, duration record

A real 48 s run judged 34 paid takes: 0 accepted. Three causes were measurement
and request plumbing; the missing audible gear change (pace_change FAIL on all
34) is the provider's audio and is not changed here. No gate, threshold or
refusal was weakened.

- `hook_placement.check_returned` returned FAIL "UNMEASURED: section headers"
  for every take whose words came from local transcription, which hears words
  and never editorial labels. With no headers it now finds each sheet hook
  block as its exact approved words on the measured word times, counts it only
  when the singing detector measured it sung, and applies the same build-up and
  story-beat floors and the extra-hook check. Untrusted timing, no measured
  segments, hook words shared with another section, or fewer sung hooks than the
  sheet carries stay UNMEASURED (blocking). No header is invented. On the same
  real take read both ways the first hook time agrees (22.589 s).
- The header branch could PASS with no first hook (headers present, none a
  hook): the time floors only ran when a hook header existed. That is now a FAIL.
- `song_dispatch.validate_request` now refuses a final `input.style` missing
  either pace direction when the pace order is known (argument or the request's
  `_pace_plan`); `song_choices.build_requests` passes it. `run_takes` checked
  only `plan["pace_change"]`, so a plan carrying the order as `_pace_plan` (the
  key the judge also reads) sent a style with neither direction; it now checks
  the same order the judge reads.
- `run_takes` records `duration` {requested_s, delivered_target_s, mode} and
  writes `DURATION_HEADROOM_REQUESTED` to stderr when the request asks for the
  15 percent headroom: nothing trims the raw take before the length gate, which
  refuses audio over the delivered seconds.

New check: `scripts/core/sung_hook/test_three_walls.py` (fixtures from the real
run, brand token replaced).

## v2.9.63 - 2026-10-17 - song generation, word-timing provenance and timing-word shape repairs

Four repairs on the song-choices and word-timing path. No quality-control gate,
threshold or refusal was weakened.

- `song_choices._real_generate` passed `generation=True` to `kie_dispatch.dispatch`,
  which accepts no such argument. The call raised `TypeError` before the dispatcher
  ran, so no real generation could happen. The stale argument is removed.
- `_real_generate` now keeps the provider's generation `task_id` on every take it
  returns, so `lyric_timing` no longer raises `SUNO_TRACK_MISSING` for those takes.
  The per-track Suno `audio_id` is not surfaced by the dispatcher envelope, so it
  stays absent. It is never filled with the task id, and a dispatcher-made `sync-`
  id is never recorded.
- `lyric_timing.fetch_suno_timestamped_lyrics` and `provide_word_timings` now pass the
  run's recorded choice-card receipt (argument first, else `track["card_receipt"]`)
  into the dispatch request, as `picture_gate.make_regenerate` already does. The
  card gate in `kie_dispatch` is unchanged: with no valid receipt it still refuses
  `CARD_UNANSWERED`. Nothing is invented.
- `sung_hook.measure`, `hook_placement.returned_sections` and `song_contract`
  (`_sung_hits`, `check_returned_song`) now read aligned words in both shapes:
  canonical `{word,start,end}` from `normalize_aligned_words` and raw Suno
  `{word,startS,endS}`, following `timing_guard`. Before, canonical words raised
  `KeyError('startS')` and `judge_take` reported a `judge_exception` FAIL.
  New check: `scripts/core/sung_hook/test_timing_word_shapes.py`.

## v2.9.62 - 2026-10-16 - BATCH-DSF-12: signature launch wave, skill-72 motion v2, skill-78 product selection, miniapp deletion

Batch `BATCH-DSF-12` — four members merged together into ONE batch branch off
`main` @ `0575636fd`, with one version bump and one entry for the whole batch,
per the swarm plan.

**The single bump is `v2.9.61` -> `v2.9.62`, and it is carried by member `#2119`
inside this batch** (`skill-version.txt` and the `SKILL.md` frontmatter
`version:` field moved together in that member's own commit). No second bump was
applied: a second bump would have taken `v2.9.63` and skipped a patch. The batch
diff against `main` therefore shows exactly one version move.

- `#2137` (`s49/signature-launch-wave1` @ `efe25c46b`) — S49 Wave 1: the Signature Launch domain schemas (`shared-utils/signature_launch/domain/*.schema.json`, incl. `purchase-event.v1.0.schema.json` and `route-graph.schema.json`), the route compiler, the launch-plan validator (`49-signature-funnel/scripts/validate_launch_plan.py`) and its `signature-funnel-entry.sh` wiring. 45 files, +6114/-390.
- `#2128` (`skill72-motion-v2` @ `c0f912c2b`) — Skill 72 Motion Graphics V2, the integrated release candidate, plus the `shared-utils/motion-render-runtime` provision/rollback/probe path and the `skill72-motion-graphics-tests` workflow.
- `#2143` (`martin/s78-signature-product-selection` @ `9c163b679`) — Skill 78 Signature Product Selection (Signature Launch L1 checkpoint): the new skill folder, its registration in `23-ai-workforce-blueprint/skill-department-map.json`, the regenerated `role-library/_index.json`, and the Layer-B "Skills You Operate" / dept-guide restamps that make the repo-consistency gate pass.
- `#2119` (`martin/pres-fix-d5-miniapp-deletion` @ `558e2f718`) — FIX-PLAN Item 13 / B10 S10-D5: the deprecated `templates/role-library/presentations/intake-miniapp/` tree and `deck-intake-turngate.py` are deleted (-7515 lines), with the `presentation-intake-guard` and `version-consistency` workflows, the refresh/repair scripts and `create_role_workspaces.py` updated to match. Also carries this batch's single version bump.

**Conflict resolution on this batch head (real, not papered over).** Merging
`#2143` produced content conflicts in the two generated manifests,
`23-ai-workforce-blueprint/templates/role-library/_index.json` and
`universal-sops/_content-manifest.json`. Both were resolved the only way they can
be: the conflict sides were taken, then the files were **regenerated from the
merged tree by their own generators** and verified clean —

- `python3 scripts/hash-universal-sops-manifest.py` -> `--check` PASS (115 files, all sha256 match)
- `python3 23-ai-workforce-blueprint/scripts/hash-content-manifest.py` -> `--check` PASS (538 roles + 148 sops + 19 personas)

The same two files conflicted when `origin/main` was merged into `#2128` and were
resolved and regenerated identically on that member branch.

**One more merge-resolution defect, found and fixed on the same evidence.** Taking the
incoming `_index.json` wholesale also took `main`'s `"version": "27.1.27"`, regressing the
branch's own repo-release marker while every other marker stayed at `27.1.28`. The
regenerator preserves `version`, so it survived regeneration and only the instrument caught
it — `scripts/bump-version.sh --check` went red:

```
templates/role-library/_index.json [version]   27.1.27   <-- DRIFT
DRIFT DETECTED — at least one file disagrees with /version.   (rc=1)
```

Restoring `27.1.28` on the `#2128` member branch (head `c0f912c2b`) and re-merging it here
turns the instrument green: `bump-version.sh --check` -> "All 10 version markers agree"
(rc=0), and `qc-assert-repo-consistency.py` -> rc=0, 10/10 dimensions OK.

**Area regressions, run on this batch head (BUILD-PLAN.md "Regression commands per area"):**

- Service: `node --test 75-drama-song-ad-factory/mini-app/service/test/*.test.mjs` -> 111/111 pass; `service/prove/prove_push_optional.mjs` and `prove_service_boundaries.mjs` -> ALL CASES PASSED.
- Page: `bash 75-drama-song-ad-factory/mini-app/ui/checks/run-all.sh` -> all 6 present checks passed.
- Approvals module: `node 75-drama-song-ad-factory/mini-app/approvals/prove/approvals.prove.mjs` -> C1-C5 ALL PASS.
- Bridge: `python3 75-drama-song-ad-factory/shared-bridge/checks/run_checks.py` -> ALL PASS.
- Timer: `install-timer.sh --platform mac --dry-run` -> rc=0. `--platform hostinger` and `--platform contabo` -> rc=1 "identity refused", **identical on `origin/main`** (control run in the same shell), so it is a pre-existing condition of the instrument, not a regression from this batch.
- Skill 75 core: `python3 -m pytest -q 75-drama-song-ad-factory/scripts/core` -> 2272 passed, 4 skipped, 0 failed.
- `retired-artifacts-ledger-guard` -> `OK: _retired.json in sync with git history (artifacts=54 sops=8 roles=46 departments=17)`, rc=0. `#2119`'s ledger entry records the **real** deleting commit `689404ca2` rather than a synthetic `refs/pull/N/merge` hash, which is why it is stable across merge refs.

**Race recorded as fact — and how it ended.** The launchd merge train opened its
own batch PR `#2155` (`batch/auto-merge`, head `d7881fd35`, "Merge train: 1 PR(s)
— #2137") carrying exactly one member, `#2137`. At the time this batch was built,
`#2137` was still `OPEN` with `mergedAt=null`, so this batch legitimately carried
it: `git merge-base --is-ancestor efe25c46b HEAD` was YES and it went in as a
normal `--no-ff` merge commit.

**`#2137` then landed elsewhere first.** `#2155` was merged at 2026-10-16T10:19:33Z
and `#2137` at 10:19:35Z, taking `main` to `8c3d1ce9a`. `#2137`'s head
`efe25c46b` is now an ancestor of `main`, so this batch's copy of it is a no-op
duplicate: the same commit, merged twice, with nothing to reconcile. `origin/main`
was merged into this branch afterwards (clean, no conflicts) so the PR sits on the
current `main`, and the remaining three members — `#2128`, `#2143`, `#2119` — are
the only content this batch still contributes. `#2155` was never touched: not
closed, not drafted, not commented, not forced.

No behaviour outside SPEC.md was added and no bridge file was touched.

## v2.9.61 - 2026-10-16 - BATCH-AGN-24H-O3: W4-proof-U2 accepted platform proof, privacy-repaired receipt

Batch `BATCH-AGN-24H-O3` - the accepted `W4-proof-U2` platform proof lands on
main with its receipt header privacy-repaired (one batch PR). Window:
2026-10-15T23:54:34Z - 2026-10-16T23:54:34Z.

- `unit/AGN-924-proof-REPAIR` (W4-proof-U2 privacy repair, AGN-924) -
  `references/agnes-platform-proof.md`: the TEST-01 container-persistence
  receipt (single-platform test, same-recipe parallel validation) and the three
  sourced receipt claims from the accepted head reach main, and every
  identifier site is swapped for a generic label: line 1's two identity
  categories become "a client VPS", and the six box-label cells (Instrument,
  Transport and the client-container rows) become "a client VPS box" and
  "a-client-vps-box-openclaw-1". Every other byte stays put: capture pointers,
  recipe wording, dates and every truthful output are preserved - the diff
  against the accepted copy is exactly 7 lines (line 1 plus those six cells),
  12 bytes shorter, 319 lines on both sides.

Version `v2.9.60` -> `v2.9.61` (main already carries `v2.9.60` from #2146; this release takes the next patch. G3 gates a skill-content change on that bump). Both the
`skill-version.txt` file and the `SKILL.md` frontmatter `version:` field carry
`v2.9.61` in the same commit, so the frontmatter guard holds.

## v2.9.59 - 2026-10-15 - BATCH-AGN-24H-O: last-24h leftover units

Batch `BATCH-AGN-24H-O` — the four wave-1/wave-2 units that were still open
against main after batch `#2130` merged, merged together (one version bump and
one entry for the whole batch). Window: 2026-10-14T23:54:34Z -
2026-10-15T23:54:34Z.

- `#2099` (`unit/AGN-W1-agnes-core-U9`, W1-agnes-core-U9) — `agnes_transitions`:
  chained segments, beat-aligned scene changes, crossfades and one soundtrack.
- `#2089` (`unit/AGN-W1-method-story-U1`, W1-method-story-U1) — `method_plan`:
  the Story Beat Blueprint and music-cue validator, the gates A-F record and the
  pace order builder.
- `#2080` (`unit/AGN-W1-method-trailer-U2`, W1-method-trailer-U2) —
  `delivery_clips`: trailer file names, end-card trailers and per-trailer
  destinations in the delivery receipt.
- `#2108` (`unit/AGN-W2-wiring-U1`, W2-wiring-U1) — `factory next` reads
  `method.json` and the Agnes answer: purpose routing, permission and platform
  gates, the trailer stage, Agnes segment jobs as a background job and the
  runbook rows.

Version `v2.9.58` -> `v2.9.59` (G3 gates a skill-content change on that bump).
Both the `skill-version.txt` file and the `SKILL.md` frontmatter `version:`
field carry `v2.9.59` in the same commit, so the frontmatter guard holds.

## v2.9.53 - 2026-10-14 - INTAKE-FIXES item 12: build hygiene never reaches the client

`#2065` (`unit/SWI-202`, W2-item12-U1) — the doctrine half of SPEC.md item 12. A drift
decision menu was put in front of a client mid-intake; clients never decide
repo-drift questions. `SKILL.md`, inside the enforced flow ("Start here: the
enforced flow", right after the no-skip-gate paragraph, not an appendix), now
states that drift between the installed tree and its source is build hygiene
and, during a client run, the drift report is OPERATOR-ONLY and SILENT: no
decision menu, no numbered report / add-files / full-re-sync / type-your-own
choice, no prompt that waits for an answer, nothing about drift in the client's
chat; the sync continues non-interactively on its documented default and the
drift is reported to the operator only, by named file and path. The decision
menu stays available on the explicit operator path (a named flag or an
operator-run sync outside a client run).

No code emitter exists in this repository to change: the four menu phrases
("Report only" / "Add 5 files" / "Full re-sync" / "Type something") are absent
from onboarding `origin/main`, from 999-setup `origin/main`, from the client
box's `~/.claude/tools`, `~/.claude/skills` and `~/.openclaw`, and from the
installed OpenClaw package, so the menu was composed at run time by the agent.
The fix that binds an agent is therefore the doctrine in the enforced flow.
The 999 packaged twin carries the same paragraph, because
`references/parity-contract.md` lists creative doctrine and the enforced flow
among the items that must be identical across both distributions (trevorotts1/999-setup `#226`). Version
`v2.9.52` -> `v2.9.53` (G3 gates a skill-content change on that bump); the 999
copy bumps its own VERSION train with its SKILL.md frontmatter, as its
parity-contract re-sync procedure requires.

## v2.9.52 - 2026-10-14 - INTAKE-FIXES batch O-1: intake doctrine, count truth, sync manifest, keyless research gatherer

Batch `BATCH-SWI-O-1` — four wave-1 units merged together (one version bump and
one entry for the whole batch, per the swarm plan):

- `#2051` (`unit/SWI-001`, W1-doctrine-U1) — the intake doctrine, the count truth and the overwork rule in prose in `SKILL.md`: dramatizations rather than true stories, no client fact-checking, the card's own total is the only number anyone may say, and the card's questions are the whole client load.
- `#2053` (`unit/SWI-002`, W1-doctrine-U2) — the same count truth in the card strings (`choice_card/intake_card/__init__.py`, `intake_card.py`, `intake_preflight/factory.py` no longer say "six-question") plus the `test_intake_card_h9.py` companion test encoding 14.
- `#2054` (`unit/SWI-006`, W1-recon-U1) — tree reconciliation: `references/sync-manifest.json` and `references/sync-manifest.md`, the per-file digest and disposition record the box roll consumes.
- `#2055` (`unit/SWI-005`, W1-research-U1) — the keyless web-search gatherer wired into the research stage (7 files under `scripts/core/research_engine/`), same JSON envelope and exit contract as the validator it feeds.

This single version bump satisfies G3 ("skill content change requires
`skill-version.txt` bump") for `#2055`. No behaviour outside SPEC.md was added,
and no older CHANGELOG entry was rewritten.

## v2.9.51 - 2026-10-13 - DRAMA-FIXES-OCT-13 batch #10 (R2-B): the studio page collects the story brief

Batch `BATCH-DSF-10` — release group R2-B, one member merged in (one version
bump and one entry for the whole batch, per the swarm plan). Cut at v2.9.51
because batch #8 (R2-A, #2010) took v2.9.50 on `main` while this batch was
building; this entry sits above it.

- `#2003` (`unit/DSR-105`, DSR-105) — the story brief. `scripts/core/choice_card/intake_card/intake_card.py` stays the only question source and gains five typed BRIEF questions (`offer`, `link`, `audience`, `character`, `photos`), so the card asks 14 instead of 9. `mini-app/ui/questions.json` was regenerated from it and the drift check passes; `mini-app/service/src/index.js` reads the brief out of the leading replies and stores it BESIDE the replies, marking `brief_complete` false with `brief_missing` rather than refusing an order; `mini-app/ui/studio.js` passes the question into `answerBox`, so the textarea shape comes from the typed contract instead of from sniffing option wording.
- Carries the `DSR-107` repair commits (`5b661c55a` .. `4d730e5b45e6828ff914709604fc65797ebd93c0`): the typed box's wording still gates whether it appears, and `mini-app/service/test/brief.test.mjs` plus `studio-render.test.mjs` assert the input listener rather than a value we just set.

No behaviour outside SPEC.md was added and no bridge file was touched.

## v2.9.50 - 2026-10-13 - DRAMA-FIXES-OCT-13 batch #8: the box enrols, the link is handed over, the timer installs, the client hears the pickup

Batch `BATCH-DSF-8` - release group R2-A, four Round 2 units merged together
(one version bump and one entry for the whole batch, per the swarm plan):

- `#1998` (`unit/DSR-101`) enrols the box and registers the studio timer at install: `shared-bridge/enroll-on-install.sh` plus `shared-bridge/checks/test_enroll_on_install.py`, and the call sites in `install.sh`, `update-skills.sh` and `INSTALL.md`.
- `#1993` (`unit/DSR-102`) makes the agent hand the client the personal studio link: `SKILL.md`, step 6 of STUDIO ORDERS in `INSTRUCTIONS.md` (who runs it, when, and what to say when the bridge answers `NO_KEY`) and the video department SOP.
- `#1997` (`unit/DSR-103`) makes `--register` actually install the studio timer on mac, hostinger and contabo: everything under `timer-artifacts/` (`install-timer.sh`, the launchd plist template, both cron templates, `README.md`, `PLATFORM-PROOF.md`).
- `#2000` (`unit/DSR-104`) lets the agent start after pickup and tells the client: `shared-bridge/studio_bridge.py`, `shared-bridge/wake_agent.sh`, `shared-bridge/checks/test_studio_handoff.py`, and `INSTRUCTIONS.md` steps 2-3.

`INSTRUCTIONS.md` overlap: `#1993` and `#2000` both edit that file. `#1993`'s hunks
sit in the step 6 link hand-over and `#2000`'s in steps 2-3, so git auto-merged them
and both survive on this head - the link hand-over wording and the poll/wake
wording are all present, and no conflict marker was ever written.

No behaviour outside SPEC.md was added; every unit's own tests and the area
regressions pass on this batch head.

## v2.9.49 - 2026-10-13 - DRAMA-FIXES-OCT-13 batch #7: proof receipts plus inbox freshness

Batch `BATCH-DSF-7` — three W4 units merged together (one version bump and one
entry for the whole batch, per the swarm plan):

- `#1976` (`unit/DSF-411`, W4-e2e-proof-U1) adds `references/studio-e2e-receipt.md`, the live end-to-end proof run on the operator Mac.
- `#1970` (`unit/DSF-302`, W4-e2e-proof-U2) replaces `timer-artifacts/PLATFORM-PROOF.md` with the no-docker platform proof (mac PROVEN, hostinger/contabo UNDETERMINED).
- `#1979` (`unit/DSF-611`) is the inbox-freshness fix: `mini-app/service/src/index.js` (+17/-3) read-modify-writes the R2 inbox on the order-created path instead of listing KV in the same request as the put, plus `mini-app/service/test/inbox-freshness.test.mjs` (+213).

No behaviour outside SPEC.md was added and no bridge file was touched; every
unit's own tests and the area regressions pass on this batch head.

## v2.9.48 - 2026-10-13 - DRAMA-FIXES-OCT-13 batch #4: the client-facing folder holds deliverables only

Batch `BATCH-DSF-4` — six client-folder units merged together (one version bump
and one entry for the whole batch, per the swarm plan):

- `DSF-201` (CF-1) the delivery folder refuses extra files (`DELIVERY_FOLDER_NOT_CLEAN`) and the lip-sync mouth strips move to `<run>/qc/mouth-strips/`.
- `DSF-202` (CF-2) the studio page serves an allow-list of assets only (`.assetsignore` plus the allow-list in the Worker).
- `DSF-203` (CF-3) the Ready-to-Post kit JSON is written to `<run>/qc/`, never beside the PDF in the delivery folder.
- `DSF-204` (CF-4) delivery receipts go to `<run>/receipts/` and the runbook no longer names a `final.mp4` nobody writes.
- `DSF-205` (CF-5) a failed render deletes the captioned and any partial files instead of leaving them in the delivery folder.
- `DSF-206` (CF-6) approvals publish image, audio, video and PDF files only.

No behaviour outside SPEC.md was added; every unit's own tests and the area
regressions pass on this batch head.

## v2.9.45 - 2026-10-13 - DRAMA-FIXES-OCT-13 batch #1: the studio page, service routes and personal links

Batch `BATCH-DSF-1` — nine Drama Fixes units merged together (one version bump
and one entry for the whole batch, per the swarm plan):

- `W1-studio-service-U1` personal link keys: mint, rotate, revoke, admin link (`link.js`).
- `W1-studio-service-U2` page data: session list, draft save, order answer validation (`page-api.js`).
- `W1-studio-service-U3` approvals on the service: publish, list, first answer wins, file stream (`approvals-api.js`).
- `W1-studio-service-U4` `questions.json` exported from `intake_card.py` plus a drift check.
- `W1-studio-page-U1` `service-client.js` installs `studioService` from the `#k=` link key.
- `W1-studio-page-U2` the order flow: home, one question per screen, draft, recap, Lock it in (`studio.js`).
- `W1-studio-page-U3` approval cards on the page: script, song pick, storyboard (`approvals-view.js`).
- `W1-studio-page-U4` the upload page reads the key from the link fragment.
- `W1-studio-page-U5` the admin page is served by the studio itself under `ui/admin/`.

No behaviour outside SPEC.md was added; every unit's own tests and the area
regressions pass on this batch head.

## v2.9.44 - 2026-10-13 - KV-FREE-TIER: check-ins stop burning the KV free tier

Cloudflare blocked KV writes (429) on 2026-10-12 and 2026-10-13: namespace
DS_STUDIO wrote ~1,125 times a day against the free tier's 1,000. Root cause:
every `POST /api/studio/checkin` (each box, every 2 minutes) wrote
`checkin:<client_id>` to KV, ~720 writes per box per day.

- The check-in time now lives in R2 (`checkin:<client_id>` in zhw-drama-studio,
  same key helper) and is re-saved at most every 20 minutes
  (`options.CHECKIN_SAVE_EVERY_MS`, kept under the 30-minute stale rule).
  Boxes still check in every 2 minutes; order pickup speed is unchanged.
  "Last check-in" on the page can read up to 20 minutes old.
- `options.lastCheckIn(objectStore, clientId)` and
  `inbox.checkIn(objectStore, ...)` take the R2 store; every caller in
  `index.js` passes it.
- Fixed: the box sends `{"orders": true}`, which `checkIn` treated as an order
  list and crashed on (`(orders || []).filter is not a function`). Only a real
  array is used as a list now; anything else reads the inbox.
- No box-side change. One Worker redeploy applies it to the whole fleet.

## v2.9.43 - 2026-10-12 - Direct client uploads

- Sign links for zhw-drama-studio and derive SigV4 signing keys using raw HMAC bytes through aws4_request.
- Send the first 16 bytes as an array and match the service's image/audio/video size limits.
- Add a streaming bridge upload command with fake-transport tests and secret-free receipts.
- Add the phone upload form at /uploads, with file bytes sent straight to R2.
- Deploy through a handler-only Worker entry and disable asset HTML redirects so /uploads serves the form directly.
- Keep the browser PUT CORS rule on every deploy, preserve optional upload keys, and correct the runtime-secret comment.
- Keep the existing projects/ retention rule. A clients/ prefix would also delete protected client files; intake-only retention needs a separate sweep or per-client rules.
- Owner requested Codex perform implementation and verification directly, without DeepSeek or Opus.

## v2.9.42 - 2026-10-12 - OPTIONS-LASTCHECKIN: the option line shows the check-in the box actually made

Fixes the live `Last check-in: not yet.` that `GET /api/studio/options`
returned to a client that had just checked in. ORCHESTRATOR-MEASURED,
2026-10-12 00:04:30-00:06:23: `POST /api/studio/checkin` with the paired key
returned 200 and stored `checkin:<client_id>` in KV, and `GET
/api/studio/options` with the same key returned 200 with
`Last check-in: not yet.`. Root cause, confirmed in code: `inbox.checkIn`
writes ONE record under `checkin:<client_id>`, while `options.optionLine` read
`record.last_check_in` off the `client:<id>` record - a field nothing writes
after the record is created (`keys.buildKeyRecord` and the service's own
`clientRecord` default both set it to `null`) - and the options route passed
only the client record.

- ONE shared key helper, `ids.checkinKey`, is now the only spelling of
  `checkin:<id>`: `inbox.js` writes through it, `options.js` reads through it.
  No other spelling of the key exists anywhere in the service.
- `options.lastCheckIn(store, clientId)` is the ONE reader of the stored
  check-in (moved there from `inbox.js`, next to the line that shows it, and
  built on that helper). `inbox.checkIn` keeps writing the same record through
  the same helper.
- `options.optionLine(record, nowMs, lastCheckMs)` now takes that value and
  falls back to `record.last_check_in` only for a record that already carries
  one, so the four approved strings are unchanged.
- Every `optionLine` caller uses that one source: `GET /api/studio/options`,
  `POST /api/studio/options` (admin) and `POST /api/studio/orders`
  (`option_line`). The orders route's `staleVerdict` caller already read the
  stored check-in and is unchanged, so the page line and the staleness clock
  can no longer disagree.
- Two tests added in `test/service.test.mjs`: after a check-in the page shows
  the real time and never `not yet` (and still says `not yet` for a client that
  has never checked in), and the check-in key has ONE producer that the page
  reads (aging the stored check-in through that key moves the page line).
  RED on main's `src` - the failing assertion is the literal
  `Last check-in: not yet.` after a check-in - GREEN on this head. Service
  suite 27/27; `prove/prove_service_boundaries.mjs` and
  `prove/prove_push_optional.mjs` both exit 0 before and after.
- No deploy and no Cloudflare write in this unit.
## v2.9.41 - 2026-10-12 - DEPLOY-2TOKEN: the deploy probes every step's scope before it writes, on a per-step token

The live Drama Studio deploy died mid-write. From main `5f321a96c`, `deploy.sh
deploy` had already run `ensure_bucket` and `ensure_retention` (a lifecycle PUT)
when the KV step failed with `FATAL Cloudflare API GET
/accounts/<acct>/storage/kv/namespaces?per_page=100 returned HTTP 401 ...
Authentication error` - a PARTIAL WRITE, with the secrets, the Worker deploy and
the DNS step never reached.

Read-only HTTP probes on 2026-10-12 (codes only, no value, no mutation) show the
split: the operator's Workers/R2 token = Workers scripts 200, Worker secrets 200,
R2 buckets 200, R2 lifecycle 200, KV namespaces 401, zone DNS records 403; the
operator's KV/DNS token = KV namespaces 200, zone DNS records 200, R2 buckets 403.

- **(1) Per-step token.** `CLOUDFLARE_DRAMA_STUDIO_API_TOKEN` stays the deploy
  token (account/zone resolution, the zone guard, R2, the secrets, the Worker
  deploy). A new OPTIONAL `STUDIO_KV_DNS_API_TOKEN` (manifest
  `env.kv_dns_token_var`) covers `ensure_kv_namespace` and `ensure_dns`; unset or
  empty it FALLS BACK to the deploy token. `cf_api` now authenticates with the
  variable named by `CF_TOKEN_VAR`, and the `cf_api_kvdns` wrapper repoints it for
  those two steps. No token value is printed anywhere.
- **(2) Read-only preflight.** Before the first write, `preflight()` probes every
  step's scope with its ASSIGNED token, GET only: Workers scripts list, Worker
  secrets list (when the Worker exists), R2 buckets list and the R2 lifecycle GET
  (when the bucket exists) on the deploy token; KV namespaces list and zone DNS
  records list on the KV/DNS token. Any non-200 fails the deploy BEFORE any
  mutation, in one line naming the step and the variable (for example
  `FATAL preflight: kv-namespace needs a token with KV namespaces read/write;
  STUDIO_KV_DNS_API_TOKEN (falling back to CLOUDFLARE_DRAMA_STUDIO_API_TOKEN) got
  HTTP 401`). `--dry-run` with a deploy token runs the same probe; without one it
  plans it, still making no call.
- **(3) Three new `--self-test` cases**, each RED without its part of the fix and
  GREEN with it: PT-a (a KV probe answering 401 fails in preflight, naming
  `kv-namespace` and `STUDIO_KV_DNS_API_TOKEN`, with ZERO write calls recorded),
  PT-b (KV/DNS variable unset: the KV and DNS probes fall back to the deploy
  token), PT-c (both set: KV and DNS use the KV/DNS token and every other probe
  uses the deploy token). Every existing case stays green.
- `deploy.manifest.json` records `env.kv_dns_token_var` with its fallback note;
  `DEPLOY.md` documents both variables by NAME, the step-to-token table, the
  preflight and the operator recipe. No token was created, rotated or modified by
  this unit, and it made no Cloudflare write and no real deploy.

---

## v2.9.39 - 2026-10-11 - CHECKIN-UA: the shared bridge sends the studio's one explicit User-Agent

Cloudflare in front of `https://studio.zerohumanworkforce.com` refuses Python's
default User-Agent (`Python-urllib/3.x`) with HTTP 403 and the body
`error code: 1010`; the same request with an explicit User-Agent gets 200.
Measured read-only on 2026-10-11 (`GET /api/studio/health`, no key): bare
`urllib.request.urlopen` -> 403 `error code: 1010`, the same call with an explicit
User-Agent -> 200 `{"ok":true,"service":"drama-studio-service","version":"0.1.0"}`.
A bridge or pairing script shipped without the header cannot check in at all.

- `shared-bridge/studio_bridge.py` now defines ONE constant,
  `STUDIO_USER_AGENT = "drama-studio-client/2.7.48 (+https://studio.zerohumanworkforce.com)"`,
  and `_http` sends it on every request it builds. No other behaviour change.
- Paired 999 commit: `.claude/skills/drama-studio/studio_bridge.py` carries these
  exact bytes (sha256 equal on both sides, recorded in the twin fingerprints), and
  `studio.py` / `studio_check.py` in that repo carry an identical literal constant
  at their own request sites; the 999 prover `prove/prove_user_agent.py` asserts all
  three strings are equal before it drives a request.
- `shared-bridge/checks/run_checks.py` gains check F. It starts a fake studio on
  `127.0.0.1` (localhost only: no key, no live host, no client box) and drives the
  real `studio_bridge._http` at it, requiring both the 200 and the exact string on
  the wire. Two controls on the same server: bare urllib must be refused 403/1010
  (the instrument discriminates), and a planted-bad bridge copy with the header line
  removed must be refused too. Red on main, green on this head.
---

## v2.9.40 - 2026-10-11 - CHECKIN-500: a non-studio client_id is refused, never a Worker crash

Fixes the live `AF-DS-ID-INVALID` crash on `POST /api/studio/checkin`. Live
evidence (ORCHESTRATOR-MEASURED, `wrangler tail drama-studio-mini-app`,
2026-10-12T02:31:51Z, one POST with the paired operator key): HTTP 500
`error code: 1101`, outcome `exception`, name `Error`, message
`AF-DS-ID-INVALID`, stack `scopePath <- inboxPath <- readInbox <- checkIn <-
handle`. Root cause, confirmed in code: `POST /api/studio/admin/pairing-code`
stored ANY `client_id` string, so the operator pairing stored a non-studio
client id such as a human-readable name — not a studio-invented id (`ids.js`
`CLIENT_ID_RE` `^c-[0-9a-f]{32}$`). `POST /api/studio/pair` copied it into the
machine key record, `authorizeClient` returned it unchanged, and `readInbox ->
inboxPath -> scopePath` threw; nothing caught it and the Worker crashed. `GET
/api/studio/options` "worked" with the same key only because it builds no
scoped path.

- **(a) the admin door refuses a non-studio id.** `POST
  /api/studio/admin/pairing-code` now checks `isClientId(body.client_id)` and
  returns `400 AF-DS-ADMIN-INVALID` before minting — no code is created and
  nothing is stored.
- **(b) one refusal point on the key path.** `authorizeClient` (`isolation.js`)
  now refuses a stored key whose `client_id` fails `isClientId`, in ONE place,
  returning `AF-DS-ID-INVALID`; `index.js` answers it as a structured `401`
  JSON error ("This key is not bound to a studio client id. Pair this computer
  again.") instead of throwing from `scopePath`. Every key-authorized route is
  covered, so a pre-existing bad-id key (the operator Mac's current key) can no
  longer crash any route.
- **(c) a missing inbox object is an empty inbox.** `checkIn` with a valid
  `c-<32 hex>` client and no inbox object returns `200`, `line: null`, and
  records the check-in.
- **Tests** (`mini-app/service/test/service.test.mjs`): the live failure
  reproduced (admin refusal + a pre-seeded bad-id key refused on check-in and on
  another key route), missing-inbox `200`, and the one-waiting-order
  `DRAMA_ORDER` line. Suite 25/25 green; `prove_service_boundaries.mjs` and
  `prove_push_optional.mjs` green. `skill-version.txt`, SKILL.md frontmatter and
  this entry land in ONE commit (G3).

## v2.9.37 - 2026-10-11 - OB-KIE-2: kie-rate-limit.md records the recordInfo and discovery limits

Joint-plan OB-KIE-2 (line 1066) paired change. The parity doc
`references/kie-rate-limit.md` gains the two limits KIE's official `kie-models`
skill "Rate limits" section names alongside the createTask cap. The doc change,
the SKILL.md frontmatter version, `skill-version.txt` (G3), and this entry land in
ONE commit - no bump-only commit.

- `references/kie-rate-limit.md` now states all three limits with a per-number
  source: `createTask` 20 per 10 seconds per account (KIE docs "Rate Limit"),
  `recordInfo` **10 per second per task**, and discovery (`models`, `schema`,
  `price`, `success-rate`) **1 per second shared**. Both new numbers come from KIE's
  `kie-models` "Rate limits" section (fetched 2026-10-09), already recorded in this
  repo at `07-kie-setup/references/kie-official-agent-docs-digest.md` rule 9 and
  `07-kie-setup/references/kie-common-rules.md` rule 3. No number was invented.
- The stale bullet "Status polls are not named in the limit" is replaced by the
  `recordInfo` 10-per-second-per-task rule, so the doc no longer contradicts itself.
- Paired change: the 999 twin
  `.claude/skills/drama-song-ad-factory/references/kie-rate-limit.md` is byte-identical
  to this file (sha256 `e15a7592e5dff36bb032519c5f25decd7cc54628d3c0edca392cf4dd814df3aa`).
## v2.9.38 - 2026-10-11 - DEPLOY-FIX: the Drama Studio deploy runs as ONE command

Fixes the five `mini-app/deploy/deploy.sh` defects the live Drama Studio deploy
found (evidence: `finish/DEPLOY/lanes/DEPLOY-U1-lane/DEPLOY-U1-evidence.md`,
"Exact repository fix needed"). The live Worker was already up (version
`588491b2-...`) via a hand-built lane config; these fixes make the committed
`deploy.sh` reproduce that deploy in one command. `deploy.sh` and
`deploy.manifest.json` and `DEPLOY.md` changed; the U2-owned `worker/wrangler.toml`
is untouched.

- **(1) `main` did not resolve.** `deploy_worker()` wrote the throwaway config
  into `$TMPDIR`, but the committed `main = "src/index.js"` is relative to the
  config's own directory, so `wrangler deploy` failed with *"The entry-point file
  at \"src/index.js\" was not found."* The temp config is now built by a pure
  `write_resolved_config()` helper that rewrites `main` to the **absolute** path
  of `mini-app/service/src/index.js`. The committed toml is never touched.
- **(2) account skipped when the zone id was supplied.** `resolve_account_and_zone()`
  only called the API inside `if [ -z "$R_ZONE_ID" ]`, so a supplied
  `STUDIO_ZONE_ID` left the account unresolved and the live G4 guard failed. The
  account is now resolved **independently** of the zone (fetch the zone by id and
  read its `account.id`); an empty result still fails G4 hard.
- **(3) `DS_STUDIO` KV namespace never resolved.** The toml's
  `<PLACEHOLDER_KV_NAMESPACE_ID_DS_STUDIO>` (and its preview id) reached wrangler
  unresolved. New `ensure_kv_namespace()` finds the namespace **by title** via the
  Cloudflare API and **creates it only if absent**, then resolves its id into the
  temp config — no `<PLACEHOLDER_*>` id is left.
- **(4) incomplete secret list.** `set_secrets()` set only the manifest's
  `R2_*` names, so the service's real bindings were never set. The manifest now
  marks `DS_ENROLLMENT_SECRET`, `DS_ADMIN_KEY` and `R2_ACCOUNT_ID` **required**
  (the service README bindings) and `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`
  **optional**. A missing required secret fails the deploy closed; a missing
  optional one only warns — the R2 S3 keys are **deferred until presign ships**
  (the service does not read them at runtime) and are documented as needing a
  token with *API Tokens Write*. No value is ever printed.
- **(5) no DNS step.** The route host had no record. New `ensure_dns()` ensures a
  **proxied CNAME** `studio.zerohumanworkforce.com -> zerohumanworkforce.com`,
  created only if absent, and **refuses any zone but the guarded one**
  (`require_guarded_zone`).

Each defect has a `--self-test` case that is RED without its fix and GREEN with
it (absolute `main`; KV id resolved into the config and created-only-if-absent;
account resolved with a supplied zone id; required-vs-optional secrets; DNS
refuse/create/skip). `--self-test` and `--dry-run` stay offline — no token, no
curl, no wrangler mutation (the API and wrangler are stubbed/plan-only). No
Cloudflare write and no real deploy in this unit.

---

## v2.9.36 - 2026-10-11 - U17: the GoHighLevel text/e-mail sender (version 1, no live send)

ONE new module, ONE delimited block in the ONE battery, and the single skill
version bump that G3 requires for a skill-content change (this same commit).
Nothing outside skill 75 changed; the repository root `/version` is untouched.

- New `scripts/core/ghl_sender/` (module, package init, README): the version-1
  GHL sender the studio uses to hand a finished video's LINK to a client and to
  send the follow-up NUDGES over the client's own GoHighLevel rail. Two
  channels, ONE endpoint: `text` -> `POST /conversations/messages` type `SMS`
  (`contactId`, `locationId`, `message`) and `email` -> the same endpoint type
  `Email` (`contactId`, `locationId`, `subject`, `html`, `emailFrom`,
  `emailTo`), with `Version: 2021-04-15` and `Content-Type: application/json`.
  This is the canonical shape the repo already documents
  (`38-conversational-ai-system/references/ghl-api-quick-reference.md`) — no
  second endpoint, sender, proxy, adapter or dashboard was added.
- TOKEN-PRESENCE GATING: `token_present()` checks the location-token env NAMES
  and returns a boolean; a send with no token REFUSES with
  `AF-U17-TOKEN-MISSING` BEFORE anything is built or transmitted, and the
  transport is never called. ONLY the presence check exists — the token VALUE is
  never read into a variable this module returns, stores or prints;
  `Authorization: Bearer <token>` is attached by the injected transport from the
  runtime's own secret store, so a secret never enters this module's request
  bytes, receipts or output.
- NO LIVE SEND, NO TEST SEND: the module opens no socket. The wire call is a
  TRANSPORT the runtime injects, and there is no default live transport — a send
  with none injected REFUSES with `AF-U17-TRANSPORT-MISSING`. `build_request()`
  produces the exact non-secret request bytes (compact JSON, deterministic) and
  `build_receipt()` returns ONE receipt per message (channel, type, purpose,
  contact/location, url, the request `body_sha256`, the rail's `messageId` /
  `conversationId`, `sent_at`) — never a secret, never the body verbatim.
- The CLI `build` verb prints the exact request it would send; the `send` verb
  refuses with exit 5 (there is no live transport here).
- Proof: `HOME=$(mktemp -d) python3 75-drama-song-ad-factory/scripts/core/music_qc/test_wwfix_u1.py </dev/null`
  — 30 new U17 checks, all green, inside the one existing battery (no second
  suite). Positives: the text and e-mail bodies are byte-exactly canonical; a
  token-present send calls the injected stub exactly once and returns one
  receipt. Negative controls: no token sends nothing and never calls the
  transport; a request carrying the secret is flagged by the same detector that
  clears a real one; a built request and a receipt both carry no Authorization
  header and no token value.
- Version markers: `skill-version.txt` and the `SKILL.md` frontmatter `version:`
  land at v2.9.36 in this same commit, bundled with the real content (G3 gates a
  skill-content change on that bump).

## v2.9.35 - 2026-10-11 - U10-EXTRAS-U1: optional Telegram button, card link and measurement view, native fields first, OFF by default

Joint plan section 5, row **U10 extras** (verbatim: "Optional Telegram
button/card link/measurement view, native fields first"; version table line
832). One new module and its own suite; nothing existing is edited, so the
required version-0 delivery is untouched.

- New `scripts/core/choice_card/intake_card/optional_extras.py` — the optional
  surface, OFF by default. `extras_enabled` is true only for the exact
  on-values `"true"` / `"1"` (unset, empty, `"false"`, `"yes"`, `"TRUE"` all
  stay off). With extras off every function returns its input UNCHANGED, so the
  required GHL-first delivery and every required message/card/status path are
  byte-identical; the module imports the required delivery nowhere.
- Native fields first: the **Telegram button** is the native Bot API
  `reply_markup.inline_keyboard` field appended to the payload the existing
  message pattern already builds (`intake_card.telegram_payload`); the **card
  link** is one `Open in Drama Studio: <url>` line reading the card's OWN
  native `studio_url` first, the environment only as a fallback; the
  **measurement view** renders ONLY the status counts a caller already has —
  no store, no page, no scheduler, no network call. No link or button is ever
  invented (extras on + no URL -> nothing added).
- A caller that DEMANDS an extra while extras are off gets a refusal with the
  named code `AF-DS-EXTRAS-DISABLED` and zero side effects; the CLI exit code
  is `4` (ok `0`, error `1`), the same non-zero exit the skill's other gates
  use. No send, no credential, fixture-only.
- Proof: new `scripts/core/choice_card/intake_card/test_optional_extras_u10x.py`
  (40 checks green) proves the off-by-default truth table, the native-field
  additions, the append/no-op card link with native-first URL, the
  counts-only measurement view, no input mutation, the named refusal, that the
  module never imports the required delivery, and four real CLI subprocess
  legs with true exit codes (0 ok, 4 refused).
- Version: `skill-version.txt` and the `SKILL.md` frontmatter `version:` land
  at v2.9.35 in this same commit (G3 gate). The repository root `/version` is
  unchanged.

## v2.9.34 - 2026-10-11 - U9: talk-to-a-person / send-a-question code path (no live send)

ONE real-content commit whose parent is the live head of `main`
(`0f6e6a8b`, read at build time). Adds the version-1 client question path and
bumps Skill 75 exactly once, inside this one commit; the repository root
`/version` and root `CHANGELOG.md` are unchanged.

- `scripts/core/choice_card/intake_card/person_question.py` - the U9 code path.
  A client's free-text QUESTION or TALK-TO-A-PERSON request builds ONE payload,
  is validated at the trust boundary (`unknown-kind`, `empty-text`,
  `text-too-long`, `missing-run-id`, `unknown-channel`, `unknown-epic`), and is
  ROUTED to an epic: an explicit epic wins, else the first topic keyword match
  (billing / song / storyboard / delivery), else the talk-to-a-person KIND
  (handoff), else the default intake epic. Routing is load-bearing -- the epic
  decides the target when the caller names none.
- NO live send. `deliver()` reuses the skill's ONE channel-neutral send path
  (`choice_card.intake_card.channel_send`, U11) with a RECORDING sink, so the
  stub records exactly what WOULD have been sent (the `openclaw message send`
  argv) and the real transport is never reached; the record says `sent: false`.
  With a run_dir it appends one JSON line per question to
  `<run_dir>/control/person-question.jsonl`.
- Fixtures: `person_question_fixtures.json`. Test:
  `choice_card/intake_card/test_person_question_u9.py` (11 checks); one
  delimited block joins the battery `music_qc/test_wwfix_u1.py`.

## v2.9.33 - 2026-10-11 - WORKER-CFG: ship mini-app/worker/wrangler.toml (closes the U2/U4 config gap)

ONE real-content commit whose parent is the live main head
(`0babaac894f88f8a49b629b3abde7bc1e47985d3`, read at build time). Skill 75 is
bumped exactly once, inside this one commit; the repository root `/version`
and root `CHANGELOG.md` are unchanged.

- Ships the missing Cloudflare Worker config `mini-app/worker/wrangler.toml`
  that U4 deploy.sh preflight line 173 refuses without: "FATAL preflight:
  missing .../worker/wrangler.toml (U2 service contract). Cannot deploy.". U2
  deliberately shipped no wrangler.toml and U4 #1815 shipped only
  `mini-app/deploy/` files, so the file belonged to neither unit.
- Content: `name = "drama-studio-mini-app"`, `main = "src/index.js"`, route
  `studio.zerohumanworkforce.com/*` on zone `zerohumanworkforce.com`,
  `compatibility_date = "2024-09-23"`, `<PLACEHOLDER>` `account_id`; one R2
  binding `DRAMA_STUDIO` -> bucket `zhw-drama-studio`; one KV binding
  `DS_STUDIO` with `<PLACEHOLDER>` id/preview_id; `[observability] enabled`.
  Both binding names are exactly what `service/src/index.js` reads. No real
  id; secrets stay out of the file (`wrangler secret put`); the
  zerohumanworkforce.com zone landmine is documented in the file.
- No deploy.sh edit: U4's deploy.sh resolves only
  `<PLACEHOLDER_CF_ACCOUNT_ID>` and has no KV-namespace step and no
  `R_KV_ID`/`R_PREVIEW_ID` variables, and kv/r2 creation is out of scope for
  this unit, so the KV placeholders stay the committed contract (same shape as
  the Book Writer config).

## v2.9.32 - 2026-10-11 - WW-29: optional vocalise, no stale early-hook rule, consistent R&B Flow direction, one reconciled fewer-words budget

ONE real-content commit whose parent is the live head of `unit/WWC-U1`
(`6341e24c3d`, read at build time), joining the three parallel builders'
patches (WW29-U1 documents, WW29-U2 template/recipe/option-(ii) budget,
WW29-U3 music director) with the integrator's cross-builder joins into a
single coherent change. Skill 75 is bumped exactly once, inside this one
commit; the repository root `/version` and root `CHANGELOG.md` are unchanged.

- WW-29 change list: the mandatory "two long held wordless notes" opening is
  removed and the vocalise is OPTIONAL, never a forced lead-in (the WW-16
  3-second opening ceiling is kept and still refuses a DECLARED long/held cue);
  the stale hook-in-the-first-fifteen-percent rule is removed from the recipe,
  the model data and the music-style data, and the measured hook-placement /
  payoff doctrine stands (the hook is the payoff, placed at/after the build-up
  and at the story beat where its words become true); required cast, shift,
  hook, ending and negative clauses survive the final cap and an overflow
  REFUSES with a named reason rather than deleting a clause; `negative_tags`
  is transmitted in the final `request["input"]`; evidence confidence is
  documented (DOCUMENTED / CONSISTENT / LORE).
- R&B Flow rap/sung direction is consistent across data, recipe, director and
  docs: `suno_recipe.is_rap_style` reads a style's OWN data so the label
  "R&B Flow" and the id "rnb-flow" judge identically (the base hard-coded
  `RAP_STYLE_IDS` matched the bare id only, silently switching the rap-negative
  guard off for the label).
- OPTION (ii): `words_fit._fewer_words_budget` now prices the non-sung budget
  with rap words at the rap rate for a rap style, so the "fewer words" option
  and `length_formula.plan` are ONE rule on an R&B Flow card; a non-rap style's
  budget is byte-identical to the base; the per-verse rap floor is unchanged and
  a card that cannot hold the two-verse floor is still refused.
- Integrator joins: `suno_recipe/test_suno_recipe.py`'s `test_sheet_rules` no
  longer pins the removed vocalise mandate (it is replaced by a positive control
  proving the no-vocalise sheet is legal, still refused by `prepare` without its
  length); `references/prompt-templates/music/{rnb-flow,soul-ballad,soul-rise}.json`
  skeleton rules no longer carry the stale "Hook 1 by 15%" rule or force a
  vocalise.
- Documents: `SKILL.md`, `INSTRUCTIONS.md` and `references/stage-runbook.md`
  reconcile to the same doctrine, name the real `suno_recipe.style_text` builder
  (the phantom `prompt_templates.suno_parts` is gone), and state the five-gate
  delivered-audio boundary (WW-21's `song_dispatch.accept_audio_results`, never
  a sixth gate).
## v2.9.31 - 2026-10-11 - WWC combined branch C: WW-25 copy-first archive, WW-26 three complete briefs, WW-27 ensemble character bible and distinct voices, WW-28 causal plot and earned hook

ONE real-content commit whose parent is the live head of `unit/WWB-U1`
(`9b4b30df07`, read at build time), joining the three parallel builders'
patches (WWC-U25, WWC-U26, WWC-U27) with the carried WW-28 patch
(`wave3/carry/WW-28.patch`) into a single coherent change, and finishing
WW-28's DEPENDS-ON-WW-27 clause on WW-27's cast model. Skill 75 is bumped
exactly once, inside this one commit; the repository root `/version` and root
`CHANGELOG.md` are unchanged.

- WW-25 (copy-first archive): the existing shipping writer
  `song_choices.deliver_choices` copies each approved take into a NEW
  noncolliding `<run>/song-choices/archive/<stamp>` folder, verifies every
  copied file's sha256 against its source, writes a complete receipt and only
  THEN publishes. Originals are never deleted or moved; a prior archive is
  never overwritten; a copy fault or hash mismatch refuses with both sides
  preserved and nothing published. No parallel archive module was created.
- WW-26 (three complete briefs, including the upbeat option):
  `song_choices/variants.json` carries three COMPLETE briefs per style (all ten
  directions each, exactly one explicit upbeat role), assembled per variant
  through `suno_recipe.brief_style_text`; `_require_three` checks complete
  treatments, not identifiers; `_check_three_briefs` refuses
  MISSING_DIRECTION / GENRE_SUBSTITUTION / UPBEAT_DIRECTION /
  SHARED_CORE_PLUS_SUFFIX / STYLE_TOO_LONG on the exact serialized
  `request["input"]["style"]` before spend.
- WW-27 (ensemble character bible and distinct voices): the new
  `character_bible` cast model (seven character fields, six voice-direction
  fields, ensemble by default, a speaking villain or foil that receives a
  consequential reply, undeclared speakers and a single-voice ensemble style
  refused) is wired into `song_contract.check_sheet`,
  `suno_recipe.build_request`/`guard_request`, `music_director.build_generate_request`
  and `lyric_writer.validate_lyrics`; `qc_voice_match.line_voice_fit` decides a
  second voice on TIMBRE, beyond pitch.
- WW-28 (causal plot and earned hook): `story_arc` gates the nine causal
  fields, the fiction/testimonial split, the mood-board plot, the exact
  payload closing call, the exact hook line versus the refrain, two-declared
  versus companion-line counting and maker self-approval; the twelve-beat /
  eight-stage / fifteen-stage mappings are asserted preserved.
- WW-28 DEPENDS-ON-WW-27 (finished here): the independent non-maker's
  'exchanged replies' leg now judges a declared cast on WW-27's model --
  `character_bible.traded_replies` over `speaker_turns` -- and reports
  `cast_model: "ww27-ensemble-cast"`; with no cast declared it keeps the base
  speaker-prefix leg unchanged.

## v2.9.30 - 2026-10-11 - WWB combined branch B: WW-22 ordered approved-story-line matching, WW-23 both musical transitions, WW-24 measured-only evidence provenance

ONE real-content commit whose parent is the live head of `unit/WW30-U2`
(`c6dc6e9d41`, read at build time), joining the three parallel builders'
patches (WWB-U22, WWB-U23, WWB-U24) into a single coherent change. This branch
is skill-75 only: the repository root `/version` and root `CHANGELOG.md` are
unchanged (the same shape #1858 used). WW-28 is NOT on this branch -- per
`WW-ROUND3-FIX-PLAN.md` line 100 it depends on WW-27 (combined branch C, above
this branch) and its patch is carried forward to `wave3/carry/WW-28.patch`.

- WW-22 (ordered approved-story-line matching): `normalize_approved_words`
  keeps repeats and refuses a set; `ordered_match` matches the approved words
  against the observed words IN ORDER, replacing the multiset; `ordered_run_match`
  is the ONE contiguous-run matcher `first_plot_line_s` now reads through; and
  `text_coverage_gate` matches in order. `song_contract.check_sheet` carries the
  exact approved opening line into the request/evidence context. `up\n\n` stays
  lexical.
- WW-23 (both musical transitions): two approved semantic anchors (drop, return)
  and two distinct seam timestamps (`boundary_s`, `return_boundary_s`); the
  return-energy check is SYMMETRIC; D3 judges BOTH seams; the pre-generation gate
  `check_pace_plan` / `check_pace_style` / `pace_provider_leak` blocks a missing
  seam, a reused boundary and a one-direction final style before any spend;
  numbers stored once in `acceptance-profile.json` `ww_wave.pace_change`.
- WW-24 (measured-only evidence provenance): `timing_guard` measures no audio and
  validates each D1..D5 result's evidence record against the take binding;
  `story_coverage.script_report` separates lexical estimate, music-only allowance
  and runtime, refusing `INFLATED_SECONDS_OF_WORDS`; `spoken_share.measured_runtime_s`
  refuses a plan as physical runtime. No sixth audio gate.
- IN-BRANCH WIRING (WW-23 -> WW-22): `song_contract.check_pace_style` now binds
  its anchor presence through WW-22's `story_coverage.ordered_run_match` instead
  of a raw substring scan.

Every guard is reachable from the production path; no guard weakened, no floor
lowered, no assertion's intent changed, nothing skipped or xfailed. Base
boundaries intact: WW-21's fail-closed acceptance boundary, the per-verse rap
floor, `parse_lyrics` storing the bracket cue under `"cue"`, the pace clause LAST
in the assembled `input.style`, and the createTask contract with its
`LEGACY_FLAT_CONTRACT` guard.

## v2.9.29 - 2026-10-11 - WW30R re-cut: pull request 1856's createTask migration stacked as draft `unit/WW30-U2` on live `unit/WWR3INT-U2`, with the three opus-fail test fixes

ONE real-content commit whose parent is the live head of `unit/WWR3INT-U2`
(`531f5b390f`, read at build time). It carries pull request #1856's content
delta (`871eab98c..d6b3f45c`, its own single commit, read live at
`d6b3f45c304bbc100edf13086e7b8007525e97df`) onto that base as ONE coherent
change, and keeps EVERY change the base already carried -- WW-21's fail-closed
boundary, the WW-16 opening-vocalise ceiling, `parse_lyrics` storing the
bracket cue under `"cue"`, and WW-07's pace clause LAST in the assembled
`input.style` (the drop and the return, after the ending and arrangement
clauses). `suno_recipe.build_request` keeps BOTH signatures: `pace_plan` (WW-07)
AND `callback_url` (WW-30), and `song_choices.build_requests` still appends the
pace clause after the variant clause -- now on the nested `input.style`.

The three suites the opus check returned FAIL on at `d6b3f45c` are fixed INSIDE
this same commit, each still testing what it tested, against the shape
production actually emits:

- `sung_hook/test_hook_placement.py` reads `request["input"]["lyrics"]`, not the
  retired top-level `request["lyrics"]` (KeyError 'lyrics').
- `suno_recipe/test_voice_tags_u5.py` reads `request["input"]["vocal_gender"]`,
  not the retired top-level field (which read `None`).
- `sung_hook/test_no_skip_and_goldens.py`'s golden-sheet builder emits the
  nested createTask envelope instead of the retired flat `/api/v1/generate`
  payload (`REQUEST_ENVELOPE_REJECTED: LEGACY_FLAT_CONTRACT`).

The `LEGACY_FLAT_CONTRACT` guard and every other guard are unchanged; no
assertion was weakened, skipped, xfailed or re-pointed. Skills 75 and 68 still
build and validate exactly ONE music contract: POST `<KIE host>/api/v1/jobs/createTask`
with the outer `model` `ai-music-api/generate`, a TOP-LEVEL camelCase
`callBackUrl` and a nested snake_case `input`; `input.lyrics` is the single
approved lyrics source (a competing `prompt` is `COMPETING_LYRICS`); the legacy
flat route is RETIRED with no fallback. The individual V6-family VALUE is
recorded `UNDETERMINED` with UNRANKED candidates `V6`, `V6_MINI`, `V6_WILD`;
the task-ID acknowledgement nesting is reported UNVERIFIED. Proved with the
zero-spend fake transport only (`test_music_createtask_ww30.py`): the exact URL
and serialized payload are captured, each refusal is asserted by name, and
success / rejection / timeout / malformed acknowledgement / multiple returned
tracks are each exercised. No provider call, nothing spent.

Bundles the Skill 75 v2.9.29 bump (read live from the base's skill-version
v2.9.28) and the root v27.1.11 release roll (read live from the base's
`/version` v27.1.10) with its CHANGELOG entry, together in the same commit.

## v2.9.28 - 2026-10-11 - WWR3INT2 re-cut: pull request 1855 onto live main (WW-21 kept whole) on the 88-second R&B Flow card

ONE real-content commit. It carries the FULL CONTENT of pull request #1855's
three commits (`9e33dd85`, `90961735`, `c43b8117`) -- the WW-PREVENT-RECURRENCE
wave with its WW-16 and WW-07 production fixes -- onto live `origin/main`
(`fdb7bf1af`, read at build time, which already holds WW-21 via the batch merge
`197ee673a`). The version bump for `skill-version.txt`, the `SKILL.md`
frontmatter and this entry ride inside the same commit -- never a bump-only or
changelog-only commit.

Overlaps with WW-21 were resolved so that **neither side wins silently**:

* `song_choices/song_choices.py`, `song_dispatch/song_dispatch.py`,
  `music_qc/test_wwfix_u1.py` and `core/acceptance-profile.json` are the four
  files both sides touched.
* `song_dispatch.song_dispatch._finish` keeps **WW-21's total, fail-closed
  boundary** (empty gate set blocks with `EMPTY_GATE_SET`, a malformed record
  blocks, a missing required gate blocks) AND the WW-08 behaviour #1855 relies
  on: a required gate that did not run is recorded in `gates` as `UNMEASURED`
  and the same names stay in `missing`; `not_applicable` carrying its style flag
  advances. `required_gates` is carried for the delivery decision
  (`take_accepted`).
* WW-21's whole aggregation and evidence-binding block (`accept_audio_results`,
  `take_binding`, `record_acceptance`, `acceptance_from_run`,
  `acceptance_refusal`, the `RAP_NEITHER_PLANNED_NOR_MEASURED` loophole
  closure, `_MIN_AUDIO_RESULTS`) is present, and #1855's
  `take_accepted` / `constituent_receipt` / `constituent_ok` are present beside
  it. `story` and `timeline` were added to `GATES` because #1855's judge emits
  them for every take.
* `acceptance-profile.json` carries both WW-21's `audio_results` block and
  #1855's `ww_wave` block.

Production fixes that survive and are re-proved on this head:

* **WW-16** -- `suno_recipe.parse_lyrics` stores the bracket cue text under the
  key `"cue"`, so `check_lyric_sheet`'s vocalise-ceiling guard is reached by the
  production path through `song_dispatch.validate_request`; the fixture
  `scripts/core/suno_recipe/fixtures/one-check-lyrics.txt` line 5 is refused
  before spend.
* **WW-07** -- in `song_choices.build_requests` the variant / arrangement clause
  is placed so the pace drop and the return are the LAST text in the assembled
  `request["style"]` on all three variants; the `build_requests` docstring reads
  "AFTER the ending and arrangement clauses"; and a test asserts, on the
  ASSEMBLED `request["style"]`, that the pace offset is GREATER than the
  Arrangement offset.

The rapped R&B Flow fixtures in `music_qc/test_wwfix_u1.py`,
`song_choices/test_song_choices_fu_song.py`,
`song_choices/test_song_wire_fu_song2.py` and `suno_recipe/test_suno_recipe.py`
moved from the 58-second card to the **88-second card** (option (i) of the
orchestrator's decision). WW-01 made the rap floor PER VERSE, and below 88 s no
sheet clears BOTH the per-verse floor AND the style's sung-share target at once;
at 88 s the shipped golden `suno-90s-rnb-flow.json` clears every gate the same
way. The rap floor and every other guard is untouched -- nothing was lowered,
loosened, skipped, xfailed or routed around, and no assertion's intent changed.

`/version` (the repository root version, `v27.1.10`) is UNCHANGED: `v27.1.11` is
reserved for the WW-30 re-cut that stacks on this one. `scripts/bundle-release-in-branch.sh`
was NOT run, because a prior quality check measured it as `REPO_ROOT`-scoped (it
would have changed the root `/version` and the root `CHANGELOG.md`); the skill-75
files were bumped by the same shape #1854 used instead.

Zero paid provider calls: every suite drives fake transports only. No provider
was called, nothing was spent, no song or video was regenerated.

---

## v2.9.27 - 2026-10-11 - WW-21: the total fail-closed acceptance boundary (five bound delivered-audio results, zero purchases on every refusal)

WW-21 is the **aggregation and evidence-binding boundary that runs before
spend**. It is **not a sixth delivered-audio gate**: it measures no audio and
claims no audio-quality outcome. The operator plan names exactly five audio
gates -- D1 real rap, D2 story start, D3 both pace changes, D4 three audibly
different versions, D5 more than one character voice -- and WW-21 decides only
whether the five results *carried to it* may advance.

`scripts/core/song_dispatch/song_dispatch.py`

* `_finish` is now **total**. Before it, `_finish({})` returned `PASS`: an
  empty gate set was indistinguishable from a perfect take, and an `UNKNOWN`
  or `UNAVAILABLE` gate verdict was silently ignored (`FAIL`, `FLAG` and
  `UNMEASURED` were the only verdicts it understood). Now `FAIL`, `FLAG`,
  `UNMEASURED`, `UNAVAILABLE`, `UNKNOWN`, an unrecognised verdict, a missing
  or empty verdict string, a non-mapping record, a **missing required gate**,
  an **empty gate set** and any exception raised while reading the mapping all
  block, and only `PASS` advances.
* New `accept_audio_results(results, binding)` -- the total, fail-closed
  aggregation over the five carried results -- plus `take_binding` (the take's
  own export sha256 + creative revision + profile revision),
  `record_acceptance` (the single writer), `acceptance_from_run` and
  `acceptance_refusal`. A result may not advance on absent, empty,
  non-mapping, malformed or **stale** evidence; a **manually relabelled**
  binding (`source: manual`, a bare string, a missing key) is refused as a
  binding.
* The **rap-style no-planned/no-measured-rap loophole is closed.** The
  `rap_share` branch used to `PASS` with the detail "no rap planned, none
  measured", so an R&B Flow take whose plan declares no rap word count and
  whose audio measured 0.0 s of rap advanced as if the rap gate had been
  satisfied. It is now `RAP_NEITHER_PLANNED_NOR_MEASURED` and the take cannot
  pass; the WW-21 boundary blocks it outright.

`scripts/core/song_choices/song_choices.py`

* The block reaches the **real delivery boundary**: the moment a variant has a
  produced take under `<run>/music/takes/<variant>/` (the folder the production
  generator fills), a WW-21 acceptance record is required for it, and until
  that record is all-`PASS` the take is **never offered, never picked and never
  purchased**. `deliver_choices` (offer), `record_pick` (pick) and
  `refusal`/`dispatch_refusal` (the `kie_dispatch` purchase seam) all consult
  the same one implementation, so the gate and the receipt cannot drift.

`scripts/core/acceptance-profile.json`

* `audio_results` names the five required results and their verdict
  vocabulary. **PROPOSED (WW-21, 2026-10-11):** `minimum_count = 5` is the
  COUNT OF THE FIVE GATE NAMES THE PLAN ALREADY NAMES -- a proposed value, not
  a measured limit, and **not a number Trevor set**. It is labelled PROPOSED
  here, in the code (`_MIN_AUDIO_RESULTS`) and in the test docstring, and it
  moves only when the plan's own gate list moves.

`scripts/core/music_qc/test_wwfix_u1.py`

* The positive control (all five valid results pass, zero purchases) and every
  negative control the plan names: remove one result, inject `UNKNOWN`,
  `UNAVAILABLE` and `UNMEASURED`, a stale digest, a malformed non-mapping
  record, a removed required gate, a manual relabel and `_finish({})`. Each
  BLOCKS with its named reason and asserts **zero purchases**.
* The dead-guard proof: `cmd_generate` -- the production entry point -- builds
  a plan with no `words` key at all, so the rap guard is reached through the
  real call path (`cmd_generate -> one_variant -> run_takes -> judge_take ->
  _finish`), its input is printed at that call site, and it fires on the value
  that path produces.

No threshold, check, test or guard was weakened, skipped, xfailed, deleted or
re-run to green. No paid call is made anywhere in this unit; nothing was
regenerated.

## v2.9.26 - 2026-10-11 - empty-home test: make the core copy deterministic so the `__pycache__` race cannot fail `QC static invariants`

The required check `QC static invariants`, step "Skill 75 empty-home test suite (manual 02 B6)",
went RED on main after PR #1838 added `music_qc/pace_change.py`. That step runs every
`scripts/core/test_*.py` file with its own `python3` process in parallel across the runner's
cores, so while `audio_c3/test_lyric_timing_f17.py` copied `scripts/core/` it walked the
`__pycache__` directories a sibling process was concurrently populating — including CPython's
transient `__pycache__/<mod>.cpython-3xx.pyc.<pid>` bytecode, which exists when `os.scandir`
lists the directory and is renamed away before `copytree` reads it. `shutil.copytree` therefore
raised `shutil.Error: [... "[Errno 2] No such file or directory"]`. It is a race, not a
deterministic regression: the same check was green on the previous main and on #1838's batch
head, and only the newly-added module's bytecode widened the window.

Both `shutil.copytree(CORE, core2)` calls in
`scripts/core/audio_c3/test_lyric_timing_f17.py` (the two scan tests) now pass
`ignore=shutil.ignore_patterns("__pycache__", "*.pyc")`, so the copy no longer walks generated
bytecode. The scan itself (`scripts/qc-no-local-asr.sh`) already reads only `*.py` files with
`--exclude-dir=__pycache__`, so the copied tree is byte-identical to what the scan inspects —
nothing the tests depend on is dropped. No assertion, `check()` call, expected value, exit-code
expectation, skip, xfail, retry, `try/except`, or `sleep` was added, removed or altered; the
only change is the two `ignore=` arguments.

---

## v2.9.25 - 2026-10-11 - WWFIX-U1 gaps: the sung-share floor, markup-as-story, the unwired audio gates and the hardcoded dispatch count

Four defects found in v2.9.22, fixed in the product. No test assertion was weakened, skipped,
deleted or re-run to green, and `.github/workflows/qc-static.yml` is untouched.

Numbered v2.9.25 because `origin/main` already carries `skill-version.txt` at v2.9.24 (a repo-side
bump with no CHANGELOG entry of its own), and a version file that does not CHANGE is not a bump:
G3 measures the diff against main. v2.9.24 therefore stays main's number; this entry is the next
one above main's v2.9.23 U20 entry.

- **The sung-share floor every sheet is judged against (RED `QC static invariants`, step
  "Skill 75 empty-home test suite (manual 02 B6)", `sung_hook/test_no_skip_and_goldens.py`
  `AssertionError: 68.5 != 71.1`).** `words_fit.style_sung_target_pct` re-derived the style's
  sung-of-voice FLOOR from a plan that v2.9.22's D1 rap floor had re-priced, so R&B Flow fell from
  71.1 to 68.5 at 148 s and from 66.0 to 65.8 at 298 s — the D1 rap reservation silently lowered a
  floor that was already being enforced. It now reads the plan with `rap_floor=False` (the FU-U2
  carve, i.e. exactly the split the style held before D1), so both pinned values come back with no
  change to `length_formula.plan()`'s default behaviour. The D1 rap floor keeps its OWN gate
  (`length_formula.rap_floor_gate` / `song_contract.rap_floor_for`); a new rule may not re-price an
  existing one. Before-fail: `style_sung_target_pct("rnb-flow", 148)` was 68.5, pinned 71.1.
- **Rap sheets that must hold BOTH floors (the same step).** At 58 s the restored floor (72.9% of
  voice time) and the D1 rap floor (20 words) cannot both fit a sheet that also carries a spoken
  closing call to action: 61 sung + 20 rap + 14 spoken = 95 words against a 76-word budget (85 with
  the band). The two rap-only test sheets in `music_qc/test_wwfix_u1.py` and
  `suno_recipe/test_suno_recipe.py` therefore run WITHOUT the spoken `[Outro]`; every `rap=False`
  sheet keeps the intro + closing call to action, and every assertion value is unchanged. The R&B
  Flow golden sheet gains one sung line (`I keep running on empty,`) for the same reason — more
  singing, which is never a fault.
- **Markup counted as story text (defect 1).** `story_coverage` counted the split end-marker row
  and other bracketed section tags as lexical story words. `is_lexical` now rejects any token
  carrying `[` or `]`, and `aligned_lexical_words` skips every aligned row that lies INSIDE a
  bracketed tag or marker (`_markup_rows`, a depth scan over the aligned row stream). Markup is
  structure, never a spoken word.
- **The defect-1 fix is now pinned by a real-fixture test (WWFIXPIN-U1).** The markup fix shipped
  with no test able to detect its regression: the only other importer, `music_qc/test_wwfix_u1.py`,
  drove the story gates on synthetic rows of `count`/`la` with no brackets. The new core test
  `scripts/core/story_coverage/test_story_coverage_markup.py` (auto-discovered by `QC static
  invariants` and the Skill 75 suites) drives the public API — `aligned_lexical_words`,
  `is_lexical`, `lexical_coverage_gate` — against the real returned take
  `song_contract/fixtures/one-check-v2-g2a-take.json`. It asserts the split end-marker header
  fragments ('Rap ', 'Verse 3 ', 'Chanel (' …) and the `Instrumental ` row are EXCLUDED, that
  tag-only and marker-only tokens are never lexical, that the split `[End]` marker (`'…['` then
  `'End]'`) is never counted, that real lyric words on markup-carrying rows ('Girl! ' / 'Girl, ')
  are KEPT, and it pins the fixture's measured lexical word count at 319 (64.024 s of lexical
  time). With the markup logic reverted the same fixture reads 329 and the test fails (6 of its 7
  tests red); restored, it passes.
- **The two D1 audio gates were never called (defect 2).** `music_qc/rap_check.py` and
  `music_qc/pace_change.py` shipped in v2.9.22 but nothing in the pipeline invoked them, so
  "UNMEASURED blocks a take PASS" was true only of the modules in isolation; `run_takes` could still
  deliver a PASS on an unmeasured rap read or an unmeasured gear change. Both are gates of
  `song_dispatch.judge_take` now (`GATES` gains `rap_audio` and `pace_change`), and `_finish` counts
  UNMEASURED with FLAG so only an all-PASS take passes. `rap_audio` applies to a rap-delivering
  style and nowhere else; `pace_change` is PASS when the plan orders no gear change.
- **`cmd_generate` reported a hardcoded dispatch count (defect 3).** The report carried the literals
  `"dispatched": 1` and `"dispatched": 3`. `one_variant` regenerates a FAIL once, so a retry is a
  SECOND provider job and the umbrella run makes six. The count is now measured from the run
  (`sum(r["attempts"])`) and pinned against the generator's own call count.

---

## v2.9.23 - 2026-10-11 - U20: OPTIONAL web push in the onboarding planned service (version 2, OFF by default, never a version-0 gate)

Unit U20 of the drama studio joint plan. Plan **line 1091**: `| U20 | Optional
web push | U3 | onboarding planned service | U3; never version-0 gate | 6 | 3 |
Optional owner | 2 |`; plan **line 832** (version table): `| **Version 2** |
Optional web push U20 and optional U10 extras: ... none blocks version 0 |`. The
whole unit exists to be **optional**: nothing here runs, stores, sends or changes
anything until an operator sets `DS_WEB_PUSH_ENABLED`. Predecessor U3 is merged
(PR #1817); this is a DRAFT PR only — nothing is deployed and no provider is
called.

- New `mini-app/service/src/push.js` — the optional surface, OFF by default.
  `pushEnabled(env)` is true only for the exact on-values `"true"`/`"1"` (unset,
  empty, `"false"`, `"yes"`, `"TRUE"` all stay off). It follows the existing
  service discipline rather than a parallel one: identity and path scoping from
  `ids.js`, the isolated key-record pattern from `isolation.js`, a
  `"active" | "revoked"` status like a key record in `keys.js`, subscription keys
  namespaced `push:<client_id>:<subscription_id>` so another client cannot even
  name a record, and one `subscriptionBelongsTo(record, clientId)` predicate
  every read and revoke funnels through.
- `sendPush({ env, store, clientId, payload, transport })` REFUSES — named code
  `AF-DS-PUSH-DISABLED`, zero side effects, zero transport calls — unless web push
  is enabled AND a VAPID private key is configured AND a transport was injected.
  A 404/410 from a push service prunes that subscription (`status: "revoked"`),
  the same way a revoked key fails to resolve. It opens no socket of its own: the
  RFC 8291 encryption + VAPID JWT signing is a **transport the runtime injects**
  (`{ subscription, payload, vapid }) -> { status }`), so this unit ships no
  vendor and no network call.
- New routes in `mini-app/service/src/index.js`: `GET /api/studio/push` (public,
  one boolean, `false` for every studio with the flag unset); `POST
  /api/studio/push/subscribe` (key-auth; **503 `AF-DS-PUSH-DISABLED` and stores
  nothing** when off); `POST /api/studio/push/unsubscribe` (key-auth; a record
  that is not the caller's reports `AF-DS-PUSH-MISSING`); and `POST
  /api/studio/admin/push/send` (admin-only; 503 until push is enabled,
  configured and a transport is injected). `handle()` gains an OPTIONAL fifth
  `deps` argument — every existing four-argument caller is unchanged.
- New `mini-app/ui/push.js` — the browser-side OPTIONAL surface. **Not imported
  by `studio.js` or `index.html`**, so the version-0 page is unchanged by U20.
  `pushSurfaceState()` shows nothing unless handed `enabled: true` AND
  `supported: true`; `enablePush()` refuses and asks the browser nothing unless
  `enabled` is exactly `true`. `api-client.js` gains the three optional
  entrypoints (`getPushStatus`, `subscribePush`, `unsubscribePush`) in a separate
  `OPTIONAL_PUSH_ENTRYPOINTS` list; the nine required ones are untouched.
- Retention: `retention.js` gains a `push_subscription` kind marked
  `never: true`, so a sweep partitions subscriptions out of a delete list. A
  subscription is removed only by an explicit unsubscribe or a push service
  404/410. `schema.sql` records the `push:<client_id>:<subscription_id>` contract
  and the env-only VAPID names. No key material is ever stored: a record holds the
  push endpoint and the browser's two PUBLIC keys only, and no VAPID value is
  stored, echoed or printed.
- Proof: `node 75-drama-song-ad-factory/mini-app/service/prove/prove_push_optional.mjs`
  runs 10 cases green (exit 0) — off-by-default across eight flag inputs, the
  inert surface, the unconfigured-send refusal, a POSITIVE control that the
  enabled path really sends and prunes, per-client isolation, never-swept
  retention, no-key-stored, version-0-unchanged, and the two UI-surface cases.
  `bash .../service/prove/planted-bad.sh` exits 0: four planted defects (each
  removing one `U20-GUARD:` line) turn their matching case red (exit 2) and the
  clean run is re-asserted green. The version-0 suite is untouched and still
  green: `node --test service/test/service.test.mjs` 22/22, the U2 boundary
  prover passes, and `bash ui/checks/run-all.sh` passes all four checks.
- Version: `skill-version.txt` and the `SKILL.md` frontmatter `version:` land at
  v2.9.23 in this same commit, bundled with the real content (G3 gate).

---

## v2.9.22 - 2026-10-11 - WWFIX-U1: the rap floor, the story gates, the pace instrument and the three-version music trap

Every threshold added below is a NEW ACCEPTANCE RULE set by this fix, not a measured limit of an
earlier run; the two exceptions anchored to real measurements are the pace controls (fast 90.909 /
half-time 44.776 bpm) and the rejection of the shipped takes (tempo ratio 1.0).

- **D1 rap floor (NEW RULE).** `length_formula` gains `RAP_FLOOR_S = 8.0`, `RAP_FLOOR_SHARE = 0.10`,
  `rap_floor_s(D)`, `rap_floor_words(style_id, D)`, `rap_gate`/`assert_rap_floor` and
  `RapFloorError`. `rap_s >= max(8.0, 0.10 * D)` and `rap_words >= ceil(rap_s * the style's rap
  rate)`; at D = 88 that is 8.8 s and 22 words. `plan()` always emits `words.rap`, `rap_s`,
  `rap_floor_s` and the gate report for a rap style, and the opener keeps its cap while the closing
  call to action YIELDS, so the spoken blocks can no longer carve the rap budget to zero. Before-fail
  reproduced on origin/main: `plan(90, 'rnb-flow')` had NO `rap` key and `plan(180,'rnb-flow')`
  reported `rap_s` 11.5 with no floor; `plan(90,'soul-ballad')` is byte-identical (word total 95).
  `song_contract.check_sheet` refuses a rap sheet below the floor before any spend
  (`RAP_PLANNED_ZERO_WORDS`); the previous behaviour on origin/main PASSED that sheet.
- **D1 story gates (NEW RULES), `scripts/core/story_coverage/`.** `story_start_gate` measures the
  approved PLOT LINE (a run of at least 4 consecutive plot words, never one stray word) against an
  ABSOLUTE `FIRST_STORY_WORD_MAX_S = 5.0` and the opening wordless span against
  `OPENING_NON_LEXICAL_MAX_SHARE = 0.15` of the delivered seconds; `lexical_coverage_gate` demands
  `LEXICAL_COVERAGE_MIN = 0.70` of delivered time in real lexical words with NO vocalise counted;
  `story_arc_gate` demands a measured lexical line in every story-arc window of at least 5 s.
  `song_contract.check_returned_story` exposes the verdict to the take judge, and
  `coverage_report()` keeps the words figure and the music-only figure under SEPARATE labels (the
  58.4 s figure is 50.416 s of words + 8 s of music, never 58.4 s of words).
- **D1 pace gate (NEW RULES), `scripts/core/music_qc/pace_change.py`.** Positive spectral flux with
  local onset peaks, a fixed mean-plus-standard-deviation threshold and a >= 0.12 s peak spacing. A
  gear change needs BOTH a >= 30% onset-rate reduction AND a >= 3 dB energy drop in the problem
  window, the return to baseline within 20% and 3 dB, and an independent smooth-transition check.
  bpm is reported and octave-folded but NEVER grants a PASS (85.2 and 181.5 bpm are the same beat an
  octave apart, which is why the run's own `deliver.py` half-time rule was wrong). Missing evidence
  is UNMEASURED, which blocks a take PASS.
- **D1 rap on the audio stays UNMEASURED, fail-closed**, `scripts/core/music_qc/rap_check.py`. No
  validated rap detector exists, so `gate`/`classify` return UNMEASURED until a labelled rap control
  is present; no fabricated threshold ships.
- **D2 the three-version music trap, `scripts/core/song_choices/`.** `one_variant` is the ONE
  single-variant worker path; `run_unit(requests, unit_id=..., variant_id=...)` is the per-unit
  selector and dispatches ONE variant; `generate_choices` is the umbrella and runs all three once in
  three threads inside ONE agent unit. `cmd_generate` reports `dispatched: 1` for a unit and
  `dispatched: 3, media_concurrency: 3, builder_agent_units: 1` for the umbrella, so three THREADS
  are never relabelled as three visible agent units. `plan_units` names WW-001..WW-003, providerSlots
  3, reserve 0, one owned folder and one owned request each; `_require_three` refuses a wrong or
  repeated set before any spend; `fan_in`/`deliver_choices` take no generate callable at all, so
  fan-in can only check and deliver. `factory._song_choices_next` exposes the umbrella command AND
  the three unit descriptors with an EXPLICIT `--orchestrated` selection and selects exactly one:
  never both, because an unqualified umbrella in every unit prompt pays for NINE generations.
- **D2 provider-overlap receipt, ONE implementation** (`song_choices/overlap.py`): `overlap_s =
  min(terminal_at) - max(submitted_at)` over exactly the THREE INITIAL attempts, PASS at >= 1.000 s,
  FAIL at 0.999 s / zero / negative, UNAVAILABLE (never a pass) without labelled aware-UTC
  timestamps; a regenerated attempt never counts and the gate never authorises a paid redo.
  `kie_dispatch` stamps `accepted_submit_at` only after a VALID task id and `terminal_at` at the first
  terminal provider response; both ride the ok envelope.
- **New tests** `scripts/core/music_qc/test_wwfix_u1.py`: the four D2 tests plus the dispatch-count
  test, `_require_three`/`_select_one`, the overlap boundary (1.000 PASS / 0.999 FAIL / zero FAIL /
  UNAVAILABLE), the rap floor and the zero-rap refusal, the story start / lexical coverage / story
  arc gates, the pace controls and the bpm-never-passes rule, the fail-closed rap check, the
  words-versus-music labels, and a regression pin that the failed run's 58 s sheet parses as
  69 sung + 13 spoken + 19 rap = 101 words, never as 101 words of one delivery.
- **Existing fixtures updated to carry the rap the style delivers**: `song_choices` test sheets and
  the `suno_recipe` seam sheet now use an R&B Flow sheet with a rap verse, and
  `song_contract/fixtures/rnb-flow-150-pass.txt` (Verse 2) plus
  `references/prompt-templates/fixtures/suno-sheets/suno-90s-rnb-flow.json` (Verse 2 line) were
  extended to meet the floor. `song_choices` and `suno_recipe` suites are green (18 and 36 tests).
- **Version**: `skill-version.txt` and the `SKILL.md` frontmatter `version:` land at v2.9.22 in this
  same commit, bundled with the real content (G3 gates a skill-content change on that bump).

---

## v2.9.21 - 2026-10-10 - U11: one channel-neutral send path and a requested-only device notice

- New `scripts/core/choice_card/intake_card/channel_send.py`: `app`, `terminal` and `storyboard` are delivery CHANNELS, not three senders. `CHANNEL_SEND[channel]` is `send()` bound to that channel's name, so all three reach the SAME function object and the send rules can never drift between them. The test proves the identity directly: `CHANNEL_SEND[c].func is send` is true for each of the three names.
- Nothing was re-implemented and no gate was weakened: the send builds the EXISTING `intake_card.openclaw_send_argv` (the same `openclaw message send --channel telegram ...` argv the choice card's `render_messages --format openclaw-json` and the storyboard approval runner's `openclaw_sender` already build). A `gate=` callable runs BEFORE anything is built or sent and a refusal raises `SendRefused`, so the CLI exits 5 with an empty stdout — nothing is sent on a refusal. `song_pick_gate(run_dir)` is the existing `song_choices.refusal` reused verbatim.
- `device_notice()` is the only notice sent to the client's device and it happens ONLY when `requested=True`: unsolicited means nothing is sent and it returns `None`. Pass a `run_dir` and the one nudge is recorded at `<run_dir>/control/device-notice.json`, so every later call is a no-op — one nudge, then silence, the client is never spammed. An unknown channel name raises `ChannelError`; there is no silent send on a wrong channel.
- `README-channel-send.md` documents the shared entrypoint, what it reuses, the requested-only notice and the two CLI verbs (`send`, `notice`) with their exit codes (`0` sent or nothing to send, `5` refused).
- Proof: `python3 75-drama-song-ad-factory/scripts/core/choice_card/intake_card/test_channel_send_u11.py` (10 checks green). Positive: a send through each of the three channels reaches the one entrypoint and builds the existing argv. Negative controls: an unrequested notice sends nothing (with the requested case as its control), a second requested notice on the same run is silent, and a refusing gate stops the send with a real non-zero process exit and no output.
- Version markers: `skill-version.txt` and the `SKILL.md` frontmatter `version:` land at v2.9.21 in this same commit, bundled with the real content (G3 gates a skill-content change on that bump, and the frontmatter is checked against `skill-version.txt`).

## v2.9.19 - 2026-10-10 - U4-U1: Drama Studio mini-app deploy files, dry-run path and a hard zone guard (files only, no deploy)

- New `mini-app/deploy/` (three deploy-side files): `deploy.sh`, `deploy.manifest.json` and `DEPLOY.md`. U2 owns `worker/` (the service) and U3 owns `pages/` (the UI); this unit owns `deploy/` only and ships no worker, no page and no deployment. Nothing is deployed by this commit: no `wrangler` call, no Cloudflare mutation, no bucket creation, no secret creation, no token use.
- `deploy.sh` reuses the Book Writer deploy pattern (`53-book-writer/mini-app/deploy`). Real Cloudflare ids stay `<PLACEHOLDER>` in `worker/wrangler.toml`; the script resolves them into a THROWAWAY config in `$TMPDIR` (deleted on exit) passed to `npx wrangler --config`, so no real id ever lands in git. Token and secret VALUES are env-only (`CLOUDFLARE_DRAMA_STUDIO_API_TOKEN`, forwarded per call to wrangler's native `CLOUDFLARE_API_TOKEN`; secret values piped to wrangler stdin) and no value is ever printed.
- HARD ZONE GUARD, cannot be disabled: G1 the target zone NAME must equal the manifest's intended zone (`zerohumanworkforce.com`); G2 the target zone id must not equal the known FOREIGN zone id (the `businessaftersixty.com` landmine); G3 when an intended account is pinned (`STUDIO_INTENDED_ACCOUNT_ID`) the target account id must equal it; G4 a live run must resolve a real zone id AND account id — an empty "not found" is a FAIL, never a pass.
- `--dry-run` validates and plans every step with no wrangler and no API call, and is honest: unresolved ids report as unresolved and never as a pass; the guard still fails hard on a wrong zone.
- `--self-test` is the offline proof (no token, no network): it demonstrates the guard refusing a wrong zone name, a foreign zone id and a wrong account (each a non-zero exit with the guard message), that an intended-zone `--dry-run` plans and the guard passes, and that `--dry-run` is PLAN-only and never fabricates a PASS. `bash 75-drama-song-ad-factory/mini-app/deploy/deploy.sh --self-test` exits 0 with `U4 deploy self-test: PASS`.
- Version markers: `skill-version.txt` and the `SKILL.md` frontmatter `version:` land at v2.9.19 in this same commit, bundled with the real content (G3 gates a skill-content change on that bump, and the frontmatter is checked against `skill-version.txt`). The real deploy is a separate, later, Trevor-authorized step.
## v2.9.19 - 2026-10-11 - U1: the studio-json export (question / price / example) from the intake card

- `intake_card.py` gains `--format studio-json`: the Drama Studio renders one screen per intake question, and this export hands it exactly what a screen shows — the question text, the price line (when that screen carries one) and a "See a great answer" example read from the client guide (`references/CLIENT-GUIDE.md`, the first `**Great answer:**` line under the matching `## STEP n:` heading). New `studio_json` / `studio_questions` build every screen from the SAME question list the card asks, so the card and the studio cannot disagree about a question or a price; the envelope is `{"format": "studio-json", "version": 0, "question_count", "questions"}` and each option carries its number, label, one sentence, its own price and whether it is the recommended pick.
- The two price surfaces read ONE sentence: new `_model_price_line(length_label)` is the single place the "Prices are for your <length> ad, with the song, pictures and a 20% redo allowance." line is built, and both the card's `ask` and the studio export's `price` read it. `spend_question` now carries the BUDGET screen's price line (`price` key: `$x` when a price is known, `up to $x` when only a limit is, `None` when neither), and `_model_question` carries its own price line beside the ask.
- Fail closed: a screen with no question text, no example, or no options raises `StudioExportError` (a named `field=` and `id=` on stderr) and the CLI exits 1 — never a json file the studio would render half-empty (`STUDIO_JSON_FIELD_MISSING`, `STUDIO_JSON_GUIDE_UNREADABLE`).
- New `test_studio_json_u1.py` (129 lines, 8 tests over the shared `python3 core/choice_card/intake_card/test_studio_json_u1.py` runner): every screen carries its question, price and example and the option keys are exactly `{n, text, detail, price, recommended}`; the model screen carries the live four model prices and the found example; the budget screen shows the card total when given; the CLI writes the export and exits 0; and three negative controls prove a missing question text or example refuses loudly with a real non-zero process exit and no degraded file on stdout. `__init__.py` re-exports `studio_json`, `studio_questions` and `StudioExportError`.
- Proof: `python3 75-drama-song-ad-factory/scripts/core/choice_card/intake_card/test_studio_json_u1.py` runs 8 tests green.
- Version: `skill-version.txt` and the SKILL.md frontmatter land at v2.9.19 in this commit (G3 gate); the 999-setup twin takes its own train.
## v2.9.19 - 2026-10-10 - Mini-app Studio UI (version 0): five pages, eight options, QR, accessibility floor, real-download proof

Unit U3-U1. New client-facing Studio UI under `mini-app/ui/` (no service behaviour — the service is U2's).

- Five pages — Start, Your eight answers, The recap, Your approvals, Your premiere — in `studio.js` + `index.html`, with a skip link, progress bar, section nav, focusable `<main>`, polite live region and `<noscript>` fallback.
- The eight options (offer, audience, star, length, music, look, quality, budget) as native radio groups with real labels; the numbered recap card; the "Looks good — start my video" confirmation state; and a per-approval "Looks good" state (script, song 1-of-3, storyboard) that stays on the page once taken.
- `qr.js`: a dependency-free QR generator (byte mode, EC level M, versions 1..10), inline SVG, no CDN. The QR is `role="img"` with an accessible name and the same link is written out in plain text underneath as the real alternative.
- `download.js` is the one place that decides a delivery link is an ACTUAL download: HTTP 200 on the exact tapped URL, `Content-Disposition: attachment`, positive `Content-Length`, that many bytes arriving, and a binary `Content-Type`. A 3xx is refused outright (redirects are never followed) — a share link that bounces to a landing page is not a download and the button stays disabled with the reason shown.
- `api-client.js` states the whole U2 service boundary as nine named entrypoints (`getSession`, `saveAnswer`, `getOptions`, `listInbox`, `postInbox`, `requestUpload`, `advance`, `getDelivery`, `verifyDeliveryLink`) and implements none of it; until U2 lands the page boots, draws every screen and says in words that nothing can be saved yet.
- Accessibility asserted by `checks/a11y-check.mjs` (32 rules, light and dark): WCAG contrast computed from the real stylesheet tokens with every text pair clearing 4.5:1, a real `<label>` and `id` for every input, focus order = source order (no positive `tabindex`), a page change moving focus to the new page heading, a visible `:focus-visible` ring, every state announced in a polite live region and no state carried by motion or colour alone, and a `prefers-reduced-motion` guard. Not covered and said so in the same words: a real browser and a screen reader.
- Proof: `cd 75-drama-song-ad-factory/mini-app/ui && bash checks/run-all.sh` runs four checks — `ui-contract.mjs` (the version-0 surface exists and imports cleanly), `a11y-check.mjs`, `qr-roundtrip.mjs` (the QR decoded by an independent decoder), and `download-bytes-check.mjs` (real bytes with the redirect-only negative control) — exit 0 = all pass, 2 = a check failed.
- Version: `skill-version.txt` and the `SKILL.md` frontmatter land at v2.9.19 in this commit (G3 gate).
## v2.9.20 - 2026-10-10 - U12: the pairing/admin surface behind the approval and QR gates

The studio's pairing and admin surface at `mini-app/pairing`: the admin mints a
client key and a single-use pairing code, the code burns on first use, wrong or
absent admin keys are refused with nothing written, and the QR the machine scans
is proved module-for-module identical to Apple's own `CIQRCodeGenerator`. Option 3
is refused without a recorded approval naming the client, and nothing the browser
loads persists anything. Seven files, disjoint from U2's `service/**`, U3's pages
and U4's deploy files; it consumes U2's boundary prover, never copies it.

Checks: 18 pairing tests exit 0; 17 pairing-guardrail checks exit 0; 14 QR cases
module-for-module identical to Apple's encoder, exit 0.

## v2.9.19 - 2026-10-10 - U2: the Drama Studio service foundation at mini-app/service

The planned studio home (joint plan section 5.4) gets its service side: per-client
keys and pairing codes, the inbox entry, direct uploads, retention, isolation, the
option field and the real-wait line, and an approved lifecycle with one operator
record per client per day. Service only — U3 owns the pages, U4 the deploy files,
U12 the pairing/admin pages. Reuses the existing worker/media pattern; no new
framework, scheduler or dashboard.

Checks: 22 service tests exit 0; the boundary prover passes 9 cases exit 0.
## v2.9.19 - 2026-10-10 - U5 shared studio bridge: atomic claim, replay, Windows-safe lease, quiet board

Unit U5 of the drama studio joint plan (row U5). Adds the box-side half of the
drama studio as four new files under `75-drama-song-ad-factory/shared-bridge/`,
one implementation shared by OpenClaw boxes and Claude Code computers. No file
here edits another unit's path (U1/U11 own `choice_card/intake_card`, U2
`mini-app/service/**`, U3 the mini-app UI, U4 `mini-app/deploy/**`, U12 the
pairing/admin surface).

- `studio_claim.py` — the ledger. Atomic single-winner order claim (`INSERT OR
  IGNORE` against a `UNIQUE` order id, so the database arbitrates and the losing
  racer exits `2`), a replay guard (`UNIQUE(run_id, message_id)`), a Windows-safe
  lease (one `UPSERT ... WHERE` in SQLite, never a lock file named from a key), a
  notice gate, and cleanup receipts.
- `studio_bridge.py` — the bridge. Key handshake, status, delivery, photo
  handling, the quiet board, the owned-run cleanup receipt, and the CLI.
- `checks/run_checks.py` — the five runnable checks (A–E), each with a true exit
  code and a control on the same instrument.
- `README.md` — the shared-bridge contract, the service contract it speaks to U2,
  the three guarantees, the notice discipline and the deliberate limits.

- Notice discipline: exactly one approval nudge, then at most one reminder
  (default 24 hours later), then silence — `ClaimLedger.notice_gate()` returns
  `"nudge"`, `"reminder"` or `None`, and `None` stays silent rather than being
  re-worded. Check D holds the guard load-bearing from both sides: the predicate
  fails on an unguarded sequence, and clearing the guard re-opens a notice.
- The Windows liveness probe never reaches `os.kill`, which on Windows
  `terminates` the process it is asked about; it uses
  `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` and fails closed. Check C
  proves the probe answers alive/dead without touching `os.kill` or a
  colon-named lock file.
- The presented key is read from env `DS_KEY` only — never argv, never a file
  named on the command line, never a log line. Check E proves nothing is printed
  with a positive control showing the detector can see the sentinel when present.
- Proof: `python3 75-drama-song-ad-factory/shared-bridge/checks/run_checks.py`
  reports `ALL PASS` (checks A–E) with exit 0. This is the real-content commit of
  PR #1820 (branch `unit/U5-U1`); the v2.9.18 -> v2.9.19 patch bump and the
  SKILL.md frontmatter are bundled into that same commit per the bundle protocol.
## v2.9.19 - 2026-10-10 - Approvals layer and producer hand-off mini-app (U8-U1): first answer wins, version dedup, nudge -> reminder -> silence

Adds seven new files under `mini-app/approvals/` and touches nothing else in the mini-app (no `mini-app/service/**`, `mini-app/ui/**`, `mini-app/deploy/**`, pairing surface or `intake_card` file).

- `approvals.mjs` — the approvals layer, pure over an injected store: register/dedup an item, record an answer (first answer wins), the nudge -> reminder -> silence ladder, and the producer hand-off gate. The refusal dict and exit 5 reuse the skill's existing gate convention.
- `ui.mjs` — the three approval cards and the studio-lines region; renders the service's lines verbatim (real `<button>`/`<h2>`, `textContent` never `innerHTML`, every state in words).
- `producer-handoff.mjs` — the CLI that carries ONE approved item to the producer and refuses an unapproved one with a real non-zero exit (5).
- `package.json` — `{"type":"module"}`, no dependencies.
- Four behaviours, each with a runnable proof (`prove/approvals.prove.mjs`, exit 0/2) and a planted-bad control (`prove/planted-bad.sh`, mutates a LOCAL copy, shows red, restores, then the clean control): a competing answer is refused by name (`APPROVAL_ANSWER_TAKEN`) and the record is left untouched; the same version returns the existing item (`created:false`) while a genuinely new version creates a new item (`created:true`); exactly two notices, then silence; the hand-off refuses an unapproved item with exit 5.
- Bundled in the same commit: `skill-version.txt` and the `SKILL.md` frontmatter land at v2.9.19 on this unit branch, so the G3 skill-content-without-version-bump gate passes on this head.
## v2.9.19 - 2026-10-11 - U10-U1: video-link delivery — client-owned GHL-first verified link, R2 fallback

- New `mini-app/video-link-delivery/` (joint plan section 5, row "U10 required", verbatim scope: "Only client-owned GHL-first verified video link and R2 fallback"; decision 5, answered by Trevor 2026-10-10). `video_link_delivery.py` answers one question — which link may be handed over, and is it really that link — under the order client-owned GoHighLevel (white label: Convert and Flow) FIRST, Cloudflare R2 (bucket `drama-studio`) only as the fallback, and it does not upload the video, message anyone, schedule anything or add a second control service or scheduler. It reuses the shape of the repo's proven `06-ghl-install-pages/tools/ghl_media.py`: bare `urllib` (no `requests`), a fail-loud `_require`, an injectable `fetcher` so every path is testable with no live call, and a single JSON envelope on stdout with a real exit code.
- "Verified" is not a label: `verify_link()` FETCHES the URL and streams the bytes through sha256, so a link is deliverable only when it returns HTTP 200 **and** the bytes hash to the finished video's `expected_sha256`; a 200 that serves different media is refused exactly like a link that does not resolve.
- The refuse rules, each exit 4: `cross-client-delivery` (the record and the delivery must be the same client), `token-in-url` (no candidate may embed a secret or be a signed/expiring link), `operator-owned-link` (an operator location id or operator host is refused outright, never silently skipped into the fallback), `ghl-candidate-not-client-media` / `ghl-candidate-not-client-owned`, `fallback-unverified`, and `no-verified-deliverable-link` (nothing verified ⇒ refuse rather than hand over anything unverified). The delivered record's `ownership` is derived from the source (`client-ghl` / `studio-r2-fallback`), never taken from the caller, so an operator-hosted upload can never be labelled as the client's.
- CLI (repo envelope contract, `references/cli-contract.md`): `python3 mini-app/video-link-delivery/video_link_delivery.py deliver --request <path.json> [--out <record.json>]` — exactly one JSON object on stdout, no log noise; exit `0` ok / `1` error / `4` rejected.
- Proof: `python3 75-drama-song-ad-factory/mini-app/video-link-delivery/checks/run_checks.py` exits 0 — six checks (A–F) pass and all six planted-bad copies are caught, so the check discriminates rather than rubber-stamping. Every URL is served by a local mock server on `127.0.0.1`: no live network call, no credential, no client message, no client-box write.
- Version: `skill-version.txt` and the SKILL.md frontmatter land at v2.9.19 in this commit (G3 gate).
## v2.9.19 - 2026-10-10 - U6: direct-shell persistent timer artifacts for macOS, Hostinger and Contabo (files only — nothing installed)

Bundles the skill-version bump into the U6 real-content commit (G3: skill 75 content changed, so `skill-version.txt` and the `SKILL.md` frontmatter bump together on this one commit).

- `timer-artifacts/run-timer.sh` — the direct-shell poller the scheduler runs; platform-aware, `exec`s the U5 `shared-bridge/studio_bridge.py handshake`. No idle model event, no interactive session, no model token on the exec line.
- `timer-artifacts/install-timer.sh` — renders the platform definition into its install path. Files only: `--dry-run` is the default, `--register` is always refused. It never installs, loads, enables or schedules anything anywhere.
- `timer-artifacts/mac/com.blackceo.drama-studio-bridge.plist.template` — macOS LaunchAgent, `ProgramArguments = [/bin/sh, run-timer.sh]`, `RunAtLoad` + `StartInterval 120`, no `KeepAlive`.
- `timer-artifacts/hostinger/drama-studio-timer.cron.template` and `timer-artifacts/contabo/drama-studio-timer.cron.template` — `*/2` direct-shell poll on the persistent volume (state on the persistent root, never ephemeral `$HOME`).
- `timer-artifacts/checks/run_checks.py` — the runnable checks A–G, each with a plantable negative control and a true exit code.
- `timer-artifacts/README.md` — the mechanism and the install paths, stating nothing is installed, loaded, scheduled or registered.
- No credential is embedded; `run-timer.sh` references the key from its 0600 store and exports `DS_KEY` in the environment only.
- Proof: `python3 75-drama-song-ad-factory/timer-artifacts/checks/run_checks.py` is 22/22 green (exit 0) on the pristine tree; a lane-local copy with a planted credential literal in `run-timer.sh` fails `F no-secret` with a true non-zero exit (21/22), and that copy was deleted. No LaunchAgent, `launchctl` entry or crontab line for the timer exists on the build machine.
## v2.9.19 - 2026-10-10 - HYBRIDDP-U1: dual-presence rule for hybrid ads (APPROVED 2026-10-11)

Owner order 2026-10-11 (joint plan section 3.17). Every hybrid ad carries
**exactly one** `DUAL_PRESENCE` shot: the photoreal lead and an opaque sketch
twin visible together in one locked-off side-by-side two-shot, starting 45-75%
of the ad (target 55-65%), held 3.0-6.0 s, photoreal 55-65% of width, twin
35-45%, head heights within 15%, twin on the side opposite the lead. Two
negative controls are required - the same shot with the twin removed, and the
single-style "some time later" phone shot at 112.0-114.3 s - and both must
return zero passing frames. It is a planned shot with its own storyboard field,
never a patch.

- `SKILL.md` gains the dual-presence bullet between the Five looks and Music
  bullets; `INSTRUCTIONS.md` gains its own between Five looks and Music styles.
- `scripts/core/style_bibles/hybrid/hybrid_bible.py` (stdlib only, never
  renders, never calls a provider, never spends) gains the dual-presence
  constants (commented STARTING values - calibrate on both controls),
  `dual_presence_errors()` / `assert_dual_presence()` refusing each rule BY
  NAME and never a bare boolean, `dual_presence_shot_list()` emitting the
  single `DUAL-01` entry with `BASE_REAL` (photoreal clip) and `OVERLAY_SKETCH`
  (alpha PNG, matched pose frame) and refusing to emit when the validator
  refuses, `dual_presence_assembly()` (100% opacity alpha overlay on the
  photoreal base, dissolve in 8 frames or fewer, hard cut out on 1 frame,
  cross-blend refused by name) and the frame-level gate `qc_dual_presence()` /
  `qc_dual_presence_window()`: sample at 4 fps, a frame passes when one half is
  line art (low saturation, high edge density) and the other half is photoreal
  colour, require `duration_s x 4` CONSECUTIVE passing frames with floor 12,
  and run BOTH negative controls - a missing control is not a pass. Every
  threshold comes from the constants, so calibration changes one place.
- New colocated test `scripts/core/style_bibles/hybrid/test_hybrid_dual_presence.py`
  (17 tests, stdlib, offline, $0): every named rule refused, one mutation per
  rule; the shot list refusing to emit; the assembly refusals; the gate's OWN
  known-good control FIRST - a synthetic frame pair it must PASS and a
  synthetic single-style frame it must FAIL, so a gate that returns zero
  passing frames on everything cannot read as a pass - then the positive
  control and BOTH negative controls. Also proves a 17-frame run does not pass
  an 18-frame requirement, and that the twin-removed clip used as the positive
  control fails the gate.
- MEASUREMENT, reported plainly (approved Spaulding 3V3 FIX2 video, sha256
  `0213de02ff690bbb17d72a3171af432e6a2a36ee87409d4e341c70cf89503004`, read
  from a read-only copy; the original was never edited, moved or re-encoded):
  with the STARTING thresholds above and a 50/50 half split, the gate returns
  ZERO passing frames on the real flagship beat window (88.292-93.792 s) - both
  halves classify photoreal - while a real sketch window (2-6 s) classifies
  SKETCH and real photoreal windows (100-104 s and the 112.0-114.3 s phone
  control) classify PHOTOREAL. The instrument therefore discriminates, so this
  is a real negative and not a broken check. The beat window does show elevated
  low-saturation pixels (mean 8.3% of the frame vs 0.7% in plain photoreal) and
  elevated edge density (0.20-0.29 vs 0.10-0.12), so the twin region is
  plausibly present but smaller than, or positioned off, the 50/50 boundary.
  NO real-video calibration was run: the bands ship as the plan's STARTING
  values and calibrating them against both controls is the follow-up work the
  plan itself calls for. Control one (twin removed) has no real-video
  counterpart and is proven on synthetic frames only.

## v2.9.18 - 2026-10-10 - PKG-11 attempt 4: twelve REAL `produce_delivery` paths, real-run e2e, no fixture bytes

Released with onboarding v27.1.1 (same follow-up batch; attempt 3 only claimed the one naming scheme).

- Every `produce_delivery(run_dir, item)` adapter (all twelve) now calls THAT producer's own real deliver path on the contents of `run_dir`: `build_audio_versions` + `write_version_docs` (DEL-01), `character_bible.write_delivery` (DEL-02), `script_pdf.render` (DEL-03), `storyboard_grid.deliver` (DEL-04), `build_video_delivery` + `write_video_docs` (DEL-05), `deliver_clips` (DEL-06), `ready_post_kit.prepare` + `write_kit` (DEL-07), `build_cover` + `write_cover_docs` (DEL-08), `lyric_sheet.write_delivery` (DEL-09), `export_captions_srt` (DEL-10), `copy_character_images` (DEL-11), `welcome_sheet.build_welcome_sheet` (DEL-12). New `scripts/core/delivery_package/run_inputs.py` is the ONE place that says where each producer's real inputs live in a run (approved script and approval record, approved storyboard records and stills, character brief and records, `music/` audio and `music/word-timings.json`, `edit/ad.mp4` + `edit/timeline.json`, card answers) and how a deliver path's output is handed back to the packaging call (`stage`, fail closed when a file never landed). No adapter imports `contract.produce_item` and no deliver path writes fixture bytes (`PDF_BYTES`, `SRT_TEXT`, `NOTE_BYTES`, `MEDIA_BYTES`, `PNG_BYTES`): `produce_item` remains only as the clearly named test-fixture helper behind `write_reference_package`. The ffmpeg that burns captions and draws the cover title is MEASURED for the filter (env override, PATH, then the bundled build); a box with none refuses instead of shipping a file without its words.
- DEL-02 now ships BOTH of its contract files through its own real path: `write_delivery` renders `02 - Character Bible.pdf` and copies the run's reference pictures into `02 - Character Bible Images/` (one file per view, a copy never a re-encode). No reference picture in the run is a refusal (`NO_REFERENCE_IMAGES`), never an empty directory.
- `test_delivery_package_e2e.py` BUILDS a non-empty run folder with the real producer inputs (media through ffmpeg, records as JSON), runs `package_run` over it and proves `contract.verify_folder` reports all twelve items present with zero missing and every file opening -- with no skip anywhere. The negative control removes one REAL produced item from a copy of that package and `verify_folder` must fail naming exactly it. A second packaging run runs with `contract.produce_item` replaced by a raiser: all twelve adapters still produce every item from the run, and no produced file carries fixture bytes.
- Current docs now state the one scheme everywhere they name a delivery file (`QC.md`, `references/stage-runbook.md`, `references/character-bible.md`, `references/choice-card-spec.md`): `01 - Instrumental.mp3`, `01 - Voice Only.mp3`, `01 - About These Audio Files.txt`, `02 - Character Bible.pdf` + `02 - Character Bible Images/`, `04 - Storyboard.pdf`, `05 - Video Captioned.mp4` / `05 - Video Clean.mp4`, `06 - Clip 60s.mp4` / `06 - Clip 90s.mp4`, `08 - Cover Thumbnail.png`.
- Proof: `python3 scripts/core/delivery_package/test_delivery_package_e2e.py` runs 9 tests green (real run, no skip); the skill 75 tree in ONE pytest process is 1649 passed / 4 skipped (the same four pre-existing skips, none of them this test); the per-file empty-`HOME` loop is 156 files green. Version markers: `skill-version.txt` and the SKILL.md frontmatter land at v2.9.18 on this follow-up batch (G3 gate); the 999-setup twin takes its own train 2.7.39 -> 2.7.41 with its `VERSION` + frontmatter. Shared files stay byte-identical across both repositories.

## v2.9.17 - 2026-10-10 - PKG-11 attempt 3: one delivery package naming scheme, real producers pass the 12-item gate

Released with onboarding v27.1.1 (follow-up to the v27.1.0 batch; closes the delivery package naming gap flagged there).

- ONE naming scheme, `NN - Label.ext`, defined in `scripts/core/delivery_package/contract.py`. All 12 producers' deliver paths (audio versions, character bible, script PDF, storyboard grid, video captioned and clean, 60 and 90 second clips, ready-to-post kit, cover image, lyric sheet, caption file, character images, welcome sheet) emit the `contract.PACKAGE_ITEMS` names. Attempt 2 failed because only 5 of 12 did and the adapters wrote fixture bytes.
- `produce_delivery` adapters call each producer's real deliver path (no fixture bytes).
- `test_delivery_package_e2e` runs the REAL producers into a folder and passes `contract.verify_folder` for all 12 items, plus a negative control.
- Includes the operator-only wording scrub (see v2.9.16).

## v2.9.16 - 2026-10-09 - operator wording scrub

- Wording scrub, behavior identical: the two-strike unlock line says operator-only (no personal name) in the SKILL.md gate block, the `two_strike.py` policy docstring, the `two_strike_skills_map.json` source field and the two-strike README.

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
- New `test_delivery_package_e2e.py`: a run through the packaging entry point. (Its behavior moved with DEL-13's producers: at v2.9.16 the test builds a non-empty run and runs the twelve real deliver paths with no skip -- see the v2.9.16 entry.) A raising producer or a folder that does not verify still fails. `QC.md` records the package-items line.
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

- **PKG-07-U2 (DEL-16): shot-planner rules ship as `scripts/camera_shot_rules/` (renamed from shot_planner in the v27.1.0 batch: scripts/core/shot_planner already owns that import name).** The camera vocabulary every shot brief carries (establishing wide through insert and detail; eye/low/high/bird's-eye/dutch angles; static through crane moves; 24/35/50/85 mm lenses; aperture wide open to stopped down) plus the DEL-16 rules, enforced for music and for dialogue or narration alike: one camera move per clip and four-to-six-second clips; whip pans and fast orbits only as an edit transition between two clips; text and logos in post; "shallow depth of field" in prompts, never an f-stop number; the shot-length ladder from about eight seconds for extreme wides down to about two and a half for extreme close-ups; medium-shot dominance; close-ups at most thirty-five percent; at most two identical framings in a row; every scene opens on an establishing wide; five shot types and three angles from two minutes up; lens and aperture matched to emotion; coverage spans master/medium/close-up/reverse/insert/cutaway with the 180-degree rule, eyelines, scene geometry, shot-reverse-shot, motivated moves, rack focus, depth of field, lighting choice and screen-direction continuity. Every pacing percentage is labeled a planning range, not a measured standard. New `test_del16_rules.py` (positive + negative case per rule, three content modes); CLI `vocabulary`/`plan`/`check` on the control envelope.

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
- LPG003 loosened the rules (Trevor: "loosen the checks so it's not as strict"): PASS / ACCEPT_WITH_FLAG / FAIL. FAIL only for face count not 1, face under 20%, |roll| over 20, |yaw| over 0.25, jawOpen over 0.30, sharpness under 60. Smile, teeth, small face, mild tilt are flags, never a paid regeneration. Calibrated so every Trevor-approved Kiesett version 2 and client picture passes or flags.
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
