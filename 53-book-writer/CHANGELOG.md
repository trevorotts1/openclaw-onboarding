# Changelog — Skill 53 (book-writer)

## 1.1.0 — Wave-0 hardening (merge-train T-53-book-writer)

- **FIX-XC-09a — no-Anthropic gate fail-closed at P7.** `check_qc` no longer passes on an absent
  `RUN-LEDGER.json` (the old `Result("noop-ledger")` PASSED) and no longer scans a disabled `env={}`.
  P7 now hard-fails when the ledger is absent OR records ZERO model ids, and runs the credential scan
  against the LIVE process env (`env=dict(os.environ)`, NAMES only, values never read/printed).
- **FIX-XC-11e — role-SOP registry + dispatcher named + SOP mis-cite fixed.** The 7 role SOPs under
  `roles/` are registered in `roles/_index.json` with a canonical `content_sha` (new stamper/checker
  `scripts/hash_role_index.py`; `--check` gated in `verify.sh`). The SOLE dispatcher (foreman) is named
  as the assembler `run_book_writer.py`. `universal-sops/book-writer-craft/SOP-BOOK-01` no longer
  mis-cites the palette as `roles/PERSONAS.json` / "7 named book personas" (it is the skill-root DATA
  palette; the 7 role SOPs live in `roles/`).
- **FIX-S36-50 — human-gate approval receipts are now machine-checked.** `run/checkpoints/gate-receipts.json`
  (`approved:true` + `approved_by` + timestamp, mirroring Skill 48's shape) is REQUIRED: GATE-1 at P3 and
  GATE-2 at P4 always; GATE-3/GATE-4 at P6 when the matching revision round ran. A file authored by the
  pipeline no longer self-approves a gate.
- **FIX-S36-51 — preflight really probes.** `preflight.sh` runs a bounded `ollama list` + records
  provider-key NAMES (never values), preserves operator-filled tiers, and HARD-FAILS (exit 7) when a
  REQUIRED tier (HEAVY/MID/FORMATTER) is unresolved or resolves to an `/anthropic|claude/i` id. With
  `--run-dir` it cross-checks the resolved tier→model map into `RUN-LEDGER.json`.
- **FIX-S36-52 — deliver bundle + P8 checker + staging discipline.** (i) P8-DELIVER is a real checker:
  it copies the certified bundle to a labeled, timestamped `~/Downloads` folder (root overridable via
  `BOOK_WRITER_DELIVERY_ROOT`) and re-verifies every file's sha256 against `MANIFEST.json`. (ii)
  `prove_bw_anon` now RUNS in the runtime pipeline (P6, over the assembled bundle) and the PERSONAS.json
  gate mis-cite (`scripts/qc-assert-no-client-names.sh`, which never shipped) is fixed to
  `scripts/prove_bw_anon.py`. (iii) `mc_board` receipt path is parameterized to `run/checkpoints/`
  (was `working/checkpoints/`). (iv) the bundle is assembled into a STAGING dir and promoted to
  `delivery/` ONLY after a full P0→P7 pass; a gate failure quarantines it — an uncertified book never
  sits in `delivery/`.
- Determinism preserved: the golden `certificate_sha` (`691733c8…`) is unchanged; `verify.sh` +
  `qc-book-writer.sh` are green.
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
