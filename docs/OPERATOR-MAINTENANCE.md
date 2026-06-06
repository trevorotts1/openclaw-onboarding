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
