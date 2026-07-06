# DESIGN LIBRARY — MASTER INDEX
**Version:** 2.0 | **Last Updated:** 2026-06-12
**Audience:** AI agents. This is the lookup table for every style in the library. ALWAYS resolve style IDs here before opening card files. ALWAYS register new cards here immediately after creation.

---

## HOW TO USE (AI instructions)

**Resolving "use style {ID}":** find the row → open the file at File Path → follow MASTER-SOP.md Workflow B.

**Resolving a friendly name ("use signature style 1" / "use signature 2"):** operators do not have to memorize ID codes. Every registered card also carries a **Sig #**, a per-category friendly alias (signature 1, 2, 3, and so on) assigned in registration order within that category. To resolve a friendly name:
1. Determine the category from context (e.g. a PowerPoint request → PPT table; "ad" → FB or AD table; if ambiguous, ask which category).
2. In that category's table, find the row whose **Sig #** equals the spoken number ("signature style 1" → Sig # = 1).
3. Use that row's **ID** as the canonical reference and continue with Workflow B exactly as for "use style {ID}".
- "Signature style N" is ALWAYS category-scoped: PPT signature 1 and FB signature 1 are different cards. If the operator gives no category, resolve to the category their request implies; if still ambiguous, ask. Never guess across categories.
- The friendly alias is a convenience layer only. The **ID** remains the single source of truth used in file paths, generation logs, and handoffs.

**Assigning a Sig #:** when you register a new card, set its **Sig #** to the next unused integer in that category (1 for the first card in the category, 2 for the second, …). Never reuse a Sig # within a category even after a card is retired (retired rows keep their Sig # so spoken references stay stable). Sig # is independent of the numeric part of the ID (IDs can skip; Sig # counts registration order).

**Registering a new style:** append a row to the correct category table. Required fields, no exceptions:
- **Sig #**: friendly alias = next unused integer in this category (1, 2, 3, in registration order; see "Assigning a Sig #" below). Lets an operator say "use signature style N".
- **ID** — next available number for that prefix (scan the table; never reuse a retired ID)
- **Style Name** — matches the card header
- **One-Line Summary** — copied exactly from the card's one-line style summary
- **Status** — draft / tested / production (keep in sync with the card)
- **Ver** — current card version
- **Date** — last updated
- **File Path** — relative path from `design-library/`

**ID prefixes:** SI (single image) · FB (Facebook ad) · BC (book cover) · MAG (magazine cover) · SM (social media) · BN (banner) · AD (advertisement) · **FN (funnel / landing page / website page)** · PPT (PowerPoint deck; families = PPT-NNN-A, -B, ...) · PS (personal photo shoot — shoot cards; client identity profiles are NOT registered here, they live in their client folders)

**Retiring a style:** never delete the row. Set Status to `retired` and add "(retired: reason)" to the summary. History matters.

---

## SINGLE IMAGE DESIGNS (SI-)
| Sig # | ID | Style Name | One-Line Summary | Status | Ver | Date | File Path |
|---|---|---|---|---|---|---|---|
| - | - | *(empty - awaiting first analysis)* | | | | | |

## FACEBOOK AD DESIGNS (FB-)
| Sig # | ID | Style Name | One-Line Summary | Status | Ver | Date | File Path |
|---|---|---|---|---|---|---|---|
| - | - | *(empty - awaiting first analysis)* | | | | | |

## BOOK COVER DESIGNS (BC-)
| Sig # | ID | Style Name | One-Line Summary | Status | Ver | Date | File Path |
|---|---|---|---|---|---|---|---|
| - | - | *(empty - awaiting first analysis)* | | | | | |

## MAGAZINE COVER DESIGNS (MAG-)
| Sig # | ID | Style Name | One-Line Summary | Status | Ver | Date | File Path |
|---|---|---|---|---|---|---|---|
| - | - | *(empty - awaiting first analysis)* | | | | | |

## SOCIAL MEDIA DESIGNS (SM-)
| Sig # | ID | Style Name | One-Line Summary | Status | Ver | Date | File Path |
|---|---|---|---|---|---|---|---|
| - | - | *(empty - awaiting first analysis)* | | | | | |

## BANNER DESIGNS (BN-)
| Sig # | ID | Style Name | One-Line Summary | Status | Ver | Date | File Path |
|---|---|---|---|---|---|---|---|
| - | - | *(empty - awaiting first analysis)* | | | | | |

## ADVERTISEMENT DESIGNS (AD-)
| Sig # | ID | Style Name | One-Line Summary | Status | Ver | Date | File Path |
|---|---|---|---|---|---|---|---|
| - | - | *(empty - awaiting first analysis)* | | | | | |

## FUNNEL / LANDING / WEBSITE PAGE DESIGNS (FN-)
*Style cards for sales-funnel, landing-page, and website-page imagery. Consumed by the Skill 6 GHL delivery rail and the Skill 49 / 56 engines via an optional `style_card_id` on the page/intake spec: when set, DIU Workflow B resolves the card and its LONG tier is embedded as the Brand-Style block (block 8) of every image prompt. File Path is relative from the library root; the card's LONG tier feeds GPT-Image 2 / Nano Banana 2 (per MODEL-SPECS routing).*
| Sig # | ID | Style Name | One-Line Summary | Status | Ver | Date | File Path |
|---|---|---|---|---|---|---|---|
| - | - | *(empty - awaiting first funnel/landing/website style card)* | | | | | |

## POWERPOINT DESIGNS (PPT-)
| Sig # | ID | Style Name | Families | One-Line Summary | Status | Ver | Date | File Path |
|---|---|---|---|---|---|---|---|---|
| - | - | *(empty - awaiting first analysis)* | | | | | | |

## PERSONAL PHOTO SHOOT — SHOOT CARDS (PS-)
| Sig # | ID | Style Name | One-Line Summary | Status | Ver | Date | File Path |
|---|---|---|---|---|---|---|---|
| - | - | *(empty - awaiting first shoot card)* | | | | | |

## CLIENT IDENTITY PROFILES (reference list, not style cards)
| Client | Slug | Consent date | Folder |
|---|---|---|---|
| — | *(empty)* | | |
