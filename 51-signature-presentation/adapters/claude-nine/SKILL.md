---
name: signature-presentation
description: Run the signature-presentation deck skill (Skill 51) from the claude-nine CLI in ANY cwd. Invokes bin/presentation, which runs the department's canonical door — no other path exists.
---

# Signature Presentation — claude-nine adapter

Invoke the packaged entry from any session cwd:

    ~/.claude-nine/skills/51-signature-presentation/bin/presentation \
        --run-dir <RUN_DIR> --slides slides.json --out out.pptx

(On boxes where the skill installs elsewhere, use that tree's
`bin/presentation` — the wrapper always resolves its own dir first.)

`bin/presentation` sources the platform secrets with `set -a`, refuses if the
Presentations department is not materialized, and execs
`presentation-canonical-entry.sh` — the single sanctioned door — passing your
args through and returning its exit code.

Notify: if `openclaw` is absent from PATH and `PRESENTATION_NOTIFY_CMD` is
unset, the wrapper exports the file-queue transport
(`working/outbox.jsonl`). Relay those rows yourself when the run finishes.
Set `PRESENTATION_NOTIFY_CMD` to override.

Methodology + gates: read `SKILL.md` at the skill root. The adapter changes
HOW you invoke, never WHAT the fail-closed gates enforce.
