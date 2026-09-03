# Changelog - ghl-convert-and-flow (Skill 29)

All notable changes to this skill are documented here.

---

## [v6.9.1] - 2026-09-03 — safe contact upsert policy: generic add/save defaults to upsert

### Changed
- **Contact write decision table in INSTRUCTIONS.md.** Generic "add/save this
  person" routes to POST /contacts/upsert (match keys + supplied fields only);
  POST /contacts/ is labeled explicit-new-record only; known contactId reads
  first then PUTs supplied fields. Safe payload rule (no empty/null/blank, no
  tags array in write bodies) and verify-after-write (GET read-back; never
  re-fire the write to check) documented.
- **`references/contacts.md` routing header + upsert-first endpoint notes** and
  **`references/modules.md`** endpoint labels match the same policy.
  "Contact Created" workflow triggers untouched (event names, not instructions).

## [v6.9.0] - 2026-08-03 — five-version model, reversals after independent web validation

### Reverted — two "corrections" from v6.7.0 that were themselves WRONG
An independent web validation showed the GitHub OpenAPI repo (which v6.7.0 treated as ground
truth) **lags HighLevel's live docs** — last repo commit 2026-06-19, most specs synced
2026-05-01, `saas-api.json` synced **2025-08-13**, while the changelog runs to 2026-07-30.
Two v6.7.0 verdicts were artifacts of that lag. My own live probe agreed with the validator.

- **SaaS `2023-02-21` restored.** HighLevel publishes a complete SaaS documentation set under
  `2023-02-21` and it is a first-class supported version. **PROVEN live: `GET
  /saas-api/public-api/agency-plans/{companyId}` returns 200 under it.** Changing it to
  `2021-04-15` (from the year-stale spec file) was wrong.
- **`POST /users/` `2023-02-21` restored in skill 44.** Documented verbatim at
  `marketplace.gohighlevel.com/docs/2023-02-21/ghl/users/create-user/index.html`. It is
  **not** a contradiction with the agency reference's `2021-07-28` — HighLevel documents the
  endpoint under multiple supported versions and both work.
- **The "causing live 400s" rationale is withdrawn everywhere.** PROVEN: `GET /contacts/`,
  `/users/` and `/calendars/` return 200 under all four published versions. No endpoint was
  found that rejects `2021-04-15`. The `2021-07-28` standardisation stands as a **consistency
  choice**, not a bug fix. Anyone chasing a real client failure should look at scopes,
  PIT-vs-OAuth and location-vs-company token first.

### Changed — the version model was structurally wrong
- **There are FIVE concurrently-supported versions, not "v2 and v3"** — `v3` (released
  **June 11, 2026**, not 06-19), `2023-02-21`, `2021-07-28`, `2021-04-15` and `legacy`,
  **every one "Supported until: TBD"**. No retirement dates, no forced migration. An older
  supported version is not a defect.
- **The Version is declared PER-OPERATION, not per-app.** `ad-publishing-v3` has 95 ops of
  which **94 still declare `2021-07-28`**. `phone-system-v3` names the parameter lowercase
  `version`; `store`/`store-v3` declare none. Documented, with the list of operations that
  declare no Version parameter at all.
- Counts corrected: **32** specs declare `2021-07-28` exclusively (33 accept it, counting
  `links`) — not "33 of 41".
- A **standing staleness warning** now sits in `auth.md`, `api-generations.md` and every
  reference banner: check `marketplace.gohighlevel.com/docs` before calling any doc wrong.

### Added
- **Opportunities pipeline CRUD — the "do not ship" gate is LIFTED.** All four operations are
  documented live under `Version: v3`. Shipped with the semantics that bite: update replaces
  the whole `stages` array (omit a stage and it is deleted); **delete is an irreversible
  cascade that removes every opportunity in the pipeline**; `useOpportunityProbability`
  silently falls back if any stage lacks `stageWinProbability`.
- **Calendars v3 Services / booking-catalog surface (41 → 59 ops)** — the largest capability
  the earlier audit missed entirely. `/calendars/services/{catalog,bookings,locations}` and
  `/calendars/schedules/event-calendar/{calendarId}`.
- **Scopes rebuilt against the true union: 142.** The three sources are DISJOINT — pre-v3
  specs 118, v3 specs 127, `Scopes.md` 91. Names which source each came from, lists the 13
  v3-only scopes and the 4 dropped in v3. **`pipelines.create` removed** — it is a
  response-body enum on `/users/*`, not a requestable OAuth scope.
- Webhook facts no skill carried: **retries fire ONLY on HTTP 429** (a receiver returning 500
  gets no retry), user-lifecycle webhooks (`user.created|updated|deleted`), and the Webhook
  Logs dashboard.
- SaaS **deprecated/current endpoint split** documented; the `allow-attach-rebilling`
  GET-vs-POST conflict between HighLevel's own changelog and spec flagged as verify-live.

### Not asserted (no published basis)
- v3 is **not** called GA/beta/preview by HighLevel — do not quote a maturity label.
- HighLevel published **no** deprecation guidance for the OAuth renames, and no version has a
  retirement date.
- No MCP rate limits are published.

---

## [v6.8.0] - 2026-08-03 — v3 promoted to a first-class generation, verified by live probe

### Added
- **`references/api-generations.md`** — the artifact that prevents the whole class of defect
  fixed in v6.7.0. Covers: both generations side by side (41 v2 specs / **42** v3 specs), a
  **per-surface generation table** giving the correct `Version` for every one of the 41
  surfaces plus whether a v3 spec exists and when to prefer it, the generation-gated paths,
  first-class treatment of the two breaking OAuth renames with runnable cURL for both forms,
  everything v3 adds that v2 cannot do, and a four-step decision rule.
- **`references/agency-api.md`** — agency/company-scoped operations (OAuth token management,
  sub-account provisioning, the 22 SaaS operations, agency users, companies, snapshots,
  marketplace billing) brought **into the repo** for the first time. The
  `apis/GoHighLevel-Agency-API-Reference.md` file found on boxes is agent-authored TYP
  content with no repo source and is not published by `update-skills.sh`; this file is the
  repo-managed source of truth and states so explicitly.

### Fixed — by live read-only probe (GET only, operator-owned accounts, 2026-08-03)
- **Withdrew the "wrong Version header causes live 400s" claim.** It is false for the
  affected endpoints. `GET /contacts/`, `/users/` and `/calendars/` return **200 under all
  four published version strings** (`2021-07-28`, `2021-04-15`, `2023-02-21`, `v3`). What is
  true, and now documented: omitting the header is a **401** (`"version header was not
  found."`) and an unpublished value is a **401** (`"version header is invalid"`). The
  v6.7.0 corrections remain right — they align the docs with what HighLevel declares — but
  the defect was documentation drift and fleet-wide contradiction, not live 400s.
- **The v3 rename IS real and IS enforced, for the path that matters.**
  `GET /oauth/installed-locations` returns **404 `Cannot GET` under `2021-07-28`** and
  resolves only under `Version: v3`; the v2 form `GET /oauth/installedLocations` resolves
  under **both**. Same pattern proven for `/brand-boards/.../brand-voices` (200 under `v3`,
  404 under `2021-07-28`). So: a renamed or brand-new v3 path needs `Version: v3`; an
  existing v2 path keeps working everywhere.
- **Spec removals are NOT enforced at the runtime yet.** `GET /contacts/`, `GET /users/` and
  `GET /emails/builder` all still return 200 under `Version: v3` despite the v3 specs
  dropping them. Documented as "dropped from the spec, still answering — do not rely on
  that lasting" rather than as a flat removal.
- **`GET /opportunities/pipelines/{pipelineId}` is PROVEN live** (200 under both
  `2021-07-28` and `v3`) despite being absent from both published specs.
  `references/opportunities.md` now documents it. The pipeline WRITE operations were **not**
  probed — no write call is made against GoHighLevel for verification — and remain flagged
  confirm-before-use.
- **`X-RateLimit-Daily-Reset` is real**, observed on live responses, though absent from
  HighLevel's published header list. Skills 36 and 44 rely on it; that reliance is sound.
- **`2023-02-21` still works on SaaS**: `GET /saas-api/public-api/agency-plans/{companyId}`
  returns 200 under it. Existing SaaS code on the old value is not broken. `2021-04-15` is
  still the documented value and the one to use for new work.

### Changed
- v3 spec count corrected **43 → 42** (enumerated from the GitHub contents API; the delta
  report that drove this work said 43).
- `SKILL.md` and `references/auth.md` restated to match the probe findings, with pointers to
  `api-generations.md`.

**Every claim in this release is either a `Version` enum / path read out of the published
OpenAPI specs, or a live GET result recorded on 2026-08-03. No write calls were made.**

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

## [v7.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
