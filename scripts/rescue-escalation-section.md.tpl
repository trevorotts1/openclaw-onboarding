<!-- RESCUE_ESCALATION_BOXNAME_V2 -->
## Escalate to Rescue Rangers (when you are stuck)

<!-- RESCUE_ESCALATION_PROTOCOL_REVISION: 3 -->

When you hit a problem you cannot solve on your own, escalate to Rescue Rangers by POSTing to the n8n webhook. Your gateway CAN reach this public URL outbound.

**Protocol revision:** 3. Revision 3 requires a resolution to name the exact
incident it closes (`incidentId`), carry a unique `operationId` and the
`attemptId` that produced the fix, and carry a `resultDigest` over the canonical
structured outcome. A revision-2 block could resolve without any of that, so a
revision-2 resolution that arrives without an incident id is handled as a LEGACY
resolution: it is never guessed at, the incident stays open, and the operator is
asked to correlate it. Both revisions are readable by the intake; only revision
3 can close an incident by name.

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
# Capture the body AND show it: `ticketId` in it is the incident id Step 1 of
# the resolution block records. Printed exactly as received -- never reformatted.
#
# The response is ALSO written to disk. Do not skip that: these fenced blocks
# are routinely run in SEPARATE shells, so a shell variable would be gone by the
# time Step 1 ran and the admission ticket id would be lost exactly when it is
# needed. The file is the hand-off, and it holds no secret -- an admission
# response carries a status and a ticket id.
_RR_STATE="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}"
[ -d /data/.openclaw ] && _RR_STATE="/data/.openclaw"
[ -d /home/node/.openclaw ] && _RR_STATE="/home/node/.openclaw"
_RR_ADMIT="$_RR_STATE/state/rr-escalation/last-admission.json"
mkdir -p "$(dirname "$_RR_ADMIT")" 2>/dev/null && chmod 700 "$(dirname "$_RR_ADMIT")" 2>/dev/null
_RR_RESP="$(curl -s -X POST "$RESCUE_RANGERS_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  "${_RR_SECRET_ARGS[@]}" \
  --data-binary @/tmp/rr-escalation.json)"
printf '%s\n' "$_RR_RESP"
printf '%s' "$_RR_RESP" > "$_RR_ADMIT" 2>/dev/null && chmod 600 "$_RR_ADMIT" 2>/dev/null
rm -f /tmp/rr-escalation.json
```

`status:"accepted"` with a non-null `ticketId` means the incident exists, and
that id is what a later resolution must name. `accepted:false` (or
`ticketId:null`) means NOTHING was admitted -- there is no incident to resolve
against, so escalate again rather than proceeding to the resolution block.

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

**When the fix works**, POST the resolution signal and STOP escalating.

**A resolution MUST NAME THE EXACT INCIDENT IT CLOSES.** It carries the
`incidentId` the intake returned when you escalated -- read back from this box's
own task journal, never reconstructed, never guessed. A resolution that does not
name its incident is not applied: the incident stays open and the operator is
asked to correlate it. That is deliberate. Closing the wrong incident is worse
than closing none.

**Step 1 -- record the admission ticket ID at escalation time.** The escalation
curl printed a JSON body; `ticketId` in it is the incident's canonical id. Append
it to the task journal right after the POST:

```
_RR_STATE="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}"
[ -d /data/.openclaw ] && _RR_STATE="/data/.openclaw"
[ -d /home/node/.openclaw ] && _RR_STATE="/home/node/.openclaw"
_RR_JOURNAL="$_RR_STATE/state/rr-escalation/journal.jsonl"
# Derived here as well as above: this block is routinely run in a FRESH shell,
# where the escalation block's own _RR_BOX is long gone. Reading it unguarded
# would journal the ticket against an EMPTY slug, and the resolution block --
# which matches on the box slug -- would then never find its own record.
_RR_BOX="${FLEET_STANDING_BOX_SLUG:-{{BOX_NAME}}}"
mkdir -p "$(dirname "$_RR_JOURNAL")" 2>/dev/null && chmod 700 "$(dirname "$_RR_JOURNAL")" 2>/dev/null
RR_ADMIT="$_RR_STATE/state/rr-escalation/last-admission.json" RR_BOX="$_RR_BOX" RR_JOURNAL="$_RR_JOURNAL" RR_ATTEMPT="${ATTEMPT_ID:-}" python3 - <<'PYJ'
import json, os, time
p_in = os.environ.get("RR_ADMIT", "")
try:
    # The ADMISSION FILE is the source of truth, not a shell variable that does
    # not survive into this shell.
    with open(p_in, encoding="utf-8") as fh:
        d = json.loads(fh.read() or "{}")
except Exception:
    d = {}
tid = str((d.get("ticketId") or "")).strip()
if not tid:
    # No ticket id means nothing was admitted. NEVER invent one: a fabricated
    # id would later close an incident that belongs to someone else's work.
    print("RR-JOURNAL: NO ticketId in the admission response (status=%s) -- nothing journalled. Escalate again, or report to Trevor's chat 5252140759." % str(d.get("status") or "unknown"))
else:
    p = os.environ["RR_JOURNAL"]
    rec = {"ticket_id": tid, "box_slug": os.environ.get("RR_BOX", ""),
           "attempt_id": os.environ.get("RR_ATTEMPT", ""), "status": str(d.get("status") or ""),
           "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    os.chmod(p, 0o600)
    print("RR-JOURNAL: admission ticket %s recorded for %s" % (tid, os.environ.get("RR_BOX", "")))
PYJ
```

If that prints `NO ticketId`, you have nothing to resolve against later -- say so
to the end user instead of posting a resolution.

**Step 2 -- post the resolution, with the incident id required.** Replace
`<one-line what fixed it>` with the actual outcome. The block reads the journal,
and REFUSES to post when the box has no recorded incident id:

```
_RR_STATE="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}"
[ -d /data/.openclaw ] && _RR_STATE="/data/.openclaw"
[ -d /home/node/.openclaw ] && _RR_STATE="/home/node/.openclaw"
_RR_BOX="${FLEET_STANDING_BOX_SLUG:-{{BOX_NAME}}}"
_RR_JOURNAL="$_RR_STATE/state/rr-escalation/journal.jsonl"
RR_BOX="$_RR_BOX" RR_JOURNAL="$_RR_JOURNAL" \
RR_FIXED="<one-line what fixed it>" \
RR_CLIENT="{{CLIENT}}" RR_AGENT="{{AGENT}}" \
  python3 - <<'PYR' > /tmp/rr-resolved-body.json
import hashlib, json, os, sys, time
box = os.environ.get("RR_BOX", "")
journal = os.environ.get("RR_JOURNAL", "")
if not journal or not os.path.isfile(journal):
    sys.stderr.write("RR-RESOLVE: REFUSED -- no task journal at %s, so the incident this box escalated cannot be named. Nothing posted; the incident stays open. Report to Trevor's chat 5252140759.\n" % (journal or "(unset)"))
    sys.exit(2)
newest = {}
with open(journal, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if str(rec.get("box_slug") or "") != box:
            continue
        if str(rec.get("ticket_id") or "").strip():
            newest = rec
incident = str(newest.get("ticket_id") or "").strip()
if not incident:
    sys.stderr.write("RR-RESOLVE: REFUSED -- the task journal holds no admission ticket id for this box. Never guess which incident to close; the incident stays open and is offered to the operator for correlation. Report to Trevor's chat 5252140759.\n")
    sys.exit(2)
attempt = str(newest.get("attempt_id") or "").strip() or "0"
fixed = os.environ.get("RR_FIXED", "")
stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
# outcome digest: sha256 over the CANONICAL structured outcome -- the redacted
# reply, the incident it names, and the attempt that produced it. A digest over
# prose is not a digest, so the canonical form is hashed, not the raw sentence.
outcome = {"incident_id": incident, "attempt_id": attempt, "outcome_type": "target_resolved",
           "reply": {"text": fixed[:500], "reply_chars": len(fixed)}}
digest = hashlib.sha256(json.dumps(outcome, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
# operation_id is DETERMINISTIC on (box, incident, attempt): a replayed
# resolution posts the SAME id, and the server records an idempotent receipt
# instead of a second close. A new attempt gets a new id.
operation = "op_" + hashlib.sha256(("rr-resolve|%s|%s|%s" % (box, incident, attempt)).encode("utf-8")).hexdigest()
print(json.dumps({
    "action": "escalate",
    "clientName": os.environ.get("RR_CLIENT", ""),
    "agentName": os.environ.get("RR_AGENT", ""),
    "boxName": box,
    "incidentId": incident,
    "operationId": operation,
    "attemptId": attempt,
    "resultDigest": digest,
    "runtimeId": box,
    "result": outcome,
    "problem": "RESOLVED: " + fixed
}))
sys.stderr.write("RR-RESOLVE: posting resolution for incident %s (operation_id=%s, digest=%s)\n" % (incident, operation, digest[:16]))
PYR
# A REFUSAL MUST BE LOUD. The python block exits 2 without writing a body when
# the incident cannot be named, and an empty file is the tell -- so say so and
# return 2 rather than falling through to a silent success. A resolution that
# quietly did nothing is indistinguishable from one that worked, and the ticket
# would sit open with nobody told.
if [ -s /tmp/rr-resolved-body.json ]; then
  curl -s -X POST "$RESCUE_RANGERS_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    "${_RR_SECRET_ARGS[@]}" \
    --data-binary @/tmp/rr-resolved-body.json
  echo
  rm -f /tmp/rr-resolved-body.json
else
  echo "RR-RESOLVE: NOTHING POSTED -- the resolution was refused (see the reason above). The incident is still OPEN. Do not report this as resolved to the end user." >&2
  rm -f /tmp/rr-resolved-body.json
  return 2 2>/dev/null || exit 2
fi
```

`runtimeId` is this box's canonical slug. Say precisely what that proves and
what it does not: the intake authenticates the REQUEST (the `X-Rescue-Secret`
header, over a Cloudflare Access service-token channel) and then checks that the
slug it was given is an ENROLLED box. So `runtimeId` is a claim about which box
is speaking, made over an authenticated channel, against an enrolled roster --
it is not yet a per-box cryptographic identity. Per-enrollment caller binding is
a separate fix; do not describe this box as cryptographically identified until
that lands. Never put a hostname, container id, or blank in `runtimeId` for the
same reason `boxName` forbids it.

Read the response. `status:"resolution_recorded"` means the named incident was
closed. `status:"correlation_required"` means the resolution could not be tied
to one incident and NOTHING was closed -- relay that to the operator; do not
re-post it and do not escalate the same problem again as if it were new.

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
