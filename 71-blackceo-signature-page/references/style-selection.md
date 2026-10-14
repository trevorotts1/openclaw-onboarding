# Style selection record: `style-selection.json`

Skill 71, Item 10 as rebuilt by FIX-PLAN Amendment 6, Part B1.

## What this is

Before any prompt is authored for a run, the run records **which style
system governs each image** in `image-inventory-prompts/style-selection.json`.
The record is the artifact every later style check binds to: the prompt
validator's lock/anchor expression checks, the denylist screen, the
contamination screen, Item 15's declared-style exemptions, and the
review form a reviewer scores against (Part B5). It replaces the
bible-carried `style_block` string the withdrawn Item 10 design assumed;
external styles are encoded in prompts as descriptive language, never
pasted verbatim (image guide v5, element D and fidelity gate check 9).

A run with no selection record cannot close `image-inventory-prompts`
(gate wiring: GATE-CHANGE-REQUESTS.md, GCR-S2-4). The Page Visual Bible
remains the page-level lock; the selection record is per image or per
set, for the cases where images in a set legitimately differ.

## File shape

```json
{
  "schema_version": 1,
  "selections": [
    {
      "applies_to": ["IMG-001", "IMG-002"],
      "source_library": "photographers",
      "style_id": "VDL-005",
      "branded_name": "White Field Intensity",
      "mode": null,
      "blend": null,
      "hybrid_flag": false,
      "extraction_ref": {
        "path": "references/style-traits/photographers.json",
        "sha256": "<sha256 of the extraction file the run was authored against>"
      },
      "declared_series": false,
      "declared_style_traits": []
    }
  ]
}
```

`applies_to` is either the string `"all"` or a list of inventory image
ids. Where two records claim the same image, the record later in the
list wins for that image; authoring tools should avoid overlaps.

The machine-readable schema is `references/style-selection.schema.json`.
`scripts/validate_prompt.py` performs the structural checks it depends
on (stdlib only) and fails closed on a malformed record.

## Fields

- `source_library`: one of `image-guide-sauce-only`, `photographers`,
  `cinematic`, `visual-artists`.
- `style_id`: the VDL, CIS, or ART identifier, or the branded system
  name where the library uses one (sauce-only runs).
- `branded_name`: the name a compliant prompt carries. For Visual
  Artists selections the validator checks the prompt CARRIES this name
  (assembly slot 1); for every library, an undeclared foreign branded
  name or style id in a prompt is contamination and fails.
- `mode`: REQUIRED (non-null) when the selected entry is multi-mode
  (Photographers VDL-006, VDL-032, VDL-036 class; Visual Artists
  entries 26, 32, 39, 42 and entry 22's core modes), because no single
  lock set exists until a mode is chosen. The value must be one of the
  mode names recorded in the extraction entry. Absent/null for
  single-mode entries.
- `blend`: Cinematic only. `null`, or
  `{"primary_style_id": ..., "secondary_style_id": ...,
  "secondary_traits": [1 to 3 named traits], "owner_authorized": true}`.
  A declared blend whose `owner_authorized` is not `true` does NOT
  pass: Image Guide v5's master rule activates exactly one external
  style per page, and Cinematic Global rule D's two-system blend is
  permitted inside Skill 71 only with Trevor's recorded authorization
  (FIX-PLAN conflict N2). The existence of rule D is not standing
  permission.
- `hybrid_flag`: Visual Artists only. `false` unless the user
  explicitly requested a hybrid (that guide's exactly-one-system rule);
  when `true`, the record must also carry
  `"hybrid_requested_by_user": true`.
- `extraction_ref`: path (skill-relative) and SHA-256 of the trait
  extraction file used. The validator verifies the hash before trusting
  the extraction, so a run's prompts are always judged against the
  extraction they were authored under. `null` only for
  `image-guide-sauce-only` selections.
- `declared_series`: `true` when a serial system is selected; feeds
  Item 15's declared-series exemption (Part D, Item 15 delta).
- `declared_style_traits`: the run-level declarations Item 15's
  exemptions read, drawn only from `centered composition`,
  `spacious framing`, `sparse negative space`, `uniform ratio`, and
  only where the selected style mandates them (the extraction entry
  records which traits a style makes available for declaration).
- `declaration_block`: REQUIRED for procedural-class styles (for
  example VDL-045): the declared editorial world for the image, with
  fields `era`, `social_world`, `character`, `tone`, `set`,
  `camera_language`, `styling_logic`, `beauty_logic`, `color_logic`,
  per the entry's own procedure. Trait checks are replaced by the
  declaration-block check for these styles (Part B3(vii)); coherence
  among the declarations is reviewer judgment (Part B6), never a
  mechanical pass.

## Handling rule for the denylist (Part B3(iv))

The per-library denylist files under `references/style-traits/`
(`denylist-photographers.json`, `denylist-cinematic.json`,
`denylist-visual-artists.json`) are HUMAN-ONLY validator data. They are
loaded by `scripts/validate_prompt.py` only. They must NEVER be copied
into prompt context, worker briefs, or any run file a prompt author
reads: a screen whose wordlist leaks into the author's context
manufactures the failure it exists to catch. The selection record never
contains denylist names; it names the branded system only.
