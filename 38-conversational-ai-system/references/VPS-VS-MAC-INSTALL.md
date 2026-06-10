# ⚙️ Things to consider when installing: VPS (Hostinger Docker) vs Mac mini (Skill 38)

> **Why this exists.** Skill 38 installs cleanly on BOTH a Hostinger Docker VPS and a
> Mac mini (Homebrew/launchd), but the two environments differ in WHERE env vars live,
> HOW you reload them, HOW you restart the gateway, and HOW the public hook is exposed.
> Getting these wrong is the #1 cause of "the hook went live but inbound messages do
> nothing" and "the token I set disappeared after a reboot." Read the column for the box
> you are on BEFORE you wire the GHL hook.
>
> This reference is MIRRORED verbatim into the generated client reference sheet
> (`scripts/21-generate-client-reference-sheet.sh`, the "⚙️ Things to consider when
> installing: VPS (Hostinger Docker) vs Mac mini" section) and is machine-enforced by
> `scripts/qc-reference-sheet.sh`. If you edit one, edit the other — the QC gate FAILs
> the generated doc if this section is missing or incomplete.

---

## 🟦 VPS (Hostinger Docker)

OpenClaw runs **inside a Docker container**. The host filesystem and the container
filesystem are different places; this trips up most installs.

- **Env vars live in the HOST file `/docker/<project>/.env`** (the docker-compose
  `env_file`). This is the canonical place to READ and ADD keys. See
  `references/HOSTINGER-DOCKER-ENV.md` for the full discovery sequence.
- **Apply env changes with `docker compose up -d --force-recreate`** —
  `docker compose -f /docker/<project>/docker-compose.yml up -d --force-recreate`.
  A plain `docker compose restart` does **NOT** reload `env_file` changes, so a key you
  add will be invisible to the running process until you force-recreate.
- **GHL / provider creds ALSO go in the container `/data/.openclaw/secrets/.env`** — the
  GHL skill reads its credentials from `secrets/.env` (it does not read the docker-compose
  `env_file`). On the host that file is `/docker/<project>/data/.openclaw/secrets/.env`
  (bind-mounted to `/data/.openclaw/secrets/.env` inside the container). Put the GHL
  Private-Integration token + location id there.
- **The `/hostinger/server.mjs` wrapper REWRITES `hooks.token` on EVERY container boot**
  to `$OPENCLAW_HOOKS_TOKEN || hooks_${OPENCLAW_GATEWAY_TOKEN}`. This is the wrapper, NOT
  `openclaw doctor`. To make the hooks bearer token PERSISTENT, set `OPENCLAW_HOOKS_TOKEN`
  in the host `/docker/<project>/.env` (then force-recreate). If you do not, any token you
  set by hand is silently replaced by `hooks_<gateway-token>` on the next boot, and the
  `Authorization: Bearer` value in your GHL hook stops matching.
- **The gateway port is often NOT 18789.** Do not assume it. Read the `PORT` env var or run
  `openclaw gateway status` and use the port it actually reports for the tunnel ingress and
  any `localhost:<PORT>` smoke test.
- **Public hook exposure** — either run `cloudflared` as a **PM2** process
  (`pm2 start ... && pm2 save` so it survives reboot) OR reuse an existing **Traefik**
  route (the `*.hstgr.cloud` ingress some boxes already have). Either way, the public
  hostname must terminate at the gateway's actual port.
- **`apt` is a Homebrew shim** on these boxes and brew is off PATH. Don't fight `apt` /
  `apt-get` / `apk` / `yum` — install packages with the full path
  `/data/linuxbrew/.linuxbrew/bin/brew install <pkg>`.

## 🍎 Mac mini (Homebrew / launchd)

OpenClaw runs natively as a launchd user service. No Docker; paths are under `$HOME`.

- **PROVIDER keys (e.g. `OLLAMA_API_KEY`) MUST go in the `openclaw.json` top-level `env`
  block.** The launchd service-env file does NOT carry provider keys to the running
  gateway, and `~/.openclaw/.env` alone is **insufficient** for provider auth — the model
  provider will fail to authenticate even though the key "looks set." Put provider keys in
  the `env` block at the top of `openclaw.json`.
- **GHL creds still live in `~/.openclaw/secrets/.env`** (same as the VPS pattern — the
  GHL skill reads `secrets/.env`).
- **Restart the gateway with**
  `launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway`.
- **Remote access** is via **Cloudflare Tunnel + an Access service token** (SSH in as the
  user's own login). Wrap remote commands in `zsh -lc "..."` or `node` is off PATH and the
  CLI fails with confusing errors.
- **Public hook exposure** — install `cloudflared` as a persistent system service with
  `sudo cloudflared service install <TOKEN>`.

## 🟰 COMMON to BOTH (non-negotiable, identical on every box)

- **The GHL Custom Webhook RAW BODY is the FLAT 23-key body — always.** 23 keys is the
  minimum AND the standard; never a stripped/short body, never nested objects. (See
  `references/GHL-INBOUND-AND-PLAYBOOKS.md` §14 for the canonical body.)
- **`deliver: false`** on the server `hooks.mappings` entry (the agent SENDS via the GHL
  Conversations API; OpenClaw does not auto-deliver the raw model output).
- **GHL creds are read from `secrets/.env`** (VPS: `/data/.openclaw/secrets/.env`;
  Mac: `~/.openclaw/secrets/.env`).
- **The `conversational-logs/` directory is node-owned** (the agent reads the per-contact
  log BEFORE replying and appends BOTH the inbound message and the sent reply AFTER —
  hook sessions are single-turn, so the per-contact log file IS the conversation memory).
- **Ollama Cloud `:cloud` models hard-cap `maxTokens` at 65536** (NOT the 384k spec). Set
  `maxTokens: 65536` / `contextWindow: 1048576`; a 384k `maxTokens` returns HTTP 400 on
  every call and silently breaks the primary model.
