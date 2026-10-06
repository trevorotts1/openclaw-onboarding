# Loop Protection test fixtures

Synthetic, placeholder-named fixtures for the drill battery (`verify.sh`, spec 9.4).
Every fixture is fully offline, carries NO real client identifier, and NO real secret
value. They reproduce the incident SHAPES the taxonomy (Section 2) is built from:

| Fixture | Drill | Loop class | What it proves |
|---|---|---|---|
| `restart-storm.jlist.json` | D-RESTART | LP-B1 | a Box A-class restart storm trips the process breaker in one tick; the `pm2_env`/`env` block is DROPPED (name/status/pid/restarts only) |
| `identical-signature.runs.json` | D-SIG | LP-A1 | 5 identical failure signatures = D3 "loop confirmed" P1 |
| `corrupted-offset.json` | D-OFFSET | LP-C1 | the stored offset rewinds to oldest-pending-minus-one |
| `orphan-port.json` | D-ORPHAN | LP-B3 | an orphan :18789 listener + stale handoff = P1; kill-list is ONLY the orphan pid |
| `subtractive-misconfig.json` | D-BURN-adjacent | LP-A1 | subtractive compaction math yields an effective ceiling <= 0 |
| `idle-burn.trajectory.jsonl` | D-BURN | LP-A2 | idle-window paid burn = D2 P1; a working window is silent |
| `cross-run-resend.sends.json` | D-RESEND | LP-A10 | 3 identical cross-run sends (distinct run ids, same source->target, same payload) = D7 P1 loop-confirmed; 2 = WARN-only; a distinct-payload fan-out never fires; raw payload never in a finding |
| `october-sessions.active.json` | D-OCTOBER-FEEDS | D2 | the REAL `openclaw sessions --all-agents --active 1440 --json` envelope and row field names (captured read-only on the operator box), synthetic values: metered / usage-window / local / unknown-tier sessions |
| `october-audit.agent_run.json` | D-OCTOBER-FEEDS | D3 | the REAL `openclaw audit --kind agent_run --json` shape (`events`, `nextCursor`, `redaction: metadata_only`): 5 identical failed runs in one session |
| `october-audit.tool_action.json` | D-OCTOBER-FEEDS | D5 / D6 | the REAL `audit --kind tool_action` shape: 12 `status=blocked` calls in one runId (D5) and 15 `failed` `exec` calls in 30 s (D6) |

No fixture is ever run against a live box, a live config, or a real credential.
