# SPEC — Book Writer (Skill 53) end-to-end review fixes — 2026-08-24

Scope: `53-book-writer/` (+ its consumers in `~/blackceo-command-center/` where the board contract
touches it). Baseline health proven BEFORE any fix: 13 prover self-tests PASS, verify.sh full battery
PASS (incl. golden certificate idempotency), ENGINE-PIN matches, 66 prompt pins match disk,
tone-core lockstep across skills 52/53/54 PASS, roles/_index.json CHECK PASS, 18/18 broken variants
rejected by make_broken.py fresh run, test_cc_contract.py (19) / test_mc_board_reconcile.py (19) /
test_department_slug.py (3) all OK.

Review method: adversarial probe scripts against live code paths (no grep-only claims); five Sonnet
reviewer agents on provers/fixtures, CC integration, cross-skill wiring, workflow trace, and
Convert&Flow surface; findings merged below. Each finding carries file:line refs and a concrete
failure scenario.

---

## Confirmed findings (main-agent probes)

### F01 — HIGH — chapter keying inconsistency between orchestrator and prover
- Where: `run_book_writer.py:176-179` (`chapter_files()` = `sorted(self.chapters_dir.glob("ch*.md"))`,
  enumerated in manuscript_text/check_chapters) vs `scripts/prove_bw_chapters.py::_from_dir`
  (keys chapters by filename digits).
- Failure: files named `ch1.md` vs `ch01.md`, or an extra `ch13.md` dropped in, enumerate differently
  in the two components → title-lock/manuscript assembly can read a different set than the count/len
  prover measured → a chapter can be assembled but never length-proven.
- Fix: single canonical enumeration — key by digits everywhere; fail closed on duplicate or missing
  numbers (1..12 exact, no extras); orchestrator cross-checks each embedded heading number.

### F02 — HIGH — no-Anthropic walker misses preflight_tier_map values
- Where: `scripts/prove_bw_noanthropic.py::_iter_model_ids` walks only keys
  `model/model_id/resolved_model/provider_model`; `preflight.sh` writes
  `led["preflight_tier_map"]={t: tiers.get(t,"")}` into RUN-LEDGER.json — plain string values that
  escape the walker.
- Failure: an `/anthropic|claude/i` id preserved in `preflight_tier_map.HEAVY-WRITER` passes the gate
  even though the same id under `model` would fail it.
- Fix: scan ALL string leaf values of RUN-LEDGER.json for `/anthropic|claude/i` (keep the existing
  targeted walk as fast-path); add negative test: tier-map value containing "claude" must autofail
  AF-BK-ANTHROPIC.

### F03 — MED — title-lock target list silently skips missing files
- Where: `run_book_writer.py:337-341` check_package builds title-lock targets with `if p.is_file()`.
- Failure: a stage that should have produced e.g. cover prompt fails silently → title lock is proven
  over fewer files → weaker lock, no error.
- Fix: required targets are required — absent file is its own fail-closed violation (distinct AF
  message), not a silent skip.

### F04 — MED — bypass scan covers only *.py
- Where: `scripts/prove_bw_process.py::_run_dir_sources` rglobs only `*.py`.
- Failure: a `.sh`/`.js`/`.ts` helper inside the run dir calling n8n/GHL/Drive endpoints evades
  AF-BK-ENTRY-BYPASS entirely.
- Fix: include `*.sh *.js *.ts *.mjs *.cjs`; negative test: bypass pattern in a .sh file must trip
  the scanner.

### F05 — MED — GATE-433 declared in manifest, never enforced
- Where: `BOOK-WRITER-MANIFEST.json` gates_order declares `"GATE-433"` first for mode 4x3x3;
  `run_book_writer.py` enforces only GATE-1-title (:234), GATE-2-outline (:251), GATE-3-approval
  (:362), GATE-4-approval-r2 (:368). `'GATE-433' in src` is False.
- Failure: 4x3x3 runs advance past a declared gate without its receipt — manifest promises what the
  engine does not do (enforcement-not-description violated).
- Fix: either enforce GATE-433 receipt in 4x3x3 mode before P4 advances, or remove it from gates_order
  if the 433 counts/map provers fully subsume it — enforcement must match the manifest exactly.

### F06 — LOW — version drift: manifest says 1.2.0, SKILL.md frontmatter says 1.2.2
- Where: BOOK-WRITER-MANIFEST.json `skill_version` vs SKILL.md `version: 1.2.2`.
- Fix: align both at the next stamped version (this release bumps anyway).

### F07 — LOW — stage 45 artifact unchecked
- Where: stages 41–44 artifacts are proven (433 provers); stage 45 output has no prover hook.
- Fix: require stage 45's artifact like its siblings, or mark it explicitly degradable in the manifest
  the way stage 23 (optional cover PNG) is — no silent middle ground.

### F08 — LOW — BW_ANON_TOKENS unset is silent
- Where: `prove_bw_anon.py` reads BW_ANON_TOKENS; entry/preflight never warn when unset.
- Failure: anonymization prover runs with an empty token list → vacuous pass.
- Fix: preflight/entry emit a visible warning when BW_ANON_TOKENS unset/empty (prover itself stays
  fail-open-free per its own semantics; warning makes the vacuous pass visible).

### F09 — LOW — na_autopick consumer undocumented
- Fix: document the na_autopick consumer in WIRING-SPEC.md + the relevant role SOP so downstream
  wiring is discoverable (docs-only).

---

## Reviewer findings (merged, verified against reports' own executed proofs)

### From rev-provers (prover suite adversarial review)

| ID | Sev | Finding | Fix |
|---|---|---|---|
| R-P1 | CRIT | `prove_bw_continuity.py:64` — continuity PASSES with ZERO chapters on disk (`elif chapter_sha.get(pc)` skips absent); deadbeef receipt shas pass | hard-fail `pc not in chapter_sha` + require len(chapter_sha)==12 |
| R-P2 | HIGH | `_bw_common.py:70` word_count defeated by U+200B/U+200C/U+00AD splitting words (1050 real words measured 2100) | strip_markdown deletes Cf/Cc chars + NFKC normalize; ZWSP negative self-test |
| R-P3 | HIGH | `make_broken.py:90,281-285` BLOCKED sentinel leaves ok untouched — 8/18 variants self-disable if source stubbed; latent gutting of negative suite | delete sentinel; missing source = FAIL |
| R-P4 | HIGH | `verify.sh:101` missing make_broken.py = WARN, verify exits 0 | [FAIL]+fails+=1; drop `>/dev/null 2>&1` at :92 |
| R-P5 | HIGH | `verify.sh:188,211-215` e2e gate + live hash-pin self-disable ([TODO] when ch12/SHIP_CERT absent) — only place entry.sh really runs | preconditions hard-fail; unconditional `prove_bw_process --run-dir --skill-dir`; `--certificate SHIP_CERT` |
| R-P6 | HIGH | `prove_bw_process.py:87` bypass-scan allowlist keyed on BASENAME — Slack poster at `run/prove_bw_tone.py` cloaked | delete name check; identity by resolved path only |
| R-P7 | HIGH | `install.sh:48-70` mint_pin recreates absent pin → rm pin + edit prover + reinstall = clean AF-BK-HASH-PIN | remove auto-mint; explicit `--mint-pin`; verify.sh asserts pin == committed value |
| R-P8 | HIGH | `prove_bw_noanthropic.py:36` isinstance(v,str) — `{"model":["anthropic/claude-opus-4"]}` yields nothing, evades gate | leaf-walk v on key match regardless of type; never fall through |
| R-P9 | HIGH | `run_book_writer.py:211-217,320-333` five gates existence-only (avatar/cover-prompt/titles/blurb/chapter-titles; zero-byte certifies); AF-BK-AVATAR-MISSING declared, no prover, no autofails entry | avatar prover (word floor + sections) + floors for others; register AF code |
| R-P10 | MED | Manifest autofail symbol drift: `_write_certificate`(actual `write_certificate`); HASH-PIN/ENTRY-BYPASS enforced_by "book-writer-entry" (really prove_bw_process.py); STAGE-SKIPPED names run() which never emits; nothing invokes `--certificate` → check_stage_chain dead | correct refs; verify.sh ast-resolves every enforced_by/py_symbol; call check_stage_chain inside write_certificate |
| R-P11 | MED | `prove_bw_process.py:157` `if skill_dir:` — omitting --skill-dir skips pin entirely (rc=0) | default skill_dir = parents[1] |
| R-P12 | MED | delimiter-free hash concatenation (process:108-111, install.sh:61) — boundary collisions | length-prefixed framing `name:len\n`; coordinated re-mint |
| R-P13 | MED | (=F04) rglob *.py only | extend {.sh,.js,.ts,.mjs,.cjs,.rb,Makefile} |
| R-P14 | MED | `prove_bw_stories.py:55` empty story set passes; intake.book_stories non-N/A but stories.json zero checked → certify | cross-check intake; fail on zero-checked with non-N/A intake stories |
| R-P15 | MED | AF-BK-ANON default-off vacuous (BW_ANON_TOKENS unset → no-op pass, self-test asserts correct) | require tokens file at delivery; fail P6 when absent (supersedes F08 warn-only) |
| R-P16 | MED | nonce self-forgeable (caller-controlled file + env var) — accident-prevention only, docstring implies security boundary | state honestly in WIRING-SPEC.md |
| R-P17 | MED | continuity receipts post-hoc forgeable; prover proves consistency not temporal injection; docstrings overclaim | soften MASTERDOC/REPAIRS/docstring claims |
| R-P18 | MED | `prove_bw_challenge.py` day numbers unchecked — 30× "Day 1" passes | assert sorted(day_numbers)==range(1,31) |
| R-P19 | MED | (=F01/T10) lexicographic sort scrambles ch1,ch10,ch2 → enumerate index mismatch feeds continuity | sort by extracted int; reject non-ch\d{2}.md |
| R-P20 | LOW | test-fixtures/ orphaned (prose refs only) | document or wire; no silent middle |
| R-P21 | MED | ANTHROPIC/CLAUDE_API absent from _OPERATOR_CRED_HINTS | add both |
| R-P22 | LOW | entry.sh:50,110,117 help/PLAN banner claim gates run under --plan; :96 skips | fix text |

### From trace-workflow (execution trace, engine run end-to-end)

| ID | Sev | Finding | Fix |
|---|---|---|---|
| R-T1 | FRAMING | run_book_writer.py dispatches ZERO LLM calls — post-hoc auditor, not executor; authoring is chat-layer reading baked prompts | correct framing in SPEC/WIRING-SPEC; no code change |
| R-T2 | HIGH | entry.sh never calls preflight.sh — model-map.json write-only; HEAVY-WRITER=claude-* box ships certified | wire preflight gate into entry before run dispatch (exit 7 semantics preserved); golden battery updated |
| R-T3 | HIGH | (=F02) preflight_tier_map values invisible to no-Anthropic walker | folded into deep-walk-all-string-leaves fix (with R-P8/R-T4/R-T5) |
| R-T4 | HIGH | nested model objects `{"model":{"id":"anthropic/..."}}` bypass | folded into deep-walk fix |
| R-T5 | HIGH | alias keys (model_name/modelId/llm/engine/model_used) bypass | folded into deep-walk fix (scan ALL string leaves) |
| R-T6 | HIGH | receipts existence-only: approved_by any string, timestamp unparsed, no artifact binding → forged "x"/2026-01-01 passes all gates | require artifact_sha256 == live sha of APPROVED-TITLE.txt/13-outline.md + ISO-8601 approved_at; update golden gate-receipts.json |
| R-T7 | MED | (=F05/C4) GATE-433 declared-not-enforced; gates_order puts it first though its stages sit at P4 | enforce in check_outline (mode==4x3x3) + reorder gates_order |
| R-T8 | MED | degraded:search/image prose-only — zero code reads/writes/validates degraded | receipts-based degraded mechanism: absent IMAGE/RESEARCHER artifact requires run/checkpoints/degraded-receipts.json entry, else fail |
| R-T9 | MED | (=R-P17) batch sequencing post-hoc | docs softened (code temporal-proof deferred, noted) |
| R-T11 | HIGH | nothing appends RUN-LEDGER per model call; provenance self-reported vs ":428-429 each stage's resolved id" promise | check_qc cross-checks manifest stages w/ on-disk artifacts against ledger entries (validated against golden ledger first) |
| R-T12 | MED | no chat→intake.json validator (Q0 conversational layer unscripted) | document honestly; file-level validation remains prove_bw_intake.py |

### From rev-crossskill (wiring)

| ID | Sev | Finding | Fix |
|---|---|---|---|
| R-C1 | HIGH | Skill 51 handoff FALSE — 433_Deck_Data appears nowhere in 51; 51's AF-INTAKE-BATCH rejects exactly that shape; schema misaligned | downgrade claim to "schema-valid deck payload FOR Skill 51; no automated import" in SKILL.md:145, MASTERDOC.md, INSTRUCTIONS.md, WIRING-SPEC.md:44, CHANGELOG.md, install.sh:7565-7566, SOP-BOOK-01:23 |
| R-C2 | HIGH | Skills 49/50 manuscript handoff doc-only | same downgrade (manual input) |
| R-C3 | MED | 4-way version drift 1.2.0/1.2.2/1.2.2/v1.1.6; bw_intake_accept reads only skill-version.txt | align all at release bump (1.3.0) + verify.sh assertion manifest==skill-version.txt==frontmatter |
| R-C4 | MED | gates_order dead data, self-contradictory order | reorder ["GATE-1-title","GATE-2-outline","GATE-433","GATE-3-approval"] + note (pairs R-T7) |
| R-C5 | MED | verify_tone_core_sync blind spots: hardcoded stage/file lists; core gains stage → silent miss; writing_rails/na_autopick declared, never baked in 53 | reverse enumeration: walk CORE prompts/*/, fail on anything absent from skill copy; rails baking FLAGGED for Trevor |
| R-C6 | MED ⚑ TREVOR CALL | tone-core-manifest forbids raw "pick a well-known person" instruction, but prompts/04-tone-style-1/user.md:12 contains exactly that; na_autopick:true declared on stages 04-07, zero consumers in 53 | BYTE-LOCKED shared IP across 52/53/54 — coordinated 3-skill re-pin needed. FLAGGED, NOT FIXED |
| R-C7 | LOW | stage 44 (deliverable producer) sits in P7-QC | move to P6-PACKAGE in manifest or annotate; assembler phase impact checked during fix |
| R-C8 | LOW ⚑ | typo "modeo" in byte-locked shared IP | bundle with R-C6 coordinated tone-core edit |

### From trace-convertflow (network surface / Convert&Flow audit)

VERDICT: local-only claim HOLDS — zero GHL/Convert&Flow/n8n automation consumes Skill 53 output
(token search across 29-ghl-convert-and-flow + 44-convert-and-flow-operator: 0 hits; control found
131 "workflow" files, instrument discriminates). GHL "book" hits are Brunson free-plus-shipping
marketing vocabulary, decoupled from Skill 53.

| ID | Sev | Finding | Fix |
|---|---|---|---|
| R-CF1 | HIGH | mc_board.py — the skill's ONLY network-IO file (urlopen :279) — absent from ENFORCE_FILES AND skipped by bypass_scan's skill_dir prefix → editable to POST anywhere with no AF-BK-HASH-PIN, no AF-BK-ENTRY-BYPASS | add scripts/mc_board.py to ENFORCE_FILES; re-mint ENGINE-PIN |
| R-CF2 | HIGH | (=R-P6/F04) bypass glob *.py only + basename _CANON exclusion trivially bypassed | folded into fix-provers item 6 |
| R-CF3 | LOW | /webhook/ pattern over-broad — mc_board's own CC webhook refs would falsely trip in run-dir copies | anchor to n8n hosts or exempt CC base URL |
| R-CF4 | MED | (=R-K1) evidence_root omitted at run_book_writer.py:890,903,916 → CC projection permanently unwired | folded into fix-engine item 9 (all three sites) |
| R-CF5 | MED | CC deep-checks claims mc_board.py "byte-for-byte identical" across skills — FALSE (53 legitimately drifts: BUG-31 CC-compat + parameterized receipt_subdir) | correct CC docstring deep-checks.ts:1446-1447 (fix-docs-board scope C) |
| R-CF6 | MED | (=R-C1/R-C2) 51/49/50 handoffs receiverless | folded into fix-docs-board A1/A2 |
| R-CF7 | LOW | README.md:238 v18.0.0 vs skill-version.txt 1.2.2 | release stamping reconciles |
| UNDET | — | live n8n workflows 4d50PNmVOyE9GJWz/KF6PCxzSzKWeOwN6 activity on main.blackceoautomations.com not checked (read-only remit) | operator follow-up if wanted |

Undetermined items noted for Trevor: whether the two source n8n factories still fire on the live
instance is NOT proven either way — outside this repo's evidence.


---

## Sound items (catalogued — do NOT re-litigate)

- Exit-code contract 0/2/3/4/5/6/7 consistent across entry + provers.
- Front-door nonce handshake correct (0600 nonce file, trap cleanup, exit 4 on mismatch).
- ENGINE-PIN hash-pin over the full enforcement set verified matching on disk.
- Gate receipts cannot be self-attested; producer→review→done board transitions owned by independent
  QC scorer ≥8.5; FAIL-SOFT board never gates runs.
- Golden sample certificate_sha idempotency holds; batch receipts carry prior-chapter sha256 maps.
- Broken-variant suite (18 variants) rejects every mutation with the expected AF code.
- Tone-core byte-lockstep across Skills 52/53/54 proven by verify_tone_core_sync.py.
- mc_board department slug hardening + reconcile sweep U100 behave per contract; CC deep-checks
  consume board_reconcile_converged fields correctly.

## Constraints binding the fix wave

- Back up before writing; state backup path; announce every write in the same message.
- Re-stamp ENGINE-PIN.sha256 after any engine/prover edit; re-stamp roles/_index.json content_sha
  after any role edit.
- Re-run verify.sh + make_broken.py to green AFTER fixes, BEFORE Sonnet QC pass.
- Scope strictly to book-writer paths + their direct consumers; untouched: presentation-dept
  uncommitted work in onboarding repo, CC fix/eintr-guard-sync-departments branch state.
