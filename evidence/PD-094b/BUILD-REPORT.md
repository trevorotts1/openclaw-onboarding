# PD-094b — BUILD REPORT

- **Unit:** PD-094b — "The dollar-figure paragraph follows the price decision"
- **Lane:** FL24 · repo `trevorotts1/openclaw-onboarding`
- **Branch:** `pd/fl24-role-procedures-c--hold-d17` (created from `origin/main` @ `ebf5c769a2ad5b2582bf2256588095cbef20cfac`)
- **Code head (commit 1):** `f4d7dd13d01f1d329717a83beca7c692b8c41302`
- **Builder:** deepseek-chain. **QC (per spec):** opus-chain, thinking medium.
- **Held by:** decision D-17 — built and staged, **not merged until Trevor says yes**.

---

## 1. STEP 1 — my own row, and the branch discrepancy

### Gate output (verbatim)

```
$ python3 -I .../FINAL/scripts/step_gate.py ready --control /Volumes/mac mini m4/swarm-contract/loop-control/pd-fix
{
 "ready": [],
 "waiting": { ... },
 "count": 0
}
```

`ready` contains **no** PD-094b entry. Nothing in the ready list was taken. The row was read from
`ledger.json` instead, and it shows why the gate omits it:

```
id = "PD-094b"  phase = "BUILDING"
note = "build dispatched deepseek-chain in wf_c908f1d6-dbb at 2026-11-13 10:47:12 EST"
branch = "pd/fl24-role-procedures-c--hold-d17"
needs_met = true   depends_on = ["PD-100","PD-090"]   decision_hold = ["D-17"]
```

So the gate's `ready` list excludes a unit already dispatched to a builder. This session **is** that
builder. `step_gate.py check --control . --unit PD-094b` returns `"may_dispatch": false`, reason
`"not offered"` — same cause.

Dependencies verified ACCEPTED (QC PASS), not assumed:

| Unit | phase | head | QC |
|---|---|---|---|
| PD-100 | ACCEPTED | `276762b420499f2fda50c0651667c3011d2bf588` | PASS |
| PD-090 | ACCEPTED | `af296dd88e939092ca2118f036a534daede58ce7` (remote QC head `388ed0df3ffbe0354363cfd19bc146bebe69fd86`) | PASS |

### Branch state, proven with both commands

```
$ git ls-remote --heads origin refs/heads/pd/fl24-role-procedures-c--hold-d17
(no output)                                       exit 0 — branch ABSENT
$ git ls-remote --heads origin refs/heads/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac	refs/heads/main   exit 0 — main RESOLVES
```

Related refs at the same moment:

```
55dbc08155a861ca00f69a426ed80608975af935	refs/heads/pd/fl23-role-procedures-b
388ed0df3ffbe0354363cfd19bc146bebe69fd86	refs/heads/pd/fl23-role-procedures-b--hold-d17
276762b420499f2fda50c0651667c3011d2bf588	refs/heads/pd/fl24-role-procedures-c
```

### The discrepancy, stated plainly

1. The ledger's branch for this unit (`...--hold-d17`) did not exist on origin. Per instruction it was
   created from `origin/main`.
2. The lane table names the **lane** branch `pd/fl24-role-procedures-c` (exists, head `276762b`, PD-100).
   The `--hold-d17` suffix is the hold-branch convention already used by PD-090 — the same decision
   D-17 creates a sibling staging branch rather than blocking the lane.
3. A local branch of that name existed in the lane worktree at `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`,
   an ancestor of `origin/main` — stale and never pushed. The lane worktree was left untouched and clean;
   all work happened in a scratch worktree created from `origin/main`.
4. Consequence, recorded rather than hidden: because the branch is based on `origin/main`, PD-090's
   rewritten `AF-PRICE-FACE` row is **not physically present in this tree**. It lives on
   `pd/fl23-role-procedures-b--hold-d17` (`388ed0df3`) and is not merged because D-17 forbids merging.
   A3 is therefore proven against PD-090's branch content, quoted below. Both units land together on the
   same yes, which is why they share the `--hold-d17` staging suffix.

---

## 2. STEP 2 — the spec, quoted

`01-BUILD-SPEC.md`, lines 4015–4037:

> ### PD-094b — The dollar-figure paragraph follows the price decision
>
> | Field | Value |
> |---|---|
> | Findings | PD-094, PD-090 |
> | Severity | Severe |
> | Builder | deepseek-chain — difficulty mechanical: one paragraph replaced in one role file |
> | Quality control (finds and fixes) | suggested opus-chain at thinking level medium (mechanical wording, path or one-file change); re-check of any repair by a FRESH opus-chain agent at medium or above; the orchestrator decides |
> | Critical first | no |
> | Lane and repository | FL24 · trevorotts1/openclaw-onboarding |
> | Wave | 2 |
> | Depends on (must be ACCEPTED, that is QC-passed, first) | PD-100, PD-090 |
> | Held by decision | D-17 (built and staged, not merged until yes) |
> | Existing tests it breaks and must update | none known in advance; the lane's reading units and the test census name the rest (rule 15) |
> | Live-action flag | none: files and stubbed tests only |
> | Acceptance rows the checker must run | A1, A2, A3 |
>
> **Unit text (written in consolidation):**
>
> - **Change (Slide Image Creator role file, Part F, then regenerate its mirror):** replace the paragraph that begins "The only authorized dollar figure on the deck face is the SINGLE big callout" with: `On slides that are not offer-arc slides listed in AF-PRICE-FACE, the face carries promises and outcomes, not dollar values.` Change nothing else.
> - **Acceptance:** (A1) the new sentence is present once and the old paragraph is gone (read Part F). (A2) the mirror equals the role file's section 9. (A3) the rule now agrees with PD-090's rewritten AF-PRICE-FACE (quote both).

`02-SWARM-PLAN.md`, lines 179 and 255:

> | FL24 | PD-094, PD-093, PD-094b [D-17] |
>
> | FL24 | openclaw-onboarding | `pd/fl24-role-procedures-c` | Slide Image Creator, Assembly, Speech Writer, Audio, Media Librarian and Typography role files and mirrors, and the workbook procedure | PD-094, PD-093, PD-101, PD-102, PD-108, PD-100, PD-100b [D-3], PD-094b [D-17] |

`06-DECISIONS-FOR-TREVOR.md` — D-17:

> ### D-17 — built and staged, not merged until yes
> - **Question:** May dollar values appear on value-stack, tally and component slides, or only one price on the whole deck (PD-090, PD-094b)?
> - **Options:** itemized value stack stays / one price only
> - **Default:** The registered deck-level rules win (itemized value stack stays). Stage the wording change; not merged until yes.
> - **Units waiting on a yes:** PD-090, PD-094b
> - **Was:** PROC D-13

**Scope held.** Nothing in PD-093, PD-101, PD-102, PD-108, PD-100, PD-100b, or the workbook procedure was
touched. No dependency was built. The one residual contradiction found is named in §8, not fixed.

---

## 3. STEP 3 — files changed, and the Part F location discrepancy

Exactly two files, both inside this unit's owned paths:

| File | Change |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/sops/slide-image-creator-sops.md` | 1 line replaced (one paragraph → one sentence) at Part F of SOP 9.10 |
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd094b_dollar_paragraph.py` | new test file, A1/A2/A3 |

**The spec's premise about which file carries Part F is false, and this is the second discrepancy.**
Part F is **not** in `slide-image-creator.md`. `git grep -l "SINGLE big callout" origin/main` returns exactly
one file: `sops/slide-image-creator-sops.md` (line 791). The role file records the divergence itself, line 790:

> *Numbering note (pre-existing divergence, recorded by the Item 26 weave, not created by it): SOPs 9.10 (one-page infographic) and 9.11 (producing-rule additions) are carried in the SOP mirror (sops/slide-image-creator-sops.md) and are binding from there; this role file's Section 15 mistake table already cites them. The next free number in both files is 9.12, used below.*

And `00-START-HERE.md` line 237:

> **Mirror rule:** role file is authoritative. If a sops/ file diverges from the role file's Section 9, the role file wins and the mirror must be regenerated immediately. Never edit the sops/ file directly.

So "edit the role file, then regenerate its mirror" cannot be performed: the block has no role-file source to
edit. The mirror file is the authoritative carrier of SOP 9.10 by the role file's own recorded decision, so the
one-line edit lands there and nothing is regenerated. Both statements are in §7.

**Overlap with sibling units: none.** PD-094 (same files) edits item (10) in SOP 9.10 and explicitly defers item (7)
— "Item (7), the dollar-figure paragraph, is not built here; it is PD-094b (held by decision D-17)" (spec line 3866) —
so the two units do not race the same paragraph. PD-090 edits `qc-specialist-presentations.md`, a different file.

---

## 4. STEP 4 — acceptance rows, run by id

Test file: `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd094b_dollar_paragraph.py`

### At head `f4d7dd13`

```
$ python3 -I -m pytest .../test_pd094b_dollar_paragraph.py -q
...                                                                      [100%]
3 passed in 0.36s
```

By test id:

```
$ pytest ... -q -k "test_A1_"   → 1 passed, 2 deselected in 0.08s
$ pytest ... -q -k "test_A2_"   → 1 passed, 2 deselected in 0.11s
$ pytest ... -q -k "test_A3_"   → 1 passed, 2 deselected in 0.12s
```

### At base `ebf5c769` (same test file copied in, run with `PD094B_BASE=ebf5c769…`)

```
2 failed, 1 passed in 0.16s
FAILED test_A1_new_sentence_present_once_and_old_paragraph_gone
FAILED test_A3_rule_agrees_with_pd090_price_face
```

The tests discriminate: both rows that assert the change are RED at base, GREEN at head. Temp copy removed.

| Row | Base | Head | What it asserts |
|---|---|---|---|
| A1 | RED | **GREEN** | new sentence present exactly once in Part F; `SINGLE big callout` and the old paragraph lead absent from the file |
| A2 | GREEN | **GREEN** | see §7 — mirror coverage + role file untouched (literal whole-file equality is FALSE at base, pre-existing) |
| A3 | RED | **GREEN** | Part F names `AF-PRICE-FACE` as the dollar whitelist; FAIL/PASS examples preserved; PD-090's rewritten row authorizes the same offer-arc classes (cross-branch leg, PD-090 ref reachable) |

### Mutation proof

1. **Neutralise:** the new sentence was replaced back with the original paragraph
   (`grep -c "SINGLE big callout"` → 1, `grep -c "not offer-arc slides"` → 0).
2. **RED:** `pytest -q` → `2 failed, 1 passed in 0.37s`
   ```
   FAILED test_A1_new_sentence_present_once_and_old_paragraph_gone
   FAILED test_A3_rule_agrees_with_pd090_price_face
   ```
3. **Restore:** original new sentence written back (`RESTORED`).
4. **GREEN:** `pytest -q` → `3 passed in 0.18s`.

### Wider affected suite — identical counts, base and head

Nine SOP/role-library prose-consistency and registry tests that read these trees
(`test_fix36_doc_code_reconcile`, `test_gip_weave_af_p24`, `test_af_c8_archetype_carveout`,
`test_af_c8_copy_contract`, `test_fix8_bundle_complete`, `test_fix36_registry_parity`,
`test_fix36_registry_parity_cand17`, `test_f23_drift_gate_pr_paths`,
`test_pd168b_infographic_skip_not_a_deadlock`):

| Tree | Result |
|---|---|
| Base `ebf5c769` | **130 passed** in 3.77s |
| Head `f4d7dd13` | **130 passed** in 3.54s |

No failure. Nothing to classify as pre-existing in the wider suite.

---

## 5. STEP 5 — hunk attribution and remote head

`git diff` against base is exactly one hunk in one file:

```
@@ -788,7 +788,7 @@ On offer-component slides, the slide face carries the PROMISE / OUTCOME of each
-The only authorized dollar figure on the deck face is the SINGLE big callout (the final price, e.g., "$97") on the main offer slide. Every other slide states promises, outcomes, and transformations. The value-stack math (total stack dollar value, running tally) lives in the presenter notes and the re-pitch, not on the audience-facing slide copy.
+On slides that are not offer-arc slides listed in AF-PRICE-FACE, the face carries promises and outcomes, not dollar values.
```

Every hunk is PD-094b's. No sibling unit's text is present, removed, or reflowed.

Remote head proof after push (fast-forward/create; no rebase, no force-push, not main):

```
$ git ls-remote --heads origin refs/heads/pd/fl24-role-procedures-c--hold-d17
f4d7dd13d01f1d329717a83beca7c692b8c41302	refs/heads/pd/fl24-role-procedures-c--hold-d17
$ git rev-parse HEAD
f4d7dd13d01f1d329717a83beca7c692b8c41302
```

Equal, 40 characters literal.

---

## 6. STEP 6 — remote head re-proof after this report

A report cannot contain the sha of the commit that adds it. The two commands were therefore re-run
immediately after the report commit and both printed the same 40-character value:

```
$ git ls-remote --heads origin refs/heads/pd/fl24-role-procedures-c--hold-d17
<40-char sha>	refs/heads/pd/fl24-role-procedures-c--hold-d17
$ git rev-parse HEAD
<40-char sha>          # identical string
```

The literal value is recorded in the unit return block, not invented here.

---

## 7. A2 — what is provable, and what is not

A2 as written — "the mirror equals the role file's section 9" — is **not true of the base commit and cannot be
made true by this unit**. Measured at `ebf5c769` by extracting each `### SOP 9.N` block from both files and
comparing byte-for-byte:

| SOP | role vs mirror at base |
|---|---|
| 9.1 | DIFF (28742 vs 28186 chars) |
| 9.2 | equal |
| 9.3 | DIFF (1341 vs 3192) |
| 9.4 | DIFF (3759 vs 3392) |
| 9.5 | DIFF (3409 vs 4315) |
| 9.6 | equal |
| 9.7 | equal |
| 9.8 | DIFF (14674 vs 14668) |
| 9.9 | DIFF (8164 vs 7817) |
| 9.10 | **mirror only** (role file has no SOP 9.10) |
| 9.11 | **mirror only** |
| 9.12 | DIFF (14000 vs 13972) |

That is pre-existing drift in seven sections plus two mirror-only SOPs — present at base, unchanged by this unit
(the wider suite is 130 passed at base and at head).

A2 is therefore implemented as the strongest **true** invariant, and labelled as such in the test docstring:

1. every `SOP 9.N` heading the role file defines still appears in the mirror (no block dropped);
2. `SOP 9.10` is mirror-only — the spec's "role file, Part F" premise is provably false, and the test asserts it
   so a future role-file addition forces a real mirror regeneration;
3. the new sentence is not duplicated into the role file;
4. the role file is byte-identical to base (when base is resolvable).

I did not write a test that asserts mirror equality and then exclude the seven failing sections silently. The
drift is named here with its numbers.

---

## 8. Honest unproved / out of scope

1. **A2 literal reading is unproved because it is false at base.** Reproducing table in §7. Not caused by this
   unit; not fixed here (fixing seven drifted SOP blocks is a different unit's job).
2. **The spec's "role file, Part F" location is wrong.** Part F exists only in the SOP mirror; therefore no role
   file edit and no mirror regeneration happened. The edit is in the file the role file itself declares binding
   ("carried in the SOP mirror … binding from there").
3. **A3's in-tree coherence is deferred by decision.** On this branch, `qc-specialist-presentations.md` still
   carries the pre-PD-090 row ("Unauthorized per-item dollar values or multiple prices on the offer face"). A3 is
   proven against PD-090's branch (`388ed0df3`), which is the intended merge partner under D-17. Until both merge
   together, the two files disagree in any single tree that has only one of them.
4. **Residual contradiction left untouched, by instruction ("Change nothing else").**
   `slide-image-creator.md` line 959 (Section 15 mistake table, item 18) still says *"Only the single final price
   callout is authorized on the offer face (SOP 9.10 Part F)."* After the AF-PRICE-FACE rewrite that sentence is
   stale. It is in the role file, not Part F, and is not this unit's paragraph. **Recommend a follow-up unit**,
   not an edit here.
5. **Not merged, by design.** D-17 is HOLD; the default is "stage the wording change; not merged until yes". No
   merge, no force-push, nothing written to `main`. No fleet roll.
6. **The lane clone was not used for the build.** All work happened in a scratch worktree from `origin/main`; the
   lane worktree was left clean. Its stale local branch (`1a476d2`) was not updated or deleted.

---

## 9. Proof that the rule now agrees with PD-090 (A3, quoted both)

**PD-090, `qc-specialist-presentations.md`, commit `af296dd88` on `pd/fl23-role-procedures-b--hold-d17`:**

```
-| AF-PRICE-FACE | Unauthorized per-item dollar values or multiple prices on the offer face | slide-image-creator-sops.md SOP 9.10 Part F |
+| AF-PRICE-FACE | Unauthorized dollar figures on a slide face outside the price-belt, value-stack, tally, re-pitch, value-gap, callback and component-card classes the rule authorizes | slide-image-creator-sops.md SOP 9.10 Part F |
```

**PD-094b, `sops/slide-image-creator-sops.md`, Part F at head:**

```
On slides that are not offer-arc slides listed in AF-PRICE-FACE, the face carries promises and outcomes, not dollar values.
```

Agreement: the producing rule no longer claims one deck-wide price. It defers the dollar-figure whitelist to
`AF-PRICE-FACE` and leaves dollar values to the offer-arc classes that row authorizes (price-belt, value-stack,
tally, re-pitch, value-gap, callback, component card). The removed paragraph was the direct contradiction — it
said the "SINGLE big callout … on the main offer slide" was the *only* authorized dollar figure on the whole deck
face, which banned exactly the value-stack and tally figures PD-090 authorizes. D-17's default ("itemized value
stack stays") is now stated identically by both files.
