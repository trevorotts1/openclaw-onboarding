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

`OPERATOR_HELP_CHAT_ID` / `OPERATOR_ESCALATION_CHAT_ID` are written into
`openclaw.json` env.vars by `configure-operator-telegram.sh` ONLY when an operator
escalation chat is explicitly provided. **There is NO hardcoded default (v12.4.0
co-mingling fix):** if none is configured, operator escalation is DISABLED and
maintenance/escalation/resume sends NO-OP rather than defaulting to any personal
chat. To enable, set `env.vars.OPERATOR_ESCALATION_CHAT_ID` to the operator chat id.

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
(legacy cron label) -- no double-run.

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

---

## Fleet Cloudflare Access Revocation Runbook (client offboarding)

**Applies to:** every managed Mac/VPS client box that fronts a loopback service behind
BlackCEO Cloudflare Access on the zerohumanworkforce.com zone (the Command Center, the
podcast dashboard, and any future per-client dashboard). This is the ONE fleet Cloudflare
revocation runbook. Per-skill revocation procedures are APPENDED here as blades, never split
into a second, competing runbook.

Purpose: when a client stops working with BlackCEO, cut their access to every BlackCEO-hosted
surface unilaterally and verifiably, from the Cloudflare edge inward, and do it without ever
messaging the client. Cutting a client off is a handful of Cloudflare API calls that BlackCEO
alone controls and the client cannot undo.

Preconditions (every blade):

- `CLOUDFLARE_API_TOKEN` confirmed SET in the operator secret stores. Confirm SET, never print
  its value. This token is operator-side only and never lives on a client box.
- Account ID 13f808b72eb78027a8046357c6cf1afa (`CLOUDFLARE_ACCOUNT_ID`, correct).
- Zone zerohumanworkforce.com = a9ecc0a067f52eaa4c59dc9b11d9dd55. Hardcode it or resolve it
  live via `GET /zones?name=zerohumanworkforce.com`. ZONE-ID TRAP: the `CLOUDFLARE_ZONE_ID`
  environment variable points at the WRONG zone. Never trust it; the scripts refuse to run if
  the resolved zone name is not zerohumanworkforce.com.
- Config edits on a client box run as the node user, never root (root-owned config freezes the
  gateway). Gateway restarts follow the fleet MASTER-only kickstart or detached-run doctrine; a
  revocation that downs a box still running other services is a FAILED revocation.

Silence: revocation emits ZERO client-facing messages. No client Telegram, no Convert and Flow
message, no email. Operator-verbose only: every step logs to the operator ledger and posts a
step-by-step operator report. Never source or trigger any client-notifying gate from here (for
example qc-completeness.sh standalone leaks a client Telegram alert; it is never run in a
revocation).

Edge-first ordering: kill live sessions before deleting routes so no logged-in session outlives
its hostname. The pure Cloudflare API steps (the edge blade) fully cut public access even when
the box is dark; box-side steps are recorded as pending in edge-only emergency mode.

### The three-blade kill switch

Every per-client offboarding pulls three blades, in order. Each blade is idempotent (safe to
re-run) and independently verifiable.

1. APPLICATION BLADE (the dashboard app layer, on the box). Rotate or delete the per-client
   dashboard bearer token in all box environment stores, then stop and deregister the dashboard
   service (PM2 delete on VPS boxes; launchd or cron-watchdog removal on Mac boxes, same SSH
   discipline). The data layer goes dead even if a port were ever exposed.
2. EDGE BLADE (Cloudflare only, no box access needed). Revoke live Access sessions, delete the
   Access app, delete the DNS record, remove the tunnel ingress rule. This alone cuts all public
   access and is the entire content of edge-only emergency mode.
3. ENGINE BLADE (the inbound engine, on the box). Remove the skill's hook mapping from the
   OpenClaw hooks config, rotate or delete the per-client hook secret, stop the skill's daily
   smoke-test cron, and drain the skill's held queues. The box stops accepting and stops working
   new jobs for the departed client.

### Podcast Production Engine blades (appended; scripted as revoke-podcast-client.sh)

The Podcast Production Engine ships `revoke-podcast-client.sh <slug>` in the skill's scripts
directory. It is the automation of the three blades above for the podcast surfaces and it is the
enforcement point for the SOP Podcast Revocation and Churn. Full endpoint shapes and the design
rationale live in `project-prds/podcast-engine/design/cloudflare-design.md` Section 3; every
endpoint is LIVE-VERIFY against current Cloudflare and OpenClaw docs before running. The nine
steps map onto the three blades:

Edge blade (steps 1 to 4, pure Cloudflare API, no box access):

1. Revoke live dashboard sessions on the Access app for `<slug>-podcast.zerohumanworkforce.com`
   (`POST /accounts/{account_id}/access/apps/{app_id}/revoke_tokens`) so anyone logged in is
   bounced instantly.
2. Delete that Access application (`DELETE /accounts/{account_id}/access/apps/{app_id}`); no new
   logins possible, allow-list gone.
3. Delete the dashboard DNS record for `<slug>-podcast.zerohumanworkforce.com` so the hostname
   stops resolving at the edge.
4. Remove the tunnel ingress routes for the podcast dashboard, and for the podcast hook path when
   the hooks hostname is podcast-only. If the hooks hostname is SHARED with other skills, leave
   the hostname and remove only the podcast hook mapping in the engine blade. Tenancy is recorded
   in the provision ledger so revocation never guesses.

Engine blade (steps 5, 7, 8, on the box, as the node user):

5. Remove the podcast intake hook mapping from the OpenClaw hooks config and rotate or delete
   `PODCAST_INTAKE_HOOK_SECRET` in all box environment stores, so even a resurrected route is
   dead. Apply config per gateway-restart doctrine and prove the gateway is back UP.
7. Stop the daily credit smoke-test cron for this client (`openclaw cron list`, identify the
   podcast smoke-test job id, `openclaw cron rm <id>`; also clear any crontab fallback) so the
   daily paid probes and the founder alerts stop.
8. Drain the podcast credit-out queue for this client, closing held jobs as client offboarded
   (not aged out) and reporting the dropped job ids to the operator channel only.

Application blade (step 6, on the box):

6. Rotate or delete `PODCAST_DASHBOARD_TOKEN` from the box environment stores and stop and
   deregister the dashboard service on 127.0.0.1:4010.

Independent end-to-end verification (step 9, no false done):

- 9a. `curl -sI https://<slug>-podcast.zerohumanworkforce.com` must NOT return 302 to
  sweet-wave-ca28.cloudflareaccess.com; expect a resolution failure or a Cloudflare 1016 or 530
  class error.
- 9b. A dummy POST to the old hook URL must fail (route gone or hook 404; anything but a 2xx).
- 9c. Cloudflare API reads confirm no Access app for the hostname, no DNS record, no ingress rule.
- 9d. Box reads confirm no hook mapping, tokens absent from the stores (SET-ness only, never
  printed), dashboard service not running, cron gone, and the gateway still healthy.
- 9e. Write the per-item ledger entry (the `/tmp/<sweep>/<slug>.json` pattern) and post the
  operator report. Only then is the revocation done.

Edge-only emergency mode: when the box is unreachable, run the edge blade (steps 1 to 4) plus
verifications 9a to 9c; this fully cuts public access from the Cloudflare side alone. Record the
application and engine blade steps as pending and re-run them idempotently once the box is back.

Churn cleanup rule: a departed client leaves ZERO recurring jobs behind. After the engine blade,
`guard-cron-inventory.py` must show no podcast smoke-test cron and no heartbeat entry for the box,
and the credit-out queue must hold no jobs for the slug. Re-provisioning a returning client is the
mirror path (`provision-podcast-client.sh`), proven on the operator canary box before any client
box is touched.

### Anthology Engine blades (appended; scripted as revoke-anthology-client.sh)

The Anthology Engine ships `revoke-anthology-client.sh --anthology-id <id> --confirm-name <name>
--live` in the skill's scripts directory. This subsection IS the SOP Anthology Revocation and
Churn: per PRD Section 13's SOP plan, it is appended to the fleet revocation runbook here rather
than authored as a separate craft document under `universal-sops/anthology-craft/`, so the fleet
keeps exactly the ONE revocation runbook and this never becomes a second, competing document.

UNLIKE the podcast and Command Center surfaces above, the Anthology Engine provisions NO new
Cloudflare hostname, Access application, or DNS record of its own: Layer 4 (the producer board and
the participant token page) lives INSIDE the producer's EXISTING Command Center, behind whatever
edge surface that box's Command Center already runs, and the intake webhook rides the box's
EXISTING hooks hostname (shared, WAF POST-only, per the same tenancy-in-the-ledger rule as the
podcast engine's shared hooks hostname). So the anthology blade below covers the APPLICATION and
ENGINE blades only; when a box's Command Center dashboard itself sits behind a dedicated Access
app, that app's edge blade is the standard two Cloudflare steps already documented above (revoke
sessions, delete the Access app) and is NOT duplicated here.

Full step detail and the design rationale live in `revoke-anthology-client.sh`'s own header (SPEC
Section 13.3); the eight R-steps run in this order, as the node user, never root:

1. R1, invalidate every outstanding participant gate token. Rotate `ANTHOLOGY_GATE_TOKEN_SECRET`
   (value NEVER printed); every token signed by the old secret then fails verification.
2. R2, archive the Anthology board cards (`mc_board.py`; FAIL-SOFT, board unreachability never
   blocks the churn).
3. R3, revoke Drive shares and hand back fresh view links (`drive_adapter.py revoke-share`; under
   the anyone-can-read delivery root, TRUE revocation moves the file out of the public subtree,
   surfaced, never guessed).
4. R4, disable the intake webhook route. Remove ONLY the anthology-intake mapping from the
   gateway hooks config; the box-wide hooks surface and every other integration (podcast, Command
   Center) are left intact, shared-box safe.
5. R5, produce the data-export bundle (`anthology_state.py export-bundle`; the client keeps their
   own record; the file carries NO secret).
6. R6, archive the ledger rows (`anthology_state.py upsert-anthology --status archived`;
   deactivate-never-delete, ninety-day retention).
7. R7, VERIFY. Probe a revoked token link and the disabled route; both must fail (bad_signature on
   the token, route gone or 404 on the webhook).
8. R8, prove ZERO recurring jobs remain. `guard-cron-inventory.py --expect zero` confirms no
   anthology daily tick and no heartbeat entry survive for this producer; the daily tick is
   removed as part of this step.

R7 and R8 are the ENFORCED gates: if a probe still answers or a recurring job survives, the script
exits 4. `--live` requires a typed `--confirm-name` matching the ledger anthology name (the same
typed-name discipline as the s9_ready trigger) and refuses to run as root.

Secret hygiene: both labels (`ANTHOLOGY_GATE_TOKEN_SECRET`, `ANTHOLOGY_INTAKE_HOOK_SECRET`) are
reported SET or NOT SET only; no value is ever printed, logged, or echoed. Convert and Flow naming
throughout; nothing Anthropic in this file or in the script it documents.

Churn cleanup rule: a departed producer leaves ZERO recurring jobs behind. After R8,
`guard-cron-inventory.py --sweep --producer-id <id> --roster <active-roster.json>` (or an inline
`--roster-id <id>`, repeatable, without a roster file) doubles as the fleet check for any anthology
cron belonging to a producer no longer on the active roster: an off-roster producer whose tick
still fires reports as CRON-ORPHAN, a nonzero (exit 4) result. This is the same standing guarantee
SOP-ANTHOLOGY-05 (Credit Health and Queue) owns for a healthy, active producer: exactly one cron,
never zero while active and never more than zero once churned.
