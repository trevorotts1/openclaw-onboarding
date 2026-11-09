# Native checkout build boundaries

`checkout.configure_native` already has an executable adapter for main native
product/price binding, exact unselected bump attachments, Required/Hidden field
states and native accept/decline target bindings. This is separate from the
visible appearance/configuration handler in `checkout.configure_ui`.

Native checkout UI jobs now inventory every requested mode, product display,
contact field, checkout switch, content textbox and input-theme control before
the first value edit. A missing or ambiguous later control stops the batch before
earlier mode/switch/field values change. An enabled Terms editor is also checked
during preflight; a disabled editor can only be checked immediately after its
explicit switch exposes it. This does not imply payment or split-test proof.

Native field-state updates now preserve every existing sibling field and
unrequested property on the edited field. The first post-write native read
compares the entire merged field-state map, rather than only the last edited
flag. A requested bump plan is resolved before any main-price write, including
existing bump capacity, exact reusable bindings, duplicate offers/prices,
recurrence limits and currency conflicts. After the bump/action writes, the
full preserved/requested bump list and requested main price are read again.

These operations require a real location/page-bound managed adapter capture and
the existing Skill 44/79 dependency contract. No real capture is bundled as a
public synthetic example. An absent capture is an execution dependency; it does
not authorize invented route or element-property names.

## Split testing remains a separate missing native implementation

The shared `ghl_split_variant.py` is a capture-bound planning schema. It explicitly
does not implement browser or network execution and refuses traffic activation.
The repository's split capture is an offline fixture and cannot enable it.

Before the native variant creation/allocation handler can be implemented, capture
the authoritative control/variant relation, real variant ID, traffic units/range,
current allocation and create/save/read controls on an approved staging funnel.
The observed missing-domain notice and uncertain earlier variation intent must
be reconciled before any new Create variation click. Two disconnected pages are
never an implementation of a native split test.

No optional tests or native payment journeys were run during this build pass.


## Captured split identity checks

The capture-gated split planner now checks exact variant ID, control relation
and typed unchanged traffic readback even when a capture's key list omits a
binding field. Reuse validates the whole returned inventory: malformed rows,
duplicate IDs, multiple matches, a different captured ID, conflicting occupied
IDs and explicit foreign location/funnel claims require reconciliation. No
missing native ID is fabricated from capture metadata, and a first matching row
cannot hide a later conflict. Requests retain their explicit text/boolean types
and cannot smuggle whitespace, control characters or path/query delimiters.

These are executable identity/planning safeguards. They do not create a native
variant, allocate traffic or enable the capture-gated writer. The real split
creation/allocation implementation still needs authoritative native UI/API
capture; an offline fixture and a missing-domain probe cannot supply it.
