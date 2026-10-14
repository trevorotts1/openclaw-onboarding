# Style trait extractions and review forms (Item 10, Amendment 6 Part B2/B5)

Checked-in, reviewed data extracted ONCE from the three Creative
Direction libraries, in the extraction discipline of Item 17's copy
specs: every value traceable to its library section, nothing invented.
Trevor's spot-check is the acceptance gate for these files; until then
their status is **PENDING OWNER SPOT-CHECK**, recorded in each file's
`extraction_status` field. Each extraction file is pinned against the
library version it was extracted from in
`references/external-authorities.json` (Item 11 pin list).

## Files

- `photographers.json`: per-entry Mandatory Signature Locks (five
  categories) with designer-specified checkable tokens, the Technical
  recipe's numeric ranges as structured values, the Avoid list,
  multi-mode lock sets keyed by mode, and VDL-045 as
  `class: "procedural"` (no trait list; the declaration-block check
  governs). Its `review_form` carries the library's ten-question Style
  Fidelity Check and the four-of-five locks dominance rule.
- `cinematic.json`: per-profile five anchors in concrete translated
  form with check tokens, numeric micro-rules, closed vocabularies,
  the Avoid list, and each profile's declarable Item 15 traits. Its
  file level carries the section 0A compiled-prompt schema (adopted as
  the superset schema, FIX-PLAN conflict N4), Global rules A and D,
  and `review_form`: the manual's eight-dimension Fidelity Gate with
  its thresholds (average at least 8.0, Content Preservation at least
  9.0, Signature Fidelity at least 8.0, no other dimension below 7.5,
  at least four of five anchors visibly present, no dominant Avoid
  violation) and its bounded repair loop (repair delta for failed
  dimensions only, maximum two automatic repair cycles inside the
  skill's three-attempt failed-only rule).
- `visual-artists.json`: per-entry mandatory traits in checkable form,
  the entry's own quality-gate dimension NAMES (9 to 11 per entry),
  the Avoid list, entry 31-class pre-render concept fields, and entry
  48's two zone counts with their sources (conflict N5; the checkable
  band is the overlap, 2 to 3). Its `review_form` carries the guide's
  four-question originality gate as reviewer attestation.
- `denylist-photographers.json`, `denylist-cinematic.json`,
  `denylist-visual-artists.json`: HUMAN-ONLY validator data (Part
  B3(iv)). Loaded by `scripts/validate_prompt.py` only. Never copy
  these names into prompt context, worker briefs, or any run file a
  prompt author reads.

Extraction is scoped to the single selected entry: Avoid lists and
representation traits are system-local and mutually exclusive across
entries, so no cross-entry merge or global negative block is ever built
from these files. Representation intelligence for Black subjects lives
in Visual Artists entries 1 to 24; where an entry 25 to 50 governs an
image with Black subjects, the entry records
`representation_source: "image-guide-v5-section-7"` and the
requirements come from Image Guide v5 section 7.

Coverage is now the complete library set per library: all 49
Photographers entries, all 50 Cinematic profiles, and all 50 Visual
Artists entries (149 in total), extended from the original
representative, schema-proving set by the Item 10 full extraction
(Ruling 7, 2026-10-14). The `coverage` field in each file states what
is extracted and the library total. The whole set, old and new entries
alike, remains PENDING OWNER SPOT-CHECK, gated on the same spot-check.

## Review-side wiring (Part B5)

The review form for an image IS the selected style's own fidelity
apparatus, from the `review_form` data above and, for Visual Artists,
the entry's own `gate_dimensions`: Photographers selections are scored
on the ten-question Style Fidelity Check with the four-of-five locks
rule; Cinematic selections on the eight-dimension Fidelity Gate with
its thresholds and repair bound; Visual Artists selections on the
entry's named dimensions, each at 8 or above, NO averaging, plus the
originality attestation.

Over all of these, the image guide's per-artifact rule governs the
stage arithmetic: EACH prompt and EACH image must average at least 8.5
AND score at least 8 on every applicable criterion AND carry zero
auto-fails. Cross-artifact pooling is withdrawn: one strong image may
not lift a weak image's sub-8 criterion over the bar. The gate side of
this arithmetic lives in S1's `stage_gate.py` (landed with the Item 2/12
delta pass); the criteria-set changes that bind the contract's criteria
names to these review forms are filed as gate change requests in
`../../GATE-CHANGE-REQUESTS.md` (stream root).

One override, stated plainly so no builder discovers it mid-build: the
Visual Artists guide's protocol mandates SELF-scoring at every
checkpoint. Skill 71's Item 2 independent-review machinery OVERRIDES
that workflow at the guide's Steps 5, 6, and 8: author self-scores are
drafts subject to independent re-score.
