# Changelog — Anthology Writer (Skill 54)

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
