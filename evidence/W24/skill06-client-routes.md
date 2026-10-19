# GHL-169 — Skill 06 client routes (routed callers + named gaps)

Unit: GHL-169. Branch: `ghlupd/GHL-169-skill06-client-routes`, cut from
`origin/main` (`2ff1d9083`, 2026-10-19). Worktree:
`/Volumes/mac mini m4/Downloads/GHL updates/worktrees/W24-skill06`.

**Proof labels.** **SOURCE-VERIFIED** — read from this revision. No live API
call was made, no credential resolved for a real call, no workflow activated,
no communication sent.

**Base-revision note.** `evidence/W18/v4-and-client-path-verification.md` was
used only as a pointer. Every call site below was re-derived from source and
from the frozen registry
`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`.
The media LIST client from `ghlupd/W19-media` and the GHL-150 capability-record
change (`920ce3fd4`) are **not ancestors of this base** (`git merge-base
--is-ancestor` = NOT-MERGED), so nothing from them is assumed here.

---

## 1. Route decision per caller

| Caller | Raw route found (file:line) | Registry row? | Disposition |
|---|---|---|---|
| `tools/ghl_media.py` | `GET /medias/files` — no client existed on this base | `media.files.list` GET `/medias/files` `v3` (`operations.py:597-599`) | **ROUTED.** New `list_media` calls `ghl_public_client.list_media_files` → `PublicGhlAdapter.call`. Required `type` is refused before the adapter is built. |
| `tools/ghl_media.py:860` | `POST /medias/upload-file` multipart | `media.upload` `v3` (`operations.py:591-593`), no readback plan | **NAMED GAP.** Adapter transport JSON-encodes every body (`public/transport.py:112`) and cannot carry multipart/form-data; the row has no readback plan and every write refuses without a non-vacuous caller `ReadbackSpec` (`public/adapter.py:418-458`). No evidenced readback filter exists for an uploaded file. |
| `tools/ghl_media.py:1082` | `POST /medias/folder` | `media.folders.create` `v3` (`operations.py:594-596`), no readback plan | **NAMED GAP.** Same readback rule; no evidenced readback expectation for a created folder. |
| `tools/ghl_object_router.py` | no I/O (dependency-injected rail data) | — | **ROUTED (declaration).** `PUBLIC_OPERATION_ROUTES` / `public_operation_route()` name the routed and declared operation IDs per object type. Guard test asserts every ID exists in the frozen registry. |
| `tools/ghl_rest_canvas.py:126,141,154,166,193,206,218,228,240` | internal SPA routes on `backend.leadconnectorhq.com`, executed in-browser with a Firebase `token-id` | `funnels.pages.get`/`.autosave` internal UNKNOWN paths; `workflows.private.*` skill44_private; `funnels.*` internal rows | **NAMED GAPS.** No public adapter route: the rows are internal (`B-INTERNAL`), several have `UNKNOWN` path templates, and the public adapter's location-PIT HTTP transport cannot carry an in-browser Firebase call. Recorded per route in `ghl_route_gaps.NAMED_GAPS`. |
| `tools/ghl_funnels_read.py:145,146` | `GET /funnels/funnel/list`, `GET /funnels/page` | no row for either path | **NAMED GAP.** Registered alternatives are different routes — `funnels.list` GET `/funnels/` (`operations.py:564-566`) and `funnels.pages.list` GET `/funnels/{funnelId}/pages` (`operations.py:567-570`) — and neither envelope/paging shape was captured. Substituting them would replace a captured contract with an unverified one, so they are recorded, not claimed. |
| `tools/ghl_survey_rest.py:44` | `GET backend.leadconnectorhq.com/surveys/{id}` (token-id) | `surveys.get` internal, firebase_internal (`operations.py:557-558`) | **NAMED GAP.** Internal SPA read; no public adapter route. |
| `tools/ghl_survey_rest.py:81` (`survey_list_path`) | `GET services.leadconnectorhq.com/surveys/?locationId=` | `surveys.list` GET `/surveys/` `v3` (`operations.py:554-556`) | **ROUTED (call).** `ghl_public_client.list_surveys` performs the call through `surveys.list`; the path builder remains as the contract-shape reference and the guard test asserts it still matches the row. |
| `tools/ghl_survey_rest.py:160` (`survey_save_route`) | captured POST/PUT `/surveys` (SPA save) | `surveys.write` undocumented, no path/auth class (`operations.py:562-563`) | **NAMED GAP.** Anti-blind-POST, capture-gated; cannot be a registry-driven call. |

Machine-readable form: `06-ghl-install-pages/tools/ghl_route_gaps.py`
(`NAMED_GAPS`, `ROUTED_OPERATIONS`). **SOURCE-VERIFIED**

## 2. Routed path

New `06-ghl-install-pages/tools/ghl_public_client.py`:

- `engine()` imports the frozen public package from
  `44-convert-and-flow-operator/tools/engine` (explicit env override
  `GHL_PUBLIC_ENGINE_ROOT`; no silent fallback).
- `make_adapter()` builds `PublicGhlAdapter` with a location-PIT
  `AuthContext` (source label `env:GHL_LOCATION_PIT`; the value is the
  caller's argument and is never recorded). No gate is shipped, so the
  checked-in record remains default-deny.
- `OpenerTransport` implements the frozen `Transport` seam over the existing
  `(Request, timeout)` opener so tests keep one mocking seam. It adds only the
  browser User-Agent `services.*` requires; method, path, `Version`, auth and
  tenant binding come from the adapter row.
- `call_public()` returns the parsed body and raises `PublicRouteError` for any
  non-`ok` status, including a pre-transport capability refusal.

Dependency: the engine path is discovered by walking up from `tools/` (or
`GHL_PUBLIC_ENGINE_ROOT`). A standalone Skill 06 install without the Skill 44
engine refuses with a typed `PublicRouteError(rule="public_engine_not_found")`
— never an ungated raw fallback. **SOURCE-VERIFIED**

Media LIST required-type gate: `normalize_media_type()` (and the identical
gate in `ghl_media.list_media`) refuses a missing/out-of-set `type` before an
adapter or transport exists. Media write gaps are not silently rerouted: the
raw functions remain and are declared. **SOURCE-VERIFIED**

## 3. Negative control

`tests/test_ghl_public_routes.py::TestNoReintroducedRawREST`:

- Scans the five caller files for `urllib.request.Request(`, `urlopen(req`,
  `urllib.request.urlopen(` and `leadconnectorhq.com`; every marker line must
  be in the pinned `ALLOWED_RAW_LINES` set (each is a declared gap or
  documentation/constant text). A new raw call has new line text → FAIL.
- Pins exact transport counts (`ghl_media.py`: 2 POST Requests, 2 urlopen;
  `ghl_funnels_read.py`: 1 GET Request, 1 urlopen) so a duplicate of an
  existing raw line is also caught.
- Asserts gap anchors still exist and that the routed `list_media` function
  contains no `urllib.request.Request(`/`urlopen(`.
- `test_scanner_discriminates` runs the same scanner with nothing allowed and
  requires a non-empty result — a broken scanner cannot report a false green.
- `test_routed_media_list_owns_no_raw_transport` fails if the raw branch is
  pasted back into the routed function.

## 4. Version bump (G3)

- `skill-version.txt` → `v27.1.39`
- `SKILL.md` `metadata.version` → `v27.1.39`
- `CHANGELOG.md` top heading → `## [v27.1.39] - 2026-10-19`
- `python3 06-ghl-install-pages/scripts/check-version-drift.py 06-ghl-install-pages`
  → `markers-agree=True changelog-wellformed=True -> OK` (the base revision was
  `DRIFT`: `27.1.38` vs `27.1.36`).

## 5. Test evidence

Command (no live calls; every transport is a fake opener):

```
python3 -m pytest 06-ghl-install-pages/tests -q
```

Result on the final tree:

```
1 failed, 2708 passed, 17 skipped in 453.97s
```

The one failure is `test_ghl_secret_hygiene.py::test_no_client_identifiers_in_new_files`,
which runs the repo-wide `scripts/qc-assert-no-client-names.sh`. Its hits are in
files outside this unit's ownership (`evidence/W11/ghl-111-scope-facts.json`,
`platform/vps/**`, `scripts/ghl-mcp-autostart.sh`, `tests/unit/**`) and it also
fails on the base revision (baseline below). No Skill 06 file is a hit.

New file alone:

```
python3 -m pytest 06-ghl-install-pages/tests/test_ghl_public_routes.py -q
22 passed
```

Baseline before this unit (same command, same base):

```
4 failed, 2683 passed, 17 skipped in 737.58s
```

The four baseline failures were pre-existing. Three are repaired here:
`test_ghl_funnels_read.py::test_version_pair_untouched` (pinned a stale
`v27.1.31`; updated because this unit must roll the pair),
`test_guard_ghl_auth_fallback.py::test_token_only_guard_green` and
`test_s06_09_parity.py::test_version_pair_agrees_via_drift_script` (the
pre-existing version drift, now `OK`). The remaining failure is
`test_ghl_secret_hygiene.py::test_no_client_identifiers_in_new_files`, a
repo-wide guard whose hits are outside Skill 06 and which also fails on the
base revision — untouched.
