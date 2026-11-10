# Mixed quiz question authoring

Use `quizzes.configure` with `configuration.question_batches` to author different
captured question types in one ordered job. Each entry is one existing
`written_answer_questions`, `short_answer_questions`, or
`multiple_choice_questions` configuration. Owner identity stays in the parent
inputs. Every entry declares the complete prior `pages` inventory and the same
`expected_quiz_name`.

The first entry may target a positively inventoried empty existing page. Every
later entry must use `create_page: true`, the exact generated `new_page_label`
(`Page N+1`), and `target_page: N+1`. Each entry authors exactly one question.
These bounds deliberately use the captured empty-page insertion path. They do
not enable unresolved populated-page append, Picture Choice, or shell creation.

The compiler checks that each next inventory is exactly the previous inventory
plus the previous authored question/page, including choice options. The native
writer independently checks that inventory again before insertion and saves
and reopens its editor before the next batch starts. Unknown property defaults
and page/question identities are never synthesized.

Each entry receives its own runner intent and typed outcome. If a later entry
fails or is interrupted, the job requires reconciliation; rerunning the same
job does not insert earlier questions again. Complete job replay also performs
no new writes. Actual submissions, scoring, results and learner behavior remain
separate acceptance work. This source composition has focused offline coverage;
it is not a claim of completed live native acceptance.
