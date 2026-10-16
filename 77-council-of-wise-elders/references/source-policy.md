# Council Source Policy Reference

How the council may use evidence, and how it must talk about evidence.
Advisor pack contents are authored by the pack units; this reference is
the policy they and the runtime must satisfy.

## Evidence classes stay separate

- **Bibliographic reference.** A work is named as a seat's foundation.
  Its record status is `bibliographic_only`. Naming a book proves
  nothing about its contents being available to the council.
- **Verified source.** A source whose content was actually obtained
  from an authorized copy, parsed into an authorized derived store, and
  verified against its locators. Only verified sources can ground a
  claim about what the work says.
- **Client-confirmed fact.** Supplied or confirmed by the client in the
  brief. Never mixed with scaffold or standard-company placeholder
  data.
- **Scaffold placeholder.** Standard-company or template content. Never
  presented as the client's revenue, cash, mission, or customer demand.

## Quotation rules

- No invented quotations. Ever. A quotation is released only when its
  full tuple validates: source identity, locator, the text itself, the
  original speaker, and the book author as separate fields. A quote
  attributed to a person inside someone else's book keeps
  `original_speaker` distinct from `book_author`.
- Quotation validation runs after final verdict composition and before
  result release (see protocol.md). Blocked quotations are repaired or
  withheld before anyone sees the result.
- Paraphrase is always labeled as paraphrase, in the seat's own words,
  grounded in verified concepts.

## Coverage minimums

A seat's pack is not grounded until its anchors meet the coverage
minimum recorded in that seat's advisors/<seat-id>/coverage.json: for
book-anchored seats, at least three independently traceable concepts
plus one application case per anchor work. Seats whose anchors are not
yet obtained record exactly that; the seat abstains on source-grounded
claims rather than improvising them.

## Rights and storage

- Raw book texts never enter any repository or distributable archive.
  Only authorized derived stores (concepts, frameworks, decision
  rules, questions) travel with a pack, each traceable to its source
  record.
- A source obtained from a copy whose rights status is unresolved is
  not ingested. Record the gap; do not work around it.
- Per-seat source records live in advisors/<seat-id>/sources.json and
  carry their status per record. Records for works present in the
  source library are ingested as derived material with quality
  unverified and rights as recorded. Records for works absent from
  the library carry verification_status `not_ingested`, which is the
  honest state for a supply gap: no pack content is claimed for those
  works, and every pack's qualification stays bibliographic_only
  until provenance-verified material is ingested.

## Labels

Every seat output, in every surface, carries the seat's exact profile
label from config/advisors.json. A seat is an AI perspective inspired
by published work. It is not the individual and not an endorsement, and
no output may blur that line for effect.
