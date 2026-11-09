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
The handler reads every requested question and the requested existing result-tier
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

## Marketing-quiz result copy

`quizzes.configure` accepts `configuration.result_page` for native Header
business-name copy and Call to action content/button text/HTTPS destinations.
See `quiz-result-copy.json`; replace every previous-value placeholder with the
actual native inventory before execution. Every requested old/new field pair
must use the same keys. No business name, offer copy or destination is invented.

Dynamic CTA variants require the exact existing dynamic-content mode and score
source. The handler never changes those settings. It selects only the editing
tier view, preflights every requested variant before writing, checks all authored
variants again before Save, then saves the native modal and the outer quiz once.
Independent reopening verifies every requested score/tier-specific value. Static
CTA mode has one variant without a tier and must already be static. The captured
Header business-name editor remains visible when its preview text is disabled.

The score-source reader uses its captured label and smallest unique native-select
container, explicitly excluding the tier picker and rejecting ambiguous shapes.
The editing-tier picker uses its captured native ID; no global select indexing.
Only literal plain text is inserted into the RTE. URL changes require HTTPS
without embedded credentials. Untouched content/button/link values within each
requested variant are compared before and after Save. Styling, global dynamic
mode/source changes, uploads and other result sections remain outside this
handler. `behavior_verified` and `submission_verified` remain false. No optional
or live tests have been run for this implementation pass.

## Existing result-tier layouts

`quizzes.configure` accepts an existing native tier layout with any complete
integer-percentage partition, rather than imposing three rows. Supply `tiers`,
`expected_tier_labels`, and `expected_tiers` with every current label and previous
range in exact row order. The native popover must expose exactly that many
label inputs and two range inputs per row. First/last range endpoints must remain
locked at 0/100, and all interior controls must be editable before the first fill.

Every current range and label is checked during preflight. After editing, native
Save and independent editor reopening must preserve every desired row. The
operation edits existing rows only; it never presses Add tier, creates/removes a
row, or changes a template. Existing three-tier jobs remain compatible; adding
`expected_tiers` gives them the same exact old-range guard.

See `quiz-existing-tier-layout.json`. Native layout limits, native styling/media
controls, and submitted result behavior remain separate from this implementation.

## Authored Radio questions through the existing API fallback

`radio_dependencies.provision_radio(inputs, evidence_root, capability=receipt)`
creates approved Radio contact definitions or reuses exact inventoried IDs, then
returns `object_fields` and fresh `field_dependencies` for the existing native
survey placement job. It does not create fields in the browser.

Inputs contain only `location_id` and `questions`. Each question requires
`name`, `field_key`, `data_type:"RADIO"`, at least two unique text `options`,
`expected_id`, and Boolean `allow_creation`. Reuse requires the exact existing
ID. Creation requires explicit `expected_id:null`, `allow_creation:true` and
proven absence of both the name and key in the complete same-location inventory.
A returned generated key must match the authored key; mismatch retains the
created ID for reconciliation and never retries POST.

This deliberately uses the existing caf legacy `/custom-fields/` fallback,
whose body already carries `options` and `objectKey`. The public v3 create row
remains `B-OPTIONS-FIELD`: its currently published request schema does not expose
choice-option authoring. No v3 claim or unsupported route substitution is made.

The private host must supply a fresh `skill44-radio-fallback-capability/1`
receipt from actual measured same-location list, create and independent get
responses. The exact route, method, successful status, response hash, location-PIT
auth class, required scopes and version must be present. The measured create/get
sample must prove the same Radio ID and ordered options. Versions are checked
against the existing caf resolver rather than introduced in this helper. A
` supported:true` flag or a documentation placeholder is insufficient. No
capability measurement performs a write here.

`radio_dependencies.build_survey_questions(inputs, evidence_root, page=page,
capability=receipt)` chains this provisioning with the existing exact-slide
native placement. It additionally requires `location_name`, the exact existing
survey `start_url`, `expected_slide_count`, complete `slide_labels`, and
`target_slide`. The managed host owns the signed-in Page. The survey and slide
are read before any schema creation. API and native intent journals are retained
separately; an uncertain stage stops. Completed native replay retains its original
receipt timestamp so refresh of a dependency GET does not repeat placement.

The standalone `radio_dependencies.py --inputs ... --capability ...
--evidence-root ... --check` validates without network or evidence writes. Omit
`--check` only for an authorized dependency provision. Native placement is the
managed-Page function above or the existing `surveys.configure` host operation.
This implements text Radio questions on existing survey slides. Other widget
types, new survey creation, quiz widgets, and native submission proof remain
separate requirements. No live field creation was performed in this build.

## Business-name display in quiz results

`configuration.result_page.expected` and `changes` also accept the exact
Boolean key `business_name_enabled`. The native Header switch is specifically
labeled **Business name**. It hides/shows that name in the result header; the
logo, Header layout and other sections remain independent. This does not mean
the whole Header is hidden. See `quiz-business-name-visibility.json`.

Both previous and desired values must be real Booleans. The current state and
captured label are checked before authoring. The business-name RTE remains
visible with the switch off. A switch-only change preserves its complete stored
HTML formatting and plain text before Save and after independent reopening.
Existing business-name text edits also preserve the current enabled state unless
a matching explicit old/new Boolean pair is requested. These settings can share
a job with tier-specific CTA copy while each old-value guard remains required.

The switch/visible-RTE behavior was inspected in the native result modal on
November 9, 2026 and cancelled without saving. The Python handler has focused
control/guard/replay coverage; it has not performed a native submission or result
acceptance run. Both behavior and submission proof remain pending.

## Quiz result Header layout

`configuration.result_page.expected/changes.header_layout` accepts the exact
existing native choices `Default` and `Reverse`. The handler binds the two
captured non-button cards and their selected-class state, requires exactly one
selected layout, and preserves the business-name enabled flag and stored text.
A layout-only edit also preserves stored business-name HTML formatting and the
Header logo URL, width and height through Save and independent reopening.
No logo URL is fetched and no uploader is opened. See `quiz-header-layout.json`.

The native card selection was observed and cancelled on November 9, 2026.
Python control/identity/collateral-state checks are covered offline; submitted
result behavior remains pending. Other Header media changes are separate work.

## Native Short Answer question creation

`quizzes.configure.configuration.short_answer_questions` is a dedicated native
creation job. Supply the exact existing quiz name, complete ordered `pages`
inventory, `target_page`, and authored `questions`. Do not combine this job with
scoring/result edits. See `quiz-short-answer-creation.json`; every existing
question property must come from the native inventory.

Each inventoried page carries its exact label and every existing question's
`field_type`, `question`, `placeholder`, `short_label`, `query_key`, `required`,
and `hidden`. Current supported existing widgets are `TEXT` and `RADIO`; new
questions use `TEXT` from the captured Short Answer tile. Authored question labels
and Query Keys must be globally unique and disjoint from the complete existing
inventory. An existing default key `single_line` does not prevent insertion:
the one-widget delta and exact new ordered index bind the selected new widget,
whose captured default key is checked before authoring its final distinct key.

The canvas's Short Answer input exposes no stable field ID, name or explicit
type. The handler does not fabricate one. It selects each actual canvas widget
and independently reads its native Question/Placeholder/Short Label/Query Key
properties plus Required/Hidden checkboxes. Every existing property and rendered
input binding is retained before the first drag. Empty pages require the captured
inside-canvas drop placeholder, never an inferred zero field count.

One real native pointer drag appends a Short Answer inside the exact requested
page canvas seven pixels inside the last question's lower edge, using fresh
element-relative bounds and the captured repeated final pointer events. Normal
populated canvases end at that wrapper and need no blank tail. An unsafe edge
or uncertain insertion stops without a second drag. The new widget
must match the captured active TEXT/default-query shape before authoring its
properties. Later inventory must prove one exact new question on the intended
page and unchanged existing questions; Save and independent reopening must
preserve the complete desired inventory.

The native type/drag/property controls were inspected November 9, 2026, and the
unsaved capture was discarded. This handler performs no separate dependency API
call (`dependency_api_used:false`); backend effects and submitted answer behavior
remain unverified. Optional/live acceptance is deferred. New survey shells, other
question types and answer routing remain separate implementation requirements.

## Integrated checkpoint boundaries

The native condition stack implements ordered Show/Hide rules, homogeneous
AND/OR clauses within each rule, and one explicit rule per target. An explicit
complete `expected_rules` list enables same-count edits, including captured
tail-clause removal while preserving the initial If row. Condition-card removal,
reordering and count changes remain separate requirements. A dedicated outcome
stack also appends Redirect to URL, Display
custom message and Disqualify lead effects while preserving prior card HTML.
See `form-condition-stack-edit.json` and `form-condition-outcomes.md`. Nested
mixed predicates remain a separate requirement.

Dedicated `configuration.multiple_choice_questions` jobs create captured
CHECKBOX Multiple Choice and RADIO Single Choice/Yes-No questions. Dedicated
`configuration.written_answer_questions` jobs create TEXT Short Answer,
LARGE_TEXT Long Answer and NUMERICAL Number questions. Their complete existing
question inventories, exact target page, authored final keys and shared-option
acknowledgment are required as described in `quiz-multiple-choice-creation.md`
and `quiz-written-answer-creation.md`. New keys must be distinct from existing
keys, but a prior native default key does not block index-bound insertion.
Answer routing and uncaptured question types remain separate requirements.

The choice frontdoor also accepts captured `SINGLE_OPTIONS` Single Dropdown
questions with three explicit options and no `hidden` property. It does not
invent a Hidden control or treat a different widget's settings as its own.
An explicit `create_page:true` and generated `new_page_label` author one question
on a new empty page at `target_page:N+1`; the original full inventory and hash
remain bound through saved readback and completed replay. See
`quiz-new-empty-page-question.md`. The populated-page append path remains a
measured gap for Dropdown widgets, and Multi Dropdown has a separate unimplemented
identity/control contract. Positive UI capture and offline checks are not saved
or submitted acceptance.

API-backed existing Single Dropdown and Large Text schema placement uses
independent native Query Key values; no canvas API ID is fabricated. Initial
adoption of a disabled API-picker row is refused because that observed state
does not link the API ID to one canvas widget. An exact new insertion can replay
from its original completed journal. Radio placement instead binds the actual
opaque input name to the API ID and preserves its measured native Query Key.
The new question and condition handlers require complete exact receipts on both
fresh completion and replay. Their native functional/submission acceptance
remains pending.

The payment-owned Order Confirmation handler supports the captured uniquely priced product contract only. Catalog GET identity, native selected product and reopened mode are verified by code; charges, payment behavior and submitted journeys remain pending. See `form-order-confirmation.md`.
