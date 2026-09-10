# PRES-055 leg A — Mac-native + standalone-no-gateway (W6 WF23, Opus)

Scope: NEW files ONLY under `accept-a/` in worktree `run/worktrees/wf23-onb-accept`,
branch `pres055-wf23-a` from `db4c0fdff`. READ-ONLY everywhere else in the repo.
NEVER push/tag/release/merge/stash. No live client data, no real paid calls
(no KIE key, no GHL/CC credentials, no model keys in env; env -i hermetic).

## What leg A runs (deployed artifact, hermetic scratch)

| Module | Leg | Nature |
|---|---|---|
| `readiness_a.py` | Adapter readiness | Real `claude --version` / `claude-nine --version` invocations; installed-wheel skill surface (skill51 SKILL.md + bin/presentation + claude-code/nine adapter docs); OpenClaw gateway dead-port probe with live-process negative control (current PID alive, closed port refused). |
| `intake_resume_a.py` | Hermetic install + fresh intake + pause/resume | venv in /tmp scratch, `pip install` exact wheel, `presentation init/doctor/start/status/verify/export` via console script; engine `--resume --diagnose-only` (real resume entry, no budget burn); engine `--run --dry-run` stage enumeration; watchdog/supervise/sweep verbs real; standalone import checks (engine manifest v68 pin, ghl 6/6, skill51 provers). |
| `render_qc_a.py` | Real local render + independent visual QC | Real PNGs via Pillow + real .pptx via python-pptx from fixture copy (LOCAL-SYNTHETIC-RENDER, never claimed canonical KIE); two independent QC passes (PNG magic+payload; pptx zip slide count); real `bundle_gate.py` + dispatcher `--once` from installed package, fail-closed receipts. |
| `delivery_a.py` | Delivery + IDs | Real `export` provenance; stage events from state.json; catalog routed model IDs (resolved-not-called); GHL/CC connected NOT-VERIFIED (no creds, no network). |
| `run_leg_a.py` | Orchestrator | Runs all legs, writes receipts to packet `run/evidence/PRES-055/a-mac/` + `run/candidates/PRES-055-a/candidate.json` (after worktree commit SHA known). |

## Labels

- DEPLOYED-RUN-PASS: real command green against installed exact artifact in hermetic env.
- LOCAL-SYNTHETIC-RENDER: real bytes (Pillow/python-pptx), fixture copy only; canonical KIE render NOT-RUN (no key, zero paid).
- NOT-VERIFIED: attempted honestly, blocker recorded (no creds / human gate / paid model), zero fabrication.
- No receipt here self-approves anything. QC-PRES-055 stays OPEN pending INDEPENDENT QC.
