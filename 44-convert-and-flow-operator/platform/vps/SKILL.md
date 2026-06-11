---
name: convert-and-flow-operator
platform: vps
---

# Skill 44 — Convert and Flow Operator (VPS overlay)

Venv root: `/data/.openclaw/tools/convert-and-flow-cli/.venv`
Wrapper: `/data/.openclaw/tools/convert-and-flow-cli/caf`

## Firebase token on VPS

There is no Chrome in the Docker container. When the Firebase refresh token is expired or missing:
1. The agent sends a Telegram nudge to the owner: "I need you to grab the Convert and Flow token to build workflows directly."
2. The owner copies the token from their browser at https://app.gohighlevel.com
3. The owner pastes it to the agent in Telegram
4. The agent writes it to `/data/.openclaw/secrets/.env` and wires it via `openclaw config set`

See parent SKILL.md for the full skill description.
