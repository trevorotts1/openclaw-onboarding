# W24 / GHL-170 — capability-gate breadth suite

- Unit: GHL-170 (exclusive ownership: capability-breadth-suite)
- Branch: `ghlupd/W24-breadth` in worktree
  `/Volumes/mac mini m4/Downloads/GHL updates/worktrees/W24-breadth`
- Base: `2ff1d9083` (freshly fetched `origin/main` at run time)
- New artifact: `44-convert-and-flow-operator/tools/engine/tests/test_capability_breadth.py`
- Production modules edited: **none**. Findings below are recorded, not fixed.
- Live calls: **none**. Every dispatch goes through the in-repo `FakeTransport`;
  there is no token, PIT, location id or customer value in the suite.

## Test evidence

Command, from `44-convert-and-flow-operator/tools/engine`:

```
python3 -m pytest tests/test_capability_breadth.py -q
..........                                              [100%]
10 passed, 700 subtests passed in 0.13s
(exit 0)
```

Full engine suite before the new file (baseline):

```
python3 -m pytest tests -q
363 passed, 3 skipped, 770 subtests passed in 1.79s
(exit 0)
```

Full engine suite after the new file:

```
python3 -m pytest tests -q
373 passed, 3 skipped, 1470 subtests passed in 1.51s
(exit 0)
```

Delta: +10 tests, +700 subtests, 0 failures, 0 new skips.

## Registry shape exercised (dynamic, no hardcoded id list)

`python3` enumeration of `cli_anything.gohighlevel.public.operations.OPERATIONS`:

| Measure | Count |
|---|---|
| Rows | 140 |
| public_direct | 111 |
| skill06_authoring | 12 |
| skill44_private | 6 |
| official_mcp | 4 |
| retired | 4 |
| excluded | 2 |
| capability_gap | 1 |
| read rows | 68 |
| write rows | 72 |

The suite pins `EXPECTED_OPERATION_COUNT = 140` and
`EXPECTED_PRE_GATE_REFUSALS = 24`. A registry change fails the suite with a
message naming the new count and the constants to update.

## Required cases and results

1. **Checked-in record admits nothing in breadth.**
   The record is read at test time; it names tenant `XCgFTEA1oDvsPnTqqgoB`,
   `record_version` 1, with 4 capability rows, all `enabled=false`.
   - Gate layer: `CapabilityGate.require()` raises `CapabilityDisabled`
     (`rule == "capability_disabled"`) for **140/140** registry rows.
   - Adapter layer: all 140 rows return `Status.denied` with
     `refused_before_transport == True` and **0 transport calls**.
     - 116/140 are refused by the capability gate with
       `capability_disabled`.
     - 24/140 are refused earlier by the adapter's frozen tenant-binding
       check, still denied with 0 transport calls:
       - 18 × `unknown_tenant_binding`: `forms.update`, `surveys.get`,
         `surveys.write`, `funnels.create`, `funnels.steps.create`,
         `funnels.get`, `funnels.delete`, `funnels.pages.get`,
         `funnels.pages.autosave`, `funnels.pages.list_internal` (retired),
         `forms.authoring`, `surveys.authoring`, `funnels.pages.authoring`,
         `workflows.restore` (capability_gap), `mcp.list_locations`,
         `mcp.search_operations`, `mcp.describe_operation`,
         `mcp.execute_operation`.
       - 6 × `tenant_path_missing`: `workflows.private.list`,
         `workflows.private.get`, `workflows.private.create`,
         `workflows.private.save`, `workflows.private.trigger.link`,
         `workflows.private.publish`.
     - Every one of the 24 is a non-`public_direct` route (12
       skill06_authoring, 6 skill44_private, 4 official_mcp, 1 retired,
       1 capability_gap), so **all 111 public_direct rows are denied by
       `capability_disabled`**.

2. **Exactly one synthetic enablement.**
   A synthetic record for tenant `Mct54Bwi1KlNouGXQcDX` enabling only
   `locations.get` (complete offline evidence, `activation=UNVERIFIED`) is
   loaded into the adapter.
   - `locations.get` is admitted: `Status.ok`, exactly 1 transport call,
     receipt capability evidence reports `enabled=true` and
     `observed_http_status=200`.
   - The other 139 rows are all denied with 0 transport calls:
     115 `capability_disabled` + the same 24 pre-gate refusals.
   - Control: `load_capability_record()` for that tenant reports exactly one
     row and it is enabled.

3. **Tenant mismatch denies.**
   - Synthetic record for `XCgFTEA1oDvsPnTqqgoB` enabling `locations.get`;
     control load for `XCg...` shows the row enabled. Loaded for the live
     tenant `Mct54Bwi1KlNouGXQcDX`, the gate is empty (`len(gate) == 0`) and
     all 140 adapter calls are denied with 0 transport calls.
   - The checked-in record (tenant `XCg...`) also yields a zero-row gate for
     the live tenant, and every row reports `enabled=false`.
   - Row-level tenant: a record whose capability row carries
     `tenant=XCgFTEA1oDvsPnTqqgoB` while the gate/qualifier is the live tenant
     is refused with `capability_tenant_mismatch`, `refused_before_transport`,
     and 0 transport calls.

4. **Dynamic enumeration + loud count guard.**
   The suite iterates `OPERATIONS.items()`, asserts the row's
   `operation_id` matches its key, asserts unique keys, and asserts the number
   of rows actually exercised equals `len(OPERATIONS)` (140). The pinned count
   and the pinned 24 pre-gate refusals fail with an explicit "update the
   breadth suite" message if `operations.py` changes shape.

5. **Mutation controls (in-test monkeypatch, production untouched).**
   Three mutants are injected and each must make the breadth assertions
   raise `AssertionError`:
   - `adapter._gate_skips` patched to always return `True` (gate bypass):
     caught — an admitted row reaches transport.
   - `CapabilityGate.get` patched to return an enabled, fully evidenced
     capability for every id: caught — admission reaches transport.
   - `adapter.load_capability_record` patched to bind another tenant's
     enablement to the requesting tenant: caught — the enabled row is admitted
     and reaches transport.

## Findings (recorded, not fixed — production files are owned elsewhere)

1. **F-1 — `capability.py` dead code (cosmetic, no behavioural impact).**
   `Capability.evidence_ok()` ends with an unconditional `return (...)` at
   `cli_anything/gohighlevel/public/capability.py:147-152`, followed by an
   unreachable second `return` at lines 153-158 that references an undefined
   name `tenant_read`. It can never execute; it is a leftover from the
   provisional-evidence rule reversal. Owner: public adapter lane.

2. **F-2 — 24 rows never reach the capability gate through `adapter.call`.**
   All are fail-closed and zero-transport, but the denial rule differs from
   `capability_disabled`:
   - 18 rows are refused by `_apply_tenant_binding` because their frozen
     `tenant_binding` literal (`token-id`, `connection scope`, `unknown`,
     `n/a`) has no adapter binding rule.
   - 6 `workflows.private.*` rows declare `tenant_binding="path.locationId"`
     but their path templates name the parameter `{loc}`
     (e.g. `GET /workflow/{loc}/list`), so `_apply_tenant_binding` raises
     `tenant_path_missing`. These rows are `skill44_private`, i.e. the gate is
     skipped for them by design, and the private rail builds its own calls.
   This is not a security weakening — nothing reaches transport — but any
   consumer that expects `capability_disabled` specifically must not assume it
   for these 24 ids. Owner: registry/adapter lane.

3. **F-3 — checked-in record is enablement-empty.** The record names
   `XCgFTEA1oDvsPnTqqgoB` and carries 4 rows (`locations.get`,
   `contacts.list`, `contacts.search`, `custom_fields.list`), every one
   `enabled=false`, `read_verified=false`. This matches the frozen evidence
   rule (a real tenant 200 is required); the breadth suite therefore proves
   default-deny, not live capability.
