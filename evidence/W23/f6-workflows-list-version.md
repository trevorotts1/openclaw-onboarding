# F6 — `workflows.list` Version reconciliation (named blocker)

**Unit:** GHL-168 (W23-v4fix). **Scope:** recorded evidence only. This unit made
no live API call.

## The discrepancy

| Source | Version claimed for `GET /workflows/` |
|---|---|
| `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py` (`workflows.list` row) | `v3` |
| Recorded live call, `GHL_UPDATES_live-ledger.md` line 759 | `2021-07-28` → **200** (747 workflows) |

The ledger line, verbatim:

```
| workflows list | GET /workflows/?locationId · 2021-07-28 | **200** (747) |
```

The live 200 proves `2021-07-28` is accepted for the recorded tenant
(`Mct54Bwi1KlNouGXQcDX`, BlackCEO LLC). It does **not** prove that `v3` fails —
GHL accepts more than one Version on several endpoints, so one working Version
is not evidence against another.

## Determination

**What Version this endpoint requires is not determinable from recorded evidence.**
No recorded capture shows a `v3` request for `GET /workflows/` and its response.
Settling it needs exactly one authorized live call at `v3` (read-only, same
tenant) and its HTTP status recorded in the ledger.

Per the unit contract, the registry row is therefore **left unchanged** — no
guess is committed. Changing `v3` to `2021-07-28` on the strength of a single
200 would trade one unverified claim for another.

## Named blocker

**`B-WORKFLOWS-LIST-VERSION`**

- **Owner:** operator (account authority) + W04 registry lane.
- **Unblock:** one authorized `GET /workflows/?locationId=<live tenant>` at
  Version `v3`, status recorded in `GHL_UPDATES_live-ledger.md`. If it returns
  200, the row stays `v3` and this blocker closes. If it returns a Version
  error, move the row to `2021-07-28` and record the error verbatim.
- **Interim behaviour:** unchanged. The row still declares `v3` with blocker
  `A-UNVERIFIED`; any caller that exercises it reports the recorded status.

## Code trail

The row is annotated in place (`public/operations.py`) with this blocker name so
the claim cannot drift away from its evidence. A test
(`tests/test_workflow_v4_tenant_binding.py::F6WorkflowListVersion`) pins the
row's values and this document's existence.
