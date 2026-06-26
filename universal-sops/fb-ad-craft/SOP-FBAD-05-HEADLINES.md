# SOP-FBAD-05: WRITE THE 10 HEADLINES

**Cluster:** FB/IG Ad-Craft Rules
**Master authority:** `AD-PIPELINE-MANIFEST.json` + `MASTER-AD-QC-AUTOFAIL-RULESET.md` (Gate A)
**Owning role:** Direct-Response Ad Copywriter
**Stage:** S3-HEADLINES — `depends_on: [PICK-10]` (runs in parallel with S2 + S4)
**Produces:** `working/s3-headlines.md` + `working/checkpoints/s3-receipt.json`
**Author-hats (PINNED):** Robert Bly (lead) + Brendan Kane
**Gates:** AF-FBAD-HEADLINE-SHAPE (+ Gate A AF-FBAD-COPY-QC)

---

## 0. WHY THIS SOP EXISTS

The headline is the bold line under the image, beside the CTA button — the last thing
the eye lands on before deciding. One headline per chosen overlay, 1:1. To keep the 10
coherent and testable, headlines may use ONLY the four locked shapes.

## 1. THE FOUR LOCKED SHAPES (the only allowed forms)

| Shape (`shape` value) | Form | Author lean |
|---|---|---|
| `how-to` | "How to ___ without ___" | Bly (Bly's classic how-to headline) |
| `question` | "Tired of ___?" / "Ready to ___?" | Kane (curiosity gap) |
| `number-list` | "3 reasons ___" / "7 ways ___" | Bly (specificity) |
| `direct-promise` | "Get ___ in ___" (a concrete promise) | Bly + Kane |

Any headline outside these four shapes HARD-FAILS (AF-FBAD-HEADLINE-SHAPE). Spread the
10 across the shapes (don't ship 10 questions).

## 2. CRAFT NOTES

- Headlines stay on-mission and in the audience's wording.
- Keep them short enough to not truncate on mobile (~40 characters is the safe read).
- Pair each headline to its body's promise — they are one ad.

---

## 3. INDEPENDENT QC (Gate A — The Words)

Graded with the overlays (02) and bodies (04) by the independent Ad Quality Reviewer.
Pass = 8.5+ no category < 7 (AF-FBAD-COPY-QC) AND independent (AF-FBAD-QC-INDEPENDENCE).

---

## 4. ATTESTATION APPEND (replaces any prose "do not skip")

`working/s3-headlines.md` — the 10 headlines, numbered to match the chosen overlays.
`working/checkpoints/s3-receipt.json`:
```json
{
  "headline_count": 10,
  "headlines": [
    { "shape": "how-to", "text": "How to land podcast guests without cold DMs" },
    { "shape": "question", "text": "Tired of chasing guests?" },
    "... one object per headline; shape in {how-to, question, number-list, direct-promise} ..."
  ]
}
```
`_chk_headline_shape` validates every `shape` against the locked set. An off-shape
headline HARD-FAILS S3.
