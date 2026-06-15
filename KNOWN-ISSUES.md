# Known OpenClaw Core Issues

These are defects in the OpenClaw core runtime that the onboarding repo
CANNOT patch directly (they live in the npm package, not in our skills or
scripts). Documented here so fleet operators recognize the symptoms fast,
apply the workaround, and file upstream. Last reviewed 2026-05-26 against
the openclaw dist installed on the fleet.

---

## 1. Memory embeddings stall blocks the agent loop

**Symptom:** Owner messages get no response. Logs show repeated
`embeddings rate limited; retrying`. The agent loop blocks BEFORE the LLM
call is ever made, because the memory-search embeddings step has no
timeout and sits in a retry spin while the embeddings provider rate-limits.

**Root cause:** The memorySearch embeddings call is awaited synchronously
ahead of the model call with no cap on retry/backoff. A throttled provider
therefore stalls the whole turn rather than degrading gracefully.

**Mitigation status: AUTO-APPLIED by install.sh (PRD 2.6, v11.8.3+)**

`install.sh` Step 7a (`configure_active_memory`) now automatically writes
the full fallback object and cache settings into `openclaw.json` whenever
BOTH a Gemini key AND an OpenAI key are present at install time. A QC check
(`qc_check_memory_search_fallback`) immediately asserts the keys are present
and auto-remediates if not.

You should NOT need to apply this workaround manually on boxes installed
with v11.8.3 or later. To verify a box is protected:

```bash
python3 -c "
import json
cfg = json.load(open('~/.openclaw/openclaw.json'.replace('~', __import__('os').path.expanduser('~'))))
ms = cfg.get('agents',{}).get('defaults',{}).get('memorySearch',{})
fb = ms.get('fallback')
print('OK' if isinstance(fb, dict) and fb.get('provider') and ms.get('cache') else 'MISSING')
"
```

**Manual workaround (boxes installed before v11.8.3 or single-provider
installs that later gained a second key):**

Config knobs confirmed present in the running dist:

- `memorySearch.fallback.provider`
- `memorySearch.fallback.model`
- `memorySearch.fallback.apiKey`

Configure a FAST fallback embeddings provider so a rate-limit on the
primary provider trips over to the fallback instead of spinning. Recommended:
point the fallback at a low-latency local or secondary-key provider distinct
from the primary. If the stall persists even with a fallback set, reduce
memory-search pressure by leaving caching on:

- `memorySearch.cache.enabled = true`
- `memorySearch.cache.maxEntries` (raise if the box has RAM headroom)

You can also disable memory search entirely as a last resort
(`memorySearch.enabled = false`) to confirm it is the cause.

**Upstream ask:** add an `embeddingTimeoutMs` (or equivalent) so the
embeddings step fails open to the LLM call after N ms instead of blocking
the turn indefinitely.

---

## 2. Stalled long-thinking-model session, recovery=none

**Symptom:** A session hangs with a log line like:

```
stalled session ... activeWorkKind=model_call lastProgress=model_call:started recovery=none
```

Seen with `deepseek-v4-pro` at `thinking=high` plus a deep message queue.
The model call starts, makes no further progress, and the StallWatchdog
reports `recovery=none` so nothing auto-recovers. The queue stays wedged.

**Root cause:** The stall watchdog detects the lack of progress but, for a
model call that has already entered the `model_call:started` state, it has
no recovery action wired (recovery=none), so it only observes the stall.

**Workaround (config knobs confirmed present in the running dist):**

- `agentTimeoutMs` / `agentTimeoutSeconds` -- set a bounded agent timeout so
  a wedged turn is force-ended instead of hanging forever. Pick a ceiling
  comfortably above your slowest legitimate deep-thinking turn (for high
  thinking on a heavy reasoning model, several minutes).
- When it happens live: `docker compose up -d --force-recreate` (or restart
  the container) to clear the wedged queue, OR swap the agent to a faster
  model (lower `thinking`, or a non-deep-reasoning model) until the backlog
  drains.

**Upstream ask:** wire a recovery action for `activeWorkKind=model_call`
stalls (cancel + requeue the turn) so the StallWatchdog can report a
non-`none` recovery instead of merely observing the wedge.

---

## 3. KIE nano-banana-2 image slug is account/region-dependent (422)

**Symptom:** Skill 37 closeout Infographic #2 (the "How Work Flows" diagram)
fails on submit with a KIE 422 like `model name not supported` for
`nano-banana-2`, even though the same slug works on other KIE accounts.
Seen on Teresa Pelham's KIE account 2026-05-27; it had worked elsewhere in
a prior release.

**Root cause:** Model availability on KIE is gated per account/region.
`nano-banana-2` (Gemini 3.1 Flash Image) is not enabled for every KIE
account, so a request that is valid on one account returns 422 on another.
This is a KIE provisioning behavior, not a slug typo.

**Workaround (already wired into the repo):**
`37-zhc-closeout/scripts/generate-infographics.sh` keeps `nano-banana-2` as
the PRIMARY model and falls back to `gpt-image-2-text-to-image` (the proven
safety net) when the primary is rejected. As of v10.X.8 the retry loop also
detects a `model name not supported` / 422 submit error and switches to the
fallback EARLY instead of burning both primary attempts. Override the primary
explicitly with `ZHC_IMAGE_MODEL` if a given account has a different preferred
slug. Do NOT remove `nano-banana-2` as the primary; it works on most accounts
and renders text better than the fallback.

**Upstream ask:** none (KIE account provisioning, not an OpenClaw defect).
The fallback chain is the durable fix.

---

## 4. Mac-tunnel goes offline every few minutes (CF error 1033 / 530) on Wi-Fi

**Symptom:** Client Mac reports the OpenClaw dashboard/tunnel is unreachable. Connector
log (`/Library/Logs/com.cloudflare.cloudflared.err.log`) shows repeated:

```
failed to accept QUIC stream: timeout: no recent network activity
```

All 4 edge connections drop simultaneously; CF returns error 1033 or 530 for ~6s
before reconnect. On wired Ethernet the problem is rare or absent.

**Root cause (confirmed: Christy Mac, 287 drops in 22h):**
cloudflared defaults to `--protocol quic` (UDP/7844). Consumer Wi-Fi routers age out
idle UDP NAT mappings in minutes. When the mapping expires, QUIC collapses before
cloudflared can recover it. The root LaunchDaemon also had `KeepAlive = {SuccessfulExit: false}`
meaning a clean exit zero would never auto-restart -- a latent respawn bug.

**This is a fleet-wide class issue for every Wi-Fi Mac-tunnel client.** Wired-Ethernet
boxes are mostly unaffected (longer NAT idle timers), but all Wi-Fi Mac boxes are exposed.

**Fix: 4-layer defense in depth (see `platform/mac/tunnel-hardening/`):**

| Layer | Effect | Privilege |
|---|---|---|
| A | `--protocol http2` in root daemon (TCP -- no UDP NAT expiry) | sudo |
| B | `KeepAlive=true` unconditional + `RunAtLoad=true` | sudo |
| C | 20s edge ping (keeps QUIC NAT warm; safety net) | no sudo |
| D | AC no-sleep (`pmset`) + */5 watchdog | sudo + no sudo |

Quick remediation for an existing box (Layer C alone stops most drops with no password):

```bash
# No sudo -- push now
bash platform/mac/tunnel-hardening/install-keepalive-agent.sh
bash platform/mac/tunnel-hardening/install-watchdog-agent.sh

# Sudo -- run once per box for full hardening
sudo bash platform/mac/tunnel-hardening/harden-mac-tunnel.sh
```

New installs: `14-install-cloudflared-service.sh` now applies all four layers
automatically at provision time.

**Upstream ask:** cloudflared should default to `--protocol http2` or `auto` on macOS
rather than QUIC-first, given how common consumer Wi-Fi NAT aging is.

See:
- `platform/mac/tunnel-hardening/README.md` -- full spec + verify block
- `38-conversational-ai-system/references/cloudflare-tunnel-troubleshooting.md` -- Layer 2 section
- `docs/OPERATOR-MAINTENANCE.md` -- existing-fleet remediation playbook

---

## 5. WhatsApp auto-install crash-loop (Hostinger Docker VPS only)

**Status: PERMANENTLY RESOLVED by fleet enforcement — no manual action needed on
boxes installed or updated with v12.14.3+.**

**Symptom:** Gateway goes into a crash-restart loop immediately on boot. Logs show
the WhatsApp plugin attempting QR-code pairing setup and then failing. The full
container goes offline; `docker compose logs` shows a repeating cycle of
gateway-start → WhatsApp init → crash → restart every few seconds.

**Root cause:** The Hostinger Docker wrapper (`server.mjs` boot logic) calls
`meetsRequirements()` and auto-installs + enables the WhatsApp plugin on **every**
gateway boot when `WHATSAPP_NUMBER` is set in the project `.env` file
(`/docker/<project>/.env`), regardless of what `openclaw.json` says. A bot that has
never been QR-paired with WhatsApp Web immediately crashes on that auto-install.
Setting `plugins.entries.whatsapp.enabled = false` alone is not sufficient because
the wrapper's boot sequence runs before the gateway reads `openclaw.json`.

**Permanent fix (auto-applied, no manual action needed on v12.14.3+ installs):**

`scripts/apply-fleet-standards.sh` and `install.sh` now:

1. Set `plugins.entries.whatsapp.enabled = false` in `openclaw.json` (prevents
   gateway activation even if the env var is present).
2. Comment out `WHATSAPP_NUMBER=<value>` in `/docker/<project>/.env` so the
   wrapper's `meetsRequirements()` check never triggers the auto-install path.

Both steps are idempotent and non-blocking. Step 2 creates a timestamped backup
before modifying the env file.

**If you are remediating a box manually:**

```bash
# Step 1 — comment out WHATSAPP_NUMBER in the Hostinger env file
# (replace <project> with your project folder name, e.g. openclaw)
ENVF="/docker/<project>/.env"
cp "$ENVF" "${ENVF}.bak-$(date +%Y%m%d%H%M%S)"
sed -i 's/^\(WHATSAPP_NUMBER=.*\)$/# WHATSAPP_NUMBER PERMANENTLY DISABLED\n# \1/' "$ENVF"

# Step 2 — disable in openclaw.json via fleet-standards script
bash ~/.openclaw/skills/scripts/apply-fleet-standards.sh

# Step 3 — force-recreate the container so it picks up the new env
docker compose up -d --force-recreate
```

**Why not just remove the WhatsApp plugin from the image?** The plugin ships with
the Hostinger Docker image (upstream OpenClaw). We cannot prevent its presence, but
we can prevent its activation. The two-layer fix (env file + openclaw.json) is the
durable solution.

**Fleet rule:** WhatsApp is permanently banned fleet-wide. `apply-fleet-standards.sh`
hard-fails if `plugins.entries.whatsapp.enabled = true` after the merge step. See
`FLEET-STANDARDS.md §3` for the full policy.

---

## Filing upstream

Issues 1-4 are core-runtime or infrastructure, not onboarding. File against the
openclaw project with the symptom log lines above. Until fixed, the workarounds here
keep the fleet responsive. The recommended fallback-embeddings and agent-timeout values
should be carried in the default onboarding config so fresh installs are protected by
default. Issue #5 (WhatsApp) has been permanently resolved at the fleet-standards layer
and does not require an upstream fix.
