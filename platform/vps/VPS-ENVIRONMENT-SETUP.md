# VPS Environment Variables Setup
## Complete this BEFORE running the install command

This guide walks you through setting up all required environment variables in Hostinger's hPanel. These variables survive container restarts and power your client's AI agent.

---

## How to Get There

1. Log into **hpanel.hostinger.com**
2. Click the client's VPS (e.g. `corey.myvps`)
3. Left sidebar → **Docker Manager**
4. Find the `openclaw-[id]` project → click **Manage**
5. Click **Edit** on the container
6. Scroll down to the **Environment** section

---

## SSH Key Setup (Trevor Only — One-Time Per Client)

Before running the install, Trevor must add the SSH key so the agent can connect to the VPS if needed.

1. In hPanel VPS overview → click **"SSH key → Manage"**
2. Add this public key:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIO4Bx1veA6T4y7SUA+qOsCM67ZKU45eggwcg0VPT/7tK stefanie@trevsmacmini
```
3. Save. Done. Trevor's agent can now SSH into this VPS anytime.

---

## Required Environment Variables

Set these in the hPanel Environment section BEFORE running install.

### Core (Always Required)

| Variable | Value | Notes |
|----------|-------|-------|
| `TZ` | e.g. `America/Chicago` | Client's timezone |
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Claude |
| `OPENAI_API_KEY` | `sk-proj-...` | GPT |
| `OPENROUTER_API_KEY` | `sk-or-...` | OpenRouter models |
| `GEMINI_API_KEY` | `AIza...` | Gemini |
| `MOONSHOT_API_KEY` | `sk-...` | Kimi |
| `MINIMAX_API_KEY` | `...` | MiniMax |

### Messaging

| Variable | Value | Notes |
|----------|-------|-------|
| `TELEGRAM_BOT_TOKEN` | `123456:ABC...` | Client's bot token |
| `TELEGRAM_CLIENT_CHAT_ID` | `1234567890` | Client's Telegram user ID |
| `TELEGRAM_TREVOR_CHAT_ID` | `5252140759` | Always Trevor's ID |
| `TELEGRAM_SPAULDING_CHAT_ID` | TBD | Add when known |
| `TELEGRAM_LEANNE_CHAT_ID` | TBD | Add when known |

### Convert and Flow (GHL)

| Variable | Value |
|----------|-------|
| `GOHIGHLEVEL_API_KEY` | Client's GHL API key |
| `GOHIGHLEVEL_LOCATION_ID` | Client's location ID |

### Google

| Variable | Value | Notes |
|----------|-------|-------|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON string | If using Google Workspace |
| `GMAIL_USERNAME` | `client@gmail.com` | If using regular Gmail |
| `GMAIL_PASSWORD` | App password | If using regular Gmail |

### Voice & Audio

| Variable | Value |
|----------|-------|
| `FISH_AUDIO_API_KEY` | Fish Audio key |
| `FISH_AUDIO_VOICE_ID` | Client's voice ID |
| `TELNYX_API_KEY` | Telnyx key (if applicable) |
| `TWILIO_ACCOUNT_SID` | Twilio SID (if applicable) |
| `TWILIO_AUTH_TOKEN` | Twilio token (if applicable) |

### Other Integrations (Add If Client Has Them)

| Variable | What It's For |
|----------|--------------|
| `GITHUB_TOKEN` | GitHub access |
| `TAVILY_API_KEY` | Web search |
| `KIE_API_KEY` | Image generation |
| `VERCEL_TOKEN` | Vercel deployments |
| `CONTEXT7_API_KEY` | API documentation |

---

## After Setting Variables

1. Click **Deploy** in Docker Manager to apply changes
2. Wait for deployment to complete
3. Then run the install command:
```
docker ps
docker exec -it [container-name] bash
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main/install.sh | bash
```

---

## Notes

- Variables set in hPanel persist across ALL container restarts
- Additional variables can also be added via SSH to `/docker/[project]/.env` — these also persist
- `OPENCLAW_GATEWAY_TOKEN` and `PORT` are pre-set by Hostinger — do not override them
