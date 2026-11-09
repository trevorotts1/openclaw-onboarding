Native choice creation uses captured Quick Add tiles. `CHECKBOX` with three
options selects Multiple Choice; `RADIO` with three selects Single Choice and
`RADIO` with two selects Yes / No. Supply the exact existing quiz URL, title, every ordered
page and the complete text/key/flag properties of every prior question. Existing
CHECKBOX records also require their exact ordered `options` array. Existing
RADIO records may optionally bind their two or three exact options; all existing
RADIO native input names/IDs, option labels, scores and categories are retained
read-only either way. New questions require the captured count of unique
authored values and explicit `acknowledge_shared_field_options: true` because
the native editor warns that option changes can affect field reuse.
An option rename that would transiently collide with another still occupied
default label is refused before insertion; no invented staging labels are used.

`SINGLE_OPTIONS` with three options selects the captured Single Dropdown tile.
Its records omit `hidden` entirely: the native quiz General panel has Required
and no Hidden control, whose unexpected appearance is refused. The default key
is `dropdown`, the generated label has five characters and the active canvas
contains a typeless, ID-less, name-less `input.dropdown-input.form-placeholder`.
Only the exact selected widget's `#options-card .option` labels are read or
edited. Each has `option-label-UUID-N` ID and `UUID_N` for attribute; there are
no per-option disabled checkbox/radio input values to pretend to verify.
The separate native property option Label values, categories and scores must
match independently after editing, saving and reopening. Three Jump switches
are retained; a Spread control is absent for this captured type.

One native drag inserts seven pixels inside the last question's lower edge on
the exact target page, using fresh bounds and the captured repeated final pointer
events. Normal populated canvases need no blank tail. A changed page count stops
immediately. A new CHECKBOX must match default `checkbox` Query Key, generated
five-character name and three disabled inputs labeled `Option 1`, `Option 2`,
`Option 3`. RADIO uses default `radio`, a six-character generated name, and
either those three options or `Yes`, `No`. Closing the drawer can deselect all
widgets normally; the exact new index-bound label is clicked explicitly, then
the writer requires one selected owner before properties. No API dependency
creation occurs and no API field ID is inferred.

The writer opens native property controls, authors question text, placeholder,
Short Label, Query Key and Required/Hidden flags, then fills the three native
contenteditable option labels. Disabled checkbox values must update exactly;
sibling option identities remain bound by their locally parsed UUID/index.
Native input and label IDs are duplicated, so all reads use scoped input or
label selectors rather than global IDs. New RADIO instead exposes a measured
UUID input name, `UUID_N` IDs and `option-label-UUID-N` label IDs. The name and
all IDs must be fresh against every inventoried prior RADIO before any new
question/option properties are authored. Existing default `radio` Query Keys
may remain while the final new authored key must be distinct. Existing RADIO and CHECKBOX option
labels, categories, raw score strings, enabled states and native input values
are retained in the runtime inventory. This path also preserves the full
all-false Jump To/Spread switch inventory; active jumps or spread require a
separate capture and fail before creation. It does not configure answer routing.

The outer runner must journal intent before the single drag, bind the complete
configuration hash on first execution and replay, and refuse mixed assessment
actions in this operation. Completion requires a real Save and independent
quiz-list reopen with full page, property, option and scoring inventory readback.
Source/fixture checks do not prove live saved behavior or submitted outcomes.

Every new native choice UUID is also checked against visible prior choice
option identities and existing input names, including cross-type reuse. No
global API identity or absence outside this exact editor is inferred.
