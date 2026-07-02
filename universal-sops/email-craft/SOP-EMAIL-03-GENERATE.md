# SOP-EMAIL-03: GENERATE CORPUS-FAITHFUL COPY

**Cluster:** Email-Craft Rules (`universal-sops/email-craft/`)
**Master authority:** `EMAIL-PIPELINE-MANIFEST.json` + `MASTER-EMAIL-QC-AUTOFAIL-RULESET.md`
**Owning role:** Conversion Copywriter (Marketing)
**Stage:** P2-GENERATE
**Produces:** `working/copy/emails.json`
**Gates this stage satisfies:** AF-EMAIL-FRAMEWORK-INCOMPLETE (and pre-satisfies the full P3 battery)

---

## 0. WHY THIS SOP EXISTS

Copy is authored to the SELECTED structure, in the founder's brand voice, at the correct sequence position — and it is authored to PASS the floor prover on the first try. Writing to the bands is cheaper than bouncing.

## 1. WRITE EACH EMAIL AGAINST ITS STRUCTURE BEATS

Open the selected framework's `.md` in `50-email-engine/email-library/frameworks/` and hit every declared beat. Where a framework declares a part count, a supplied `sections[]` must match it exactly (PASTOR = 6, Million Dollar Sales = 12) or QC raises AF-EMAIL-FRAMEWORK-INCOMPLETE.

## 2. HIT THE SACRED BANDS AS YOU WRITE

- **Body:** 150-300 words; the 3-B Plan is < 150. If the owner asked for an exact length, set `word_band_override: [lo, hi]` on that email (a logged client-exact override wins).
- **Subjects:** exactly 2 (A/B), both non-empty. The second is the more prolific / disruptive variant.
  - Convert&Flow: 8-12 words, `{{contact.first_name}}` inside the first 40 chars, NO pricing tokens.
  - High-ticket: 80-87 rendered chars, exactly ONE purposeful emoji, first name present.
- **Previews:** the sequence-declared count (Convert&Flow master = 1, high-ticket = 2). Preview complements, never repeats, the subject.
- **CTAs:** >= 1 per email; landing-page E1-E3 require >= 3 (near the start, a natural middle, near the end).
- **Format:** double line breaks between paragraphs; never > 3 sentences without a break; <= 4 emoji in the body; each CTA and each list item on its own line.
- **Signature:** the founder's ACTUAL name closes every email. No `[Founder Name]` / `{{founder}}` placeholder.
- **High-ticket only:** each email carries >= 1 disruptive element (`disruptive_elements: [...]`).
- **Persona style:** adopt the tone ONLY. NEVER name or quote the person.

## 3. SEQUENCE HARMONY

In a sequence, each email after E1 references / harmonizes with the prior ones and advances the arc. Do not repeat a persona style within a high-ticket campaign.

## 4. WRITE THE LEDGER

Emit `working/copy/emails.json` as the sequence ledger: `sequence_type`, `sequence_id`, `founder_name`, and `emails[]` with `e_slot`, `framework`, `objective`, `buyer_type`, `subjects[2]`, `previews`, `body`, `ctas[]` (+ `disruptive_elements` for high-ticket). For a single email, emit the email object directly. Hand to P3-QC.
