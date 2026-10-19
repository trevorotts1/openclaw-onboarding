# reference-set/ — Skill 56 (Sales Page Assets)

Fictional, fleet-clean reference material only. **NEVER a real client name, brand, founder, page HTML,
image URL, or secret** (rule R5). Use the fictional slugs `jane-doe` / `glow-method` in any example.

The canonical VALID + VIOLATION fixtures live INSIDE each prover's `--self-test` (deterministic, no
external files), so this folder holds no golden run by default. A golden regression sample added here
must clear the same bars the provers enforce AND the content-authenticity grade (>= 8.5, HANDOFF fix #8):
no 6+ word phrase repeated more than ~3x, no mid-phrase cutoffs, image prompts genuinely authored.

The real reference images for sales-page assets are skill 71's visual standard set:

`../../71-blackceo-signature-page/assets/visual-standards/`

That set ships 44 images — wireframes, mockups, and the hybrid board — inventoried in
`manifest.json` (44 entries, 41,607,411 bytes total, largest file 6,647,564 bytes). Score assets
against the traits in skill 71's `references/qc-contract.md` ("Visual standard set traits") with
this set open beside the artifact under review.

Run the full read-only gate with `bash ../verify.sh`.
