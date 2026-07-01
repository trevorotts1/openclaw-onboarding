# Changelog - ghl-convert-and-flow (Skill 29)

All notable changes to this skill are documented here.

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
