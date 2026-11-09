# Broken variant — discovery-drift (connected-but-unconfigured channel; AF-SM-DISCOVERY-DRIFT when unconfirmable)

**C2 live connected-accounts discovery (merge plan C2/R8).** The fixture's discovery probe shows
the client's GHL location has a live-connected **twitter** account, but the config `platforms`
enum is only `["facebook", "instagram"]` and no `platformsExcluded` entry logs a deliberate skip.

That is the **BANNED silent-miss** a fixed enum causes — the exact failure Skill 35 hardened
against: a channel the client actually connected being silently skipped by the weekly run.

Expected (F06 contract, as `../../../../verify.sh` step 4 asserts it): `preflight_gate.py` exits **0**
and the persisted account plan (`--report`) carries the twitter account as an explicit
`skipped` / `connected-but-unconfigured` row: a connected channel is never silently missed, and F06
made it a visible warning instead of a run-wide block. The fix is either adding `twitter` to
`platforms` or recording the client's explicit choice in `platformsExcluded` - the client's choice is
FINAL, and visible, never silent. The fail-closed `AF-SM-DISCOVERY-DRIFT` (exit **2**) trip is an
unconfirmable discovery: the same fixture with `probes.connectedAccounts` not an account list (verify.sh
materializes that variant to a temp file).

```
python3 scripts/preflight_gate.py examples/golden-week/broken-variants/discovery-drift/config.json
```
