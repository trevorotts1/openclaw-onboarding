# Design Intelligence Bridge

The explicit handoff contract between Skill 72 (motion) and Skill 45
(Design Intelligence), written from the Skill 72 side only.

Skill 45 owns image style analysis. Skill 72 owns motion. The only
legal crossing between them is an explicit handoff: a reference goes
to a Style Analyst, and a style card comes back. Nothing else crosses.
Skill 72 never performs style analysis itself, never re-scores a card,
and never edits files inside the Skill 45 tree or the Presentations
tree. Any change inside those trees belongs to their owners; this
document is the Skill 72 side of the seam, plus the record shapes
Skill 72 keeps.

## Ownership

| Owner | Owns | Never does |
| --- | --- | --- |
| Skill 45, Design Intelligence | Style analysis, style cards, the 12-dimension model, the fidelity protocol | Motion design, timelines, decks |
| Presentations | Its decks and deck SOPs, including webinar, funnel, sales, and audience decks | Style analysis as a service, motion |
| Skill 72, Motion Graphics | Storyboards, style frames, design.json, timelines, renders | Style analysis, deck ownership |

Webinar, funnel, sales, and audience decks are not Skill 45 work and
not Skill 72 work. A design question about a deck does not route
through this bridge. When a Skill 72 scene plays inside a deck, the
scene still follows this contract for its own references, and the deck
around it remains Presentations' property.

## What Skill 72 sends

A bridge request is one JSON record kept with the job. It names exactly
what crosses and why:

```json
{
  "schema_version": "1.0",
  "request_id": "bridge-req-<job-scoped id>",
  "job_id": "<manifest job_id>",
  "company_id": "<manifest company_id>",
  "references": [
    {
      "asset_id": "<assets.json id>",
      "path": "<job-relative path>",
      "sha256": "<sha256 of the reference bytes>",
      "consent_basis": "<recorded consent basis, or null>"
    }
  ],
  "job_context": {
    "mode": "powerpoint_graphic | vsl_desktop | vsl_mobile | standalone_video",
    "content_scope": "<manifest content_scope>",
    "scenes": ["<scene ids the analysis serves>"],
    "question": "<the decision this analysis must inform>"
  },
  "dimensions_requested": ["composition", "color", "typography"],
  "requested_by": "<planner or director step that raised the request>"
}
```

Rules on the send side:

- Reference media travel with their hashes. The bytes analyzed are
  the bytes named; if a reference changes, its hash changes and the
  request is reissued, never silently re-pointed.
- `dimensions_requested` is a subset of Skill 45's twelve dimensions
  (render, composition, subject, color, grading, lighting,
  typography, layering, subject-background, negative space, workflow,
  unity). Ask only for the dimensions the job's question needs.
  Typography is dimension 7; a type question names it explicitly
  instead of asking for "the style".
- `question` is a decision, not a vibe: for example, whether a
  reference composition can carry a chart scene without losing the
  data, or which of two references a headline treatment should follow.
- Job context is the minimum the analysis needs: mode, scope, the
  scenes served, and the question. Client material beyond the named
  references does not cross.

## What comes back

A style card: Skill 45's record, in Skill 45's own terms. Skill 72
stores the card's identity and the fields it consumed, cited by id:

```json
{
  "schema_version": "1.0",
  "card_id": "<Skill 45 style card id>",
  "request_id": "<the bridge request it answers>",
  "reference_hashes": ["<sha256 values the card analyzed>"],
  "findings": [
    {"dimension": "composition", "finding": "<per-dimension finding in Skill 45's terms>"},
    {"dimension": "typography", "finding": "<per-dimension finding in Skill 45's terms>"}
  ],
  "fidelity": {
    "protocol": "skill45-fidelity",
    "average": 4.2,
    "minimum_dimension": 3,
    "hard_rule_violations": 0,
    "strikes": 0
  },
  "content_vs_dna": "<Skill 45's separation of the reference's content from its aesthetic DNA>",
  "state": "analysis_only"
}
```

Rules on the return side:

- Fidelity is Skill 45's protocol and Skill 45's numbers: average at
  least 4.0, no dimension under 3, zero hard-rule violations, with the
  3-strike escalation Skill 45 defines. Skill 72 quotes those numbers
  with the card id attached. It never rounds them into an approval,
  never re-scores them, and never averages them into a Skill 72 score.
- A card is analysis, not approval. It carries `state:
  analysis_only`. Design approval is a separate act, recorded in the
  job's approvals and checked by the style-frame gate.
- Findings arrive per dimension. A card that returns only a summary
  score has not completed the handoff; send it back through the bridge
  rather than filling the gap locally.

## How the output is used inside Skill 72

- Card findings feed two places: the canonical design.json token
  record (colors, type scale, layout numbers, where a finding
  supports a token choice) and frame.md, where the per-frame critique
  quotes the card's findings against the named reference in stronger,
  weaker, or different terms.
- The planner cites cards by id in the storyboard records it writes.
  The citation is the whole integration: no card content is copied
  into Skill 45's tree, and no Skill 72 file pretends to be a card.
- The bridge never silently restyles a job. A design change driven by
  a card lands in design.json and the style-frame records visibly,
  which changes the design revision, which stales any earlier
  style-frame approval. The gate (scripts/check_style_frames.py)
  blocks promotion until the current design is approved. That chain
  is deliberate: analysis can arrive at any time, but it only takes
  effect through the records.
- Ordering holds: analysis precedes style frames, style frames
  precede animation authoring. A card that arrives after animation
  has started is input to a redesign decision, not a patch applied
  mid-flight.

## Consent-first rule for real-person imagery

- A reference depicting a real person crosses this bridge only with a
  recorded consent basis naming why the imagery may be analyzed and
  used. No basis, no crossing: the request is blocked with that
  reason, and the job proceeds without the reference or not at all.
- A synthetic lookalike is not a workaround. Substituting a generated
  near-copy of a real person to dodge the consent question violates
  the rule it pretends to satisfy.
- Consent discipline belongs to the job's records (intake and asset
  provenance) as well as to this bridge. The bridge checks the basis
  is recorded; it does not manufacture one.

## When there is no card

If Skill 45 analysis is unavailable, or no card exists for a reference,
the job makes its design decisions job-locally and labels them as
such in frame.md: designed here, not analyzed. Absence of a card is a
fact to record, never a gap to paper over with a locally invented
score.
