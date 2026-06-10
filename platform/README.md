# platform/ — Platform Overlays

This directory contains platform-specific files for the two OpenClaw deployment targets. The root of this repo is the shared unified codebase (PRD 2.1).

## Structure

```
platform/
  mac/          — Mac mini / macOS-specific files
  vps/          — Hostinger Docker VPS-specific files
```

## How install.sh uses these

`install.sh` auto-detects the platform via `detect_platform()` in `lib-shared.sh` (presence of `/data/.openclaw` → VPS, otherwise → Mac). The platform is also settable via:

```bash
OPENCLAW_PLATFORM=mac  bash install.sh   # force Mac path
OPENCLAW_PLATFORM=vps  bash install.sh   # force VPS path
```

`install.sh` sources the appropriate `platform/<platform>/bootstrap.sh` before `set -euo pipefail`. That bootstrap file sets all canonical path variables (`OC_CONFIG`, `OC_JSON`, etc.) and runs platform-specific pre-flight checks (VPS: container re-exec + disk space; Mac: Homebrew prereqs).

## Key platform differences

| | Mac mini | Hostinger Docker VPS |
|---|---|---|
| `OC_CONFIG` | `~/.openclaw` | `/data/.openclaw` |
| `WORKSPACE` | `~/.openclaw/workspace` | `/data/.openclaw/workspace` |
| Backups | `~/Downloads/openclaw-backups` | `/data/.openclaw/backups` |
| Downloads | `~/Downloads` | `/data/Downloads` |
| Service mgmt | launchd | container nohup + cron |
| GHL MCP start | `scripts/ghl-mcp-autostart.sh` | `platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh` |
| Container re-exec | n/a | `platform/vps/bootstrap.sh` |

## Mac-specific files (`platform/mac/`)

- `bootstrap.sh` — Homebrew prereq check + Mac path variable setup
- `STT-TRANSCRIPTION.md` — Mac speech-to-text setup (OpenClaw desktop)

## VPS-specific files (`platform/vps/`)

- `bootstrap.sh` — Hostinger Docker container re-exec + disk pre-flight + path setup
- `VPS-ENVIRONMENT-SETUP.md` — hPanel environment variable guide
- `INSTALL-GOTCHAS.md` — Hostinger Docker edge cases
- `STT-TRANSCRIPTION.md` — VPS speech transcription reference
- `36-ghl-mcp-setup-scripts/` — GHL MCP server supervision (nohup + healthcheck)
- `vps-onboarding/` — Cloudflare tunnel connector setup
- `skills/` — VPS-bundled skill extras
