# Core File Updates — Skill 39 (Real Estate Playbook & Property Intelligence v1.0.5)

These lines are written to the workspace's AGENTS.md, MEMORY.md, and TOOLS.md at install time
by `scripts/08-update-core-files.sh` — the SINGLE canonical writer (and the Sales-Brain pointer by
`scripts/05-install-sales-brain-extension.sh`). Every block sits behind a clearly-named, VERSION-FREE
`<!-- BEGIN/END skill-39 ... -->` marker and is written REPLACE-IN-PLACE: a re-run — including after a
version bump — overwrites the block in place (and strips any legacy version-stamped variant) instead of
appending a duplicate. Backups are written before any edit.

**Versioning:** semver-tagged starting at v1.0.0. Future v1.1/v1.2 extend without restructuring.

---

## [ADD TO AGENTS.md] — appended by `scripts/08-update-core-files.sh`

Behind `<!-- BEGIN skill-39 real-estate -->` / `<!-- END skill-39 real-estate -->`:

Key behaviors added (real-estate context only — these never fire for a non-RE client):
- **Property intelligence** — when an address is in play, run `scripts/property-lookup.sh --address "<addr>"` (geocode keyless Census first, then look up + comps + Street View via the operator-keyed provider; the runtime worker appends the F52 event). NEVER fabricate; absence → honest gap + operator-supplied-key path.
- **Buyer/seller/investor qualification** — supply the matching question set conversationally; honor fair-housing guardrails; tag `ZHC-buyer-lead` / `ZHC-seller-lead` / `ZHC-investor-lead`.
- **Showing scheduler** — on a booked showing, confirm access details, set 24h+2h reminders, surface the state disclosure pointer, escalate the disclosure decision to the licensed agent.
- **Lead routing** — route to the best-fit agent by specialty; round-robin on ties; fair-housing respected.
- **Pre-foreclosure outreach** — consume Skill 40's public-records output; run the care-first outreach playbook; tag `ZHC-pre-foreclosure-prospect`. Skill 39 never scrapes records itself.
- **GHL + Command Center sync** — `scripts/lib-ghl-sync.sh` applies tags (`ghl_tag`), places/advances the pipeline (`ghl_opportunity`), books showings (`ghl_book`), and moves the Kanban card (`cc_move`); each is a fail-soft HONEST no-op when its credential is absent. A builder never self-promotes its own task to `done`.
- **Event log** — append one line to `<MASTER_FILES_DIR>/real-estate-events.jsonl` for every property lookup, showing, CMA/comps request, qualification, route, and pre-foreclosure touch.

## [ADD TO AGENTS.md — Sales-Brain RE extension pointer] — appended by `scripts/05-install-sales-brain-extension.sh`

Behind `<!-- BEGIN skill-39 sales-brain-re-extension -->` / `<!-- END skill-39 sales-brain-re-extension -->`:

> When the conversation is in a REAL-ESTATE sales context, ALSO load
> `38-conversational-ai-system/protocols/sales-best-practices-real-estate-extension.md`
> (installed additively by Skill 39 — RE objection patterns, CMA pricing-reveal timing, SPICED-RE).
> This extends, never replaces, Skill 38's `sales-best-practices-protocol.md`.

## [ADD TO MEMORY.md] — appended by `scripts/08-update-core-files.sh`

Behind `<!-- BEGIN skill-39 memory-rules -->` / `<!-- END skill-39 memory-rules -->`:

Real-estate design rules:
1. **No-Fabrication Rule** — never invent an address, price, sqft, comp, owner, or photo. No provider/no match → honest gap + operator-supplied-key path. Mark operator-provided figures `source: operator`.
2. **Fair-Housing Rule** — never ask about or steer by protected class in qualification or routing.
3. **Disclosure-Pointer Rule** — disclosure compliance is a POINTER matrix, not legal advice; the disclosure decision escalates to the licensed agent/broker.
4. **CMA-Anchor Rule** — never reveal a price before the CMA walk-through; anchor on verified comps, not the seller's hoped list price.
5. **Pre-Foreclosure Care Rule** — distressed-owner outreach is empathetic and options-focused, never predatory; honor do-not-contact + state cooling-off rules.
6. **Event-Log Rule** — every RE action appends one line to `real-estate-events.jsonl` (field names + counts, never raw PII).
7. **Skill-38-Additive Rule** — the RE Sales-Brain layer is an additive drop-in; never overwrite Skill 38's own protocol.

## [ADD TO TOOLS.md] — appended by `scripts/08-update-core-files.sh`

Behind `<!-- BEGIN skill-39 tools -->` / `<!-- END skill-39 tools -->`:

A concise quick-reference for the runtime worker `scripts/property-lookup.sh`, the provider-abstraction
primitives `scripts/lib-property.sh` (geocode / lookup / comps / streetview — streetview fetches the image
BYTES server-side and emits a local `image_path`, never a keyed URL), the event helper
`scripts/lib-re-events.sh re_event <type> <json>`, and the fail-soft GHL + Command Center write layer
`scripts/lib-ghl-sync.sh` (`ghl_tag` / `ghl_opportunity` / `ghl_book` / `cc_move`) — plus the provider-key
and credential env vars and their honest-gap behavior. No keys, no client data — UNIVERSAL.

## GHL + Command-Center write layer (v1.0.3) — now fully wired (v1.0.5)

- `scripts/lib-ghl-sync.sh` — sourced/called fail-soft helper: `ghl_tag` (caf `contacts add-tag`), `ghl_opportunity` (caf `opportunities`), `ghl_book` (caf `calendars book`), and `cc_move` (PATCH the Command Center task). Each is an HONEST no-op when its credential is absent — no fabricated success. Credentials are operator-supplied via env: canonical `GOHIGHLEVEL_API_KEY` (caf also resolves `CAF_API_KEY`/`GHL_API_KEY`) for GHL writes, and `MC_API_TOKEN` + `MISSION_CONTROL_URL` (defaults to `http://localhost:4000`) for Command Center moves. A builder never self-PATCHes its own task to `done`.
- `wire.sh` (root) — idempotent, fail-soft re-wire of install steps `00`–`08` for the canonical updater (re-applies the blocks above once per version after a wipe-and-replace).
- The marker-refresh writer promised here is now BUILT (v1.0.5): `08-update-core-files.sh` writes each block replace-in-place behind a version-free marker, so `lib-ghl-sync.sh` is surfaced INSIDE the marker-fenced AGENTS.md + TOOLS.md blocks with no duplicate blocks on already-wired boxes (legacy version-stamped markers are stripped on refresh).

## What does NOT get touched

- Skill 38's own protocol files — left untouched. The RE Sales-Brain layer is an ADDITIVE new file.
- Skill 40 — Skill 39 only CONSUMES its output; it never edits Skill 40.
- Operator's SOUL.md / IDENTITY.md / USER.md / HEARTBEAT.md — only AGENTS.md, MEMORY.md, and TOOLS.md are appended to, behind clear markers, with backups first.
