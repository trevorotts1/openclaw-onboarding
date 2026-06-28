# Mac-Tunnel Keepalive Hardening

This kit makes every Mac-tunnel connector 24/7 reliable against the QUIC idle-timeout
drop that causes CF error 1033 / 530 on Wi-Fi boxes.

**Root cause (confirmed on a Mac client box, 287 drops in 22h):** cloudflared defaults to
QUIC (UDP). Consumer routers age out idle UDP NAT mappings in minutes. When the mapping
dies all four edge connections drop simultaneously, producing a ~6s gap where the tunnel
has no origin. Fix: force TCP (`--protocol http2`) so NAT-aging no longer applies.

---

## The 4 layers

| Layer | What it does | Privilege | File |
|---|---|---|---|
| A | `--protocol http2` in root LaunchDaemon (TCP, no UDP NAT expiry) | sudo | `harden-mac-tunnel.sh` |
| B | `KeepAlive=true` + `RunAtLoad=true` on the root daemon (unconditional respawn) | sudo | `harden-mac-tunnel.sh` |
| B-nosudo | `KeepAlive=true` user-level `cloudflared tunnel run` agent (auto-restart, no sudo) — for Macs running a named-tunnel user agent instead of the root daemon | no sudo | `install-tunnel-run-agent.sh` |
| C | 20s edge ping (keeps NAT warm even on QUIC; safety net before/after sudo harden) | no sudo | `install-keepalive-agent.sh` |
| D-nosudo | */5 watchdog (detects dead connector, logs ESCALATE for root daemon) | no sudo | `install-watchdog-agent.sh` |
| D-sudo | `pmset -c sleep 0` (AC no-sleep; box stays up on mains power) | sudo | `harden-mac-tunnel.sh` |

Layers C and D-nosudo alone stop most drops with no password. Layer A is the root fix.
Both together = fully bulletproof.

> **Service self-heal:** keeping the connector *connected* is this kit's job; keeping
> its LaunchAgent (and the OpenClaw gateway) *bootstrapped and running* after a
> boot-out is `platform/mac/service-selfheal/` (`remediate.sh`). Install both for a
> fully self-healing Mac.

---

## New installs (Bucket 1)

`38-conversational-ai-system/scripts/14-install-cloudflared-service.sh` now
automatically calls `harden-mac-tunnel.sh` (Layers A+B+D) immediately after the Darwin
`service install` step, then runs `install-keepalive-agent.sh` and
`install-watchdog-agent.sh` (Layers C+D-nosudo) as the login user. Every new Mac
connector is hardened at provision time.

---

## Existing clients (Bucket 2 + Bucket 3)

### Bucket 2 -- no-sudo push (run now, no client involvement)

SSH over the CF tunnel and run both user-space agents:

```bash
# On the client box, as the login user
bash platform/mac/tunnel-hardening/install-keepalive-agent.sh
bash platform/mac/tunnel-hardening/install-watchdog-agent.sh
```

Or use the fleet wave (see `docs/OPERATOR-MAINTENANCE.md`). Pre-existing
`com.zhc.tunnel-keepalive` is automatically replaced -- no double-run.

Verify keepalive is ticking after ~20s:

```bash
tail -5 /tmp/clawd-tunnel-keepalive.log
# Expect: [2026-...Z] edge-ping ok
```

### Bucket 3 -- one-time sudo harden (Layers A+B+D, per box)

Stage the script on the box and ask the client to run it once:

```bash
# Stage (operator runs over SSH)
scp platform/mac/tunnel-hardening/harden-mac-tunnel.sh <client>:~/Downloads/harden-mac-tunnel.sh

# Client runs (enters their own password)
sudo bash ~/Downloads/harden-mac-tunnel.sh
```

After they confirm, verify remotely (no sudo needed):

```bash
/usr/libexec/PlistBuddy -c "Print :ProgramArguments" \
  /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
# Must contain --protocol and http2

tail -20 /Library/Logs/com.cloudflare.cloudflared.err.log
# Should NOT contain "no recent network activity" within the next 30 min
```

Record each box in the fleet ledger:
`~/clawd/fleet-heartbeat/mac-tunnel-keepalive-ledger.tsv`

---

## Verify a fully hardened box

```bash
# 1. Connector is using http2
/usr/libexec/PlistBuddy -c "Print :ProgramArguments" \
  /Library/LaunchDaemons/com.cloudflare.cloudflared.plist | grep http2

# 2. KeepAlive is unconditional true (not a dict)
/usr/libexec/PlistBuddy -c "Print :KeepAlive" \
  /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
# Expected: true

# 3. Keepalive agent is running
launchctl print gui/$(id -u)/com.clawd.tunnel-keepalive | grep 'pid ='

# 4. Watchdog agent is loaded
launchctl print gui/$(id -u)/com.clawd.tunnel-watchdog | grep 'state ='

# 5. AC sleep disabled
pmset -g | grep -E 'sleep|disablesleep'
# Expected: sleep=0, disablesleep=1

# 6. No QUIC drops in the last hour
grep 'no recent network activity' \
  /Library/Logs/com.cloudflare.cloudflared.err.log 2>/dev/null | tail -3
# Expected: empty or timestamps > 30 min ago
```

---

## Cross-references

- `KNOWN-ISSUES.md` -- entry 4: Mac-tunnel Wi-Fi QUIC drop (CF 1033/530)
- `38-conversational-ai-system/references/cloudflare-tunnel-troubleshooting.md` -- Layer 2 protocol section
- `docs/OPERATOR-MAINTENANCE.md` -- existing-fleet remediation playbook
- `mac-mini-onboarding/connect-openclaw-to-cloudflare-tunnel.md` -- Step 7b
- Source diagnosis: Mac client live trace (287 drops, 22h)
- CF docs: developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/cloudflared-parameters/run-parameters (`--protocol`)
