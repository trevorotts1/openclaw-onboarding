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

## Unreleased — registration wiring (build unit U22, branch `skill62/cinematic-engine`)

Closes the "every registry/department-map registration" gap named in the 1.0.0 entry
above. On-branch only — not merged, not deployed, no version/tag ripple (deferred to
U25/U27 per the ledger). Frontmatter/`skill-version.txt` stay at `1.0.0` (no engine
behavior changed, wiring-only).

Added, in the shared fleet registration files (outside this skill directory):

- `23-ai-workforce-blueprint/skill-department-map.json` — Skill 62 client-facing entry:
  `departments: ["web-development"]`, primary role `funnel-builder-specialist`,
  10 plain-language intent triggers (spec §3.4), `execution_sops: ["funnel-craft",
  "website-craft", "video-pipeline-craft"]`. Closes the orphan check
  (`check-skill-department-map.py`: skill folder 62 existed on disk but was not in the
  map; now 0 violations, 62 skills / 28 client-facing).
- `06-ghl-install-pages/funnel-engines/registry.json` — third STEP-0 funnel-engine
  selector entry (`cinematic-web-funnel-engine`, priority 8, confidence_threshold 0.55),
  following the exact template Skills 49/56 already used. Proven not to hijack ordinary
  funnel/webinar/static requests or the other two engines' explicit names, and to route
  cinematic/animated/immersive/scroll requests correctly (see U22 ledger evidence).
- `cc-compat.json` — standard registration note: NO new Command Center endpoint, NO
  `mission-control.db` schema change, minVersion/pinnedTag UNCHANGED (v4.59.1 / v6.0.2).
- Generated/re-stamped from the map (idempotent, marker-guarded; no hand edits):
  `templates/role-library/web-development/funnel-builder-specialist.md` ("Skills You
  Operate" block), `templates/role-library/web-development/how-to-use-this-department.md`
  ("Skills This Department Can Operate For You" block), and the Intent-triggers headers
  in `universal-sops/funnel-craft/README.md`, `universal-sops/website-craft/README.md`
  (new block), and `universal-sops/video-pipeline-craft/README.md`. Content-hash
  manifests re-stamped clean (`23-ai-workforce-blueprint/scripts/hash-content-manifest.py`,
  `scripts/hash-universal-sops-manifest.py`).

Command Center generic-discovery no-change proof and any justified Command Center
enhancement are separate, later build units (U23/U24) — not part of this entry.
