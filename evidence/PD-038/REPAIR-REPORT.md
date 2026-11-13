# PD-038 — repair lane report (PR 3204)

Branch: `pd/fl04-manifest`
Lane: repair (mergeable again, no history rewrite)

## 1. The conflict as given

From `_batch-merger/runs/openclaw-onboarding-20261113-145033/evidence/3204-CONFLICT.txt`:

```
Auto-merging 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_engine_client_report.py
CONFLICT (content): Merge conflict in 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_engine_client_report.py
Automatic merge failed; fix conflicts and then commit the result.
```

Real conflicted path, quoted verbatim:
`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_engine_client_report.py`

## 2. What was merged

| Ref | SHA |
|---|---|
| PRE (branch head at start, proven by `git ls-remote`) | `2bfc0569cada530c5bdb8f0ab23064915c0664c0` |
| `origin/main` (target, proven by `git rev-parse`) | `ebf5c769a2ad5b2582bf2256588095cbef20cfac` |
| merge base | `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` |
| merged head (new, first parent = PRE, second = main) | `6124b1e13344482073fb7d5fb3740ad1fa08e16b` |

Merge was `git merge origin/main` on `repair-PD-038` cut from `origin/pd/fl04-manifest`. Strategy `ort`, **clean, exit 0** — no unmerged paths, no conflict markers produced.

## 3. Resolution per hunk

**There were no conflict hunks.** The conflict from the batch-merger run does not reproduce.

Blob shas for the conflicted path:

| Side | Blob |
|---|---|
| merge base `1a476d2` | `a218d121b81f4da98b3dbb9ee55c14496278d904` |
| `origin/main` `ebf5c76` | `a218d121b81f4da98b3dbb9ee55c14496278d904` |
| `origin/pd/fl04-manifest` `2bfc056` | `7e08c9806f7267ee5fff962969fc11c5ecd4e495` |
| merged `HEAD` `6124b1e` | `7e08c9806f7267ee5fff962969fc11c5ecd4e495` |

`git diff <base> origin/main -- <path>` is **empty**: main never changed this file since the merge base. The two sides are therefore blob-identical on main's side, so `ort` takes the branch version verbatim. Nothing was invented, and no side was dropped — main's state for this path *is* the base state.

Because the previous conflict was against an older `main` that has since moved, the file is now trivially non-conflicting.

### Unit files byte-identical before and after

All 13 paths this branch changes vs. its merge base, branch head blob vs. merged-HEAD blob:

```
IDENTICAL 634c565d0627e1e582c19bf43cc366f4ddb7c748 .github/workflows/presentations-drift-gates.yml
IDENTICAL af350415b14992e22f2a12bbd6c9fa4a9ca0a91c 23-ai-workforce-blueprint/templates/role-library/presentations/00-START-HERE.md
IDENTICAL 7e08c9806f7267ee5fff962969fc11c5ecd4e495 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_engine_client_report.py
IDENTICAL f5bb1daa11d327af98e928d5e4ae4483dd4504e8 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_manifest_defer_trap.py
IDENTICAL bcff1a1d74ec700702382b57aac2b8373ae7f1aa 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_manifest_sop_refs.py
IDENTICAL 77fa357ce0a93f200fb61374685b70b28105ac4f evidence/PD-018a/BUILD-REPORT.md
IDENTICAL 1f85cb2c5b5dc6a9138cd71635cfdd4f9c231ffb evidence/PD-047/BUILD-REPORT.md
IDENTICAL 0d8283b05c9dd23cefb65d3b94ab12c2754e037e evidence/PD-307m/BUILD-REPORT.md
IDENTICAL 85318f9d65285239e7c15757339ada1a01d074ad scripts/ci/pd_manifest_order_check.py
IDENTICAL 1c0af9bb00902c9341df1484068ad417f30aaad3 scripts/ci/presentations-drift-gates.sh
IDENTICAL 215d5f327bbbc5532cf553d8622dad11a5fcfef6 universal-sops/_content-manifest.json
IDENTICAL efee791f3c5e0ea6fdf773d648acb156b20e632c universal-sops/presentation-slide-craft/MANIFEST-SOURCE.txt
IDENTICAL 0ee3538408a10fa2fae822063bcd1b52acae22cb universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json
```

## 4. Acceptance rows at the merged head `6124b1e1`

Working directory: `23-ai-workforce-blueprint/templates/role-library/presentations/scripts`

### Row A1 — `test_declined_sales_branch_defers_the_build_and_the_run_succeeds`

```
$ python3 -m pytest tests/test_pd_manifest_defer_trap.py -v
tests/test_pd_manifest_defer_trap.py::test_declined_sales_branch_defers_the_build_and_the_run_succeeds PASSED [ 50%]
tests/test_pd_manifest_defer_trap.py::test_ungated_build_phase_is_stranded_on_the_non_optional_edge PASSED [100%]
============================== 2 passed in 0.99s ===============================
rc=0
```

### Row A2 — `test_ungated_build_phase_is_stranded_on_the_non_optional_edge`
Same run, PASSED (control row — proves A1 can fail).

### Row A3 — GATE 10: manifest defer-trap

```
$ python3 scripts/ci/pd_manifest_order_check.py --manifest universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json
manifest_version=75 phases=56
[default (sales_checkout=yes, vsl=no)] 9 finding(s)   (INFO rows only)
[both upsells] 10 finding(s)                          (INFO rows only)
[deck only] 4 finding(s)                              (INFO rows only)
[vsl only] 13 finding(s)                              (INFO rows only)
PASS: no DEFER_TRAP or NO_PRODUCER row in any election set.
rc=0
```

### Row A4 — the formerly conflicted file

```
$ python3 -m pytest tests/test_engine_client_report.py tests/test_pd_manifest_sop_refs.py -v
============================== 32 passed in 0.47s ===============================
rc=0
```

No red rows, so no base-commit comparison was required.

## 5. Ancestry proof

```
$ git merge-base --is-ancestor 2bfc0569cada530c5bdb8f0ab23064915c0664c0 HEAD
rc=0
```

PRE is an ancestor of the new head. First-parent line is unbroken; the only new commit is the merge, whose parents are exactly `PRE` and `origin/main`.

## 6. Remote-head proof

```
$ git push origin HEAD:refs/heads/pd/fl04-manifest
   2bfc0569c..6124b1e13  HEAD -> pd/fl04-manifest

$ git ls-remote --heads origin pd/fl04-manifest
6124b1e13344482073fb7d5fb3740ad1fa08e16b	refs/heads/pd/fl04-manifest

$ git rev-parse HEAD
6124b1e13344482073fb7d5fb3740ad1fa08e16b
```

Remote head equals local head, 40 chars literal. Fast-forward, no force, no rebase.

## 7. What could not be proven

- Whether the original batch-merger conflict was against a `main` that has since gained the same blob — that run's recorded `main` sha is not in the evidence file, so the reason the conflict disappeared cannot be attributed definitively. What is proven: at the shas above, base blob == main blob, so no conflict is possible for that path.
- GitHub-side mergeability state after the push is not re-queried here; only the git-level ref equality and ancestry are proven.
- CI on GitHub for the merged head was not observed from this lane.
