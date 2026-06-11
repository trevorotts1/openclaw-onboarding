# Changelog - ghl-convert-and-flow (Skill 29)

All notable changes to this skill are documented here.

---

## [v6.6.0] - 2026-06-10 — Skill 44 era: header Tier 0 sentence + medias.md carve + modules.md pointer

### Why
Skill 36's router now routes Tier 0 (Convert and Flow CLI, skill 44) first. Skill 29 SKILL.md header and blockquote referenced the old 5-tier chain and lacked a media upload reference file.

### Changes
- SKILL.md frontmatter `description:` updated: "Use after Tier 0 (Convert and Flow CLI, skill 44) and the Tier 1/2 MCPs per skill 36's 6-tier escalation rules."
- SKILL.md body blockquote updated: Tier 0 (skill 44) added as the first stop; media uploads explicitly pointed to `references/medias.md`; "6-tier" replaces "5-tier".
- `references/medias.md` CREATED: carved from the proven skill 28/35/37 implementations. Documents POST /medias/upload-file endpoint, auth (LOCATION PIT only), Version header, multipart fields, parentId folder caveat, BOTH CDN URL forms (filesafe.space + GCS msgsndr), retry pattern, scope, pre-upload verification, imgBB out-of-band note.
- `references/modules.md` medias block updated: key endpoint line + deep reference pointer to medias.md added.

## [v6.5.6] - prior
