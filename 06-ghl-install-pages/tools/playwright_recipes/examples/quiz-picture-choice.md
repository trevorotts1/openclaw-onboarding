# Picture Choice on an exact existing quiz

Use `quizzes.configure` with the exclusive `configuration.picture_choice_questions`
object. It accepts the same owner/page fields as the captured question writers:
`expected_quiz_name`, full ordered `pages`, `target_page`, and `questions`, plus
`acknowledge_shared_field_options: true`. Exactly one new question is supported.
The target must be a positively inventoried empty page, or explicitly append one
with `create_page: true` and the exact native `new_page_label: "Page N+1"`.

The new question has `field_type: "PICTURE_CHOICE"`, explicit `question`,
`placeholder`, `short_label`, `query_key`, `required`, `hidden`, and
`expected_persisted_unique_key`. The last value is the caller's exact expected
native Contact key (for example `contact.your_next_move`); the writer does not
derive it or write a guessed key. All three `options` must declare:

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
correct option card. Local upload, option count changes, and presentation edits
are outside this operation. The captured presentation has three columns, Cover
fit, visible labels, Other option off, and Spread to Columns on.

Prior Picture Choice questions in `pages` use `field_type: "PICTURE_CHOICE"`,
the complete text/key/flag properties, actual persisted `unique_key`, and three
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
