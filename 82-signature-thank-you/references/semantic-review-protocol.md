# Semantic Review Protocol — the A14 Independent Layer (S82-09, observation O-02)

**Purpose.** The structural validators (`validate_thank_you.py`,
`validate_entitlements.py`, `validate_access.py`) prove provenance,
totals, CTA classification, and entitlement equality. They cannot
judge *meaning*: a paragraph can carry no CTA, name no offer ID, and
still sell. Acceptance A14 (doc 18) therefore requires, on top of the
L1 positive/negative tests, an **independent semantic review** that
reads the final page's copy the way a buyer would and fails it if any
part of it pitches something the buyer did not purchase. Spec 12
section 7: "Use an independent semantic review to catch promotional
copy that a structural allowlist misses."

**Independence rule.** The reviewer is never the author of the copy,
renderer change, or artifact under review, and never the session that
produced it. A self-review, or a review by the repairing session of
its own repair, does not satisfy this protocol. The verdict records
the actual author and reviewer session identities (doc 18 section 1);
a review without them is not evidence.

## 1. Surfaces under review

Review the **rendered** artifact (the actual HTML fragment from
`scripts/render_thank_you.py`, or the installed page where a live
level applies), not the source templates alone. Every buyer-visible
copy surface is in scope:

- the confirmation **headline** and status label;
- the **reassurance text** under the headline;
- the order-reference line and the **order summary** (item names,
  billing text, totals rows, caption);
- **access block** headings, descriptions, and action labels;
- **primary next action** and every CTA label;
- "What happens next" **delivery-expectation** lines;
- per-item status wording (paid / pending / failed / refunded lines);
- **state and error copy** (reconciling banner, outage banner, the
  three error fragments) — a support fallback may not smuggle a pitch;
- brand-supplied strings rendered into the page (brand name, support
  label) — untrusted copy is reviewed too, not just house copy.

Out of scope: HTML comments, CSS, and schema/JSON internals the buyer
never sees (the pre-screen also ignores them).

## 2. The pitch tests

The reviewer reads every sentence on every surface above and applies
these tests. **Any single failure fails the review.**

1. **Unpurchased-desire test.** Does any sentence create desire for,
   curiosity about, or awareness of a product, tier, or benefit the
   buyer did **not** purchase in this journey? Naming an unpurchased
   product anywhere — even without a price, a link, or a CTA — fails.
   (Structural twin: `new_offer_pitch`; the semantic layer exists for
   the cases with no offer ID to match.)
2. **Urgency / scarcity test.** Does any language pressure the buyer
   to act soon — deadlines, expiring access they already own,
   limited availability, countdowns, "before it's gone"? Purchased
   facts (a real billing date from the verified snapshot) are not
   urgency; pressure framed around them is.
3. **Outside-the-summary test.** Is any unpurchased product named
   **outside** the order summary — in a headline, a next-step line,
   an access description, a banner? Inside the summary, a name is
   legitimate only when it is a purchased line with verified
   provenance; outside it, an unpurchased name has no legitimate
   reason to appear at all.
4. **New-charge implication test.** Does any wording imply another
   payment is expected, one click away, or required to "complete"
   what was already bought — including soft forms ("finish setting
   up your…", "activate your full…") that reframe a new purchase as
   part of this one?
5. **Confirmation-honesty test.** Does the copy claim more certainty
   than the view holds — "all set" while anything is pending,
   refunded, or unresolved; access implied for an item whose block
   is absent; a failed item described as merely delayed?
6. **Tone test.** Is the page reassurance-and-delivery in tone
   (spec 12 section 4: reduced promotional pressure), or does it
   read like a sales page that happens to contain a receipt —
   superlatives about the *purchase decision*, FOMO framing,
   congratulation copy that pivots to more?

## 3. Pre-screen (not the review)

Before reading, run the deterministic pre-screen:

```bash
python3 scripts/semantic_scan.py <rendered-fragment.html>
```

`scripts/semantic_scan.py` flags candidate phrases (urgency/scarcity
terms, "one more thing", "upgrade", "don't miss", percentage-off,
"only $X" outside the order summary) with line numbers and reasons;
exit 0 clean, exit 1 flagged. Rules of use:

- A flag is a **lead for the reviewer**, not a verdict: the reviewer
  quotes the flagged line and judges it under section 2.
- A clean scan is **not a pass**: paraphrased pitches ("your journey
  is just beginning — imagine what the next level unlocks") contain
  none of the scanned phrases and fail only under the section 2
  tests, read by the reviewer.
- The scanner's output is attached to the review record either way.

### Known false-positive class: pitch words inside purchased names

The pre-screen matches phrases, not provenance, so it **will** flag
pitch words that occur inside a verified purchased product's actual
name — a purchased item really named "…Upgrade…" produces `pitch_verb`
flags wherever that name legitimately repeats (order summary, access
block heading, primary action, CTA labels). This is expected
pre-screen noise, not a defect in the page and not a scanner bug, and
the scanner's behavior is deliberately not changed for it: the same
word in an unpurchased context is exactly what the flag exists to
catch.

The reviewer's dismissal is part of the verdict record (section 4),
never silent: for each such flag, quote the purchased `display_name`
verbatim and cite its order-summary provenance (the purchased line it
comes from, with verified status), state that every occurrence of the
flagged phrase is inside that purchased name, and record the flag as
dismissed under this class. A flagged phrase that occurs anywhere
**outside** a verified purchased name is not dismissible under this
class and is judged under section 2 as usual.

## 4. Verdict recording

Each review produces a record (kept with the run's review receipts,
never inside the artifact under review) containing:

- artifact path and **SHA-256** of the exact rendered artifact
  reviewed;
- **author session** and **reviewer session** identities, and the
  timestamp;
- the pre-screen output (clean or the flag list);
- per-surface result for each section 1 surface, and for every
  section 2 test a PASS or a FAIL with the **quoted offending text**
  (verbatim, with its surface named) for any fail;
- the overall verdict: `PASS` or `FAIL`;
- defect IDs opened for any fail (doc 18 section 9: append a new
  attempt after repair; never edit a failing record into a pass).

## 5. What a FAIL does

- A semantic FAIL **reopens S82-04** (layout and clean copy
  profiles): the offending copy surface is repaired under S82-04's
  copy profiles, the artifact is re-rendered, and the **full**
  review — pre-screen plus this protocol, by an independent
  reviewer — runs again on the new artifact hash. The previous
  failing record stays on file, linked to the new attempt.
- Structural validators passing does not override a semantic FAIL,
  and a semantic PASS does not override a structural failure; A14
  needs both layers green on the **same** artifact hash.
- If the offending copy came from brand/client-supplied strings,
  the defect is recorded against that input and the launch does not
  proceed on a reviewer-edited silent rewrite — the copy owner
  supplies corrected text (doc 16 section 3: conversion changes to
  approved copy are proposals with recorded approval).

## 6. Current status

This protocol and the pre-screen are built (S82-09). The recorded
verdict on the candidate artifact set **exists**: the independent
semantic review was performed 2026-10-15 under this protocol and
recorded in `rooms/S82/review-s82-final.md` §6 — overall verdict
**PASS** on the TEST ONLY rendered fragment (SHA-256 `230ad69b…`,
6,292 bytes; pre-screen clean; reviewer ≠ author; per-surface
and per-test results recorded). A14's semantic layer is therefore
closed at the offline level for the candidate artifact — see
`references/branch-matrix.md` (row P-08). The TEST
ONLY fixture render is the offline review subject; each real
launch's rendered page needs its own recorded verdict before it is
treated as A14-complete at its level.
