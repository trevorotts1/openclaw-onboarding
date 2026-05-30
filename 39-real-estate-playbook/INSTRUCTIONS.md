# Skill 39 — Real Estate Playbook & Property Intelligence: Runtime Instructions

This is the operator-facing runtime guide. It assumes Skill 38 is installed and the install scripts (`00`–`08`) have run. Read it top to bottom before acting (N3).

## The non-fabrication floor (read first)

**NEVER fabricate property data.** This is the #1 rule of this skill, enforced by `scripts/qc-no-fabrication.sh`. When a provider key is absent, a lookup returns nothing, or a value is uncertain:

- Report the honest gap: "I don't have a verified value for that address — I can pull it if you connect a property-data provider key, or you can give me the figure."
- Offer the operator-supplied-key path (see INSTALL.md → "Provider keys").
- Do NOT invent an address, price, square footage, comp, owner name, or photo.
- Mark any operator-provided (vs provider-verified) figure as such in the event log (`source: "operator"` vs `source: "<provider>"`).

## Property intelligence flow

### 1. Address normalization + geocoding

`scripts/lib-property.sh geocode "<raw address>"` normalizes and geocodes:

- **Primary (keyless, REAL):** US Census Geocoder (`geocoding.geo.census.gov`) — free, no key, US addresses. Returns normalized address + lat/lon + matched FIPS county (which Skill 40 reuses).
- **Optional (key):** Google Geocoding (`GOOGLE_MAPS_API_KEY`) or Mapbox (`MAPBOX_TOKEN`) for non-US / higher-precision.
- **Honest gap:** if no match, return `{"matched": false}` — never guess coordinates.

Geocoding emits a `geocode` event and (when matched) the county+state, which the pre-foreclosure flow hands to Skill 40.

### 2. Property lookup + comps (provider-gated)

`scripts/lib-property.sh lookup "<normalized address>"` and `... comps "<normalized address>"` call whichever property-data provider the operator keyed (see `references/property-provider-abstraction.md` for the contract). Examples of providers that expose APIs: RentCast (`RENTCAST_API_KEY`), a RESO/MLS Web API token, or a brokerage-internal feed. **If no provider is keyed**, both return `{"available": false, "reason": "no property-data provider configured"}` — the agent reports the honest gap, never a made-up record. Skill 39 ships the abstraction + example adapter stubs; the operator wires their licensed provider.

### 3. Street View image

`scripts/lib-property.sh streetview "<lat>,<lon>"` calls the Google Street View Static API (`GOOGLE_MAPS_API_KEY`). REAL when the key is present; honest gap (`{"available": false}`) otherwise. The image URL/bytes are attached to the lead, never fabricated.

## Buyer & seller qualification

When Skill 38 detects buyer or seller intent, Skill 39 supplies the question set (conversational, not interrogation — one or two at a time):

- **Buyer** (`templates/buyer-qualification.md`): timeline, financing (pre-approval status + budget band), neighborhood/area, must-haves vs nice-to-haves. Emits `qualify` event with `role: "buyer"`.
- **Seller** (`templates/seller-qualification.md`): motivation, timeline, target price expectation, occupancy (owner-occupied / tenant / vacant). Emits `qualify` event with `role: "seller"`.

Fair-housing guardrails (`references/fair-housing-guardrails.md`) apply: never ask about or steer by protected class. Investor intent → `role: "investor"` + `ZHC-investor-lead`.

## Showing scheduler (lockbox / MLS rules)

`protocols/showing-scheduler-protocol.md` governs scheduling. Config lives in `templates/showing-scheduler-config.template.json` (operator fills lockbox type, showing-window rules, MLS confirmation requirements, agent-must-accompany flags). On a booked showing: confirm date/time/address + access details, set 24h + 2h reminders, run state disclosure compliance (below), emit a `showing` event.

## State disclosure compliance

`protocols/state-disclosure-compliance-protocol.md` + `references/state-disclosure-matrix.md`. The matrix is a POINTER per state/DC (what disclosures are typically required and where the authoritative form lives) — NOT legal advice. The agent surfaces the relevant pointer and escalates the actual disclosure decision to the licensed agent/broker. Emits a `disclosure_surfaced` event.

## Lead routing by agent specialty

`protocols/lead-routing-protocol.md` + `templates/agent-specialty-roster.template.json`. Routes each qualified lead to the best-fit agent by specialty (buyer/seller/luxury/investment/first-time/relocation/area), respecting fair-housing rules and round-robin fairness when specialties tie. Emits a `lead_route` event with the chosen agent + reason.

## Open-house automation

`protocols/open-house-automation-protocol.md`. Registration capture → instant thank-you → timed follow-up sequence → feedback prompt. The follow-up scan runs on the cron registered by `07-register-crons.sh`. Emits `open_house` events.

## Pre-foreclosure outreach (pairs with Skill 40)

`protocols/pre-foreclosure-outreach-protocol.md`. When Skill 40 surfaces a Notice-of-Default / pre-foreclosure / tax-delinquency record for a property, Skill 39 runs a CARE-FIRST outreach playbook (empathetic, options-focused, never predatory; honors do-not-contact and state cooling-off rules). Skill 39 NEVER scrapes records itself — it consumes Skill 40's `public-records-queries.jsonl` output. Emits `pre_foreclosure_touch` events and tags `ZHC-pre-foreclosure-prospect`.

## Sales-Brain RE extension (the additive hook)

`scripts/05-install-sales-brain-extension.sh` installs `references/sales-brain-real-estate-extension.md` as a NEW file in the client's installed Skill 38 (`38-conversational-ai-system/protocols/sales-best-practices-real-estate-extension.md`) — **additive, never overwriting Skill 38's own `sales-best-practices-protocol.md`.** It then appends ONE pointer line to AGENTS.md behind `<!-- BEGIN/END skill-39 sales-brain-re-extension -->`. The engine loads the extension ONLY in a real-estate context, so a non-RE client is unaffected. The extension adds RE objection patterns, CMA pricing-reveal timing, and SPICED-RE. Re-running the script is idempotent (it diffs the file + checks the marker). Emits a `sales_brain_extension_installed` event.

## `real-estate-events.jsonl` schema

Append-only JSONL at `<MASTER_FILES_DIR>/real-estate-events.jsonl`. One JSON object per line. Written by `scripts/lib-re-events.sh re_event <type> <json-payload>`. The machine-readable schema is `templates/real-estate-events.schema.json`. Common fields on every event:

| Field | Type | Meaning |
|---|---|---|
| `ts` | string (ISO-8601 UTC) | When the event was appended |
| `skill` | string | Always `"39-real-estate-playbook"` |
| `event` | string | One of the event types below |
| `lead_ref` | string | Opaque local lead reference (NOT PII — a hash/handle) |
| `source` | string | Data origin: a provider slug, `"operator"`, `"census"`, or `"none"` |

Event types and their type-specific payload fields:

| `event` | Type-specific fields |
|---|---|
| `geocode` | `matched` (bool), `county_fips`, `state` (matched only) |
| `property_lookup` | `available` (bool), `provider`, `fields_returned` (array of field names — NOT values, to stay PII-free in the log) |
| `comps` | `available` (bool), `provider`, `comp_count` |
| `streetview` | `available` (bool) |
| `qualify` | `role` (`buyer`/`seller`/`investor`), `tag` |
| `showing` | `state`, `lockbox_type`, `reminders_set` (bool) |
| `disclosure_surfaced` | `state`, `matrix_pointer_id` |
| `lead_route` | `agent_specialty`, `reason`, `tie_broken_by` |
| `open_house` | `stage` (`registered`/`followup`/`feedback`) |
| `pre_foreclosure_touch` | `record_type` (`NOD`/`pre_foreclosure`/`tax_delinquency`), `outreach_stage`, `from_skill_40` (bool) |
| `sales_brain_extension_installed` | `target_skill38_path`, `marker_added` (bool) |

**PII discipline in the log:** the event log records field NAMES and counts, not raw property addresses/owner names/prices. The lead is referenced by an opaque `lead_ref`. This keeps the operator-visible ground-truth log free of client PII while still proving exactly what the RE layer did. (`scripts/qc-no-personal-data.sh` enforces no real identifiers in the source; runtime payloads use the opaque handle by contract.)

## Idempotency & re-runs

All `00`–`08` scripts are idempotent (version/marker compare, then act). `lib-property.sh` and `lib-re-events.sh` are libraries (sourced or called), not state mutators beyond the append-only log. Re-running the installer never double-appends core-file blocks (BEGIN/END markers) and never overwrites Skill 38's own protocol.

## Verification checklist (post-install)

- [ ] `~/.openclaw/skills/39-real-estate-playbook/` exists with all listed files
- [ ] `scripts/*.sh` are `chmod +x`
- [ ] `00-verify-prerequisites.sh` passes (Skill 38 present, MASTER_FILES_DIR resolvable, jq + curl present)
- [ ] `<MASTER_FILES_DIR>/real-estate-events.jsonl` exists (created by `03-init-real-estate-events-log.sh`)
- [ ] Sales-Brain RE extension installed as a NEW file in Skill 38 (not an overwrite) + AGENTS.md pointer present
- [ ] `bash scripts/qc-no-personal-data.sh` → PASS
- [ ] `bash scripts/qc-no-fabrication.sh` → PASS
