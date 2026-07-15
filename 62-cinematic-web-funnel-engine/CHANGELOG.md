# Changelog — Cinematic and Web Funnel Engine (Skill 62)

## 1.0.0 — 2026-07-15

Initial skeleton (build unit U2, branch `skill62/cinematic-engine`).

Added:

- `SKILL.md` with frontmatter `name`/`description`/`version: 1.0.0`.
- `skill-version.txt` (`1.0.0`, lockstep with frontmatter per
  `scripts/qc-assert-skill-frontmatter-version.sh`).
- `CWFE-MANIFEST.json` — the P0-P16 phase spine (17 phases) and 22 `AF-CWFE-*` autofail
  codes (17 per-phase + 5 cross-cutting: front-door, paid-gate, restart-duplicate,
  content-duplicate, secret-leak), mirroring the `AF-FUN-*` pattern established in
  `49-signature-funnel/FUNNEL-MANIFEST.json`.
- `cinematic-web-funnel-entry.sh` — fail-closed front door (ADR-6): dependency check,
  version-lockstep check, run-scoped 0600 nonce mint/export, then orchestrator
  invocation. Mirrors the entry-shell pattern of Skills 49 and 56.
- `run_cinematic_web_funnel.py` — manifest-driven, no-skip orchestrator. Refuses to run
  without a nonce matching the front door's nonce file (`AF-CWFE-FRONT-DOOR`); walks
  `CWFE-MANIFEST.json` phases in order; emits `PROCESS-CERTIFICATE.json` only when every
  phase gate passes.
- `MASTERDOC.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `QC.md` (this changelog's siblings).

Not yet included (later build units): phase gate scripts, provider adapters, schemas,
state engine, budget gate logic, content-methodology router, intake, scene/journey
planner, image/video generation flow, FFmpeg pipeline, seam QC, Next.js template, GHL
integration, Vercel deployment adapter, iframe embed package, accessibility/performance
paths, tests, and every registry/department-map registration (`skill-department-map.json`,
`06-ghl-install-pages/funnel-engines/registry.json`, `cc-compat.json`).
