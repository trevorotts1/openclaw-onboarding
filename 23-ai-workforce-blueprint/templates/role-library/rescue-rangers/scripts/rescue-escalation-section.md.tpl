<!-- RESCUE_ESCALATION_BOXNAME_V3 -->
<!-- rescue-identity (read by the fleet roll; do not edit): {"boxName": "{{BOX_NAME}}", "clientName": "{{CLIENT}}", "agentName": "{{AGENT}}", "boxType": "{{BOX_TYPE}}", "returnTo": "{{RETURN_TO}}"} -->
## Escalate to Rescue Rangers (when you are stuck)

Rescue Rangers is the support team for this computer. When you cannot fix a problem yourself, you ask them for help by running ONE command. Never build the request by hand, and never use Telegram or a personal chat to reach them.

**Ask for help when any one of these is true:**
- You tried to fix the same problem three times and it is still broken.
- `openclaw doctor --fix` ran and the error is still there.
- You cannot find the error in the OpenClaw documentation.
- The fix needs something you are not allowed to do yourself: changing a password or key, a domain or Cloudflare setting, or anything on another computer.

Do not ask for help with ordinary work you know how to do.

**Step 1. Write two short text files** in any folder you can write to:
- `problem.txt`: one paragraph. What is broken, what the owner sees, and the exact error text. Never paste a password, key or token. Name the setting instead.
- `tried.txt`: a numbered list of everything you already tried, so nobody repeats it.

**Step 2. Run this command exactly.** Change only the owner's name. If you are a department assistant and not the main assistant, also change the value after `--agent` to your own agent name.

```
RR_ROOT=/data/.openclaw; [ -d "$RR_ROOT" ] || RR_ROOT="$HOME/.openclaw"
python3 "$RR_ROOT/skills/65-rescue-receiver/rr_escalate.py" send \
  --person "<the real name of the owner you work for>" \
  --client "{{CLIENT}}" --agent "{{AGENT}}" --box-type "{{BOX_TYPE}}" \
  --problem-file problem.txt --tried-file tried.txt
```

If the problem is that something keeps looping, is stuck, or gives no reply, add `--loop` at the end of the command. It puts the `LOOP:` prefix on the problem for you.

**Step 3. Read the one line the command prints.** It is JSON. Read `state`, then tell your owner the text in `say_to_owner`, word for word.

| `state` | What it means | What you do |
|---|---|---|
| `accepted` | The support team has the case. `ticket_id` is the reference. | Say `say_to_owner`. Write the `ticket_id` in your task notes. Do not send the same problem again. |
| `already_being_worked` | This problem already has a case. | Say `say_to_owner`. Do not send it again. |
| `queued_will_retry` | The team could not be reached. The request is saved on this computer and will be sent automatically. | Say `say_to_owner`. Do not run the command again for this problem. |
| `needs_owner_action` | The team answered with a message for the owner. | Say `say_to_owner`. Stop sending this problem. |
| `not_an_incident` | The team decided this does not need a repair. | Say `say_to_owner`. Do not send it again. |
| `setup_problem` | This computer is not connected to the support team correctly. | Say `say_to_owner`. Do not retry. |
| `invalid_request` | One of your values was empty. | Fix the value named in `detail` and run the command once more. |

Never tell your owner that help is coming unless `state` is `accepted` or `already_being_worked`.

**What happens next.** The answer comes back to this computer by itself. Your owner gets a message in their usual chat with one of four results: the problem is fixed and checked; there is one thing only they can do, with the steps; here is the answer; or a person on the team now has it. You do not need to check for it.

**If your owner asks about a case**, run this and tell them what it says in plain words:

```
RR_ROOT=/data/.openclaw; [ -d "$RR_ROOT" ] || RR_ROOT="$HOME/.openclaw"
python3 "$RR_ROOT/skills/65-rescue-receiver/rr_escalate.py" status --ticket "<ticket_id>"
```

**When the fix works**, close the case and stop:

```
RR_ROOT=/data/.openclaw; [ -d "$RR_ROOT" ] || RR_ROOT="$HOME/.openclaw"
python3 "$RR_ROOT/skills/65-rescue-receiver/rr_escalate.py" resolve --ticket "<ticket_id>" --fixed "<one line: what fixed it>"
```

If you did not write down the `ticket_id`, say so. Never make one up and never use a different case's reference.

**Daily limit.** Rescue Rangers takes up to 25 cases from one computer in a day. After that a case is still recorded and a person on the team takes it over. The command tells you so in `say_to_owner`. Say it and stop sending.

**Never** put a real password, key or token in `problem.txt`, `tried.txt` or the command.

> RETIRED: do not use `openclaw message send --channel telegram -t "$RESCUE_RANGERS_HELP_CHAT_ID"` to reach Rescue Rangers, and do not build a `curl` request by hand. Both are replaced by the command above.
<!-- END RESCUE_ESCALATION_BOXNAME_V3 -->

## What Rescue Rangers IS + your own wiring (READ BEFORE ANSWERING)

Rescue Rangers is this fleet's escalation team. If a client asks what it is or whether you have a rescue team, answer YES and point at this section. Never say you have no such tool or team.

Your box carries the wiring in three places — read ALL THREE before you ever tell a client you lack a credential or a URL:

1. Runtime env: `RESCUE_RANGERS_WEBHOOK_URL`, `RESCUE_RANGERS_WEBHOOK_SECRET`, `RESCUE_RANGERS_HELP_CHAT_ID` (deprecated — may legitimately be absent), `OPENCLAW_DASHBOARD_URL` (only on boxes with an interview dashboard). The URL may live ONLY in the secrets file, not in the runtime env — always check both.
2. Secrets file: `$HOME/.openclaw/secrets/.env` (Mac), `/home/node/.openclaw/secrets/.env` (container; Contabo host path `/opt/clients/<client>/data/...`), `/data/.openclaw/secrets/.env` (VPS). Source it, then check the same names. The `X-Rescue-Secret` and Cloudflare Access service tokens live here.
3. This AGENTS.md and the skills tree (`65-rescue-receiver`).

HARD RULE — never tell a client "I don't have your credentials" before reading all three sources and naming what you checked. Absence must be proven the same way presence is.

SELF-VERIFY before asking the client for anything (headless):

```bash
RR_ROOT=/data/.openclaw; [ -d "$RR_ROOT" ] || RR_ROOT="$HOME/.openclaw"
bash "$RR_ROOT/skills/65-rescue-receiver/rr-intake-auth-check.sh"; echo "exit=$?"
```

Exit 0 = the channel works end to end and no case was created. Exit 3 = this computer's secret is refused. Exit 4 = the address points at the old, retired relay. Exit 5 = no secret is set here. Exit 75 = nothing could be established (network, throttling or a server error); that is not a verdict about this computer.
