# Cinematic and Web Funnel Engine — Master Architecture Document (Skill 62)

Canonical source: `/Users/blackceomacmini/Downloads/cinematic-web-funnel-engine-docs/CINEMATIC-AND-WEB-FUNNEL-ENGINE-SPEC.md`.
This document is the in-repo orientation layer for anyone extending this skill; where the
two disagree, the spec wins.

## 1. What this engine is

A productized, client-facing capability that turns the open-sourced "Scroll World"
scroll-cinematic website technique into a governed production engine: intake, content
methodology delegation, bounded paid media generation on the client's own Kie.ai key,
deterministic phase gates, real-browser QC, Vercel deployment, and GoHighLevel (Convert
and Flow) conversion integration. The product is a complete, working, conversion-capable
website or funnel — not a video, not a demo.

## 2. Architecture Decision Record (binding — mirrors spec Section 5)

- **ADR-1** — It is a skill, not a department. Web Development owns it; supporting
  departments contribute through existing roles and skills.
- **ADR-2** — Vercel is the default application host. GHL remains the CRM/automation/
  conversion/calendar/form/payment/attribution platform.
- **ADR-3** — GHL-native full hosting is not the primary route. Three delivery modes:
  direct-hosted (default, Vercel), GHL iframe (supported), GHL-native lite (future,
  gated by a compatibility prover).
- **ADR-4** — Next.js/React/TypeScript own the site runtime: pages, components, routing,
  scroll behavior, forms, analytics, metadata, responsive layouts, reduced motion,
  deployment.
- **ADR-5** — Python owns orchestration: provider calls, manifests, cost calculations,
  paid-call approval, state transitions, downloads, FFmpeg orchestration, seam analysis,
  generation resumability, deterministic provers.
- **ADR-6** — Bash is the only canonical front door. All production runs begin through a
  fail-closed shell entrypoint (`cinematic-web-funnel-entry.sh`). Direct execution of the
  internal orchestrator (`run_cinematic_web_funnel.py`) is rejected unless a valid
  run-scoped nonce is present. This is enforced today — see Section 5.
- **ADR-7** — Kie.ai is the default provider, not a hard dependency in business logic. A
  provider interface is implemented; the engine must not scatter direct Kie HTTP calls
  throughout unrelated files.
- **ADR-8** — Seedance (`bytedance/seedance-1.5-pro`) is the default continuity model for
  final scene/connector renders (image-to-video with `input_urls` of 1-2 images pins the
  opening/closing frame); Veo (`veo3`/`veo3_fast`) is the premium optional override. Model
  slugs and prices resolve from the live Kie registry at build time — never hardcoded.
- **ADR-9** — Real encoded boundary frames are authoritative. The next clip or connector
  starts from the actual final frame extracted from the encoded preceding clip, never
  from the original still alone.
- **ADR-10** — The engine routes content methodology instead of duplicating it. Signature
  Funnel (Skill 49) and Sales-Page-Assets (Skill 56) retain ownership of their copy
  architecture and sacred gates; this engine owns cinematic planning, media generation,
  web assembly, scroll runtime, deployment, and cinematic-deliverable QC.

## 3. Canonical Phase Spine (P0-P16)

The full spine — phase id, required output, gate script, and `AF-CWFE-*` autofail code —
is the machine-readable source of truth in `CWFE-MANIFEST.json`. Human-readable summary:

| Phase | Name | Required output |
|---|---|---|
| P0 | Environment and dependency resolve | environment receipt, resolved model map |
| P1 | Intake | locked project brief and truth sources |
| P2 | Methodology selection | content engine decision and delegation receipt |
| P3 | Content | approved content manifest and copy QC receipt |
| P4 | Journey | scene plan, architecture, cost forecast |
| P5 | Budget approval | signed/recorded paid-call authorization |
| P6 | Concept and anchor | approved anchor and style contract |
| P7 | Scene stills | approved scene images and asset ledger |
| P8 | Draft motion | draft clips and review receipt |
| P9 | Final media | final scene/connector clips and task ledger |
| P10 | Encode and seam QC | browser media, boundary frames, seam report |
| P11 | Site build | Next.js project and build receipt |
| P12 | CRM integration | working GHL integration and event proof |
| P13 | Browser QC | desktop/mobile/reduced-motion/accessibility/performance report |
| P14 | Preview deployment | Vercel preview receipt |
| P15 | Final approval and production deploy | production receipt or approved handoff |
| P16 | Certification | signed process certificate and final artifact index |

A phase passes on artifacts + a deterministic gate script exit code, never on an agent's
claim. The certificate is emitted only if every mandatory phase passes contiguously.

## 4. Deterministic gates (binding — mirrors spec Section 17)

Intake gate, content gate, budget gate, media gate, site gate, conversion gate,
accessibility/performance gate, deployment gate, certificate gate — see the spec Section 17
for the exact validation list per gate. Each gate's enforcement point is named in
`CWFE-MANIFEST.json` (`gate` + `py_symbol` per phase).

## 5. What is real today (this build unit)

- The skill directory, frontmatter, and `skill-version.txt` are in lockstep (`1.0.0`).
- `CWFE-MANIFEST.json` declares the full P0-P16 spine and 22 `AF-CWFE-*` codes (17 phase
  codes + 5 cross-cutting: front-door, paid-gate, restart-duplicate, content-duplicate,
  secret-leak).
- `cinematic-web-funnel-entry.sh` is a real, fail-closed shell: it checks `python3` is on
  `PATH`, checks `skill-version.txt` is present/non-empty and matches the frontmatter
  major version, mints a run-scoped 0600 nonce file, exports it, and only then invokes
  the orchestrator with `--nonce`. A direct `python3 run_cinematic_web_funnel.py` call
  (no nonce, or a nonce that does not match the nonce file) is rejected with
  `AF-CWFE-FRONT-DOOR`.
- `run_cinematic_web_funnel.py` is a real, manifest-driven, no-skip state machine: it
  loads `CWFE-MANIFEST.json`, walks the phases in `order`, and for each phase looks for
  its declared `gate` script on disk. Because no gate script exists yet (those land in
  later build units — see `CWFE-MANIFEST.json` → `build_status`), every phase currently
  resolves `GATE-SCRIPT-MISSING` and the orchestrator correctly refuses to emit a
  certificate. This is fail-closed behavior working as designed at the skeleton stage,
  not a defect — a later unit adding a gate script for a phase makes that phase (and
  only that phase) real without touching the orchestrator's control flow.
- `--self-test` on both the entry shell and the orchestrator exercises: nonce
  enforcement, manifest load + phase-order validation, and the frontmatter/skill-version
  lockstep check (also independently checked by
  `scripts/qc-assert-skill-frontmatter-version.sh` at the repo root).

## 6. What is explicitly NOT built in this unit

Environment/model resolver, provider abstraction (Kie adapter extension), schemas/state
engine, budget gate logic, content-methodology router, intake artifacts, scene/journey
planner, image/video generation flow, FFmpeg pipeline, seam QC calibration, Next.js
template and scroll engine, GHL integration, Vercel deployment adapter, iframe embed
package, accessibility/performance paths, the actual phase provers, and the test suite.
Each is a separate, named work unit in the cinematic build ledger/checklist. Registering
this skill in `23-ai-workforce-blueprint/skill-department-map.json`, the
`06-ghl-install-pages/funnel-engines/registry.json` selector, and `cc-compat.json` is
likewise a later unit — this skeleton does not touch those files.
