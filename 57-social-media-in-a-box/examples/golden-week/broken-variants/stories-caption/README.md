# broken-variant: stories-caption (C7)

Closes the C7 coverage gap for the FB/IG Stories captions fold. This is the
authentic golden reformat record with an added `storiesCaption` of **290 chars**
(over the 250-char `stories_caption` band). Instagram hashtags (7, in the 5–15
band), LinkedIn hashtags (exactly 3) and both `followUpComment` fields stay
in-band, so **only the Stories caption band trips**.

- **Prover:** `scripts/prove_bands.py stories-caption/reformat.json`
- **Blocked at:** P3-CONTRACT
- **Exit:** 2
- **Code:** `AF-SM-STORIES-CAPTION`
- **Certificate issued:** false · **Publisher ran:** false

`verify.sh` step 4 executes this variant for real and asserts the exact exit
code + code. The source fixture stays byte-for-byte read-only.
