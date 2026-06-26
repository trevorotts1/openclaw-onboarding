# Skill 48 — How to drive a run

The Facebook & Instagram Ad-Run Producer drives the foreman; it does no craft itself.

## The dependency-map foreman

```
python3 scripts/ad_director.py --run-dir <RUN> --plan      # show readiness
python3 scripts/ad_director.py --run-dir <RUN> --phase S0-INTAKE
python3 scripts/ad_director.py --run-dir <RUN> --phase S1-OVERLAYS
# PICK-10 (human pause #1) -> capture with ad_selection.py, then:
python3 scripts/ad_director.py --run-dir <RUN> --phase PICK-10
# S2 / S3 / S4 now run AT THE SAME TIME (independent):
python3 scripts/ad_director.py --run-dir <RUN> --phase S2-PRIMARY-TEXT
python3 scripts/ad_director.py --run-dir <RUN> --phase S3-HEADLINES
python3 scripts/ad_director.py --run-dir <RUN> --phase S4-IMAGE-PROMPTS
python3 scripts/ad_director.py --run-dir <RUN> --phase S5-IMAGE-GEN   # waits on S4
python3 scripts/ad_director.py --run-dir <RUN> --phase S6-TARGETING   # waits on S2+S3
python3 scripts/ad_director.py --run-dir <RUN> --phase S7-DELIVER     # waits on S5+S6
# PUBLISH (human pause #2) -> after the owner approves:
python3 scripts/ad_director.py --run-dir <RUN> --phase PUBLISH
```

## Exit codes
- `0` — the phase attested (dependencies met + receipt validated); OR a
  `--recover`/`--resume` actionable step (`DONE`/`PRODUCE`/`REDO` — read the JSON `action`).
- `2` — a phase started before a `depends_on[]` phase was done (AF-FBAD-DEP-SKIPPED), a
  usage error, a refused `--adhoc`, or a refused paid run under a tmp dir. Fix the order / artifact.
- `3` — a receipt failed its content check (e.g. AF-FBAD-IMAGE-TASKID, AF-FBAD-COPY-QC).
  Send the stage back to its producing role.
- `4` — the Kie balance is below the estimated floor (AF-FBAD-KIE-BALANCE) on the legacy
  `--phase` path. Top up and re-run the SAME run-id.
- `5` — PARKED (`--recover`/`--resume`): a durable save-point was written and the job
  paused at a non-recoverable / human-gated / budget-exhausted condition. Clear the
  blocker, then `--resume`.

## Self-correct + park-and-resume (the foreman that does NOT die)
Instead of driving each `--phase` by hand, drive the recovering foreman turn by turn:
```
python3 scripts/ad_director.py --run-dir <RUN> --recover   # one verdict per call
python3 scripts/ad_director.py --run-dir <RUN> --resume    # after a park clears
python3 scripts/ad_director.py --run-dir <RUN> --status    # attested / spend / park / next
```
Each `--recover` returns ONE JSON verdict; do exactly what `action` says, then call again:
- `PRODUCE` — make this phase's `produces_artifact`, then `--recover` again.
- `REDO` — a recoverable (`recovery:auto`) gate failed: redo **only** the failing artifact
  using `feedback`, up to `max` attempts, then `--recover` again (the re-call re-runs the
  REAL check — never a fabricated pass).
- `ADVANCE` — (internal) a phase just attested; the loop continues automatically.
- `PARK` / `AWAIT_HUMAN` (exit 5) — a `recovery:park` gate (over the money ceiling /
  out of balance, a fabrication/tampering check, a missing human approval), an exhausted
  fix budget, or a no-progress loop wrote a durable checkpoint (`working/checkpoints/PARKED.json`
  + a box pointer under `OC_ROOT/workspace/.park/fbad/`). Nothing is discarded.
- `DONE` — every phase attested.

When a park clears (money added / human replies / the bad artifact corrected), `--resume`
re-runs the parked checkpoint's real checker(s) and, only if they pass, re-enters at the
exact last-incomplete phase — skipping every attested phase and every paid ledger key, so
it **never re-charges and never re-uploads**. A still-failing blocker stays parked.

Budgets are configurable: `FBAD_MAX_FIX_ATTEMPTS` (per-gate auto budget; default 3, QC
gates 2-3), `FBAD_MAX_TOTAL_FIX_ATTEMPTS` (global, default 30), `FBAD_MAX_NO_PROGRESS`
(identical-resubmission cap, default 2). A PAID run must live under the durable runs root
`OC_ROOT/workspace/fbad-runs/<run_id>/`, not a reboot-wiped tmp dir (refused unless
`--allow-ephemeral`). Operators inspect/clear parks with `scripts/unpark-ad-run.sh`.

## The two human gates (non-skippable)
`PICK-10` and `PUBLISH` can never be bypassed — no owner skip record and no `--adhoc`
relaxes them. The foreman validates their receipts even under `--adhoc`.

## Money
The producer estimates cost up front, gates it against the per-job ceiling BEFORE any
spend, watches the cheap LOCAL running tally during S5 (stops before crossing), and runs
the single balance preflight once at start. The run-id namespaces every receipt so a
retry never re-spends or double-uploads.

## Independent QC
Each scored gate (Words / Image Prompts / Images / Targeting / Package) needs an 8.5+
scorecard (no category < 7) from a DIFFERENT worker than the maker. Below the line, the
maker redoes ONLY the failing piece; escalate to the owner only after the redo budget.
