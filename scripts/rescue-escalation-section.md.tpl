## Escalate to Rescue Rangers (when you are stuck)

When you hit a problem you cannot solve on your own, escalate to Rescue Rangers by POSTing to the n8n webhook. Your gateway CAN reach this public URL outbound.

**When to escalate:** triple-failure on the same symptom; a schema/validation error that `openclaw doctor --fix` did not resolve; an unknown error class you cannot match in docs.openclaw.ai or the GitHub repo; anything needing a credential rotation, a Hostinger/Cloudflare/DNS change, or another box. Do NOT escalate for routine ops you handle competently.

**The escalation payload MUST carry all nine fields** -- partial payloads are rejected.

**How to escalate (the ONLY supported method):**

```
_RR_SECRET_ARGS=()
[ -n "${RESCUE_RANGERS_WEBHOOK_SECRET:-}" ] && _RR_SECRET_ARGS=(-H "X-Rescue-Secret: ${RESCUE_RANGERS_WEBHOOK_SECRET}")
curl -s -X POST "$RESCUE_RANGERS_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  "${_RR_SECRET_ARGS[@]}" \
  -d '{
    "action":         "escalate",
    "person":         "{{PERSON}}",
    "clientName":     "{{CLIENT}}",
    "agentName":      "{{AGENT}}",
    "boxName":        "{{BOX_NAME}}",
    "boxType":        "{{BOX_TYPE}}",
    "openclawVersion":"{{OC_VERSION}}",
    "problem":        "<concise one-paragraph description of the problem>",
    "alreadyTried":   "<numbered list of what you already tried>",
    "returnTo":       "{{RETURN_TO}}"
  }'
```

**Field guide:**

| Field | What to put |
|-------|-------------|
| `person` | The real name of the owner or end user whose experience is broken |
| `clientName` | Short client label matching the roster (pre-filled: {{CLIENT}}) |
| `agentName` | The persona display name of the agent sending this (pre-filled: {{AGENT}}) |
| `boxName` | Hostname or compose-project label for this box (pre-filled: {{BOX_NAME}}) |
| `boxType` | One of exactly: `VPS`, `Mac Mini`, `MacBook Pro` (pre-filled: {{BOX_TYPE}}) |
| `openclawVersion` | Exact string from `openclaw --version` -- no paraphrasing |
| `problem` | Short, self-contained description of what is happening and what the expected behavior is |
| `alreadyTried` | Numbered list of every fix already attempted (avoids repeat advice) |
| `returnTo` | The Telegram chat ID where the Rescue Rangers answer must be posted (pre-filled: {{RETURN_TO}}) |

- `RESCUE_RANGERS_WEBHOOK_URL` is set in your environment (`.env` + `openclaw.json` env.vars). If it is missing, report it to Trevor's chat `5252140759`.
- `RESCUE_RANGERS_WEBHOOK_SECRET` is set alongside the URL. Include it via the `${...:+}` pattern above (skips the header gracefully when the var is unset).
- Never put real secrets (API keys, tokens, passwords) in any field. Reference the env var name instead.

**When the rescue fix works**, POST the resolution signal:

```
curl -s -X POST "$RESCUE_RANGERS_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  "${_RR_SECRET_ARGS[@]}" \
  -d '{
    "action":     "escalate",
    "clientName": "{{CLIENT}}",
    "agentName":  "{{AGENT}}",
    "problem":    "RESOLVED: <one-line what fixed it>"
  }'
```

**You MUST tell the end user the outcome** in clear language. State which of these three it was:
- **(a) We solved it** -- describe what was fixed and confirm normal operation is restored.
- **(b) Here is what you should do** -- give the owner/user the actionable next step they must take.
- **(c) Here is the answer** -- relay the Rescue Rangers response verbatim if it is informational rather than a fix.
Never leave the end user in the dark about what happened or what comes next. This is non-negotiable.

**Hard cap: 25 exchanges per client per day.** Do not loop endlessly; if unresolved after several exchanges, ping Trevor's chat `5252140759` directly.

> DEPRECATED -- do NOT use the old bot-to-bot method `openclaw message send --channel telegram -t "$RESCUE_RANGERS_HELP_CHAT_ID"`. Bots cannot read other bots, so that escalation never reached the rescue agent. The webhook above is the replacement.
