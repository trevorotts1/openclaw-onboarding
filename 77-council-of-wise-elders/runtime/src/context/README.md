# CWE-022 context: authorized retrieval and bounded context assembly

Implements directive Sections 8, 9, and 13 for the portable core:
graph product `bounded-authorized-context`.

## Modules

- `types.ts`: the catalog port and candidate model. A catalog exposes
  content-free headers (scope, visibility, provenance enums, canonical
  content hash) and loads content only for evidence IDs the retrieval
  layer has already admitted.
- `retrieval.ts`: authorized retrieval. The CWE-007 session gate runs
  before the catalog is touched; each header is decided with the same
  CWE-007 port against the material's own scope and visibility;
  Section 8.3 source-scope rules, the distributable bar on
  user_private material (CWE-012 condition 3), Section 8.6 revocation,
  and frozen-manifest membership with hash equality are applied before
  any content load. Loaded candidates are revalidated against the
  CWE-012 schemas and cross-checked (source, version, canonical hash).
  Skips are silent: no counts, no digests, no error text derive from
  skipped material. `assertPackagesValid` runs the CWE-012 export
  package validator as a pre-flight.
- `assembly.ts`: bounded assembly. Byte accounting is canonical
  (Section 11.6 serializer) against the route's actual context limit
  minus caller-measured reserves for system rules, response schema,
  and output. The minimum valid context (brief view plus each selected
  seat's first authorized item) either fits whole or the result is the
  typed `CONTEXT_TOO_SMALL` readiness result with the lower-context
  modes that would fit. Discretionary items are added whole, in
  deterministic order, under the remaining budget and per-seat input
  budgets. Round 1 omits `private_preference_ref` from the brief view;
  the preference content is never an input to this module. Output is
  deterministic: same inputs, byte-identical payload, same content
  hash.
- `session-source.ts`: composition with the CWE-006 scoped store
  through the CouncilStore port: loads the frozen brief, spec, and
  scope for a session and assembles against them.

## Provenance rule

Every item carries its CWE-012 provenance (source_id, source_version,
locator, quality, rights_status, allowed_scope, original speaker, mark).
The quality label is carried verbatim and never upgraded;
verification_status is `verified` only for a primary_substantive
record. All records in the current build are unverified or
bibliographic_only, so real assemblies label items unverified.

## Boundaries and remaining work

- The CWE-011 export format drifts from the CWE-012 canonical schemas
  (CWE-012 condition 4). Reconciling that drift is the integration
  runner's adapter (CWE-050), not this module: candidates here are
  canonical Section 8.3 records and evidence units.
- The Command Center adapter surface named in the CWE-022 prose block
  (CC `src/lib/council/context.ts`) is outside this unit's ONB owned
  paths and lands with the CWE-029/CWE-050 wiring, consuming this
  module's surface.
- Local lexical/FTS fallback and embedding configuration (CWE-022
  prose build step 2) belong to the host catalog implementation behind
  the MaterialCatalog port; this layer is retrieval-order and
  authorization only, and leaves embedding configuration untouched.
- Locator-preserving summarization for oversized items is a host
  catalog concern: this layer never truncates an item, it includes
  whole items or returns CONTEXT_TOO_SMALL.
