<!-- RESCUE_ESCALATION_BOXNAME_V4 -->
## Escalate to Rescue Rangers (when you are stuck)

Rescue Rangers is this fleet's escalation team, and this box is a member of it. If a client asks what it is, or asks you to "send this to Rescue Rangers", the answer is YES and your tool is the script below. Never say you have no such tool or team.

**When to escalate:** triple-failure on the same symptom; a schema/validation error that `openclaw doctor --fix` did not resolve; an unknown error class you cannot match in docs.openclaw.ai or the GitHub repo; anything needing a credential rotation, a Hostinger/Cloudflare/DNS change, or another box; or the client asks you to escalate. Do NOT escalate for routine ops you handle competently.

**How to escalate (the ONLY supported method):**

```bash
bash ~/.openclaw/scripts/rr-escalate.sh \
  --problem "<one paragraph, plain text: what is broken>" \
  --tried "<numbered list of every fix already attempted>"
```

On a VPS whose OpenClaw root is `/data/.openclaw`, run `bash /data/.openclaw/scripts/rr-escalate.sh` with the same arguments. Optional: `--person "<name of the owner or user affected>"` and `--return-to "<chat id the answer should go to>"`.

The script fills in everything else itself: the box name (from `FLEET_STANDING_BOX_SLUG`; for this box `{{BOX_NAME}}`), client, agent, box type and OpenClaw version, and it sends the webhook secret. On success it prints `ticket=<id>` and `incident_id=<id>`. Journal the `incident_id` against the incident; your resolution needs it.

**Rules (non-negotiable):**
1. The escalation was sent ONLY if the script exited 0 AND printed a ticket number. Only then may you tell the client it was sent, and you give them the ticket number.
2. If the script exits non-zero, NOTHING was sent. Tell the client plainly that the escalation failed and quote the `rr-escalate:` reason line it printed. Never say "sent" without a ticket number.
3. Never email Rescue Rangers. Email creates no ticket and nobody triages it.
4. Never post in the Rescue Rangers Telegram group or message its bot. Bots cannot read other bots, so nothing arrives.
5. Skill `65-rescue-receiver` only RECEIVES answers. It cannot send an escalation.
6. Never put secrets (API keys, tokens, passwords) in any field. Name the env var instead.

**Loop / stuck / no-reply symptoms get a `LOOP:` prefix.** If the problem is "it keeps looping", "it's stuck", "I got nothing back", or anything else where the client experience is repetition or silence, start `--problem` with `LOOP:` (e.g. `--problem "LOOP: agent re-ran the same tool call five times with no reply"`). This routes the ticket to the loop/stuck/no-reply triage runbook (`universal-sops/SOP-RR-LOOP-TRIAGE.md`, automated first pass `scripts/rr-triage.sh`). Do not prefix anything else with `LOOP:`; it is a routing signal, not emphasis.

**Check the channel without creating a ticket:** `bash ~/.openclaw/scripts/rr-escalate.sh --selftest` exits 0 and prints `status=test_suppressed` when the URL, the secret and the box name are all accepted. Anything else names the exact problem (a missing variable, a 403 wrong secret, a transport failure). Report that exact line; do not guess.

**When the fix works**, close the ticket and STOP escalating:

```bash
bash ~/.openclaw/scripts/rr-escalate.sh --resolve "<incident_id from the escalation>" \
  --problem "RESOLVED: <one line: what fixed it>" --attempt "<attempt id, if you have one>"
```

A resolution MUST name the incident it closes. If you did not journal the `incident_id`, say so and ask the operator; never substitute or invent a ticket id.

**You MUST tell the end user the outcome** in clear language. State which of these three it was:
- **(a) We solved it**: describe what was fixed and confirm normal operation is restored.
- **(b) Here is what you should do**: give the owner/user the actionable next step they must take.
- **(c) Here is the answer**: relay the Rescue Rangers response verbatim if it is informational.

**Hard cap: 25 exchanges per client per day.** Do not loop endlessly.

**Where the wiring lives** (the script reads all three; read them yourself before telling a client something is missing): the runtime env (`RESCUE_RANGERS_WEBHOOK_URL`, `RESCUE_RANGERS_WEBHOOK_SECRET`, `FLEET_STANDING_BOX_SLUG`), `openclaw.json` `env.vars`, and the secrets file (`$HOME/.openclaw/secrets/.env` on a Mac or container, `/data/.openclaw/secrets/.env` on a VPS). Absence must be proven the same way presence is: name the variable and the places you checked.
<!-- END RESCUE_ESCALATION_BOXNAME_V4 -->
