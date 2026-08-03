# Changelog - ghl-convert-and-flow (Skill 29)

All notable changes to this skill are documented here.

---

## [v6.7.0] - 2026-08-03 — API currency: the Version-header defect, corrected scopes, and five missing capability surfaces

### Fixed — CRITICAL, this was causing live 400s on every box
- **Seven client-facing reference files taught the WRONG `Version` header.**
  `contacts`, `locations`, `opportunities`, `users`, `payments`, `campaigns` and
  `phone-numbers` all instructed agents to send `Version: 2021-04-15`. Every one of those
  app specs publishes `2021-07-28`. 231 occurrences corrected across the seven files
  (header lines, the "Headers: Authorization + Version" bullets, and every cURL template).
- `SKILL.md` stated `Version: 2021-04-15 (required on most calls)` as the GLOBAL default.
  It is inverted: **33 of the 41 published app specs use `2021-07-28`.** Replaced with an
  explicit per-app rule that names the seven exceptions, so a blanket rule cannot be
  re-introduced in either direction.
- `references/auth.md` said "Most endpoints require `Version: 2021-04-15`" — same inversion,
  same fix.
- `references/webhooks.md` claimed `Version: 2021-04-15` was "required on all calls".
  Webhooks are inbound POSTs *from* GoHighLevel; there is no Version header to send.
- Per-endpoint version fixes in `EXAMPLES.md` (16 of 22 curls), `INSTALL.md`,
  `INSTRUCTIONS.md`, `QC.md`, `ghl-convert-and-flow-full.md` and `CORE_UPDATES.md`.
  The conversations and calendars examples were left on `2021-04-15` — those are correct.

### Fixed — scopes
- **`references/auth.md` scope list rebuilt from the specs.** Nine scope families were named
  wrong (a wrong scope name 401/403s exactly like a missing one): `blogs.*` →
  `blogs/list.readonly` + 6 siblings; `social-media-posting.*` → the `socialplanner/*`
  family; `phone/number.*` → `phonenumbers.read|write` + `numberpools.read`;
  `custom-menus.*` → `custom-menu-link.*`; `marketplace.*` → `charges.*` +
  `marketplace-installer-details.readonly` + `marketplace-external-auth-migration.write`;
  `voice-ai/agents.*` → `voice-ai-agents.*` (hyphen, not slash); `courses/readonly` →
  `courses.write`; `saas/location.readonly` → `saas/location.read`;
  `funnels/pageCount.readonly` → `funnels/pagecount.readonly`.
- The count "All 106 Scopes" was wrong. **118 are declared in the spec `security` blocks;
  130 is the union with `docs/oauth/Scopes.md`.** All 130 are now listed, verified
  name-for-name against both sources with zero invented and zero missing entries.
- Removed the `stores/*` scopes as **unverified** — neither `store.json` nor `Scopes.md`
  declares any store scope. Also removed `marketing.*`, `proposals-and-estimates.*` and
  seven other names that appear in neither source.

### Fixed — OAuth
- **Authorization URL was missing the `/v2/` segment** (HighLevel moved it 2026-05-27).
- Added the **white-label variant** `marketplace.leadconnectorhq.com/v2/oauth/chooselocation`,
  which is the host a white-labelled agency actually needs and which was absent entirely.
- Documented `&loginWindowOpenMode=self`, the 24h/1-year token lifetimes with refresh
  rotation, and the official JS/TS/Python/PHP SDKs.

### Added — capability that existed but was undocumented
- `references/agent-studio.md` — 11 endpoints, full AI agent lifecycle (`2021-04-15`).
- `references/voice-ai.md` — 11 endpoints, agents + **actions** + call-log/transcript
  dashboard (`2021-04-15`). Previously only a scope name existed, with no endpoints anywhere.
- `references/conversation-ai.md` — 12 endpoints, the API layer that configures the
  conversational agent itself (`2021-04-15`).
- `references/knowledge-base.md` — 14 endpoints, crawler + FAQs (`2021-04-15`). Feeds both
  Conversation AI and Voice AI.
- `references/ad-publishing.md` — 94 endpoints, Facebook/Google/LinkedIn campaigns, adsets,
  ads, custom audiences, pixels, lead forms, reporting, keyword ideas.
- All five generated directly from the published OpenAPI specs, so endpoint paths, scopes,
  required params and descriptions are the spec's own.

### Added — the v3 generation
- `references/auth.md` documents that a **second API generation shipped 2026-06-19**
  (43 specs, `Version: v3`) and its two breaking renames:
  `POST /oauth/locationToken` → `/oauth/location-token` and
  `GET /oauth/installedLocations` → `/oauth/installed-locations`, both removed without
  deprecation. **The v2 paths still work under `2021-07-28`, so this is forward-guidance,
  not a break.** Also covers the camelCase OAuth token body, the removal of `GET /contacts/`
  and `GET /users/`, and the wholesale replacement of the `/emails/builder*` surface.
- v3-only capability is called out where it lands: chat-widget, social planner scheduling
  queues + comments, brand voices, the rebuilt emails surface.

### Changed
- `references/modules.md` rewritten: header corrected from "All 35 GHL Modules" to **41**,
  every endpoint count re-read from the specs (invoices 41→42, calendars 34→41,
  conversations 19→29, opportunities 10→12, payments 24→23, marketplace 7→9,
  phone-system 2→4), and the seven modules it omitted entirely added — agent-studio,
  conversation-ai, knowledge-base, brand-boards, ad-manager, affiliate-manager, chat-widget.
  Store, snapshots, proposals and marketplace billing gained real endpoint lists.
- `SKILL.md` module-stats table rebuilt with per-module Version headers; totals corrected
  from "413 endpoints, 35 modules, 106 scopes" to **576 operations, 41 specs, 118 scopes**.
- Opportunities pipeline CRUD, announced 2026-06-26, is **absent from both published specs**
  — noted as "announced, not yet in the published spec; probe live before use" rather than
  documented as available.

### Verified unchanged (deliberately not touched)
- Workflows remain **read-only** — `GET /workflows/` is the only operation in both the v2
  and v3 specs. Base URL, rate limits and header names, the medias `2021-07-28` value, and
  the conversations/calendars `2021-04-15` values were all confirmed correct.

**Source for every claim:** the `Version` enums, paths, and `security` blocks published at
`https://github.com/GoHighLevel/highlevel-api-docs` (v2 `apps/`, v3 `apps/v3/`), plus
`docs/oauth/Authorization.md` and `docs/oauth/Scopes.md`, all enumerated 2026-08-03.

---

## [v6.6.3] - 2026-07-01 — docs: unified 11-alias GHL LOCATION-PIT resolver + platform-identity rewrite

### Changed
- Credential resolver chains in `EXAMPLES.md`, `INSTALL.md`, `QC.md`, and
  `qc-ghl-convert-and-flow.sh` expanded from the 5-alias chain shipped in v6.6.2 to the full
  canonical 11-alias LOCATION-PIT set (`TERMINOLOGY.md`). `qc-ghl-convert-and-flow.sh`'s
  `LEGACY_RE` guard (fails the build if a shipped example references an unresolved legacy `$VAR`)
  extended to cover every newly-added alias name.
- `SKILL.md`: "What Is This Skill?" rewritten to lead with the GHL = Convert & Flow = Go High
  Level platform-identity statement and the "the API key IS the PIT" framing (replacing the older
  "also branded as" phrasing). Quick Reference table row corrected from "API key type: OAuth2
  Bearer" / "Deprecated: use PITs" to "the API key IS the PIT — no separate type exists." The
  Credentials section now documents the unified 11-alias resolver and cross-references the
  PIT-aliases banner shared by all five GHL skills.

---

## [v6.6.2] - 2026-06-30 — Credential canonicalization, fail-loud preflight, hardened QC

### Why
The credential env-var name was fractured across five names; the primary runtime examples used
`$GHL_API_KEY` / `$GHL_LOCATION_ID` / `$PRIVATE_INTEGRATION_TOKEN`, which are unset on a correctly
provisioned box (canonical is `GOHIGHLEVEL_API_KEY` / `GOHIGHLEVEL_LOCATION_ID`), so most
copy-paste calls fired an empty Bearer and 401'd. QC normalized to a different name than the
examples, giving false-green. CORE_UPDATES.md also told the agent to load the 430K master
reference — contradicting SKILL.md and poisoning TOOLS.md/MEMORY.md. (Also reconciles the
skill-version.txt v6.6.1 / CHANGELOG v6.6.0 gap: v6.6.1 shipped with no changelog entry.)

### Changes
- CANONICAL CREDS: every runnable example now uses `$GOHIGHLEVEL_API_KEY` /
  `$GOHIGHLEVEL_LOCATION_ID` (SKILL.md, INSTRUCTIONS.md incl. substitution rules, INSTALL.md,
  EXAMPLES.md, ghl-convert-and-flow-full.md, references/opportunities.md + locations.md). The
  other references' Auth header lines now name the canonical var; cURL templates keep the
  `<PRIVATE_INTEGRATION_TOKEN>` placeholder with a substitute-and-double-quote note.
- ONE RESOLVER: shipped a single fail-loud resolver (sources `~/.openclaw/secrets/.env`, maps
  legacy aliases GHL_API_KEY / GHL_PRIVATE_INTEGRATION_TOKEN / PRIVATE_INTEGRATION_TOKEN /
  GHL_PRIVATE_TOKEN → canonical, blocks with the exact var+file+how-to, never an empty Bearer).
  Replaced the EXAMPLES.md robust pattern that tested the wrong var and false-blocked a box.
- ONE SECRETS PATH: `~/.openclaw/secrets/.env` everywhere; dropped `~/clawd/secrets/.env` wording
  (kept the VPS container-env + alias fallback). Core-file workspace path `~/clawd/` left intact.
- CORE_UPDATES.md: removed the "open the master reference before a GHL call" directive; re-pointed
  to Tier-0-first routing (CLI skill 44 → MCP → Tier 3); canonical creds; never-load-master.
- HARDENED qc-ghl-convert-and-flow.sh: canonical+alias resolver; live network-gated
  GET /locations/{id} (200 PASS / 401 FAIL incl. agency-PIT signal; Version 2021-07-28 doubles as
  the media-scope pre-check); FAIL if any shipped example references a legacy `$VAR`; self-locating.
- QC.md: env loaders resolve to the canonical names QC actually tests (kills the false-confidence
  gap); dropped the legacy clawd path.
- INSTALL.md: token example corrected from a stale JWT to the real `pit-...` format; smoke test
  now sources and guards credentials.
- Added verify-in-CF-UI pointers (SKILL.md table + inline on key writes) and documented the
  Skill 32 Command Center Kanban caller-contract (this library owns no board).
- Version header: left the 2021-04-15 default intact; documented that media uses 2021-07-28 —
  confirm per-endpoint, not a blanket change.

## [v6.6.0] - 2026-06-10 — Skill 44 era: header Tier 0 sentence + medias.md carve + modules.md pointer

### Why
Skill 36's router now routes Tier 0 (Convert and Flow CLI, skill 44) first. Skill 29 SKILL.md header and blockquote referenced the old 5-tier chain and lacked a media upload reference file.

### Changes
- SKILL.md frontmatter `description:` updated: "Use after Tier 0 (Convert and Flow CLI, skill 44) and the Tier 1/2 MCPs per skill 36's 6-tier escalation rules."
- SKILL.md body blockquote updated: Tier 0 (skill 44) added as the first stop; media uploads explicitly pointed to `references/medias.md`; "6-tier" replaces "5-tier".
- `references/medias.md` CREATED: carved from the proven skill 28/35/37 implementations. Documents POST /medias/upload-file endpoint, auth (LOCATION PIT only), Version header, multipart fields, parentId folder caveat, BOTH CDN URL forms (filesafe.space + GCS msgsndr), retry pattern, scope, pre-upload verification, imgBB out-of-band note.
- `references/modules.md` medias block updated: key endpoint line + deep reference pointer to medias.md added.

## [v6.5.6] - prior
