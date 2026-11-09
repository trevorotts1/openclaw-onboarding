Explicit new empty-page authoring adds one requested page and one requested
question in the same native runner intent. Supply the complete original pages
and their question inventories, `create_page: true`, the exact expected new
`new_page_label`, and `target_page` equal to the original page count plus one.
The new label is the captured generated `Page N+1` caption, validated before
Add Page. It is an expected native label, not a request to rename the page.
This mode accepts one question; further pages use separate explicitly authored
jobs with updated full prior inventories. Existing-page mode never switches
to page creation after an unexpected drop.

The writer binds the last original `.survey-form-container.flex` owner and its
one `button#add-slide-button`, while the total Add Page button count must match
the complete page count. It clicks exactly once. The new count, exact new
heading, visible `Drag and drop components` marker, scoped Add Elements control
and complete unchanged old question/option/scoring inventory must all be proven
before any question drag. No API page ID is inferred and uncertain Add Page
outcomes are not repeated.

Add Page can automatically open the Quiz Element drawer. The drag rail reuses
that drawer when present. Full metadata verification may require closing it;
if absent afterward, the rail opens only the new empty target owner's
`button#add-elements-button`. It then drops at the center of that measured empty
canvas. Changed owner counts, wrong new index/type, old metadata drift or lost
save stop the operation. Native UI inspection demonstrated the explicit new
empty-page path for Single Dropdown and Multi Dropdown, independently of their separate
per-type property/identity work. Multi Dropdown is not implemented by this
checkpoint. Populated-page append acceptance is still a
separately measured gap for those widgets.

The runtime owner plan is a deep copy extended after successful page creation.
The original payload remains unchanged and binds the configuration hash and
receipt target. Save and independent list-to-editor reopening must retain all
old pages plus the exact new page/question. A staged page, property input value
or offline regression is not live saved or submitted proof.
