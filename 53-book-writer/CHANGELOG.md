# Changelog — Skill 53 (book-writer)

## 1.0.0 — initial release

- **Book Writer — Ghostwriting Engine (Avatar Alchemist, BOOK version).** Turns ONE completed
  book-intake interview into a tone-matched 12-chapter nonfiction book plus companion assets (avatar
  dossier, the blended "The {First} {Last} Tone", locked title/subtitle + approved outline, manuscript,
  a 30-Day Challenge, an AI cover prompt).
- **Book/Brand version selector (Q0):** `version=book` runs here; `version=brand` hands off to Skill 52
  (avatar-alchemist). Modes `full` and `4x3x3` (offer book → `433_Deck_Data.json` handed to Skill 51).
- **Enforcement:** twelve fail-closed, model-free provers (`scripts/prove_bw_*.py`) MEASURE the stripped
  text and ignore self-reported counts — 12 chapters, 2000–3500 words each, ≥3000-word blended tone,
  exactly 30 challenge days, byte-exact locked title/subtitle, verbatim story placement, sequential
  chapter-batch continuity, no placeholders, no Anthropic ids, anonymization. `AF-BK-*` map in
  `BOOK-WRITER-MANIFEST.json`.
- **One governed path:** `book-writer-entry.sh` (deps → bypass-scan → hash-pin → nonce) →
  `run_book_writer.py` (deterministic assembler/certifier, phases P0→P8, no skips) → signed
  `PROCESS-CERTIFICATE` with a deterministic `certificate_sha` on a full pass.
- **Shared tone core:** stages 04–08 baked byte-identical from `shared-utils/tone-writing-core`
  (proved by `verify_tone_core_sync.py`); shared with Skills 52 (Brand) + 54 (Anthology).
- **Runtime posture:** fully local — no n8n / Airtable / Google / Gmail / Slack / GHL — on the client's
  own model providers, never Anthropic, never operator keys.
- Cross-linked with (never merged into) Skill 52. Anthology is the separate sibling Skill 54.
- Golden regression sample `examples/golden-marcus-halloway/` (*The Quiet Authority*, fictional author
  Marcus Halloway) — data anchors + broken-variant generator shipped; Wave-2 authors the golden prose
  and Agent D assembles the certified bundle.
