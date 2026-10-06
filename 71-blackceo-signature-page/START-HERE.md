# START HERE - Phase 1 Runtime Evaluation

This package is already designed as the BlackCEO Signature Page production skill. Treat the bundled BlackCEO workflow and references as the methodology to preserve, not as a draft invitation to redesign it.

## Your job as a receiving agent

1. Read `SKILL.md`.
2. Read `references/authority-map.md`.
3. Verify that your runtime discovers this skill and can load its supporting references.
4. Run the deterministic smoke tests in `tests/test_scripts.py`.
5. Verify the local installation/symlink behavior appropriate to your runtime.
6. Verify that scripts can run with the runtime's available Python environment.
7. Verify PDF assembly from ordered PNGs.
8. Verify any configured external tools separately: browser, image engine, GHL, GitHub, Vercel, or other connectors.
9. Repair only runtime-compatibility defects. Do not rewrite the BlackCEO production methodology, quality thresholds, copy architecture, one-style-per-page rule, image-prompt range, or three-attempt failed-work repair policy unless Trevor explicitly authorizes a methodology change.
10. Report every intentional change and every unresolved blocker.

## Phase 1 targets

- Claude Code
- Claude-Nine
- Codex

The three targets should share one canonical core when the local environment supports safe symlinks. Do not create three competing copies of the methodology unless the runtime forces that architecture.

## Phase 2 is separate

Do not adapt this package for OpenClaw in Phase 1. OpenClaw/GitHub distribution is the next phase after local-agent evaluation and reconciliation.

## No credentials in the package

Never add Kie.ai, Agnes, GHL, GitHub, Vercel, browser-session, or other secrets to this skill archive. Connect those through the runtime's normal secure configuration.
