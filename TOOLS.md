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

## Funnel + Automation + Email Template Libraries (Skill 06 / Skill 44 / Skill 50) — template-first / reuse-before-reinvent

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
