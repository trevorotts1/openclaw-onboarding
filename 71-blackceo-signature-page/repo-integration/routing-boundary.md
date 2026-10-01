# Skill 71 Routing Boundary

## skill-department-map

After adding Skill 71, remove the generic trigger `build me a landing page` from Skill 49's client intent list. Keep Skill 49's multi-step funnel language such as:

- build my funnel
- signature funnel
- 3/5/7 step funnel
- opt-in and upsell chain
- upsell/downsell funnel
- full funnel

Skill 71 should own plain single-page landing-page language.

## Skill 6 funnel-engine selector

Skill 49's selector is for the multi-step Signature Funnel. Do not let generic single-page phrases force a Skill-49 match.

At minimum, after Skill 71 is wired:

- remove `signature landing page` from Skill 49 `match.names` / `match.keywords`, OR require additional funnel signals before choosing Skill 49 for that phrase;
- preserve 3/5/7, upsell, downsell, OTO, checkout, and branching signals for Skill 49;
- do not add Skill 71 to the funnel-engine registry unless the current Skill-6 implementation specifically requires single-page authoring engines there. Skill 71 can hand its completed build bundle directly to Skill 6's existing single-page delivery path.

This prevents one plain landing-page request from being claimed by both Skill 71 and the older multi-step funnel engine.
