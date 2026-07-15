# Operator / Agent Instructions — Cinematic and Web Funnel Engine (Skill 62)

## When to use this skill

A client asks (in ordinary language) for an animated website, an immersive/cinematic
landing page, a scroll-story page, a premium interactive sales page or squeeze page, a
funnel that combines conversion content with AI-generated motion, or explicitly wants
"my website to move as I scroll." See `SKILL.md` frontmatter `description` and the intent
triggers in the spec, Section 3.4. Do not hijack ordinary static/video/funnel requests
that did not ask for the cinematic/animated/immersive treatment — that routing logic is
wired in a later unit (the `06-ghl-install-pages/funnel-engines/registry.json` selector
entry) and does not exist yet in this skeleton.

## How to run it (once later units land the phase gates)

Everything goes through the front door. Never call the orchestrator directly.

```bash
bash cinematic-web-funnel-entry.sh --run-dir <RUN_DIR>
```

The front door, in order: checks `python3` is present, checks `skill-version.txt` is
present/non-empty and matches the frontmatter major version, mints a run-scoped 0600
nonce, exports it, then invokes `run_cinematic_web_funnel.py --run-dir <RUN_DIR> --nonce
<NONCE>`. The orchestrator loads `CWFE-MANIFEST.json`, walks phases `P0` through `P16` in
order, shells each phase's declared gate script, and only emits `PROCESS-CERTIFICATE.json`
if every mandatory phase passes contiguously.

## Self-test (works today)

```bash
bash cinematic-web-funnel-entry.sh --self-test
```

This does NOT require a run directory and does NOT require any phase gate script to
exist. It proves the front door and orchestrator mechanics are sound: dependency check,
version lockstep, nonce enforcement, and manifest phase-order integrity.

## Current honest limitation

As of this build unit, no phase gate script exists on disk (see `CWFE-MANIFEST.json` →
`build_status`). Running `bash cinematic-web-funnel-entry.sh --run-dir <RUN_DIR>` today
will correctly walk to `P0-ENVIRONMENT`, find its gate script missing, and stop with a
fail-closed `GATE-SCRIPT-MISSING` result — no certificate, no partial credit. That is the
correct behavior for an engine with zero implemented phases; it is not evidence of a bug
in the front door or orchestrator.

## Delegation reminders for whoever builds the next unit

- Never hand-roll a Kie HTTP call, a GHL REST call, or a mail sender inside this skill.
  Extend `47-movie-producer/kie-adapters/` for media; delegate all GHL work to Skill 6
  (`06-ghl-install-pages`) / Skill 44 (`44-convert-and-flow-operator`).
- Never author sacred copy here. Consume a locked content manifest from Skill 49
  (`49-signature-funnel`) or Skill 56 (`56-sales-page-assets`) per ADR-10.
- Never use an Anthropic model ID in a client runtime path.
- Never log or persist a secret value — record presence by name only.
- No paid provider call before: P1 locked brief + P4 scene plan + a live registry price
  snapshot + P5 recorded budget-cap approval + an idempotency check (`AF-CWFE-PAID-GATE`).
