# Skill 71 (BlackCEO Signature Page) - OpenClaw experience

How the client is asked, and told, when Skill 71 (BlackCEO Signature Page) runs in OpenClaw (chat, including Telegram). Code: `<REPO_ROOT>/shared-utils/signature_launch/experience/`.

## Asking (one short chat message at a time)

1. Detect: `python3 <REPO_ROOT>/shared-utils/signature_launch/experience/harness_profile.py --harness openclaw`.
2. Render: `python3 <REPO_ROOT>/shared-utils/signature_launch/experience/render_question.py --questions-file <bank.json> --answers-file <answers.json> --harness openclaw`. It prints one short numbered message per unanswered question.
3. Say ONE message in this session's own reply. Wait for the client's reply. Do not send the next question until they answer.
4. Read the reply with `parse_reply` in `render_question.py`: a number picks that choice, any other text is their own answer, and the word "help" (or "not sure", "I don't know") starts the help path. Never treat silence or "skip" on a must-answer question as an answer.
5. Record the answer into the answers file with the intake engine, in its intake. If the session restarts, run step 2 again: answered questions are skipped, the rest are asked.

## When the client does not know

They reply "help". Run the engine's help path: colours from their logo file, or from their website by a plain web fetch of the page and its stylesheet (no browser of any kind), three suggested palettes with plain-English reasons, then a safe default flagged "to confirm". The build is never blocked silently, and the default is reported at delivery.

## Progress and delivery

- While pages build, send one short message per FINISHED page: `python3 <REPO_ROOT>/shared-utils/signature_launch/experience/progress_report.py --rows-file <rows.json> --harness openclaw --announced <keys already sent>`. Keep the printed `announced` keys so no page is announced twice. No walls of text.
- At the end, send `python3 <REPO_ROOT>/shared-utils/signature_launch/experience/delivery_report.py --rows-file <rows.json> --answers-file <answers.json> --ledger-file <ledger.json> --harness openclaw` as plain lines (no tables).

## Speed

Pages are built in parallel lanes by the launch dispatcher, not by chat. Never start a second run to go faster.

## Where the answers live

One answers file per run (the shared client-intake answers file, written by `shared-utils/client_intake/`). Every question, in every harness, comes from the same question bank and lands in the same answers file, so a run started in one harness can be resumed in another. Anything we had to default or suggest is listed under `to_confirm` and is reported at delivery with a one-line way to change it.

## Never

- Never send client messages or use Telegram, GHL or any other channel except this session's own reply.
- Never borrow credentials: no Telegram token, no operator key, no other client's key.
- Never guess a skills path. Use the install root you verified, or ask.
- Never default price, offer name and claims, representation, community or bonus truth, entitlement, or paid-render approval. These pause the build until the client answers.

The adapter changes HOW the client is asked and told, never WHAT the gates enforce.
