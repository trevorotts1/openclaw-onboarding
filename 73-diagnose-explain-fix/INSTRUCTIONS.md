# Skill 73 — Runtime Instructions

Trigger: `/def <problem>`, or `/def opus|sonnet|haiku <problem>`.

Run SKILL.md's four phases in order. The short version:

1. **Diagnose** — root cause, not symptom. Trace every caller and consumer before
   concluding. State the cause in one sentence that explains every symptom, with the
   evidence. "Undetermined" beats a confident wrong cause.
2. **Explain** — fifth-grader plain language: what broke, why, what happens if nobody
   touches it. Facts (paths, commands, error text) stay verbatim.
   The canonical explainer is the `eli5` skill at `~/.claude/skills/eli5/SKILL.md`.
   **It is NOT installed in this OpenCLAW tree** (`~/.openclaw/skills`, verified
   2026-09-21) — apply its rules inline from that file instead.
3. **Model question** — ask ONCE, only if the model was not already named. Exactly one
   question: which model. Never "should I fix it?", never "which agent?".
4. **Fix** — dispatch a SUBAGENT carrying what is broken, how it will be fixed, and
   why. All three, every time. Backups before writes, additive only, no secrets
   printed, real verification output in the report.

This skill never asks for permission to fix. `/def` already said fix it.
