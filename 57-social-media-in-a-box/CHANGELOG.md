# Changelog — Social Media in a Box (Skill 57)

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
