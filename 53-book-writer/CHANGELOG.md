# Changelog — Skill 53 (book-writer)

## 1.1.5 — 2026-07-12 — P2-07: mc_board.py never silently drops an unrecognized department_slug

### Fixed
- **`mc_board.py` — an UNRECOGNIZED `department_slug`** (a typo, a regressed
  hardcoded fake slug like the historical `funnels`/`books`/`email` family, or an
  empty string) is now caught client-side before the ingest POST, logged loudly to
  stderr, and RE-ROUTED to the `general-task` catch-all department with the
  original bad slug annotated on the card description and on `begin_run`'s initial
  board event note. Never silently dropped. Recognized slugs (the 22 mandatory + 6
  universal-primary floor departments + known variant aliases, mirrored from
  `23-ai-workforce-blueprint/scripts/department-floor.py:116-158`) pass through
  unchanged. Applied identically to the shared `mc_board.py` family
  (49/50/53/54/55/56/57), preserving Skill 53's `receipt_subdir` parameterization.

### Added
- **`test_cc_contract.py`** — six new regression cases: an unrecognized slug
  reroutes to `general-task`, an empty slug reroutes, a known slug
  (`web-development`) and `general-task` itself pass through unchanged, the
  reroute logs loudly to stderr, and `begin_run`'s initial advance note records the
  original bad slug as a board-visible event.

## 1.1.3 — fabricated Command Center department slug corrected (FIX-BK-DEPT-01)

- **Pre-existing shipped defect fixed — no gate/schema change.** `run_book_writer.py`'s
  `_mc_board_begin` posted every Book Writer task card with a hardcoded `department="books"`,
  but no script anywhere in this repo ever creates a "books" department (no workspace row, no
  agent runtime, nothing in `department-naming-map.json`). `scripts/mc_board.py` fails SOFT on
  an unrecognized `department_slug` (a board outage / bad value is caught, logged to stderr, and
  the run continues — never a gate), so this never threw a visible error: every Book Writer card
  has been silently dropped or misrouted since the skill shipped.
- **Root cause:** `WIRING-SPEC.md` section 8 documented the ORIGINAL intent — ride on an
  EXISTING department, the "Content / Publishing lineage, same owner as Skills 50/51" — but the
  shipped code used a standalone "books" slug that was never actually seeded to match that
  intent.
- **Fix:** `department="books"` -> `department="marketing"`, the REAL, mandatory,
  always-seeded canonical department (`23-ai-workforce-blueprint/department-naming-map.json`
  `.mandatory`) that `23-ai-workforce-blueprint/skill-department-map.json`'s skill-53 entry
  already authoritatively declares (`"departments": ["marketing"]`), matching sibling skills
  52 (avatar-alchemist), 54 (anthology-writer), 55 (product-bio), and 56 (sales-page-assets) —
  the same content/publishing family. Confirmed against a working sibling in the same shared
  `mc_board.py` helper family: `55-product-bio/run_product_bio.py` already correctly posts
  `department="marketing"`.
- **New regression coverage:** `scripts/test_department_slug.py` statically extracts the
  `department=` literal from `_mc_board_begin` and asserts it (a) is a member of the canonical
  mandatory department set, (b) is never the historic fabricated `"books"` slug, and (c) matches
  `skill-department-map.json`'s authoritative skill-53 binding. Wired into `verify.sh` (section
  10). This is purely Command-Center-board metadata (fail-soft, never a gate): the
  `certificate_sha` / SACRED invariants / golden `certificate_sha` are unaffected.

## 1.1.2 — Wave-2 doc-truth correction (FIX-S36-49 · ruling R5)

- **Doc correction only — no code, no gate change.** Added an explicit **"Authoring layer — SHIPPED
  vs. PENDING (truthful status)"** section to `SKILL.md` and corrected the `prompts/<stage dirs>` bullet.
  This closes a no-false-done violation: `SKILL.md` sold "baked versioned prompts" for the whole stage
  graph, but only the **five shared-tone-core stages (04–08)** actually ship as
  `{system.md, methodology.md, user.md}` triplets. The **22 non-tone authoring-stage prompt dirs**
  referenced by `BOOK-WRITER-MANIFEST.json` `stages[]` (avatar 01–03, titles/blurb/outline 10–14,
  chapter batches 15–18, rewrites 19–20, challenge 21, cover 22–23, 4x3x3 extras 41–45) are **not yet
  shipped**. Per **ratified ruling R5 (2026-07-05)** the full 12-chapter authoring-triplet build is
  **DEFERRED to a separate scoped follow-up campaign** — this change only tells the truth about what
  ships today. Every SACRED invariant and its fail-closed prover is unchanged; no `_index.json`
  `content_sha` re-stamp is required (`SKILL.md` is not a hashed/indexed file, and the enforcement
  hash-pin set excludes it).

## 1.1.1 — merge-train T-w1-board-and-54 (Wave-1)
- **FIX-XC-06** — on a fail-closed gate (any P0–P7 phase or P8-DELIVER) the run now
  marks its Command Center card `blocked` (failing phase + AF code as the note)
  instead of stranding it at in_progress. Added the fail-soft `block_run()` wrapper to
  `scripts/mc_board.py`, preserving this skill's parameterized `run/checkpoints`
  receipt_subdir. Board work stays fail-soft — never affects the assembler's exit code.

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
