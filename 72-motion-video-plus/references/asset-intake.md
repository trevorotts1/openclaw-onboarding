# Asset Intake and Preparation (MG-011)

This document defines how image and media assets enter a Skill 72 V2 job:
what is recorded about each asset, how the records are verified against
the real bytes, and what happens when an asset is missing, changed, or
not approved for the use a scene wants to make of it.

The rule this layer exists to enforce: "use this image" must never
quietly become "recreate something inspired by this image." A supplied
logo or product image is embedded as the exact bytes supplied, or the
job stops with a named blocker. It is never silently redrawn, and a
missing required image is never silently replaced with generic shapes.

## Where preparation sits

1. The contracts layer validates the job's serialized shape:
   `python3 scripts/motion_contracts.py validate <job_dir>`.
2. The preparation layer resolves the asset manifest to verified bytes:
   `python3 scripts/prepare_assets.py prepare <job_dir>`.
3. Only then does scene coding begin, against assets whose existence,
   hashes, dimensions, media types, and usage rights are proven.

This is the `SCHEMA_VALID` to `INPUTS_READY` step of the lifecycle in
directive Section 16.8. Preparation is a resolution step, not a render:
it produces a machine-readable preparation report, and with `--report
PATH` it persists the same report atomically at PATH (normally the
job's evidence area).

## What is recorded for every asset

The canonical manifest is `assets.json` in the job directory, governed
by `references/contracts-v2.schema.json` (`$defs` assets, entrypoint
`references/asset-schema.json`). Each asset record carries:

| Field | Meaning |
|---|---|
| `id` | Stable asset identifier that scenes and storyboard beats reference in `asset_ids` |
| `path` | Job-relative path to the local file (no absolute paths, no `..` escapes) |
| `sha256` | Recorded content hash of the exact bytes approved for this job |
| `kind` | Media class: `image`, `video`, `audio`, `font`, or `svg` |
| `usage` | Usage class: `embed_original`, `approved_derivative`, or `reference_only` |
| `rights_ref` | Non-empty reference to the rights or consent record for this asset |
| `focal_point` | Normalized `{x, y}` focal point, or `null` when none is declared |

The schema does not yet carry dimensions, provenance source, rights
status, intended role, crop constraints, protected regions, permitted
edits, per-asset placement, an explicit required flag, or derivative
linkage. Until the contracts owners extend the schema, those fields are
recorded in the preparation-layer sidecar `asset-provenance.json` in
the job directory, keyed by asset id, and are enforced by the
preparation layer:

| Sidecar field | Meaning |
|---|---|
| `source` | Where the asset came from (for example `client_supplied`, `generated_kie`, `stock_licensed`, `created_in_house`, `derived_in_house`) |
| `rights_status` | Rights or consent status (for example `owned`, `client_supplied`, `licensed`, `consent_on_file`, `public_domain`) |
| `role` | Intended role (for example `hero_image`, `brand_logo`, `data_evidence`, `mood_reference`) |
| `media_type` | Exact media type (for example `image/png`); checked against the bytes |
| `dimensions` | Declared `{width, height}`; checked against the measured bytes |
| `crop` | Crop constraints (for example whether cropping is allowed and the minimum visible fraction of the subject) |
| `protected_regions` | Regions that motion and crops must protect (faces, logos, proof details), as normalized boxes with labels |
| `permitted_edits` | The edits allowed for this asset (for example `crop`, `resize`, `color_grade`); an empty list means no edits |
| `placement` | Intended placement (for example full frame, inset, overlay corner) |
| `required` | Optional explicit required flag; see requiredness below |
| `derived_from` | For derivatives: the asset id of the source asset |
| `approval_ref` | For derivatives: the approval record that authorizes the derivative |

The preparation report lists, per asset, any of `source`,
`rights_status`, and `role` that the sidecar leaves unrecorded under
`provenance_gaps`. Gaps are reported honestly rather than filled in.
For derivatives, provenance is not optional: see the usage rules.

## Usage classes

- `embed_original`: the scene embeds the exact recorded bytes. The
  preparation layer recomputes the hash on every run; any byte change
  fails with `MG_HASH_MISMATCH`. This is the class for supplied logos
  and product images, and the hash check is what makes a silent redraw
  impossible: redrawn bytes are different bytes.
- `approved_derivative`: the scene embeds a derived file (a crop, a
  resize, a poster frame). The derivative must name its source asset
  in the sidecar (`derived_from`, an asset id declared in the same
  manifest, never itself) and an approval record (`approval_ref`).
  Without both, the derivative is unapproved and preparation fails
  with `MG_APPROVAL_REQUIRED`; scenes waiting on it are named as
  blocked.
- `reference_only`: the asset informs art direction only. It is never
  embeddable. If any scene file or storyboard beat lists a
  `reference_only` asset in `asset_ids`, preparation fails with
  `MG_SCHEMA_INVALID`, because reference material must not silently
  become published content.

## Requiredness and targeted blockers

An asset is required when any scene file or storyboard beat references
it, or when its sidecar entry sets `required: true`. Everything else
is optional.

- A missing required asset produces a targeted blocker: the report's
  `blockers` list names the asset and the scenes waiting on it, and
  preparation exits 3 (`MG_INPUT_MISSING`). Independent assets in the
  same job still verify; one missing image does not stall unrelated
  work.
- A missing optional asset is a warning only. Preparation can still
  succeed, and the warning stays visible in the report.
- A scene that references an asset id not declared in `assets.json`
  is also a blocker (exit 3): its bytes cannot be resolved at all.

## What the preparation layer measures

For every declared asset whose file exists, the layer computes the
real sha256, detects the media type from the bytes, and reads the real
dimensions from the file headers (PNG, JPEG, GIF, and WebP headers and
SVG attributes, parsed with the Python standard library only). It then
checks:

- actual hash equals recorded hash (any mismatch: exit 9,
  `MG_HASH_MISMATCH`);
- detected media type agrees with the declared `kind` (mismatch:
  exit 2, `MG_SCHEMA_INVALID`);
- sidecar `media_type` and `dimensions`, when declared, agree with
  the measured values (mismatch: exit 2);
- the path resolves inside the job directory (an escape: exit 9,
  `MG_SECURITY_VIOLATION`);
- the usage rules above (reference misuse: exit 2; unapproved
  derivative: exit 4, `MG_APPROVAL_REQUIRED`);
- `assets.json` itself satisfies the canonical assets schema, and
  asset ids are unique (violations: exit 2).

When several failure classes exist, the exit code follows the first
blocking class in directive Section 16.9 order: integrity (9),
validation (2), dependency (3), authority (4). The report's
`first_error_category` names the head category and `findings` lists
every problem found, not just the first.

## Invalidation

Changing an image changes its hash. When a hash mismatch is found,
the report's `invalidated_scenes` names every scene that uses the
changed asset: previews, approvals, and renders built on the old
bytes are stale for exactly those scenes and must be redone. Scenes
that do not use the asset are unaffected. This is the preparation
layer's half of the acceptance rule; the approval layer consumes the
same principle through revision hashing (directive Section 16.7).

## Fonts

`assets.json` also carries `font_requirements`. Font resolution
belongs to the shared runtime registry (each requirement's `source`
is `runtime_registry`, and substitution is forbidden), so the
preparation report lists font requirements with status
`deferred_to_runtime_registry` and invents no evidence about them.

## Where new imagery comes from

Asset preparation never generates imagery. When a job genuinely
needs a generated image, generation follows the approved KIE.ai route
with the exact model named for the job locked in (no substitution, no
`openai/` API prefix), and the resulting file enters the job like any
other asset: recorded path, recorded hash, provenance in the sidecar.
Fixture and test work uses local, clearly labeled assets and no paid
generation. Client credentials are pulled at use time by the job that
needs them; nothing in this layer stores or prints credential values.

## Schema-gap note (for the contracts owners)

Recorded at MG-011 delivery, 2026-10-14. The MG-011 specification
lists twelve provenance and usage fields per asset. The shipped
assets schema carries seven of them (`path`, `sha256`, `kind`,
`usage`, `rights_ref`, `focal_point`, plus `id`). It does not carry:
dimensions, provenance source, inline rights or consent status,
intended role, crop constraints, protected regions, permitted edits,
per-asset placement, an explicit required flag, or derivative
linkage (`derived_from`, approval reference). The `kind` enum is a
coarse media class, not an exact media type. MG-011 enforces the
missing fields through the `asset-provenance.json` sidecar described
above and does not edit the canonical schema. Recommendation: a
future contracts item promotes the sidecar fields into the assets
`$def` (with `box` reused for protected regions), at which point the
sidecar retires and this layer reads the same fields from
`assets.json` directly.
