# SOP-EMAIL-02: SELECT THE FRAMEWORK / BUYER-TYPE / OBJECTIVE / PERSONA / SEQUENCE

**Cluster:** Email-Craft Rules (`universal-sops/email-craft/`)
**Master authority:** `EMAIL-PIPELINE-MANIFEST.json` + `50-email-engine/email-library/`
**Owning role:** Email Campaign Strategist (Marketing)
**Stage:** P1-SELECT
**Produces:** `working/routing/email-match.json`
**Gates this stage satisfies:** AF-EMAIL-FRAMEWORK-UNKNOWN, AF-EMAIL-OBJECTIVE-INVALID, AF-EMAIL-PERSONA-INVALID

---

## 0. WHY THIS SOP EXISTS

The Email Superlibrary is the IP. The right framework for a spontaneous impulse buyer is not the right framework for a methodical evaluator, and a landing-page promo slot has a SACRED framework map. Selection is deterministic and logged so the choice is auditable, not a habit.

## 1. RUN THE MATCHER

```
python3 50-email-engine/tools/email_matcher_cli.py --match "<the brief request in plain words>" --json
```

The matcher (a stdlib lexical scorer with an optional embedding re-ranker) returns the top framework / buyer-type / objective / persona-style / sequence entry, its confidence, and ranked runners-up. Filter by `--type framework|buyer-type|objective|persona-style|sequence` when you need one facet.

## 2. THE THREE FLEX MODES

- EXPLICIT_USER_SPEC -> honor it. If the owner named a framework, use it (log the override).
- UNSURE -> suggest the top match + one runner-up and ask.
- HANDS_OFF -> use the top match above the confidence threshold.

Every chosen id must be canonical (one of the 13 frameworks / 4 objectives / 12 persona styles), or the prover raises AF-EMAIL-FRAMEWORK-UNKNOWN / AF-EMAIL-OBJECTIVE-INVALID / AF-EMAIL-PERSONA-INVALID.

## 3. SEQUENCE MAPS ARE SACRED

For a named sequence the per-slot framework is fixed:

- **landing-page-10-promo (E1..E10):** E1-E3 PASTOR (Solutions), E4 Features-to-Benefit, E5 Six W's, E6 Before-After-Bridge, E7 3-B Plan, E8 Million Dollar Sales, E9 AIDA, E10 PAS.
- **12-email (buyer-type / high-ticket, E1..E12):** E1 3-B Plan, E2 Star-Chain-Hook, E3 Features-to-Benefit, E4 Six W's, E5 ACCA, E6 PASTOR-Solutions, E7 PASTOR-Story, E8 Star-Story-Solution, E9 PAS, E10 AIDA, E11 Million Dollar Sales, E12 Before-After-Bridge.

The buyer-type band for the 12-email set is fixed too (E1-2 spontaneous, E3-6 methodical, E7-9 humanistic, E10-12 competitive). A slot whose framework/buyer-type breaks the map is AF-EMAIL-SEQUENCE-MAP / AF-EMAIL-BUYERTYPE-MAP at QC.

## 4. PERSONA STYLES ARE HIGH-TICKET, TONE-ONLY

The 12 persona styles apply to high-ticket / upsell copy. A style is adopted for TONE and rhetoric ONLY — the person is NEVER named or quoted (AF-EMAIL-PERSONA-NAMED). Do not repeat a persona style within one high-ticket campaign.

## 5. LOG THE DECISION

Write `working/routing/email-match.json` with the chosen ids, the confidence, the runners-up, and a one-sentence rationale. This log travels with the job card.
