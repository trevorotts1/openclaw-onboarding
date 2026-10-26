# START HERE — BlackCEO Signature Page (Skill 71)

This package is the BlackCEO Signature Page production skill. Treat the bundled
BlackCEO workflow and references as the methodology to preserve, not as a draft
invitation to redesign it.

## First run: create a run, write intake, check the first stage

From this skill directory, run these commands in order. The first only makes an
empty folder; `write_intake.py` writes the run's `intake.json`; `stage_gate.py
init` prepares the run's state; the last asks the stage gate whether the first
stage may start. That is the whole entry path.

```bash
mkdir -p ~/signature-runs/demo

python3 scripts/write_intake.py ~/signature-runs/demo \
  --page-version standard --copy-version standard --page-kind sales \
  --brand-owner blackceo --image-cap 1 --test-run

python3 scripts/stage_gate.py init  ~/signature-runs/demo
python3 scripts/stage_gate.py check ~/signature-runs/demo intake
```

Expected result of the last command: exit 0 and a line beginning
`PASS: stage intake may start`. If it exits non-zero it names the missing
dependency; fix that and run it again.

Drop `--test-run` and add `--design-style A|B|C` (ask the client with
`python3 scripts/design_style.py question`) for a real production run.

From there the workflow is: read `SKILL.md`, run
`scripts/stage_gate.py check <run_dir> <stage>` before every stage and
`scripts/stage_gate.py close <run_dir> <stage>` to end it. A stage that does not
close is not done.

## Install and update

See `INSTALL.md`. Verification is `bash verify.sh` from this directory; it is
safe to run at any time, not only during install or update.

## Historical: Phase 1 runtime evaluation checklist

Everything below this line is the **historical** Phase 1 evaluation record. It
was written when this skill was first checked out on local agents (Claude Code,
Claude-Nine, Codex) before OpenClaw distribution. Keep it as evidence of how the
package was validated; it is **not** the current onboarding path and the
Phase-1 restrictions it states (including "do not adapt for OpenClaw in Phase 1")
no longer apply — OpenClaw is a supported runtime now.

### What the Phase 1 pass did

1. Read `SKILL.md`.
2. Read `references/authority-map.md`.
3. Verified that the runtime discovers this skill and can load its supporting references.
4. Ran the deterministic smoke tests in `tests/test_scripts.py`.
5. Verified the local installation/symlink behavior appropriate to that runtime.
6. Verified that scripts run with the runtime's available Python environment.
7. Verified PDF assembly from ordered PNGs.
8. Verified configured external tools separately: browser, image engine, GHL, GitHub, Vercel, or other connectors.
9. Repaired only runtime-compatibility defects. The BlackCEO production methodology, quality thresholds, copy architecture, one-style-per-page rule, image-prompt range, and three-attempt failed-work repair policy are not changed without Trevor's explicit authorization.
10. Reported every intentional change and every unresolved blocker.

### Phase 1 targets

- Claude Code
- Claude-Nine
- Codex

The three targets share one canonical core where the local environment supports
safe symlinks; the methodology is never forked into three competing copies.

### Phase 2 (completed)

OpenClaw/GitHub distribution followed the local-agent evaluation and
reconciliation. This repository tree is that distribution.

## No credentials in the package

Never add Kie.ai, Agnes, GHL, GitHub, Vercel, browser-session, or other secrets to
this skill archive. Connect those through the runtime's normal secure
configuration.
