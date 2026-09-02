---
name: signature-presentation
description: Run the signature-presentation deck skill (Skill 51) from Claude Code in ANY cwd. Invokes bin/presentation, which runs the department's canonical door — no other path exists.
---

# Signature Presentation — Claude Code adapter

Invoke the packaged entry, never a hand-rolled render:

    /Users/blackceomacmini/openclaw-onboarding/51-signature-presentation/bin/presentation \
        --run-dir <RUN_DIR> --slides slides.json --out out.pptx

`bin/presentation` resolves the skill dir from its own path (any cwd), sources
the platform secrets with `set -a`, refuses if the Presentations department is
not materialized, and execs `presentation-canonical-entry.sh` — the single
sanctioned door — with your args and its exit code.

Notify: if `openclaw` is absent from PATH and `PRESENTATION_NOTIFY_CMD` is
unset, the wrapper exports the file-queue transport
(`working/outbox.jsonl`). Relay those rows yourself when the run finishes.
Set `PRESENTATION_NOTIFY_CMD` to override.

Methodology + gates: read `SKILL.md` at the skill root. The 8-Questions
intake, the sacred-structure ledger, and the Phase-3 no-pitch prover still
gate every build — the adapter changes HOW you invoke, never WHAT is enforced.
