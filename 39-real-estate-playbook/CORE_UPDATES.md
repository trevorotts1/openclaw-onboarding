# Core File Updates — Skill 39 (Real Estate Playbook & Property Intelligence v1.0.0)

These lines are appended to the workspace's AGENTS.md, MEMORY.md, and TOOLS.md at install time
by `scripts/08-update-core-files.sh` (and the Sales-Brain pointer by `scripts/05-install-sales-brain-extension.sh`).
Every block is behind a clearly-named `<!-- BEGIN/END skill-39 ... -->` marker and is idempotent —
re-running the installer never double-appends. Backups are written before any edit.

**Versioning:** semver-tagged starting at v1.0.0. Future v1.1/v1.2 extend without restructuring.

---

## [ADD TO AGENTS.md] — appended by `scripts/08-update-core-files.sh`

Behind `<!-- BEGIN skill-39 real-estate v1.0.0 -->` / `<!-- END skill-39 real-estate v1.0.0 -->`:

Key behaviors added (real-estate context only — these never fire for a non-RE client):
- **Property intelligence** — when an address is in play, geocode (keyless Census first), then look up + comps + Street View via the operator-keyed provider. NEVER fabricate; absence → honest gap + operator-supplied-key path.
- **Buyer/seller/investor qualification** — supply the matching question set conversationally; honor fair-housing guardrails; tag `ZHC-buyer-lead` / `ZHC-seller-lead` / `ZHC-investor-lead`.
- **Showing scheduler** — on a booked showing, confirm access details, set 24h+2h reminders, surface the state disclosure pointer, escalate the disclosure decision to the licensed agent.
- **Lead routing** — route to the best-fit agent by specialty; round-robin on ties; fair-housing respected.
- **Pre-foreclosure outreach** — consume Skill 40's public-records output; run the care-first outreach playbook; tag `ZHC-pre-foreclosure-prospect`. Skill 39 never scrapes records itself.
- **Event log** — append one line to `<MASTER_FILES_DIR>/real-estate-events.jsonl` for every property lookup, showing, CMA/comps request, qualification, route, and pre-foreclosure touch.

## [ADD TO AGENTS.md — Sales-Brain RE extension pointer] — appended by `scripts/05-install-sales-brain-extension.sh`

Behind `<!-- BEGIN skill-39 sales-brain-re-extension -->` / `<!-- END skill-39 sales-brain-re-extension -->`:

> When the conversation is in a REAL-ESTATE sales context, ALSO load
> `38-conversational-ai-system/protocols/sales-best-practices-real-estate-extension.md`
> (installed additively by Skill 39 — RE objection patterns, CMA pricing-reveal timing, SPICED-RE).
> This extends, never replaces, Skill 38's `sales-best-practices-protocol.md`.

## [ADD TO MEMORY.md] — appended by `scripts/08-update-core-files.sh`

Behind `<!-- BEGIN skill-39 memory-rules v1.0.0 -->` / `<!-- END skill-39 memory-rules v1.0.0 -->`:

Real-estate design rules:
1. **No-Fabrication Rule** — never invent an address, price, sqft, comp, owner, or photo. No provider/no match → honest gap + operator-supplied-key path. Mark operator-provided figures `source: operator`.
2. **Fair-Housing Rule** — never ask about or steer by protected class in qualification or routing.
3. **Disclosure-Pointer Rule** — disclosure compliance is a POINTER matrix, not legal advice; the disclosure decision escalates to the licensed agent/broker.
4. **CMA-Anchor Rule** — never reveal a price before the CMA walk-through; anchor on verified comps, not the seller's hoped list price.
5. **Pre-Foreclosure Care Rule** — distressed-owner outreach is empathetic and options-focused, never predatory; honor do-not-contact + state cooling-off rules.
6. **Event-Log Rule** — every RE action appends one line to `real-estate-events.jsonl` (field names + counts, never raw PII).
7. **Skill-38-Additive Rule** — the RE Sales-Brain layer is an additive drop-in; never overwrite Skill 38's own protocol.

## [ADD TO TOOLS.md] — appended by `scripts/08-update-core-files.sh`

Behind `<!-- BEGIN skill-39 tools v1.0.0 -->` / `<!-- END skill-39 tools v1.0.0 -->`:

A concise quick-reference for `scripts/lib-property.sh` (geocode / lookup / comps / streetview) and
`scripts/lib-re-events.sh re_event <type> <json>`, plus the provider-key env vars and their honest-gap
behavior. No keys, no client data — UNIVERSAL.

## What does NOT get touched

- Skill 38's own protocol files — left untouched. The RE Sales-Brain layer is an ADDITIVE new file.
- Skill 40 — Skill 39 only CONSUMES its output; it never edits Skill 40.
- Operator's SOUL.md / IDENTITY.md / USER.md / HEARTBEAT.md — only AGENTS.md, MEMORY.md, and TOOLS.md are appended to, behind clear markers, with backups first.
