# Mixed quiz question authoring

Use `quizzes.configure` with `configuration.question_batches` to author different
captured question types in one ordered job. Each entry is one existing
`written_answer_questions`, `short_answer_questions`,
`multiple_choice_questions`, or `picture_choice_questions` configuration. Owner identity stays in the parent
inputs. Every entry declares the complete prior `pages` inventory and the same
`expected_quiz_name`.

Any entry may append to an exact fully inventoried existing page, including a
populated first target, the same page again, or an earlier page. Set its explicit
`target_page` and supply the complete preceding inventory for every page. To
append a new page, use `create_page: true`, the exact generated `new_page_label`
(`Page N+1`), and `target_page: N+1`. Each entry still authors exactly one
question. Picture Choice retains its captured three-option, approved-existing-media
contract. Quiz shell creation remains owned by `quizzes.create`.

The compiler checks that each next inventory is exactly the previous inventory
plus the previous authored question/page, including choice options. For prior
Picture Choice questions, use persisted `unique_key` and label/image URL options,
without creation-only media-button names. Short Answer batches retain TEXT only
and use the existing complete-inventory written-answer writer. The native
writer independently checks that inventory again before insertion and saves
and reopens its editor before the next batch starts. Unknown property defaults
and page/question identities are never synthesized.

Each entry receives its own runner intent and typed outcome. If a later entry
fails or is interrupted, the job requires reconciliation; rerunning the same
job does not insert earlier questions again. Complete job replay also performs
no new writes. Actual submissions, scoring, results and learner behavior remain
separate acceptance work. Existing leaf writers have their recorded capture and
focused checks. The existing-page mixed compiler follow-up is
`IMPLEMENTED_PENDING_EXECUTION`: its focused tests have not run because the
execution environment is unavailable. No prior passing check covers this new
compiler change, and no completed live native acceptance is claimed.
