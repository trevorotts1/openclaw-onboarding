# Assessment implementation additions

Manual/live and optional local testing is deferred at the owner’s request. These
examples describe implemented control paths, not a live acceptance claim.

## Quiz question properties

`quizzes.configure` accepts `placeholder` and `short_label` on an existing
choice question, with matching `expected_placeholder` and `expected_short_label`.
Empty strings are explicit values. Existing question text/query identity, option
labels and option counts still guard the target. Shared-field editing requires
`shared_field_change_ack:true`. Query-key authoring is also available through
`query_key`, but requires every existing choice question in the configuration,
unique existing and desired Query Keys, and no direct key swap into another
question’s existing identity. All identities are read before the first write.
The handler reads every requested question and the requested existing three-tier
layout before writing the first authored value.

See `quiz-question-properties.json`.

## Quiz category renaming

`quizzes.configure` also accepts `category_changes`, an array of exact
`{"expected_name":"Existing category","name":"Approved new name"}` pairs.
All existing category identities and collisions are checked before editing.
Overall Only is reserved; swaps into an occupied category name are refused.
Native Submit saves the same category entry, then independent reopening checks
the new name. Category creation and choice scoring can share the job only when
their requested category names match the post-rename inventory.

## Ordered survey forward-rule stacks

`surveys.configure` accepts a `configuration` containing `expected_slide_count`,
all native `slide_labels`, and a nonempty `rules` array. Every rule uses the same
existing forward Jump To schema: `source_slide`, `target_slide`, `if_field`,
`operator`, optional `value` and optional `source_placeholder`. Unary operators
Is Empty/Is Filled do not accept an ignored value.

This is a complete ordered native condition stack, not an append into arbitrary
existing logic. The existing conditions must be an exact prefix of the requested
stack; unrelated or differently ordered conditions stop before writing. Duplicate
conditions with conflicting destinations are rejected. Every source/target and
existing conflict is inspected first; each missing rule is authored once; every
requested rule and its priority are independently inspected after the last Save.
A retained uncertain writer journal still requires explicit reconciliation.

The runtime receipt binds the configuration hash and rule count, with
`behavior_verified:false` and `submission_verified:false`. Native behavior remains
deferred. This does not implement AND/OR conditions, non-Jump-To effects, backward
loops, new question types, custom-field schema creation or completion actions.
See `survey-rule-stack.json`.

## Existing survey object questions

`surveys.configure` also accepts the API-inventoried object-field shape in
`survey-object-fields.json`. Replace every placeholder with actual inventory.
The example `observed_at:0` is deliberately stale: the host must supply a real
recent successful same-location API GET receipt, never a fabricated timestamp.
The dependency definition and requested field must match exactly. The captured
native type is currently RADIO; other data types stop before insertion.

`target_slide` selects one existing slide from the complete numbered
`slide_labels` inventory. The wrapper selects that owner before the native
Add Object Fields operation, then independently reopens and reselects it. Other
slides’ field counts must remain unchanged. Contact-field schemas and choice
options are API-owned; this operation only places an existing exact ID/key.

The native result retains submission/behavior verification as pending. The
owner deferred optional, manual and live tests; these source additions are not
claims that a Python job ran against a client survey.
