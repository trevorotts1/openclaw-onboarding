---
name: real-estate-playbook
description: Property intelligence and real estate automation playbook — property lookup, lead qualification scripts, showing scheduler, lead routing, and real-estate-events.jsonl schema. Integrates with GHL for pipeline management and Telegram for agent notifications.
---

# Skill 39: Real Estate Playbook & Property Intelligence

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file) — overview, component map, honest MVP status
2. INSTALL.md — one-time setup: prerequisites + the numbered install scripts (`00`–`08`) + provider env keys
3. INSTRUCTIONS.md — runtime guide: property lookup flow, qualification scripts, showing scheduler, lead routing, the `real-estate-events.jsonl` schema
4. CORE_UPDATES.md — what gets appended to AGENTS.md + MEMORY.md + TOOLS.md
5. EXAMPLES.md — worked, copy-pasteable example flows (UNIVERSAL placeholders only)
6. CHANGELOG.md — change history

Per N3 ("read before act"), do not skip. Per N4, follow steps in declared order.

## Governing protocol (binding for this skill and all skills in the repo)

This skill is governed by `../QC-PROTOCOL.md` (repo root) — the Sub-Agent Handoff and Mandatory QC Protocol. Every install, every PR, every multi-file change runs the 10-category QC rubric (8.5 threshold) BEFORE declaring done. Sub-agents receive full instructions (never summaries). See `QC-PROTOCOL.md` Part 5 for the sub-agent contract.

## What This Skill Is

**Skill 39 is the real-estate VERTICAL on top of Skill 38 (Conversational AI System).** Skill 38 is the universal conversational AI brain (sales, follow-up, dual-mode CS+support, routing, typed KBs). Skill 39 adds the real-estate-specific layer: property intelligence (lookup, comps, geocoding, Street View), buyer + seller qualification scripts, a showing scheduler, state disclosure compliance, lead routing by agent specialty, open-house automation, and a pre-foreclosure outreach playbook that pairs with Skill 40 (ZHC Public Records Scraper).

It is a SIBLING of Skill 38, not a replacement. Skill 38 owns the conversation engine; Skill 39 owns the real-estate domain knowledge that engine reasons over.

## Honest MVP status (real vs stubbed)

This skill is shipped as an MVP. Every component is marked below as **REAL** (works today with the documented env keys), **PROVIDER-GATED** (works only when the operator supplies the relevant API key; honest gap otherwise — NEVER fabricated), or **STUB** (scaffold + documented contract, no live integration yet). **The skill NEVER fabricates property data.** When a provider key is absent or a lookup returns nothing, the agent reports the honest gap and offers the operator-supplied-key path — it does not invent an address, price, or comp.

| Component | Status | Notes |
|---|---|---|
| Provider abstraction (`property-provider-abstraction.md` + `lib-property.sh`) | REAL | One contract; many providers; operator-supplied env keys; honest-gap on absence |
| Address normalization + geocoding | PROVIDER-GATED | Census Geocoder (free, no key — REAL) + optional Google/Mapbox (key) |
| Property lookup (Zillow / RentSpree / MLS-adjacent) | PROVIDER-GATED | Adapter stubs + contract; live only with the provider's key + ToS acceptance |
| Comps lookup | PROVIDER-GATED | Same provider abstraction; honest gap when no comps source is keyed |
| Street View image generation | PROVIDER-GATED | Google Street View Static API (key) — REAL when `GOOGLE_MAPS_API_KEY` set; probes metadata first, fetches bytes server-side to a local `image_path` (the key is never placed in the emitted output) |
| Buyer qualification questions | REAL | `templates/buyer-qualification.md` — timeline / financing / neighborhood / must-haves |
| Seller qualification questions | REAL | `templates/seller-qualification.md` — motivation / timeline / price / occupancy |
| Showing scheduler (lockbox / MLS rules) | REAL (scaffold) | `protocols/showing-scheduler-protocol.md` + `06-scaffold-showing-scheduler.sh` |
| State disclosure compliance | REAL (data set) | `references/state-disclosure-matrix.md` — 50-state + DC pointer matrix |
| Lead routing by agent specialty | REAL | `protocols/lead-routing-protocol.md` + `templates/agent-specialty-roster.template.json` |
| Open-house automation | REAL (scaffold) | `protocols/open-house-automation-protocol.md` |
| Pre-foreclosure outreach playbook | REAL (scaffold) | `protocols/pre-foreclosure-outreach-protocol.md` — pairs with Skill 40 |
| Sales-Brain RE extension (additive) | REAL (additive) | `references/sales-brain-real-estate-extension.md` — drop-in, does NOT edit Skill 38 |
| GHL + Command Center write layer | REAL (fail-soft) | `scripts/lib-ghl-sync.sh` — tagging / pipeline / booking via caf + Kanban PATCH; HONEST no-op without credentials, never fabricates |
| `real-estate-events.jsonl` emission | REAL | `lib-re-events.sh` append helper; schema documented in INSTRUCTIONS.md |

## How Skill 39 fits in the pipeline

```
Inbound real-estate lead (portal / sign call / web form / open house)
   │
   ▼
Skill 38 conversation engine (tone, follow-up, routing, typed KBs)
   │
   ├── intent = buyer  → Skill 39 buyer-qualification (timeline/financing/neighborhood/must-haves)
   ├── intent = seller → Skill 39 seller-qualification (motivation/timeline/price/occupancy)
   ├── address given   → Skill 39 property lookup + geocode + Street View + comps (provider-gated)
   ├── ready to view   → Skill 39 showing scheduler (lockbox / MLS rules) + disclosure compliance
   └── distressed lead → Skill 39 pre-foreclosure outreach  ──pairs──►  Skill 40 public records
   │
   ▼
Lead routed to the right agent by specialty  →  real-estate-events.jsonl appended
```

## The Sales-Brain Real-Estate extension (additive hook — does NOT edit Skill 38)

Skill 38 ships `protocols/sales-best-practices-protocol.md` (BANT / MEDDIC / SPICED + 6 generic objection patterns). Skill 39 does **NOT** edit that file. Instead it ships an **additive extension** at `references/sales-brain-real-estate-extension.md` and a drop-in installer (`scripts/05-install-sales-brain-extension.sh`) that:

1. Writes the extension into the CLIENT'S installed Skill 38 folder as a NEW file (`38-conversational-ai-system/protocols/sales-best-practices-real-estate-extension.md`) — additive, never overwriting Skill 38's own protocol.
2. Appends ONE pointer line to AGENTS.md (behind a `<!-- BEGIN/END skill-39 sales-brain-re-extension -->` marker) so the engine loads the RE extension when a real-estate context is active.
3. Records the extension in `real-estate-events.jsonl` as a `sales_brain_extension_installed` event.

The extension adds: **RE objection patterns** (commission, "Zillow says it's worth more", dual agency, "we'll wait for rates to drop", FSBO), **CMA pricing-reveal timing** (never reveal a number before the CMA walk-through; anchor on comps, not list price), and **SPICED-RE** (Situation = current home/living situation; Pain = why move now; Impact = cost of staying; Critical event = lease end / job / school year; Decision = who signs). It is read ONLY when the conversation is in a real-estate context, so it never pollutes a non-RE client's sales brain. The hook is documented in INSTRUCTIONS.md → "Sales-Brain RE extension".

## The `real-estate-events.jsonl` contract (F52)

Skill 39 emits one append-only JSONL event log at `<MASTER_FILES_DIR>/real-estate-events.jsonl` per the F52 master-files event contract (the same pattern Skill 38 uses for its run manifest). Every property lookup, showing, CMA request, qualification, lead-route, and pre-foreclosure touch appends exactly one line. The schema is documented in full in INSTRUCTIONS.md → "real-estate-events.jsonl schema" and emitted by `scripts/lib-re-events.sh`. The log is the operator's ground truth for what the RE layer actually did — no agent self-report substitutes for it.

## What This Skill Does NOT Do

- Does NOT fabricate property data. No address, price, comp, owner, or photo is ever invented. Absence → honest gap + operator-supplied-key path.
- Does NOT modify Skill 38's own protocol files. The Sales-Brain RE layer is an ADDITIVE drop-in (new file + pointer line), never a destructive edit.
- Does NOT give legal, lending, fiduciary, or appraisal advice. Disclosure compliance is a POINTER matrix (where to look per state), not legal counsel — those decisions escalate to the licensed agent/broker.
- Does NOT bypass fair-housing rules. The qualification + routing scripts carry fair-housing guardrails (never steer by protected class).
- Does NOT scrape public records itself. Pre-foreclosure / NOD / tax-delinquency data comes from Skill 40 (its sibling) — Skill 39 only consumes Skill 40's output and runs the outreach playbook.
- Does NOT ship MLS credentials or any provider API key. All keys are operator-supplied at install via env.

## Prerequisites

| Prerequisite | Required | Why |
|---|---|---|
| Skill 38 (Conversational AI System) installed | MANDATORY | Skill 39 is the RE vertical ON TOP of the Skill 38 conversation engine |
| `MASTER_FILES_DIR` resolvable (Skill 38 Step O.2) | MANDATORY | The `real-estate-events.jsonl` log lives there |
| `jq` on PATH | MANDATORY | Scripts parse provider JSON + append events with jq |
| `curl` on PATH | MANDATORY | Geocode + provider + Street View HTTP calls |
| `GOOGLE_MAPS_API_KEY` (or `MAPBOX_TOKEN`) | OPTIONAL | Geocoding + Street View imagery (free Census geocoder works keyless) |
| A property-data provider key (e.g. `RENTCAST_API_KEY`, MLS/RESO token) | OPTIONAL | Property lookup + comps; honest gap without it |

## Files in This Folder

| File | Purpose |
|---|---|
| `SKILL.md` | You are here — overview, component map, honest MVP status, F52 contract |
| `INSTALL.md` | One-time setup: prerequisites, numbered scripts `00`–`08`, env keys |
| `INSTRUCTIONS.md` | Runtime guide: lookup flow, qualification, scheduler, routing, the JSONL schema |
| `CORE_UPDATES.md` | Lines appended to AGENTS.md / MEMORY.md / TOOLS.md |
| `EXAMPLES.md` | Worked example flows (UNIVERSAL placeholders) |
| `CHANGELOG.md` | Version history |
| `skill-version.txt` | Currently `1.0.5` |
| `scripts/00-verify-prerequisites.sh` | Verifies Skill 38, MASTER_FILES_DIR, jq, curl; reports provider-key presence |
| `scripts/01-locate-master-files-folder.sh` | Resolves + persists MASTER_FILES_DIR (reuses Skill 38 selection if present) |
| `scripts/02-configure-providers.sh` | Records which property/geocode/StreetView providers are keyed; honest-gap report |
| `scripts/03-init-real-estate-events-log.sh` | Creates the `real-estate-events.jsonl` log + a `.schema.json` sidecar |
| `scripts/04-install-qualification-scripts.sh` | Installs buyer + seller qualification templates into the client master files |
| `scripts/05-install-sales-brain-extension.sh` | ADDITIVE drop-in of the RE Sales-Brain extension into the installed Skill 38 |
| `scripts/06-scaffold-showing-scheduler.sh` | Scaffolds the showing-scheduler state + lockbox/MLS-rules config |
| `scripts/07-register-crons.sh` | Registers open-house follow-up + post-close anniversary scan crons |
| `scripts/08-update-core-files.sh` | Appends the AGENTS.md / MEMORY.md / TOOLS.md pointers (idempotent markers) |
| `scripts/property-lookup.sh` | RUNTIME worker (not an install step): resolves provider status, prints AVAILABLE vs HONEST GAP per capability, appends one F52 `property_lookup` event |
| `scripts/lib-property.sh` | Provider-abstraction library: geocode, lookup, comps, Street View (honest-gap aware; Street View key kept out of the emitted output) |
| `scripts/lib-re-events.sh` | Append-one-line helper for `real-estate-events.jsonl` (resolves `MASTER_FILES_DIR` from persisted state; loud-fails, no Downloads fallback) |
| `scripts/lib-ghl-sync.sh` | Fail-soft GHL (via caf) + Command Center write layer: `ghl_tag` / `ghl_opportunity` / `ghl_book` / `cc_move`; HONEST no-op without credentials |
| `scripts/qc-no-personal-data.sh` | UNIVERSAL-skill identifier gate (zero client/personal data) + PII-free F52 emitter check |
| `scripts/qc-no-fabrication.sh` | Asserts no script returns invented property data on a provider miss |
| `scripts/qc-fair-housing.sh` | CODED fail-closed fair-housing gate — refuses any event/payload carrying a protected-class field (also enforced at the `re_event` chokepoint) |
| `protocols/showing-scheduler-protocol.md` | Lockbox / MLS-rules showing scheduler runtime |
| `protocols/lead-routing-protocol.md` | Route leads by agent specialty + fair-housing guardrails |
| `protocols/open-house-automation-protocol.md` | Open-house registration → follow-up automation |
| `protocols/pre-foreclosure-outreach-protocol.md` | Distressed-owner outreach (pairs with Skill 40) |
| `protocols/state-disclosure-compliance-protocol.md` | When/what disclosures, per the state matrix |
| `references/property-provider-abstraction.md` | The provider contract: how to add/swap a provider |
| `references/sales-brain-real-estate-extension.md` | The additive RE Sales-Brain extension (drop-in source) |
| `references/state-disclosure-matrix.md` | 50-state + DC disclosure pointer matrix |
| `references/real-estate-tags.md` | The ZHC RE tag vocabulary + when each fires |
| `references/fair-housing-guardrails.md` | Fair-housing rules the qualification + routing scripts must honor |
| `templates/buyer-qualification.md` | Buyer qualification question set |
| `templates/seller-qualification.md` | Seller qualification question set |
| `templates/agent-specialty-roster.template.json` | Operator-filled agent specialty roster for routing |
| `templates/showing-scheduler-config.template.json` | Lockbox + MLS showing-rules config |
| `templates/real-estate-events.schema.json` | The JSONL event schema (machine-readable) |

## ZHC tags this skill emits

`ZHC-buyer-lead`, `ZHC-seller-lead`, `ZHC-investor-lead`, `ZHC-pre-foreclosure-prospect` (full vocabulary + fire conditions in `references/real-estate-tags.md`).

## Security & honesty note

All provider keys are operator-supplied via env; the skill never ships a key and never logs a raw key (only `${KEY:0:6}…` if a snippet ever appears). The skill is UNIVERSAL: no client name, business, address, phone, email, or location id appears anywhere in the source — `scripts/qc-no-personal-data.sh` machine-enforces this. The no-fabrication floor is also machine-enforced by `scripts/qc-no-fabrication.sh`.

## Support

- INSTRUCTIONS.md — runtime
- INSTALL.md — one-time setup
- CHANGELOG.md — version history
- https://docs.openclaw.ai — platform docs
