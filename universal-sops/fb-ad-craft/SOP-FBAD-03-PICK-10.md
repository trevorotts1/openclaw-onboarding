# SOP-FBAD-03: PICK YOUR TOP 10 (the first human pause)

**Cluster:** FB/IG Ad-Craft Rules
**Master authority:** `AD-PIPELINE-MANIFEST.json` + `MASTER-AD-QC-AUTOFAIL-RULESET.md`
**Owning role:** Facebook & Instagram Ad-Run Producer
**Stage:** PICK-10 — `depends_on: [S1-OVERLAYS]` — **HUMAN GATE (non-skippable)**
**Produces:** `working/s1-selection.json`
**Gates:** AF-FBAD-SELECTION-COUNT, AF-FBAD-SELECTION-SUBSET
**Capture helper:** `48-facebook-ad-generator/scripts/ad_selection.py`

---

## 0. WHY THIS SOP EXISTS

This is one of only TWO places a human is needed, and it can NEVER be skipped — no
owner-authorized skip and no `--adhoc` relaxes it (the foreman enforces this). The
owner chooses which 10 of the 70 overlays become real ads; everything downstream
fans out 1:1 from this choice.

## 1. THE FLOW

1. S1 attests; the card moves to **Review**. The 70 overlays are attached
   (deliverables) and the owner is pinged in Telegram with the numbered list 1–70.
2. The owner replies `PICK: 3,7,12,…` (ten numbers).
3. The capture helper:
   - parses the numbers,
   - **checks the count** is exactly the locked 10 (AF-FBAD-SELECTION-COUNT),
   - **de-duplicates** (a repeated number is collapsed, not counted twice),
   - **checks the range** — every pick is a real 1..70 index (AF-FBAD-SELECTION-SUBSET),
   - **echoes the 10 chosen lines back** to the owner to confirm,
   - writes the choice **once**. A second reply **replaces** the first (never adds).
4. Only then does the producer call `POST /api/ad-campaigns/{id}/resume`, which PATCHes
   S2, S3, and S4 to `in_progress` — they start **at the same time**.

## 2. ERROR HANDLING (no silent acceptance)

- Wrong count (e.g. 9 or 11) → reject, tell the owner the exact count needed, wait.
- A number out of 1..70 → reject, name the bad number, wait.
- Duplicates → collapse and re-echo the de-duplicated 10 for confirmation.
- The downstream stages WAIT. They are blocked by the foreman's dependency gate until
  this selection is saved and valid.

---

## 3. ATTESTATION APPEND (replaces any prose "do not skip")

`working/s1-selection.json`:
```json
{ "selection": [3, 7, 12, 18, 22, 31, 40, 55, 61, 68], "overlay_count": 70 }
```
`_chk_selection_count` requires exactly 10 distinct picks; `_chk_selection_subset`
requires every pick to be a real in-range index. Because PICK-10 is a HUMAN GATE, the
foreman validates this receipt even under `--adhoc` — the human's decision is never
bypassed.
