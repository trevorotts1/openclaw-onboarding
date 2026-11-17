# cc_owner_questions

The agent's side of Command Center owner questions. The Command Center stores each question for the
client, writes a plain-English recommendation, and pushes ONE message to the client's main chat ending
with `(ref Q-ABC123)`. This helper lets the agent recognise the client's reply and post it back. It never
sends a chat message itself, so the client is never messaged twice.

Installed path: `~/.openclaw/skills/shared-utils/cc_owner_questions/cc_owner_questions.py`
(VPS: `/data/.openclaw/skills/shared-utils/...`). Python 3 standard library only.

```bash
python3 cc_owner_questions.py open [--json]
python3 cc_owner_questions.py match --text "<client message>" [--json]
python3 cc_owner_questions.py answer --ref Q-ABC123 --text "<client reply, verbatim>" \
  --source-message-ref "<inbound message id>" [--channel telegram|webchat]
```

`match` prints the `Q-XXXXXX` code when the message contains one; otherwise, when exactly one question is
open, prints `single-open <ref> <question>` so the agent can confirm; otherwise `none` or `ambiguous N open`
(exit 1).

Token and address use the same order as `scripts/mc-route.sh`: `MC_API_TOKEN` from the dotenv stores, then
the live environment (never printed). Base URL: `CC_OWNER_QUESTIONS_URL`, else `MC_ROUTE_INGEST_URL` minus
`/api/tasks/ingest`, else `MISSION_CONTROL_URL`, else `http://127.0.0.1:4000`.

| Exit | Meaning |
|---|---|
| 0 | success |
| 1 | `match`: nothing or more than one open question |
| 2 | bad usage |
| 3 | Command Center unreachable or no token |
| 4 | Command Center needs updating (route missing) |
| 5 | unknown question |
| 6 | already answered |
| 7 | chat message not verified |
| 8 | other Command Center error |

See `docs/CC-OWNER-QUESTIONS.md`.
