# Native redirect, message and disqualification conditions

`forms.conditions` accepts one complete ordered `condition.rules` list. Lists
containing Redirect to URL, Display custom message or Disqualify lead use the
dedicated `native_condition_outcomes` handler. The same list can retain captured
Show Field/Hide Field rules as an existing prefix. Without `expected_rules`, it
retains append-only behavior. With an explicit complete `expected_rules` list,
`rules` may be an unambiguous unchanged ordered subset, including an empty list.
This removes inventoried cards through the captured confirmation; it does not
reorder or overwrite retained cards. See `form-condition-outcome-removal.md`. Replace all identities, fields, URLs and copy in the
example with the actual approved form inventory and authored intent.

Every rule has `match` (`all`/`any`), ordered `clauses`, and one exact `effect`:

| Effect | Required additional properties |
|---|---|
| `Show Field` / `Hide Field` | `target` |
| `Redirect to URL` | `redirect_url` |
| `Display custom message` | `message` |
| `Disqualify lead` | Explicit `mode: Show custom message` and `message`, or `mode: Redirect to URL` and `redirect_url` |

Messages are literal plain text, with line endings normalized and surrounding
whitespace trimmed. The script limits text to 50,000 characters; this is not a
claim of the platform's maximum. Redirects reuse the existing HTTPS/no-embedded-
credentials validation. Unknown fields, ignored effect properties, nested mixed
AND/OR structures and duplicate/conflicting predicates for one effect are refused.
A single-clause `any` predicate normalizes to the same native state as `all`.
Distinct native effects retain their explicit authored order.

The live-captured drawer repeats Redirect to URL in existing summary cards. Add
operations therefore select tiles only inside the native heading, avoiding a
matching card's outcome text. Native modal predicates, homogeneous connectors,
selected disqualification mode and full URL/message value are checked before
modal Save. No Escape key or guessed close button is used.

The complete summary inventory reads direct outcome spans. Message and
message-disqualification cards contain actual rich HTML; its SHA256 is retained
internally to protect every prior card's markup through append and independent
reopen. Summary plain text alone is never treated as proof that formatting
remained unchanged. The full authored rule order, effect mode, text and URL must
also match exactly. Native Save traffic is allowed to settle, then the exact
form is reopened from its independent list before completion is reported.

The receipt binds the configuration hash and rule count and keeps
`behavior_verified`, `submission_verified` and `disqualification_executed` false.
Editor configuration does not prove that a lead was redirected, shown a message
or disqualified. No form submission or live lead action is initiated. An
uncertain save requires reconciliation; the handler does not repeat an append.
