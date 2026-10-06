---
name: cinematic-web-funnel-engine
description: Builds conversion-focused cinematic websites, landing pages, squeeze pages, sales pages, and multi-step funnels with complete copy, AI-generated scroll-controlled scenes, frame-matched video transitions, responsive Next.js delivery, Vercel deployment, and GoHighLevel/Convert and Flow integrations. Use when a client asks for an animated website, immersive landing page, cinematic funnel, scroll-story page, premium interactive web experience, or a funnel that combines conversion content with AI-generated motion.
version: v2.1.0
---

# Cinematic and Web Funnel Engine (Skill 62)

A governed production engine that turns the open-sourced "Scroll World" scroll-cinematic
website technique into a productized, client-facing capability: intake, content-methodology
delegation, bounded paid media generation on the client's own Kie.ai key, deterministic
phase gates, real-browser QC, Vercel deployment, and GoHighLevel (Convert and Flow)
conversion integration. Not a demo and not a video-background generator — a complete,
conversion-capable website/funnel builder whose visual story happens to be AI-generated and
scroll-controlled.

> The full binding contract lives in `MASTERDOC.md` and the source specification
> `CINEMATIC-AND-WEB-FUNNEL-ENGINE-SPEC.md` in the engine authoring-docs package.
> Where this file and the spec differ, the spec wins.

## Build status (this unit)

This is the **skeleton unit**: skill identity, machine-readable phase manifest, and the
fail-closed front door + orchestrator shell exist and are fully functional. The phase
gate scripts (provers), provider adapters, schemas, Next.js template, and tests are
separate, later build units (see `CWFE-MANIFEST.json` → `build_status` and the cinematic
checklist). Running the front door today correctly and honestly refuses to certify any
run, because no phase gate scripts exist yet — that is fail-closed behavior working as
designed, not a bug.

## What this skill owns / produces

- `MASTERDOC.md` — canonical architecture reference (ADRs, phase spine, gates, scope).
- `CWFE-MANIFEST.json` — the P0-P16 phase spine (`produces_artifact`, `gate`, `py_symbol`)
  and the `AF-CWFE-*` autofail codes (trigger / enforced_by / py_symbol), mirroring the
  `AF-FUN-*` pattern in `49-signature-funnel/FUNNEL-MANIFEST.json`.
- `cinematic-web-funnel-entry.sh` — the canonical fail-closed front door (ADR-6). Nothing
  may drive the orchestrator, call a provider, touch GHL, or mint a certificate except
  through this shell.
- `run_cinematic_web_funnel.py` — the no-skip, manifest-driven orchestrator state machine.
  Refuses to run without a valid front-door nonce (`AF-CWFE-FRONT-DOOR`); emits a signed
  `PROCESS-CERTIFICATE.json` only when every phase gate in the manifest passes.
- `INSTALL.md` — install/update contract for the onboarding installer.
- `INSTRUCTIONS.md` — operator/agent runbook for driving a project through the engine.
- `QC.md` — the engine-build QC contract (separate from generated-website QC).
- `CHANGELOG.md` — version history, starting at `1.0.0`.

## Ownership (binding, wired in a later unit)

**Primary department:** Web Development. **Primary role:** resolves to the best existing
live role after a role-library census (`funnel-builder-specialist` preferred, verified live
on Skill 49). **Supporting departments:** Marketing, Video, Graphics, CRM. This skill does
not duplicate the Signature Funnel (Skill 49) or Sales-Page-Assets (Skill 56) sacred copy
systems — it consumes their locked content manifests (ADR-10). The
`23-ai-workforce-blueprint/skill-department-map.json` entry, role-guide stamping, and the
`06-ghl-install-pages/funnel-engines/registry.json` third-engine registration are a later
work unit, not this skeleton.

## Delegation seams (never forked here)

- Image/video generation → Kie.ai on the client's own `KIE_API_KEY`, through Skill 74
  (`74-kie-live-adapter`, the one fleet KIE transport). `providers/kie.py` is not a Kie
  client any more: it calls Skill 74 per call in `active` mode for validate, prompt-budget,
  upload, createTask, wait, save and price, and keeps only this skill's policy (model
  registry, tiers, the Veo 3.1 wire shape, the quality-tier refusal). Each run logs
  `path=skill74`. If Skill 74 is not installed the quarantined `providers/_kie_legacy.py`
  fallback runs and logs `path=legacy`. Veo: this skill calls createTask with model
  `veo-3-1`, while 47 still uses the legacy `/api/v1/veo/generate` route. Veo price authority is
  the live catalog (`python3 74-kie-live-adapter/scripts/kie_live_adapter.py price --model veo-3-1`);
  the registry holds dated fallback constants only. Only the Fast id is sendable (no documented
  tier selector on `veo-3-1`; the Quality id is planned).
- GHL media/build/workflows → `06-ghl-install-pages` / `44-convert-and-flow-operator`
  (Skill 6 is the one GHL delivery rail).
- Vercel deployment → `08-vercel-setup`.
- GitHub → `10-github-setup`.
- Signature Funnel copy → `49-signature-funnel`. Direct-response copy → `56-sales-page-assets`.

## Client sovereignty

Client-owned credentials only. Never Anthropic model IDs in client runtime paths. No
secret values in code, logs, receipts, or artifacts — presence recorded by name only.
