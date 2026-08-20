<!-- RESCUE_ESCALATION_BOXNAME_V2 -->
## Escalate to Rescue Rangers (when you are stuck)

When you hit a problem you cannot solve on your own, escalate to Rescue Rangers by POSTing to the n8n webhook. Your gateway CAN reach this public URL outbound.

**When to escalate:** triple-failure on the same symptom; a schema/validation error that `openclaw doctor --fix` did not resolve; an unknown error class you cannot match in docs.openclaw.ai or the GitHub repo; anything needing a credential rotation, a Hostinger/Cloudflare/DNS change, or another box. Do NOT escalate for routine ops you handle competently.

**IDENTITY IS MANDATORY AND IT IS NOT FREE TEXT.** The `boxName` field MUST be this box's canonical fleet slug, which is the value of the environment variable `FLEET_STANDING_BOX_SLUG`. For this box that value is `{{BOX_NAME}}`.

Never send any of these as `boxName`:
- a hostname (anything ending `.local`, or `mac.lan`)
- a Docker container id
- a company, brand, or trading name
- the word `TBD`, `unknown`, `n/a`, or a blank string

An escalation that arrives with the wrong `boxName` cannot be attributed to you, is not counted against your own daily cap, and cannot be checked against your account standing. Getting this field right is the whole point of the field.

**The escalation payload MUST carry all nine fields** -- partial payloads are rejected.

**Loop / stuck / no-reply symptoms get a `LOOP:` prefix.** If the problem you are escalating is "it keeps looping", "it's stuck", "I got nothing back", or anything else where the client experience is repetition or silence, prefix the `problem` field with `LOOP:` (e.g. `"problem": "LOOP: agent re-ran the same tool call five times with no reply"`). This routes the ticket to the loop/stuck/no-reply triage runbook (`universal-sops/SOP-RR-LOOP-TRIAGE.md`) so a responder -- or an automated first pass running `scripts/rr-triage.sh` -- starts at that runbook's Step 0 instead of guessing the mechanism from free text. Do not prefix anything else with `LOOP:` -- it is a routing signal, not emphasis.

**How to escalate (the ONLY supported method):**

```
_RR_SECRET_ARGS=()
[ -n "${RESCUE_RANGERS_WEBHOOK_SECRET:-}" ] && _RR_SECRET_ARGS=(-H "X-Rescue-Secret: ${RESCUE_RANGERS_WEBHOOK_SECRET}")
_RR_BOX="${FLEET_STANDING_BOX_SLUG:-{{BOX_NAME}}}"
cat > /tmp/rr-escalation.json <<JSON
{
  "action":          "escalate",
  "person":          "<real name of the owner or end user this agent serves>",
  "clientName":      "{{CLIENT}}",
  "agentName":       "{{AGENT}}",
  "boxName":         "$_RR_BOX",
  "boxType":         "{{BOX_TYPE}}",
  "openclawVersion": "<run: openclaw --version>",
  "problem":         "<one paragraph, plain text, no double-quote characters>",
  "alreadyTried":    "<numbered list, plain text, no double-quote characters>",
  "returnTo":        "{{RETURN_TO}}"
}
JSON
curl -s -X POST "$RESCUE_RANGERS_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  "${_RR_SECRET_ARGS[@]}" \
  --data-binary @/tmp/rr-escalation.json
rm -f /tmp/rr-escalation.json
```

The heredoc above is deliberately UNQUOTED (`<<JSON`, not `<<'JSON'`) so that `$_RR_BOX` expands to the real slug. Do not quote it. Do not inline the JSON into `-d '...'` single quotes -- the variable would not expand and you would send the literal text `$_RR_BOX`.

**Field guide:**

| Field | What to put |
|-------|-------------|
| `person` | The real name of the owner or end user whose experience is broken |
| `clientName` | Pre-filled: {{CLIENT}} |
| `agentName` | Pre-filled: {{AGENT}} |
| `boxName` | The value of `$FLEET_STANDING_BOX_SLUG`. For this box: `{{BOX_NAME}}` |
| `boxType` | Pre-filled: {{BOX_TYPE}} |
| `openclawVersion` | Exact string from `openclaw --version` -- no paraphrasing |
| `problem` | Short, self-contained description of what is happening |
| `alreadyTried` | Numbered list of every fix already attempted (avoids repeat advice) |
| `returnTo` | The Telegram chat ID where the Rescue Rangers answer must be posted |

- `RESCUE_RANGERS_WEBHOOK_URL` is set in your environment. If missing, report to Trevor's chat `5252140759`.
- `RESCUE_RANGERS_WEBHOOK_SECRET` is set alongside the URL. The array pattern above skips the header when unset.
- `FLEET_STANDING_BOX_SLUG` is set in your environment. If it is missing, that is itself a setup gap -- use the literal `{{BOX_NAME}}` and report the gap to Trevor's chat `5252140759`.
- Never put real secrets (API keys, tokens, passwords) in any field. Reference the env var name instead.

**When the fix works**, POST the resolution signal and STOP escalating:

```
_RR_BOX="${FLEET_STANDING_BOX_SLUG:-{{BOX_NAME}}}"
cat > /tmp/rr-resolved.json <<JSON
{
  "action":     "escalate",
  "clientName": "{{CLIENT}}",
  "agentName":  "{{AGENT}}",
  "boxName":    "$_RR_BOX",
  "problem":    "RESOLVED: <one-line what fixed it>"
}
JSON
curl -s -X POST "$RESCUE_RANGERS_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  "${_RR_SECRET_ARGS[@]}" \
  --data-binary @/tmp/rr-resolved.json
rm -f /tmp/rr-resolved.json
```

**You MUST tell the end user the outcome** in clear language. State which of these three it was:
- **(a) We solved it** -- describe what was fixed and confirm normal operation is restored.
- **(b) Here is what you should do** -- give the owner/user the actionable next step they must take.
- **(c) Here is the answer** -- relay the Rescue Rangers response verbatim if it is informational.
Never leave the end user in the dark about what happened or what comes next. This is non-negotiable.

**Hard cap: 25 exchanges per client per day.** Do not loop endlessly; if unresolved after several exchanges, ping Trevor's chat `5252140759` directly.

> DEPRECATED -- do NOT use the old bot-to-bot method `openclaw message send --channel telegram -t "$RESCUE_RANGERS_HELP_CHAT_ID"`. Bots cannot read other bots, so that escalation never reached the rescue agent. The webhook above is the replacement.
<!-- END RESCUE_ESCALATION_BOXNAME_V2 -->

## What Rescue Rangers IS + your own wiring (READ BEFORE ANSWERING)

Rescue Rangers is this fleet's escalation team. If a client asks what it is or whether you have a rescue team, answer YES and point at this section. Never say you have no such tool or team.

Your box carries the wiring in three places — read ALL THREE before you ever tell a client you lack a credential or a URL:

1. Runtime env: `RESCUE_RANGERS_WEBHOOK_URL`, `RESCUE_RANGERS_WEBHOOK_SECRET`, `RESCUE_RANGERS_HELP_CHAT_ID` (deprecated — may legitimately be absent), `OPENCLAW_DASHBOARD_URL` (only on boxes with an interview dashboard). The URL may live ONLY in the secrets file, not in the runtime env — always check both.
2. Secrets file: `$HOME/.openclaw/secrets/.env` (Mac), `/home/node/.openclaw/secrets/.env` (container; Contabo host path `/opt/clients/<client>/data/...`), `/data/.openclaw/secrets/.env` (VPS). Source it, then check the same names. The `X-Rescue-Secret` and Cloudflare Access service tokens live here.
3. This AGENTS.md and the skills tree (`65-rescue-receiver`).

HARD RULE — never tell a client "I don't have your credentials" before reading all three sources and naming what you checked. Absence must be proven the same way presence is.

SELF-VERIFY before asking the client for anything (headless):

```bash
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' "$RESCUE_RANGERS_WEBHOOK_URL" || true   # 404 or 302 is NORMAL (webhook is POST-only)
_RR_SECRET_ARGS=()
[ -n "${RESCUE_RANGERS_WEBHOOK_SECRET:-}" ] && _RR_SECRET_ARGS=(-H "X-Rescue-Secret: ${RESCUE_RANGERS_WEBHOOK_SECRET}")
curl -s -X POST "$RESCUE_RANGERS_WEBHOOK_URL" -H "Content-Type: application/json" \
  "${_RR_SECRET_ARGS[@]}" \
  -d '{"action":"escalate","clientName":"__AUTHTEST__","problem":"channel self-check"}'; echo
```

`{"accepted":true,"ticketId":null,"status":"test_suppressed"}` = the channel works end-to-end with zero ticket residue. 403 = wrong secret. 200 `missing_message` = OLD relay (wrong URL).
