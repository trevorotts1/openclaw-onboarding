# D-BACKOFF

Simulated failing job. Proves: the backoff intervals are 2h / 4h / 8h ... (jitter
disabled for the drill so the sequence is exact) and the attempt counter is PERSISTED
across a watchdog restart (a fresh Ledger over the same state dir sees attempt 3, not
0). A backoff that lives in memory is how "backoff" becomes a storm. Run by `verify.sh`
step 3. Offline.
