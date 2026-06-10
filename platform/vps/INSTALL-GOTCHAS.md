# INSTALL-GOTCHAS — Hostinger Docker container edge cases

> **Read this BEFORE running install.sh on a fresh Hostinger Docker VPS.** Every gotcha here was discovered on a real client install and has a documented workaround. install.sh handles them automatically — this file exists so agents and humans can recognize the warnings/soft-failures in install logs without confusion.

This file is the single source of truth for known limitations of the **Hostinger `hvps-openclaw:latest`** Docker image (the container Hostinger's one-click Docker Manager deploys for OpenClaw clients). It covers what the image lacks, what the install.sh works around, and what's still genuinely broken pending an upstream fix.

Linked from `INSTALL-CONTRACT.md` Rule 12.

---

## 1. `unzip` is missing → install.sh uses python3 zipfile fallback

**Symptom (pre-v10.14.2):**
```
Step 4: Extracting Package
install.sh: line 1490: unzip: command not found
```

**Cause:** The Hostinger image ships `node`, `npm`, `python3`, `git`, `curl`, `brew` — but NOT `unzip`. install.sh Step 4 historically called `unzip` to extract the GitHub-archive zip.

**Workaround (shipped in v10.14.2):** install.sh now tries `unzip` first, falls back to `python3 -c "import zipfile; zipfile.ZipFile(...).extractall(...)"`. Python 3 is always present (the Hostinger entrypoint `/hostinger/server.mjs` and the credential-discovery scripts use it). Both methods are tested-equivalent for the zip the install downloads from GitHub.

**Log line you'll see:** `unzip not available; falling back to python3 zipfile extraction` — this is normal, not an error.

---

## 2. `wget` is missing → install.sh uses curl

**Symptom (pre-v10.14.3):**
```
Step 6: Installing Calibre…
⚠️  wget not available — cannot run Calibre Linux installer.
Skill 22 ebook extraction limited to PDF/EPUB.
```

**Cause:** The image has `curl` but not `wget`. install.sh used `wget` for the Calibre Linux installer fetch.

**Workaround (shipped in v10.14.3):** install.sh now uses `curl -fsSL -o /tmp/calibre-installer.sh https://download.calibre-ebook.com/linux-installer.sh`. Same result.

---

## 3. `lsof` is missing → gateway-restart stale-pid scan skips gracefully

**Symptom:**
```
[restart] lsof failed during initial stale-pid scan for port 18789: ENOENT
Gateway service disabled.
Start with: openclaw gateway install
```

**Cause:** The image has no `lsof`. `openclaw gateway restart` tries to find an existing gateway PID via `lsof -i :18789` first; without `lsof`, that scan fails with ENOENT. The subsequent "Gateway service disabled" output is also misleading (see #6 below).

**Workaround (shipped in v10.14.3):** install.sh's gateway-restart step is now CONDITIONAL — it checks `openclaw gateway status` first, and only restarts if the gateway is actually unhealthy. The Hostinger entrypoint hot-reloads `openclaw.json` and `AGENTS.md` on file change, so a restart is almost never needed after install.

**Log line you'll see:** `Gateway healthy — no restart needed.`

---

## 4. `apt` is rejected by Linuxbrew shell → use `brew install <pkg>`

**Symptom:**
```
apt-get install -y unzip
Error: apt is not available. Please use brew instead.
Example: brew install <package>
```

**Cause:** The Hostinger image overrides `apt` with a stub that refuses calls and redirects to Linuxbrew. This is intentional (forces consistent package management across Hostinger's stack).

**Workaround:** If you need a Linux utility installed inside the container, use `brew install <pkg>` (where pkg is on Linuxbrew). Examples that DO work:
- `brew install unzip` (~10 sec, ~666 KB)
- `brew install jq`
- `brew install ripgrep`

Examples that DON'T work (Linuxbrew formula refuses Linux):
- `brew install calibre` → see #5 below

---

## 5. Linuxbrew's `calibre` formula refuses Linux

**Symptom:**
```
brew install calibre
Error: macOS is required for this software.
==> Fetching downloads for: calibre
```

**Cause:** Calibre's Linuxbrew formula is macOS-only (Calibre on Linux is officially distributed via their installer script, not Linuxbrew). The formula errors out before even trying.

**Workaround (shipped in v10.14.3):** install.sh skips Linuxbrew for Calibre entirely on Linux. It goes directly to Calibre's official installer via `curl -fsSL https://download.calibre-ebook.com/linux-installer.sh | sh /dev/stdin install_dir=/data/.openclaw/calibre isolated=y`. The `install_dir` parameter avoids needing sudo. After install, ebook-convert is symlinked into `/data/.npm-global/bin/` (already on the node user's PATH).

**If Calibre install still fails:** Skill 22 (Book-to-Persona) falls back to PDF/EPUB-only via Python's pypdf and ebooklib. MOBI/AZW3/KFX won't work, but everything else does.

---

## 6. `channels.telegram` schema is strict — DO NOT add `botName`/`botUsername`

**Symptom:**
```
openclaw cron list
Error: Invalid config at /data/.openclaw/openclaw.json:
- channels.telegram: invalid config: must NOT have additional properties
- channels.telegram: invalid config: must NOT have additional properties
```

**Cause:** OpenClaw's config schema for `channels.telegram` is closed — only specific properties are allowed (`botToken`, `dmPolicy`, `groupPolicy`, `streaming`, `enabled`). Adding any other property (like `botName`, `botUsername`) makes the ENTIRE config invalid, which blocks `openclaw cron *` and `openclaw message send` commands.

**Workaround:** Bot identity metadata (name, username, display name, owner contact) belongs in a **sidecar file** at `/data/.openclaw/channel-metadata.json`. The Hostinger entrypoint doesn't validate sidecar files — they're free-form metadata for agents and humans to reference.

**Sidecar format:**
```json
{
  "telegram": {
    "botName": "Temperance",
    "botUsername": "TemperanceCEObot",
    "ownerChatId": "8279177438"
  }
}
```

install.sh and the Layer B onboarding agents read from this sidecar without going through schema validation.

---

## 7. Gateway "Service: systemd user (disabled)" status is MISLEADING

**Symptom:**
```
openclaw gateway status --verbose
Service: systemd user (disabled)
…
Runtime: unknown (Failed to connect to system scope bus via machine transport: Permission denied)
```

**Cause:** Inside the container, there's no systemd. The status output reports the SYSTEMD service is "disabled" because systemd isn't running. But the gateway IS running — supervised via the Hostinger entrypoint (`nohup` + `disown` style). The "Connectivity probe: ok" line lower in the same output is the actual health signal.

**Don't be fooled.** If you see:
- `Connectivity probe: ok` → gateway is up
- `Capability: write-capable` → gateway is up at write-scope (basic features work)

The systemd-service-disabled line is purely informational. Skip it.

**Don't try to fix it:** Running `openclaw gateway install` inside the container hits `systemctl daemon-reload failed: Failed to connect to system scope bus` — because there's no systemd. That's expected and fine; the gateway doesn't need systemd inside a container.

---

## 8. Scope upgrade for `operator.admin` requires owner approval

**Symptom:**
```
openclaw cron create …
gateway connect failed: GatewayClientRequestError: scope upgrade pending approval
(requestId: e6c267a7-…)
GatewayTransportError: gateway closed (1008): pairing required:
device is asking for more scopes than currently approved
```

**Cause:** install.sh's `auto_repair_cli_scopes` raises the CLI to `operator.write` automatically (basic chat works). But `openclaw cron create` and outbound `openclaw message send` require `operator.admin` — and OpenClaw refuses to auto-grant admin scope without owner consent. The request gets logged on the gateway, awaiting approval.

**Workaround:** After install, the owner sends a message to their Telegram bot and replies `approve` (or equivalent) when prompted. Until then:
- Sunday update cron isn't registered (but everything else works)
- Outbound `openclaw message send` from scripts fails (so the install.sh Telegram kickoff message doesn't deliver — but the terminal block + AGENTS.md flag still work)

**This is by design.** Not a bug to fix in install.sh. Document it in your client-handoff procedure: "After install, your bot will ask you to approve admin scope so it can set up the Sunday auto-update. Tap Approve."

---

## 9. Default install user is `node`, NOT `root`

**Symptom:** Files written by install.sh end up unreadable by the OpenClaw runtime.

**Cause:** Hostinger's container runs the OpenClaw process as the `node` user (UID 1000). `/data/.openclaw/` is owned `node:node` with `drwx------` (700). If install.sh runs as root (because someone `docker exec`'d without `-u node`), it creates root-owned files inside a 700-owner-only dir that the running node process can't read.

**Workaround (shipped in v10.14.0):** install.sh's auto-detect re-exec block uses `docker exec -u node -i …` automatically. If you ever invoke `docker exec` manually for ops, ALWAYS include `-u node`. The container's `Config.User` is `node` so omitting `-u` would default to that, but be explicit.

---

## 11. 🔴 `meta` block in openclaw.json is schema-strict — sidecar pattern for owner identity

**Symptom (discovered live during Maria's install):**
```
openclaw cron list
OpenClaw config is invalid
File: ~/.openclaw/openclaw.json
Problem:
  - meta: Invalid input
Fix: openclaw doctor --fix
```

And as a knock-on effect — install.sh's Step 10 dies silently:
```
Step 10: Writing UPDATE PENDING Flag to AGENTS.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<install log just stops here>
```

**Cause:** The `meta` block in openclaw.json is a **closed schema** — it accepts only specific keys (`lastTouchedAt`, `lastTouchedVersion`). Adding any other property (e.g. `meta.ownerName`) makes the entire config invalid. Then install.sh's Step 10 (line 1899 in v10.14.4) calls `openclaw config get agents.defaults.workspace` to resolve the workspace path; that CLI call validates config first, exits non-zero, and `set -euo pipefail` kills the entire script right there. No error message — the script just stops mid-step.

**Same family as Gotcha #6 (channels.telegram schema-strict).** Both `meta` and `channels.telegram` reject unknown properties.

**Workaround (canonical, shipped in v10.14.5):**

Owner identity and bot identity metadata both belong in a **sidecar file** outside openclaw.json:

`/data/.openclaw/channel-metadata.json`:
```json
{
  "_about": "Channel + owner identity metadata — outside openclaw.json schema. Read by install.sh v10.14.5+.",
  "ownerName": "Maria",
  "telegram": {
    "botName": "Sir Jordan",
    "botUsername": "SirJordanbot"
  }
}
```

install.sh v10.14.5+ reads this sidecar FIRST when resolving the owner's first name for the personalized greeting (Hi Maria! 👋), then falls back to `OPENCLAW_OWNER_NAME` env var, then to legacy openclaw.json fields (read-only fallback for backward compat). It **never writes** to openclaw.json's `meta` or `channels.telegram` blocks.

**Pre-install prep (recommended for client rollouts):** before running install.sh, write the sidecar:
```bash
docker exec -u node <container> python3 -c "
import json, os
META = '/data/.openclaw/channel-metadata.json'
existing = json.load(open(META)) if os.path.exists(META) else {}
existing['ownerName'] = 'Maria'
existing.setdefault('telegram', {}).update({'botName': 'Sir Jordan', 'botUsername': '@SirJordanbot'})
json.dump(existing, open(META, 'w'), indent=2)
print('Sidecar written:', existing)
"
```

**v10.14.5 also adds a pre-flight schema check at the top of install.sh** — if openclaw.json is invalid for ANY reason (not just meta.ownerName), install.sh bails immediately with a clear error message + pointer to this gotcha, instead of silently crashing mid-Step 10.

**Defensive belt-and-suspender:** Step 2 of Step 10's workspace resolver (line 1898-1907 in install.sh) now wraps the `openclaw config get` pipeline with `|| true`, so even if a sub-agent leaves config invalid mid-install, the script continues to a successful UPDATE PENDING flag write.

---

## 13. 🔴 Hostinger image ships TWO openclaw CLIs at different versions — auto-cleanup in v10.14.6+

**Symptom (discovered live during Evelyn's gateway restart):**
```
gateway connect failed: GatewayClientRequestError: protocol mismatch
protocol mismatch conn=… client=cli cli v2026.4.21 min=3 max=3 expected=4
```

And from the bot to the owner:
> "The openclaw cron commands are blocked by a CLI version mismatch (CLI is v2026.4.21, gateway is v2026.5.19)."

**Cause:** The Hostinger `hvps-openclaw:latest` image is built with `npm install -g openclaw` at image-build time. With default npm settings that installs to `/usr/local/lib/node_modules/openclaw` and symlinks to `/usr/local/bin/openclaw` — **pinned to whatever CLI version was current on the day the image was built**. We've seen baked-in versions as old as **v2026.4.21** (April images) and **v2026.5.7** (May images).

Meanwhile the container's runtime sets `NPM_CONFIG_PREFIX=/data/.npm-global` so that the `node` user can `npm install -g openclaw@latest` without root. When ANYTHING later does that (Hostinger startup, our install.sh, a skill, an operator), it installs the newer version to `/data/.npm-global/bin/openclaw` — leaving the old one at `/usr/local/bin/openclaw` orphaned but still callable.

PATH puts `/data/.npm-global/bin` first, so `openclaw` from a shell resolves to the new one. But:
- Any code that hardcodes `/usr/local/bin/openclaw`
- Anything that uses `npx openclaw` with a wrong package cache
- The Hostinger entrypoint's own subprocess paths in some cases

…will hit the STALE CLI. The newer gateway rejects the stale CLI's connection with `protocol mismatch` (the wire protocol bumped from v3 → v4 between 2026.5.7 and 2026.5.19). Result: `openclaw cron create` silently fails (Step 12), `openclaw message send` silently fails (Step 10/11 Telegram kickoff), the bot tells the owner to `/restart` but that doesn't fix the underlying duplicate.

**This affects EVERY Hostinger Docker-Manager-deployed OpenClaw VPS** — same baseline image, same dual-install defect.

**Workaround (auto-fix shipped in v10.14.6):**

install.sh v10.14.6+ detects the dual install in the auto-detect block (host-side, BEFORE the node-user install runs). It calls `docker exec -u root <container>` to:
- Compare versions of `/usr/local/bin/openclaw` vs `/data/.npm-global/bin/openclaw`
- If they differ, back up the stale one to `/data/.openclaw/backups/cli-cleanup-<ts>/`
- Remove `/usr/local/bin/openclaw` and `/usr/local/lib/node_modules/openclaw`

Idempotent — re-running is safe; if only one CLI exists, no action.

**For POST-INSTALL clients** (anyone already installed on v10.14.5 or earlier — Evelyn, Maria, Angela T as of 2026-05-21), use the standalone cleanup script:

```bash
# From the host, naming the container:
ssh root@<vps>
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main/scripts/fix-dual-cli.sh -o /tmp/fix-dual-cli.sh
bash /tmp/fix-dual-cli.sh <openclaw-container-name>

# Or all-in-one:
ssh root@<vps> "bash <(curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main/scripts/fix-dual-cli.sh) <openclaw-container-name>"
```

After cleanup, the bot's `openclaw cron create` and `openclaw message send` calls succeed — no `/restart` needed if the gateway has been hot-reloading. If the bot is still acting confused, send `/restart` once and it'll come back clean.

---

## 14. `apt-get update` not needed (and would fail anyway)

**Symptom (when someone ports install logic from a normal Debian/Ubuntu host):**
```
apt-get update
Error: apt is not available. Please use brew instead.
```

**Workaround:** Don't include `apt-get update` or `apt-get install` in any skill's INSTALL.md. Use `brew install` for Linux utilities or `pip3 install --break-system-packages` for Python packages.

---

## Summary table — what to expect

| Helper | Hostinger image has it? | install.sh handling |
|---|---|---|
| `curl` | ✅ yes | required |
| `python3` | ✅ yes (3.13) | required |
| `node` / `npm` | ✅ yes (22) | required |
| `git` | ✅ yes | required |
| `brew` (Linuxbrew) | ✅ yes | optional |
| `unzip` | ❌ no | python3 zipfile fallback (#1) |
| `wget` | ❌ no | curl fallback (#2) |
| `lsof` | ❌ no | conditional gateway restart (#3) |
| `apt` / `apt-get` | ❌ no (stub) | don't use; brew or pip instead (#4) |
| `systemd` (system D-Bus) | ❌ no | gateway runs via entrypoint, not systemd (#7) |

---

## If you hit a gotcha NOT documented here

1. Capture the exact error output
2. Note which Hostinger image version (`docker inspect <container> --format '{{.Config.Image}}'`)
3. File at https://github.com/trevorotts1/openclaw-onboarding-vps/issues with label `hostinger-edge-case`
4. Add an entry to this file in the same commit as the install.sh fix

**Last updated:** v10.14.3 (2026-05-21). Captured during the live install on client Evelyn Bethune (VPS 1651955) which surfaced 8 of the 10 gotchas above in a single ~25-minute session.
