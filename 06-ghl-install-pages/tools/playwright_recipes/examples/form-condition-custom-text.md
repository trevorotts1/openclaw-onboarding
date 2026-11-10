# Existing custom Single Line fields in conditions

Use `forms.conditions` with `form-condition-custom-text.json`. The custom field
must already exist in the requested form. This job creates no contact-field schema
and does not change labels, Query Keys or field properties.

Supply `field_bindings` beside the ordered rules, or beside a single compound
rule's clauses. It is the complete ordered inventory of the form's local custom
`TEXT` widgets, including unused custom TEXT siblings. Each entry includes its
exact visible `label`, independently inventoried native `query_key`, and literal
`field_type: "TEXT"`. Label/key duplication, builtin shadowing, missing siblings
and unsupported custom widget types refuse before condition writes.

The writer verifies all custom labels and native Query Keys before editing
conditions, then repeats the same inventory after independently reopening.
Custom source and target selections filter the native searchable selector by
the exact label and require a unique visible matching option. The first visible
options in this virtualized menu are never treated as a full field inventory.
Changed requests, custom siblings and Query Keys change the receipt hash; older
builtin requests keep their existing hashes.

Custom TEXT supports the captured eight operators: Is Empty, Is Filled, Is Equal
To, Is Not Equal To, Contains, Does Not Contain, Starts With and Ends With. The
binding applies consistently to compound Show/Hide groups, Show/Hide stacks and
redirect/message/disqualification outcome predicates. Existing full expected-rule
and protected rich-message contracts remain required for edits and removals.

Native November 10 evidence saved and independently reopened a custom TEXT
Contains predicate joined by Or to First Name Is Filled, hiding that same custom
TEXT field. That capture grounds control support; installed-script execution and
actual respondent branch behavior remain separate proof. Custom Radio, numerical,
file and other option-valued condition profiles are not enabled by this capture.

Evidence anchors: the targeted source-selector dialog SHA256 is
`098f29a512fd36ae005535cacf936ea1400c51a579a8f37a17179cc1574ced0f`;
the independently reopened native Conditions dialog SHA256 is
`e3f94a658ccc196f0f33f6492793694deec2c0b914a12f11ed9dbbc765b38d98`.
These identify the bounded private capture without copying account details into
the repository. Earlier truncated whole-page captures are not evidence for the
selector or operator implementation.
