#!/usr/bin/env bash
# test-pointer-audit.sh - fixture battery for scripts/pointer-audit.sh.
#
# Builds throwaway workspaces (never a real box path) and proves the audit
# PASSES a clean fixture and CATCHES each defect it exists for: bloat, a broken
# pointer, an orphan playbook, a duplicate playbook, a pointer with no WHEN
# trigger, an unresolved placeholder, a missing index; plus the backup mode,
# the dry-run (writes nothing), the content-preservation proof (pass and fail)
# and the tooling-error exit code.
#
# Usage: bash tests/test-pointer-audit.sh      (exit 0 = every case passed)
# Runs under macOS bash 3.2 and Linux bash.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
AUDIT="$HERE/../scripts/pointer-audit.sh"
ROOT="$(mktemp -d 2>/dev/null || mktemp -d -t pointertest)"
trap 'rm -rf "$ROOT"' EXIT
# Guard: any default path the audit resolves lands inside the throwaway root,
# never in a real master files, backup or workspace folder on this machine.
export OPENCLAW_MASTER_FILES_DIR="$ROOT/guard-mf" OPENCLAW_BACKUP_DIR="$ROOT/guard-bk" \
       OPENCLAW_WORKSPACE="$ROOT/guard-ws" OPENCLAW_ROOT_DIR="$ROOT/guard-oc"
PASS=0 FAIL=0

ok()  { PASS=$((PASS + 1)); echo "  ok   $*"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL $*"; }

# expect <name> <want-exit> <must-contain-or-empty> -- <audit args...>
expect() {
  local name="$1" want="$2" needle="$3"; shift 4
  local out rc
  out="$(bash "$AUDIT" "$@" 2>&1)"; rc=$?
  if [ "$rc" != "$want" ]; then bad "$name (exit $rc, wanted $want)"; printf '%s\n' "$out" | sed 's/^/       | /' | head -40; return; fi
  if [ -n "$needle" ] && ! printf '%s\n' "$out" | grep -qF -- "$needle"; then
    bad "$name (exit $rc ok, but output lacks: $needle)"; printf '%s\n' "$out" | sed 's/^/       | /' | head -40; return
  fi
  ok "$name (exit $rc)"
}

# make_clean <dir>: a healthy workspace + master files folder
make_clean() {
  local d="$1"
  mkdir -p "$d/ws" "$d/mf/playbooks"
  cat > "$d/ws/AGENTS.md" <<EOF
# Agent rules

## Hard rules
- Never share credentials. Never delete files without asking.

## Playbooks
QuickBooks Online: rules and playbook live at $d/mf/playbooks/quickbooks-online.md. Read it whenever the user mentions QuickBooks, invoices, or bookkeeping.
EOF
  printf '# Memory\n\n- Core files means AGENTS.md, TOOLS.md, MEMORY.md, USER.md, IDENTITY.md, SOUL.md.\n' > "$d/ws/MEMORY.md"
  printf '# Soul\n\nWarm and direct.\n' > "$d/ws/SOUL.md"
  cat > "$d/mf/playbooks/quickbooks-online.md" <<'EOF'
# QuickBooks Online playbook
System: QuickBooks Online
Last verified: 2026-09-28
Triggers: QuickBooks, invoices, bookkeeping

## Rules (current)
- Invoices go out on the first business day of the month.

## What changed
- 2026-09-28: created from AGENTS.md.

## Moved-text archive (historical record, not instructions)
Invoices go out on the first business day of the month. Always attach the statement.
EOF
  cat > "$d/mf/playbooks/README.md" <<'EOF'
# Playbooks master index
- [QuickBooks Online](quickbooks-online.md) - invoicing and bookkeeping rules - last verified 2026-09-28
EOF
}

run_audit_args() { echo "--workspace $1/ws --master-files $1/mf"; }

echo "pointer-audit fixture battery"

# 1. clean fixture passes
C="$ROOT/clean"; make_clean "$C"
# shellcheck disable=SC2046
expect "clean fixture passes" 0 "PASS [pointer-audit.sh]" -- $(run_audit_args "$C") --dry-run

# 2. bloat: AGENTS.md above 40,000 characters
B="$ROOT/bloat"; make_clean "$B"
{ echo "## Old onboarding notes"; i=0; while [ $i -lt 700 ]; do echo "This is situational onboarding knowledge sentence number $i for the fixture."; i=$((i + 1)); done; } >> "$B/ws/AGENTS.md"
# shellcheck disable=SC2046
expect "bloat is caught" 1 "SIZE: AGENTS.md is" -- $(run_audit_args "$B") --dry-run
# shellcheck disable=SC2046
expect "bloat block is listed as a candidate" 1 "## Old onboarding notes" -- $(run_audit_args "$B") --dry-run

# 3. broken pointer
P="$ROOT/broken"; make_clean "$P"
echo "Payroll: rules live at $P/mf/playbooks/payroll.md. Read it whenever the user mentions payroll or wages." >> "$P/ws/AGENTS.md"
# shellcheck disable=SC2046
expect "broken pointer is caught" 1 "BROKEN POINTER: AGENTS.md" -- $(run_audit_args "$P") --dry-run

# 4. orphan playbook (not indexed, no pointer)
O="$ROOT/orphan"; make_clean "$O"
printf '# Stray\nSystem: Zoom Webinars\nLast verified: 2026-09-01\n\n## What changed\n- 2026-09-01: created.\n' > "$O/mf/playbooks/zoom-webinars.md"
# shellcheck disable=SC2046
expect "orphan (not indexed) is caught" 1 "ORPHAN (not indexed): zoom-webinars.md" -- $(run_audit_args "$O") --dry-run
# shellcheck disable=SC2046
expect "orphan (no pointer) is caught" 1 "ORPHAN (no pointer): no core file points to zoom-webinars.md" -- $(run_audit_args "$O") --dry-run

# 5. duplicate playbooks for one system
D="$ROOT/dup"; make_clean "$D"
sed 's/invoices go out/INVOICES GO OUT/' "$D/mf/playbooks/quickbooks-online.md" > "$D/mf/playbooks/quickbooks-rules.md"
echo "- [QuickBooks rules](quickbooks-rules.md) - duplicate" >> "$D/mf/playbooks/README.md"
echo "QuickBooks again: $D/mf/playbooks/quickbooks-rules.md. Read it when the user mentions QuickBooks." >> "$D/ws/TOOLS.md"
# shellcheck disable=SC2046
expect "duplicate playbooks are caught" 1 "DUPLICATE PLAYBOOKS (same System: line)" -- $(run_audit_args "$D") --dry-run

# 6. pointer without WHEN trigger
W="$ROOT/nowhen"; make_clean "$W"
sed -i.bak 's/ Read it whenever the user mentions QuickBooks, invoices, or bookkeeping\.//' "$W/ws/AGENTS.md"; rm -f "$W/ws/AGENTS.md.bak"
# shellcheck disable=SC2046
expect "pointer with no WHEN is caught" 1 "POINTER WITHOUT WHEN" -- $(run_audit_args "$W") --dry-run

# 7. unresolved placeholder
U="$ROOT/placeholder"; make_clean "$U"
echo "Kie notes: [MASTER_FILES_FOLDER]/apis/kie/README.md. Read it when the user mentions Kie." >> "$U/ws/MEMORY.md"
# shellcheck disable=SC2046
expect "unresolved placeholder is caught" 1 "UNRESOLVED: MEMORY.md" -- $(run_audit_args "$U") --dry-run

# 8. missing index
I="$ROOT/noindex"; make_clean "$I"; rm -f "$I/mf/playbooks/README.md"
# shellcheck disable=SC2046
expect "missing index is caught" 1 "INDEX MISSING" -- $(run_audit_args "$I") --dry-run

# 9. dry run writes nothing; a normal run writes exactly one report
R="$ROOT/report"; make_clean "$R"
# shellcheck disable=SC2046
bash "$AUDIT" $(run_audit_args "$R") --dry-run >/dev/null 2>&1
if [ -d "$R/mf/70-lean-core-file-system" ]; then bad "dry run wrote files"; else ok "dry run wrote nothing"; fi
# shellcheck disable=SC2046
expect "normal run writes a report" 0 "Report: $R/mf/70-lean-core-file-system/reports/pointer-audit-" -- $(run_audit_args "$R")
n="$(find "$R/mf/70-lean-core-file-system/reports" -name 'pointer-audit-*.md' | wc -l | tr -d ' ')"
[ "$n" = "1" ] && ok "exactly one report file" || bad "expected 1 report file, found $n"

# 10. backup mode copies core files and playbooks
K="$ROOT/backup"; make_clean "$K"
# shellcheck disable=SC2046
out="$(bash "$AUDIT" $(run_audit_args "$K") --backup-root "$K/bk" --backup 2>&1)"; rc=$?
dest="$(printf '%s\n' "$out" | tail -1)"
if [ "$rc" = "0" ] && [ -f "$dest/core/AGENTS.md" ] && [ -f "$dest/playbooks/quickbooks-online.md" ] && [ -s "$dest/MANIFEST.txt" ]; then
  ok "backup copies core files, playbooks and a manifest (exit 0)"
else bad "backup mode (exit $rc, dest=$dest)"; fi

# 11. content-preservation proof: pass when moved text is in a playbook,
#     fail when a removed paragraph exists nowhere
M="$ROOT/prove"; make_clean "$M"
cp "$M/ws/AGENTS.md" "$M/old-agents.md"
printf '\nInvoices go out on the first business day of the month. Always attach the statement.\n' >> "$M/old-agents.md"
expect "proof passes when the moved paragraph is in the archive" 0 "PASS [pointer-audit.sh]: every paragraph removed" -- \
  --master-files "$M/mf" --prove-moved "$M/old-agents.md" "$M/ws/AGENTS.md"
printf '\nThe courier account number rule was never copied anywhere.\n' >> "$M/old-agents.md"
expect "proof fails when a removed paragraph exists nowhere" 1 "UNPROVEN: The courier account number rule" -- \
  --master-files "$M/mf" --prove-moved "$M/old-agents.md" "$M/ws/AGENTS.md"

# 11b. a heading that stays behind (as the pointer's home) does not hide its
#      moved body: the body alone must be proven
H="$ROOT/heading"; make_clean "$H"
printf '# Rules\n\n## QuickBooks notes\nInvoices go out on the first business day of the month. Always attach the statement.\n' > "$H/old.md"
printf '# Rules\n\n## QuickBooks notes\nQuickBooks Online: see the playbook. Read it whenever the user mentions invoices.\n' > "$H/new.md"
expect "proof passes when only the body moved and the heading stayed" 0 "unproven=0" -- \
  --master-files "$H/mf" --prove-moved "$H/old.md" "$H/new.md"

# 12. tooling errors are exit 2, never a verdict about the box
expect "missing workspace is a tooling error" 2 "TOOLING ERROR" -- --workspace "$ROOT/does-not-exist" --master-files "$C/mf" --dry-run
expect "unknown flag is a tooling error" 2 "TOOLING ERROR" -- --no-such-flag

# 13. idempotent: two audits of an unchanged fixture give identical output
# shellcheck disable=SC2046
a1="$(bash "$AUDIT" $(run_audit_args "$O") --dry-run 2>&1 | grep -v '^Run: ')"
# shellcheck disable=SC2046
a2="$(bash "$AUDIT" $(run_audit_args "$O") --dry-run 2>&1 | grep -v '^Run: ')"
[ "$a1" = "$a2" ] && ok "re-run of an unchanged fixture is identical" || bad "re-run output differs"

echo "pointer-audit fixture battery: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
