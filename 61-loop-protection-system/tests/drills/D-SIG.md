# D-SIG

Planted identical-error log (`tests/fixtures/identical-signature.runs.json`). Proves:
D3 fires at the 3/5 thresholds correctly - five consecutive identical failure
signatures (rolling hash over error class + tool sequence + target) = P1 "loop
confirmed"; a differing run resets the streak. Run by `verify.sh` step 3. Offline.
