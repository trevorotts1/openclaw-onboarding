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

Add whatever helps you do your job. This is your cheat sheet.
