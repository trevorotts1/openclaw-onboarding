# Skill 83 (Black Friday Launcher) - Claude Code experience

How the client is asked, and told, when Skill 83 (Black Friday Launcher) runs in Claude Code. Code: `<REPO_ROOT>/shared-utils/signature_launch/experience/`.

## Asking (structured question tool)

1. Detect: `python3 <REPO_ROOT>/shared-utils/signature_launch/experience/harness_profile.py --harness claude-code` (an explicit flag always wins; with no flag it reads the answers file, then the environment, then falls back to plain chat).
2. Ask ONE question at a time. Render the next applicable question from the shared guided bank (`<REPO_ROOT>/shared-utils/client_intake/question-bank.json` in Black Friday mode — never a raw bank): `python3 <REPO_ROOT>/shared-utils/signature_launch/experience/render_question.py --questions-file <REPO_ROOT>/shared-utils/client_intake/question-bank.json --answers-file <answers.json> --harness claude-code`. It prints exactly one structured question tool call: 2 to 4 options with each option's own explanation (never flattened), a short header, free text through "Other". Never batch questions. The seasonal questions (promotion dates, the offer and any discount or bonus, real limitations, existing vs new buyers, delivery and follow-up) and the three picture questions all come from this same interview, one at a time — the picture questions are not the whole interview. Length estimates and progress cover the applicable questions only and are computed at runtime.
3. Make the call exactly as printed. Do not add, reorder or reword options. The last option is always "I'm not sure, help me".
4. Record each answer into the answers file with the intake engine, in its intake. The client's assistance preference is asked first and may change at any time: A "set it up for me to review" (use what is known, ask only what is missing, show the proposal for review), B "help me choose" (every decision explained and walked through), C "I know what I want" (jump to execution, flag anything important still missing). Any default or recommendation is a proposal flagged "to confirm" — never a silent decision, never an approval for spending. Copy never invents urgency or scarcity: real dates and real limits only, from the client's own answers.

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
