# Changelog - Skill 39: Real Estate Playbook & Property Intelligence

## [1.0.0] - 2026-05-30 - Initial release

First release of the real-estate VERTICAL on top of Skill 38 (Conversational AI System). Shipped as
an honest MVP: every component is labelled REAL / PROVIDER-GATED / STUB in SKILL.md, and the skill
NEVER fabricates property data.

### Property intelligence
- Provider abstraction (`references/property-provider-abstraction.md` + `scripts/lib-property.sh`): one
  contract, many providers, operator-supplied env keys, honest-gap on absence.
- Address normalization + geocoding: keyless US Census geocoder (REAL) + optional Google/Mapbox.
- Property lookup + comps: provider-gated (example adapter stubs + the contract); honest `available:false`
  when no provider is keyed — never a fabricated record.
- Street View image generation: Google Street View Static API (REAL with `GOOGLE_MAPS_API_KEY`).

### Conversation layer
- Buyer qualification (`templates/buyer-qualification.md`): timeline / financing / neighborhood / must-haves.
- Seller qualification (`templates/seller-qualification.md`): motivation / timeline / price / occupancy.
- Showing scheduler (`protocols/showing-scheduler-protocol.md` + lockbox/MLS-rules config).
- State disclosure compliance: 50-state + DC POINTER matrix (`references/state-disclosure-matrix.md`) — not legal advice.
- Lead routing by agent specialty (`protocols/lead-routing-protocol.md`) + fair-housing guardrails.
- Open-house automation + pre-foreclosure outreach playbooks (the latter pairs with Skill 40, consuming
  its `public-records-queries.jsonl` output; Skill 39 never scrapes records itself).

### Sales-Brain RE extension (additive — does NOT edit Skill 38)
- `references/sales-brain-real-estate-extension.md` + `scripts/05-install-sales-brain-extension.sh`:
  installs the extension as a NEW file in the client's installed Skill 38 (never overwriting Skill 38's
  own `sales-best-practices-protocol.md`) + one AGENTS.md pointer line behind a marker. Adds RE objection
  patterns, CMA pricing-reveal timing, and SPICED-RE; loaded only in a real-estate context.

### F52 event contract
- `<MASTER_FILES_DIR>/real-estate-events.jsonl` append-only event log (`scripts/lib-re-events.sh`),
  machine-readable schema at `templates/real-estate-events.schema.json`. Records field names + counts and
  an opaque `lead_ref`, never raw PII. Schema documented in INSTRUCTIONS.md.

### ZHC tags
- `ZHC-buyer-lead`, `ZHC-seller-lead`, `ZHC-investor-lead`, `ZHC-pre-foreclosure-prospect`
  (`references/real-estate-tags.md`).

### Quality
- UNIVERSAL: zero client/personal data; machine-enforced by `scripts/qc-no-personal-data.sh`.
- No-fabrication floor machine-enforced by `scripts/qc-no-fabrication.sh`.
- Governed by `../QC-PROTOCOL.md` (8.5 threshold, 10-category rubric).
- Registered in `install.sh` (`install_skill_39_real_estate_playbook`) + the README skill catalog.
