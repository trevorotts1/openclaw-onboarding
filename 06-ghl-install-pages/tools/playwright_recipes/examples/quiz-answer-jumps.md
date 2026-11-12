# Set a Single Choice answer destination

Use `quizzes.configure` with an exclusive `configuration.answer_jumps` object.
This uses the existing `quiz_configuration` action and its normal native
Save/reopen path. See `quiz-answer-jumps.json`.

Supply every existing canvas question title in exact page/question order in
`question_labels`. Titles must be unique. Each target in `questions` binds its
zero-based global `index`, `expected_question`, exact `expected_query_key`, and
every answer option in native order. Each option supplies `label`, its current
`expected_destination`, and authored `destination`. Use null for disabled Jump
To, `Next Question` for the native next question choice, or the exact title of a
question later in the complete order. Existing backward destinations can be
inventoried and replaced; new backward/self loops are refused.

The writer binds the captured `quiz_element_sidebar`, each indexed option row,
its switch and `radioN` destination control. Before choosing, the entire native
destination menu must match Next Question plus every other existing question.
It changes only the selected answer routing and preserves raw categories,
unassigned/disabled scores, question properties, Required/Hidden and Spread to
Columns. It rechecks all configured targets before Save and after independently
reopening. Destination or protected-state drift stops completion.

For captured Multiple Choice, add `"field_type": "CHECKBOX"` to the target question. Use `null`, `"Next Question"`, or an exact forward question title; enabling the switch selects Next Question in the native UI. For a named target the complete native menu must match the inventoried question order. The reader also protects the checkbox style, categories and raw scores. Live checkbox routing and respondent behavior require separate acceptance. It does not publish or submit a respondent. See `quiz-checkbox-answer-jumps.json`.

## Choice Standard/Bubble style

Each target question may also include
`"presentation": {"expected_style": "Standard", "style": "Bubble"}`. The exact
case-sensitive styles are Standard and Bubble. This uses the native radio or checkbox style cards captured in the same quiz sidebar. Supply every answer's unchanged
old/desired destinations for a style-only request.

The writer checks both style-card identities and exactly one active card before
clicking the requested card once. Routing, raw scores/categories, field properties,
Required/Hidden and the Spread to columns state must remain unchanged. The saved
style is independently checked after reopen. This does not author Spread/column
controls or other question-family styles. Changing style while Spread is active
refuses until the corresponding column-value inventory is captured.

Single and Multi Dropdown targets may use `"field_type": "SINGLE_OPTIONS"` or `"MULTIPLE_OPTIONS"` with the same complete option/destination inventory. Runtime checks the indexed row, switch, destination selection and full menu; a changed native structure stops the job. These dropdown paths are source-built and have not received live acceptance.

Yes / No questions use the same native `RADIO` owner as Single Choice. Supply the exact `Yes` and `No` option labels and the question's actual Query Key; omit `field_type` or set it to `"RADIO"`. The same protected routing and saved readback apply.
