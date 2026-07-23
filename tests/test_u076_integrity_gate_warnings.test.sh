#!/bin/bash
set -euo pipefail
S="$(cd "$(dirname "$0")/.." && pwd)/scripts/qc-system-integrity.sh"
P=0;F=0
p(){ echo "  PASS: $1"; P=$((P+1)); }
f(){ echo "  FAIL: $1"; F=$((F+1)); }
echo "=== U076 Tests ==="
grep -q "v9.6.3" "$S" && p "version" || f "version"
grep -q "^NA=0" "$S" && p "NA=0" || f "NA=0"
grep -q "na_result()" "$S" && p "na_result" || f "na_result"
grep -q "symlink drift detected" "$S" && p "drift FAIL" || f "drift FAIL"
grep -q "content is stranded" "$S" && p "legacy FAIL" || f "legacy FAIL"
grep -q 'FAILURES+=("7.0' "$S" && p "7.0 FAIL" || f "7.0 FAIL"
C=0; for g in X.8 X.9 X.10 X.12 X.13 X.14; do grep -q "na_result \"$g\"" "$S" && C=$((C+1)); done
test "$C" -ge 5 && p "$C gates N/A" || f "$C gates N/A"
grep -q "NOT APPLICABLE" "$S" && p "NA section" || f "NA section"
grep -q "NARESULTS=()" "$S" && p "NARESULTS" || f "NARESULTS"
grep -q "N/A:" "$S" && p "N/A line" || f "N/A line"
grep -q "U076" "$S" && p "U076 ref" || f "U076 ref"
echo "=== $P/$((P+F)) ==="
test "$F" -eq 0
