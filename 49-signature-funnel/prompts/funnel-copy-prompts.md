# Signature Funnel — BAKED copy + image prompts (provider-agnostic)

> These prompts are **baked into the skill** so the pipeline needs no Airtable/n8n/cloud prompt store at
> runtime. They are **provider-agnostic**: the runtime picks the **client's OWN strongest configured
> model** for authoring (never Anthropic, never the operator's keys — see MASTERDOC §7). Every prompt
> instructs the writer to emit JSON that conforms to the copy/prompt ledger shape the fail-closed
> provers enforce (`prove_sf_copy.py`, `prove_sf_prompt_floor.py`). The SACRED bands here are copied
> from MASTERDOC and are non-negotiable — a violation is a hard AF-FUN-* autofail, not a suggestion.
>
> Shared preamble (prepend to every copy prompt): *"You are a prolific expert direct-response
> copywriter embodying the client's stated voice from the locked brief. Write for CONVERSION. Respect
> every character/word band EXACTLY — **Write to the TOP of every band; under-length is as much a
> failure as over-length.** A band has a floor and a ceiling: you are forbidden from falling below the
> minimum just as you are forbidden from exceeding the maximum. Use the offer title verbatim where
> required. Return ONLY the JSON object described, no prose around it."*

### PERSONA TASK-MODE SEAM (FIX-XC-02a — prepend AFTER the shared preamble)

The copywriter-persona Step-0 grounding (SOP-FUNNEL-02-COPY §2 Step 0) resolves the matched copy persona
via `persona-selector-v2.py` and logs it to `persona-selection-log.md`. Its **Section 4 "Agent Governance
Framework"** is injected here so the writer builds TO the persona's Task Mode, not merely names it:

> `{{PERSONA_TASK_MODE}}` — verbatim Section-4 Execution Standard + Decision Logic + Definition of Done +
> Failure Patterns from the matched `persona-blueprint.md` (persona id `{{SELECTED_PERSONA_ID}}`).
> Ground every headline, offer, and CTA in this Task Mode, INSIDE the three-constraint envelope
> (brand-voice-lock + locked brief + compliance). The persona's NAME alone does not load it.

`{{SELECTED_PERSONA_ID}}` is read from `persona-selection-log.md`; if the log is absent or names no
registered slug, `prove_sf_intake.py` fails closed (**AF-FUN-INTAKE-PERSONA-LOG**) and generation never
starts — the seam is never rendered ungrounded.

---

## PROMPT 1 — MAIN PAGE (the 12-section Hero)

Author all 12 sections at once for the main page from the locked `brief.json`. Obey the Harmony Chain,
the Pain Ladder (Sec 2 circumstantial / Sec 3 private / Sec 4 witnessed — three DIFFERENT pains, 2nd
person, present tense, never a question), the Benefit Ladder (Sec 8 felt / Sec 9 measured / Sec 10
become), and One CTA Voice (a single first-person possession-verb CTA phrase, labeled `CTA: <phrase>`).

SACRED bands (measured on stripped text):
- Sec 1 (The Big Bold Claim): **180–225 chars**, the product title present, labeled CTA. ONE promise.
- Sec 2/3/4 (The Big Bold Pain 1/2/3): **180–225 chars** each, 2nd person, NO "?", labeled CTA.
- Sec 5 (The Big Bold Why): **18–30 words** (write to the top), starts "That's the reason why…", motivational CTA.
- Sec 6 (The Big Bold Who): **18–30 words** (write to the top), **3–6 personas**, **NO CTA**.
- Sec 7 (The Big Bold What): **70–120 words**, **5–10 bullets**.
- Sec 8/9 (Benefit 1/2): **18–30 words** (write to the top), **NO CTA button**.
- Sec 10 (Benefit 3): **18–30 words** (write to the top), carries the **inspirational CTA button**.
- Sec 11 (The Big How To): **100–150 words**, **NO CTA button**, **5–10 steps (ideal 7)**; steps 1–6
  **89–116 chars** each; step 7 **≤170 chars**; MUST include a share, an email-bonus, a founder-text,
  and a community step; the final step is the in-copy CTA.
- Sec 12 (The Big Bold Heartfelt Message): **100–150 words**, **6 labeled parts**; part 2 (The Big
  Struggle) starts "I used to be just like you…".

Output JSON: `{"page_type":"main","sections":[{"section":1,"name":"The Big Bold Claim","copy":"…","cta":"CTA: …"}, …,
{"section":6,"personas":["…"]}, {"section":7,"copy":"…","bullets":["…"]},
{"section":10,"copy":"…","has_cta_button":true,"cta":"CTA: …"},
{"section":11,"steps":[{"text":"…","kind":"share"},{"text":"…","kind":"email_bonus"},{"text":"…","kind":"founder_text"},{"text":"…","kind":"community"}, …]},
{"section":12,"parts":[{"label":"The Big Bold Heartfelt Message","text":"…"},{"label":"The Big Struggle","text":"I used to be just like you…"}, …6 parts…]}]}`

---

## PROMPT 2 — UPSELL PAGE (OTO1)

Same sacred Sections 1–7 (same names, same bands, CTA every section, true scarcity + FOMO only, no
fabricated urgency). **Exclude the original Sections 8–11 and the founder letter.** Add the replacement
**Section 8 = "7 Reasons To Commit To Your ____ Future"** (blank = an identity-charged on-brand phrase):
exactly **7** numbered reasons escalating practical → identity; reason 7 lands the CTA. Section 1 uses
the **momentum frame** (confirm the buy, then extend it — never restart the sale).

Output JSON: `{"page_type":"upsell","sections":[ {sections 1–7 as above}, {"section":8,"name":"7 Reasons To Commit To Your <Fill> Future","items":["Reason 1: …", …7 total…],"cta":"CTA: …"} ]}`

---

## PROMPT 3 — DOWNSELL PAGE (OTO1-decline)

Same exclusions. Section 1 uses the **graceful-concession frame** (honor the no, then reduce the
barrier: smaller/lighter/staged). Replacement **Section 8 = "When Time Runs Out"**: exactly **7** things
they'll miss (final/one-time value), loss-framed with dignity. CTA every section.

Output JSON: `{"page_type":"downsell","sections":[ {sections 1–7}, {"section":8,"name":"When Time Runs Out","items":["…", …7 total…],"cta":"CTA: …"} ]}`

---

## PROMPT 4 — UPSELL 2 (OTO2)

Same sacred derivation. Section 8 = **"7 Reasons To Commit To Your ____ Future"** with a blank-fill that
MUST differ from OTO1. The offer is **categorically different in KIND** from OTO1 (not "more of the
same, bigger"). Section 1 is **journey-neutral** — anchored on the ORIGINAL purchase (seen by accepters
AND decliners). Use the **final-door frame** ("this is the last page where this exists").

Output JSON: `{"page_type":"upsell-2","sections":[ {sections 1–7}, {"section":8,"name":"7 Reasons To Commit To Your <DifferentFill> Future","items":[…7…],"cta":"CTA: …"} ]}`

---

## PROMPT 5 — DOWNSELL 2 (OTO2-decline)

Section 8 = **"When Time Runs Out"** — 7 **final-door** misses (the last price / bonus / seat / moment).
The **dignity close**: they've said no twice; Section 1 offers the smallest true yes (starter tier,
split-pay, single seat, recording-only). **After this page the funnel NEVER pitches again.**

Output JSON: `{"page_type":"downsell-2","sections":[ {sections 1–7}, {"section":8,"name":"When Time Runs Out","items":[…7…],"cta":"CTA: …"} ]}`

---

## PROMPT 6 — THANK-YOU PAGE

Three labeled parts, celebratory, zero selling. **NO offer CTAs** — utility buttons only
(`Join The Community`, `Share With A Friend`, `Add To Calendar`). One image maximum. Truth gate at full
strength (only promise what Q16 confirmed real).
- **TY-1 "The Big Bold Welcome":** **120–180 chars**, name the product title, second person.
- **TY-2 "What Happens Next":** **4–6 steps, each 89–116 chars**, momentum-ordered (email bonus →
  founder text → community → share-a-friend); every step starts with a verb + names its payoff.
- **TY-3 "The Big Empowering Close":** **≤170 chars**, destiny register, signed by the founder.

Output JSON: `{"page_type":"thank-you","buttons":["Join The Community","Share With A Friend"],"sections":[{"section":"TY-1","copy":"…"},{"section":"TY-2","steps":["…", …4–6…]},{"section":"TY-3","copy":"…"}]}`

---

## PROMPT 7 — IMAGE PROMPT (per section; the 5,000–19,000-char builder)

For each section that carries an image, build ONE natural-language `gpt-image-2` prompt of
**5,000–19,000 characters** (no Midjourney syntax, **no em dashes**). Use the 8-block build order and
resolve every spintax choice from the locked brief (representation honored EXACTLY, brand colors named
as plain color words):

1. **Subject & Wardrobe** · 2. **Composition & Shot** · 3. **Typography** *(text-bearing sections only;
dominant for Sec 11 — the exact words in quotes, spelling-locked letter for letter)* · 4. **Signature
Grade Block** *(embed the ~1,290-char canonical constant from MASTERDOC §4 VERBATIM)* · 5. **Lighting**
· 6. **Quality & Render** · 7. **Facial Intelligence** *(deep skin tones rich and dimensional, never
ashy or grey; melanin-true lighting)* · 8. **Brand-Style + Negative Block** *(final paragraph, imperative
"Do not …" negatives)*.

Aspect ratios: all 16:9 except **Sec 12 → 3:4** (aspect_ratio is an API parameter, never prompt text).
Non-text sections must state "No text, no letters, no words anywhere in the image." Reference-image hook
defaults to `mode: none` (pure text-to-image); when populated, append the style-only guard.

**OPTIONAL — Brand-Style block 8 from a design style card (FIX-XC-02c):** when the intake carries a
`style_card_id` (a registered Skill 45 `FN-…` card, Q18), resolve it via DIU Workflow B and embed the
card's **LONG tier** VERBATIM as the Brand-Style portion of **block 8**, ahead of the always-on negative
directives. The Signature Grade Block (block 4) is unchanged. Unset `style_card_id` = current behavior
(brand colors carry the look; block 8 is the default Brand-Style + Negative paragraph).

**Aspect-ratio pass-through (FIX-IMG-03):** each prompt-ledger record's `aspect_ratio` is carried
VERBATIM into its `prompts.json` entry — the Skill 6 rail's `kie_generate.py` reads
`slide.get("aspect_ratio", …)`, so **Sec 12's 3:4 (and any per-section ratio) is honored** at generation
instead of silently defaulting to 16:9.

Output JSON per prompt: `{"page_type":"…","section":N,"aspect_ratio":"16:9","text_bearing":false,"prompt":"…5,000–19,000 chars…"}`
(for Sec 11: `"text_bearing":true,"words":["DECIDE","COMMIT","RISE"]`; Sec 12: `"aspect_ratio":"3:4"`).

Then generation is DELEGATED to Skill 47 `kie_image.py`; media folder + upload and the GHL build are
DELEGATED to Skill 6. This skill never hand-rolls a Kie call or a GHL REST call (the entry shell's
bypass-scan refuses it).
