# SOP-FBAD-02: WRITE THE ~70 OVERLAYS (the baked-in lines)

**Cluster:** FB/IG Ad-Craft Rules
**Master authority:** `AD-PIPELINE-MANIFEST.json` + `MASTER-AD-QC-AUTOFAIL-RULESET.md` (Gate A)
**Owning role:** Direct-Response Ad Copywriter
**Stage:** S1-OVERLAYS — `depends_on: [S0-INTAKE]`
**Produces:** `working/s1-overlays.md` + `working/checkpoints/s1-receipt.json`
**Author-hats (PINNED):** Brendan Kane (*Hook Point*, lead) + Phil Jones (*Exactly What to Say*) + Shelle Rose Charvet (*Words That Change Minds*)
**Gates:** AF-FBAD-OVERLAY-COUNT, AF-FBAD-OVERLAY-WORDCOUNT, AF-FBAD-OVERLAY-TOPLINE, AF-FBAD-ON-MISSION, AF-FBAD-AUDIENCE-WORDING (+ Gate A AF-FBAD-COPY-QC)

---

## 0. WHY THIS SOP EXISTS

The overlay is the single line of text **baked into the picture** — the thing that
stops the scroll. The human picks their favourite 10 of these, so the set must be a
clean, fixed-size menu of distinct, legible, on-mission lines. Off-mission, over-long,
or audience-paraphrased lines poison the whole downstream batch.

## 1. THE 30 / 30 / 10 SPLIT (who writes what hat)

Write exactly the locked count (default **70**) lines, in three voices:

- **30 — Brendan Kane (Hook Point):** scroll-stopping hook lines. Pattern interrupts,
  curiosity gaps, "the thing nobody tells you about ___." Lead the set.
- **30 — Phil Jones (Exactly What to Say):** short directive "magic words" lines —
  "Imagine if…", "What happens when…", "Just because ___ doesn't mean ___." Tight,
  imperative, 3–8 words.
- **10 — Shelle Rose Charvet (Words That Change Minds):** tonal-variety lines that flex
  motivation language patterns (toward/away, options/procedures) for the spread of the
  audience.

## 2. THE LOCKED RULES (auto-failed)

- **Exactly the locked count (70).** Not 68, not 72 (AF-FBAD-OVERLAY-COUNT).
- **Every line 3–19 words** so it bakes legibly into a 1500×1500 square
  (AF-FBAD-OVERLAY-WORDCOUNT). Count words per line and record them.
- **The fixed locked top line is present** — the recurring lead line the brand opens
  every overlay set with (AF-FBAD-OVERLAY-TOPLINE).
- **On-mission:** every line FEATURES the guest/show (recruit / spotlight), never
  "sell a product" (AF-FBAD-ON-MISSION).
- **The client's exact audience wording is preserved verbatim** wherever the audience
  is named — never paraphrased (AF-FBAD-AUDIENCE-WORDING).

## 3. CRAFT NOTES

- Distinct angles — no two lines that are the same idea reworded (the Devil's Advocate
  checks this at the package gate).
- Plain-reader clarity: a stranger gets it in one read.
- No emoji in overlays (emoji live in the body, SOP-FBAD-04).

---

## 4. INDEPENDENT QC (Gate A — The Words)

The overlays are graded with the bodies (04) and headlines (05) by an **independent**
Ad Quality Reviewer (a different critic than the copywriter): rules-followed, on-mission,
audience-wording kept, hook strength, persuasion craft, variety, plain-reader clarity.
Pass = 8.5+ with no category < 7 (AF-FBAD-COPY-QC) AND independent (AF-FBAD-QC-INDEPENDENCE).
Below the line, redo only the failing lines (2-redo budget) — never the good ones.

---

## 5. ATTESTATION APPEND (replaces any prose "do not skip")

`working/s1-overlays.md` — the 70 numbered lines (what the owner sees at pick-10).
`working/checkpoints/s1-receipt.json` — the machine proof the foreman reads:
```json
{
  "overlay_count": 70,
  "word_counts": [6, 5, 7, "... one integer per line, all 3..19 ..."],
  "top_line_present": true,
  "on_mission": true,
  "audience_wording_preserved": true
}
```
`_chk_overlay_count` / `_chk_overlay_wordcount` / `_chk_overlay_topline` /
`_chk_on_mission` / `_chk_audience_wording` validate this receipt. A wrong count, an
over-long line, a missing top line, off-mission copy, or paraphrased audience wording
HARD-FAILS S1 — the card never reaches the pick-10 pause.
