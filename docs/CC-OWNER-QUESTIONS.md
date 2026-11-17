# Command Center owner questions: answering from chat

The Command Center owns every question for the client. It stores the question with a plain-English
recommendation and pushes ONE message to the client's main chat:

```
<question>

My recommendation: <recommendation>

Reply YES to go with my recommendation, or tell me what you want instead. (ref Q-ABC123)
```

The client's OpenClaw agent does not send these questions. Its job is to recognise the reply and post it
back with `shared-utils/cc_owner_questions/cc_owner_questions.py` (see its README for flags and exit codes).

## Flow

1. The client replies: a quote-reply to the question, a message containing `Q-ABC123`, or a short yes or no
   right after the question.
2. The agent does not route it as new work. It runs `answer --ref Q-ABC123 --text "<exact words>"
   --chat-id <the client's chat id> --source-message-ref <the inbound message id>`. With no code in hand it runs `match` first. One open
   question and a reply that clearly answers it: confirm it, then answer. Two or more open and the reply is
   ambiguous: ask the client once which one.
3. The Command Center interprets the words (YES, ok, go ahead accept the recommendation), applies them and
   replies 200. The agent tells the client in one plain sentence what was done.

## What the Command Center returns

| Response | Helper exit | Agent says |
|---|---|---|
| 200 | 0 | what was done, in one sentence |
| 409 already answered | 6 | it was already handled |
| 404 unknown question | 5 | ask which question they mean |
| 404 with no JSON (older build) | 4 | passes to the operator that the Command Center needs updating |
| 422 message not verified | 7 | passes to the operator |
| unreachable or no token | 3 | passes to the operator |

The Command Center needs the message reference as `<channel>:<chat id>:<message id>`, for example
`telegram:<chat id>:<message id>`. The helper builds it from `--chat-id` and `--source-message-ref`. A
reference already in that three-part form is passed through unchanged. A bare message id with no `--chat-id`
is refused (exit 2) before anything is sent. When the Command Center rejects a call, the helper prints its
error code and any hint it gives.

## Rules

- Never print or log the token. Never send the question text to the client yourself.
- Never show the client an internal fault (dispatch caps, API quota or 401 errors, gateway errors) as their
  question. Those go to the operator.
- When the agent itself tells the client about anything the Command Center needs, it includes a recommendation.

The agent rules ship as the `CC_OWNER_QUESTIONS_V1` block in the repo `AGENTS.md` and are stamped into each
box's workspace `AGENTS.md` by `shared-utils/agents-doctrine-blocks.sh` (`stamp_cc_owner_questions`), called
from `scripts/apply-fleet-standards.sh`. The helper reaches the box with the rest of `shared-utils/`.
