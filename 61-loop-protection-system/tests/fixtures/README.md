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

No fixture is ever run against a live box, a live config, or a real credential.
