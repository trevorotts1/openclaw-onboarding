# Module 0 — Preflight (fail-closed readiness gate)

**Source:** `part2-validation` (13 nodes). **Prover:** `scripts/preflight_gate.py`. **Phase:** P0.

Deterministic readiness gate per run. Blocks the entire pipeline (`sys.exit 2`) unless ALL pass:

| Check | Threshold | Endpoint (live mode) | AF code |
|---|---|---|---|
| Kie.ai credits | **≥ 200** | `https://api.kie.ai/api/v1/chat/credit` | AF-SM-PREFLIGHT-CREDITS |
| OpenRouter balance | **≥ $5** | `https://openrouter.ai/api/v1/credits` | AF-SM-PREFLIGHT-BALANCE |
| GHL Private Integration Token | valid | `GET /locations/{locationId}` | AF-SM-PREFLIGHT-TOKEN |
| Required config fields + secrets SET | present | — (never printed) | AF-SM-PREFLIGHT-CONFIG |
| Client status | **== Paid** | — | AF-SM-PREFLIGHT-STATUS |
| **C2 connected-accounts reconcile** | config `platforms` ≡ live listing (± logged `platformsExcluded`) | `GET /social-media-posting/oauth/{locationId}/accounts` | AF-SM-DISCOVERY-DRIFT |

**C2 live discovery (v0.2.0, merge plan C2/R8).** Both drift directions BLOCK, fail-closed: a
configured platform with no live-connected account (posting would silently fail), and a
live-connected platform missing from the enum (the BANNED silent-miss — a channel the client
actually connected must never be silently skipped; the client's deliberate skip lives ONLY in the
logged `platformsExcluded` list). Offline dry-runs supply `probes.connectedAccounts`; in `--live`
an unconfirmable listing is itself a FAIL. The reconcile result is persisted as
`connected_accounts` in the preflight report — the ONLY source Owner Q&A may answer publish scope
from (never a memorized list).

FAIL → a labeled failure report (`--report PATH`) + the configured notification channel; NO
downstream module can execute.

**Two modes.** Offline (default) reads a `probes` object from the config (`kieCredits`,
`openrouterBalance`, `ghlTokenValid`) and evaluates thresholds deterministically — used by dry-runs
and the self-test. `--live` probes the real endpoints with the CLIENT's own keys; a probe that
cannot be confirmed is treated as FAIL (fail-closed). Secret values authenticate but are NEVER
printed.

```
python3 scripts/preflight_gate.py working/copy/config.json --report working/preflight/preflight_report.json
python3 scripts/preflight_gate.py --self-test
```
