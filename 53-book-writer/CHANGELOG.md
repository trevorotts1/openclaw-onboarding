# Changelog — Skill 53 (book-writer)

## 1.2.0 — BUG-3: the 22 non-tone authoring-stage prompt triplets now ship; the authoring layer is complete

- version pin in `WIRING-SPEC.md` corrected from 1.1.6 to 1.2.0 (version-pin table row and README
  catalog row template).
- The 22 non-tone prompt triplets referenced by `BOOK-WRITER-MANIFEST.json` `stages[]` — avatar
  (`01`–`03`), titles/blurb/chapter-titles (`10`–`12`), outline/extract (`13`–`14`), the four chapter
  batches (`15`–`18`), the two book rewrites (`19`–`20`), the 30-Day Challenge (`21`), cover prompt/image
  (`22`–`23`), and the 4x3x3 extras (`41`–`45`) — are baked under `prompts/` alongside the five tone-core
  stages (04–08). The full authoring layer now ships.
- `SKILL.md` "Authoring layer" disclosure updated from "SHIPPED vs. PENDING" to reflect that every
  authoring stage is driven by a pinned baked prompt triplet on disk.
- `run_book_writer.py` fail-closed messages now reference the baked stage prompt (e.g. `prompts/<stage>`)
  instead of the stale "authoring stage deferred to a scoped follow-up campaign" text. Fail-closed
  behavior is unchanged.

### Verified (2026-08-10, D-1/D-17 repair campaign — documentation only, no code change)

- **D-17 — non-UTF-8 JSON already fail-closes.** `scripts/_bw_common.py` `read_json()` catches
  `(OSError, ValueError)`; `UnicodeDecodeError` is a `ValueError` subclass, so a non-UTF-8 JSON file
  exits 3 (USAGE/IO) with a clean stderr message, never a traceback. Proven live with a Latin-1 file:
  `printf '\xff\xfe{"a":1}' > /tmp/latin1.json` then `read_json('/tmp/latin1.json')` →
  `USAGE/IO: cannot read/parse JSON … 'utf-8' codec can't decode byte 0xff …`, exit code 3.
  No redundant `UnicodeDecodeError` except clause was added — the proof decides, and it passed.
- **D-1 — `CHAP_WORD_MAX = 3500` is consistent.** The constant (`scripts/_bw_common.py`) matches the
  autofail trigger (`prove_bw_chapters.py` line 44: `wc < CHAP_WORD_MIN or wc > CHAP_WORD_MAX`), the
  manifest autofail trigger (AF-BK-CHAP-LEN: "any chapter's MEASURED stripped word count is outside
  [2000,3500]"), and the SACRED floor 2000–3500. No change. The golden example's largest chapter
  (`ch09.md`, 2512 stripped words) does not exercise the ceiling — expected, not a defect.
- **UNIT 11 — golden example delivery title-lock drift fixed.** The locked GATE-1 title/subtitle
  (`The Quiet Authority: How the Best New Leaders Trade Control for Trust`) was missing from
  `00-INDEX.md`, `Avatar_Document-Marcus_Halloway.md`, and `30_Day_Challenge-Marcus_Halloway.md`
  under `examples/golden-marcus-halloway/delivery/Marcus_Halloway-Book/`. The three delivery files
  now carry the byte-exact locked strings and `prove_bw_titlelock.py` PASSes on all three.
- **UNIT 12 — golden example delivery MANIFEST.json self-hashes refreshed.** The manifest's
  `files[]` sha256 table in `examples/golden-marcus-halloway/delivery/Marcus_Halloway-Book/`
  had drifted from the on-disk delivery files: the manifest was amended (and UNIT 11 changed
  three delivery files) after its hash table was written. All six stale rows are re-computed
  from the current file bytes — `00-INDEX.md`, `30_Day_Challenge-Marcus_Halloway.md`,
  `Avatar_Document-Marcus_Halloway.md`, `MANIFEST.json`, `PROCESS-CERTIFICATE.json`,
  `PROCESS-CERTIFICATE.md` — and every row now matches its file's sha256. Invariant note: the
  manifest's OWN row stores the sha256 of the manifest as fixed in this commit (i.e. the
  hash of the manifest as of the final edit); because the value is part of the file it
  hashes, that row can never re-verify against the live file (a self-hash fixed point
  does not exist) — re-hash it any time the manifest is amended.
- **UNIT 5 — 52→53 route manifest fixed.** `52-avatar-alchemist/AA-PIPELINE-MANIFEST.json`
  now routes the book intake to `53-book-writer` with a matching `handoff` field, and
  `AA-GATE-HASHES.json` re-pins the manifest so Skill 52's verify.sh routing test passes.
- **UNIT 13 — counting claims corrected.** SKILL.md and related docs now state the real
  numbers: 21 Python files and 14 prover scripts (was "20 Python files" / "twelve
  fail-closed provers"), and the 4x3x3 pipeline stage count corrected from 45 distinct
  stages to 27.
- **UNIT 4 — README catalog row fixed.** The `53-book-writer` row in README.md now
  displays version 1.2.0, matching `53-book-writer/skill-version.txt`.
- **UNIT 7 — 4x3x3 trigger wording corrected.** The manifest autofail trigger and
  SKILL.md/WIRING-SPEC descriptions now state the 4x3x3 counts prover fires on **OR**
  semantics (either wrong count independently triggers AF-BK-433-COUNTS), matching the
  shipped `prove_bw_433.py` implementation.
- **UNIT 15 — REPAIRS.md reference corrected.** Row 7's Skill 44 hook reference is now a
  generic integration hook, and the row names the real sibling Skill 54.
- **UNIT 1 — version pins corrected.** `WIRING-SPEC.md` version-pin table row and the README
  catalog row template were still 1.1.6; both now pin `1.2.0`, matching
  `53-book-writer/skill-version.txt` and the SKILL.md frontmatter.
- **UNIT 2 — avatar prover shipped.** `scripts/prove_bw_avatar.py` now enforces the avatar
  phase (previously declared but never enforced): the avatar dossier must exist, be
  non-empty, and reach 500 stripped words at `run/artifacts/01-avatar.md`, else the run
  fails closed with `AF-BK-AVATAR-MISSING` (exit 2). Wired into the manifest autofail map
  and the WIRING-SPEC §7 code list; `verify.sh` now runs 13 prover self-tests. Engine pin
  re-minted to cover the new prover.
- **UNIT 3 — AF-BK-ACCEPT-* codes added to the manifest.** The three intake-accept codes
  (`AF-BK-ACCEPT-UNREADABLE`, `AF-BK-ACCEPT-WRONG-VERSION`, `AF-BK-ACCEPT-REJECTED`) were
  documented in WIRING-SPEC §7 but missing from `BOOK-WRITER-MANIFEST.json` `autofails`;
  all three are now declared in the manifest (22 autofail rows, including the UNIT 2
  `AF-BK-AVATAR-MISSING` row).
- **UNIT 6 — intake-accept documented.** The `bw_intake_accept.py` receipt contract (sha256
  over the exact forwarded bytes, exit 0 accepted / 2 rejected / 3 usage-io, the three
  refuse codes) is now documented in `SKILL.md` and `INSTRUCTIONS.md` (Skill 52 selector
  row), matching the shipped script.
- **UNIT 8 — department wiring resolved in §8.** `WIRING-SPEC.md` §8 now records the
  department wiring as resolved (marketing, always-seeded; declared in
  `23-ai-workforce-blueprint/skill-department-map.json` skill-53 entry), with past-tense
  record keeping instead of open instruction.
- **UNIT 9 — reciprocal references added.** `52-avatar-alchemist/SKILL.md` now links back to
  the Book Writer (Skill 53) route, and `51-signature-presentation/SKILL.md` references
  the Book Writer handoff — both directions of the cross-skill graph now point both ways.
- **UNIT 10 — mini-app removed.** The stale `mini-app/` directory is gone from the skill
  tree (untracked or tracked content fully removed); nothing in the skill references it.

## 1.1.6 — 2026-07-21 — T0-28: this skill can now ACKNOWLEDGE a routed intake

### Added
- **`scripts/bw_intake_accept.py`** — the target side of the 52 -> 53 route, and the
  reason `book-routed` can mean something. Skill 52 previously decided a book intake was
  routed because a sibling `53-*book*` directory existed; this skill was never consulted.
  This command is that consultation: it reads the forwarded intake, decides acceptance
  with **this skill's own fail-closed gate** (`prove_bw_intake.evaluate`, handoff mode —
  never a re-implementation of it), and emits a machine-readable receipt on stdout.
- The receipt carries the sha256 of the **exact forwarded bytes**, this skill's name and
  version, the decider, and a receipt id, so a caller that forwards one payload cannot
  satisfy itself with a receipt minted for another. `--receipt-out` also persists it; a
  failed persist is a hard error (exit 3), never a quiet acceptance.
- Refusals are reasoned, not silent: `AF-BK-ACCEPT-UNREADABLE` (unparseable bytes),
  `AF-BK-ACCEPT-WRONG-VERSION` (a brand intake, which belongs to Skill 52), and
  `AF-BK-ACCEPT-REJECTED` carrying the underlying `AF-BK-*` codes.
- Exit 0 accepted · 2 rejected · 3 usage/IO. `--self-test` covers all five outcomes and
  proves two different payloads never share a digest.


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
