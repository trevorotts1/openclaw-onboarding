# Diagram Patterns: Causal Diagrams and Spatial Explanations (MG-017)

This reference documents the four mechanism patterns implemented in
`runtime/src/diagrams/`, the rules that make a diagram a demonstration
rather than a list of labels, and the claim discipline that governs
what a diagram may be said to show. The patterns register as catalog
components C04 (Object-through-mechanism) and C09 (Causal/branching
diagram).

A diagram earns its place by showing relationships and
transformations: a viewer follows the same subject through the
mechanism and sees cause produce effect in the right order. A row of
process labels with arrows drawn between them, where nothing travels,
nothing changes, and nothing is caused, is not a mechanism graphic; it
is a text list with decoration, and the planner should not select a
diagram component for it.

## The four patterns

### flow_through

One persistent subject travels a path through labeled stages in causal
order and arrives at the final stage. Use it when the explanation IS a
sequence: how a lead becomes a delivery, how a request becomes a
result. The subject is the viewer's anchor; stages activate only when
the subject arrives, so the order on screen is the causal order, not a
reveal order chosen for looks. If there is no identifiable thing that
travels, this is the wrong pattern.

### branching_decision

One input reaches a decision node and exactly one declared branch is
taken. The untaken branches are drawn as real alternatives and are
never traveled. Use it when the explanation is a rule: if this, then
that, and here is the basis for the choice. The selected branch is
declared in the scene document (`selected_branch_edge_id`), never
inferred from geometry, copy, or which outcome looks best. A branching
diagram whose selection is not declared is refused at validation,
because an inferred selection can silently change meaning when labels
move.

### before_after_system

The same objects appear in two states with a declared transformation
between them. The subject is one of the objects: its identity persists
while its state flips at the transform midpoint. Use it when the
explanation is a change of state rather than a journey: unsorted to
sorted, manual to automated, scattered to organized. Both states stay
labeled and comparable; neither is hidden to make the change look
bigger than it is.

### bottleneck_removal

A flow chain whose constraint stage first constricts the flow (the
subject slows and creeps through the narrow stage) and is then visibly
widened at a declared relief frame while flow continues through it and
speeds up. Use it when the explanation is a constraint and its removal:
the queue at review, the single approver, the narrow step. The relief
frame must fall while the subject is inside the constraint; a "relief"
that happens before anything arrives, or after everything has passed,
demonstrates nothing and is refused at resolution.

## Rules that make it a mechanism

- **Persistent identity.** Important objects carry ids that never
  change across frames. The subject's position is a deterministic
  function of frame, computed from the resolved path, so the same id
  is trackable at every proof frame and on every seek. If a viewer
  cannot point at the same thing at the start, middle, and end, the
  scene is not demonstrating a mechanism.
- **Causality in time.** A downstream stage cannot activate before its
  upstream cause completes. Activation frames are computed, not
  choreographed by feel: path nodes activate when the subject arrives;
  other nodes activate when their incoming edge finishes drawing; no
  edge starts drawing before its source activates. The test suite
  evaluates this mechanically on the frame functions.
- **Connection drawing is progress, not fades.** An edge draws as a
  growing prefix of its own path. A path edge draws exactly as the
  subject traverses it, so the drawn tip is the subject's position.
  Fading a whole edge in would claim the connection exists before the
  cause has traveled it.
- **Paths terminate at their targets.** Every edge polyline ends
  exactly at its target node's entry anchor (measured tolerance
  1e-6 source pixels, for float hygiene only). A path that stops near
  a node, or overshoots into it, misstates the relationship.
- **Labels never collide, and never shrink.** Label boxes are sized
  from text measured with the actual font binary at the declared
  label size. When a pattern cannot fit the canvas without collision,
  layout returns a named impossibility (`MG_LAYOUT_IMPOSSIBLE`, for
  example `chain_exceeds_canvas`) instead of overlapping labels or
  shrinking essential text below its floor. The honest responses to an
  impossibility are: shorten the labels, split the chain across beats,
  reduce the number of outcomes shown, or use a larger canvas.
- **Depth only when it clarifies.** These primitives are flat by
  default. Spatial depth is used only when the relation itself is
  spatial (see C10), never as decoration on a causal diagram; depth
  that does not clarify the relation competes with it.
- **The title proves nothing.** Changing only the title changes no
  geometry: node boxes, edge paths, and the subject trajectory are
  functions of the diagram spec alone. A test that a new headline can
  satisfy is a test of the headline, not of the mechanism, and the
  suite carries the retitled-twin negative to keep it that way.

## Claim discipline

A diagram shows a mechanism. It does not prove a business outcome
unless its data carries that proof. The fixture scenes say this in
their own disclosure lines, and production scenes must do the same:
words like "this process doubled conversions" belong to evidence, not
to a mechanism graphic. Where a diagram illustrates a process with
invented or exemplary content, the scene is labeled illustrative, in
the same spirit as the reference suite's fixture labeling. A diagram
may honestly claim: the steps, their order, the branch rule, the
constraint, and the transformation. It may not claim results.

## Registration and integration notes

- C04 and C09 are registered in the catalog with closed input schemas
  from `runtime/src/diagrams/schema.ts`, proof contracts, and the
  MG-017 test runner (`runtime/tests/run-diagrams.ts`). C04 registers
  the flow_through, before_after_system, and bottleneck_removal
  patterns; C09 registers branching_decision and flow_through.
- Engine note: Section 7.1 names Hyperframes as C04's default engine.
  The primitives and frame functions are engine-agnostic, but the only
  proven diagram render path at this item is the Remotion composition
  in `runtime/src/diagrams/render/`, so both entries register Remotion
  dispatch only. A Hyperframes diagram generator is future work for
  the adapter items; the catalog does not claim it until it exists.
- The canonical contracts schema is unchanged and remains C05-only.
  Contracts-level job dispatch for C04/C09 scenes (orchestrator
  wiring, in the MG-018 pattern) is an integration note for MG-025.
- The diagrams render harness carries its own shared-runtime resolver
  because the Remotion adapter's resolver is module-private; MG-025
  may export a shared resolver and retire the duplicate.
