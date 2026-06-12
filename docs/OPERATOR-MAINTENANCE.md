# Operator Maintenance & Telegram Channel Separation (FIX 2)

**Version:** v10.15.48
**Applies to:** every managed Mac/VPS client box.

## The problem this fixes

Each client box runs ONE Telegram bot and ONE agent (`main`). Message delivery
resolves "the chat from the last session" — which is almost always the owner's
DM. So when the operator (Trevor) self-pings the box for maintenance, or a
Rescue-Rangers escalation fires, or a resume cron drives a build, the message
**lands in the CLIENT's personal Telegram chat.** The client sees internal
operator traffic they were never meant to see.

## The fix: two Telegram accounts + a binding

`scripts/configure-operator-telegram.sh` (run automatically by `install.sh` and
re-applied idempotently) writes this structure into `openclaw.json`:

```json
{
  "channels": {
    "telegram": {
      "defaultAccount": "default",
      "accounts": {
        "default":  { "botToken": "<CLIENT bot>",   "dmPolicy": "pairing",   "allowFrom": ["<client chat id>"] },
        "operator": { "botToken": "<OPERATOR bot>",  "dmPolicy": "allowlist", "allowFrom": ["5252140759","6663821679","6771245262"] }
      }
    },
    "bindings": [
      { "channel": "telegram", "accountId": "operator", "agentId": "main" }
    ]
  }
}
```

- **`default`** = the client bot. Owner-facing. The client's chat id only.
- **`operator`** = a SEPARATE bot. Operator IDs only (`5252140759` /
  `6663821679` / `6771245262`). The client's id is **never** added here.
- **`defaultAccount: "default"`** keeps all owner-facing routing unchanged.
- The **binding** routes operator-account traffic to the same `main` agent but
  on an isolated session key, and replies go back out the **operator** bot.

The merge is **additive**: it never removes the client account and never narrows
the client's `allowFrom`.

## ⚠️ EXISTING BOXES NEED AN OPERATOR BOT TOKEN

The repo encodes the *structure*. A second Telegram bot still needs its own
token from **BotFather**. On a box that doesn't have one yet,
`configure-operator-telegram.sh` writes the operator account with an **empty
`botToken`** and reports:

```
STATUS: operator-telegram=STRUCTURE_ONLY_NEEDS_TOKEN
```

To finish provisioning an existing box:

1. Create an operator bot in BotFather (one operator bot can be reused across
   the fleet, or one per box — operator's choice).
2. Set the token on the box:
   ```bash
   echo 'OPERATOR_TELEGRAM_BOT_TOKEN=<token>' >> ~/.openclaw/secrets/.env
   # (VPS: /data/.openclaw/secrets/.env)
   ```
3. Re-run the (idempotent) configurator + propagate:
   ```bash
   bash ~/.openclaw/onboarding/scripts/configure-operator-telegram.sh
   ```
4. Verify:
   ```bash
   bash ~/.openclaw/onboarding/scripts/diagnose-telegram-config.sh
   # The "Operator channel separation (FIX 2)" block must show all ✓ PASS,
   # including "operator account HAS a bot token".
   ```

## The operator-drive contract (maintenance must NOT use the client chat)

When the operator or a cron drives **maintenance** on a client box, the message
MUST be sent on the operator session key and reply out the operator bot — NOT
the client's default chat:

```bash
# Drive maintenance on the OPERATOR session (isolated from agent:main:main):
openclaw message send \
  --channel telegram \
  --account operator \
  --session-key agent:main:operator \
  --reply-channel telegram \
  --reply-to "$OPERATOR_HELP_CHAT_ID"   # set in env.vars by the configurator
  --message "..."

# Or, for a fire-and-forget maintenance run with NO owner-facing delivery:
openclaw message send --session-key agent:main:operator --no-deliver --message "..."
```

`OPERATOR_HELP_CHAT_ID` is written into `openclaw.json` env.vars by
`configure-operator-telegram.sh` (defaults to `5252140759`).

**Rule:** owner-facing onboarding/closeout messages use the **default** account
(unchanged). Operator maintenance, Rescue-Rangers escalations, and resume-cron
self-pings use the **operator** account / session key. Never the reverse.

---

## Mac-tunnel Keepalive Hardening -- Existing-Fleet Remediation Playbook

**Background:** Every Wi-Fi Mac-tunnel client is exposed to repeated CF-1033 tunnel drops
caused by QUIC (UDP) NAT idle-timeout. The full diagnosis and 4-layer fix spec are in
`platform/mac/tunnel-hardening/README.md`. This section is the operator-facing
remediation runbook for the existing fleet.

Ledger: `~/clawd/fleet-heartbeat/mac-tunnel-keepalive-ledger.tsv`
Format: `client\ttimestamp\tkeepalive_pid\twatchdog_pid\tresult`

### Wave A -- no-sudo push (immediate; no client involvement)

For each Mac-tunnel client, SSH over the CF tunnel and run both user-space agents:

```bash
# SSH wrapper (non-login shell needs the full cloudflared path)
# ProxyCommand: /opt/homebrew/bin/cloudflared access ssh --hostname <tunnel-hostname>
# Remote commands via: ssh -o ProxyCommand=... <user>@<hostname> "zsh -lc '...'"

# Run on the client box as the login user:
bash ~/path/to/platform/mac/tunnel-hardening/install-keepalive-agent.sh
bash ~/path/to/platform/mac/tunnel-hardening/install-watchdog-agent.sh
```

The keepalive installer detects and replaces any existing `com.zhc.tunnel-keepalive`
(Christy's legacy label) -- no double-run.

Per-box verify after install:

```bash
launchctl print gui/$(id -u)/com.clawd.tunnel-keepalive | grep 'pid ='
# Must show a non-zero PID

tail -5 /tmp/clawd-tunnel-keepalive.log
# Expected after ~20s: [<ts>] edge-ping ok

launchctl print gui/$(id -u)/com.clawd.tunnel-watchdog | grep 'state ='
# Expected: state = running
```

Append to ledger when each box is done (append-only; skip already-done entries):

```bash
echo -e "<client>\t$(date -u +%FT%TZ)\t<keepalive_pid>\t<watchdog_pid>\tok" \
  >> ~/clawd/fleet-heartbeat/mac-tunnel-keepalive-ledger.tsv
```

Fan out in parallel (SSH/kickoff only; fire detached, do NOT babysit). Use Haiku for
the SSH/kickoff/poll; reserve Sonnet for real build work.

### Wave B -- one-time sudo harden per box (Layers A+B+D)

Stage `harden-mac-tunnel.sh` on each box, then instruct the client to run it once:

```bash
# Stage (operator over SSH)
scp platform/mac/tunnel-hardening/harden-mac-tunnel.sh \
  <client>:~/Downloads/harden-mac-tunnel.sh

# Instruction to the client (they enter their own password)
sudo bash ~/Downloads/harden-mac-tunnel.sh
```

After the client confirms, verify remotely (no sudo needed):

```bash
# Protocol is http2 in the LaunchDaemon
/usr/libexec/PlistBuddy -c "Print :ProgramArguments" \
  /Library/LaunchDaemons/com.cloudflare.cloudflared.plist | grep http2

# No recent QUIC drops in the connector log
grep 'no recent network activity' \
  /Library/Logs/com.cloudflare.cloudflared.err.log | tail -3
# Expected: empty or timestamps older than 30 min
```

Update the ledger with the sudo-harden timestamp when confirmed.

### Wave C -- close the loop

When a box has BOTH the http2 daemon (Wave B) AND the keepalive agent (Wave A), it is
fully hardened. The watchdog stays as the permanent safety net. Watch the watchdog log
for any ESCALATE lines that indicate the root connector went down:

```bash
grep ESCALATE /tmp/clawd-tunnel-watchdog.log
# If present: operator must run harden-mac-tunnel.sh on that box
```

### Fleet client priority (Wi-Fi clients first)

Check each client's network type before Wave A to prioritize effort:
- Wi-Fi clients: HIGH priority -- exposed to QUIC idle drops
- Wired Ethernet clients: lower urgency (drops rare but hardening is still recommended)

All Mac-tunnel clients get Wave A (keepalive + watchdog) regardless of network type.
