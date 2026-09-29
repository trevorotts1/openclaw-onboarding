#!/usr/bin/env bash
# tests/unit/mc-route-heredoc-sync.test.sh
#
# JGT103 QC follow-up: a fleet roll runs update-skills.sh, which copies the repo's
# scripts/mc-route.sh onto every box, and THEN runs apply-fleet-standards.sh (and,
# on some paths, apply-routing-fix.sh), each of which re-writes
# "$OC_ROOT/scripts/mc-route.sh" from its OWN embedded `<<'MC_ROUTE_SH'` heredoc —
# clobbering the just-copied file. If that heredoc is stale, the roll ships the
# new CEO_EXECUTION_POLICY_V3 bullet (which tells the CEO to call
# `mc-route.sh auto`) alongside an OLD mc-route.sh that has no `auto` mode at all,
# so every owner message — including plain questions — becomes a card and raises
# a false ESCALATE_TO_OPERATOR.
#
# This test asserts BOTH stamper heredocs stay byte-identical to the shipped
# scripts/mc-route.sh, so that can never happen again.
#
# FAIL-FIRST: on the pre-fix branch head the two heredocs still hold the old
# (pre-auto-mode) helper while scripts/mc-route.sh has the new one, so both
# comparisons fail. After the fix they are byte-identical.

set -uo pipefail

PASS=0
FAIL=0
ERRORS=()

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MC_ROUTE="$REPO_ROOT/scripts/mc-route.sh"
FLEET_STANDARDS="$REPO_ROOT/scripts/apply-fleet-standards.sh"
ROUTING_FIX="$REPO_ROOT/scripts/apply-routing-fix.sh"

echo ""
echo "=== mc-route.sh stamper heredoc sync guard (JGT103 QC follow-up) ==="
echo ""

for f in "$MC_ROUTE" "$FLEET_STANDARDS" "$ROUTING_FIX"; do
  if [ ! -f "$f" ]; then
    echo "  FAIL: $f not found"
    exit 1
  fi
done

extract_heredoc() {
  # $1 = file to scan. Prints the exact body between <<'MC_ROUTE_SH' and the
  # closing MC_ROUTE_SH marker line, or exits nonzero if not found.
  python3 - "$1" <<'XT'
import re, sys
path = sys.argv[1]
text = open(path).read()
m = re.search(r"cat > \"\$MC_ROUTE_HELPER_PATH\" <<'MC_ROUTE_SH'\n(.*?\n)MC_ROUTE_SH\n", text, re.S)
if not m:
    sys.exit(1)
sys.stdout.write(m.group(1))
XT
}

WORK="$(mktemp -d "${TMPDIR:-/tmp}/mc-route-heredoc-sync.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

if ! extract_heredoc "$FLEET_STANDARDS" > "$WORK/fleet-standards.sh"; then
  fail "could not find MC_ROUTE_SH heredoc in apply-fleet-standards.sh"
else
  ok "found MC_ROUTE_SH heredoc in apply-fleet-standards.sh"
fi

if ! extract_heredoc "$ROUTING_FIX" > "$WORK/routing-fix.sh"; then
  fail "could not find MC_ROUTE_SH heredoc in apply-routing-fix.sh"
else
  ok "found MC_ROUTE_SH heredoc in apply-routing-fix.sh"
fi

echo "--- apply-fleet-standards.sh heredoc vs scripts/mc-route.sh ---"
if cmp -s "$WORK/fleet-standards.sh" "$MC_ROUTE"; then
  ok "apply-fleet-standards.sh MC_ROUTE_SH heredoc is byte-identical to scripts/mc-route.sh"
else
  fail "apply-fleet-standards.sh MC_ROUTE_SH heredoc DRIFTED from scripts/mc-route.sh: $(diff "$WORK/fleet-standards.sh" "$MC_ROUTE" | head -5)"
fi

echo "--- apply-routing-fix.sh heredoc vs scripts/mc-route.sh ---"
if cmp -s "$WORK/routing-fix.sh" "$MC_ROUTE"; then
  ok "apply-routing-fix.sh MC_ROUTE_SH heredoc is byte-identical to scripts/mc-route.sh"
else
  fail "apply-routing-fix.sh MC_ROUTE_SH heredoc DRIFTED from scripts/mc-route.sh: $(diff "$WORK/routing-fix.sh" "$MC_ROUTE" | head -5)"
fi

echo "--- both stamper heredocs agree with each other (twin sync) ---"
if cmp -s "$WORK/fleet-standards.sh" "$WORK/routing-fix.sh"; then
  ok "twin stamper heredocs stay in sync"
else
  fail "twin stamper heredocs drift from each other"
fi

echo ""
echo "=== $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Failures:"
  for e in "${ERRORS[@]}"; do echo "  - $e"; done
  exit 1
fi
exit 0
