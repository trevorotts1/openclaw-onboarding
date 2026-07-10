# D-OFFSET

Corrupted telegram offset fixture (`tests/fixtures/corrupted-offset.json`). Proves:
LF-2 rewinds `stored_offset` to `oldest_pending_update_id - 1` and the change is
byte-verified in the file. Adopts the fleet-wide `telegram-offset-healthcheck.sh`
behavior. Run by `verify.sh` step 3. Offline.
