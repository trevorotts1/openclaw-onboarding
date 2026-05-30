# ⚙️ Things to consider when installing: VPS (Hostinger Docker) vs Mac mini

> **Scope:** the authoritative VPS-vs-Mac install-divergence reference for Skill 38. The generated client
> reference sheet (`scripts/21-generate-client-reference-sheet.sh`) emits this same section into the client's
> doc, and `scripts/qc-reference-sheet.sh --require-manual-fill` machine-enforces that BOTH the VPS points and
> the Mac points are present. Keep this doc and the generated section in sync — if you change one, change the
> other. Companion reference: `GHL-INBOUND-AND-PLAYBOOKS.md` (the Mac-mini / Homebrew GHL-inbound deep-dive,
> which flags the Mac-vs-VPS divergences inline).

OpenClaw runs on two kinds of box, and they handle config in **different places**. The single most common
fleet install failure is doing a VPS step on a Mac (or vice-versa): the env var ends up in the wrong file, a
plain `restart` silently fails to reload `env_file`, the `hooks.token` gets rewritten on boot, or a provider
key never reaches the gateway because it was not placed in the `openclaw.json` env block on a Mac. Use the
section that matches the box you are installing on.

**Which box am I on?** A **Hostinger Docker VPS** is a Linux server managed in the Hostinger panel with a
`/docker/<project>/` folder. A **Mac mini** is a physical/virtual Mac running OpenClaw via Homebrew + launchd.

---

## 🐧 VPS (Hostinger Docker)

- 🔑 **Env vars (API keys, tokens) live in the HOST file** `/docker/<project>/.env`. The Hostinger Docker
  Manager UI writes there — **NOT** to files inside the container under `/data/`. Existing keys
  (Anthropic / OpenAI / Gemini) already live there; that is the canonical place to ADD provider keys.
- 🔁 **Apply env changes with `docker compose up -d --force-recreate`** (run from `/docker/<project>/`). A
  plain `docker compose restart` does **NOT** reload `env_file` changes — the new vars never reach the running
  container, so the change silently does nothing. Always `up -d --force-recreate` after editing `.env`.
- 🔐 **GHL + the secrets the skill reads at runtime ALSO go in the container** `/data/.openclaw/secrets/.env` —
  that is where the GHL skill reads them. Both the host `.env` and the container `secrets/.env` persist (the
  `/data` bind mount), but only the host `.env` shows in `docker exec printenv` and matches the existing
  provider-key pattern.
- 🪝 **The hooks token gets REWRITTEN on every boot.** The `/hostinger/server.mjs` wrapper rewrites
  `hooks.token` to `hooks_${OPENCLAW_GATEWAY_TOKEN}` on every container boot — so a token you set by hand
  silently reverts on the next recreate. **To make your hooks token persistent, set `OPENCLAW_HOOKS_TOKEN` in
  the host `/docker/<project>/.env`** (then `docker compose up -d --force-recreate`); the wrapper honors
  `OPENCLAW_HOOKS_TOKEN` instead of rewriting. This is NOT `openclaw doctor` — it is the wrapper, and it runs
  every boot.
- 🔌 **The gateway port is often NOT 18789.** Read the actual `PORT` env var (or run `openclaw gateway status`)
  before assuming a port — Hostinger frequently maps a different one.
- 🌐 **Public hook URL** is exposed either via a **`cloudflared` tunnel** (run it under **PM2** and `pm2 save`
  so it survives a reboot) **OR** via an existing **Traefik route** (`*.hstgr.cloud`). You do **NOT** run
  `sudo cloudflared service install` on a VPS.
- 📦 **`apt` is a brew shim** on these containers (and brew is off PATH). Install packages with the full path:
  `/data/linuxbrew/.linuxbrew/bin/brew install <pkg>` — `apt` / `apt-get` will not do what you expect.

---

## 🍎 Mac mini (Homebrew / launchd)

- 🔑 **PROVIDER keys (e.g. `OLLAMA_API_KEY`) MUST go in the `openclaw.json` TOP-LEVEL `env` block.** The
  launchd service-env file does **NOT** carry provider keys to the gateway, and putting the key in
  `~/.openclaw/.env` **alone is insufficient** — the provider will fail to authenticate. Add provider keys to
  the `env` object at the top level of `~/.openclaw/openclaw.json`.
- 🔐 **GHL creds still live in** `~/.openclaw/secrets/.env` (same as the VPS — the GHL skill reads
  `secrets/.env`).
- 🔁 **Restart the gateway with** `launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway`. Because there is
  **NO Hostinger wrapper** on a Mac, the `hooks.token` in `openclaw.json` is **stable** — it is not rewritten
  on boot, and you do **NOT** need the `OPENCLAW_HOOKS_TOKEN` trick.
- 🛰️ **Remote access** is via a **Cloudflare tunnel + Access service token** (SSH in as the user's own login;
  wrap remote commands in `zsh -lc "..."` or `node` is off PATH).
- 🌐 **Public hook URL** is exposed via `sudo cloudflared service install <connector-token>` (installs a
  launchd LaunchDaemon). ⚠️ `sudo` prompts for the admin password and needs an **interactive Terminal** — it
  cannot run over a non-interactive rescue SSH session (no TTY). If operating remotely, hand this one command
  to the operator to run locally, then resume.

---

## 🤝 Common to BOTH (do not skip regardless of box)

- 📨 **The GHL Custom Webhook RAW BODY is the FLAT 23-key body** — never a shorter/stripped body, never nested.
  (See `GHL-INBOUND-AND-PLAYBOOKS.md` §0–§1 for the canonical 23-key spec.)
- 🔐 **GHL creds are read from `secrets/.env`** — container `/data/.openclaw/secrets/.env` on a VPS,
  `~/.openclaw/secrets/.env` on a Mac.
- 📁 **The `conversational-logs/` directory is node-owned** (the gateway process creates + appends the
  per-contact conversation logs there) — do not chown it away from the node user or memory writes fail.
- 🚫 **The inbound hook mapping uses `deliver: false`** (the agent sends its own reply via the GHL
  Conversations API; `deliver: true` double-sends and breaks the reply path).
- 🧠 **Ollama Cloud `:cloud` models hard-cap `maxTokens` at 65536** — set `maxTokens: 65536` (a 384k value
  returns HTTP 400 on every call and silently breaks your primary model). Set `contextWindow: 1048576`.
