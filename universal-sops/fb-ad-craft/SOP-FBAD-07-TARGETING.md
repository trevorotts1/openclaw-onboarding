# SOP-FBAD-07: BUILD THE TARGETING BRIEF (PLAI's three tiers)

**Cluster:** FB/IG Ad-Craft Rules
**Master authority:** `AD-PIPELINE-MANIFEST.json` + `MASTER-AD-QC-AUTOFAIL-RULESET.md` (Gate D)
**Owning role:** Audience Research Specialist
**Stage:** S6-TARGETING — `depends_on: [S2-PRIMARY-TEXT, S3-HEADLINES]`
**Produces:** `working/checkpoints/s6-targeting.json` + `working/checkpoints/s6-targeting-brief.md`
**Gates:** AF-FBAD-TARGETING-SHAPE, AF-FBAD-TARGETING-REAL (+ Gate D AF-FBAD-TARGETING-QC)
**Resolver:** `48-facebook-ad-generator/scripts/ad_targeting_resolve.py`

---

## 0. WHY THIS SOP EXISTS

PLAI's audience builder expects a specific shape — named groups, each with three layers
of interests — and Meta only accepts REAL interest entities. An invented interest is
the single most common way a "finished" ad brief silently breaks in the builder. So
every interest must resolve to a real Meta entity, or be honestly marked
flagged-unverified; it is never fabricated.

## 1. THE THREE-TIER SHAPE (PLAI's builder)

Build one or more **groups**, each with:
- a plain-English **explanation** (the "why this group");
- **layer1 / layer2 / layer3** — three layers of interests (broad → specific), each a
  non-empty list (AF-FBAD-TARGETING-SHAPE).

Derive the groups from the ~22-question audience profile (demographics, income, needs,
goals, objections). If a targeting doc was supplied at intake, start from its named
groups; otherwise derive from the profile.

## 2. EVERY INTEREST IS REAL OR FLAGGED (auto-failed)

For each interest, the resolver attempts to resolve it to a real Meta entity (a real
`meta_id`). Each interest entry ends as one of:
- `{ "name": "...", "resolved": true, "meta_id": "6003020834693" }`, or
- `{ "name": "...", "flagged_unverified": true }` — the HONEST degrade when no
  resolver/key exists, so the package can still ship.

Inventing a `meta_id` is forbidden (AF-FBAD-TARGETING-REAL). The Perplexity-Pro research
path is the primary resolver; the fallback is the flagged-unverified degrade. Never
treat a guess as resolved.

## 3. SANITY

Demographics and geography must be sane for the dossier (age band, country/region,
language). The brief carries an explanation per group a human can read and trust.

---

## 4. INDEPENDENT QC (Gate D — The Targeting)

An **Independent Targeting Reviewer** (not the audience researcher) grades: every entry
real (or honestly flagged), correct three-tier shape, matches the audience dossier, a
plain-English why per group, sane demographics/geography. Pass = 8.5+ no category < 7
(AF-FBAD-TARGETING-QC) AND independent (AF-FBAD-QC-INDEPENDENCE). 2-redo budget.

---

## 5. ATTESTATION APPEND (replaces any prose "do not skip")

`working/checkpoints/s6-targeting.json`:
```json
{
  "groups": [
    {
      "name": "Core fans",
      "explanation": "People who already follow this kind of show — warmest tier.",
      "layer1": [ { "name": "Podcasts", "resolved": true, "meta_id": "6003020834693" } ],
      "layer2": [ { "name": "Audiobooks", "resolved": true, "meta_id": "6003123299417" } ],
      "layer3": [ { "name": "Self improvement", "flagged_unverified": true } ]
    }
  ]
}
```
`_chk_targeting_shape` validates the three-tier shape + the per-group explanation;
`_chk_targeting_real` fails any interest that is neither resolved with a `meta_id` nor
`flagged_unverified`.
