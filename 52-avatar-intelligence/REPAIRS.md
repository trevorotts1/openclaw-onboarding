# REPAIRS — auditable, reversible source dispositions (R1–R7)

Every source anomaly is explicitly dispositioned (KEEP / REPAIR / DROP). Repairs are ON by
default; the foreman's `--strict-source` flag replays the original defective wiring for A/B.
Faithful-or-repaired, never silently changed.

## Repairs (default ON)

| Repair | Source defect | What we do | Where enforced |
|---|---|---|---|
| **R1** | Blended Tone was passed only the tone-style NAMES, so the 4 tone chains were dead compute | `08-blended-tone` receives the four tone-style ANALYSIS documents (`artifact.04..07`) in its `<tone_style_N>` tags | baked `prompts/08-blended-tone/user.md`; DAG `depends_on` |
| **R2** | Solution-Aware pt2 injected the Problem-Aware doc (copy-paste bug) | `12-solution-aware-pt2` injects `artifact.11-solution-aware` and says "Solution Aware" | manifest `depends_on`; prompt header note |
| **R3** | Facebook Audience Generator's `<audience_targeting_cheat_sheet>` tag was empty | it now explicitly references the Black CEO Method 7-Tier framework in `methodology.md` | baked `prompts/15-facebook-audiences` |
| **R4** | Ad Sets 2–13 all froze on "category 2" | each of the 13 ad sets gets its TRUE category brief restored from the Airtable `User` fields | baked ad-set `user.md` R4 directive; `G-ADSET-CAT` / `AF-AV-ADSET-CAT` |
| **R5** | Facebook headline writer's "Name of product/offer/mission:" line was empty | filled from `{{intake.offer_name}}` / `{{intake.product_info}}` | baked `prompts/37-fb-headline-copy` |
| **R6** | `Answer 9 Questions` output was generated then unused | now feeds the hero page (`39` `depends_on` `38`) | manifest `depends_on`; prompt header note |
| **R7** | Hero page was hardcoded to `anthropic/claude-sonnet-4` via OpenRouter | re-pointed to the client TIER-A model; the Anthropic chain is removed (client-path rule) | `preflight.sh` model-map; `G-NOANTHROPIC` |

## Other dispositions

- Orphan `o3` node → **DROP** (disconnected in source).
- Disabled Go High Level write-back → **OUT** (hook preserved via optional `contact_id`; the skill
  never calls GHL).
- Reported Drive folder-name mismatch → **RETRACTED + MOOT** (digest-truncation artifact).
- Awareness records' `System`-field leftover blended-tone persona → **KEEP verbatim** (behavioral
  fidelity; the working instructions live in methodology/user).
- Empty Facebook cheat-sheet tag / empty product line → repaired by R3 / R5.
- Cosmetic leftovers (`Book-titles-N.html`, "HTML Test 3", the misspelled `brand-intellegence`
  webhook path) → **die with the plumbing**.
- Strictly sequential 41-call relay → **REPLACED** by the digest-verified DAG (20 waves,
  `AA-PIPELINE-MANIFEST.json`); the ad-set harmony chain stays sequential by design (`--fast-ads`
  is an opt-in fidelity trade-off).

`--strict-source` reverts R1/R2/R4/R5/R6 to their defective wiring for A/B comparison; R7 (the
Anthropic ban) is **never** reverted on a client box.
