# Signature Presentation — Codex adapter

Build a signature-presentation deck by running the packaged entry, from any
working directory:

    /path/to/51-signature-presentation/bin/presentation \
        --run-dir <RUN_DIR> --slides slides.json --out out.pptx

`bin/presentation` is a bash wrapper: it resolves its own skill dir, sources
the platform secrets env with `set -a`, REFUSES if the Presentations
department is not materialized, and `exec`s `presentation-canonical-entry.sh`
(the department's single sanctioned door) with your arguments and its exit
code. Do NOT run `python3 working/*.py` — that is the ungoverned path and
every gate refuses it.

Notify (supervised relay, PRES-052): when `openclaw` is absent from PATH and
`PRESENTATION_NOTIFY_CMD` is unset, the wrapper exports the file-queue
transport, which appends typed notify rows (company/presentation/run/task/
stage/event id, revision, delivery state, lease, retry deadline,
acknowledgement) to `<run-dir>/working/outbox.jsonl`. Supervise from job
start, not at finish: poll `python3 presentation_job.py --relay-status
--run-dir <RUN_DIR>` while the engine runs for stage completion,
waiting-on-configuration, stalled/retrying, and active progress before final
output. QUEUED IS NOT DELIVERED — only a recorded acknowledgement (local vs
Command Center tracked separately) certifies the operator was notified.
Transport readiness is probed, never assumed from an installed executable.
Use the requested local host channel by default; never borrow Telegram
credentials and never send to another client. Setting
`PRESENTATION_NOTIFY_CMD` overrides this.

The methodology gates (8-Questions intake in one atomic block, the sacred
4-phase / >=100-slide structure ledger, the Phase-3 no-pitch prover) remain
fully enforced by the door — the adapter only changes how the build is
invoked. Full methodology: `SKILL.md` at the skill root.
