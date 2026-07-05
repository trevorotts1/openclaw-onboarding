# Changelog — Skill 53 (book-writer)

## 1.0.4 — 2026-07-05 — shared mc_board board review-skip root fix (FIX-XC-01a)

- **`scripts/mc_board.py` (shared helper, byte-identical across 49/50/53/55/56/57):** the producer no
  longer PATCHes a run's Command Center card straight to `done`. `complete_run` now posts the terminal
  status `review` ("certified — awaiting QC promotion") with the deliverable link registered on the
  card; `card_advance(status="done")` is HARD-BLOCKED. `review -> done` is owned exclusively by the
  independent QC scorer (PASS >= 8.5). Ports the CC `LEGAL_TRANSITIONS` map + BFS legal-path walker +
  current-status GET from `48-facebook-ad-generator/scripts/cc_board.py`, and honors
  `CC_STATUS_PATH_TEMPLATE` / `CC_STATUS_METHOD` for route parity. Still fully fail-soft — the board is
  a VIEW, never a gate.
- **`scripts/test_cc_contract.py` (new, byte-identical):** stdlib contract test proving `complete_run`
  posts `review` and never `done`, the legal-path walk, route-template parity, and disabled-board no-op.

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
