# Native Number, Checkbox, File Upload and Signature

Compile `forms.configure` with `widget_fields`; use the accompanying JSON as a
shape example after replacing its location, account, existing form URL and title.
`expected_fields` is the complete current inventory of these four families,
including each absolute one-based canvas index and every current property.
An empty list asserts that none of these four families is already present.

Each requested field has a captured `kind`, `index` and full `desired` properties.
`index: null` explicitly creates a new field with one native Quick Add drag before
Submit. An integer edits that exact existing canvas owner. Existing edits run
before new appends; source order among appends is retained. Other fields, Address
children, consent and Submit are preserved. A retained uncertain journal refuses
another write rather than guessing whether a prior drag succeeded.

| Kind | Native family | Captured controls |
| --- | --- | --- |
| `number` | `NUMERICAL` | Label, Placeholder, Short Label, local Query Key, Width, Required, Hidden/value; separate canonical field metadata |
| `checkbox` | `CHECKBOX` | The same general controls; regular option add/remove/labels, calculation values, Standard/Bubble, columns and special Other lifecycle/placeholder |
| `file_upload` | `FILE_UPLOAD` | Label, Placeholder, Short Label, Required; private/public access at creation, exact supported file-type set, multiple files and optional max-file limit |
| `signature` | `SIGNATURE` | Label, Placeholder, Short Label, Width and Required; separate canonical field metadata |

Number/Checkbox local `query_key` is distinct from Advanced `unique_key`.
All canonical `unique_key` values use `contact.<key>`. The native unsaved key
input/placeholder exposes a bare key; saved readback exposes the disabled
`contact.<key>` value. Only this observed prefix normalization is performed.
Existing canonical keys, global Custom Field Names and File Upload access cannot
be changed by this form job. A new field authors its desired metadata before Save.

`required` and `hidden` are mutually exclusive where both controls exist. File
Upload and Signature do not invent Hidden or a general Query Key control. File
types use canonical ordered tokens `all`, `pdf`, `doc`, `png`, `gif`, `jpg`, `xls`;
`all` is exclusive. `max_files` is a positive count or `null` for unlimited and
must be `null` when multiple files are off. No file is uploaded by this action.

Checkbox `options` contains regular `{label, value}` rows. `value` is `null` while
calculations are off, and canonical decimal text (or the captured unassigned
empty value) when on. `columns` is `null` when spread is off. `other` is `null` or
`{label: "Other", placeholder: "..."}`: the native Other label is readonly and
does not become a fabricated fourth regular choice. No signature is entered.

The writer checks tenant/editor/title, complete prior inventory and Query Key
collisions, saves once, independently reopens and compares all requested fields
and preserved sibling canvases. Completed CLI replay reopens and reads current
state before returning the old receipt; it never repeats creation or editing.

Source uses November 10 native root captures, including all four saved/reopened
widgets and File Upload's immutable canonical metadata. Focused unit and compiler
checks are separate from final installed-script, respondent-upload and signature
behavior proof. Those native functional outcomes are not claimed here.
