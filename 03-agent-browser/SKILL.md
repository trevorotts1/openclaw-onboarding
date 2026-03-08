---
name: agent-browser
description: Install and use Vercel's agent-browser CLI for precise, ref-based browser automation. This is the preferred browser automation tool for OpenClaw onboarding and setup workflows.
---

# Agent Browser (Vercel) Skill

## What This Does

This skill ensures **agent-browser** is installed and usable.

agent-browser is our **preferred** browser automation tool because it:
- Produces accessibility snapshots with stable element refs (@e1, @e2, etc.)
- Lets the agent click/fill by ref for high-precision automation
- Is easier to operate reliably than ad-hoc browser clicking

## Where The Real Documentation Lives

This onboarding package includes a lightweight wrapper.

The full operational skill docs live on the machine at:
- `~/clawd/skills/agent-browser/SKILL.md`

If that path exists, treat it as the source of truth.
