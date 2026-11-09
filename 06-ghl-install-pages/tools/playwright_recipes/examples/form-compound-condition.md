# Native compound Show/Hide conditions

`forms.conditions` accepts a condition with `clauses`, `match`, `effect`, and
one `target`. `match:"all"` uses AND between every clause; `match:"any"` uses
OR. Mixed nested groups and plural targets require a different captured native
contract and are refused. The captured target picker selects one field.

Supply 2 to 20 explicit source/operator clauses. Is Empty and Is Filled have
no value. Captured binary operators require an explicit nonempty `value`:
Is Equal To, Is Not Equal To, Contains, Does Not Contain, Starts With, Ends With.
The source-field vocabulary stays limited to the observed native menu.

The handler reads the complete existing condition-card inventory. An empty
native inventory permits one create; an exact existing rule permits reuse.
Any unrelated, reordered, duplicated or conflicting rule requires explicit
reconciliation before writing. It never deletes rules or silently appends into
an existing stack. Native clause IDs, displayed values, connector modes and
outcome are checked before Save. Save-close and the outer form Save follow,
then independent list reopen checks every summary token and the full inventory.

The result binds the configuration hash and clause count. Submission behavior
remains unverified. Native UI was inspected during implementation; this is not
a claim that the Python handler ran a live client job.
