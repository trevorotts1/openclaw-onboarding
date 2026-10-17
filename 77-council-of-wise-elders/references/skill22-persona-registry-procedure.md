# Skill 22 persona-category registry procedure (CWE-045)

Purpose: keep the Council of Wise Elders' elder personas present in
Skill 22's persona-category registry (the ground truth the persona
matcher reads, per Skill 22's own documentation) without ever
inventing classification data. This procedure is the CWE-050
owner-tooling remainder for the persona-category registry; the tool
is `scripts/register-skill22-personas.mjs` in this skill.

## Ground rules (from Skill 22 itself)

- The shipped seed, `22-book-to-persona-coaching-leadership-system/persona-categories.json`,
  is READ-ONLY for tooling. It is updated only when shipping new
  default personas with the repo. No step of this procedure writes it.
- The canonical live registry is the workspace data file
  (`<workspace>/data/coaching-personas/persona-categories.json`),
  seeded from the shipped file on first run. Merges land THERE, via
  Skill 22's own fleet tooling (see step 4).
- A persona with no verified source material behind it is never
  registered. CWE-011's export records bibliographic absence
  honestly; this procedure carries that absence forward instead of
  filling it in.
- Tag classification (domain, perspective, audiences, topics) is
  Skill 22 Phase-6 work or an owner's deliberate act. Council
  tooling never invents a tag.

## Inputs

1. A CWE-011 Skill 22 export directory: `export-manifest.json`
   (schema `wise-elders.skill22-export/v1`) plus one package per
   seat with `sources.json`.
2. The Skill 22 seed named above (read for vocabulary and for the
   already-registered check).

## Steps

1. Build the staging file. From this skill's folder:

       node scripts/register-skill22-personas.mjs \
         --exports <cwe-011 export dir> \
         --seed <repo>/22-book-to-persona-coaching-leadership-system/persona-categories.json \
         --out <staging.json>

   The staging file (schema
   `wise-elders.persona-registry-staging/v1`) accounts for all nine
   council seats exactly once:

   - `already_registered`: a present work whose author and book
     already have a registry entry. No change is proposed.
   - `register`: a present work with no entry yet. The proposed
     persona carries the author and book from the export's credited
     sources and EMPTY tag arrays, plus `needs_owner_tagging: true`.
   - `absent` (in `absent_seats`): a seat with no present works.
     Nothing is proposed for it.

2. Review the staging file. Every `register` entry needs an owner
   decision: fill its tag arrays with values drawn ONLY from the
   seed's declared vocabularies (`domainTags`, `perspectiveTags`,
   `audienceTags`, `topicTags`; `custom` is free-form), or leave it
   untagged and let Skill 22's Phase-6 classification repair handle
   it after merge (it stamps `needs_retag` there, by Skill 22's own
   doctrine). Do not remove `needs_owner_tagging` until the tags are
   real.

3. Validate before merging:

       node scripts/register-skill22-personas.mjs --check <staging.json> \
         --seed <repo>/22-book-to-persona-coaching-leadership-system/persona-categories.json

   The check refuses unknown seats, duplicate keys, register entries
   whose key already exists, already-registered keys that do not
   exist, tags outside the seed vocabularies, and malformed
   provenance hashes. A failed check stops the procedure; fix the
   staging file or the export, never the checker.

4. Merge into the canonical workspace registry with Skill 22's own
   tooling: add each `register` entry's `persona` object (WITHOUT the
   staging-only `provenance` and `needs_owner_tagging` fields) to the
   canonical file's `personas` map under its key, then run Skill
   22's `pipeline/persona_fleet.py sync-categories` so only canonical
   seed fields ship. The merge is an owner act: this procedure's
   tool never performs it.

5. Re-run the check from step 3 against the canonical registry file
   (pass it as `--seed`) after the merge: every previously `register`
   key must now read as already present, and no seat may be
   unaccounted for.

## Current state of record

Measured by running this procedure against CWE-011's accepted
export and the shipped Skill 22 seed during CWE-045: 14 present-work
entries, of which 12 were already registered in the seed and 2 were
genuinely new proposals; 2 seats (Les Brown, Oprah Winfrey) were
absent because CWE-011's export records no present works for them.
The staging output of that run is build evidence, not a registry
change: no registry file was written by CWE-045.
