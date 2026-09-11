---
name: signature-presentation
description: Run the signature-presentation deck skill (Skill 51) from Claude Code in ANY cwd. Invokes bin/presentation, which runs the department's canonical door — no other path exists.
---

# Signature Presentation — Claude Code adapter

Invoke the packaged entry, never a hand-rolled render:

    <REPO_ROOT>/51-signature-presentation/bin/presentation \
        --run-dir <RUN_DIR> --slides slides.json --out out.pptx

`bin/presentation` resolves the skill dir from its own path (any cwd), sources
the platform secrets with `set -a`, refuses if the Presentations department is
not materialized, and execs `presentation-canonical-entry.sh` — the single
sanctioned door — with your args and its exit code.

Notify (supervised relay, PRES-052): if `openclaw` is absent from PATH and
`PRESENTATION_NOTIFY_CMD` is unset, the wrapper exports the file-queue
transport (`working/outbox.jsonl` — typed rows: company/presentation/run/
task/stage/event id, revision, delivery state, lease, retry deadline,
acknowledgement). Supervise from job start, not at finish: poll the event
viewer while the engine runs —

    python3 presentation_job.py --relay-status --run-dir <RUN_DIR>

— which shows stage completion, waiting-on-configuration, stalled/retrying,
and active progress before final output. QUEUED IS NOT DELIVERED: a queued
row never certifies the client was notified — only a recorded acknowledgement
(local vs Command Center tracked separately) does. Transport readiness is
probed, never assumed from an installed executable: an installed-but-unready
OpenClaw gateway reports NOT READY. Use the requested local host channel by
default; never borrow Telegram credentials and never send to another client.
Set `PRESENTATION_NOTIFY_CMD` to override.

Methodology + gates: read `SKILL.md` at the skill root. The 8-Questions
intake, the sacred-structure ledger, and the Phase-3 no-pitch prover still
gate every build — the adapter changes HOW you invoke, never WHAT is enforced.
