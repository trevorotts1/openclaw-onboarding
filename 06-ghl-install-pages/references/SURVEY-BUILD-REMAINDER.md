# Survey source build scope at v27.1.109

The recorded `surveys.create` and `surveys.configure` source contracts are BUILT.
This is source coverage. Maintained-script and live respondent acceptance remain
pending. The authoritative current operation ledger is [PLAYWRIGHT-PROGRESS.md](PLAYWRIGHT-PROGRESS.md), with exact contracts in [PLAYWRIGHT-BUILD-STATUS.json](PLAYWRIGHT-BUILD-STATUS.json).

## Implemented recorded source

- Owned survey shells, slides, captured standard fields, Radio, Single Line,
  Multi Line, Number, Checkbox, Single Dropdown, Multi Dropdown, File Upload,
  Signature and Text Box List.
- Captured Bot protection, Source, Monetary, Score, Rating, Date-only,
  Date and time, Time-only, Text heading, HTML, Image, Picture Choice and URL
  creation/property adapters, with guarded Survey owner identities.
- Forward Jump To and captured plain Message/HTTPS Redirect completion.
- Compound predicates and captured Show/Hide, conditional Message/Redirect
  and After Submit disqualification outcomes.
- Existing mixed legacy Jump To/outcome inventories. Jump cards remain unchanged
  at their exact ordinal. Known outcomes can be edited in place or appended after
  an unchanged complete prefix; unsupported reorder/removal stops before writes.
- Captured paragraph/basic-mark and new-window ASCII HTTPS-link preservation,
  with raw markup hashes and independent saved reopen checks in the scripts.

## Boundaries and pending acceptance

Unprofiled contact/address/payment tiles, arbitrary mixed-question placement,
other disqualification timing, arbitrary rich HTML and arbitrary Jump To reorder
are outside the recorded profiles. The adapters fail closed when native controls
or complete expected inventories differ. Several content adapters reuse guarded
Form primitives; their native Survey maintained-script acceptance remains pending.

Source tests and manual control captures are separate from actually executing the
maintained scripts, answering a live survey and proving each respondent branch.
