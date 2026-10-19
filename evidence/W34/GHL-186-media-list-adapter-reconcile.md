# GHL-186 — Skill 06 media LIST: adapter route is the single path

Branch: `ghlupd/GHL-169-skill06-client-routes` (rebased onto `origin/main`)
Unit: GHL-186 (owner: skill06-media-conflict)
Version: v27.1.40

## 1. Conflict reproduced

Rebase of `4f180cb10` onto `origin/main` (`c5ea6e51d`) stopped on two real
semantic conflicts:

- `06-ghl-install-pages/tools/ghl_media.py` — `list_media`. `origin/main`
  (from merged PR #2316) issued a raw `GET /medias/files` with
  `GHL_MEDIA_LIST_PATH/TYPES/VERSION` and `_GHL_UA`. The branch routes the
  same call through `ghl_public_client.list_media_files` and takes the method,
  path and `Version` from the frozen `media.files.list` registry row.
- `06-ghl-install-pages/tools/ghl_object_router.py` — the `media` object's
  note. `origin/main` described a raw public LIST; the branch describes an
  adapter-routed LIST plus the declared upload/folder gaps.

`git ls-files -u` listed exactly those two paths.

## 2. Resolution (binding decision)

The capability-gated adapter route is the single path for `media.files.list`.

- `ghl_media.py`: resolved to the branch side (adapter call, `MEDIA_LIST_TYPES`
  in-module, `capability` / `capability_record` arguments). The raw list path is
  not retained, so there is exactly one code path. Main's media-list constants
  (`GHL_MEDIA_LIST_PATH`, `GHL_MEDIA_LIST_TYPES`, `GHL_MEDIA_LIST_VERSION`,
  `_GHL_UA`) and `import urllib.parse` are dropped with that path: they had no
  remaining reference after resolution.
- `ghl_object_router.py`: resolved to the branch side — the `media` note says
  LIST is routed through the frozen adapter as `media.files.list`, and upload /
  folder create are declared named gaps in `ghl_route_gaps.py`.

No merge, no force, no test deletion.

## 3. Test reconciliation — `tests/test_ghl_media.py` (converted, not dropped)

The four cases that merged in #2316 reached the raw transport; they now reach
the same transport through a gate that admits `media.files.list`
(`_media_list_gate()` in the test file). Same fake opener, no live calls.

| Case | Conversion |
|---|---|
| `test_type_file_builds_v3_get_and_reaches_transport` | pass the gate; still asserts GET `https://services.leadconnectorhq.com/medias/files`, `locationId` + `type=file`, `Version: v3`, Bearer LOCATION PIT, browser UA (`Python-urllib` absent), and `{files,count,traceId,http}`. Query order is the frozen row's canonical `locationId` then `type` (the raw path emitted `type` first); both parameters and values are unchanged. |
| `test_type_is_normalized` | pass the gate; asserts normalized `type=image` in the emitted URL. |
| `test_http_error_is_typed` | pass the gate; asserts `MediaListError` carrying the adapter's typed `validation_error` and its underlying `http_status == 422`; also asserts the PIT does not leak into the message. |
| `test_body_without_files_is_typed` | pass the gate; asserts `MediaListError` matching `payload_no_files` (adapter's typed rule for a body without `files`). |

Added (same file):

- `test_default_gate_denies_before_transport` — no capability argument raises
  `MediaListError("capability_disabled")` and the injected opener is never
  called (0 transport calls).

Kept unchanged (required-`type` gate, pre-transport):

- `test_list_without_type_fails_before_any_http` (None -> 0 calls)
- `test_blank_type_fails_before_any_http` (blank -> 0 calls)
- `test_invalid_type_rejected_before_transport` (out-of-set -> 0 calls)
- `test_blank_location_or_pit_rejected`

`tests/test_ghl_public_routes.py` still covers the routed media/survey calls,
default-deny, registry consistency and the raw-call negative control.

Version bump required one expectation update in
`tests/test_ghl_funnels_read.py::TestStaleClaimCorrections::test_version_pair_untouched`
(v27.1.39 -> v27.1.40); the test itself is unchanged in intent.

## 4. Test evidence

Suite command:

```
python3 -m pytest 06-ghl-install-pages/tests -q
```

Result on this branch:

```
1 failed, 2717 passed, 17 skipped in 418.89s (0:06:58)
FAILED 06-ghl-install-pages/tests/test_ghl_secret_hygiene.py::TestRepoSourceHygiene::test_no_client_identifiers_in_new_files
```

Targeted file run:

```
python3 -m pytest 06-ghl-install-pages/tests/test_ghl_media.py -q
52 passed, 4 skipped
```

Version drift check:

```
python3 06-ghl-install-pages/scripts/check-version-drift.py 06-ghl-install-pages
skill-version.txt=27.1.40 SKILL.md=27.1.40 CHANGELOG=27.1.40 (... ) -> OK
```

### The one failing test also fails at `origin/main`

The guard `scripts/qc-assert-no-client-names.sh` scans the whole repo and hits
pre-existing files untouched by this branch. Same single test run in a clean
`git archive origin/main` tree and in this branch:

- `origin/main` tree (`/tmp/macmini-GHL-186-main`):
  `FAILED ...::test_no_client_identifiers_in_new_files` —
  `AssertionError: no-client-names guard FAILED` at
  `06-ghl-install-pages/tests/test_ghl_secret_hygiene.py:129`, with the same
  hits (`23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh:387`,
  `CHANGELOG.md:188`, `platform/vps/contabo/container-startup.sh:87`,
  `platform/vps/hostinger/container-startup.sh:100`,
  `scripts/ghl-mcp-autostart.sh:1643`,
  `tests/unit/closeout-watchdog-rr-box-identity.test.sh:6`,
  `tests/unit/skill15-workspace-seed.test.sh:106`).
- This branch: identical failure, same line 129, same guard return code 1.

Conclusion: pre-existing, unrelated to this unit; this branch adds no client
identifier.

## 5. Files touched by this unit

- `06-ghl-install-pages/tools/ghl_media.py` (conflict resolution)
- `06-ghl-install-pages/tools/ghl_object_router.py` (conflict resolution)
- `06-ghl-install-pages/tests/test_ghl_media.py` (4 converted, 1 added)
- `06-ghl-install-pages/tests/test_ghl_funnels_read.py` (version expectation)
- `06-ghl-install-pages/skill-version.txt`, `SKILL.md`, `CHANGELOG.md` (v27.1.40)
- `evidence/W34/GHL-186-media-list-adapter-reconcile.md` (this file)
