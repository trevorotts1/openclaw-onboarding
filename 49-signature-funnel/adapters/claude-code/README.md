# Skill 49 (Signature Funnel) - Claude Code experience

How the client is asked, and told, when Skill 49 (Signature Funnel) runs in Claude Code. Code: `<REPO_ROOT>/shared-utils/signature_launch/experience/`.

## Asking (structured question tool)

1. Detect: `python3 <REPO_ROOT>/shared-utils/signature_launch/experience/harness_profile.py --harness claude-code` (an explicit flag always wins; with no flag it reads the answers file, then the environment, then falls back to plain chat).
2. Render the questions still unanswered: `python3 <REPO_ROOT>/shared-utils/signature_launch/experience/render_question.py --questions-file <bank.json> --answers-file <answers.json> --harness claude-code`. It prints structured question tool calls: 2 to 4 options each, a short header, related questions batched together (at most 4 per call), free text through "Other".
3. Make the call exactly as printed. Do not add, reorder or reword options. The last option is always "I'm not sure, help me".
4. Record each answer into the answers file with the intake engine, in launch mode and legacy mode.

## When the client does not know

They pick "I'm not sure, help me". Run the engine's help path: colours from their logo or website, three suggested palettes with plain-English reasons, then a safe default flagged "to confirm". The build is never blocked silently, and the default is reported at delivery.

## Progress and delivery

- While pages build, show the status table: `python3 <REPO_ROOT>/shared-utils/signature_launch/experience/progress_report.py --rows-file <rows.json> --harness claude-code`.
- At the end, show `python3 <REPO_ROOT>/shared-utils/signature_launch/experience/delivery_report.py --rows-file <rows.json> --answers-file <answers.json> --ledger-file <ledger.json> --harness claude-code`: every page with desktop and mobile wireframes and mockups, a "To confirm" list, and the image spend.

## Speed

Pages are built in parallel lanes by the launch dispatcher (a worker pool in Skill 49), not by this harness, so speed is the same here as everywhere. Do not spawn your own page agents.

## Where the answers live

One answers file per run (the shared client-intake answers file, written by `shared-utils/client_intake/`). Every question, in every harness, comes from the same question bank and lands in the same answers file, so a run started in one harness can be resumed in another. Anything we had to default or suggest is listed under `to_confirm` and is reported at delivery with a one-line way to change it.

## Never

- Never send client messages or use Telegram, GHL or any other channel except this session's own reply.
- Never borrow credentials: no Telegram token, no operator key, no other client's key.
- Never guess a skills path. Use the install root you verified, or ask.
- Never default price, offer name and claims, representation, community or bonus truth, entitlement, or paid-render approval. These pause the build until the client answers.

The adapter changes HOW the client is asked and told, never WHAT the gates enforce.
