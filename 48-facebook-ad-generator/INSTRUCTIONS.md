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
- `0` — the phase attested (dependencies met + receipt validated).
- `2` — a phase started before a `depends_on[]` phase was done (AF-FBAD-DEP-SKIPPED), a
  usage error, or a refused `--adhoc`. Fix the order / artifact.
- `3` — a receipt failed its content check (e.g. AF-FBAD-IMAGE-TASKID, AF-FBAD-COPY-QC).
  Send the stage back to its producing role.
- `4` — the Kie balance is below the estimated floor (AF-FBAD-KIE-BALANCE). Top up and
  re-run the SAME run-id.

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
