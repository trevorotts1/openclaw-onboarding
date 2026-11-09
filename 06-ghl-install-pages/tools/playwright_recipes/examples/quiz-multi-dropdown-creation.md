Quiz Multi Dropdown uses native type `MULTIPLE_OPTIONS` and the existing
`quiz_multiple_choices` action / `multiple_choice_questions` front door. Prefer
the explicit new empty-page mode for the captured working placement path.
The record has `question`, `placeholder`, `short_label`, `unique_key`, `required`
and `options`. It has no `query_key` or `hidden`; those extra properties are
refused. Single Dropdown remains a distinct type with its measured Query Key.

Multi Dropdown exposes no native `#fieldQueryKey`. The writer opens the exact
Advanced Settings header only when its controls are not already visible and
reads `#uniqueKey input` plus `#custom-field-label input`. A new authored Unique
Key must be explicit and nonempty. Existing blank key values may be preserved,
but the generated placeholder is retained as opaque metadata and never used to
derive a key, an API field ID or a `contact.` prefix. Raw Unique Key and Query
Key values stay in their actual separate native property namespaces.

The default Custom Field Name and Unique Key placeholder are read before option
count changes and protected before question properties, after option labels,
and through the complete saved independent readback. The script never renames
the custom field. General Question edits might affect that advanced name in a
native version not yet accepted; any unexpected change stops the operation.
Unique Key authoring blurs through the unchanged Custom Field Name input and
requires the exact authored literal value. Native prefixing, normalization or a
different post-save value is refused rather than guessed or accepted.

Two to fifty options is **this adapter's bounded authoring guard**, not a
measured native platform minimum or maximum. Native capture measured three
defaults, one Add from three to four, one Delete from four to three, a label
edit, and independent property-panel reopen. Larger or smaller accepted counts
have not been proven live. Each Add/Delete uses the exact active owner control,
one click and an exact one-row delta, retaining previous UUID/index identities.
Delete uses only the captured last-option trash glyph. Unexpected counts,
changed retained rows or an uncertain result stop without repeating that click;
the enclosing interrupted journal prevents replaying a partial mutation.

After every count delta the property panel is read again. Retained option
categories, raw scores, enabled states and jump states must match their complete
prior prefix; all non-option question and advanced identity metadata must remain
unchanged. A new row must match the captured zero-score, disabled-score,
non-routing defaults and prior unassigned-category display. The complete resized
snapshot is then checked once more before the first authored question property,
so a changed category cannot silently become a new accepted baseline.

Count changes happen before authored labels. Transient rename collisions are
refused before the first drag. Default and final sidebar Label/category/raw
score/disabled/jump inventories must match the canvas owner; Multi Dropdown has
no Spread control, and no Hidden setting is invented. The old full page prefix
is verified before property writes, and fresh visible native field identities
cannot reuse an inventoried prior choice owner.

The code requires outer Save plus actual list departure and full independent
editor reopen. Positive native creation and property-panel readback were
captured; successful outer Save, saved Unique Key readback, native acceptance of
the full bounded option range, submissions and functional behavior remain
separate pending proof. Source/fixture tests do not certify those outcomes.
