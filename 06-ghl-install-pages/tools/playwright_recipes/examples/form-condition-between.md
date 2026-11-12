# Inclusive Number conditions

Bind each existing local Number widget by its exact label, native Query Key,
and `field_type: "NUMERICAL"` in `field_bindings`. A Number can be a predicate
source or a Show/Hide target. Use `operator: "Between"` with `value: ["2", "8"]`
for an inclusive numeric range. Bounds must be ordered decimal strings.

The script binds the actual Start/End inputs and verifies that both captured
Include endpoint checkboxes remain checked. Exclusive ranges refuse before
writing values. The saved summary is read from direct spans so the nested
native “And” label is not mistaken for another predicate token.

These clauses work in the existing single/group, ordered-stack, and conditional
outcome handlers. No new action or provider routing is needed. November 11
form/survey native captures ground the controls; final maintained-script and
respondent evaluation remain separate acceptance checks.
