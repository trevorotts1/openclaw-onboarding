# D-ORPHAN

Scratch orphan-listener + stale-marker fixture (`tests/fixtures/orphan-port.json`).
Proves: D4 flags LP-B3 as P1 and the kill-list contains ONLY the orphan pid - the
declared supervisor pid is never in the kill target. The Box E verified 4-step
procedure. Run by `verify.sh` step 3. Offline.
