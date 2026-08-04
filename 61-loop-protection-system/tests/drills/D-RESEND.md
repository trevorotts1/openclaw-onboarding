# D-RESEND

Planted cross-run resend log (`tests/fixtures/cross-run-resend.sends.json`). Proves:
D7 fires at the 2/3 thresholds correctly - three identical cross-run sends (same
source->target pair, same normalized-payload hash, three DISTINCT run ids) within
the 300s window = P1 "loop confirmed" (LP-A8, the 2026-08-04 sessions_send-timeout-
misread incident); a below-threshold two-send pair never reaches P1 (WARN only); a
legitimate three-message fan-out with DISTINCT payloads (a real multi-step handoff)
never fires at all. The hash is computed in the drill from the fixture's plaintext
`payload` field via the real `loop_common.cross_run_payload_hash` (never a pre-baked
literal), and the raw payload text is asserted absent from every finding produced -
hash only, never the message body. Run by `verify.sh` step 3. Offline.
