# EVIDENCE-REPAIR — RR-W4-DATA-RR024

Lane owner: Opus. RR-024 ONLY. No merge. No PR. No publish. Private packet.
Bases pinned: FLEET origin/main 3bedab785f1490139e095da2a6b525ba4ff71ef1,
ONB origin/main 15d6178890e0012c92768829f487fd454e93e03c.
Worktrees: /tmp/w4-rr024-fleet branch rr/w4-data-rr024,
/tmp/w4-rr024-onb branch rr/w4-data-rr024-onb.
Origin HEAD drift noted at freeze time (FLEET 967e03ed, ONB 5f0e82bb);
work stays on pinned bases per unit brief — NOT rebased onto drift.

## What changed

FLEET (new files only, no edits to existing code):
- rescue/service/receipt-export.mjs (333 lines): OPTIONAL retained file export
  companion. Canonical record stays the append-only operation/event store
  (ledger rr_ticket_events keyed by tenant+operation; executor
  rr_fix_receipt/rr_fix_events). Guarantees: bounded opaque ID allowlist
  (RECEIPT_ID_RE, MAX 128) or sha256 identity-hash filename; resolved
  containment under rootDir; 0700 dirs / 0600 files; unique temp O_EXCL +
  fsync file + dir; per-receipt lock-file serialization; per-record OBSERVED
  resulting state + operation ID; kind activity never moves transition count;
  detail scrubbed of credential shapes, bounded 300; retention purges ONLY
  reconciled intents; disk error becomes outstanding OWNED intent
  (owner rescue-rangers + next_action_at), never a log line.
- rescue/tests/RR-024/receipt-qc.test.mjs (162 lines, 10 tests): QC battery.

ONB (one file edited):
- 23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/rescue_cc_board.py:
  RR-024 hardening of retained drill-only legacy bridge. validate_receipt_id,
  _receipt_identity sha256 fallback, _receipt_path containment, _scrub_detail
  redaction, _stable_op_id (explicit wins, else hash of attempt core),
  _acquire_lock O_EXCL dedicated lock file, mkstemp unique temp + fsync file +
  dir, op-ID dedupe, observed-state transition split (RECEIPT_TRANSITION_KINDS
  = transition/ingest/status + observed.to required), count_transitions +
  count_successful_advances alias, list_outstanding / reconcile_outstanding /
  purge_reconciled_outstanding (reconciled-only purge), ingest success records
  observed to=backlog with operation ingest|ticket|task, patch success records
  observed to=status with operation status|ticket|status|code, 3x
  str(body)[:300] sites replaced with _scrub_detail(body).
  Retirement: SOP-RR-03 + TOOLS.md + director/ticket-clerk docs already label
  rescue_cc_board.py COMPATIBILITY-ONLY drill tooling (RR-017); live board is
  CC dashboard + RR-018/019. No executable production callers found in repo
  (only installer copy list, verify.sh harness, RR-017/RR-030 test refs,
  rescue_ledger.py comment). No live outstanding evidence to migrate (drill
  receipts only, fail-soft).

## QC battery (SPEC RR-024 cases 1-7) — FLEET receipt-export.mjs: 10/10 PASS

✔ RR-024(1): traversal IDs fail or stay inside the fixture root (70.674375ms)
✔ RR-024(2): absolute-path IDs fail or stay inside the fixture root (22.63725ms)
✔ RR-024(3): oversized IDs fail or stay inside the fixture root (13.026291ms)
✔ RR-024(4): 100 concurrent writes retain 100 distinct events (813.23425ms)
✔ RR-024(5): retries dedupe by operation ID (7.569417ms)
✔ RR-024(6): disk error becomes an outstanding owned intent with owner/due (9.791208ms)
✔ RR-024(7): activity does not increase the transition count (23.245209ms)
✔ RR-024: export files carry private permissions and fsync (8.024667ms)
✔ RR-024: response detail is redacted and bounded (9.083416ms)
✔ RR-024: transition without observed resulting state is refused (0.5135ms)
ℹ tests 10
ℹ suites 0
ℹ pass 10
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 1037.799959

## QC battery — ONB rescue_cc_board.py fixed: 22/22 PASS

ok 1-contained
  ok 1-hashed
  ok 1-validate
  ok 2-noescape
  ok 2-hashed
  ok 3-validate
  ok 3-hashed
  ok 3-huge-refused
  ok 4-100events
  ok 4-distinct
  ok 4-transitions
  ok 5-one
  ok 5b-stable-retry
  ok 6-listed
  ok 6-owner-due
  ok 6-nopurge-unreconciled
  ok 7-trans1
  ok 7-alias1
  ok 7-events3
  ok 8-0600
  ok 8-0700
  ok 8-bounded
RESULT 22 passed, 0 failed

## CONTROLS — each case FAILs on base, PASSes fixed

ONB base (origin/main bridge, /tmp worktree HEAD copy) results:
[rescue_cc_board] movement receipt write failed ([Errno 63] File name too long: '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b3/cc-board/tttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttt.json.tmp').
[rescue_cc_board] movement receipt write failed ([Errno 2] No such file or directory: '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json.tmp' -> '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json').
[rescue_cc_board] movement receipt write failed ([Errno 2] No such file or directory: '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json.tmp' -> '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json').
[rescue_cc_board] movement receipt write failed ([Errno 2] No such file or directory: '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json.tmp' -> '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json').
[rescue_cc_board] movement receipt write failed ([Errno 2] No such file or directory: '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json.tmp' -> '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json').
[rescue_cc_board] movement receipt write failed ([Errno 2] No such file or directory: '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json.tmp' -> '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json').
[rescue_cc_board] movement receipt write failed ([Errno 2] No such file or directory: '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json.tmp' -> '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json').
[rescue_cc_board] movement receipt write failed ([Errno 2] No such file or directory: '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json.tmp' -> '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json').
[rescue_cc_board] movement receipt write failed ([Errno 2] No such file or directory: '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json.tmp' -> '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json').
[rescue_cc_board] movement receipt write failed ([Errno 2] No such file or directory: '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json.tmp' -> '/Users/blackceomacmini/.claude-nine/tasks/rr024probe/rr024base/b4/cc-board/conc.json').
  base 1-traversal: FAIL-as-required
  base 2-absolute: FAIL-as-required
  base 3-oversized: UNEXPECTED-PASS
  base 4-concurrent-loss: FAIL-as-required
    retained 5/20
  base 5-no-dedupe: FAIL-as-required
  base 7-activity-counted: FAIL-as-required
    count=2
{
 "1-traversal": "FAIL-as-required",
 "2-absolute": "FAIL-as-required",
 "3-oversized": "UNEXPECTED-PASS",
 "4-concurrent-loss": "FAIL-as-required",
 "5-no-dedupe": "FAIL-as-required",
 "7-activity-counted": "FAIL-as-required"
}

- (1) traversal ../ IDs: base FAIL-as-required (writes outside cc-board/);
  fixed PASS (refused as ID, hashed inside root).
- (2) absolute-path IDs: base FAIL-as-required (writes outside root);
  fixed PASS (hashed inside root, no escape).
- (3) oversized IDs: base writes nothing — ENAMETOOLONG File name too long
  on "<300-char-id>.json.tmp" (silent fail-soft miss, no receipt at all);
  fixed PASS (129-char hashed inside root; 2048-char refused outright).
  Honest note: base does not corrupt state here, it loses the receipt.
- (4) concurrent writes: base FAIL-as-required (20 threads retained 4/20 —
  shared .json.tmp + read-modify-write loss); fixed PASS (100 threads retain
  100 distinct events + 100 transitions).
- (5) retries dedupe: base FAIL-as-required (same call twice stores 2 events,
  no op-ID key); fixed PASS (explicit op-ID replays to 1; same-call retry
  dedupes via stable derived op-ID, 5b case).
- (6) disk error: base only logs to stderr, nothing owned remains
  (no intent API on base — code read); fixed PASS (selective-ENOSPC fault on
  receipt temp persists 1 outstanding intent, owner rescue-rangers, due set,
  reconciled false, unreconciled refuses purge). Note: blanket-ENOSPC mock
  also breaks the outstanding writer itself (expected — full disk breaks all
  writers); selective fault proves the path.
- (7) activity vs transition: base FAIL-as-required (2x kind activity counts
  successful_advances=2); fixed PASS (1 transition + 2 activity = 3 events,
  transitions 1, alias 1).
FLEET base: receipt-export.mjs is a NEW file — no base behavior to fail.
Canonical-store replay control on base ledger: mint then recur same op_id
twice => second replay:true, COUNT(op_id)=1 (proves canonical dedupe predates
RR-024; export companion mirrors it). No existing FLEET file modified.

## Neighbors (fixed tree, exact counts)

FLEET 66/66 PASS (RR-006 18 + RR-004 17 + RR-014 20 + RR-021 11):
✔ RR-021: separate tenants never share counters or dedup folding (5.30575ms)
✔ RR-021: exact replay returns the same receipt including cap state (no re-billing) (5.68475ms)
ℹ tests 66
ℹ suites 0
ℹ pass 66
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 246.212333

ONB:
- RR-017 self-test: 23/23 PASS
- rescue_cc_board.py --self-test: PASS (RC 0)
- RR-030 board-selftest-failsonly: 9/9 PASS
- RR-004 receiver additive fields: 12/12 PASS
- RR-008 suite: ABSENT on base (tests/rescue/RR-008 missing) — UNDETERMINED.
  Nearest board coverage: RR-030 9/9 + self-test PASS.

## Overlap statement

- RR-019: base stays origin/main, NOT RR-019 branches (FLEET c54f9343,
  CC 93f8c34 out of scope). FLEET touched zero RR-019 files
  (rescue/service/board-sync.mjs + rescue/tests/RR-019/* absent on base and
  untouched). ONB touched only rescue_cc_board.py — no RR-019 surface.
  Overlap: NONE.
- RR-023: slices stay untouched (FLEET e404fd8a migration surface,
  ONB 034a4da QUEUED branch-only). FLEET added only
  rescue/service/receipt-export.mjs + rescue/tests/RR-024/ (new paths, no
  migration-surface edits; e404fd8a carry 6c2999f present in origin drift, NOT
  in worktree base). ONB edited only rescue_cc_board.py (no migration files).
  Overlap: NONE. No file:line overlap to document.

## UNDETERMINED

- ONB RR-008 suite exact count: tests/rescue/RR-008 absent on pinned base —
  UNDETERMINED (RR-030 9/9 + --self-test PASS as nearest board coverage).
- Live CC HTTP paths (ingest PATCH activity 200/201 branches): offline
  drill-only, no live server exercised — UNDETERMINED by design (fail-soft).
- Origin drift past pinned bases (FLEET 967e03ed, ONB 5f0e82bb) not
  re-verified against this repair — UNDETERMINED, rebase out of scope.
- FLEET export companion has no production wiring yet (opt-in module, zero
  callers) — retirement/migration of real outstanding evidence N/A until
  a caller adopts it.
