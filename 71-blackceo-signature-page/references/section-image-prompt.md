# Section image prompt — wireframe template and mockup template

Two templates, one per image family: **WIREFRAME SECTION** for the
`desktop-wireframe` and `mobile-tablet` stages, **MOCKUP SECTION** for the
`visual-mockup` layout proof and the `final-mockups` client-judged mockup.
Fill every block from the run, in the order given; the order is the
anatomy and is not rearranged. Never invent copy, numbers, or labels.

The stage purpose arrives in the worker brief as `{{purpose}}`. It is a
constraint, not background: read it before the first block.

Source order for every filled field:

1. `references/qc-contract.md`, "Visual standard set traits" (sections B,
   wireframe canon; C, mockup canon; E, section order; F, discriminators).
2. The run's `section-plan.json` (section number, name, position, slots).
3. The run's copy (verbatim), `font-action-plan/font-map.json` (type
   tokens), and `visual-mockup/page-visual-bible.json` (style input).
4. `assets/visual-standards/README.md` for the target sheet's density and
   finish.

## The 12-section skeleton

Every page is one of these two orders. A section slice must print its own
number and name once, in the position below.

| # | Section | Purpose the slice proves | Default slots (ratio, art direction) |
|---|---|---|---|
| 1 | Claim | The promise, before any explanation | Eyebrow; two-tone H1; subhead; CTA button + microcopy; hero image (16:9 desktop, 2:3 mobile) — editorial aspiration, never a defeated stereotype |
| 2 | Pain 1 | Name the first cost | Number tag; H2 two-tone; body; gray objection card ("This feels familiar:"); pain photo (1:1 or 4:5) — stressed but dignified, never a stereotype |
| 2A | Solution 1 (long-form only) | Answer pain 1 in place | Label; body; optional proof image (4:5) — quiet everyday luxury |
| 3 | Pain 2 | Name the second cost | Same slots as 2 |
| 3A | Solution 2 (long-form only) | Answer pain 2 in place | Same slots as 2A |
| 4 | Pain 3 | Name the third cost | Same slots as 2 |
| 4A | Solution 3 (long-form only) | Answer pain 3 in place | Same slots as 2A |
| 5 | Why | Recognition, reason, invitation | 5A Recognition & Reason; 5B Commitment; 5C Invitation; one photo (3:4); script signature on the founder-adjacent beat |
| 6 | Who | Make the reader recognizable | Persona cards ("AND IT'S ALSO FOR YOU IF…", "NOT FOR YOU IF…"); checkmarks in tinted black circles; optional side card |
| 7 | What | Name what is included | White icon cards on a dark band, black icons (six desktop, four mobile); card grid 3 or 6 |
| 8 | Benefit 1 | Return the outcome | Checkmark row; benefit photo (16:9); ratio label |
| 9 | Benefit 2 | Return the outcome | Same slots as 8 |
| 10 | Benefit 3 | Return the outcome | Same slots as 8 |
| 11 | How-To | Show the path | Exactly **7** numbered steps; red circles + chevrons/dotted line on dark (desktop), vertical black-circle timeline (mobile); every badge 1–7 once |
| 12 | Founder letter | Close on the person | Portrait (3:4, back-view or silhouette allowed); letter in six beats; script signature; caps name and title; gray sidebar + final CTA |

Header band, then sections in order, then the closing CTA panel and footer.
Long-form adds 2A/3A/4A only; the numbered sections never renumber.

## Palette tokens

**Wireframe — photo-wireframe dialect.** Grayscale with exactly one red.
Ink `#111111` and `#242424`; paper `#ffffff`; band gray `#f6f6f6`; rule
gray `#e8e8e8`; signal red one of `#c8091a`, `#d90110`, `#ca0a19`,
`#d40213` — pick one and use it everywhere. Full-bleed white/black bands
alternate; photos are darkened black-and-white with thin red edge bars.

**Wireframe — grayscale dialect.** No saturated pixels. `#f6f6f6` band,
`#ffffff` paper, `#e8e8e8` rule, `#242424` ink; 15 alternating content
bands between the meta bar and the footer.

**Mockup — Tier H (flat, sparse).** Cream `#f7f2e9`, ivory `#fffdf9`,
green `#28513f`, blush `#f0dedb`, rose `#93504f`, brick `#bc5248` as the
dominant shares; gold `#c49a45` and `#e2c98f` rules and caption accents
only; tan caption bar `#e2cdba`; note box `#eee6db`; ink `#02120f`.

**Mockup — Tier R (layered, photo-dense).** Rust `#a2362d`, `#a93831`,
`#a94335`, `#a34133`; deep green `#172a1d`, `#193e2a`, `#0c3d32`; cream
`#f9f5ef`, `#f3e0d4`; canvas `#faf6ef`; ink `#02120f`. Brick and rust
replace the wireframe signal red; never reuse wireframe red in a mockup.

## Type tokens

| Token | Wireframe | Mockup |
|---|---|---|
| Source | `font-action-plan/font-map.json` | same, plus the page visual bible |
| Headline | Condensed heavy all-caps sans; H1 56–72 px, H2 48–64 px desktop, 34–48 px mobile | Two-tone statement-turn headline (black then red, white then red on dark), Title Case, same faces as the bible |
| Subhead | 28–36 px | Bible subhead scale, tracked caps eyebrow above |
| Body | Plain sans, 18–20 px desktop, 15–17 px mobile | Serif body in Tier R, sans in Tier H; 18–20 px desktop, 15–17 px mobile |
| CTA | 18–20 px, first-person outcome label | Same label, solid button, arrow glyph |
| Microcopy | 12–14 px desktop, 12–13 px mobile | Small caps or gray sans, directly under the button |
| Accents | Red number box, gray/dark tab | Gold script overlay and signature; caps founder name and title |

Density target: wireframe is an annotation-dense build spec — every slice
prints its number and name, type specs, slot labels with ratio and art
direction, the run's real copy, CTA chip and microcopy spec, and behavior
notes. Mockup density follows the tier: Tier R ~9 portraits per frame;
Tier H sparse, one photo per planned band at most.

Native aspect: desktop page 1440 px, content 1200 px; mobile 390 CSS px
page, 342 px content, 2x export (780 px wide). Each section slice keeps
its own native height; record the real pixel width and height from the
filed bytes. 3:1, 1:3 and 9:21 are not offered ratios; request the
nearest offered ratio explicitly or record the substitution.

---

## Template 1 — WIREFRAME SECTION

```
SECTION IMAGE PROMPT — WIREFRAME (stage: {{stage}}; mirror: {{purpose}})

1. SECTION NUMBER AND NAME — print exactly once, exactly as the plan
   reads: "{{section_number}} — {{section_name}}". Print no other number
   for this section.

2. SKELETON POSITION — "{{section_number}} of the 12-section sales
   skeleton{{long_form_insert}}", after {{previous_section}} and before
   {{next_section}}. Page order: header, 1, 2, 2A, 3, 3A, 4, 4A, 5,
   6, 7, 8, 9, 10, 11, 12, closing CTA, footer (long-form); header, 1,
   2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, closing CTA, footer (standard).

3. VERBATIM COPY — every word printed in this image, quoted exactly from
   {{copy_source}}:
   {{verbatim_copy}}
   Print these strings and nothing else. Copy is not paraphrased,
   shortened, reordered, expanded, or corrected.

4. HEADER STRIP — one strip across the top of the slice, stating:
   page width {{page_width}} px, content width {{content_width}} px,
   {{page_label}} (desktop 1440/1200; mobile 390/342).

5. TYPE SPECS — print the type spec for every text element beside or
   under it: {{type_specs}}, drawn from {{font_map}} and these tokens:
   {{type_tokens_for_this_slice}}.

6. SLOTS — for every image slot print the slot label, its ratio, and its
   art direction:
   {{slots}}
   Each ratio is one of the planned values; a slot's ratio label is
   printed once and matches the rectangle drawn.

7. BEHAVIOR NOTES — print the behavior note for this slice where it
   governs, not in a legend: {{behavior_notes}} (mobile-specific
   direction prints on the section it governs).

8. STYLE INPUT — apply the page visual bible's style input:
   {{style_input}}. Palette for this slice: {{palette_tokens}}. The slice
   is a designed build spec in the client's brand colors, never a plain
   gray browser render, never an HTML render.

9. STYLE REFERENCE LINE — print verbatim in the prompt:
   Use the attached images only as style reference for color grading, lighting, and composition -- do not copy their subjects, faces, or text.

10. DENSITY TARGET — annotation-dense spec slice: number and name, type
    specs, every slot labeled with ratio and art direction, real copy,
    CTA chip with microcopy spec, behavior notes. Background photos are
    darkened black-and-white with one thin red edge bar.

11. NATIVE ASPECT — this slice at {{native_width}} x {{native_height}} px
    (nearest offered ratio {{native_ratio}}); full page width
    {{page_width}} px, content {{content_width}} px. Record the filed
    bytes' real dimensions.

12. NEGATIVE BLOCK —
    Do not duplicate a section number, do not print the same number
    twice, and do not skip a number (no two "SECTION 3", no "05" twice,
    no "3A" twice, no founder card sequence 01/02/05/04/05/06).
    Do not mis-number the 7 steps or mismatch the step count: exactly
    7 badges, reading 1, 2, 3, 4, 5, 6, 7 once each, and exactly 7 step
    labels (no 6 steps under a 7-step headline, no 1/02/icon/3/4/6/7,
    no 1/2/2/4/5/6/7).
    Do not garble any label or annotation: no "BIGNEFIT", "BTEP 7",
    "DISCIFIONAL", "FREIDOM", "Folow Gnlume Sno Home", "widhh", and no
    invented, dropped, doubled, or substituted characters anywhere.
    Do not print any text that is not in the verbatim copy above; no
    placeholder tokens, no lorem, no bracketed markers, no captions,
    watermarks, or production labels.
```

---

## Template 2 — MOCKUP SECTION

```
SECTION IMAGE PROMPT — MOCKUP (stage: {{stage}}; mirror: {{purpose}})

1. SECTION NUMBER AND NAME — print exactly once, exactly as the plan
   reads: "{{section_number}} — {{section_name}}". Print no other number
   for this section.

2. SKELETON POSITION — "{{section_number}} of the 12-section sales
   skeleton{{long_form_insert}}", after {{previous_section}} and before
   {{next_section}}. Tier: {{tier}} (R layered photo-dense, or H flat
   sparse). The band count and order match the wireframe; only the color,
   photography, and finish change.

3. VERBATIM COPY — every word printed in this image, quoted exactly from
   {{copy_source}}:
   {{verbatim_copy}}
   Print these strings and nothing else; the mockup repeats the approved
   copy, it does not rewrite it.

4. HEADER STRIP — mockup slices carry the page's own header treatment
   instead of an annotation strip: {{header_treatment}} at page width
   {{page_width}} px and content width {{content_width}} px (desktop
   1440/1200; mobile 390/342).

5. TYPE SPECS — {{type_specs}}, drawn from {{font_map}} and these tokens:
   {{type_tokens_for_this_slice}} (two-tone statement-turn headline;
   eyebrow tracked caps; body serif in Tier R, sans in Tier H).

6. SLOTS — for every image slot print the slot's subject, ratio, casting,
   and art direction:
   {{slots}}
   Tier R: ~9 portraits per frame, consistent Black-professional casting,
   hand-chin and upward-gaze poses, jewel and earth blazers, gold hoops,
   golden-hour bokeh; layered, arched, or diagonal shapes that bleed.
   Tier H: sparse square rectangles, photos only where planned; founder
   slot stays the planned portrait or supplied asset.

7. BEHAVIOR NOTES — {{behavior_notes}}; CTA strips keep the first-person
   outcome label and the microcopy line directly under the button.

8. STYLE INPUT — apply `visual-mockup/page-visual-bible.json`:
   {{style_input}}. Palette for this slice: {{palette_tokens}} (Tier R or
   Tier H tokens; never wireframe red). Hue-shifting full-width bands,
   gold hairline rules, leaf or botanical texture only in Tier R.

9. STYLE REFERENCE LINE — print verbatim in the prompt:
   Use the attached images only as style reference for color grading, lighting, and composition -- do not copy their subjects, faces, or text.

10. DENSITY TARGET — Tier R photo-dense (about nine portraits per frame
    where the section is photographic); Tier H sparse, one photo per
    planned band at most. Script overlay on the photo in Tier R; move it
    to the caption bar in Tier H.

11. NATIVE ASPECT — this slice at {{native_width}} x {{native_height}} px
    (nearest offered ratio {{native_ratio}}); full page width
    {{page_width}} px, content {{content_width}} px. Record the real
    width and height from the filed bytes.

12. NEGATIVE BLOCK —
    Do not duplicate a section number, do not print the same number
    twice, and do not skip a number (no two "SECTION 3", no "05" twice,
    no "3A" twice, no founder card sequence 01/02/05/04/05/06).
    Do not mis-number the 7 steps or mismatch the step count: exactly
    7 badges, reading 1, 2, 3, 4, 5, 6, 7 once each, and exactly 7 step
    labels (no 6 steps under a 7-step headline, no 1/02/icon/3/4/6/7,
    no 1/2/2/4/5/6/7).
    Do not garble any label, mug slogan, or caption: no "BIGNEFIT",
    "BTEP 7", "DISCIFIONAL", "FREIDOM", "Folow Gnlume Sno Home",
    "widhh", and no invented, dropped, doubled, or substituted
    characters anywhere.
    Do not print any text that is not in the verbatim copy above; no
    placeholder tokens, no agent notes, no lorem, no bracketed markers,
    no captions, watermarks, or production labels.
```
