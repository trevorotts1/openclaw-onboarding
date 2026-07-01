# Changelog - Skill 39: Real Estate Playbook & Property Intelligence

## [1.0.3] - 2026-06-30 - Fail-soft GoHighLevel + Command-Center write layer; idempotent root re-wire

Turns the previously prose-only GHL "dependency" into real, deterministic, safe writes, and adds the
canonical-updater re-wire hook. Additive and fail-soft — no existing behavior changes; `lib-property.sh`,
the F52 JSONL contract, and all `00`–`08` install scripts stay working. (Catches the CHANGELOG up to the
current `skill-version.txt`.)

### Added
- `scripts/lib-ghl-sync.sh` — sourced/called helper with four fail-soft functions:
  - `ghl_tag <contact_ref> <tag…>` → `caf contacts add-tag` (apply ZHC RE tags programmatically).
  - `ghl_opportunity create|move …` → `caf opportunities create|update` (place/move a qualified lead in a real GHL pipeline stage — the frontmatter's "pipeline management" promise, now built).
  - `ghl_book <calendar_id> <contact_id> <slot_id> <start> <end> [title]` → `caf calendars book` (GHL-native showing + reminders).
  - `cc_move <task_id> <status> [agent_id]` → PATCH `{MISSION_CONTROL_URL:-http://localhost:4000}/api/tasks/{id}` with `Authorization: Bearer $MC_API_TOKEN` and `updated_by_agent_id`, advancing the Command Center Kanban card as the RE lifecycle moves.
  - Every call is an HONEST no-op when its credential is absent: caf missing or no exported GoHighLevel credential (canonical `GOHIGHLEVEL_API_KEY`, or the `CAF_API_KEY`/`GHL_API_KEY` aliases caf resolves) → one `[skill 39][ghl] honest-gap: …` line + a PII-free `ghl_sync` event (`available:false`) via `lib-re-events.sh` + `return 0`. Never fabricates a success and never prints a secret.
  - SELF-GRADE GUARD: a builder never self-PATCHes its own task to `done`. `cc_move` sends NO PATCH for `status=done` unless the acting agent is PROVEN to differ from the task's `created_by_agent_id` (fetched from the board); unknown builder ⇒ refuse. Mirrors the server-side review→done QC-authority gate.
- `wire.sh` (root, executable, ALWAYS `exit 0`) — fail-soft idempotent re-wire that runs the canonical install steps `00`–`08` behind their existing guards, so the canonical fleet updater re-applies the AGENTS/MEMORY/TOOLS blocks, crons, templates, and the additive Skill-38 RE extension once per version after a wipe-and-replace (Skill-44 pattern). Excludes the runtime worker `03-property-lookup.sh` and the duplicate AGENTS writer `04-update-agents-md.sh` (not install steps).

### Changed
- `templates/real-estate-events.schema.json` — added `ghl_sync` to the `event` enum and an `action` property (`tag` | `opportunity` | `book` | `cc_move`) for the new sync events.

## [1.0.1] - 2026-05-30 - Round-3 canonical reconciliation: add the F52 event-contract reference

Aligns Skill 39 with the canonical Round-3 decision (this repo's build is the canonical base; the
sibling VPS repo's named capability is merged IN). No behavioral change; additive only.

### Added
- `references/master-files-event-contract-F52.md` — the F52 event-contract reference doc (from the
  sibling repo) so the real-estate events log is documented against the same data contract as Skill 38.

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
