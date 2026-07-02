# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

## MANDATORY — Teach Yourself Protocol (TYP) Storage Rule

**NEVER paste long playbooks, SOPs, or API docs (anything over ~25 lines) into this file.** Store the full document in the master-files TYP subfolder (`~/Downloads/openclaw-master-files/<subfolder>/` on Mac; `/data/.openclaw/master-files/<subfolder>/` on VPS), then write only a hyper-concise summary + explicit path pointer here. See the Teach Yourself Protocol skill (01-teach-yourself-protocol).

---

## GHL / Convert and Flow Auth (Skill 06 / Skill 44)

- GHL-AUTH-DOCTRINE: TOKEN-ONLY (D7) — refresh-token seed is the only auth path; NO auto UI-login / password / 2FA.
  Authenticate a build with `python3 06-ghl-install-pages/tools/seed-ghl-auth.py --print-seed --out /tmp/<sess>/seed.json` (mints a Firebase id_token from GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN) then `bash tools/inject-ghl-auth.sh <sess> /tmp/<sess>/seed.json --pre-open`. NO password, NO 2FA. On token failure STOP + re-grab via the Token Grabber.
- GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY.
  Canonical auth entry = the orchestrator `python3 06-ghl-install-pages/tools/ghl_auth.py --session <sess> --out /tmp/<sess>/seed.json` (3-tier ladder). It runs Tier 1 (the seed→inject above) and ONLY on token-absent/invalid evaluates the GATED Tier-2 email-2FA bootstrap: gate A authorization recorded, gate B Gmail-access PROVEN by a live read BEFORE any login, gate C email is the selected 2FA method, gate D agency creds in the CLIENT store. On success Tier 2 SELF-HEALS a fresh GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN into the client store so the next run is Tier 1. Bounded (<=3 attempts, backoff, hard-stop on lockout/captcha). Any gate fail / lockout -> Tier 3 fail-loud (non-zero exit) with a precise client instruction. ALL login/2FA code is contained in `tools/ghl_auth_fallback.py` (+ helper `tools/ghl_login_browser.py`); locked by `scripts/guard-ghl-auth-fallback.sh`. Client uses their OWN creds/keys ONLY; secrets NEVER in repo/logs/stdout.

---

## Funnel + Automation + Email Template Libraries (Skill 06 / Skill 44 / Skill 49 / Skill 50 / Skill 52 / Skill 55) — template-first / reuse-before-reinvent

- **Funnel template library (38 templates)** — `06-ghl-install-pages/funnel-templates/` by category
  (buyer, event, lead, retention-followup, traffic-advanced). Each carries `pageStructure`,
  `copyFramework`, `skill44Widgets`, persona/`books`, `whenToUse`/`doNotUseWhen`. Match with
  `python3 06-ghl-install-pages/tools/funnel_matcher_cli.py --match "<offer summary>" --json`
  (reads the committed `tools/catalog-index.json`; rebuild via `--build-index`). Runs as STEP 0 in
  `tools/v2_dispatcher.py` (env-gated on `GHL_FUNNEL_CATALOG`/`GHL_FUNNEL_INDEX`, never blocks).
- **Automation template library (28 templates)** — `44-convert-and-flow-operator/automation-templates/`
  (welcome-indoctrination, sales-close-sequences, engagement-broadcast, funnel-specific-followups,
  multichannel-automation). Match with
  `python3 44-convert-and-flow-operator/automation-templates/_matcher/cli.py --match "<outcome>" --json`
  (Skill-44 INSTRUCTIONS Step 0.4). Shared matcher core: `_matcher/flex.py`.
- **Email superlibrary (36 entries)** — `50-email-engine/email-library/` (13 marketing-email frameworks,
  4 buyer-types, 4 objectives, 12 persona styles, 3 named sequences: landing-page-10 / high-ticket-12 /
  buyer-type-12). Match with `python3 50-email-engine/tools/email_matcher_cli.py --match "<request>" --json`
  (reads the committed `email-library/catalog-index.json`; rebuild via `--build-index`). Every generated
  email/sequence is QC'd by the fail-closed `50-email-engine/tools/prove-email.py` floor prover (SACRED
  word/subject/CTA/signature bands) before a DRAFT-ONLY Skill-44 workflow deploy. Shared SOP cluster:
  `universal-sops/email-craft/`.
- **Signature Funnel engine (Skill 49)** — `49-signature-funnel/`, the SACRED Trevor Otts 12-section
  Hero funnel (configurable 3/5/7-step: Main → Checkout → Upsell → Downsell → Upsell-2 → Downsell-2 →
  Thank-You). Routed by the **shared STEP-0 funnel-engine selector** `06-ghl-install-pages/funnel-engines/registry.json`
  + `tools/funnel_engine_selector.py --match "<request>"` (a "signature funnel" request routes here;
  `NO_ENGINE_MATCH` falls through to the template matcher; Skill 56 registers a 2nd entry later).
  Built through the ONE canonical entry `49-signature-funnel/signature-funnel-entry.sh` under
  fail-closed provers (`scripts/prove_sf_*.py`); it AUTHORS copy + image prompts, delegates image
  generation to Skill 47 and ALL GHL media + build to Skill 6 (the ONE GHL delivery rail), and issues a
  signed certificate only on a full pass. Shared SOP cluster: `universal-sops/funnel-craft/`.
- **Product Bio Engine (Skill 55)** — `55-product-bio/`, the master-brain **Product Bio**: a
  6,000–7,000-word, 10-section sales knowledge base (10 intros, 15–20 power adjectives, ICP,
  description, positioning, 8–10 objections, 10–12 FAQs, 8–10 social proof, StoryBrand 2.0, 24 named
  signature closes + a completion-verification block) + its Google-Docs-importable HTML. Built through
  the ONE canonical entry `55-product-bio/product-bio-entry.sh` from a 4-field intake
  (`product_name`/`product_description`/`first_name`/`last_name`); the two verbatim system prompts are
  sha256-pinned and every SACRED count is MEASURED by fail-closed, model-free provers
  (`55-product-bio/scripts/prove_pb_*.py`) — self-reported counts ignored — with a signed certificate
  only on a full P0→P6 pass. Delivery is a labeled LOCAL bundle in `~/Downloads/` (no n8n / Google
  Drive / Slack / Gmail / Airtable). Cross-linked with, NEVER merged into, Skill 52 (routing: standalone
  master-brain bio → 55; brand-intelligence package → 52). Shared SOP cluster:
  `universal-sops/product-bio-craft/`. The Command Center `sops` row (`product-bio-master-brain-bio`,
  marketing dept) is added by the operator at CC install/update time (the mission-control repo is a
  separate submodule); no schema change (a job is a `tasks` row).
- **Avatar Alchemist Engine (Skill 52)** — `52-avatar-alchemist/`, the Avatar Alchemist
  brand-intelligence engine: ONE completed brand-intake interview → 40 generators across 7 subsystems
  (Avatar Core, Awareness, Bios, Tone, a 13-set Facebook Ad system, Booking Bots, Landing/Hero) → 16
  named deliverables (37 documents). A Book/Brand version selector runs FIRST (`version=brand` runs the
  40-stage pipeline; `version=book` routes to Skill 53 or parks fail-closed). Built through the ONE
  sanctioned front door `52-avatar-alchemist/entry.sh` (deps → bypass-scan → hash-pin → nonce) then
  the foreman `scripts/aa_director.py`; every SACRED count/floor is MEASURED by fail-closed, model-free
  provers (`scripts/aa_*.py`) — self-reported counts ignored — with a signed provenance certificate only
  on a full 40/40 pass. Delivery is a labeled LOCAL bundle in `~/Downloads/` (no n8n / Airtable / Drive /
  Slack / Gmail). Cross-linked with, NEVER merged into, Skill 55 (routing: standalone master-brain bio →
  55; full brand-intelligence package → 52). Shared SOP cluster: `universal-sops/avatar-craft/`. The
  Command Center `sops` row (`avatar-brand-intelligence-package`, marketing dept) is added by the
  operator at CC install/update time; no schema change (a job is a `tasks` row).
- **Shared tone / writing core** — `shared-utils/tone-writing-core/`, the provider-neutral SHARED module
  (blended-tone author + 4 tone-style analyzers + writing rails) referenced by the writing skills **52
  (brand)**, **53 (book)**, and **54 (anthology)**. Each consumer bakes a lockstep copy of the five tone
  prompt dirs and proves it against this canonical source at build/CI time (`verify_tone_core_sync.py`).
  Contract: `shared-utils/tone-writing-core/tone-core-manifest.json` (ZERO Anthropic ids — the client's
  own TIER models resolve them at runtime). See its `README.md` for how a new writing skill imports it.
- **Funnel→automation link map** — `44-.../automation-templates/_links/funnel-to-automation.json`
  (canonical v2; `…-link-map.json` is the DEPRECATED v1). Maps each funnel to its recommended
  follow-up automations; keyed by `funnel_template_id`.
- **Flexibility = guide-not-rule:** every template is a GUIDE/RESOURCE, never a rule. Honor an
  explicit user choice; CREATE_NEW + `save_new_template` only when nothing fits; never block a build.
- **Build-quality gate (FAB-QC ≥ 8.5):** `shared-utils/fab_qc.py` + rubric
  `universal-sops/funnel-automation-build-quality-rubric.md`. Run per build via
  `06-ghl-install-pages/qc-built-funnel.sh <slug>` or `44-.../qc-built-workflow.sh <wf-id> --fab`.

---

Add whatever helps you do your job. This is your cheat sheet.
