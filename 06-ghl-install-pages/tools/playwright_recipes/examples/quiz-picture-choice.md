# Picture Choice on an exact existing quiz

Use `quizzes.configure` with the exclusive `configuration.picture_choice_questions`
object. It accepts the same owner/page fields as the captured question writers:
`expected_quiz_name`, full ordered `pages`, `target_page`, and `questions`, plus
`acknowledge_shared_field_options: true`. Exactly one new question or one explicitly indexed existing Picture Choice update is supported.
The target must be a positively inventoried empty page, or explicitly append one
with `create_page: true` and the exact native `new_page_label: "Page N+1"`.

The new question has `field_type: "PICTURE_CHOICE"`, explicit `question`,
`placeholder`, `short_label`, `query_key`, `required`, `hidden`, and
`expected_persisted_unique_key`. The last value is the caller's exact expected
native Contact key (for example `contact.your_next_move`); the writer does not
derive it or write a guessed key. The ordered two-to-fifty `options` must each declare:

```json
{
  "label": "Authored option label",
  "image_url": "https://example.com/exact-approved-canonical-image.png",
  "media_button_name": "exact-file.png exact-file.png Dimension icon"
}
```

The media button name and canonical URL must come from the approved existing
Media Storage catalog. Before selecting a tile, the writer checks its exact
captured thumbnail URL; after selection, it verifies the canonical image on the
correct option card. The captured indexed Add/Delete controls resize the tail
without changing retained card owners. Optional `presentation` controls the label, fit, Other and spread settings as described below. Uncaptured multiple-selection modes remain unsupported.

Prior Picture Choice questions in `pages` use `field_type: "PICTURE_CHOICE"`,
the complete text/key/flag properties, actual persisted `unique_key`, and the complete ordered
`options` containing only `label` and `image_url`. Ordinary question inventories
retain their existing schemas and must still pass their captured readers.

On first native Save, the newly added Picture Choice field changes from one
transient UUID to one persisted 20-character owner ID. Its unused Multiple
selection switch disappears. The writer permits only those captured transitions
on the new question, verifies the caller-declared persisted Unique Key, and
preserves all existing page/question identities. A mismatch or interrupted save
requires reconciliation; the same job cannot insert another question on retry.

This handler is a bounded source implementation based on native capture and
focused offline tests. Installed Python execution, respondent submissions,
scoring/results and learner behavior still require separate acceptance. Mixed `question_batches` now accept Picture Choice before or after the other
captured writers. Supply each complete following page inventory with the
persisted `unique_key` and only `label`/`image_url` in prior picture options.
Creation-only media-button names and `expected_persisted_unique_key` belong only
to the new Picture Choice request. Subsequent writers preserve the native media,
owner and style inventory. Each batch keeps its own journal and receipt; an
uncertain Picture save blocks later writers and never repeats the earlier prefix.
Every later batch still requires an explicit new empty page. Short Answer
batches use the complete-inventory written-answer writer with TEXT only.

## Update existing Picture Choice cards

Add `update_question_index` (zero-based within `target_page`) to the same
`picture_choice_questions` object. Supply the complete current quiz inventory in
`pages` and exactly one desired question in `questions`. Its
`expected_persisted_unique_key`, text, Query Key, Required and Hidden values must
match the indexed existing Picture Choice. This mode edits option count, labels,
approved catalog images and optional presentation while retaining that field.
It cannot create a page or replace a different widget type.

The existing question's `options` contain current `label` and `image_url`. The
desired `questions[0].options` contain the authored label, image URL and approved
`media_button_name` shown above. Unchanged images are retained without opening
the chooser. Filled cards use their exact indexed Change Image action.

The writer checks the whole quiz before editing, keeps persisted field IDs and
keys, verifies every sibling after editing, and independently reopens after
Save. Saved-state mismatch fails the job. This source addition has focused
offline coverage; final maintained-script execution is separately unverified.

The optional `presentation.image_fit` accepts the native `Cover`, `Contain`, or `Fill` selection. Omit it to preserve the current fit. Saved state is independently reopened and checked; live acceptance remains unverified.

The optional `presentation.spread_to_columns` selects the native spread switch. Set `columns` to null when disabled; when enabled, provide the desired column count.

The optional Boolean `presentation.other_option` enables or disables the native Other card; its fixed label and image placeholder are verified against the switch on readback.

See `quiz-picture-choice-mixed.json` for a complete copy-and-adapt `quizzes.configure` request with Contain, Other enabled, Spread disabled, and ordinary questions before and after the picture question. Replace the fixture account, URLs, names and catalog identities with independently inventoried values.

## Upload a local image

For a direct, exclusive Picture Choice request, an option may instead specify `{"label":"Choice 1","local_file":"/absolute/path/approved.png","sha256":"<64 lowercase hexadecimal characters>"}`. PNG and JPEG files up to 25 MiB are verified by Pillow image decoding and SHA256 (Pillow must be installed), frozen into temporary files, then uploaded through the native Media Storage input. The saved receipt reports each uploaded URL and its source hash. Uploads can leave a media-library item if the browser or save fails; the runner records intent and refuses automatic replay. Because a new URL is unknown before upload, local assets are not accepted inside precompiled mixed batches or new-quiz creation; run a direct Picture Choice job first, then supply its receipt URL in a later batch. Live upload acceptance remains unverified.
