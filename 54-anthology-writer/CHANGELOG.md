# Changelog — Anthology Writer (Skill 54)

## 1.4.10 — 2026-08-25 — tone-core GO fixes: doctrine docs match deterministic resolver

- `intake/aw-intake-template.md` + `REPAIRS.md` G1 no longer describe prompt-level
  "auto-pick a real, well-known figure" — they now name the shared deterministic F4.3
  selector (`tone_persona_autopick.py`), logged, never prompt self-pick.
- Stripped the forbidden self-pick line from all five tone-stage `methodology.md`
  prompts; fixed "to modeo" → "to model" in the four `user.md` prompts (lockstep with
  shared core + 52/53). Runtime wiring shipped in skill 53 v1.3.1.

## 1.4.7 — 2026-08-02 — Warfix Round 2: FIX-14, FIX-20, FIX-27, FIX-32, FIX-35, FIX-36, FIX-37

### Fixed (Round 2 — FIX-14, FIX-20, FIX-27, FIX-32, FIX-35, FIX-36, FIX-37)
- **FIX-14** — interactive resolver heredoc no longer breaks operator input;
  `preflight.sh --resolve --interactive` prompts per tier as a real script.
- **FIX-20** — `--status` / `--resume` added; append-only verdict history in
  `process_manifest.json` (`runs[]`); ENGINE-PIN re-pinned.
- **FIX-27** — board card embeds run-dir / delivery path / cert SHA in
  `description`; mirrored to canonical `50-email-engine` mc_board.
- **FIX-32** — verify.sh EXIT trap extended to all 6 temp dirs (EXTMP/DTMP/
  PTMP/PRD).
- **FIX-35** — `_slug()`/`_slugify()` deduped (accepts str or dict); dead
  `_BYPASS_PATTERNS` deleted.
- **FIX-36** — `--json` stdout is pure JSON (gate chatter → stderr); ENGINE-PIN
  restored; `--plan --json` forwards the flag.
- **FIX-37** — CC board env vars documented (SKILL.md/INSTRUCTIONS.md);
  verify-deps warns on missing `COMMAND_CENTER_URL`; board-disabled message
  mirrored to `50-email-engine` mc_board.
- ENGINE-PIN → fe02b312.

## 1.4.6 — 2026-08-02 — Warfix batch 4: FIX-31, FIX-33, FIX-34

### Fixed (batch 4 — FIX-31, FIX-33, FIX-34)
- **FIX-31** — SKILL.md `trigger` key added; orphan doc refs cleaned.
- **FIX-33** — `sys.path.insert(0)` no longer shadows stdlib modules;
  ENGINE-PIN → 9031d9c9.
- **FIX-34** — status vocabulary standardized across surfaces (INFO/WARN/ERR
  severity on `mc_board._log`); propagated to canonical `50-email-engine`
  mc_board; ENGINE-PIN → 2a5f1e31.

## 1.4.5 — 2026-08-02 — Warfix batch 3: FIX-23..FIX-30

### Fixed (batch 3 — FIX-23 through FIX-30)
- **FIX-23** — `set -e` added to `preflight.sh` / `verify-deps.sh`; kept
  `set -uo` in `verify.sh` and `anthology-entry.sh` (set -e broke the test
  harness and gate_fail error capture). Dropped a stale
  `skills/54-anthology-writer/verify.sh` duplicate.
- **FIX-24** — transient prover failures retried (3 attempts, exponential
  backoff); combined with FIX-09 timeout helper; ENGINE-PIN → dea4fcfb.
- **FIX-25** — docs omit P0A-AVATAR; MASTERDOC + intake template updated.
- **FIX-26** — same-day bundle collision no longer silently overwrites;
  ENGINE-PIN → f3223749.
- **FIX-28** — negative attack-vector E2E fixtures (AF-AW-OVERRIDE-UNLOGGED,
  AF-AW-ENTRY-BYPASS .js, AF-AW-UNRESOLVED-MODELMAP).
- **FIX-29** — enforcement set single-sourced in `ENFORCEMENT-FILES.list`
  (incl. `prove_aw_model_role.py`).
- **FIX-30** — gate numbering corrected to 4/4; overlong `--plan` lines
  wrapped; ENGINE-PIN → 274a80d2.

## 1.4.4 — 2026-08-02 — Warfix batch 2: FIX-11..FIX-22

### Fixed (batch 2 — FIX-11 through FIX-22)
- **FIX-11** — department drift reconciled (SKILL.md / role.md / run_anthology.py
  all reference `marketing`); department-consistency check added to verify.sh.
- **FIX-12** — version-of-record reconciled to 1.4.3 across manifest / SKILL.md /
  skill-version.txt / CHANGELOG; version-consistency check added to verify.sh.
- **FIX-13** — model-role correctness enforced via `prove_aw_model_role.py`
  (joins enforcement set); ENGINE-PIN → 959e2b7d.
- **FIX-15** — claim-before-act on shared run dir; PID-suffixed receipt atomic
  merge propagated to canonical `50-email-engine/mc_board.py`; lock test added.
- **FIX-16** — GATE 2 bypass scan widened beyond `.py`; working-dir bypass
  fixtures added.
- **FIX-17** — boolean/numeric values blocked at intake gate (AF-AW-INTAKE-TYPE);
  ENGINE-PIN → 8d0c8675.
- **FIX-18** — `owner_skip_approval` merge not clobber; `{gate:"*"}` wildcard
  rejected through production path; ENGINE-PIN → 9b113eda.
- **FIX-19** — `_measure()` no longer swallows ImportError; ENGINE-PIN → 54039c2b.
- **FIX-21** — actionable recovery guidance on gate fail across provers/entry;
  ENGINE-PIN → 67e5a498.
- **FIX-22** — per-phase board heartbeat (`_mc_board_advance`); ENGINE-PIN →
  389c5081.

## 1.4.3 — 2026-08-02 — Warfix batch 1: FIX-01..FIX-10

### Fixed (batch 1 — FIX-01 through FIX-10)
- **FIX-01** — ENGINE-PIN.sha256 re-pinned to the 9-file enforcement-set hash
  (9cc672e884da…); GATE 3 fails CLOSED on a missing/empty pin.
- **FIX-02** — LLM authoring dispatch documented (INSTRUCTIONS.md step 3).
- **FIX-03** — preflight vs Gate 1B happy-path dead-end documented.
- **FIX-04** — seeded-defect E2E false-PASS oracle added to verify.sh.
- **FIX-05** — orphan assets wired: `assets/print-style.css` + retired HTML
  formatters documented.
- **FIX-06** — `mc_board.py` restored byte-identical to canonical
  `50-email-engine`; byte-identity check added to verify.sh (section 12).
- **FIX-07** — partial `--upto` run advances card to `review`, never parks at
  `in_progress`; ENGINE-PIN re-pinned to 451d6644db70 (run_anthology.py changed).
- **FIX-08** — CC Blocked-gate 400: blocked PATCH now carries
  `blocked_reason`/`blocked_on_human`/`ask`; fix + 2 contract tests propagated
  to canonical `50-email-engine/mc_board.py` to preserve byte-identity.
- **FIX-09** — subprocess execution chain gains timeout; ENGINE-PIN re-pinned to
  4b3944e1 (run_anthology.py changed).
- **FIX-10** — SKILL.md frontmatter strict-parseable + verify_yaml_frontmatter.sh.

## 1.4.2 — 2026-08-01 — FIX-01: ENGINE-PIN.sha256 stale/missing; GATE 3 hardens on missing pin

### Fixed
- **ENGINE-PIN.sha256** — recomputed against the 9 enforcement-set files
  (9cc672e884da3b232431e63374c6d92225d9ea6d1c20c76ace9207e1abcf4fc5); the
  previous pin was stale at HEAD and the file was deleted in the working tree.
- **GATE 3** (`anthology-entry.sh` `version_hash_pin`) — now fails CLOSED when
  `ENGINE-PIN.sha256` is MISSING or EMPTY (the old code fell through silently,
  disarming the hash-pin gate entirely).

## 1.4.1 — 2026-07-12 — P2-07: mc_board.py never silently drops an unrecognized department_slug

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
- **`test_cc_contract.py`** — this skill's `mc_board.py` shipped with NO contract
  test at all; it now carries the same shared board-contract suite as its sibling
  skills, plus six new regression cases for the department_slug reroute: an
  unrecognized slug reroutes to `general-task`, an empty slug reroutes, a known
  slug (`marketing`) and `general-task` itself pass through unchanged, the reroute
  logs loudly to stderr, and `begin_run`'s initial advance note records the
  original bad slug as a board-visible event.

## 1.4.0 — Wave-1 extension W1.3 (prompt completion, SPEC 3.2 item 2)
- **Two NEW baked authoring assets pinned into the SINGLE source of truth.**
  `assets/prompts/11-cover-image-prompt.md` (aw-11, cover-image prompt) and
  `assets/prompts/12-primary-goal-extraction.md` (aw-12, primary-goal extraction)
  are added to `ANTHOLOGY-MANIFEST.json -> source_prompt_pins`
  (`0525c7f9…` and `ca09a4b8…`), clearing the two `AF-AW-PROMPT-DRIFT`
  "unexpected prompt file present (unpinned IP)" autofails so
  `prove_aw_fidelity.py` is GREEN again. The pins live in ONE place (the manifest);
  the earlier parallel `assets/prompts/source_prompt_pins.json` (a second pins
  source that also embedded legacy n8n slot expressions) is **removed** — the
  per-component / composite SOURCE provenance stays operator-side in
  `.build-state/W0.2.json` (never committed).
- **08 & 10 byte-proved; NO re-pin.** `08-create-outline.md` (`5a944eaf…`) and
  `10-chapter-rewrite.md` (`56c4bf76…`) were re-hashed against their recorded pins
  at W1.3 — both MATCH the source-of-record, so the pins are unchanged (the pin
  inventory ends COMPLETE either way). Zero `[UNCHANGED]` placeholders remain in
  any baked body (a pin carrying one is a hard failure).
- **Wired into the phase machine (not inert).** `skill_version` `1.3.0 → 1.4.0`;
  the `tiers` block now names aw-11 under **MID-WRITER** and adds a **LIGHT** tier
  for aw-12; aw-12 is registered as the LIGHT-tier FINAL step of `P0A-AVATAR`
  (`phases[P0A-AVATAR].authoring_sequence`, binding `{{niche_primary_goal}}`
  confirmed, producing the carried value the downstream stages consume); aw-11 is
  registered in a new top-level `cover_prompt` block (MID-WRITER author / IMAGE
  render, 2:3 portrait 1024×1536 override, consumed by the engine's
  `stage_s7_cover.py` per SPEC S7). `model-map.template.json` reconciled: aw-11
  stays MID-WRITER, aw-12 moves to the new **LIGHT** tier, and the IMAGE-tier note
  that mislabelled the cover prompt as "aw-12" now correctly reads "aw-11".
- **No enforcement-script change.** `run_anthology.py`, the provers, and
  `_aw_common.py` are untouched, so `PHASE_ORDER` (9 phases), `ENGINE-PIN.sha256`,
  and the shipped example's `certificate_sha` are all unchanged — this extension is
  manifest/config/data-only. `prove_aw_avatar` + `verify_tone_core_sync` stay green
  (aw-12 is Skill 54's OWN baked IP and is deliberately NOT in
  `avatar_handoff.stages`).

## 1.3.0 — Wave-1 extension W1.2 (avatar handoff, SPEC 3.2 item 1)
- **W1.2 — pre-P1 avatar handoff, now LIVE (not inert).** Added the P0A-AVATAR
  phase to `run_anthology.py` `PHASE_ORDER` (immediately after P0-INTAKE, before
  P1-FIDELITY), a mapped `_chk_avatar` checker in `_CHECKERS`, and the fail-closed
  prover `scripts/prove_aw_avatar.py`. The handoff DELEGATES to Skill 52
  avatar-alchemist prompts `aa-01..aa-03` BY PATH (referenced at
  `../52-avatar-alchemist/prompts`, sha256-pinned in
  `ANTHOLOGY-MANIFEST.json -> avatar_handoff`); **no Skill 52 file is copied** and
  the tone core + the 5 baked authoring prompts are untouched (so
  `prove_aw_fidelity` + `verify_tone_core_sync` stay green). The prover decides the
  three manifest AF codes:
  - `AF-AW-AVATAR-MISSING` — `working/avatar.md` absent/empty/whitespace.
  - `AF-AW-AVATAR-HANDOFF-DRIFT` — a referenced Skill 52 prompt is missing at its
    pinned path or its sha256 ≠ the manifest pin (Skill 52 absent / tampered /
    version-drifted → fail closed, never a silent stale-IP fallback).
  - `AF-AW-AVATAR-COPIED` — a Skill 52 avatar prompt was copied into the tree.
- **Atomic enforcement set (the manifest `$schema_note` law: gate + AF code +
  checker + golden/attack fixture all land together).** Added golden fixture
  `test-fixtures/golden/avatar.md`, attack fixtures `avatar_empty.md`,
  `drifted-skill52/` and `copied-skill52-tree/`, plus `verify.sh` rows
  (self-test + golden PASS + three rejects) and a `run_anthology.py --self-test`
  block that proves the P0A wiring is live (in `PHASE_ORDER`, mapped, fail-closes
  on a missing dossier). `prove_aw_avatar.py` joins the pinned enforcement set in
  `anthology-entry.sh` GATE 3 + `verify.sh`; `ENGINE-PIN.sha256` re-pinned.
- **Descriptive accuracy (`Enforcement, not description`).** The manifest no
  longer claims `working/avatar.md` is "consumed by P1-FIDELITY" (its `_chk_fidelity`
  checker never reads it). The enforced contract is stated truthfully: P0A produces
  the dossier and REQUIRES it fail-closed before P1-FIDELITY; the downstream
  tone/chapter authoring templates consume it (carried_values).
- **Version-of-record reconciled.** `skill-version.txt` bumped 1.2.0 → 1.3.0 to
  match `ANTHOLOGY-MANIFEST.json` `skill_version`.
- The shipped example `golden-unbroken-ground` gains `working/avatar.md`; its
  `PROCESS-CERTIFICATE` + `process_manifest.json` are regenerated for the 9-phase
  chain (the certificate_sha changes because the phase steps changed).

## 1.2.0 — merge-train T-w1-board-and-54 (Wave-1)
- **FIX-S36-53** — the Anthology Writer shipped ZERO Command Center wiring (no
  `mc_board.py`, and `main()` never carded a run — every run was board-invisible).
  Added the shared drop-in `mc_board.py` + a `_mc_board_begin` / `_mc_board_done`
  seam in `main()` (department **books**, persona **Anthology Writer**): a run now
  lands ONE mc-route card and advances `in_progress` → `review` (NEVER `done` — the
  independent QC scorer owns review→done).
- **FIX-XC-06** — a gate failure used to strand the card at in_progress forever. On
  any fail-closed block the run now moves the card to `blocked` (via the shared
  `mc_board.block_run` wrapper) with the failing phase + AF code as the note.
- **FIX-S36-55** — the SKILL-promised labeled `~/Downloads/Anthology-<slug>-<date>/`
  bundle is now actually written (chapter, tone doc, outline, title, blurb,
  `DELIVERY-NOTE.md`, `handoff.json`, `PROCESS-CERTIFICATE`), redirectable via
  `ANTHOLOGY_DELIVERY_ROOT` so verify/tests never touch the operator's real
  `~/Downloads`. The back-cover **blurb** (`working/blurb.md`) is now PRODUCED and
  GATED: `_chk_deliver` requires it and fails closed on a missing / empty /
  placeholder / stub blurb (`AF-AW-BLURB-MISSING`), and it ships in the labeled
  bundle. Golden fixtures + the shipped example gain `blurb.md`; the manifest P5/P7
  + autofail table document the blurb; `ENGINE-PIN.sha256` re-pinned; the
  `run_anthology.py` self-test + `verify.sh` extended (certificate_sha unchanged —
  the blurb is not hashed, so the shipped example still reproduces its sha).

## 1.1.0 — merge-train T-54 (Wave-0 fix batch)
- **FIX-XC-03j** — ported Skill 55's fixed delivery gate: `_chk_deliver` was an
  evidence-free `return True` no-op (P7 certified with NO deliverable). It now
  assembles the slug-labeled LOCAL bundle from the QC'd working copies
  (chapter / tone-doc / outline / title), byte-verifies each, fails closed on a
  missing QC'd source (`AF-AW-STAGE-SKIPPED`) and on a swap-after-QC / planted
  deliverable (`AF-AW-DELIVER-MISMATCH`). `_run_checker` now FAILS CLOSED on an
  unmapped checker (was a silent soft-pass). Added `run_anthology.py --self-test`
  proving both gates bite; wired into `verify.sh`.
- **FIX-XC-09b** — model-sovereignty is fail-closed at P6: `working/RUN-LEDGER.json`
  is now REQUIRED (was checked only `if ledger.is_file()`), and `aw_build_check`
  hard-fails a ledger that records zero model ids (`AF-AW-PROVENANCE-MISSING`) so
  the no-Anthropic gate can never pass vacuously on an unproven run.
- **FIX-XC-11f** — the `roles/anthology-writer.role.md` role recipe is now
  referenced from `SKILL.md` (registered IP, not dead weight).
- **FIX-XC-12b** — client-exact overrides win: `prove_aw_chapter` / `prove_aw_tone`
  gain a `--band-override` sourced from a LOGGED, brief-tied `working/overrides.json`
  channel; an applied-but-unlogged override fails closed (`AF-AW-OVERRIDE-UNLOGGED`),
  and an applied override is recorded on the `PROCESS-CERTIFICATE`
  (`client_band_override`) and bound into the certificate sha.
- **FIX-S36-54** — shipped `ENGINE-PIN.sha256` over the enforcement-set concat so
  the entry's GATE 3 hash pin (`AF-AW-HASH-PIN`) can actually fail; `verify.sh`
  now asserts the pin matches and that a tampered enforcement file trips the gate
  (exit 7).
- **FIX-S36-56** — (i) `preflight.sh` gains a `--check` pre-gate that fails on a
  resolved `model-map.json` still carrying `<CLIENT_*>` placeholders / a banned id
  (`AF-AW-UNRESOLVED-MODELMAP`), now wired into `anthology-entry.sh` as GATE 1b;
  (ii) the QC phases now WRITE the manifest-declared `working/qc/tone_qc_report.json`
  and `working/qc/chapter_qc_report.json` prover verdicts (previously undeclared /
  unwritten).

## 1.0.0 — initial governed build
- Enforcement core: `ANTHOLOGY-MANIFEST.json` (P0→P7 phase machine + AF-AW-*
  autofail table), the fail-closed model-free provers (`prove_aw_intake`,
  `prove_aw_fidelity`, `prove_aw_tone`, `prove_aw_chapter`, `aw_build_check`) with
  a shared `_aw_common.py`, each with a `--self-test`.
- References `shared-utils/tone-writing-core`: bakes a lockstep copy of the five
  tone stages (04..08) into `prompts/` and proves it with `verify_tone_core_sync.py`
  (AF-AW-TONE-DRIFT). Separate skill, sibling of 53 Book Writer, sharing ONE core.
- Baked authoring IP (`assets/prompts/06..10`), sha256-pinned in the manifest;
  the five source HTML-formatter LLM calls retired (deterministic Python).
- NON-Anthropic build-fix applied everywhere: no concrete model id in any baked
  prompt; tiers (HEAVY-WRITER / MID-WRITER / RESEARCHER / IMAGE) resolved per box
  to the client's strongest NON-Anthropic model; runtime `aw_build_check.py`
  (G-NOANTHROPIC) + a static verify.sh scan.
- Canonical front door `anthology-entry.sh` (deps → bypass-scan → hash-pin →
  nonce) + deterministic orchestrator `run_anthology.py` (signed certificate on a
  full pass, deterministic sha ⇒ idempotent).
- Golden worked example `examples/golden-unbroken-ground/` (a full 3-artifact
  run with a real 2,118-word chapter + a 3,058-word tone doc) + one broken-variant
  per AF-AW-* code with a generated `REJECTION-RESULTS.json`.
- `verify.sh`: read-only, idempotent self-verify gate — green end-to-end.

## [v2.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
