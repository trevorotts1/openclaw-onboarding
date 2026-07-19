# U87 / GK-25 — independent judge re-verification pass, 2026-07-19

**Status of this pass: independent re-execution of GK-25's full receipt
battery against the tracked fixture at `main` head, run by an agent that did
NOT write any part of the `fix/gk25-u87-golden-quest-real-run` fixture
repair (PR #599, merged 2026-07-17) or its evidence README. This pass adds
its own fresh receipts; it does not edit or replace the original writer
evidence at `ledgers/evidence/U87-GK-25/README.md` and `01`–`08`, which
stays intact as the historical record of that fix.**

## Why this pass exists

The unit's kanban row (`ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md`,
U87) was still marked `in-progress` as of this pass's start, with its own
text stating: *"this row must not read `verified` until a fresh judge (!=
writer) re-grades >= 8.5 AND blocker 5 is resolved."* Two things had already
happened by the time this pass started, both independently confirmed here,
not merely trusted:

1. **Blocker 5 (prompt-floor) was resolved by an explicit operator ruling**
   recorded 2026-07-16 in `ledgers/ratified-decisions-2026-07-16.md`
   ("GK-25 (U87) — prompt-floor receipt DESCOPED for the `golden-quest`
   fixture") — confirmed present, complete, and unweakened at current `main`
   head by direct read of that file in this pass's own clone.
2. **A fresh judge (!= writer) round already ran and scored 9.4** (bar 8.5,
   verdict LAND) on 2026-07-16, recorded at the operator's local
   `~/skill6-merge-queue/ONB/U87.json` judge-ticket store (outside this git
   repo — this queue's standing per-unit judge-ticket convention, the same
   one the U76 row cites by that same path pattern). That judge independently
   re-ran every applicable prover, constructed its own fresh HMAC-tamper
   test, and re-derived the arc allocation from scratch, all against PR
   #599's head SHA `07f8aa90cda7638276e86f033c83e8632b0638a9`, which is
   confirmed (`git merge-base --is-ancestor`) to be an ancestor of the
   current `main` tip used by this pass. PR #599 merged 2026-07-17
   (`gh pr view 599 --json state,mergedAt` → `MERGED`, `2026-07-17T06:03:58Z`),
   and `git log --oneline -- 51-signature-presentation/examples/golden-quest`
   confirms no commit has touched the fixture path since — the fixture this
   pass re-verifies is byte-identical to what that judge scored 9.4.

What remained, per that judge ticket's own `owedLegs`, was purely mechanical:
flip the ledger row to `verified`. This pass does that — but does not do it
on the strength of citation alone. Per this unit's own honesty standard (and
this queue's "verify LIVE, not documents" discipline), every prover in the
recipe was re-run fresh, from a clean clone, against the real committed
fixture, before this pass would write `verified` anywhere.

## What this pass independently re-verified (all fresh, all this pass's own execution)

All receipts below were captured in one continuous, uninterrupted session
(strictly ascending microsecond UTC timestamps, see each `.timestamp`
sibling) against a fresh `git clone` of `main` at commit `88b62711`, in
phase order. The tracked fixture at
`51-signature-presentation/examples/golden-quest/` was hashed (sha256,
`fixture-sha256-BEFORE.txt`) before any prover ran and re-hashed after
(`fixture-sha256-AFTER.txt`): **byte-identical, zero files changed** —
`git status --short` in the tracked clone is empty. Every prover run below
against the tracked path is read-only.

| # | Phase | Receipt(s) | Result |
|---|---|---|---|
| 1 | P-SP-CLAIM (routing, ahead of intake) | `01-routing.*` | **PASS** (exit 0) |
| 2 | P-SP-INTAKE, `--as-of` today (2026-07-19) | `02-sp-intake-today.*` | **PASS** (exit 0) |
| 2 | P-SP-INTAKE, `--as-of` the grace-window boundary (2026-08-15) | `02-sp-intake-grace-boundary.*` | **PASS** (exit 0) |
| 2 | P-SP-INTAKE, `--as-of` three weeks past the grace window (2026-09-01) | `02-sp-intake-post-grace-2026-09-01.*` | **PASS** (exit 0) — earned on the record's own merits, not the dated exemption |
| 2b | HMAC tamper test — freshly constructed this pass (flipped the last hex character of `turn_ledger_provenance.signature` on a scratch copy, never the tracked file) | `02b-hmac-tamper-test.*` | **FAILS CLOSED**, `AF-SP-INTAKE-UNPACED`, exit 2 — proves the signature check is live, not vacuous |
| 3 | P-SP-STRUCTURE, real deck (`sp_structure.json`) | `03-structure.*` | **PASS** (exit 0) |
| 3 (phase-order-with-teeth) | P-SP-STRUCTURE, `broken-variants/sp_structure_D_phase_reordered.json` | `03b-structure-phase-order-broken-D.*` | **FAILS CLOSED**, `AF-SP-PHASE-ORDER` (+ incidental `AF-SP-PHASE-RANGE`), exit 2 — byte-identical to the original writer's archived `07-failfirst-phase-order-variant-D.out` and to `broken-variants/REJECTION-RESULTS.json`'s `D_phase_reordered` entry |
| 3 (supplementary) | P-SP-STRUCTURE, `broken-variants/sp_structure_A_99_slides.json` | `03c-structure-broken-A-slidefloor.*` | **FAILS CLOSED**, `AF-SP-SLIDE-FLOOR` + `AF-SP-PHASE-RANGE`, exit 2 — byte-identical to `REJECTION-RESULTS.json`'s `A_99_slides` entry |
| 3 (supplementary) | P-SP-STRUCTURE, `broken-variants/sp_structure_B_three_case_studies.json` | `03d-structure-broken-B-casestudy.*` | **FAILS CLOSED**, `AF-SP-CASESTUDY-CAP`, exit 2 — byte-identical to `REJECTION-RESULTS.json`'s `B_three_case_studies` entry |
| 3 (arc preflight) | `_chk_arc` direct import from `build_deck.py` against `working/copy/arc_allocation.json` | `04-arc-chk.*` | **PASS** (returns `''`) |
| 3 (arc, independent re-derivation) | Freshly written this pass (not reused from any prior pass): recomputes all 103 slots' `phase`/`arc_section`/`label_slide`/`hook`/`case_study` directly from `sp_structure.json`'s raw fields and diffs against the committed `arc_allocation.json` | `04b-arc-independent-rederivation.*` | **PASS** — zero mismatches across all 103 slides, including the `SECTION-HOOK`-vs-`HOOK`/`CENTRAL-HOOK` nuance (slides 5, 12, 25, 61 all correctly show `hook: false`) |
| 4 | P-SP-P3-HYGIENE, real deck (no-pitch) | `05-no-pitch.*` | **PASS** (exit 0) |
| 4 (supplementary) | P-SP-P3-HYGIENE, `broken-variants/C_pitch_in_teaching/` | `05b-no-pitch-broken-C.*` | **FAILS CLOSED**, `AF-SP-PITCH-IN-TEACH` + `AF-SP-PRICE-IN-TEACH` + `AF-SP-CTA-IN-TEACH`, exit 2 — byte-identical to `REJECTION-RESULTS.json`'s `C_pitch_in_teaching` entry |
| 5 (descoped, re-confirmed not fabricated) | prompt-floor, real deck | `06-prompt-floor-descoped-confirm.*` | **STILL FAILS CLOSED**, exit 3, `working/prompts is not a directory` — confirms the 2026-07-16 descope ruling remains honest: the gap is still genuinely there, nothing was fabricated to hide it |
| supplementary | Certificate issuance — **isolated scratch copy only**, never the tracked path (see isolation proof below) | `07-isolated-cert-issuance.*` | **PASS** (exit 0), certificate written |
| supplementary | E2E fail-first — **isolated scratch copy only**: real fixture overlaid with the broken `E2E_broken_no_cert` checkpoints (missing the P-SP-STRUCTURE attestation) | `07b-e2e-process-integrity-broken.*` | **FAILS CLOSED**, `AF-PROCESS-INTEGRITY`, exit 9, no certificate written — byte-identical to `REJECTION-RESULTS.json`'s `E2E_no_certificate` entry |

Timestamps run `2026-07-19T06:05:43.605528Z` → `2026-07-19T06:06:31.785971Z`,
strictly ascending, one continuous session, no gaps, in phase order
(1 → 2 → 2b → 3 → 3-phase-order → 4 → 5 → certificate → E2E).

## Write-isolation proof (`prove-deck.py`)

`prove-deck.py` mutates `delivery/golden-quest-FINAL/PROCESS-CERTIFICATE.{json,md}`
on every run (re-stamps `certified_at`/`certificate_sha`). Both write-capable
runs this pass (`07-isolated-cert-issuance`, `07b-e2e-process-integrity-broken`)
ran ONLY against throwaway copies of the fixture in a scratch directory
outside this repo, never against this tracked clone. Blast radius for the
successful certificate run was measured by sha256-hashing every file in the
isolated copy before (`07-isolated-cert-sha256-BEFORE.txt`) and after
(`07-isolated-cert-sha256-AFTER.txt`): exactly the two `PROCESS-CERTIFICATE.*`
files changed, nothing else. The tracked clone's `git status --short` is
confirmed empty both before and after this entire pass, and the tracked
fixture's own sha256 listing (`fixture-sha256-BEFORE.txt` /
`fixture-sha256-AFTER.txt`, 38 files) is byte-identical.

## Phase-order check has teeth — explicit confirmation

GK-25's acceptance names the phase-order check specifically (spec:2085
clause 3). This pass's `03b-structure-phase-order-broken-D` receipt proves
it fires on exactly the defect it is supposed to catch — a phase
(`teaching`) re-appearing out of its contiguous band — and does not fire on
the real, correctly-ordered 103-slide deck (`03-structure`, PASS). The two
are the same prover (`prove_sp_structure.py`) run against two inputs in the
same session, back to back, with no code change between them: the pass/fail
delta is attributable only to the phase-order defect in the input, not to
any variance in the checker itself.

## No fabrication — the honesty gate, applied

Every receipt above is the actual, unedited captured stdout/stderr/exit
code of a real subprocess run against this repo's own tracked fixture files
(read-only) or a throwaway isolated copy (write-capable gates only). No
receipt content was hand-typed or backfilled. The prompt-floor receipt
(`06-prompt-floor-descoped-confirm`) still shows a genuine, correct FAIL —
this pass did not create `working/prompts/` or synthesize prompt content to
force a PASS; the 2026-07-16 operator ruling descopes the *requirement*
for this fixture, it does not manufacture the *receipt*, and this pass's
own fresh run confirms that distinction is still honestly represented on
disk.

One process note, disclosed for completeness: the first attempt at
timestamping this battery used the shell's `date +%6N` (sub-second)
formatter, which macOS's BSD `date` does not support — it silently emitted
the literal string `6N` instead of microseconds (e.g. `...19.6NZ`), which
would have shipped fabricated-looking (and actually meaningless) precision
into evidence. This was caught before anything was written into this
directory or the repo, and the entire battery was re-run using
`datetime.now(timezone.utc)` in Python (real, verified microsecond
precision — see the monotonic sequence above) instead. Nothing in this
directory carries the broken timestamp format.

## No client/human names, no secret values

Structured scan of every file in this directory for the operator's literal
home-directory path, this pass's own scratch tmp path fragment,
and common secret-token shapes (`sk-`, `ghp_`, `xox[baprs]-`, `AIza`,
`pit-`, `AKIA`, PEM headers): zero matches. The one absolute path that
briefly appeared in an intermediate capture (the HMAC-tamper test's `source`
field, which echoed the scratch tmp file's full path) was rewritten to a
bare relative filename (`sp_intake_tampered.json`) before being copied into
this directory — verified by the same scan above, run against the final
copied files, not the intermediate ones.

## What this pass did NOT do

- Did not edit the original writer evidence (`ledgers/evidence/U87-GK-25/README.md`,
  `01`–`08`) — that record stays exactly as PR #599 left it.
- Did not edit `ledgers/ratified-decisions-2026-07-16.md` — the ruling this
  pass relies on was read, not modified.
- Did not touch the resolver, the leg-tag format on this or any other unit's
  row, or any row besides U87's own.
- Did not merge anything. This branch stays a draft PR; the serial
  merge-writer owns the actual merge.
