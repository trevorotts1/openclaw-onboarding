# Sources: source integrity and advisor pack validation (CWE-012)

Implements directive Sections 7, 8, and the CWE-012 unit: schemas for
source records and evidence, the quotation tuple validator, the coverage
and substantive gate, the advisor pack validator with immutable audit
output, and the receiving validator for Skill 22 export packages.

The module consumes the CWE-003 canonical contracts read-only
(`../contracts/`): seat IDs and roster, the advisor profile label
function, ID and SHA-256 schemas, canonical JSON hashing. It defines the
Section 8.3 SourceRecord, which CWE-003 did not carry.

## What is checked

- **Registry (T001):** exactly the nine approved seat IDs; unknown,
  duplicate, or missing IDs fail.
- **Attribution:** every profile carries the exact label "AI perspective
  inspired by the published work of [name]. Not the individual and not
  an endorsement." Missing or altered labels fail.
- **Coverage honesty:** a title claimed in `profile.source_basis` or
  `coverage.claimed_titles` with no source record or bibliographic stub
  in the pack fails (`COVERAGE_TITLE_UNLISTED`). Coverage counts above
  the evidence present fail (`COVERAGE_COUNT_INFLATED`).
- **Substantive gate (Section 8.2):** each required work needs at least
  three independently traceable concepts (direct teaching, paraphrase,
  or reported example evidence with exact locators, against a
  `primary_substantive` record) plus at least one located application
  case. Publisher description alone classifies `bibliographic_only` and
  cannot qualify a foundation a pack claims as ready
  (`FOUNDATION_NOT_SUBSTANTIVE`). Full-book evidence classifies
  `complete_book`; gate met through non-book primary teaching classifies
  `primary_teaching`, and the pack reports `primary_teaching_based`.
- **Quotation tuples (T011, Section 8.4):** the tuple (quoted_text,
  original_speaker, source_id, source_version, locator) is verified
  against the original source record and its quotation evidence, never
  against a concatenation of advisor files. Text found only in another
  seat is `QUOTE_FOUND_IN_OTHER_SEAT`; text found only in earlier
  generated rounds is `QUOTE_ONLY_IN_GENERATED_ROUNDS`; a guest's words
  attributed to the book's author are `QUOTE_WRONG_SPEAKER` (T004).
  Normalization is limited to the documented typographic list in
  `text.ts`; letter case is not folded.
- **Revocation, scope, rights (T012, Sections 8.3, 8.6):** revoked
  sources are excluded; a `tenant` or `user_private` source in a shared
  pack audit is `SOURCE_SCOPE_LEAK`; verbatim release requires rights
  that permit it (`reference_only` is paraphrase-only); evidence
  carrying instruction-like payload text is `SOURCE_INJECTION_CONTENT`;
  a filesystem path in `private_asset_id` is `PRIVATE_PATH_LEAK`.
- **Jakes structure (Section 7.3):** three lenses inside one seat.
  Declared lenses must be the seat's three; per-card `lenses_used` must
  come from that set; any structure declaring more than one vote fails
  (`JAKES_VOTE_INFLATION`). Lenses on any other seat fail.
- **Audit:** `auditPack` returns the validation plus an audit record
  binding the pack's canonical content hash, the pack version, the
  validator version, the qualification, and the diagnostics under a
  self-excluding canonical hash. Any later edit to the record breaks
  `verifyAuditIntegrity`.

## Format assumptions (integration review with CWE-011)

CWE-011 builds the Skill 22 exporter in parallel. This validator was
built to the directive text; drift is reconciled at integration review.

- **A1.** An export package carries Section 8.3 source records and
  evidence units under the field names in `export-package.ts`
  (`seat_id`, `pack_version`, `sources`, `evidence`, `claimed_titles`).
- **A2.** Works are matched to required foundations by normalized
  `work_title` (case and punctuation insensitive); `work_id` is the
  stable key when a pipeline uses it consistently.
- **A3.** A quote tuple's `source_version` matches the record's optional
  `version` field when present, otherwise the record's
  `content_sha256`. Section 8.3 names no version field; this is the
  documented resolution.
- **A4.** Bibliographic stubs in `sources.json` (a `title` with no
  `source_id`) are classified, not schema-rejected: they acknowledge a
  work as not yet ingested.
- **A5.** Evidence units are accepted embedded per record
  (`records[].evidence`) and at the top level (`sources.evidence`); the
  union is validated.
- **A6.** Revocation is an audit input (a set of revoked source IDs),
  per Section 8.6's retrieval exclusion, not a field on the record.
- **A7.** Rights-to-release mapping is derived from Section 8.1 step 4
  and the Section 8.3 rights enum: shared-pack verbatim release requires
  `licensed_distribution` or `public_domain`; `private_use` permits
  quotation only in tenant or user-private contexts; `reference_only`
  is paraphrase-only everywhere.

## Tests

From `runtime/`, with the pinned dev dependencies installed the same
way CWE-003 documents (zod, tsx, typescript, @types/node, `--no-save`):

```sh
node --import tsx --test src/sources/sources.test.ts
```

The suite includes a disk audit of the nine scaffold packs under
`advisors/`: all nine validate structurally, and all nine report their
honest qualification (`bibliographic_only` or `incomplete`), because no
seat's required foundation is yet substantiated by ingested sources.
That is the validator working as specified, not a failure.

The disk-level subset of these checks (pack presence, JSON parse, exact
profile label, seat and folder match, claimed titles present, coverage
counts not exceeding located evidence) also runs without any installed
dependencies via `scripts/source-checks.mjs`, wired into
`scripts/verify-bundles.mjs`.
