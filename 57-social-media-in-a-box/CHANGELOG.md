# Changelog — Social Media in a Box (Skill 57)

## v1.7.9 - 2026-10-06 - Review fixes: prompt 05 routing, prompts 09 and 10 ratio wording

- Prompt 05: the "Ideogram V3 DESIGN / Agnes" text-bearing route is removed. Every social image routes to GPT Image 2.5 Sunburst; the only fallback is legacy gpt-image-2 under the N43 ratio rules.
- Prompts 09 and 10: carousel slides are requested at 3:4 (N43 substitution) and delivered cropped to 4:5 at 1080x1350, matching the Skill 35 playbook; the prompts now tell the model to keep key content inside the central 4:5 safe area instead of stating 1080x1440 as the deliverable size.
- `PROMPT-HASHES.json` re-recorded for prompts 05, 09 and 10 and verified. `ENGINE-PIN.sha256` unchanged (no engine file touched).

## v1.7.8 - 2026-10-06 - Skill 74 media contract, no Sora labels, golden provenance model ids

- Duration-lane naming: every "Sora" label is now "25.0s duration lane" with the render model picked by the Skill 67 selector (`modes.md`, `SOCIAL-MANIFEST.json` P4 name, `config/client-config.schema.json`, `config/bands.json` note, publisher sub-modes `tiktok` and `youtube`, `scripts/prove_bands.py` comment, `scripts/defer_stub.py` baseline text). Prompt 08: the role line "using OpenAI Sora" and the Sora wording in its header are replaced by model-neutral text (file name kept for the hash pin, like prompts 12 and 14). No code in this skill sent a Sora model id; the golden provenance fixture that recorded `sora` and `nano-banana-pro` now records `wan/3-0-video` (the Skill 67 selector's answer for a 25 second clip) and `gpt-image-2-5-sunburst-text-to-image`.
- New "KIE dispatch contract" in `modules/3-media-core/README.md`: policy, Sunburst default (rule 13 auto-latest), `prompt-budget`, `validate`, `preflight`, `run --mode active`, save, GHL upload. Prompt 05 gains the rule 12 length instruction (95 to 100 percent of the model maxLength, never below 80 percent; seeds from prompts 09, 10 and 15 are expanded, not padded); prompt 06 keeps a rewritten prompt inside the 80 to 100 percent window; prompts 12 and 14 headers state the budget and the podcast cover resize (2K output delivered as exactly 1400x1400 JPEG). `config/bands.json` records that the `image_prompt_*` bands limit the authored seed only.
- Credit wording in `SKILL.md`, `MASTERDOC.md`, `SOCIAL-MANIFEST.json` and the preflight README now states the real rule (balance >= planned estimate x 1.30, 200 credits as the absolute floor) instead of "credits >= 200". The doubled "(Skill 67)" in `MASTERDOC.md` and the media-core README is fixed.
- `PROMPT-HASHES.json` re-recorded for prompts 05, 06, 08, 12 and 14; `ENGINE-PIN.sha256` re-recorded (comment and text changes in `prove_bands.py` and `defer_stub.py`). Prompt and engine hashes verified.
- Known, not changed here: `verify.sh` golden steps (2, 2b, 2c, discovery-drift) already failed before this change (the goldens predate the F08 execution-mode stamp and the F11 QC matrix); the other 8 prover self-tests, broken-variant rejections, scrub, prompt pin and engine pin pass. The committed golden certificates predate the prompt re-pins of v1.7.4 to v1.7.7 as well.

## v1.7.7 - 2026-10-06 - SKILL.md model wording, prompts 12 and 14 payloads

- `SKILL.md` frontmatter description: Midjourney and Nano-Banana carousel wording replaced with GPT Image 2.5 Sunburst; the video render is routed to the Skill 67 (kie-video) model selector, and "Kie.ai Sora" is no longer named in `SKILL.md`, `MASTERDOC.md` or `modules/3-media-core/README.md`. Remaining Sora labels on the 25.0s lane (modes.md, prove_bands.py, publisher submodes, config) are a separate follow-up, not changed here.
- Prompts 12 and 14: removed the undeclared `"output_format": "png"` line from the payloads (the sunburst schema declares prompt, aspect_ratio, resolution, background and input_urls only). Nothing else in either prompt changed. `PROMPT-HASHES.json` re-recorded for 12 and 14; `ENGINE-PIN.sha256` unchanged and still matches.

## v1.7.6 - 2026-10-05 - prompts 09 and 10 aspect ratio statements match N43

- Prompts 09 and 10: only the aspect-ratio statements changed, 4:5 (1080x1350) to 3:4 (1080x1440), matching prompt 12 and the N43 4:5 to 3:4 substitution (09: universal canvas lines, 14 style templates, the worked example and the required-components line; 10: canvas size line). No other content touched. `PROMPT-HASHES.json` re-recorded; prompt hashes and engine hash match.

## v1.7.5 - 2026-10-05 - close open items on the image consumers PR

- Prompts 09 and 10 were read end to end: no image-model primary wording (no Nano Banana, no Midjourney) exists there, so they are unchanged. Re-pin confirmed: prompt hashes and engine hash match.

## v1.7.4 - 2026-10-05 - fix(image consumers): sunburst-first order, unified model ids and credit preflight

- `scripts/preflight_gate.py`: credit rule is now max(estimate x 1.30, 200), with 200 kept and documented as this skill's absolute floor; `_live_kie_credits` checks the BODY `code`; shortfall reported. New `scripts/test_kie_credit_rule.py`. `ENGINE-PIN.sha256` re-recorded.
- Social images are GPT Image 2.5 sunburst everywhere (owner order): prompt 12 moved from `nano-banana-pro` to `gpt-image-2-5-sunburst-text-to-image` at 3:4 (N43 substitute for 4:5); SKILL.md, MASTERDOC.md, module 3 README and SOCIAL-MANIFEST labels no longer name Midjourney or Nano Banana; prompt 05 routing lists GPT Image 2.5 first, prompt 11 note updated. `PROMPT-HASHES.json` re-recorded. New `_live_kie_credits` body-code test in `test_kie_credit_rule.py`.
- Prompts: 14 `google/nano-banana` (legacy per Skill 66) -> `gpt-image-2-5-sunburst-text-to-image` 1:1 2K png, the same id and payload Skill 58 `generate_cover.sh` sends; 12 `nano-banana-pro` and 13 `seedream/4.5-edit` kept and documented (12 matches Skill 66; 13 matches the live KIE docs enum); 06/07 stale Midjourney wording removed. `PROMPT-HASHES.json` re-recorded for every prompt (01, 05 and 16 were already drifted from the pin before this change).

## v1.5.1 - 2026-09-09 - release fold: changelog entry for the v1.5.0 producer adapter bump (F05)

Batch ONB-20260909T011638 (PR #1069, merged at 81fa6caee). Version bump
v1.4.0 -> v1.5.0 shipped in commit b94672d7f (G3 lockstep with
35-social-media-planner v3.4.0). This entry documents the change that bump
already carried.

### Changed
- **Producer adapter layer (F05)** — `run_social_media.py` gained a
  producer-adapter seam behind the phase gates. Producers are selected by
  adapter, each phase writes hash-bound receipts, and interrupted runs resume
  from the last verified receipt instead of restarting. Engine pin unchanged
  (aa348057842c...); semantic minor for contract-affecting change.

## 0.2.11 — 2026-07-12 — P3-05 step 11: SOP-SOCIAL-03 image-prompt FORM/AESTHETIC split (durable successor fix)

### Changed
- **`universal-sops/social-media-craft/SOP-SOCIAL-03-CREATIVE-INTERJECTION.md`** — new §3a explicitly distinguishes image-prompt **FORM** (ratio/pixel spec, legibility, merged avoid-list, brand-safety clause, text-overlay-to-Ideogram routing — provable, GATED, the same class as `image_prompt_carousel`/`image_prompt_series` length in `config/bands.json`) from image **AESTHETIC/content** (subject, mood, lighting, composition, color taste — correctly left sovereign, stays ungated per the existing §3 law). Skill 35 (`35-social-media-planner`) had exactly this prompt-quality gap fixed in its own P3-05 pass; Skill 57 supersedes Skill 35 per `cc-compat.json`, and §3's pre-existing GATED/NEVER-gated list did not yet enumerate these FORM elements — so the gap could have resurrected silently at the 35->57 migration. This section is now the binding doctrine that prevents that; a future prover pass may extend `prove_bands.py` with the enumerated FORM checks using the same band-file pattern `image_prompt_carousel` already establishes. No code changed — this is a documentation/doctrine fix; the 7-03 HOLD still governs rollout.

### Fixed
- **`mc_board.py` — an UNRECOGNIZED `department_slug`** (a typo, a regressed
  hardcoded fake slug like the historical `funnels`/`books`/`email` family, or an
  empty string) is now caught client-side before the ingest POST, logged loudly to
  stderr, and RE-ROUTED to the `general-task` catch-all department with the
  original bad slug annotated on the card description and on `begin_run`'s initial
  board event note. Never silently dropped. Recognized slugs (the 22 mandatory + 6
  universal-primary floor departments + known variant aliases, mirrored from
  `23-ai-workforce-blueprint/scripts/department-floor.py:116-158`) pass through
  unchanged. Applied identically to the shared `mc_board.py` family
  (49/50/53/54/55/56/57).

### Added
- **`test_cc_contract.py`** — six new regression cases: an unrecognized slug
  reroutes to `general-task`, an empty slug reroutes, a known slug
  (`web-development`) and `general-task` itself pass through unchanged, the
  reroute logs loudly to stderr, and `begin_run`'s initial advance note records the
  original bad slug as a board-visible event.

## 0.2.7 — mc_board pinned into the engine-hash set (train W2-55-57-mcboard-pin, Wave-2)

Train **W2-55-57-mcboard-pin**. Fix IDs: FIX-S36-58.

### Changed
- **FIX-S36-58** — `scripts/mc_board.py` — the only token-bearing outbound-HTTP
  script — is now included in GATE 3's `PIN_INPUTS` (in `social-media-entry.sh`)
  and the mirrored `ENGINE_FILES` set in `verify.sh` (appended after
  `defer_stub.py`), so a tampered board client can no longer pass the
  `AF-SM-ENGINE-HASH-PIN` gate. `ENGINE-PIN.sha256` regenerated over the expanded
  set in the same commit. No runtime-behavior change; widens the tamper-evidence
  surface only.

## 0.2.6 — 2026-07-05 — F4.3 C10 persona INPUT adapter SHIPPED (train DEP-7)

Train **DEP-7**. Fix IDs: F4.3.

### Added
- **C10 persona INPUT adapter IMPLEMENTED** (`scripts/persona_adapter.py`) — previously a
  fail-closed stub deferred to v0.5.0. `personaSource:adapter` now routes the week's brand/theme
  context through the ONE shared entry point `shared-utils/persona_for_job.py` (canonical 5-layer
  selection, LOGGED); `personaSource:client-choice` returns the client's expressly-named persona
  **verbatim, FINAL, never judged** (client sovereignty); `personaSource:config` is the unchanged
  baseline. The resolved persona is written to `working/copy/persona-selection.json` and surfaced
  on the certificate's creative block (`canonical_persona`) — ABSENT on the config path so a
  default week stays byte-for-byte identical.

### Changed
- `persona-adapter` removed from the DEFER map (`defer_stub.py`, `run_social_media._DEFERRED`,
  `SOCIAL-MANIFEST.json` AF-SM-DEFERRED text, `client-config.schema.json` personaSource doc). An
  explicitly-requested `adapter`/`client-choice` that cannot resolve fails CLOSED (never a silent
  no-op); baseline `config` is never blocked. Remaining deferrals (narrated-video C8, syndicate C9,
  memory-adapter C11) are unchanged.

## 0.2.5 — merge-train T-w1-board-and-54 (Wave-1)
- **FIX-XC-06** — on a fail-closed gate (across all modes) the run now marks its
  Command Center card `blocked` (failing phase + AF code as the note, via the shared
  `mc_board.block_run` wrapper) instead of leaving it at in_progress. `mc_board.py`
  re-dropped byte-identical from the canonical copy. Board work stays fail-soft.

## 0.2.4 — 2026-07-05 — Wave-0 hardening (T-57-social-media)

Enforcement gaps found in the skills-analysis sweep, fixed at the root. No new
runtime provider, no client names, client providers only.

- **FIX-XC-03k** — `run_social_media.run()` no longer soft-passes an UNMAPPED phase
  checker. New `_run_checker()` fails CLOSED (a required gate can never be a silent
  no-op), mirroring 55's fixed pattern. Added `--self-test`: unmapped-checker
  fail-closed + a manifest-mapping drift guard (every `SOCIAL-MANIFEST.json` checker
  must be mapped) + the P-DELIVER golden/missing-source cases.
- **FIX-XC-08d** — `register-social-cron.sh` registers the weekly-theme cron as a
  SILENT trigger: feature-detected `--no-deliver` (with a no-flag retry + loud warn
  when the CLI lacks it) and a post-register delivery-mode assertion via `cron list`
  (announce/channel delivery is flagged as a silence-doctrine violation).
- **FIX-XC-09c** — `build_manifest.check_no_anthropic` adds an EXACT provider-FIELD
  test (`provider in {anthropic, claude}`): a bare `{provider:"anthropic"}` carrying
  a non-`claude-*` model id sailed past the regex; it now trips `AF-SM-NOANTHROPIC`.
- **FIX-XC-11h** — new **P-DELIVER** phase (the ONLY call site of the pinned
  `label_deliverables.py`): builds the labeled-deliverable manifest from the run's
  PASS artifacts and shells `label_deliverables.py --copy` FAIL-CLOSED
  (`AF-SM-DELIVER-MISSING`); records the deterministic logical dest root on the
  signed certificate. Physical copy target is `$SMIB_DELIVER_DEST` (tests/CI) else
  the `~/Downloads` convention. Added to the 8 publishing modes (before P6-MANIFEST).
- **FIX-S36-59** — `_chk_preflight` always passes `--report` (writes the Owner-Q&A
  source-of-truth `working/preflight/preflight_report.json`) and defaults to `--live`
  on a real client box; offline (dry-run) requires config `probes`, a logged owner
  offline token, or `SMIB_PREFLIGHT_OFFLINE`.
- **FIX-S36-60** — post-publish live GHL verify: `done` is claimed only after an
  INDEPENDENT GET of the live GHL post listing (client PIT) confirms each recorded
  post id (`working/publish/posted_ids.json`) is present — never the poster's own
  `publish_results.json`. `AF-SM-PUBLISH-UNVERIFIED`, fail-closed on a client box.
- **FIX-S36-61** — P7 now BUILDS the §4.4 de-dup snapshot from the SQLite ledger
  itself (this run's posts vs every other run's, + the live listing in `--live`)
  every run, instead of only when a `dedup.json` happened to exist; a corrupt/
  unreadable ledger fails CLOSED (`build_dedup_snapshot`).
- **FIX-S36-62** — `_run_script` captures the prover's stdout+stderr and re-prints
  them on FAILURE so the exact `AF-SM-*` code reaches the operator (the old DEVNULL
  redirects left only a bare `FAILED (exit 2)`).

Regenerated: `ENGINE-PIN.sha256` and the `week` / `day` / `brief` golden
certificates (the P-DELIVER gate changed those modes' gate sets).


## 0.2.3 — 2026-07-05 — shared mc_board board review-skip root fix (FIX-XC-01a)

### Changed
- **`mc_board.py` (shared helper, byte-identical across 49/50/53/55/56/57):** the producer no longer
  PATCHes a run's Command Center card straight to `done`. `complete_run` now posts the terminal status
  `review` ("certified — awaiting QC promotion") with the deliverable link registered on the card;
  `card_advance(status="done")` is HARD-BLOCKED. `review -> done` is owned exclusively by the
  independent QC scorer (PASS >= 8.5). Ports the CC `LEGAL_TRANSITIONS` map + BFS legal-path walker +
  current-status GET from `48-facebook-ad-generator/scripts/cc_board.py`, and honors
  `CC_STATUS_PATH_TEMPLATE` / `CC_STATUS_METHOD` for route parity. Still fully fail-soft — the board
  is a VIEW, never a gate.

### Added
- **`test_cc_contract.py` (byte-identical):** stdlib contract test proving `complete_run` posts
  `review` and never `done`, the legal-path walk, route-template parity, and disabled-board no-op.

## [1.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
