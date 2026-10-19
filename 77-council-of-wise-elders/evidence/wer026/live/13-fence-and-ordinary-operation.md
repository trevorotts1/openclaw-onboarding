Proof D — engineering closeout fence
====================================
Captured 2026-10-18T23:27Z.

Driven through the runner's OWN reducer (`supervisor.mjs` `reduceSupervisor` and
`canAutoRestart`), pure functions, no process and no host mutation.

Sequence (fence-receipt.json is the machine record)
---------------------------------------------------
1. initial                 state=STARTING, canAutoRestart.allowed=true reason=WITHIN_BUDGET
2. REQUEST_STOP explicit=true by=operator:w15u001
                           accepted=true, state=STOPPING,
                           explicit_stop={requested_at_ms,by:"operator:w15u001",reason:...},
                           automatic_engineering_restart_allowed=false
3. isExplicitStopFenced    true
   canAutoRestart          {"allowed":false,"reason":"EXPLICIT_STOP_FENCE",
                            "restarts_in_window":0,"limit":3,"window_ms":1800000}
4. AUTO_RESTART event      accepted=false reason=EXPLICIT_STOP_FENCE
5. CLEAR_EXPLICIT_STOP without operator=true
                           accepted=false reason=OPERATOR_CLEAR_REQUIRED
6. CLEAR_EXPLICIT_STOP operator=true
                           accepted=true, explicit_stop=null,
                           automatic_engineering_restart_allowed=true,
                           canAutoRestart {"allowed":true,"reason":"WITHIN_BUDGET"}

Meaning: an explicit operator stop fenced the supervisor — no automatic repair
worker is launched — and only an operator clear re-allows it.

Ordinary council operation unaffected
-------------------------------------
No council database is committed in `evidence/wer026/journey/raw`, so a copied
data dir was seeded with an ordinary `create` from the copied raw fixtures and
then read with `status`. Nothing touched the live Command Center database and
HOME was pointed at an empty lane directory for every CLI call.

commands (exit codes):
  cp -R <install>/.../evidence/wer026/journey/raw <lane>/data/journey-copy    rc=0
  HOME=<lane>/home node <install>/.../runtime/dist/blackceo-council.mjs \
    create --spec <lane>/data/journey-copy/fixtures/session-round1.json \
           --brief <lane>/data/journey-copy/fixtures/brief-round1.json \
           --data-dir <lane>/data/journey-copy --json
    rc=0  {"ok":true,"session_id":"sess-w11u002-round1","state":"DRAFT"}
  HOME=<lane>/home node <install>/.../runtime/dist/blackceo-council.mjs \
    status sess-w11u002-round1 --data-dir <lane>/data/journey-copy --json
    rc=0  {"ok":true,"session_id":"sess-w11u002-round1","state":"DRAFT",...}

So: development supervisor fenced, production runtime service still answers.
Machine receipts: 11-fence-receipt.json, 12-cli-status-copied-data-dir.json
