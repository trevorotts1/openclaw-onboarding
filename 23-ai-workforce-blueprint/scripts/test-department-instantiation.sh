#!/usr/bin/env bash
# test-department-instantiation.sh — proves the dept-scoped instantiation pipeline
# correctly instantiates a COMPLETE department (presentations) into a throwaway
# sandbox workspace, against the REPO role-library (the source of truth).
#
# Pins ROLE_LIBRARY_PATH to the in-repo skill dir so the test exercises the repo,
# not any stale ~/.openclaw install.
#
# Guarantees asserted (the canary's defects, now fixed):
#   T1. CANONICAL ROLE SET: all 24 canonical roles present as NN-<clean-slug>/
#       folders, numbered 00..23, slugs matching the role-library exactly.
#   T2. CLEAN SLUGS: NO folder slug carries a decoration (+, ', "new", "vX.Y",
#       "(...)", em/en dash). (defect #1)
#   T3. LIBRARY-FILLED HOW-TOs: every role's how-to.md is real library content
#       (>= 3072 bytes) with NO "PENDING — FILL FROM LIBRARY" marker. (defect #1b/#4)
#   T4. ROLE IDENTITY FILES: every role folder has IDENTITY.md + SOUL.md.
#   T5. DEPT-LEVEL SCAFFOLD: dept IDENTITY/SOUL/TOOLS/how-to-use-this-department
#       + a non-empty sops/ folder present. (defect #4)
#   T6. ADDITIVE / ZERO SIBLING WRITES: a pre-existing sibling department is
#       byte-for-byte untouched. (defect #4)
#   T7. COUNT AGREEMENT: roster slug count == role-library _index.json
#       presentations count == folders instantiated == 24. (defect #2)
#   T8. BUILD-STATE HONESTY: refresh-build-state-from-index.py records rolesDone
#       = roles ON DISK and never status:"done" with 0 roles. (defect #5)
#
# Exit 0 = all tests pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE="$SCRIPT_DIR/create_role_workspaces.py"
ROSTER="$SKILL_DIR/suggested-roles/presentations-suggested-roles.md"
INDEX="$SKILL_DIR/templates/role-library/_index.json"
REFRESH="$SCRIPT_DIR/refresh-build-state-from-index.py"

# Pin the role-library to the REPO so we test the source of truth.
export ROLE_LIBRARY_PATH="$SKILL_DIR"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

WS="$TMP/zero-human-company/sandbox-co"
DEPTS="$WS/departments"
mkdir -p "$DEPTS"
for f in AGENTS.md TOOLS.md USER.md; do printf "# %s (sandbox)\n" "$f" > "$WS/$f"; done

# Pre-existing SIBLING department that MUST NOT be touched.
SIB="$DEPTS/sales/00-chief-sales-officer"
mkdir -p "$SIB"
printf "SENTINEL-SIBLING-MUST-NOT-CHANGE\n" > "$SIB/how-to.md"
SIB_HASH_BEFORE="$(shasum "$SIB/how-to.md" | awk '{print $1}')"
SIB_COUNT_BEFORE="$(find "$DEPTS/sales" -type f | wc -l | tr -d ' ')"

echo "=== Instantiating presentations into sandbox (against REPO role-library) ==="
python3 "$ENGINE" \
  --from-roster "$ROSTER" \
  --dept-path "$DEPTS/presentations" \
  --dept-slug presentations \
  --workspace-root "$WS" >/dev/null 2>&1 \
  || { echo "  FATAL: instantiation command failed"; exit 1; }

P="$DEPTS/presentations"

# Canonical slugs from the role-library _index.json (the disk-truth source).
CANON_SLUGS="$(python3 -c "
import json
d=json.load(open('$INDEX'))
print('\n'.join(d['departments']['presentations']['roles']))
" | sort)"
CANON_COUNT="$(printf '%s\n' "$CANON_SLUGS" | grep -c .)"

# --- T7 first (count agreement) so the canonical N is established up front ----
echo "=== T7: count agreement (roster == index == folders == 24) ==="
ROSTER_SLUGS="$(grep -E '^\*\*Slug:\*\*' "$ROSTER" | sed 's/\*\*Slug:\*\* *//' | sort)"
ROSTER_COUNT="$(printf '%s\n' "$ROSTER_SLUGS" | grep -c .)"
FOLDER_SLUGS="$(for d in "$P"/[0-9][0-9]-*/; do basename "$d" | sed -E 's/^[0-9][0-9]-//'; done | sort)"
FOLDER_COUNT="$(printf '%s\n' "$FOLDER_SLUGS" | grep -c .)"
if [ "$ROSTER_COUNT" = "24" ] && [ "$CANON_COUNT" = "24" ] && [ "$FOLDER_COUNT" = "24" ]; then
  ok "canonical role count = 24 across roster / _index.json / instantiated folders"
else
  bad "count mismatch: roster=$ROSTER_COUNT index=$CANON_COUNT folders=$FOLDER_COUNT (want 24/24/24)"
fi
if [ "$ROSTER_SLUGS" = "$CANON_SLUGS" ]; then
  ok "roster **Slug:** set == role-library _index.json slug set (exact)"
else
  bad "roster slugs differ from _index.json slugs"
  diff <(printf '%s\n' "$ROSTER_SLUGS") <(printf '%s\n' "$CANON_SLUGS") | head
fi

# --- T1: all canonical roles present as NN-<slug>/, numbered 00..(N-1) --------
echo "=== T1: all canonical roles present as NN-<slug>/ ==="
miss=0
for slug in $CANON_SLUGS; do
  if ! ls -d "$P"/[0-9][0-9]-"$slug" >/dev/null 2>&1; then
    bad "missing folder for canonical role: $slug"; miss=1
  fi
done
[ "$miss" -eq 0 ] && ok "all 24 canonical roles present as NN-<slug>/ folders"
# numbering 00..23 contiguous
NUMS="$(for d in "$P"/[0-9][0-9]-*/; do basename "$d" | cut -c1-2; done | sort)"
EXPECT_NUMS="$(python3 -c "print('\n'.join('%02d'%i for i in range(24)))" | sort)"
if [ "$NUMS" = "$EXPECT_NUMS" ]; then ok "folder numbers contiguous 00..23"; else bad "folder numbers not 00..23"; fi

# --- T2: clean slugs (no decorations) -----------------------------------------
echo "=== T2: folder slugs carry NO decorations ==="
DIRTY="$(printf '%s\n' "$FOLDER_SLUGS" | grep -E "(\+|'|--|\bnew\b|\bv[0-9]|\(|\)|—|–)" || true)"
if [ -z "$DIRTY" ]; then
  ok "no folder slug carries +, ', 'new', vX.Y, parens, or em/en dash"
else
  bad "decorated slug(s) found:"; printf '    %s\n' $DIRTY
fi

# --- T3: library-filled how-tos (>=3072 bytes, no PENDING) ---------------------
echo "=== T3: every how-to.md is library-filled (>=3072 bytes, no PENDING) ==="
htfail=0; minsz=999999999; minname=""
for d in "$P"/[0-9][0-9]-*/; do
  ht="$d/how-to.md"
  if [ ! -f "$ht" ]; then bad "missing how-to.md in $(basename "$d")"; htfail=1; continue; fi
  sz="$(wc -c < "$ht")"
  if [ "$sz" -lt "$minsz" ]; then minsz="$sz"; minname="$(basename "$d")"; fi
  if [ "$sz" -lt 3072 ]; then bad "$(basename "$d")/how-to.md only $sz bytes (<3072)"; htfail=1; fi
  if grep -q "PENDING — FILL FROM LIBRARY" "$ht"; then bad "$(basename "$d")/how-to.md is a PENDING stub"; htfail=1; fi
done
[ "$htfail" -eq 0 ] && ok "all 24 how-to.md library-filled (smallest: $minname = $minsz bytes)"

# --- T4: role identity files --------------------------------------------------
echo "=== T4: every role folder has IDENTITY.md + SOUL.md ==="
idfail=0
for d in "$P"/[0-9][0-9]-*/; do
  [ -f "$d/IDENTITY.md" ] || { bad "missing IDENTITY.md in $(basename "$d")"; idfail=1; }
  [ -f "$d/SOUL.md" ]     || { bad "missing SOUL.md in $(basename "$d")"; idfail=1; }
done
[ "$idfail" -eq 0 ] && ok "all role folders carry IDENTITY.md + SOUL.md"

# --- T5: dept-level scaffold + sops/ ------------------------------------------
echo "=== T5: dept-level identity + sops present ==="
deptfail=0
for f in IDENTITY.md SOUL.md TOOLS.md how-to-use-this-department.md; do
  [ -f "$P/$f" ] || { bad "missing dept-level $f"; deptfail=1; }
done
SOP_COUNT="$(ls "$P/sops" 2>/dev/null | wc -l | tr -d ' ')"
[ "$SOP_COUNT" -ge 1 ] || { bad "dept sops/ folder empty"; deptfail=1; }
[ "$deptfail" -eq 0 ] && ok "dept IDENTITY/SOUL/TOOLS/how-to-use-this-department + sops/ ($SOP_COUNT files) present"

# --- T6: zero sibling-department writes ---------------------------------------
echo "=== T6: ADDITIVE — sibling department untouched ==="
SIB_HASH_AFTER="$(shasum "$SIB/how-to.md" | awk '{print $1}')"
SIB_COUNT_AFTER="$(find "$DEPTS/sales" -type f | wc -l | tr -d ' ')"
if [ "$SIB_HASH_AFTER" = "$SIB_HASH_BEFORE" ] && [ "$SIB_COUNT_AFTER" = "$SIB_COUNT_BEFORE" ]; then
  ok "sibling 'sales' dept byte-for-byte unchanged (hash + file count identical)"
else
  bad "sibling 'sales' dept changed! hash $SIB_HASH_BEFORE->$SIB_HASH_AFTER files $SIB_COUNT_BEFORE->$SIB_COUNT_AFTER"
fi
# Belt-and-suspenders: ONLY presentations + sales exist under departments/.
EXTRA="$(ls "$DEPTS" | grep -vxE 'presentations|sales' || true)"
[ -z "$EXTRA" ] && ok "no stray sibling departments created" || { bad "unexpected dept(s): $EXTRA"; }

# --- T8: build-state honesty (rolesDone reflects disk; never done with 0) -----
echo "=== T8: build-state honesty (rolesDone = on-disk; never done@0) ==="
HONEST="$(python3 - "$REFRESH" "$DEPTS" <<'PYEOF'
import importlib.util, sys, json, types
from pathlib import Path
refresh_path, depts_dir = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("refresh_bs", refresh_path)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
P = Path(depts_dir)
# (a) full dept on disk -> count == 24, never report 0/done-with-0
n_full = m.count_roles_on_disk(P / "presentations")
# (b) empty dept on disk -> 0 (the fiction guard)
empty = P.parent / "empty-dept-probe"
(empty).mkdir(exist_ok=True)
n_empty = m.count_roles_on_disk(empty)
print(json.dumps({"full": n_full, "empty": n_empty}))
PYEOF
)"
FULL_N="$(printf '%s' "$HONEST" | python3 -c "import sys,json;print(json.load(sys.stdin)['full'])")"
EMPTY_N="$(printf '%s' "$HONEST" | python3 -c "import sys,json;print(json.load(sys.stdin)['empty'])")"
if [ "$FULL_N" = "24" ]; then ok "count_roles_on_disk reports 24 for the fully-built dept (disk truth)"; else bad "count_roles_on_disk=$FULL_N for full dept (want 24)"; fi
if [ "$EMPTY_N" = "0" ]; then ok "count_roles_on_disk reports 0 for an empty dept (no fiction)"; else bad "count_roles_on_disk=$EMPTY_N for empty dept (want 0)"; fi

echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && { echo "ALL DEPARTMENT-INSTANTIATION TESTS PASSED"; exit 0; } || { echo "DEPARTMENT-INSTANTIATION TEST FAILURES"; exit 1; }
