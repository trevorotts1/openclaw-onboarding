# PD-316 — BUILD REPORT

- Unit: PD-316 · "The upload list-back reads every page"
- Repository: trevorotts1/openclaw-onboarding
- Lane: FL33 (the media uploader) · branch `pd/fl33-media-upload--hold-d12`
- Code head: `7604c6fbebdbabb1c1023d9106693cd8b4627ef8`
- Builder: deepseek-chain (chain default), per ledger row
- Held by D-12 (built and staged, not merged until Trevor says yes)

## 1. The unit row, quoted

From `01-BUILD-SPEC.md` (LANE FL33, PD-316):

> ### PD-316 — The upload list-back reads every page
>
> | Field | Value |
> |---|---|
> | Findings | PD-316 |
> | Severity | Moderate |
> | Builder | deepseek-chain — difficulty logic: paging and one honest note |
> | Lane and repository | FL33 · trevorotts1/openclaw-onboarding |
> | Wave | 3 |
> | Depends on (must be ACCEPTED, that is QC-passed, first) | PD-301, RD-13 |
> | Held by decision | D-12 (built and staged, not merged until yes) |
> | Existing tests it breaks and must update | none known in advance; the lane's reading units and the test census name the rest (rule 15) |
> | Live-action flag | Stub transport only. |
> | Acceptance rows the checker must run | A1 |
>
> **Read first — consolidation amendments (binding; they override the carried-over text below wherever the two differ):**
>
> This unit is the list-back item only: page until the id is found or the listing ends; when the list-back cannot run, add `NOTE: remote list-back not performed` to the returned reasons. The owner-skip item is PD-316b; the ledger-lock item is built in PD-307 (lane FL36, which owns `build_webinar_video.py`). Acceptance: a stub listing of 450 entries with the deck on page 3 is found; a listing error produces the note. Built on top of PD-301's branch, so it carries the same hold.

Lane table, `02-SWARM-PLAN.md`:

> | FL33 | openclaw-onboarding | `pd/fl33-media-upload` | the media uploader | PD-301 ◆ ★ [D-12], PD-316 [D-12], PD-316b [D-15, D-33, D-12] |

Ledger row (step_gate.py / ledger.json): lane FL33, branch `pd/fl33-media-upload--hold-d12`,
depends_on PD-301 + RD-13 (both ACCEPTED), acceptance_rows ["A1"], owned paths:

- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/ghl_media_push.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_upload.py`

Scope kept to the list-back only: `_valid_owner_skip` (PD-316b) and
`build_webinar_video.py` (PD-307, lane FL36) were **not** touched.

## 2. Branch discrepancy (recorded, not hidden)

`git ls-remote --heads origin refs/heads/pd/fl33-media-upload--hold-d12` was **empty**
(branch absent) while the control `git ls-remote --heads origin refs/heads/main` resolved:

```
$ git ls-remote --heads origin refs/heads/pd/fl33-media-upload--hold-d12
(no output; exit 0)
$ git ls-remote --heads origin refs/heads/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac	refs/heads/main
```

The ledger claimed PD-301 (ACCEPTED) at head `2988932a635ccea2288c100e3660fe74c3a1a050`,
and that commit exists locally but not on `origin/main`
(`git merge-base --is-ancestor 2988932a… origin/main` exit 1). The unit text says
"Built on top of PD-301's branch", so the branch was created from PD-301's accepted head
`2988932a6` (its commit is reachable locally via `pd/fl32-curation` and
`origin/pd/fl29-infographic`), not from `origin/main`. Pushing the branch therefore
re-publishes PD-301's accepted commit together with PD-316, which is the stacked lane the
spec asks for. No rebase, no force-push.

## 3. Files changed (2)

| File | Change |
|---|---|
| `…/presentations/scripts/ghl_media_push.py` | +38 −6: new `_LIST_BACK_PAGE_SIZE` / `_LIST_BACK_MAX_PAGES` / `_list_back_deck()`; `gate_ghl_media_complete` now pages the listing and appends `NOTE: remote list-back not performed` when the readback fails |
| `…/presentations/scripts/tests/test_pd_upload.py` | +61 −0: two A1 tests (`test_list_back_pages_until_deck_found`, `test_list_back_error_produces_note`) |

Hunk attribution (every hunk in this branch commit `7604c6f` is PD-316):

1. `ghl_media_push.py` @@ -337,6 +337,37 @@ — helper + constants → PD-316 list-back.
2. `ghl_media_push.py` @@ -1263,13 +1294,14 @@ — `gate_ghl_media_complete` list-back call site + NOTE → PD-316.
3. `test_pd_upload.py` @@ -176,0 +178,61 @@ — the two A1 tests → PD-316.

No sibling-unit hunk is present. `tests/test_upload_gate.py`,
`tests/test_pres026_media_resume.py`, `ghl_media.py`, `_skill48_ghl_media.py` were not
edited (see §7).

## 4. Acceptance row A1 — one test per assertion, run by id

```
$ python3 -I -m pytest tests/test_pd_upload.py::test_list_back_pages_until_deck_found -q
.                                                                        [100%]
1 passed in 0.34s

$ python3 -I -m pytest tests/test_pd_upload.py::test_list_back_error_produces_note -q
.                                                                        [100%]
1 passed in 0.10s
```

- A1a (450-entry stub listing, deck on page 3): `test_list_back_pages_until_deck_found`
  builds a 450-entry listing with the recorded deck at index 400, asserts the gate passes,
  that no "NOT present" reason is emitted, and that the offsets actually walked were
  `[0, 200, 400]`.
- A1b (listing error produces the note): `test_list_back_error_produces_note` makes
  `ghl_media.list_media` raise `RuntimeError("media list HTTP 502")` and asserts
  `"NOTE: remote list-back not performed"` is in the returned reasons (and the gate still
  passes, since NOTEs do not block).

## 5. Mutation proof

Two mutations, each neutralising one half of the change, then restored.

**MUTATION A — single page (old behaviour):** `_LIST_BACK_MAX_PAGES = 1`.

```
$ python3 -I -m pytest tests/test_pd_upload.py -q -k list_back
FAILED tests/test_pd_upload.py::test_list_back_pages_until_deck_found - Asser...
1 failed, 1 passed, 4 deselected in 0.11s
```

**MUTATION B — NOTE dropped (old silent skip):** the `reasons.append("NOTE: …")` removed.

```
$ python3 -I -m pytest tests/test_pd_upload.py -q -k list_back
FAILED tests/test_pd_upload.py::test_list_back_error_produces_note - Assertio...
1 failed, 1 passed, 4 deselected in 0.31s
```

**RESTORED — GREEN:**

```
$ python3 -I -m pytest tests/test_pd_upload.py -q
......                                                                   [100%]
6 passed in 0.28s
```

## 6. Wider affected suite, base vs head

Suite (every pytest file importing `ghl_media_push` or `gate_ghl_media_complete`):
`tests/test_pd_upload.py tests/test_upload_gate.py tests/test_gates.py
tests/test_pres026_media_resume.py tests/test_producers.py tests/test_executor_dispatch.py
tests/test_l11_webinar_executor_no_recursion.py tests/test_fix36_doc_code_reconcile.py`.

| Rev | Result |
|---|---|
| base `2988932a6` (PD-301 head, before this change) | **1 failed, 126 passed** in 16.94s |
| head `7604c6f` (this change) | **1 failed, 128 passed** in 15.41s |

The single failure is identical at both revisions and is therefore proven pre-existing:
`tests/test_pres026_media_resume.py::test_two_workers_same_run_single_operation`
(flaky duplicate-POST assertion; it fails at the untouched base commit too — base output
recorded in this build's scratch log). The +2 passed are the two new PD-316 tests.

## 7. Honest unproved / deliberate boundaries

- **Credential-absent path stays a silent skip.** `gate_ghl_media_complete` still returns
  without a NOTE when `resolve_location_pit`/`resolve_location_id` raise. That is the
  pre-existing documented contract ("silent skip … test_upload_gate expects reasons == []
  on a complete ledger with no env"), and `tests/test_upload_gate.py` (not an owned path)
  pins it at lines 88 and 163. Adding a NOTE there would have broken an out-of-scope file;
  the accepted A1 assertion (listing error → note) is implemented.
- **No live GHL call.** Acceptance is stub transport only, as the unit row requires.
  Paging against the real `GET /medias/files` was not exercised.
- **PD-301's branch was absent on origin.** The discrepancy is recorded in §2 with both
  commands and their output; the branch was created from PD-301's accepted commit because
  the unit text says this unit is built on top of it. Not verified: why the remote branch
  was deleted while the ledger kept its head.
- **The report commit itself changes the head after the code commit.** The remote head
  proof in §8 is for code head `7604c6f`; the post-report head is re-proved in the
  orchestrator's terminal output with `git ls-remote --heads origin`.

## 8. Remote head proof (code commit)

```
$ git push origin HEAD:refs/heads/pd/fl33-media-upload--hold-d12
 * [new branch]          HEAD -> pd/fl33-media-upload--hold-d12
$ git ls-remote --heads origin refs/heads/pd/fl33-media-upload--hold-d12
7604c6fbebdbabb1c1023d9106693cd8b4627ef8	refs/heads/pd/fl33-media-upload--hold-d12
$ git rev-parse HEAD
7604c6fbebdbabb1c1023d9106693cd8b4627ef8
```

40-character remote head equals local head: **yes** (`7604c6f…`).
