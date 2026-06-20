# SOP-STORY-01: THE VILLAIN -> HERO STORY ARC (narrative ordering beat)

**Cluster:** Intelligence Engines (Story Intelligence, Engine 4)
**Owning role at write time:** Slide Copywriter (writes + tags the beats); Director of Presentations (reserves the beat ORDER in `arc_allocation.json`)
**Enforced at the gate by:** QC Specialist - Presentations (deck-level auto-fail AF-NO-VILLAIN at Phase 1Q, re-verified Phase 6)
**Detection script:** `scripts/intelligence_engines_check.py --phase copy` (zero deps; exit 4 on drift)
**Registered:** SOP-SLIDE-00 §8b + §9 code index; SOP-ENGINE-00 Engine 4
**Status:** Doctrine procedure, ENFORCED (mechanical). This SOP does NOT touch `build_deck.py`'s render path.

---

## 1. THE RULE

> "No one cares about the hero until they meet the villain."

A persuasive deck is a story, and a story needs an antagonist before it can have a savior. Every pitch deck must carry an explicit **VILLAIN** beat -- the named real enemy -- that **PRECEDES** the **HERO** beat -- the solution / promise / transformation. A deck that introduces the solution before naming the antagonist has no tension; the audience does not yet feel why the hero matters.

This is Story Intelligence's NARRATIVE ordering layer. It is distinct from, and stacks on top of:
- **AF-STORY-CHARACTER-DRIFT** -- the VISUAL same-person continuity rule (a recurring character held across slides). Orthogonal: the two never both fire on one finding.
- **The old-way-vs-new-way belief-shift contrast** (slide-copywriter-sops.md SOP 9.7 step 5). The villain is the named ANTAGONIST written as its own beat, not merely a two-sided comparison row.

## 2. WHAT COUNTS AS EACH BEAT

**VILLAIN / antagonist beat.** Names the real enemy in human, specific terms:
- the broken system the audience is trapped in
- the old way that keeps failing them
- the lie they have been told / the myth they believe
- the thing actually stopping them (not a vague "challenges")

Tag the slide block `VILLAIN`. Write it so the audience says "yes -- THAT is what's been beating me."

**HERO / solution beat.** Names the way out: the solution, the breakthrough, the new way, the promise, who they become, the transformation. Tag the slide block `HERO`.

## 3. THE ORDERING REQUIREMENT (the auto-fail)

In `slides_copy.md`, read in slide order:
1. A `VILLAIN` beat MUST exist. (Missing = fail.)
2. The first `VILLAIN` beat MUST appear BEFORE the first `HERO`/solution/promise beat. (Villain after hero = fail.)

**AF-NO-VILLAIN** fires (deck-level) on either condition. Failure message:
`AF-NO-VILLAIN: DECK FAIL -- no villain/antagonist beat, or it appears after the hero/solution beat. Name the antagonist (the broken system / old way) before the solution (SOP-STORY-01).`

## 4. PRODUCING-ROLE STEPS

**Slide Copywriter:**
1. While walking the arc, write one explicit antagonist slide and tag it `VILLAIN`; write the solution/promise slide and tag it `HERO` (slide-copywriter-sops.md SOP 9.7 step 23).
2. Confirm the `VILLAIN` slide ordinal is lower than the `HERO` slide ordinal.
3. Self-check before handoff: `python3 scripts/intelligence_engines_check.py working --phase copy` exits 0.

**Director of Presentations:**
1. When building `arc_allocation.json`, reserve the antagonist beat in the early/middle arc (after Care/See-Yourself, before the Promise/Solution payoff) so the ordering is structurally guaranteed, not accidental.

## 5. FAILURE MODE

If the client's material genuinely has no antagonist to name (rare -- almost every transformation has an enemy), do NOT fabricate a villain that misrepresents the client's market. Flag the Director to confirm the real enemy with the client; never ship a deck whose solution arrives with no problem named (that deck fails AF-NO-VILLAIN by design until the antagonist beat exists).
