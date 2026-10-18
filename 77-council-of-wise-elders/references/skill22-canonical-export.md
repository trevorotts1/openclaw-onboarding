# Skill 22 → canonical Council exporter

`scripts/export-skill22.mjs` exports selected passages from existing registered
Skill 22 notes/blueprints into the existing `Skill22ExportPackage` receiving
contract. It calls no model, downloads no book and changes neither the Skill 22
registry nor installed advisor packs. It does not convert EPUB/PDF originals.

## Repeatable invocation

From the Skill 77 folder, with the pinned runtime dependencies already installed:

```sh
npm --prefix runtime run build
node scripts/export-skill22.mjs --skill22-root /path/to/22-book-to-persona-coaching-leadership-system --mapping /path/to/mapping.json --out /path/to/new-export.json
```

The runtime's normal installer also builds this entry point. Output is a new
file, created exclusively with mode 0600. An existing output, symlink or input
path is never overwritten. Use a new filename for a repeat run. Identical input
bytes and mappings produce identical JSON; there is no invented export timestamp.

Exit codes: **0** export with no unresolved diagnostics; **2** valid output was
written, with unresolved mappings/empty seats; **1** invalid top-level input,
unreadable/unsafe inventory or output error, with no successful export claim.
A partial export retains usable evidence. Do not discard it merely because exit
2 reports missing mappings elsewhere. All nine seats remain accounted for.

To inventory gaps without authorizing any content release, use this mapping:

```json
{
  "schema": "wise-elders.skill22-mapping/v1",
  "pack_version": "your-explicit-pack-version",
  "revoked_source_ids": [],
  "entries": []
}
```

## Explicit mapping contract

Each `entries[]` object contains:

- `persona_key`: an existing key in Skill 22's `persona-categories.json` for one
  of the exact nine Council authors. Source author and work title must match it.
- `source`: the complete strict `SourceRecord` in
  `runtime/src/sources/schemas.ts`, including source/work IDs, title, credited
  authors, original speaker (or null), source type, publisher/date/URL (or null),
  actual retrieved-at value, opaque private-asset ID (or null), content SHA-256,
  rights, scope, quality and explicit locators. Optional `version` is preserved.
  Missing dates, hashes, permissions or locators are not guessed from filenames.
- `hash_basis`: `skill22_derivative` or `retained_original`. A derivative basis
  requires the source content hash to match an inventoried file and cannot use
  `primary_substantive`. A retained-original hash is supplied by the mapping;
  this exporter does not open, hash or independently verify the original.
- `provenance_reference`: an explicit opaque ID for the operator's provenance
  receipt, carried into export receipts. It is not a filesystem path.
- `shared_export_approved`: explicit boolean. Only true, `shared_pack` sources
  whose rights are not `private_use` are eligible. Revoked IDs are excluded.
- `passages`: one or more selections, each containing `file`, `sha256`,
  `start_line`, `end_line`, `text_field` and `evidence` as below.

`file` is relative to Skill 22's `personas/`, e.g.
`sinek-start-with-why/extraction-notes.md`. Only that persona's inventoried files
are eligible. Path escape and cross-persona selection are rejected. SHA-256
binds the exact UTF-8 bytes. Line numbers are one-based and inclusive. Selected
lines are joined with LF and trimmed at the edges; no paraphrase is generated.

`text_field` is `paraphrase` or `excerpt`. The selected text is placed verbatim
in that field; the other is null. An operator must classify the selected text
truthfully: labeling a quotation as a paraphrase does not make it one. Excerpts
require `licensed_distribution` or `public_domain`; a quotation also requires
matching explicit original speakers. Book authors are never substituted for guests.

`evidence` is the strict `EvidenceUnit` from `schemas.ts` **without** `paraphrase`
and `excerpt`: evidence ID, source ID/version, original-source locator, kind,
mark, original speaker (or null), claim IDs and seat ID. Its source/version/seat
must match the selected record/persona, and its locator must occur in the source
record. Derivative line numbers select input text; they do not invent original
book page citations. Duplicate evidence IDs or conflicting source IDs are rejected.

Missing mapping fields, stale file hashes, unresolved locators, denied scope and
invalid evidence produce indexed diagnostic codes. Diagnostics never echo rejected
passages or private source records. Valid passages in the same entry still export.
The mapping is an explicit provenance assertion, not independent verification.
Never raise quality or invent an access/rights receipt simply to make it pass.

## Output and consumption

The JSON envelope schema is `wise-elders.canonical-skill22-export/v1`:

- `packages`: nine canonical `{seat_id, pack_version, sources, evidence,
  claimed_titles}` objects. Source metadata is preserved; only mapped accepted
  passages are included. Empty seats have empty arrays, not fabricated sources.
- `seats`: actual validator qualification, work coverage and per-package SHA-256
  (hash of UTF-8 `JSON.stringify(package)`, without indentation or newline).
- `receipts`: evidence IDs bound to derivative file hashes/ranges and the
  mapping's hash basis/provenance-reference ID.
- `diagnostics`: unresolved items by entry/passage index or missing registered
  persona/seat; `mapping_sha256` binds the parsed mapping's JSON serialization.

Use `exported.packages` directly with the runtime's `assertPackagesValid()` or
pass each package to `validateExportPackage()`. These are the canonical receiving
APIs used by context preflight. This JSON is not the older directory-style
`wise-elders.skill22-export/v1` format; do not feed it to the legacy
`adaptSkill22Export()` or registry-staging directory tool. This bridge deliberately
uses the strict contract directly and does not silently replace installed packs.

Structural acceptance is not source readiness. Existing unverified derivatives
stay unverified. Primary-source passage fidelity, missing book mappings and the
required foundation gate remain separate content/acceptance work. Installed-host
acceptance remains with the existing integration owner.

Focused tests: from `runtime/`, run
`node --import tsx --test tests/skill22-exporter.test.ts`.
