# SOP-FBAD-04: WRITE THE 10 PRIMARY-TEXT BODIES

**Cluster:** FB/IG Ad-Craft Rules
**Master authority:** `AD-PIPELINE-MANIFEST.json` + `MASTER-AD-QC-AUTOFAIL-RULESET.md` (Gate A)
**Owning role:** Direct-Response Ad Copywriter
**Stage:** S2-PRIMARY-TEXT — `depends_on: [PICK-10]` (runs in parallel with S3 + S4)
**Produces:** `working/s2-primary-text.md` + `working/checkpoints/s2-receipt.json`
**Author-hats (PINNED):** Robert Bly (*The Copywriter's Handbook*, lead) + Joanna Wiebe (*Copy Hackers*) + Donald Miller (*Building a StoryBrand*) + Alex Hormozi (*$100M Leads*)
**Gates:** AF-FBAD-BODY-HOOK, AF-FBAD-BODY-CTA, AF-FBAD-BODY-EMOJI (+ Gate A AF-FBAD-COPY-QC)

---

## 0. WHY THIS SOP EXISTS

The primary text is the long copy under the image. The first 125 characters decide
whether anyone reads the rest (everything after that is hidden behind "See more").
One body per chosen overlay, 1:1.

## 1. THE STRUCTURE OF ONE BODY (350–450 words)

1. **The 125-character hook** (Bly's "the lead is 80% of the ad" + Wiebe's voice-of-
   customer): the single most arresting line, ≤ 125 characters, that earns the click on
   "See more" (AF-FBAD-BODY-HOOK).
2. **The story** (Miller's StoryBrand): the audience is the hero, the show/guest is the
   guide; name the problem, the stakes, the transformation — in the client's audience
   wording.
3. **The proof + rising intensity** (Hormozi's $100M Leads): stack specific, believable
   reasons; escalate, don't plateau.
4. **Exactly 3 calls-to-action** woven through (not three identical buttons — three
   distinct nudges to the same destination) (AF-FBAD-BODY-CTA).

## 2. THE LOCKED WORD + EMOJI RULES (auto-failed)

- **Hook ≤ 125 characters** (AF-FBAD-BODY-HOOK).
- **Exactly 3 CTAs** per body (AF-FBAD-BODY-CTA).
- **Emoji count within the locked band (1–12)** — emoji are a controlled scannability
  device (section breaks, bullet markers), never decoration; over- or under-use both
  fail (AF-FBAD-BODY-EMOJI).
- Stay on-mission (feature the guest/show) and keep the audience wording — carried from
  S1's discipline.

## 3. CRAFT NOTES

- Plain words. Short sentences. One idea per line.
- The 3 CTAs rise in commitment: soft ("see who's been on"), medium ("here's how it
  works"), hard ("apply / book your spot").

---

## 4. INDEPENDENT QC (Gate A — The Words)

Graded with the overlays (02) and headlines (05) by the independent Ad Quality Reviewer.
Pass = 8.5+ no category < 7 (AF-FBAD-COPY-QC) AND independent (AF-FBAD-QC-INDEPENDENCE).
Below the line → redo only the failing bodies (2-redo budget).

---

## 5. ATTESTATION APPEND (replaces any prose "do not skip")

`working/s2-primary-text.md` — the 10 bodies, numbered to match the chosen overlays.
`working/checkpoints/s2-receipt.json`:
```json
{
  "body_count": 10,
  "bodies": [
    { "hook_chars": 118, "cta_count": 3, "emoji_count": 4 },
    "... one object per body ..."
  ]
}
```
`_chk_body_hook` / `_chk_body_cta` / `_chk_body_emoji` validate this receipt. A hook
over 125 chars, a body without exactly 3 CTAs, or an emoji count out of band HARD-FAILS
S2.
