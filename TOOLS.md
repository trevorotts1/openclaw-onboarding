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

Add whatever helps you do your job. This is your cheat sheet.
