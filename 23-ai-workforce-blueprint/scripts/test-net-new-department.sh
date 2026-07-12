#!/usr/bin/env bash
# test-net-new-department.sh — P2-05 step 2 CI guard: the interview-close net-new
# department path enforces its two hard rules in --check-only mode.
#
# WHAT IT PROVES (the tool does not exist pre-P2-05, so every case FAILS pre-fix):
#   1. A genuine new need (no canonical/known/on-disk collision) is accepted (rc0)
#      and gets a nearest-library seed + proposed roles.
#   2. RULE 1: a proposed slug that duplicates a canonical dept is REJECTED (rc2):
#        - exact canonical id            (billing-finance)
#        - a canonical VARIANT slug      (billing -> billing-finance)
#        - a universal-primary vertical  (engineering)
#        - an industry-gated pack dept   (listings)
#   3. RULE 2: a proposed slug that duplicates a dept already ON DISK is
#      REJECTED (rc3) — even when the on-disk dir uses a variant spelling.
#
# Exit 0 = all pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$SCRIPT_DIR/net-new-department.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

if [ ! -f "$TOOL" ]; then
  echo "  FAIL: net-new-department.py not found at $TOOL"
  echo "── test-net-new-department: 0 passed, 1 failed ──"
  exit 1
fi

run() { python3 "$TOOL" "$@"; }

# A departments/ dir with a couple of existing depts (one variant spelling).
TMPD="$(mktemp -d)"; trap 'rm -rf "$TMPD"' EXIT
DD="$TMPD/departments"
mkdir -p "$DD/marketing" "$DD/billing" "$DD/grant-writing"   # 'billing' is a billing-finance variant

# ── Case 1: genuine net-new (not canonical, not on disk) => rc0 ───────────────
set +e
out="$(run --name "Investor Relations" --check-only --departments-dir "$DD" 2>&1)"; rc=$?
set -e
if [ "$rc" -eq 0 ]; then ok "genuine net-new 'Investor Relations' accepted (rc0)"; else bad "expected rc0, got $rc :: $out"; fi
if echo "$out" | grep -qi "nearest library dept"; then ok "proposes a nearest library dept to seed roles"; else bad "no nearest-library seed in output"; fi

# ── Case 2: RULE 1 canonical duplicates => rc2 ───────────────────────────────
for slug in billing-finance billing engineering listings; do
  set +e
  out="$(run --slug "$slug" --check-only --departments-dir "$DD" 2>&1)"; rc=$?
  set -e
  if [ "$rc" -eq 2 ]; then ok "RULE 1: '$slug' rejected as canonical/known duplicate (rc2)"; else bad "'$slug' expected rc2, got $rc :: $out"; fi
done

# ── Case 3: RULE 2 on-disk duplicate => rc3 ──────────────────────────────────
# 'grant-writing' is on disk directly.
set +e
out="$(run --name "Grant Writing" --check-only --departments-dir "$DD" 2>&1)"; rc=$?
set -e
if [ "$rc" -eq 3 ]; then ok "RULE 2: 'grant-writing' rejected as on-disk duplicate (rc3)"; else bad "grant-writing expected rc3, got $rc :: $out"; fi

# On-disk VARIANT collision: 'billing' dir already resolves to billing-finance;
# proposing a *new* custom that resolves to an on-disk dir's key is rule 2.
# (marketing is on disk; proposing 'Marketing' hits rule 1 first — that's fine,
#  rule 1 is the stronger guard. Prove a pure custom-vs-disk collision instead:)
mkdir -p "$DD/investor-lounge"
set +e
out="$(run --slug "investor_lounge" --check-only --departments-dir "$DD" 2>&1)"; rc=$?
set -e
if [ "$rc" -eq 3 ]; then ok "RULE 2: custom 'investor_lounge' collides with on-disk 'investor-lounge' (rc3)"; else bad "investor_lounge expected rc3, got $rc :: $out"; fi

# ── Case 4: --check-only NEVER creates anything (read-only) ───────────────────
before="$(ls "$DD")"
run --name "Brand New Thing" --check-only --departments-dir "$DD" >/dev/null 2>&1 || true
after="$(ls "$DD")"
if [ "$before" = "$after" ]; then ok "--check-only made no filesystem change"; else bad "--check-only mutated departments/"; fi

# ── Case 5: creation-mode orchestration — RULE 3 (must pass the parity guard) ──
# Stub add-department.sh + guard so the orchestration is tested offline: success
# is reported ONLY when BOTH the create AND the runtime-parity guard pass.
STUBDIR="$TMPD/stubs"; mkdir -p "$STUBDIR"
mk_add()   { printf '#!/usr/bin/env bash\necho "stub add-department $*"\nexit %s\n' "$1" > "$STUBDIR/add.sh"; chmod +x "$STUBDIR/add.sh"; }
mk_guard() { printf '#!/usr/bin/env python3\nimport sys\nprint("stub guard")\nsys.exit(%s)\n' "$1" > "$STUBDIR/guard.py"; chmod +x "$STUBDIR/guard.py"; }

# 5a: add ok + guard ok => rc0 CREATED
mk_add 0; mk_guard 0
set +e
out="$(run --name "Investor Relations" --departments-dir "$DD" \
  --add-department-script "$STUBDIR/add.sh" --guard-script "$STUBDIR/guard.py" 2>&1)"; rc=$?
set -e
if [ "$rc" -eq 0 ] && echo "$out" | grep -qi "CREATED"; then ok "create: add-ok + guard-ok => success (rc0)"; else bad "expected rc0 CREATED, got $rc :: $out"; fi

# 5b: add ok + guard FAIL => rc4 (no runtime behind the board row)
mk_add 0; mk_guard 1
set +e
out="$(run --name "Investor Relations" --departments-dir "$DD" \
  --add-department-script "$STUBDIR/add.sh" --guard-script "$STUBDIR/guard.py" 2>&1)"; rc=$?
set -e
if [ "$rc" -eq 4 ]; then ok "create: guard FAIL blocks success (rc4) — no no_specialist_runtime slips through"; else bad "expected rc4 on guard fail, got $rc :: $out"; fi

# 5c: add-department FAIL => rc4, guard never masks it
mk_add 1; mk_guard 0
set +e
out="$(run --name "Investor Relations" --departments-dir "$DD" \
  --add-department-script "$STUBDIR/add.sh" --guard-script "$STUBDIR/guard.py" 2>&1)"; rc=$?
set -e
if [ "$rc" -eq 4 ]; then ok "create: add-department FAIL => rc4"; else bad "expected rc4 on add fail, got $rc :: $out"; fi

# 5d: a canonical-duplicate is rejected BEFORE any create is attempted
mk_add 0; mk_guard 0
set +e
out="$(run --slug "engineering" --departments-dir "$DD" \
  --add-department-script "$STUBDIR/add.sh" --guard-script "$STUBDIR/guard.py" 2>&1)"; rc=$?
set -e
if [ "$rc" -eq 2 ] && ! echo "$out" | grep -q "stub add-department"; then ok "create: canonical dup rejected pre-create (rc2, add never called)"; else bad "engineering should be rejected pre-create, got $rc :: $out"; fi

# ── Case 6: slug length sanity cap (P2-05 QC regression) ─────────────────────
# BUG (pre-fix): an arbitrarily long slug (5000 chars) returned rc0 net-new in
# --check-only and could be passed to add-department.sh as a filesystem-hostile
# directory name. FIX: a slug over MAX_SLUG_LEN (64) is rejected as bad usage.
LONG5000="$(python3 -c 'print("a"*5000)')"
set +e
out="$(run --slug "$LONG5000" --check-only --departments-dir "$DD" 2>&1)"; rc=$?
set -e
if [ "$rc" -eq 5 ]; then ok "slug cap: 5000-char slug rejected (rc5), never accepted as net-new"; else bad "5000-char slug expected rc5, got $rc :: $(echo "$out" | head -c 120)"; fi

# Boundary: 64 chars (at the cap) still passes; 65 chars is over → rc5.
S64="$(python3 -c 'print("a"*64)')"
set +e; run --slug "$S64" --check-only --departments-dir "$DD" >/dev/null 2>&1; rc=$?; set -e
if [ "$rc" -eq 0 ]; then ok "slug cap: 64-char slug (at cap) accepted (rc0)"; else bad "64-char slug expected rc0, got $rc"; fi
S65="$(python3 -c 'print("a"*65)')"
set +e; run --slug "$S65" --check-only --departments-dir "$DD" >/dev/null 2>&1; rc=$?; set -e
if [ "$rc" -eq 5 ]; then ok "slug cap: 65-char slug (over cap) rejected (rc5)"; else bad "65-char slug expected rc5, got $rc"; fi

echo ""
echo "── test-net-new-department: $PASS passed, $FAIL failed ──"
[ "$FAIL" -eq 0 ] || exit 1
