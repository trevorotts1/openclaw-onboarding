# Changelog — Anthology Writer (Skill 54)

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
