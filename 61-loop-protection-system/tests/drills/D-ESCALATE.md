# D-ESCALATE

A `[DRILL]`-marked escalation. Proves the Rescue Rangers path and the UNSENT fallback
WITHOUT touching any external API: the drill injects a transport that raises (webhook
down), so `loop_escalate.send()` writes `UNSENT-esc-*.json` for next-tick retry and
never falls back to the silently-dropped group send. The payload carries the SOP fields
+ a machine block (finding id, class, box, prepared kill-card command, revert line) and
no secret shape. Run by `verify.sh` step 3. Offline (no real network).
