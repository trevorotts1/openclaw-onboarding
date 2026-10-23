# Signature reference set

This folder holds no bundled reference images. The real reference set is skill 71's visual
standard set:

`../../71-blackceo-signature-page/assets/visual-standards/`

Distribution note: that path is the repo layout (numeric-prefixed skill folder). Installed
skills trees may name the folder `blackceo-signature-page` without the prefix (Claude Code
and claude-nine skills directories), and the design-style visual examples resolve the same
way — the intake engine accepts either name under the repo, `~/.openclaw/skills`,
`~/.claude/skills`, `~/.claude-nine/skills` and `/data/.openclaw/skills`.

That set ships 44 images — wireframes, mockups, and the hybrid board — inventoried in
`manifest.json` (44 entries, 41,607,411 bytes total, largest file 6,647,564 bytes,
every entry carrying `file`, `kind`, `bytes`, `sha256`, `width_px`, `height_px`). Read
`README.md` there for what the set is and how reviewers use it, and `ANALYSIS.md` for the
classification rule and provenance.

Default image mode is `none` (pure text-to-image; the look is carried entirely by the
Signature Grade Block). Trevor loads a curated `signature_set` into this folder later
(PRD Open Decision O6); until then `reference_images.mode` stays `none`.
