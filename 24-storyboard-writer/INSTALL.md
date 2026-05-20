# Storyboard Writer - Installation Guide

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


## Teach Yourself Protocol (TYP) - Mandatory Read Order

Before you run any commands in this skill:

1. Discover every Markdown file in this skill folder (including subfolders):
   ```bash
   cd "$(dirname "$0")" 2>/dev/null || true
   find . -name "*.md" | sort
   ```
2. Read every discovered `.md` file.
3. Use this read order:
   1) `SKILL.md`
   2) `CORE_UPDATES.md`
   3) `INSTALL.md`
   4) `INSTRUCTIONS.md`
   5) `EXAMPLES.md`

Conflict rule:
- If any generic wrapper guidance conflicts with this skill folder, this skill folder wins.

## Install

This skill uses Python's standard library only.

## Usage

### Basic storyboard (run from the skill folder)

```bash
python3 scripts/create_storyboard.py --duration 300 --model veo-3-1 --topic "Product Demo" --output storyboard
```

### List available model IDs

```bash
python3 -c "from scripts.model_database import list_models; print('\n'.join(list_models()))"
```

## Output files

- `<output>.json` - machine-readable format
- `<output>.md` - human-readable storyboard with prompts

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

**During this installation, you may encounter instructions to restart the OpenClaw gateway.**

**YOU ARE FORBIDDEN from triggering gateway restarts yourself.**

### Correct Process
When a gateway restart is needed:
1. **STOP** - Do NOT execute the restart command
2. **NOTIFY** the user: "This installation requires an OpenClaw gateway restart to complete."
3. **INSTRUCT**: "Type `/restart` in Telegram to trigger it"
4. **WAIT** for user action - do NOT proceed until confirmed

### Forbidden Actions
- Do NOT run `openclaw gateway restart` without explicit user permission
- Do NOT say "I will restart the gateway now" without asking first
- Do NOT assume the user wants the restart

---
