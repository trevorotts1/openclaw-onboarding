# U91 (X/U-X1) — verification-run evidence

`verify-master-spec-scrub.py` (this unit's deliverable) run against the
operator's local, fully assembled master spec copy —
`skill6-blended-persona-kanban-MASTER-SPEC-v2-2026-07-13.md` (Section E.2 /
X.1-X.1.5) — on 2026-07-16. Raw stdout + exit code: `verification-run.out`.

## Result

**PASS — binary scrub target MET.** 14 lines in the whole assembled document
contain the retired term: 1 is the LANGUAGE CONFORMANCE header's defining
sentence (L12), 13 are annotated legacy-filename citations (L365, 777, 984,
1047, 1271, 1501, 2223-2228, 2232 — a mix of the six onboarding-repo files
tracked in `scripts/docs-language-allowlist.json` and one Command-Center-repo
legacy reset script tracked under Decision D13 (its literal filename is
recorded in this unit's own
`scripts/verify-master-spec-scrub-extra-citations.json` supplement, not
repeated in prose here). Zero UNEXPLAINED occurrences.

This independently reproduces the count and defining-sentence line number
already recorded in `ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md`'s
U91 row (14 lines, defining sentence at L12) against a newer snapshot of the
same document (local file dated 2026-07-15T14:05, vs. the ledger row's
2026-07-13T22:10:45 evidence timestamp) — the scrub held across the
intervening edits, using a fresh, independent, re-runnable tool rather than
a repeated manual read.

## LLM-read confirmation (the acceptance criteria's second half)

X.1.2's acceptance criteria also requires "an LLM read (never a bare
pattern-match verdict)" of B-U9 and B-U16 confirming their drift
checks/schedules/acceptance survived with meaning intact. Re-confirmed this
pass by direct read at the current line numbers (drifted from the ledger
row's L845-850/L924-929 citation, which was accurate for the 2026-07-13
snapshot; located fresh via a bounded search for the `### B-U9` / `### B-U16`
headings rather than trusting stale line numbers):

- **B-U9** (master spec L900-905, master unit crosswalk = U23): item (3)
  calls for "a **monthly scheduled live proof on the operator's own box**" —
  plain operator language, the routing-drift-check schedule and its
  `site-method-decision.json` binary acceptance criterion are intact.
- **B-U16** (master spec L982-987, master unit crosswalk = U30): schedules
  "the **selector-drift probe** ... in the daily maintenance window with a
  `SELECTOR-MISS`/`PARKED` taxonomy card on failure — drift is caught on the
  operator's box before a client build hits it", and its own item (5)
  explicitly plans the code-identifier rename (owned by this unit's sibling,
  U30) — plain language, meaning and acceptance intact.

## Note on the two matcher widenings this unit's script adds over U92's

Running U92's own diff-scoped literal-substring rule against the WHOLE
document first surfaced 7 lines as `UNEXPLAINED` — all 7 turned out to be
legitimate Class B legacy-filename citations on inspection, just written
either (a) as a bare basename inside a paragraph that had already
established the directory context, or (b) citing the Command-Center-repo
legacy reset script named above (out of scope for the ONB-only CI allowlist
by design). Both are handled by `verify-master-spec-scrub.py`'s basename
matching and its own `verify-master-spec-scrub-extra-citations.json`
supplement (see that script's module docstring) — U92's own
`scripts/docs-language-allowlist.json` is untouched.
