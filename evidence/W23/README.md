# W23 / GHL-168 — V4 tenant binding (F1, F2) and `workflows.list` Version (F6)

Builder lane: `ghlupd/W23-v4fix`, worktree `worktrees/W23-v4fix`, base
`origin/main` @ `2ff1d9083`. No live API call was made. No helper agent was
spawned. Nothing was pushed or merged.

## F1/F2 reproduction (before the fix)

`lanes/GHL-168-lane/repro_f1f2.py` (fake transport, temporary capability record
admitting all five V4 operations for tenant `Mct54Bwi1KlNouGXQcDX`):

```
== fresh adapter, admitting record for live tenant ==
  definition.read    enabled=False
  create             enabled=False
  update             enabled=False
  status.change      enabled=False
  delete             enabled=False
  _enabled(update) = False
  workflow_route(definition.read) -> skill44_private_fallback
== one tenant-scoped read ==
  read status: ok
  _enabled(update) after read = True          <-- order-dependent flip
  workflow_route(update) after read -> public_v4
== control: a different tenant must stay denied ==
  no tenant parameter on the probe: WorkflowV4Adapter._enabled() takes 2 positional arguments but 3 were given
```

The same script against the fixed tree (tenant now passed explicitly):

```
== fresh adapter, admitting record for live tenant ==
  definition.read    enabled=True
  create             enabled=True
  update             enabled=True
  status.change      enabled=True
  delete             enabled=True
  _enabled(update) = True
  workflow_route(definition.read) -> public_v4
== one tenant-scoped read ==
  read status: ok
  _enabled(update) after read = True
  workflow_route(update) after read -> public_v4
== control: a different tenant must stay denied ==
  _enabled(update) for other = False
```

## Fix (minimal)

- `public/workflow_v4.py`: `_enabled(operation_id, tenant)` and
  `capability(operation, *, tenant=...)` bind the probe with
  `PublicGhlAdapter.capability(..., tenant=location_id)`. An unbound probe
  returns a default-deny gate; it never reuses a gate another call loaded. The
  four write surfaces, `_disabled_result` and the receipt use the call tenant.
- `utils/workflow_builder.py`: `workflow_route(v4, operation, *, tenant=None)`
  passes the tenant; `CampaignBuilder.route_for` passes `self.loc`.
- `gohighlevel_cli.py`: `workflows get`, `workflows export` and
  `workflows update` pass `_loc(ctx)`.

No new dependency, no unrelated refactor.

## Test evidence

From `44-convert-and-flow-operator/tools/engine`:

```
$ python3 -m pytest tests/ -q
373 passed, 3 skipped, 770 subtests passed in 1.98s
```

Baseline on the same tree before any change: `363 passed, 3 skipped, 770
subtests passed in 1.83s`. The +10 are
`tests/test_workflow_v4_tenant_binding.py`:

- `test_fresh_adapter_is_enabled_from_the_first_call` (a)
- `test_every_surface_routes_public_with_an_admitting_record` (a)
- `test_record_for_a_different_tenant_stays_denied` (b)
- `test_unbound_probe_denies_even_after_a_tenant_scoped_read` (F1 shape)
- `test_ordering_does_not_change_the_verdict` (c)
- `test_a_foreign_read_cannot_enable_the_live_tenant` (c)
- `test_disabled_receipt_is_bound_to_the_call_tenant`
- `F6WorkflowListVersion` × 3 (d)

From the repo root:

```
$ python3 evidence/W23/check-tenant-binding.py
RESULT: PASS - 48 of 48 checks passed
```

`python3 -I` is not usable for this check because `workflow_builder` imports the
internal client, which imports `requests` from the user site-packages; the check
is run without `-I`. The W18 script below is `-I`-safe and was run with it.

## W18 check status

`evidence/W18/check-v4-and-paths.py` is **not on `origin/main`**: it exists only
on `ghlupd/W18-v4` @ `7e4076619`, which is not merged. The exact file was run
against this tree (copied in temporarily, removed afterwards):

```
$ python3 -I evidence/W18/check-v4-and-paths.py
RESULT: FAIL - 6 of 138 checks failed
```

All six are the script's deliberate pins of the pre-fix defect, which a correct
fix must invalidate:

- `workflow_v4.py:289` — pins the unbound `_enabled` body (F1).
- `workflow_v4.py:387, 518, 792, 923` — pin the one-argument `_enabled` calls.
- `workflow_builder.py:121` — pins the unbound `capability = v4.capability(key)`
  route probe (F2).

No other W18 assertion moved: line drift in `workflow_builder.py` and
`operations.py` was deliberately avoided (the `workflow_route` signature/docstring
change is line-neutral; the F6 note sits after the workflows tuple). The other
132 assertions still pass.

## F6

See `f6-workflows-list-version.md`. Named blocker `B-WORKFLOWS-LIST-VERSION`.
The `workflows.list` row is unchanged (`v3`, `A-UNVERIFIED`).
