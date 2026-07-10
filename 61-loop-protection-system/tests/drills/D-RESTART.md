# D-RESTART

Synthetic crash-looping unit (`tests/fixtures/restart-storm.jlist.json`, a Box A-class
56,050-restart storm). Proves: the process breaker trips at <= 10 restarts (vs 56,050),
the unit is parked (visible-red, never respawns), a P1 is raised with a boot-log
excerpt, AND the raw `pm2_env`/`env` block is DROPPED by `loop_common.filter_pm2_record`
so no credential value ever enters the D1 evidence. Run by `verify.sh` step 3. Offline.
