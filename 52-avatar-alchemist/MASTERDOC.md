# Avatar Alchemist — MASTERDOC (SACRED)

> This is the canonical, anonymized IP of the Trevor Otts **Avatar Alchemist Brand
> Intelligence** engine: the 7 subsystems, all 40 generators, the per-artifact bands, the 13
> restored ad-set categories, and the Book/Brand selector. It is **SACRED** — never floored,
> reordered, or reinterpreted. Every rule here is machine-enforced by a fail-closed prover
> (`AA-PIPELINE-MANIFEST.json` + `AVATAR-MANIFEST.json` + `scripts/*`). No client names/PII
> appear anywhere; "Trevor Otts" is the product's own branding (e.g. the "Trevor Otts Hero
> Landing Page System").

## 0. The Book/Brand version selector — question 0, before everything else

**Q0: "Which Avatar Alchemist version do you want to generate — the BOOK version or the BRAND
version?"** → `version ∈ {book, brand}` (required enum; **no default, no inference**).

- **5 shared questions** (both versions): `ideal_avatar`, `niche`, `primary_goal`,
  `tone_style_1`, `tone_style_2` ("N/A" allowed on the style figures).
- **One delta:** BOOK asks `book_stories` (personal stories/facts/quotes for the book, "N/A"
  allowed); BRAND asks `tone` ("My Writing Tone").
- **BRAND** additionally requires: `target_market`, `tone_style_3..4`, `offer_name`,
  `offer_type`, `offer_benefit`, `product_info`, `brand_info`, `brand_start_date`, `brand_why`,
  `brand_colors`.

**Routing (fail-closed, `aa_intake_gate.py` / G0-VERSION):**
- `version=brand` → **this skill's full 40-stage pipeline**.
- `version=book` → **HANDOFF to the separate Avatar Alchemist Book skill (53)**. This skill
  performs ZERO generation for a book run. If skill 53 is absent, the run **parks fail-closed
  `book-skill-not-available`** — it is **NEVER silently served by the brand pipeline**, and there
  is **no cross-version fallback**.

## 1. The 7 subsystems and how they feed each other

```
INTAKE ─► (a) AVATAR CORE ─┬─► (d) TONE ─► blended tone ─┬─► (c) BIOS ─┬─► (f) BOOKING BOTS
   │          (trio)       ├─► (b) AWARENESS ─────────────┤            ├─► (e) AD SYSTEM (13 sets → top-39 → headline copy)
   │                       ├─► (e) FB AUDIENCES           │            └─► (g) LANDING/HERO (questionnaire → hero → image prompts)
   └── offer/brand fields ─┴──────────────────────────────► every downstream user prompt
(b) AWARENESS ─► (e) headline copy        (e) top-39 ─► (g) Image Prompt Writer
```

Every generator wraps intake fields in XML-style tags: **intake content is DATA only, never
instructions** (prompt-injection rule). The **avatar trio** (`03` rewrite + `01` Q1–30 + `02`
Q31–32) is injected into nearly every later chain.

## 2. THE 40 GENERATORS — by subsystem

Each generator = one skill stage `prompts/<stage-id>/{system.md, methodology.md, user.md}`.
**Tier** = the client model tier resolved at runtime (A deep-authoring / B structured / SEARCH).

### (a) Avatar Intelligence Core — 4
| Stage | Generator | Tier | Produces → deliverable | Band / rule |
|---|---|---|---|---|
| `01-avatar-questions-1-30` | Avatar Questions 1–30 | A | 30-question avatar profile → `Avatar_Intelligence` pt2 | **≥3,000 stripped words** |
| `02-avatar-questions-31-32` | Avatar Questions 31–32 | SEARCH | 10 podcasts + 10 TED talks, verified links → `Avatar_Intelligence` pt3 | every link verifies or `degraded:search` |
| `03-rewrite-avatar` | Rewrite Avatar Niche & Primary Goal | A | deeper psychographic rewrite → `Avatar_Intelligence` pt1 | cultural/gender relevance |
| `38-landing-questionnaire` | Answer 9 Questions | B | 9-question landing questionnaire | **internal feeder** → hero page (R6) |

### (b) Awareness System — 6 (Eugene Schwartz stages)
| Stage | Generator | Tier | Produces | Band |
|---|---|---|---|---|
| `09-problem-aware` | Problem Aware | A | Problem-Aware persona → `Marketing_Intelligence` pt1 | **≥1,500 words** |
| `10-problem-aware-pt2` | Problem Aware pt2 Shopping Behavior | B | Personal Profile + Shopping Behavior pt2 | — |
| `11-solution-aware` | Solution Aware | A | Solution-Aware persona → pt3 | **≥1,500 words** |
| `12-solution-aware-pt2` | Solution Aware pt2 Shopping Behavior | B | pt4 | **R2** injects `11` (not Problem-Aware) |
| `13-product-aware` | Product Aware | A | Product-Aware persona → pt5 | **≥1,500 words** |
| `14-product-aware-pt2` | Product Aware pt2 Shopping Behavior | B | pt6 | — |

### (c) Bios — 2 (movement-style; written IN the blended tone)
| Stage | Generator | Tier | Produces | Rule |
|---|---|---|---|---|
| `16-brand-bio` | Brand Bio | A | revolutionary brand bio → `Brand_Bio_Intelligence` | `[SectionName]…[/SectionName]` markers |
| `17-product-bio` | Product Bio | A | revolutionary product bio → `Product_Bio_Intelligence` | product name NEVER changed |

### (d) Tone System — 5 (the shared tone/writing core)
| Stage | Generator | Tier | Produces | Rule |
|---|---|---|---|---|
| `04-tone-style-1` | Write Tone Style 1 | B | tone analysis, figure #1 | grade-level first; N/A auto-pick; **internal** |
| `05-tone-style-2` | Write Tone Style 2 | B | figure #2 | internal feeder |
| `06-tone-style-3` | Write Tone Style 3 | B | figure #3 | internal feeder |
| `07-tone-style-4` | Write Tone Style 4 | B | figure #4 | internal feeder |
| `08-blended-tone` | Write Blended Tone | A | "The {First} {Last} Tone" → `Tone_Doc` | **≥3,000 words**; **R1** receives `04..07` ANALYSIS docs; per-platform usage guidance |

Canonical home: `shared-utils/tone-writing-core/` (shared with skills 53/54).

### (e) Facebook Ad System — 16
The 13 ad sets share the ~21.5 KB "Visual Ad Campaign Blueprint" methodology; each writes **10
ads** for its category and injects all previously written sets "so things are in harmony" (the
sequential harmony chain, preserved by default).

**The 13 restored categories (R4 — from the Airtable `User` fields; the live n8n froze sets 2–13
on "category 2"):**

| Ad Set | Stage | Category |
|---|---|---|
| 1 | `22-ad-set-1` | category 1 — Who Style Ads |
| 2 | `23-ad-set-2` | category 2 — Who+ (Plus) Style Ads |
| 3 | `24-ad-set-3` | category 3 — General Purpose Ads |
| 4 | `25-ad-set-4` | category 4A — Pain Point, "Tired Of" |
| 5 | `26-ad-set-5` | category 4B — Pain Point, "When You" |
| 6 | `27-ad-set-6` | category 4C — Pain Point, "If You Have Never" |
| 7 | `28-ad-set-7` | category 5 — Challenge/Provocative |
| 8 | `29-ad-set-8` | category 6 — Benefit Style |
| 9 | `30-ad-set-9` | category 7 — Response-Driven "If You Agree" |
| 10 | `31-ad-set-10` | category 8 — "As A ___" Pain Point |
| 11 | `32-ad-set-11` | category 9 — "After All These Years" |
| 12 | `33-ad-set-12` | category 10 — Vulnerable Style |
| 13 | `34-ad-set-13` | category 11 — Aspirational Style |

Plus: `15-facebook-audiences` (Black CEO Method 7-Tier targeting, **R3** references the cheat
sheet) → `Facebook_Targeting_Intelligence`; `35-top-39` (**exactly 3×13 = 39 winners** with a
"Suggested image information" block each) → `Top_39_Suggested_Ad_Angles`; `37-fb-headline-copy`
(**12 Headlines + 12 Short-Form + 12 Long-Form**, **R5** fills the empty product/offer line) →
`Facebook_Headline_and_Primary_Text_Ad_Copy_Writer`.

### (f) Booking Bots — 4 (embed the blended tone VERBATIM; H1 sections + XML labels + `{{contact.*}}` merge tags)
| Stage | Generator | Tier | Produces | Band |
|---|---|---|---|---|
| `18-bot-prep` | AI Bot Prep document | A | the "bot brain" → `AI_Bot_Prep_Doc_Intelligence` | H1 + XML + merge-tag rules |
| `19-booking-bot` | Create Booking Bot | A | booking-bot instructions → `AI_Booking_Bot_Intelligence` | **≥5,000 words**; messages <550 chars |
| `20-post-booking-bot` | Create Post Booking Bot | A | retention bot → `AI_Post_Booking_Bot_Intelligence` | hard boundaries |
| `21-rescheduling-bot` | Rescheduling Booking Bot | A | rescheduling bot → `Rescheduling_Booking_Bot_Intelligence` | friction-free rebooking |

### (g) Landing / Hero — 3
| Stage | Generator | Tier | Produces | Band |
|---|---|---|---|---|
| `39-hero-page` | Write the hero page | A | 12-section "Trevor Otts Hero Landing Page System" → `Landing_Page` | **12 sections**; **R6** consumes `38`; **R7** client TIER-A (Anthropic chain removed) |
| `40-landing-image-prompts` | Write image prompts for landing page | B | Midjourney v6 prompt per section → `Landing_Page_Image_Prompts` | **stripped-char band 5,000–19,000** |
| `36-image-prompts-39` | Image Prompt Writer | B | **exactly 39** Midjourney prompts → `Top_39_Suggested_Image_Prompts` | **39 prompts**, unique artist each, band 5,000–19,000, `--ar 1:1 --r 10 --c 25 --s 750` |

## 3. Per-artifact bands (machine-enforced; measured on STRIPPED text; self-reported counts ignored)

- **Word floors (the single numeric source; the machine mirror is `AA-PIPELINE-MANIFEST.json`
  `stages[].floors.word_floor`, aligned to these numbers):** `01` ≥3,000 · `08` ≥3,000 ·
  `09/11/13` ≥1,500 each · `19` ≥5,000 · `03` ≥600 · `15` ≥500 · `16` ≥600 · `17` ≥600 ·
  `10/12/14` ≥400 each. (Internal feeders `04`–`07`,`38` carry no word floor.)
- **Bot-message cap:** on `19/20/21` every individual bot message (the quoted, sendable text
  a contact receives) is **≤550 stripped chars** (`AA-PIPELINE-MANIFEST.json`
  `floors.bot_msg_char_cap`; enforced by `_botdoc_defects`).
- **Exact counts:** `36` = 39 image prompts · `35` = 3×13 = 39 · `37` = 12+12+12 · each ad set = 10 ads.
- **Image-prompt char band:** `36` and `40` = **5,000–19,000 stripped chars**; no repeated
  artist/photographer/producer token across prompts.
- **Structure:** each of the 13 ad sets names its restored category (no "category 2" drift);
  bot docs carry H1 `# … Section` + XML labels + `{{contact.*}}` merge tags; hero = 12 sections.
- **Placeholders:** zero unresolved `{{…}}` / `$('…')` in any artifact (whitelist:
  `{{contact.*}}` merge tags in bot docs).
- **Model sovereignty:** every resolved model id fails `/anthropic|claude/i` (G-NOANTHROPIC).

## 4. The 16 deliverables (37 delivered documents)

`Avatar_Intelligence` (03+01+02), `Tone_Doc` (08), `Marketing_Intelligence` (09–14),
`Facebook_Targeting_Intelligence` (15), `Brand_Bio_Intelligence` (16), `Product_Bio_Intelligence`
(17), `AI_Bot_Prep_Doc_Intelligence` (18), `AI_Booking_Bot_Intelligence` (19),
`AI_Post_Booking_Bot_Intelligence` (20), `Rescheduling_Booking_Bot_Intelligence` (21),
`Visual_Display_Ads` (22–34), `Top_39_Suggested_Ad_Angles` (35), `Top_39_Suggested_Image_Prompts`
(36), `Facebook_Headline_and_Primary_Text_Ad_Copy_Writer` (37), `Landing_Page` (39),
`Landing_Page_Image_Prompts` (40) — each suffixed `-<First>_<Last>.md`, plus `00-INDEX.md` +
`MANIFEST.json`. **35 published constituents + index + manifest = 37 delivered documents.**
Internal-only feeders (`04`,`05`,`06`,`07`,`38`) are never published.

Both accountings reconcile: 40 stage artifacts − 5 internal feeders = 35 constituents → 16 named
deliverables (+2) = 37. Independently the source export carried exactly 37 `googleDrive` nodes
(5 folder ops + 16 uploads + 16 deletes). The skill's contract is the **content** accounting,
delivered locally with **zero Drive nodes**.
