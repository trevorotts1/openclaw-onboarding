# Changelog — Anthology Writer (Skill 54)

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
