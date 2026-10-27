# T-23 WIRE — `monthly_manifest.py`

Lane `PBB-669` (BUILD, role `deepseek-chain`). Repo `<PATH>`.
Worktree `<PATH>`.

| | |
|---|---|
| Base sha | `c994359d6329b6f958c217ee455b40cfb8a0543c` (`origin/main`) |
| Branch | `pb/PBB-669/t-23-wire` (verified absent before creation: `git show-ref --verify --quiet refs/heads/pb/PBB-669/t-23-wire` -> rc **1**) |
| Wiring commit | `afac7f652` — `T-23: wire monthly manifest terms check into pb_contracts validate` |
| Run date | 2026-10-26 (UTC) |
| Verdict | this file contains **no** verdict of mine. Acceptance candidates are UNVERIFIED; an independent QC lane judges. |

Prior lane `PBB-649` left a commit (`849fc218e`) on branch `pb/PBB-649/t-23-wire`; nothing from it was
inherited — this work starts from the base sha above and was written independently.

---

## 1. Instrument proof — both polarities, first

Scanner: `scratch/lanes/PBB-669/scan_refs.py` (Python token scan over 12,930 text files; no grep binary).
It reports `production_refs` (code/config outside the module's own dir), `self_refs`, `doc_refs`.

| Polarity | Command | Result | Shows |
|---|---|---|---|
| KNOWN-POSITIVE | `python3 -I scan_refs.py base-tree pb_contracts` | `files_scanned=12930 unreadable=0`, **production_refs=10**, doc_refs=15, rc 0 | a token that IS referenced reads non-zero, and the list is real (`qc-pb-contracts.sh`, `interactive_owner.py`, `progressive_capture.py`, `publication_receipts.py`, ...) |
| KNOWN-NEGATIVE | `python3 -I scan_refs.py base-tree zz_no_such_module_zz_4491` | production_refs=**0**, self_refs=0, doc_refs=0, rc 0 | a token that cannot exist reads zero — the zero is the instrument agreeing, not a broken check |
| ABORT GUARD | scanner returns **127** if the root is not a directory | enforced in code | `127` is never emitted as a count |

Second instrument (behavioural): `scratch/lanes/PBB-669/probe_validate.py` runs the real CLI
`pb_contracts.py validate --kind approval --file CASE` and prints rc + `ok` + first error. Same control
principle: case `good` must be accepted (proves the path runs), `blank-cta` / `out-of-window` must be refused
only after wiring.

Logs: `scratch/lanes/PBB-669/logs/`.

---

## 2. Genuinely unwired at the exact base sha

Tree built from the sha, not from the working copy:

```
BASE=$(git -C <PATH> rev-parse origin/main)   # c994359d...
git -C <PATH> archive "$BASE" | tar -x -C scratch/lanes/PBB-669/base-tree
python3 -I scratch/lanes/PBB-669/scan_refs.py scratch/lanes/PBB-669/base-tree monthly_manifest --self-dir shared-utils/manifest --verbose
```

```
files_scanned=12930 unreadable=0
production_refs=0
self_refs=2
doc_refs=2
  self       shared-utils/manifest/monthly_manifest.py
  self       shared-utils/manifest/tests/test_monthly_manifest.py
  doc        38-conversational-ai-system/CHANGELOG.md
  doc        shared-utils/manifest/CHANGELOG.md
```

**production_refs = 0.** The module is reached only by its own suite and named only in changelogs.

---

## 3. The real call site (pre-existing production entry point)

`38-conversational-ai-system/tools/pb_contracts.py` — the shipped contract validator. Its `validate`
command already exists at base: declared in the module docstring (`validate --kind KIND --file F`, lines
11-20), registered by `build_parser()` (`validate.set_defaults(func=cmd_validate)`, base line 1215,
now 1241) and dispatched by `main()` (base 1244, now 1270), which `if __name__ == "__main__"` calls.

Wired at **`cmd_validate` — file `38-conversational-ai-system/tools/pb_contracts.py`, lines 727-748
(helper `_approval_terms_errors`) and 751-756 (`cmd_validate`)**:

```
 751 def cmd_validate(args):
 752     doc = load_json(args.file)
 753     errs = check_document(args.kind, doc)
 754     if not errs and args.kind == "approval":
 755         errs = _approval_terms_errors(doc)
 756     result = {"ok": not errs, ...}
```

`_approval_terms_errors` resolves `shared-utils/manifest` on `sys.path` and calls the module's own
`terms_errors()` — no re-implementation, no copy of the field list. Import is at call time because
`monthly_manifest` imports `pb_contracts` to read `PLACEMENT_BOUND_FIELDS`; a module-scope import would
close that cycle for every caller that never sees a manifest. A checkout missing the module returns a
refusal (`$.: approval terms check unavailable (...)`), never a silent pass.

This is a call site, not a re-export: after wiring, `validate --kind approval` on a manifest whose CTA is
a zero-width space, or whose slot sits outside the joined window, exits 1 naming the field (section 5).

---

## 4. CI append — exactly one step

`.github/workflows/qc-static.yml`, job `qc-static`, pure append (`git diff --numstat` = **22 0**):

| | before | after |
|---|---|---|
| steps in job `qc-static` | 145 | **146** |
| one-based index | — | **146** |
| step name | — | `T-23 joined monthly approval manifest suite (explicit name)` |

Appended after the last existing step (`T-24 pb-contracts suite`). Suite named by explicit path:
`shared-utils/manifest/tests/test_monthly_manifest.py`, resolved from `$GITHUB_WORKSPACE`, dry-listed with
`ls -l` before it runs, and an absent checkout **SKIPs LOUDLY** (workflow `::warning` + `⚠ SKIP ... NOT a
pass`) rather than passing silently. No other step touched.

YAML re-parsed after the edit: `YAML OK jobs=["qc-static"] steps=146 last=T-23 joined monthly approval manifest suite (explicit name)`.

---

## 5. It bites — before / after, controls held constant

Same three manifests, same command, two trees. `blank-cta` = `cta_text` is U+200B (schema `minLength: 1`
passes it); `out-of-window` = `P-2` scheduled `2026-12-15`, outside `2026-11-01..2026-11-30`.

| case | BASE `c994359d` | WIRED `afac7f652` |
|---|---|---|
| good | rc 0, ok True | rc 0, ok True |
| blank-cta | rc 0, **ok True** (gap) | rc 1, ok False — `$.placements[P-1].cta_text: an approved term must be present` |
| out-of-window | rc 0, **ok True** (gap) | rc 1, ok False — `$.placements[P-2].scheduled_at: '2026-12-15T15:00:00Z' is outside the joined campaign window 2026-11-01..2026-11-30` |
| **summary** | accepted=3 refused=0 | **accepted=1 refused=2** |

Reference counts on the same two trees (`files_scanned=12930` both):

| token | base | wired |
|---|---|---|
| `monthly_manifest` (production) | 0 | **1** — `38-conversational-ai-system/tools/pb_contracts.py` |
| `pb_contracts` (CONTROL +, held constant) | 10 | **10** |
| `zz_no_such_module_zz_4491` (CONTROL −, held constant) | 0 | **0** |

The `good` case staying accepted is the control that proves the new check refuses the gap and not
manifests in general.

---

## 6. Inverse control — revert, then restore

```
git -C <worktree> checkout c994359d... -- 38-conversational-ai-system/tools/pb_contracts.py .github/workflows/qc-static.yml
```

| measure | reverted |
|---|---|
| production_refs | **0** |
| probe | accepted=**3** refused=**0** (both gaps open again) |
| steps in `qc-static` | **145** |

Restore (`git checkout afac7f652 -- <both files>`) and hash-compare:

```
c1f41c5901ce4821616677e02145669eaff2620c73bd9cfbcaa7a969e74d7d29  38-conversational-ai-system/tools/pb_contracts.py  MATCH
d4774374c91e8e3cd4239e44a5249e3ad4c2ae02188262eeb5bd8bb98f8351ad  .github/workflows/qc-static.yml  MATCH
git status --porcelain: ''
SHA256_ALL_MATCH=True
```

**Inverse restored: yes, byte-identical.**

---

## 7. Acceptance rows

Rows read from `live-ledgers/checks.json` (`items`) and `live-ledgers/build.json` (`tasks[22]`, id `T-23`).
`checks.json` was **not** edited (lane ownership excludes ledger/census; per DECISIONS 2026-10-26T00:02Z a
lane returns a correction block instead — included at the end of this section).

| row | requirement | answer | evidence / named dependency |
|---|---|---|---|
| **C-23** | R-04, R-05 — "Exact placement/account/channel/schedule/CTA/keyword/assets/spares approval; public dispatch binds it, unrelated approved units continue." | **PENDING** — terms/CI half evidenced, dispatch half not landable by this lane | This lane: `terms_errors` now reached from a production entry point (`pb_contracts.py:751-756`), suite green 56/56, CI step 146. Per-placement invalidation ("unrelated approved units continue") is covered by `amend`/`reapprove` cases in the same suite. The "public dispatch binds it" half is `approval_errors` (T-08), which is **REVIEW, candidate `8e98f155`, not accepted/merged** — cannot be answered PASS from here. |
| **C-F10** | R-04, R-06 — fixture F-10 "Monthly approval/new cycle/retry" (tasks T-23, T-24, T-25) | **PENDING** | depends on **T-24 (NOT_STARTED)** and **T-25 (NOT_STARTED)**; a monthly-approval/new-cycle/retry *trace* cannot be assembled from this unit alone. The new-cycle and retry arms exist in the module and are covered by `test_a_date_or_semver_revision_can_advance`, `test_a_rollback_is_refused_even_when_a_word_trails_the_counter`, `next_cycle` overlap cases (green), but the fixture trace is not this lane's to close. |
| **C-F17** | R-04, R-06, R-21 — fixture F-17 "Strict public/person variants, reveal parent and fresh purpose-specific gates" (tasks T-08, T-12, T-23, T-25) | **PENDING** | depends on **T-25 (NOT_STARTED)**, **T-08 (REVIEW)**, **T-12 (ACCEPTED_UNMERGED)**. Nothing in this lane can satisfy a cross-unit trace. |

Counts: **PASS 0 — PENDING 3 — FAIL 0.** No row is claimed on the strength of having written code.

Orchestrator correction block (for `tools/apply_updates.py`; every candidate stays **UNVERIFIED** because
this lane may not approve itself):

```json
{"unit":"T-23","lane":"PBB-669","candidate_sha":"afac7f652","checks":[
 {"id":"C-23","status":"UNVERIFIED","candidate_sha":"afac7f652","evidence_ids":["E-PBB669-T23-BASE-SCAN","E-PBB669-T23-CALLSITE","E-PBB669-T23-CI-STEP","E-PBB669-T23-BITES","E-PBB669-T23-INVERSE","E-PBB669-T23-SUITE"],
  "pending_on":["T-08 acceptance (dispatch binding half)"]},
 {"id":"C-F10","status":"UNVERIFIED","candidate_sha":"afac7f652","pending_on":["T-24 NOT_STARTED","T-25 NOT_STARTED"]},
 {"id":"C-F17","status":"UNVERIFIED","candidate_sha":"afac7f652","pending_on":["T-25 NOT_STARTED","T-08 REVIEW","T-12 ACCEPTED_UNMERGED"]}]}
```

---

## 8. Suite results (heavy permit claimed, then released)

`swarmctl.py permit Purple-Billboard-Client-System-Build acquire PBB-669` ->
`{"unit": "PBB-669", "permit": "acquired", "held": 1, "max": 3}` rc 0.
Live ceiling measured **3**, not 8 (SWARM.md's "8 heavy permits" is a stale sample; the live number is the fact).
Released after the runs -> `{"permit": "released"}`, holders afterwards `[]`.

| suite | command | result |
|---|---|---|
| T-23 own suite (build check) | `python3 -I shared-utils/manifest/tests/test_monthly_manifest.py` | `Ran 56 tests`, **OK**, rc 0 — at base and at `afac7f652` |
| T-24 regression (caller) | `bash 38-conversational-ai-system/scripts/qc-pb-contracts.sh` | `Ran 46 tests`, **OK**, rc 0 |

Disclosure: the T-24 suite was also run **once before** the permit was claimed (same command, same rc 0),
as an early regression probe. Both runs agree; the recorded run in section 8 is the permitted one.

---

## 9. What this lane touched — and what it did not

Changed (2 files, +48/-0):

- `38-conversational-ai-system/tools/pb_contracts.py` — +26 (call site + helper)
- `.github/workflows/qc-static.yml` — +22 (one appended step)

Not touched: `ledger.json`, `census.json`, `DECISIONS.md`, any marker/changelog/bundle, `origin/main`,
`shared-utils/manifest/monthly_manifest.py` (the module was already correct at base — wiring, not
rewriting, was the gap), any other unit's files. No merge, no push to main, no self-approval.

## 10. Reproduce

```bash
source "<PATH>"
L="$LOOP_ROOT/scratch/lanes/PBB-669"
python3 -I "$L/scan_refs.py" "$LOOP_ROOT/worktrees/PBB-669" monthly_manifest --self-dir shared-utils/manifest --verbose
python3 -I "$L/probe_validate.py" "$LOOP_ROOT/worktrees/PBB-669" "$LOOP_ROOT/tmp/pbb669/cases-wired"
cd "$LOOP_ROOT/worktrees/PBB-669" && python3 -I shared-utils/manifest/tests/test_monthly_manifest.py
```
