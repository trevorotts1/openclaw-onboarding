# ARCHIVED — DO NOT RUN — Skill 13: Google Workspace Setup

> **This skill is archived. Do not run its installer. Do not follow it as a procedure.**
>
> **Successor: Skill 14 — Google Workspace Integration (`14-google-workspace-integration/`).**

Skill 13 walked an operator through a Google Cloud project, six enabled APIs, a
service account, a downloaded JSON key and Domain-Wide Delegation, at install
time. That install-time OAuth dance is no longer how the fleet reaches Google.

## Why you must not run this

Following this procedure creates a Google Cloud project and a downloaded service
account key on a box that does not need either, and leaves long-lived key
material on disk. The routing rule this file used to open with — ask Workspace
versus Gmail, then branch — no longer has a live branch to route to. The file
also deferred parts of its own work to a skill number and a helper script that do
not exist in this repository, so an agent that followed it would stall partway
through with nothing to run.

## Where each capability went

| Old Skill 13 capability | Where it lives now |
|---|---|
| Google Workspace onboarding for the agent | `14-google-workspace-integration/` — the live skill |
| Gmail send and read | `claude_ai_Gmail` MCP server, authenticated per session |
| Google Calendar events | `claude_ai_Google_Calendar` MCP server; appointments via Skill 29 |
| Google Drive file operations | `claude_ai_Google_Drive` MCP server |
| Google Docs and Sheets editing | MCP tools directly — no install step |
| Workspace OAuth tokens | Per-session MCP authentication, not an install-time key file |

## Read instead

- `ARCHIVED.md` in this folder — the full archive record and the capability map.
- `14-google-workspace-integration/SKILL.md` — the live skill.

The folder is retained only so that older client onboardings that reference
"Skill 13" in their `MEMORY.md` or `.onboarding-status` files still resolve.
Nothing here is maintained, and nothing here is to be executed.
