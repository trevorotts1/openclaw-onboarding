# GHL-198 — re-pin the V4 path gate to post-batch source

Base: `origin/main` `bf2385c7553cea09d32f68c49b2765acd4867ddb`.
Scope: `evidence/W18/check-v4-and-paths.py` only.

## Reproduced first

`python3 -I evidence/W18/check-v4-and-paths.py` on base:

```
RESULT: FAIL - 13 of 138 checks failed
```

All 13 matched the defect report exactly. The three V4 strings
(`if not self._enabled(operation_id):`, `capability = v4.capability(key)`,
`return bool(self._public.capability(operation_id).enabled)`) occur zero times
in the current sources.

## Re-pins (purpose kept, no check deleted)

| Was pinned | Now asserts |
|---|---|
| `workflow_v4.py:387/518/792/923` + `if not self._enabled(operation_id):` | Each write entry point (`create_workflow`, `update_definition`, `set_status`, `delete_workflow`) contains `key = "<key>"`, `if not self._enabled(operation_id, tenant):` and `self._disabled_result(` in its own body; the unbound form is absent file-wide. Anchor = method name (new `def_body` helper), not a line. |
| `workflow_v4.py:289` `return bool(self._public.capability(operation_id).enabled)` | `_enabled` takes a `tenant`, denies when the location is missing (`if location_id is None: return False`), and returns the tenant-bound capability; the unbound `capability()` probe returns `CapabilityGate().get(operation_id)` (default-deny). |
| `workflow_builder.py:121` `capability = v4.capability(key)` | `workflow_route` body probes `v4.capability(key, tenant=tenant)` and branches on `if capability.enabled:`. |
| `ghl_media.py:136` | `GHL_MEDIA_UPLOAD_PATH = "/medias/upload-file"` still exists and is sent as `GHL_SERVICES_ORIGIN.rstrip("/") + GHL_MEDIA_UPLOAD_PATH`. |
| `ghl_media.py:149` | `GHL_MEDIA_VERSION = "2021-07-28"` still exists and is sent via `req.add_header("Version", GHL_MEDIA_VERSION)`. |
| `ghl_object_router.py:369` | `m["media"] = ObjectRoute(` still present (line-independent). |
| `ghl_object_router.py:389` | `m["product"] = ObjectRoute(` and `raw HTTPS services.* /products` still present. |
| 06 "unexpected public-adapter wiring" (absence) | Adapter routing is deliberate (merged #2329). Assert exclusivity: `ghl_public_client` imports and constructs `PublicGhlAdapter`, `call_public` calls `adapter.call(**kwargs)`; `ghl_route_gaps` declares `CALLER_FILES` / `RAW_MARKERS` / `NAMED_GAPS`; every gap anchor still resolves (`missing_anchors == []`); the negative-control `ALLOWED_RAW_LINES` set (read from the test via `ast`) leaves zero undeclared raw-REST lines; and the same scan with nothing allowed is non-empty, proving the scanner discriminates. |
| `ghl_funnels_read.py:138/139` | `FUNNEL_LIST_PATH` / `PAGE_LIST_PATH` keep their values, are used in the read path (constant occurs at least twice), and are absent from the frozen registry path templates (named gaps, never public rows). |
| 35 / 49 / siglaunch | Unchanged: no `PublicGhlAdapter` wiring. |

Remaining line pins outside the failing set still pass and were left untouched.

## Negative control

Scratch mirror of the worktree with `FUNNEL_LIST_PATH` reverted to
`"/funnels/funnel/listX"`:

```
RESULT: FAIL - 1 of 138 checks failed
  - FUNNEL_LIST_PATH must stay the documented gap path '/funnels/funnel/list', used by the read path and absent from the frozen registry
```

Exactly the re-pinned check, nothing else.

## Result

`python3 -I evidence/W18/check-v4-and-paths.py`:

```
RESULT: PASS - 138 checks
```

exit 0.
