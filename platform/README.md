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
| Service mgmt | launchd | pm2 + `pm2 save` + `@reboot pm2 resurrect` (container) |
| GHL MCP start | `scripts/ghl-mcp-autostart.sh` (launchd KeepAlive plist, `PORT` pinned) | `platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh` (pm2 ecosystem + save + resurrect; NO bare nohup; `PORT`+`MCP_SERVER_PORT` pinned) |
| Container re-exec | n/a | `platform/vps/bootstrap.sh` |
| **Ollama provider** | **Signed-in LOCAL daemon** — `baseUrl: http://127.0.0.1:11434`, `apiKey: ollama-local`; serves BOTH local + `:cloud` (see `docs/OLLAMA-PROVIDER-BY-PLATFORM.md`) | **Cloud-direct** — `baseUrl: https://ollama.com` + client's `OLLAMA_API_KEY`; no local daemon |
| **STT (speech-to-text)** | LOCAL `oc-faster-whisper` primary + OpenAI cloud fallback (`docs/STT-TRANSCRIPTION.md`) | Cloud transcription only (`platform/vps/STT-TRANSCRIPTION.md`) |

## Mac-specific files (`platform/mac/`)

- `bootstrap.sh` — Homebrew prereq check + Mac path variable setup
- `STT-TRANSCRIPTION.md` — Mac speech-to-text setup (OpenClaw desktop)
- `service-selfheal/` — gateway + cloudflared service self-heal and the gateway
  HTTP-health watchdog (`gateway-health-watchdog.sh`). Auto-installed by
  `install.sh` on Mac (end-of-install); also runnable by hand via
  `install-service-remediate.sh`.
- `tunnel-hardening/` — cloudflared connector hardening + no-sudo KeepAlive agents

## VPS-specific files (`platform/vps/`)

- `bootstrap.sh` — Hostinger Docker container re-exec + disk pre-flight + path setup
- `VPS-ENVIRONMENT-SETUP.md` — hPanel environment variable guide
- `INSTALL-GOTCHAS.md` — Hostinger Docker edge cases
- `STT-TRANSCRIPTION.md` — VPS speech transcription reference
- `36-ghl-mcp-setup-scripts/` — GHL MCP server supervision (nohup + healthcheck)
- `service-selfheal/install-host-watchdog-cron.sh` — operator-run HOST installer
  for the gateway HTTP-health watchdog (`*/5` host crontab; `docker restart`s the
  openclaw container when the gateway health fails). Runs on the Docker HOST, not
  inside the container.
- `vps-onboarding/` — Cloudflare tunnel connector setup
- `skills/` — VPS-bundled skill extras
