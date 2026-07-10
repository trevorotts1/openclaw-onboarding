# D-BURN

Synthetic trajectory with idle paid events (`tests/fixtures/idle-burn.trajectory.jsonl`).
Proves: D2 raises a P1 for an idle-window paid burn, a WORKING (non-idle) window stays
silent, and the alert text carries token counts and a key path only - no secret shape.
Run by `verify.sh` step 3. Offline.
