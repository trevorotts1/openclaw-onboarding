# Create or remove native quiz score tiers

Use `quizzes.configure` with the existing score-tier configuration.
`expected_tier_labels` and `expected_tiers` inventory every current native row.
`tiers` describes every desired final row, covering integer percentages 0–100
without gaps or overlap.

When the count changes, include `tier_transitions`, an ordered list of exact
count actions. Each object contains `action` (`add` or `remove_last`) and
`expected_tiers`, the complete rows expected after that action. Ranges must
match the native count-change result. For Add, the new last label is authored
text: native generated labels vary, so the writer reads the fresh row, proves
all retained labels and ranges, and writes only its owned new label before
checking the full result. Do not guess the native generated label. See `quiz-tier-lifecycle.json` for the captured three-to-four-row
example. Reverse its before/after inventories and use `remove_last` to remove
that fourth row.

The captured Add operation splits the old last range and appends one tier;
Remove last extends the preceding range to 100. Every other retained row must
keep its label and endpoints across each count change. The writer checks the
whole native inventory before and after each action, then authors the requested
final ranges and labels, saves, and independently reopens. An unexpected count,
row change, disabled action or lost saved state stops the job. It never retries
an uncertain Add/Remove.

This uses the captured native tier controls. It does not submit a respondent or
prove score-to-result behavior. Source tests and manual capture are separate
from final installed-script execution.
