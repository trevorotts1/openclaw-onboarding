# PD-003 — BUILD REPORT

**Unit:** PD-003 · **Lane:** FL04 · **Branch:** `pd/fl04-manifest--hold-d1`
**Decision hold:** D-1 (HOLD — built and staged, NOT merged)
**Base:** `2bfc0569cada530c5bdb8f0ab23064915c0664c0` (lane tip `pd/fl04-manifest`, PD-047 ACCEPTED)
**Merge-base with main:** `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`
**Built:** 2026-11-13, US Eastern
**Builder model:** deepseek-chain (chain default) · **Planned reviewer:** opus-chain (high)

---

## Spec rows used

The ledger row for PD-003 carries `acceptance_rows: ["A1"]` with no expansion table, so the row
was taken from the unit's own spec entry in
`/Volumes/mac mini m4/swarm-contract/_scratch-pd-docs/acc.txt` (line 9074), quoted verbatim:

> ## PD-003
> **Acceptance:** a new test asserts producer order is lower than consumer order for every edge;
> `sync_check.py` exits 0; the checker from PD-038 prints zero information rows of kind
> `LATE_PRODUCER`; the presentation test suite passes (paste the summary line).

The "checker from PD-038" is `scripts/ci/pd_manifest_order_check.py` (already on the lane tip at
`2bfc0569`, added by PD-038 commit `418f80c8c`). PD-047 (`needs`/`depends_on`) is ACCEPTED on the
same tip; this branch is based on it, not on main, so the checker exists before this unit builds.

---

## What changed

Eight `order` values in `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` moved to
agree with the producer→consumer edges already declared in the same file. No phase was added,
removed or renamed; no `consumes`/`produces_artifact` field changed.

| Phase | Before | After | Why |
|---|---|---|---|
| `P9-SPEECH` | 8.5 | 7.9 | `P8-ASSEMBLE` (8) consumes `PRESENTERS-SPEECH.md` |
| `P-U-GHL-SALES` | 6.2 | 8.78 | consumes `sales.html` (8.75) and `checkout.html` (8.76) |
| `P-U-FORM-GATE` | 5.6 | 9.04 | consumes `working/vsl/html/vsl.html` |
| `P-U-GHL-VSL` | 6.4 | 9.06 | consumes `vsl.html` + the gate-form/workflow files |
| `P-U-COLLATERAL` | 8.8 | 9.07 | consumes `sales.html`, `checkout.html`, `vsl.html`, `checkout_form.json` |
| `P9.6-WEBINAR-VIDEO` | 8.92 | 9.01 | consumes `PRESENTER-AUDIO.mp3` from `P9-DELIVER` (9) |
| `P9.2-GHL-UPLOAD` | 8.9 | 9.02 | consumes `PRESENTER-AUDIO.mp3` (9) and `{deck_slug}-WEBINAR.mp4` (9.01) |
| `P-U-VSL-BUILD` | 8.93 | 9.03 | consumes `media_library.json` from `P9.2-GHL-UPLOAD` (9.02) |

`P9-DELIVER` stays at **9**: it is the delivery interlock and `canonical_render_guard.missing_attestations()`
sweeps every phase whose `order` is strictly LESS THAN delivery's. Moving delivery earlier (tried and
reverted) made `test_delivery_guard_selfblock.py` stop seeing `P7-TELEPROMPTER` (8.95) as "earlier",
so the consumers moved after it instead.

`P-0.5-RESEARCH` was deliberately **left at -0.5**. Its declared `consumes` includes
`working/copy/intake.json`, which the manifest's own order checker lists in `EXTERNAL_INPUTS`
(written by `deck-intake-driver.py` BEFORE the phase graph). `tests/test_af_intake_gate.py` pins it
as a PRE-intake phase: moving it later turns five tests red. The new test honours the same
external-input contract.

### Files touched (every one, per the owned-path rule)

| File | Change |
|---|---|
| `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` | 8 `order` values (8 lines) |
| `universal-sops/presentation-slide-craft/MANIFEST-SOURCE.txt` | restamped `content_sha256` + `generated` (explicit stamp; the generator does not write it) |
| `universal-sops/_content-manifest.json` | **regenerated**, never hand-edited, by `scripts/hash-universal-sops-manifest.py`; diff = `generated_at` + the two changed entries |
| `23-ai-workforce-blueprint/templates/role-library/presentations/00-START-HERE.md` | generated pipeline-sequence block, by `scripts/ci/phase_doc_sync.py --write` |
| `23-ai-workforce-blueprint/templates/role-library/presentations/DEPARTMENT-COUNTS-CANONICAL.md` | generated declared-phase table + order list, by the same script |
| `universal-sops/presentation-slide-craft/SOP-SLIDE-05-PROCESS-MANIFEST.md` | generated registry sentence (id list in `order`), by the same script — named by SOP-SLIDE-06 §6, reported here before editing |
| `23-ai-workforce-blueprint/templates/role-library/presentations/director-of-presentations.md` | the generated "Upsell waves" row, by the same script (not hand-edited) |
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_manifest_order.py` | **new** — the acceptance test |

`manifest_version` stays **75** (see Residuals 1). Shared files `update-skills.sh` and `install.sh`
were not touched. `universal-sops/_content-manifest.json` was regenerated, not edited.

---

## Proof of every acceptance row

### Row 1 — "a new test asserts producer order is lower than consumer order for every edge"

`tests/test_pd_manifest_order.py` walks every `consumes` artifact of every phase, finds every other
phase that produces it (same glob matching the PD-038 checker uses), and asserts
`producer["order"] < consumer["order"]`. Three cases: the edge assertion, a numeric-order guard,
and a guard that the external-input carve-out still refers to artifacts some phase consumes.

PASS on the built manifest:

```
$ python3 -m pytest tests/test_pd_manifest_order.py -q -p no:cacheprovider
...                                                                      [100%]
3 passed in 0.05s
```

CONTROL 1 — the same test against the **unedited** manifest (`git show 2bfc0569:...PIPELINE-MANIFEST.json`,
the lane tip): **RED**, 9 edges.

```
E       AssertionError: 9 edge(s) where the producer's order is not lower than the consumer's:
E           P-U-FORM-GATE (order 5.6) consumes working/vsl/html/vsl.html produced by P-U-VSL-BUILD (order 8.93)
E           P-U-GHL-SALES (order 6.2) consumes working/sales-checkout/html/sales.html produced by P-U-SALES-BUILD (order 8.75)
E           P-U-GHL-SALES (order 6.2) consumes working/sales-checkout/html/checkout.html produced by P-U-CHECKOUT-BUILD (order 8.76)
E           P-U-GHL-VSL (order 6.4) consumes working/vsl/html/vsl.html produced by P-U-VSL-BUILD (order 8.93)
E           P8-ASSEMBLE (order 8) consumes working/deliverables/PRESENTERS-SPEECH.md produced by P9-SPEECH (order 8.5)
E           P-U-COLLATERAL (order 8.8) consumes working/vsl/html/vsl.html produced by P-U-VSL-BUILD (order 8.93)
E           P9.2-GHL-UPLOAD (order 8.9) consumes working/delivery/PRESENTER-AUDIO.mp3 produced by P9-DELIVER (order 9)
E           P9.2-GHL-UPLOAD (order 8.9) consumes working/delivery/{deck_slug}-WEBINAR.mp4 produced by P9.6-WEBINAR-VIDEO (order 8.92)
E           P9.6-WEBINAR-VIDEO (order 8.92) consumes working/delivery/PRESENTER-AUDIO.mp3 produced by P9-DELIVER (order 9)
FAILED tests/test_pd_manifest_order.py::test_every_producer_comes_before_its_consumer
1 failed, 2 passed in 0.25s
```

CONTROL 2 — a single-hunk mutation of the BUILT manifest (`P-U-GHL-SALES` 8.78 → 6.2), proving one
flipped number is caught, not only the whole pre-fix file:

```
E       AssertionError: 2 edge(s) where the producer's order is not lower than the consumer's:
E           P-U-GHL-SALES (order 6.2) consumes working/sales-checkout/html/sales.html produced by P-U-SALES-BUILD (order 8.75)
E           P-U-GHL-SALES (order 6.2) consumes working/sales-checkout/html/checkout.html produced by P-U-CHECKOUT-BUILD (order 8.76)
FAILED tests/test_pd_manifest_order.py::test_every_producer_comes_before_its_consumer
1 failed, 2 passed in 0.07s
```

### Row 2 — "`sync_check.py` exits 0"

```
$ python3 -I 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/sync_check.py
  (M1 skipped: no peer manifest copy at /Users/blackceomacmini/clawd/departments/Presentations/sops/PIPELINE-MANIFEST.json [materialized department default] — single-copy checkout, nothing to compare)
=== sync_check: PRESENTATIONS SOP <-> build_deck.py LOCKSTEP ===
manifest_version: 75
phases: 56  autofails: 196  roles: 36
IN SYNC — the Python renderer, the MASTER ruleset Section-5 table, the role roster, and the SOP set all match PIPELINE-MANIFEST.json.
rc=0
```

(M1 is the peer-copy comparison; it SKIPS because this is a single-copy checkout — reported, not
hidden. The lockstep checks A1–A7/B1–B2 all pass.)

### Row 3 — "the checker from PD-038 prints zero information rows of kind `LATE_PRODUCER`"

BEFORE — unedited manifest (`2bfc0569`), **26** `LATE_PRODUCER` rows:
default 6, both-upsells 9, deck-only 4, vsl-only 7.

```
$ python3 -I scripts/ci/pd_manifest_order_check.py --manifest <unedited PIPELINE-MANIFEST.json>
manifest_version=75 phases=56
[default (sales_checkout=yes, vsl=no)] 9 finding(s)
  INFO LATE_PRODUCER      P-U-GHL-SALES (order 6.2) consumes ... sales.html; earliest active producer is P-U-SALES-BUILD (order 8.75)
  INFO LATE_PRODUCER      P-U-GHL-SALES (order 6.2) consumes ... checkout.html; earliest active producer is P-U-CHECKOUT-BUILD (order 8.76)
  INFO LATE_PRODUCER      P8-ASSEMBLE (order 8) consumes ... PRESENTERS-SPEECH.md; earliest active producer is P9-SPEECH (order 8.5)
  INFO LATE_PRODUCER      P9.2-GHL-UPLOAD (order 8.9) consumes ... PRESENTER-AUDIO.mp3; earliest active producer is P9-DELIVER (order 9)
  INFO LATE_PRODUCER      P9.2-GHL-UPLOAD (order 8.9) consumes ... {deck_slug}-WEBINAR.mp4; earliest active producer is P9.6-WEBINAR-VIDEO (order 8.92)
  INFO LATE_PRODUCER      P9.6-WEBINAR-VIDEO (order 8.92) consumes ... PRESENTER-AUDIO.mp3; earliest active producer is P9-DELIVER (order 9)
[both upsells] 10 finding(s)   (9 of them LATE_PRODUCER)
[deck only] 4 finding(s)       (4 of them LATE_PRODUCER)
[vsl only] 13 finding(s)       (7 of them LATE_PRODUCER)
```

AFTER — built manifest, **zero** `LATE_PRODUCER` rows in all four election sets:

```
$ python3 -I scripts/ci/pd_manifest_order_check.py --manifest universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json
manifest_version=75 phases=56

[default (sales_checkout=yes, vsl=no)] 3 finding(s)
  INFO SELF_CONSUME       P-U-SALES-BUILD (order 8.75) consumes its own product working/sales-checkout/html/sales.html
  INFO INACTIVE_PRODUCER  P-U-COLLATERAL (order 9.07) consumes working/vsl/html/vsl.html; producer(s) ['P-U-VSL-BUILD'] are deferred under these elections
  INFO INACTIVE_PRODUCER  P-U-QC (order 9.05) consumes working/vsl/html/vsl.html; producer(s) ['P-U-VSL-BUILD'] are deferred under these elections

[both upsells] 1 finding(s)
  INFO SELF_CONSUME       P-U-SALES-BUILD (order 8.75) consumes its own product working/sales-checkout/html/sales.html

[deck only] 0 finding(s)

[vsl only] 6 finding(s)
  INFO INACTIVE_PRODUCER  P-U-VSL-COPY (order 3.9) consumes working/upsell/copy/sales.fragment.md; producer(s) ['P-U-SALES-COPY'] are deferred under these elections
  INFO INACTIVE_PRODUCER  P-U-COLLATERAL (order 9.07) consumes working/sales-checkout/html/sales.html; producer(s) ['P-U-SALES-BUILD'] are deferred under these elections
  INFO INACTIVE_PRODUCER  P-U-COLLATERAL (order 9.07) consumes working/sales-checkout/html/checkout.html; producer(s) ['P-U-CHECKOUT-BUILD'] are deferred under these elections
  INFO INACTIVE_PRODUCER  P-U-COLLATERAL (order 9.07) consumes working/sales-checkout/checkout_form.json; producer(s) ['P-U-FORM-CHECKOUT'] are deferred under these elections
  INFO INACTIVE_PRODUCER  P-U-QC (order 9.05) consumes working/sales-checkout/html/sales.html; producer(s) ['P-U-SALES-BUILD'] are deferred under these elections
  INFO INACTIVE_PRODUCER  P-U-QC (order 9.05) consumes working/sales-checkout/html/checkout.html; producer(s) ['P-U-CHECKOUT-BUILD'] are deferred under these elections

PASS: no DEFER_TRAP or NO_PRODUCER row in any election set.
rc=0
```

The remaining INFO kinds are `SELF_CONSUME` (P-U-SALES-BUILD legitimately rewrites its own product)
and `INACTIVE_PRODUCER` (the election declined the producing branch) — neither is `LATE_PRODUCER`.

### Row 4 — "the presentation test suite passes (paste the summary line)"

Suite run at the built tree and at the unedited base (`2bfc0569`, a pristine detached worktree):

```
BUILT:   225 failed, 3658 passed, 12 skipped, 4 warnings in 998.30s (0:16:38)
BASE:    225 failed, 3655 passed, 12 skipped, 4 warnings in 1080.43s (0:18:00)
```

`SUITE_DIFF_NOTE` = **The FAILED sets are identical: 225 in each tree, `comm` shows 0 names only in
the built tree and 0 only in base. The built tree adds exactly +3 passed — the three new PD-003
tests. No pre-existing test changed state.** The suite's red count is a known pre-existing condition
of this checkout (and of the lane tip it is based on), not a PD-003 regression.

Targeted regression (the five tests that went red during the reverted P9-DELIVER experiment, plus
the manifest neighbours and the version lockstep):

```
$ python3 -m pytest tests/test_af_intake_gate.py tests/test_delivery_guard_selfblock.py \
    tests/test_engine_client_report.py tests/test_pres026_media_resume.py \
    tests/test_pd_manifest_defer_trap.py tests/test_pd_manifest_sop_refs.py \
    tests/test_manifest_assert.py tests/test_b30_brief_registration.py -q
69 passed, 1 failed in 12.28s   # failure = test_pres026_media_resume.py::test_two_workers_same_run_single_operation
```

That one test is a timing/concurrency test. It PASSES on isolated rerun on BOTH trees:

```
$ python3 -m pytest tests/test_pres026_media_resume.py -q     # base worktree
7 passed in 10.60s
$ python3 -m pytest tests/test_pres026_media_resume.py -q     # built worktree
7 passed in 10.45s
$ python3 -m pytest tests/test_pres026_media_resume.py -q     # built worktree, second rerun
7 passed in 10.27s
```

### Lockstep gates beside the acceptance rows

```
$ python3 -I scripts/ci/phase_doc_sync.py --check
PHASE_DOC_SYNC_PASS: every phase table and version marker matches manifest_version 75 (56 phases).
rc=0

$ python3 -I scripts/hash-universal-sops-manifest.py --check
PASS: universal-sops content manifest clean (116 files, all sha256 match)
rc=0
```

Entry-level BYTES verification (not just sha/--check):

```
presentation-slide-craft/PIPELINE-MANIFEST.json: disk sha=cee9d1e1...2d12 bytes=205254 | manifest sha=cee9d1e1...2d12 bytes=205254 | MATCH=True
presentation-slide-craft/SOP-SLIDE-05-PROCESS-MANIFEST.md: disk sha=12e6e24b...0d3f bytes=14168 | manifest sha=12e6e24b...0d3f bytes=14168 | MATCH=True
file_count 116 entries 116
```

`MANIFEST-SOURCE.txt` after restamp:

```
content_sha256=cee9d1e12716d9d591e34cd3b7f4a256a5b6ef2561938bb4edb2a22aadb22d12
generated=2026-11-13T12:48:10Z
```

---

## Hunk attribution — merge-base `1a476d2cb` → HEAD

Sibling units already on this branch (NOT mine; named so the reviewer can separate them):

| Commit(s) | Unit | Hunks |
|---|---|---|
| `76afd8c11` `418f80c8c` `265e563d4` `98a3ff093` | PD-038 | manifest deferrals; **`scripts/ci/pd_manifest_order_check.py` (new)**; `presentations-drift-gates.sh`; `.github/workflows/presentations-drift-gates.yml`; `test_pd_manifest_defer_trap.py`; `test_engine_client_report.py`; manifest/AF rows; `_content-manifest.json` |
| `fe19a5d25` | PD-021 | manifest phase rename (`P-SP-*` intake) |
| `4243522a5` `e0bef34c8` | PD-307m | presenter-audio `consumes` on `P9.6-WEBINAR-VIDEO`; evidence report |
| `b78085f9e` `b64fb8cd5` | PD-018a | client labels/visibility on every manifest phase; evidence report |
| `4ecf384c8` | PD-050 | test renames |
| `584cd9583` | PD-034 | generated-block operator name removal |
| `f83cefb75` `2bfc0569c` | PD-047 | eleven `sop_refs`; `test_pd_manifest_sop_refs.py`; restamps; evidence report |

My hunks (this unit's commit) are exactly:

- `PIPELINE-MANIFEST.json` — 8 `"order"` lines (the table above); nothing else in the file;
- `MANIFEST-SOURCE.txt` — 2 lines (sha + timestamp);
- `_content-manifest.json` — 3 lines: `generated_at` + `PIPELINE-MANIFEST.json` sha/bytes + `SOP-SLIDE-05` sha;
- `00-START-HERE.md`, `DEPARTMENT-COUNTS-CANONICAL.md`, `SOP-SLIDE-05-PROCESS-MANIFEST.md`,
  `director-of-presentations.md` — the generated regions only, produced by `phase_doc_sync.py --write`;
- `tests/test_pd_manifest_order.py` — new file;
- `evidence/PD-003/BUILD-REPORT.md` — new file.

---

## Residuals / known issues (report, do not hide)

1. **`manifest_version` stays 75.** SOP-SLIDE-06 §4 says "MUST increment on every manifest change";
   this lane's accepted units (PD-018a, PD-021, PD-038, PD-047) all changed manifest content and
   kept 75. Bumping here would force `MIN_MANIFEST_VERSION` in **two non-owned** scripts
   (`scripts/manifest_assert.py`, `scripts/presentation_job/manifest.py`) plus four role-file
   version markers, because `test_b30_brief_registration.py::test_registration_is_version_neutral`
   asserts manifest version == both MIN mirrors. That is a wider lockstep change than this unit's
   owned paths. Left at 75 to match the lane; the reviewer can decide whether a version bump unit
   is needed.
2. **Hand-written prose still cites old order numbers** in files outside this unit's owned paths:
   `audio-demonstration-specialist.md` (23/119/284), `fish-audio-expression-specialist.md`
   (21/31/65/160/186/242/349), `pptx-assembly-specialist.md:119`,
   `director-of-presentations.md` (255/271/273 — lines 255/271/273 are not in the generated
   regions). The machine-checked regions are correct; these are prose copies.
3. **Full-suite failures are pre-existing.** At the unedited base `2bfc0569` the suite is
   `225 failed, 3655 passed, 12 skipped`; the built tree adds the 3 new tests and changes no
   other failure. Comparing FAILED sets: 0 tests fail only in the built tree; 0 fail only in base
   (after the P-0.5/P9-DELIVER experiments were reverted).
4. **`test_pres026_media_resume.py::test_two_workers_same_run_single_operation`** is
   timing-sensitive under load; passes on isolated rerun on both trees (above).
5. **`P-0.5-RESEARCH` is a declared edge that the external-input contract excludes** —
   `working/copy/intake.json` is written by `deck-intake-driver.py` before the phase graph.
   `tests/test_af_intake_gate.py` asserts the phase is pre-intake; moving it later broke five
   tests. The new test mirrors `pd_manifest_order_check.py:EXTERNAL_INPUTS` exactly for that one
   artifact class and adds a guard that each entry is still consumed by a phase.
6. **D-1 HOLD:** this branch is built, committed and pushed, but NOT merged. No merge, no PR.

---

## Commit and remote proof

- Build commit: `ab5adf06e3e28fd0dbdb9d9221e719b71ae62524`
- Push: `git push origin pd003-build:refs/heads/pd/fl04-manifest--hold-d1`
- `git ls-remote --heads origin refs/heads/pd/fl04-manifest--hold-d1` returned
  `ab5adf06e3e28fd0dbdb9d9221e719b71ae62524	refs/heads/pd/fl04-manifest--hold-d1` at that push;
  local `git rev-parse HEAD` was the same 40-char hash — compared literally.
- The build report itself is committed on top of that build commit; the same
  `ls-remote` vs `rev-parse HEAD` equality was re-proven after every push. The final branch tip
  40-char hash is printed in this report's return text (a commit cannot contain its own sha).
- Trees clean after the push: build worktree `git status --porcelain` = empty; lane clone
  `/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL04--hold-d1` status = empty on
  `pd/fl04-manifest--hold-d1`.
- **D-1 HOLD: no merge, no PR opened.**

---

## Commands used (all run from the build worktree)

```
git branch --show-current                                  # lane clone: pd/fl04-manifest--hold-d1
git worktree add -B pd003-build .../scratchpads/PD-003/wt origin/pd/fl04-manifest
python3 -I scripts/ci/pd_manifest_order_check.py --manifest ...        # BEFORE / AFTER
python3 -I scripts/ci/phase_doc_sync.py --write                        # regenerate owned regions
python3 -I scripts/ci/phase_doc_sync.py --check
python3 -I 23-.../presentations/scripts/sync_check.py
python3 -I scripts/hash-universal-sops-manifest.py                     # regenerate content manifest
python3 -I scripts/hash-universal-sops-manifest.py --check
python3 -m pytest tests/test_pd_manifest_order.py -q                   # pass
PD_MANIFEST_PATH=<parent> python3 -m pytest tests/test_pd_manifest_order.py -q      # RED
PD_MANIFEST_PATH=<mutant> python3 -m pytest tests/test_pd_manifest_order.py -q      # RED
python3 -m pytest tests -q                                             # full suite, built vs base
```
