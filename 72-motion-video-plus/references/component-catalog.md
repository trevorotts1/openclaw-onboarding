# Motion Component Catalog (V2)

The typed, extensible catalog of reusable motion components: Directive
MG-018, implementing Sections 7 and 16.1. The catalog is a registry, not
a menu of names: a component can be dispatched only when its closed
input schema, proof contract, and tests are registered together, and an
undeclared or unregistered component name is never accepted.

Implementation: `runtime/src/catalog/` (types, entry schema, registry,
one entry file per registered component, and the pending entries for
the components whose bundles have not landed). Tests:
`runtime/tests/run-catalog.ts`, chained into `npm test` after the
existing runners. Parity evidence: `tests/evidence/mg018/parity-table.md`.

## The registration contract

Every catalog entry (one component at one version) carries:

- `componentId` and `version`
- a closed input schema: a JSON Schema object with
  `additionalProperties: false`. There is no escape hatch; the governed
  registration path refuses any schema that is not declared closed.
- engine support list and a default engine
- semantic purpose and the Section 7.1 visible change
- asset requirements in the MG-011 vocabulary (canonical asset kinds and
  the usage classes `embed_original`, `approved_derivative`,
  `reference_only`), plus structured data requirements
- layout variants (landscape 16:9 and portrait 9:16, the portrait
  genuinely recomposed, never a crop)
- a timeline contract in the Section 5.4 half-open convention:
  intervals are `[start_frame, end_frame_exclusive)`, duration is the
  difference, and seconds conversion happens only at engine boundaries
- a proof contract: selectors naming the semantic assertion kinds,
  subject selectors, evidence forms (geometry, decoded frame, full-fps
  clip), proof frames, and measured states, in the MG-009/MG-006 pattern
- typography roles
- variation descriptors: how composition, framing, type treatment, and
  pacing are driven by the job's design inputs
- at least one example (a scene for dispatchable components, a
  storyboard beat for registered identities)
- provenance and license note

Entries are themselves validated against `CATALOG_ENTRY_SCHEMA`
(`runtime/src/catalog/entry-schema.ts`) before the registry accepts
them. The schema encodes the availability rule structurally (below).

## The availability rule (Section 16.1)

A component is **unavailable until its schema, proof contract, and tests
are registered together**. Readiness for registration is not delivery.

- An `available` entry must carry a non-null input schema, a non-null
  schema source, a non-null proof contract, and at least one registered
  test, and its `unavailableReason` must be null.
- An `unavailable` entry must carry a null input schema and a null proof
  contract, and must state its reason, including the owning item that
  will register its bundle.

Validation and dispatch behavior:

| Situation | Category | Exit class |
|---|---|---|
| Component id never registered | `MG_UNKNOWN_COMPONENT` | 2 |
| Known id, props violate the closed schema | `MG_SCHEMA_INVALID` | 2 |
| Known id, unregistered version while an available version exists | `MG_SCHEMA_INVALID` | 2 |
| Schema-valid scene whose motion interval contradicts its duration | `MG_TIMELINE_INVALID` | 2 |
| Registered component (or version) with no available production bundle | `MG_CAPABILITY_UNSUPPORTED` | 3 |

`MG_CAPABILITY_UNSUPPORTED` is used for unavailable components because
Section 16.9 places it in the dependency class (exit 3, "Required
dependency unavailable"): the capability is named and registered, but
the runtime cannot execute it yet. That is distinct from an unknown id
(a contract error, exit 2). The adapters layer's sibling category is
named `MG_CAPABILITY_MISSING`; the catalog deliberately uses the
Section 16.9 stable-table name.

The catalog never silently substitutes: an unavailable component is
refused with its reason, and nothing renders in its place. Catalog
validation runs before any adapter or render work.

### Verdict parity with the shipped validators

For C05 the catalog input schema is **derived at load time** from the
canonical contracts schema (`references/contracts-v2.schema.json`,
`$defs/scene`), never hand-copied, and the unknown-id classification
replicates the shipped MG-007 dispatch rule exactly. The catalog test
suite runs a 20-case accept/reject corpus against the catalog and
against both shipped validators (TypeScript `validateJob` and the
Python `motion_contracts.py` CLI): verdicts are identical on every case,
and categories are identical on every case except one deliberate
divergence. That divergence has grown since the corpus was pinned,
and it is a shipped seam, stated plainly: the canonical contracts
scene definition is still closed on C05 (`component_id` const `C05`),
so the package validators refuse every non-C05 scene, while the
catalog now registers C04, C06, C07, C08, and C09 as available and
validates their props against their own registered schemas. A scene
for one of those components therefore passes the catalog consult and
still fails job-package validation until the validators are wired to
consult the catalog (see the integration note below). Neither layer
substitutes or silently passes the other. See
`tests/evidence/mg018/parity-table.md` for the original corpus.

## The twelve components

All entries are version 1.0.0. C01 through C09 are available for
production dispatch; C10, C11, and C12 remain unavailable, each with
its reason recorded in its entry.

| ID | Component | Default engine | State | Bundle owner |
|---|---|---|---|---|
| C01 | Image-led statement | Hyperframes | **available** | MG-005 (production); catalog bundle MG-044 |
| C02 | Product-detail demonstration | Hyperframes | **available** | MG-044 (on the MG-012 close-up geometry) |
| C03 | Before/after comparison | Hyperframes | **available** | MG-044 (on the MG-012 comparison geometry) |
| C04 | Object-through-mechanism | Remotion | **available** | MG-017 |
| C05 | Bar comparison | Remotion | **available** | MG-006 (Hyperframes build: MG-016) |
| C06 | Line trend | Remotion | **available** | MG-016 |
| C07 | Stacked allocation | Remotion | **available** | MG-016 |
| C08 | Waterfall explanation | Remotion | **available** | MG-016 |
| C09 | Causal/branching diagram | Remotion | **available** | MG-017 |
| C10 | Spatial/depth explanation | Qualified native engine integration | unavailable | unassigned in the Section 15 table |
| C11 | Evidence/offer reveal | Engine appropriate to assets | unavailable | unassigned in the Section 15 table |
| C12 | Presenter-safe loop/reveal | Either | unavailable | unassigned in the Section 15 table |

Two engine notes, recorded in the entries themselves: C04's Section
7.1 row names Hyperframes, but its registered dispatch is the proven
Remotion path only, and the entry refuses to claim the unproven one.
C05 is built natively in both engines (Remotion by MG-006,
Hyperframes by MG-016); its registered default is Remotion.

Minimum proof each component must register (Section 7.1):

- C01: subject integrity, deliberate crop, readable opening and proof frames
- C02: original UI fidelity; annotation follows the correct detail
- C03: both states and the comparison boundary are visible
- C04: persistent identity; causal order; final outcome
- C05: intermediate geometry and exact final ratios/labels
- C06: time order, correct plotted points, no fabricated smoothing
- C07: segment values, sums, units, and color/label mapping
- C08: arithmetic equality and correct connector/baseline behavior
- C09: meaningful branch selection, no orphan edges or label collisions
- C10: occlusion/perspective evidence plus readable final composition
- C11: authentic content, hierarchy, adequate final hold
- C12: no jump at loop seam; no disappearing essential information

C05's registered proof selectors use the Section 17.2 proof states at
30 fps (frames 0, 15, 45, 75, 150, 179), with bar widths measured as
geometry, decoded frames, and a full-fps clip. Section 7.1 also calls
for C05 to be built natively in Hyperframes as a capability and
reference test; that build is MG-016's deliverable, and the C05 entry
already lists Hyperframes in its engine support because the canonical
scene schema admits it.

## The governed custom-component path

New components enter through `ComponentRegistry.register(bundle)`
(`runtime/src/catalog/registry.ts`). One call takes the whole bundle:
the entry (carrying its closed input schema, proof contract, and tests)
plus an engineering review attestation. The registration is refused
with `MG_SCHEMA_INVALID` when any part is missing or defective:

- no input schema, a schema that is not `type: object`, or a schema
  whose `additionalProperties` is not exactly `false`
- an input schema that does not compile
- no proof contract, or a proof contract with no selectors
- no tests, or duplicate test ids
- no review attestation, a decision other than `approved`, or an
  unnamed reviewer or empty statement
- an official Section 7 component id (official components register
  through their owning items, not the custom path)
- a component id that is already registered (custom ids must be new)

The review attestation is an engineering review record of the bundle.
It is never an owner approval of a job: Section 5.1 forbids code from
writing owner approval, and nothing in the catalog writes one.

The path is demonstrated end to end in the catalog test suite, which
registers a small custom component (X01, a count-up figure, fixture at
`tests/fixtures/catalog/custom-bundle.json`) into a scratch registry,
validates and dispatches it, and then refuses ten partial-registration
mutations plus a duplicate registration. Custom registrations never
leak into the default registry.

## Variation: the anti-template rule

Reusing a primitive must not make two branded jobs visually identical.
Each entry records composition, framing, type-treatment, and pacing
descriptors, and the registry's `describeLayout` computes a concrete
layout descriptor from the job's design record (palette, plot geometry,
type scale) for a layout variant. The catalog test suite proves that
C05 with the shipped fixture design and C05 with a second brand design
(`tests/fixtures/catalog/brand-b-design.json`, itself validated against
the canonical design schema) produce different descriptors in palette,
plot width, and headline size, and that the landscape and portrait
descriptors for one design differ, because the portrait is recomposed.

## Integration note for the coordinator

The shipped validators (`runtime/src/validation/` and
`scripts/motion_contracts.py`) still dispatch scene schemas solely
through the canonical contracts scene definition, which registers C05
only. No catalog item modifies them: the catalog is the registry those
validators and the future orchestrator consult, and
`validateSceneProps` and `requireDispatchable` are the consult points,
with `ComponentRegistry.createDefault()` as the production registry.

The precise consequence, verified at the MG-044 build: the catalog
now registers C01 through C09 as available, each with a closed
catalog-layer schema describing its production spec shape. A job
through the dispatcher's `loadValidatedJob` still runs contracts
validation first, and the canonical scene definition is closed on
C05, so a canonical-shape job naming any other component is refused
at that gate (as `MG_UNKNOWN_COMPONENT`, converted to
`MG_CAPABILITY_UNSUPPORTED` only when every finding is an unknown
component the catalog also reports unavailable). Non-C05 components
therefore reach their adapters through the catalog layer plus the
direct adapter lane (the MG-005 and MG-039 pattern), not through
canonical job dispatch. Closing that last gap means promoting the
registered catalog-layer scene shapes into the canonical contracts
schema, which is a contracts revision for a future item to schedule,
not a catalog act.
