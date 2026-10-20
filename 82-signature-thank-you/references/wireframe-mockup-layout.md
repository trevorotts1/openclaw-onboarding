# Wireframe and mockup layout — the thank-you page

**Scope:** the picture layout of the terminal thank-you page (page role `thank_you`) for the
wireframe and mockup stages. Skill 71 draws the pictures; this document and its machine twin
`71-blackceo-signature-page/references/copy-specs/thank-you-v1.json` say what is on the page.
`references/layout-and-copy-profiles.md` stays the contract for the page's truth (honest
status, purchase records, access, billing); this file never changes it.

**Status: PROPOSED, pending Trevor's approval.** The owner supplied no precise thank-you
layout (`layout-and-copy-profiles.md`, preamble). The five sections below merge Skill 82's own
order of parts with the thank-you bands in Skill 49 (`structure/funnel_structure.json`,
`thank_you`): a welcome, 4 to 6 numbered next steps, a signed close of up to 170 characters, no
offer button, exactly one celebration image. Change the JSON twin, not the code, when Trevor
changes the layout; the test `tests/test_wireframe_mockup_layout.py` fails if this file and the
twin drift apart.

## 1. The five sections (structure only)

| # | Section | Skill 82 part it draws | Image | Buttons |
|---|---|---|---|---|
| 1 | Confirmation and welcome | header: status label and headline, reassurance, primary action, order reference | the page's one celebration image (`TY-IMG-01`) | the primary access button (filled, primary colour) |
| 2 | Order summary | order summary table, billing column, totals | none | none |
| 3 | Access | one access block per purchased item | none (an icon per card) | one utility button per card |
| 4 | What happens next | what happens next | none | none |
| 5 | Help, manage and close | support path, manage purchase, signed close | none | one filled support button; manage purchase is a secondary outlined button |

No section is an offer, a pitch or a persuasion band; no button is an offer button (Skill 82
no-pitch policy). The whole page carries one image.

## 2. Desktop layout (1440 px page, 1200 px content column)

```
+--------------------------------------------------------------------------+
| 1  CONFIRMATION AND WELCOME            hero ground                       |
|    [ CONFIRMED ]  status chip                     +-------------------+   |
|    H1  You are all set. Welcome to ...           |  celebration      |   |
|    one reassurance line                          |  image plate      |   |
|    [ START HERE: item ]  filled primary          |  (treatment per   |   |
|    ORDER REFERENCE: ...  small tracked capitals  |   composition)    |   |
+--------------------------------------------------------------------------+
| 2  ORDER SUMMARY                       light ground                      |
|    Item          | Status        | Billing         | Amount              |
|    ------------------------------------------------------------------    |
|    Item A        | [Paid]        | One-time charge | 497.00              |
|    Item B        | [Pending]     | Recurring ...   | 47.00               |
|    Total paid                                         497.00             |
|    Pending (not yet confirmed)                         47.00             |
+--------------------------------------------------------------------------+
| 3  ACCESS                              dark ground                       |
|    +-------------+  +-------------+  +-------------+                     |
|    | icon        |  | icon        |  | icon        |   one card per      |
|    | Item A      |  | Item B      |  | Item C      |   purchased item    |
|    | unlocks ... |  | unlocks ... |  | unlocks ... |                     |
|    | [ ACCESS ]  |  | [ DOWNLOAD ]|  | [ SCHEDULE ]|                     |
|    +-------------+  +-------------+  +-------------+                     |
+--------------------------------------------------------------------------+
| 4  WHAT HAPPENS NEXT                   light ground                      |
|    (1)-----(2)-----(3)-----(4)-----(5)   4 to 6 badges, dotted line      |
|    verb-led labels under each badge                                      |
+--------------------------------------------------------------------------+
| 5  HELP, MANAGE AND CLOSE              hero ground                       |
|    Support heading + line            |   signed note of thanks           |
|    [ CONTACT SUPPORT ] [ manage ]    |   script signature                |
+--------------------------------------------------------------------------+
```

## 3. Mobile layout (390 px, 342 px content column, single-column phone stack)

1. Status chip, headline, reassurance line, primary access button (full width), order reference;
   the celebration image plate sits where the composition contract places it.
2. The order table becomes stacked item cards (name, status chip, billing line, amount); the
   Total paid card comes last at full width.
3. Access cards stack one per row, each with a full-width utility button.
4. The steps stack in one column with the dotted line running down the left through the number
   badges.
5. Signed note and script signature, then the filled support button and the outlined
   manage-purchase button, both full width.

## 4. Type, status and image rules

- **Type scale** (house default, `71-blackceo-signature-page/references/wireframe-build-spec.json`):
  H1 56-72 px desktop and 36-44 px mobile; section heading 48-64 and 34-48; subhead 22-32 and
  20-24; body 18-20; button 18-20; microcopy 12-14 and 16-18. A section's own `type_specs`
  (the run's font map) replaces it.
- **Status labels** are words first: `Paid`, `Pending`, `Failed` (Skill 82 states `Action
  needed`, `Refunded` and the rest the same way). In the wireframe and mockup they are drawn as
  chips in the client's brand colours only: paid filled in the primary colour, pending outlined,
  failed in the darkest brand colour. Colour is only ever a second cue.
- **The one image** (`TY-IMG-01`): a warm celebration of the decision, never a product pitch and
  never a recognisable face drawn as a placeholder. Design style A: a rectangle with square
  corners. Style B: a 1:1 circle delivered as a PNG with transparent corners. Style C: a
  rectangle (the circle accents belong to personal pictures, and this image is not one).
  The built page places it with `render_thank_you.py` (`brand.hero_image`, filled by
  `hero_image_from_map` from the run's `image-map-upload/image-map.json`), so the page matches
  the mockup.

## 5. Trevor's visual rules apply here unchanged

These are enforced by the same Skill 71 code that draws a landing page, not restated per page:

- client brand colours only (the run's resolved palette; no example sheet's colours);
- the page's Design Board first (`page_role: thank_you`; the client approves it before the
  mockup), required icon row included;
- annotated build-spec wireframes styled on the Drive examples: numbered section chips, type
  specs, labelled image plates, filled buttons, never grey line work;
- design style A, B or C chosen by the client, with circle photos as transparent-corner PNGs;
- composition variety (each section carries a composition role; the hero takes the hero
  treatments);
- the hypersaturated colour grade, built from the client's own palette;
- the style reference gives **sheet grammar only** (chips, labels, plates, bands): its sections,
  words and layout are never copied;
- desktop and mobile for every stage, one long top-to-bottom PDF per stage, and the overview
  boards.

## 6. How a person gets these pictures

Ask for "a thank-you page" and the route is: Skill 49 dispatch stamps `copy_profile`
`thank-you` on the thank_you page request, the launch adapter runs Skill 71's
`shared_page_service.py --page-version thank-you`, whose pipeline command
`scripts/run_page_role_stages.py` runs the one request builder and the one executor for the
desktop wireframe, mobile wireframe and the mockup (stub provider unless the operator adds
`--provider kie --allow-paid`). The Design Board and final mockups follow after the client
approves the board. Free check, no provider call:

```
python3 71-blackceo-signature-page/scripts/stage_executor.py <run_dir> --preflight --stages desktop-wireframe
```

prints `PREFLIGHT_SECTIONS ... page_role=thank_you sections=5` and, per slice,
`PREFLIGHT_BLOCKS` naming the blocks the prompt carries (including `PAGE TYPE STRUCTURE`).
