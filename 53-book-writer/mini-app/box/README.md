# Book Writer Mini-App — Box side (`mini-app/box/`)

Box-side workers that run on the client's own box (never the edge). The edge
Worker is a DUMB RELAY: it stages answers and holds ZERO client PITs. These
modules own the GHL + durable-local side of the pipeline.

## `ghl_writeback.py` (U15) — GHL write-back on the Skill 44 rails

Turns ONE staged answer (produced by the U12 ingest poller) into a GHL contact
write on the CLIENT's sub-account, and mirrors every write to a durable LOCAL
LEDGER MIRROR.

### Isolation (MASTER-PLAN section 3 — three locks, enforced here)

1. **POSSESSION** — the delivery carries that client's KV binding row. A
   missing/incomplete binding is refused before any call.
2. **BINDING** — the server-side KV binding row is the **SOLE authority** for
   the destination. `client_id` + `location_id` are derived ONLY from the
   binding row; any injected `location_id` / `contact_id` / `client_id` in the
   answer body is IGNORED.
3. **CREDENTIAL + WHITELIST** — the Location-PIT is read from env (11 canonical
   aliases, location-scoped by construction) and
   `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` / `CAF_ALLOWED_LOCATION_IDS` MUST contain
   the bound location. Empty whitelist = refuse all writes (fail-closed). When
   the installed Skill 44 engine is importable, its real `safety_gate` is also
   invoked (defense in depth).

**Never the operator's GHL by construction** — there is no operator credential
and no literal location id anywhere in the file.

### GHL is a mirror, not the only copy

Every attempt is appended to the durable local ledger mirror
(`answers/<run>/<step>.jsonl`). On persistent GHL failure the module exits
non-zero with an HONEST FAILURE RECEIPT (AF-BW-MA-WB-PERSISTENT) — an answer is
never silently dropped, and a success is never fabricated.

### Rail contract

The phase config's `submit` block (U01 `gen_phase_config.py`) drives the
mapping: `custom_field_map` (question id -> `bw_<field>`), `tags`,
`raw_json_note`. `raw_json_note: true` appends the raw normalized JSON answer
as a GHL note (system-of-record). A `contact_id` in the binding row targets an
existing contact (PUT, no duplicate); otherwise a contact is created and the
returned id is captured in the ledger receipt.

### Env (env-ref creds only, no secrets in code)

| Env | Purpose |
|---|---|
| `GOHIGHLEVEL_API_KEY` | client LOCATION-PIT (11 canonical aliases) |
| `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` / `CAF_ALLOWED_LOCATION_IDS` | write whitelist; empty = refuse all |
| `GOHIGHLEVEL_APPROVAL_TOKEN` / `CAF_APPROVAL_TOKEN` | Skill 44 approval gate |
| `GOHIGHLEVEL_LOCATION_ID` | optional; the binding row always wins |

### Usage

```sh
python3 ghl_writeback.py <delivery.json> --config <phase-config.json> \
    --ledger-dir <run-dir> [--json]
python3 ghl_writeback.py --self-test
```

`delivery.json` shape (written by the U12 poller):

```json
{
  "binding": { "client_id": "...", "location_id": "...", "slug": "...",
               "phase_id": "...", "run_id": "...", "exp": 0,
               "status": "open", "contact_id": null },
  "answer":  { "qid": "...", "answer": "...", "source": "typed",
               "received_at": 0, "answer_id": "..." }
}
```

### Self-test (stubbed GHL endpoint)

`python3 ghl_writeback.py --self-test` runs against an in-process STUB that is
the control (it records every request it sees, so "nothing landed" on a refused
case is a proven negative, not an absence). Six cases:

- POSITIVE: bound answer lands on the bound location + raw-json note appended.
- NEGATIVE: unbound token -> refused (zero stub hits).
- NEGATIVE: wrong location -> refused (zero stub hits).
- NEGATIVE: injected destination in the answer body is ignored (binding wins).
- NEGATIVE: empty whitelist -> refuse all (fail-closed).
- POSITIVE: bound contact_id -> update (PUT), not duplicate create.

Exit 0 = all assertions passed; 2 = a case failed. No real GHL is ever
contacted during the self-test.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | WRITTEN — answer reached the bound GHL location AND the ledger mirror |
| 2 | REFUSED — an isolation/safety rule fired (zero GHL calls) |
| 3 | USAGE/IO — bad args / unreadable input / unwritable ledger |
| 4 | PERSISTENT — transient retry/backoff exhausted; honest failure receipt |
