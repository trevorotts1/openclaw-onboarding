# Skill 38 — Conversational AI System: Install Guide

## What this installs

The **conversational AI BRAIN** that runs on top of skill 29 (GHL Convert and Flow). Specifically:

- 32 v5.14 protocols (sales brain, intelligent follow-up, dual-mode customer service + support, typed knowledge bases, intelligent playbook routing, proactive features suite, weekly + monthly self-tuning, model version freshness, PII scrubbing, prompt-injection protection, conversation analytics, smart booking, discount codes for GHL + Stripe, Shopify integration, and more).
- 8 customer journey templates (coach + all 7 verticals fully detailed: e-commerce, SaaS, service-provider, course-creator, real-estate, consulting, wellness).
- 24 idempotent numbered install scripts (`00`–`23`, OS-aware: Darwin and Linux), plus `skill38-calendar-sync.sh` and the QC linters `qc-23-key-bodies.sh` + `qc-trinity-registry.sh` (27 `.sh` files total).
- 14 reference documents under `references/` (deep-dives + the full v6.0 source playbook + the strategic roadmap + the communications-playbook & workflow-AI/Build-with-AI standards + the **Cloudflare & GoDaddy Setup Guide** from School of AI — shipped INSIDE the skill so that when `scripts/00-verify-prerequisites.sh` halts on a missing CF API token per QC-PROTOCOL.md Rule 13, the client can be walked through Cloudflare account creation, GoDaddy nameserver migration, and API token scope selection without leaving the skill folder).
- AGENTS.md updates (Steps 1.7, 1.8, 1.9, 2.8 added; Step 1.75 upgraded).
- MEMORY.md design rules 6-14.
- 4 cron jobs: Sunday 2am weekly tune-up, Saturday 11pm proactive scan + 11:30pm model freshness, 1st-of-month comprehensive review.

## Prerequisites (ALL required)

This skill REFUSES to install until all 4 prerequisites are satisfied. The `00-verify-prerequisites.sh` script enforces this at the start.

1. **Skill 05 — GHL Setup** — GHL account + API access (`GHL_API_KEY`, `GHL_LOCATION_ID`).
2. **Skill 10 — GitHub Setup** — latest version. Do NOT auto-update; this skill verifies it's installed and current, and tells the operator to update skill 10 first if it's outdated.
3. **Skill 19 — Humanizer** — used ALWAYS-ON by this skill (per v5.14 Step 9.21). This skill does NOT ship its own humanizer; it references skill 19.
4. **Skill 29 — GHL Convert and Flow** — Convert and Flow installed AND connected to the operator's GHL location.

## What this does NOT do

- Does NOT install or modify skills 05, 10, 17, 18, 19, 29, 31.
- Does NOT replace skill 29. Skill 29 is the GENERIC GHL Convert and Flow setup; skill 38 is the conversational AI BRAIN that USES skill 29's workflow engine in unique ways (3-layer architecture in Step 9.20: Layer 0 routing check, Layer 1 GHL side with auto-tag + Workflow AI prompt + verification checklist, Layer 2 OpenClaw playbook).
- Does NOT implement pending roadmap features (F14 Voice, F15 Proactive Outreach Campaigns, F16 A/B Testing, F17 Segmentation, F18 Webhook Chaining, F21 Multi-Tenant Isolation).
- Does NOT auto-update primary models. Model freshness checks SUGGEST; operator approves YES/NO/DEFER per model.
- Does NOT generate discount codes outside per-product policy.

## Estimated install time

60-90 minutes per the v5.14 playbook (see `references/v6.0-source-playbook.md` for the full Phase-by-Phase walkthrough). The install scripts handle the mechanical parts; INSTRUCTIONS.md walks the operator through the interactive parts (model selection wizard, master files folder discovery, Notion playbook scaffolding, etc.).

## Install order (run the scripts in this order; each is idempotent)

```bash
cd ~/.openclaw/skills/38-conversational-ai-system/scripts

./00-verify-prerequisites.sh         # checks skills 05, 10, 19, 29
./01-locate-master-files-folder.sh   # Step O.2 semantic discovery
./02-create-knowledgebases.sh        # Step 9.22 four typed bases
./03-create-journey-templates.sh     # Step 9.28 customer journey templates
./04-register-crons.sh               # Sun 2am + Sat 11pm + 1st-of-month
./05-update-agents-md.sh             # Steps 1.7-1.9, 2.8, upgrade 1.75
./06-append-memory-rules.sh          # MEMORY.md design rules 6-14
./07-stripe-setup-wizard.sh          # Step 9.27 (operator opt-in)
./08-shopify-setup-wizard.sh         # Step 9.31 (operator opt-in)
```

After scripts run, follow INSTRUCTIONS.md for the interactive Phases 0-7 of the v5.14 playbook (Cloudflare tunnel creation, hook mappings configuration, Notion playbook scaffolding, channel-specific tone configuration, QC handoff).

## OS support

`darwin` (Mac mini operators) and `linux` (VPS operators). All scripts detect OS at runtime via `uname -s` and use OS-appropriate paths:

- **Darwin:** `$HOME/.openclaw/`, `$HOME/clawd/`
- **Linux:** `/data/.openclaw/`, `/data/clawd/`

## Where to read next

- `INSTRUCTIONS.md` — the operator-facing v5.14 walkthrough (Phase 0 through Phase 7).
- `protocols/` — the 32 v5.14 protocol files, verbatim from the source playbook.
- `references/v6.0-source-playbook.md` — the full 8,797-line source playbook (canonical source of truth).
- `references/conversational-ai-strategic-roadmap.md` — strategic context (✅ shipped vs 📋 pending).
