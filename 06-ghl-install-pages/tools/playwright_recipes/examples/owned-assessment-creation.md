# Captured new quiz and survey creation

Use `quiz-owned-creation.json` with `quizzes.create`, or
`survey-owned-creation.json` with `surveys.create`. Replace `LOC`, the visible
location name, the exact list URL and all authored copy/field definitions before
running the maintained `host.py`. Start with a new distinct name and explicitly
allow creation. Existing objects with that name refuse before creation.

The quiz example composes two captured questions, explicit scoring and result
copy. Each question occupies its own page; reliable append to a populated page
is still missing. The generated editor identity is retained after the empty
shell has saved and independently reopened. Every child stage retains its own
intent journal; uncertain writes refuse instead of recreating the quiz.

The survey example creates two empty slides, then places authored Radio questions
on slides 1 and 2. A current measured Skill44 Radio-field capability and complete
schema inventory are required. All dependencies are preflighted before creating
the shell; API and native journals remain separate. `slide_count` accepts 1 to 100
as an adapter bound, not a measured platform maximum. The alternate
`standard_fields` shell remains available with one distinct captured field per
slide. Choose exactly one shell mode.

Non-Radio widget/property authoring, survey compound/completion outcomes and
remaining quiz Jump To/tier/media controls are unfinished. These pipelines do
not establish respondent submission, scoring behavior or publication acceptance.
Keep the original run directory for recovery and replay.
