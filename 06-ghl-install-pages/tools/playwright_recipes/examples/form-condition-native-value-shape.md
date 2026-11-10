# Native condition value controls

The November 10 Show/Hide editor capture retains `#inputValue-0` as a
`div.n-input.invisible` for an `Is Empty` clause. It contains one
`input.n-input__input-el[type="text"]` with placeholder
`Please Type a value here`. Counting the wrapper does not prove a visible value
input, and filling the wrapper does not fill the actual textbox.

All compound, Show/Hide stack and outcome-stack writers/readers use the same
wrapper reader. Unary clauses accept the captured positively invisible wrapper
or the previously absent control shape, and refuse a visible textbox. Binary
clauses require the exact visible nested input and read back its authored value.
Changed wrapper/type/placeholder identities and ambiguous controls refuse.

The sanitized native fixture is `fixtures/form-condition-value-captured.html`.
Its comment retains the source dialog hash; no account identifiers or field data
are included. This corrects native control compatibility and does not itself
provide new custom-field types, nested expression groups or respondent proof.

The captured condition modal exposes ordered `Then`, `And`, and `Or` tabs.
Neither this modal nor the full Conditions drawer capture exposes a parenthesis
or nested-group authoring control. R28 requires requested conditions, operators,
actions and targets to persist; it does not separately prescribe nesting.
Arbitrary nested grouping remains unsupported, rather than an invented native
feature or a successful implementation claim.
