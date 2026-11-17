#!/usr/bin/env bash
# test-stale-reset-follows-company-root.sh — BU-102 (closes WF-120):
# a finished department is reset only when its files are missing from EVERY
# place the company can live.
#
# BEFORE: the disk-reality stale audit looked in exactly one tree
# (`<workspaceRoot or state dir>/departments/<id>`) and reset a "done"
# department to "pending" whenever that one tree lacked a real how-to.md. A
# company whose departments live under `companyRoot` (or under `<id>-dept`)
# was therefore demoted on every tick and rebuilt for real — data loss.
#
# AFTER: candidate trees are `companyRoot/departments`,
# `workspaceRoot/departments` and the old fallback; each department is checked
# under `<tree>/<id>` and `<tree>/<id>-dept`; it is stale only when none holds
# a real how-to.md. With no departments folder anywhere the audit prints
# `STALE_CHECK_SKIPPED: no departments folder found; nothing reset`, logs it,
# and resets nothing.
#
# Cases (fixture mirrored from the unit):
#   C1-BEFORE (pre-change script, the C1 fixture): the entry is reset to
#       "pending" — recorded first as the unchanged-behaviour baseline.
#   C1   (real script, same fixture): the entry is still "done".
#   C2   (real script, a workspace tree and a company tree both exist and
#        neither holds the file): the entry is "pending".
#   C3   (real script, no departments folder anywhere): the entry is still
#        "done" and the log message begins STALE-CHECK: STALE_CHECK_SKIPPED.
#
# Hermetic: fresh $HOME per case holding .openclaw/workspace, a stub `openclaw`
# first on PATH that records its arguments and exits 0, no network, no live
# box. Exit 0 = pass.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESUME="$SCRIPT_DIR/resume-workforce-build.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  PASS: $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

T_HOME="$(mktemp -d -p "${TMPDIR:-$PWD}")"
FIXTURE_BIN="$(mktemp -d -p "${TMPDIR:-$PWD}")"
export STUB_LOG="$FIXTURE_BIN/calls.log"
cleanup() { rm -rf "$T_HOME" "$FIXTURE_BIN"; }
trap cleanup EXIT

if [[ ! -f "$RESUME" ]]; then
  echo "FATAL: $RESUME not found"
  exit 1
fi

# Stub CLI: records every call, never reaches a real gateway.
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" >> "$STUB_LOG"\nexit 0\n' > "$FIXTURE_BIN/openclaw"
chmod +x "$FIXTURE_BIN/openclaw"

# The pre-change script: the same directory (every sibling — the lib, the
# Python modules, the floor script — reached through symlinks) with only the
# BU-102 block reverted to the single-tree form it replaced. This is the
# C1-BEFORE baseline, and it also makes C1 non-vacuous. Fail closed: if any
# fragment is absent the baseline is not written and the suite goes red.
build_pre_change_script() {
  local dir="$1" f
  mkdir -p "$dir" || return 1
  for f in "$SCRIPT_DIR"/*; do
    [[ -e "$f" ]] || continue
    [[ "$(basename "$f")" == "resume-workforce-build.sh" ]] && continue
    ln -sfn "$f" "$dir/$(basename "$f")" || return 1
  done
  python3 - "$RESUME" "$dir/resume-workforce-build.sh" <<'PY'
import sys
source, target = sys.argv[1], sys.argv[2]
text = open(source, encoding="utf-8").read()

helpers = '''HOW_TO_MIN = 256  # bytes — anything smaller is effectively empty/stub


def _candidate_trees(state, fallback):
    seen, out = set(), []
    def add(p):
        try:
            p = Path(p)
            if str(p) not in seen and p.is_dir():
                seen.add(str(p)); out.append(p)
        except OSError:
            pass
    root = state.get("companyRoot")
    if isinstance(root, str) and os.path.isabs(root):
        add(Path(root) / "departments")
    ws = state.get("workspaceRoot")
    if isinstance(ws, str) and ws:
        add(Path(ws) / "departments")
    add(fallback)
    return out


try:
'''
helpers_old = '''HOW_TO_MIN = 256  # bytes — anything smaller is effectively empty/stub

try:
'''

skip = '''trees = _candidate_trees(state, depts_dir)
if not trees:
    print("STALE_CHECK_SKIPPED: no departments folder found; nothing reset")
    sys.exit(0)

'''

scan = '''    # Check for at least one real how-to.md under every place the company can
    # live: <tree>/<id> and <tree>/<id>-dept, for each candidate tree in turn.
    has_real_howto = False
    for tree in trees:
        for dept_dir in (tree / dept_id, tree / f"{dept_id}-dept"):
            if not dept_dir.is_dir():
                continue
            for role_dir in dept_dir.iterdir():
                if not role_dir.is_dir() or role_dir.name.startswith("."):
                    continue
                how_to = role_dir / "how-to.md"
                if how_to.exists() and how_to.stat().st_size >= HOW_TO_MIN:
                    content = how_to.read_text(encoding="utf-8", errors="replace")
                    if "[PENDING" not in content:
                        has_real_howto = True
                        break
            if has_real_howto:
                break
        if has_real_howto:
            break

    if not has_real_howto:
        reset_ids.append(dept_id)
'''
scan_old = '''    # Check for at least one real how-to.md under departments/<id>/
    dept_dir = depts_dir / dept_id
    has_real_howto = False
    if dept_dir.is_dir():
        for role_dir in dept_dir.iterdir():
            if not role_dir.is_dir() or role_dir.name.startswith("."):
                continue
            how_to = role_dir / "how-to.md"
            if how_to.exists() and how_to.stat().st_size >= HOW_TO_MIN:
                content = how_to.read_text(encoding="utf-8", errors="replace")
                if "[PENDING" not in content:
                    has_real_howto = True
                    break

    if not has_real_howto:
        reset_ids.append(dept_id)
'''

for fragment in (helpers, skip, scan):
    if fragment not in text:
        sys.stderr.write("BASELINE: BU-102 fragment not found in the script\n")
        sys.exit(1)
text = text.replace(helpers, helpers_old, 1).replace(skip, "", 1).replace(scan, scan_old, 1)
open(target, "w", encoding="utf-8").write(text)
PY
  local rc=$?
  chmod +x "$dir/resume-workforce-build.sh" 2>/dev/null || true
  return "$rc"
}

# A real how-to.md (>= 256 bytes, no placeholder marker), 400 bytes of text.
write_howto() {
  local path="$1" i=0
  mkdir -p "$(dirname "$path")" || return 1
  : > "$path"
  while (( i < 4 )); do
    printf 'Director how-to line %d: own the department plan, keep the weekly rhythm, and report outcomes to the owner without waiting to be asked. ' "$i" >> "$path"
    i=$((i + 1))
  done
  printf '\n' >> "$path"
}

# state file: companySlug, interviewComplete, interviewQc.status=pass, one
# department at "done"; companyRoot written only when given.
write_state() {
  local state="$1" company_root="$2"
  python3 - "$state" "$company_root" <<'PY'
import json, sys
state = {
    "companySlug": "acme",
    "interviewComplete": True,
    "interviewQc": {"status": "pass"},
    "departments": [{"slug": "marketing", "status": "done"}],
}
if sys.argv[2]:
    state["companyRoot"] = sys.argv[2]
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    handle.write(json.dumps(state, indent=2) + "\n")
PY
}

# Build the three fixtures under one fresh HOME.
#   case1: how-to.md only under <companyRoot>/departments/marketing/01-director
#   case2: a workspace tree and a company tree exist, neither holds the file
#   case3: no departments folder anywhere
write_fixture() {
  local home="$1" mode="$2"
  local workspace="$home/.openclaw/workspace"
  local state="$workspace/.workforce-build-state.json"
  local company_root=""
  mkdir -p "$workspace" || return 1
  case "$mode" in
    case1)
      company_root="$home/company-tree"
      write_howto "$company_root/departments/marketing/01-director/how-to.md" || return 1 ;;
    case2)
      company_root="$home/company-tree"
      mkdir -p "$company_root/departments/marketing/01-director" || return 1
      mkdir -p "$workspace/departments/marketing/01-director" || return 1 ;;
    case3)
      company_root="" ;;
    *)
      echo "FATAL: unknown fixture mode $mode" >&2
      return 1 ;;
  esac
  write_state "$state" "$company_root"
}

run_case() {
  local label="$1" script="$2" mode="$3"
  local home="$T_HOME/$label"
  local state="$home/.openclaw/workspace/.workforce-build-state.json"
  write_fixture "$home" "$mode" || { echo "FATAL: fixture setup failed for $label" >&2; exit 1; }
  HOME="$home" PATH="$FIXTURE_BIN:$PATH" WORKFORCE_BUILD_STATE_FILE="$state" \
    bash "$script" >/dev/null 2>&1
  echo "  ($label: resume exit $?)" >&2
}

dept_status() {
  python3 - "$1" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    state = json.load(handle)
departments = state.get("departments") or []
entry = departments[0] if departments else {}
print(entry.get("status", "ABSENT"))
PY
}

log_message_starts_with() {
  python3 - "$1" "$2" <<'PY'
import sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
prefix = sys.argv[2]
raise SystemExit(0 if any(line.split(" ", 1)[1].startswith(prefix)
                          for line in text.splitlines() if " " in line) else 1)
PY
}

# ─────────────────────────────────────────────────────────────────────────
echo "== C1-BEFORE: pre-change script on the C1 fixture resets the entry =="

PRE_DIR="$T_HOME/pre-change-scripts"
if ! build_pre_change_script "$PRE_DIR"; then
  echo "FATAL: could not build the pre-change script baseline"
  exit 1
fi
run_case c1-before "$PRE_DIR/resume-workforce-build.sh" case1
BEFORE_STATUS="$(dept_status "$T_HOME/c1-before/.openclaw/workspace/.workforce-build-state.json")"
if [[ "$BEFORE_STATUS" == "pending" ]]; then
  ok "C1-BEFORE: the entry was reset to 'pending' (the one-tree audit reproduced)"
else
  bad "C1-BEFORE: the entry is '$BEFORE_STATUS', expected 'pending' — the baseline did not reproduce, C1 would prove nothing"
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "== C1: real script, how-to.md only under companyRoot -> the entry stays done =="

run_case c1 "$RESUME" case1
C1_STATE="$T_HOME/c1/.openclaw/workspace/.workforce-build-state.json"
C1_STATUS="$(dept_status "$C1_STATE")"
if [[ "$C1_STATUS" == "done" ]]; then
  ok "C1: the entry is still 'done' (a finished department under companyRoot is not reset)"
else
  bad "C1: the entry is '$C1_STATUS', expected 'done'"
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "== C2: real script, both trees exist and neither holds the file -> pending =="

run_case c2 "$RESUME" case2
C2_STATE="$T_HOME/c2/.openclaw/workspace/.workforce-build-state.json"
C2_STATUS="$(dept_status "$C2_STATE")"
if [[ "$C2_STATUS" == "pending" ]]; then
  ok "C2: the entry is 'pending' — stale only when no tree has a real how-to.md"
else
  bad "C2: the entry is '$C2_STATUS', expected 'pending'"
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "== C3: real script, no departments folder anywhere -> skipped, entry stays done =="

run_case c3 "$RESUME" case3
C3_STATE="$T_HOME/c3/.openclaw/workspace/.workforce-build-state.json"
C3_STATUS="$(dept_status "$C3_STATE")"
C3_LOG="$T_HOME/c3/.openclaw/workspace/.workforce-build-state.log"
if [[ "$C3_STATUS" == "done" ]]; then
  ok "C3: the entry is still 'done' — nothing was reset"
else
  bad "C3: the entry is '$C3_STATUS', expected 'done'"
fi
if [[ -f "$C3_LOG" ]] && log_message_starts_with "$C3_LOG" "STALE-CHECK: STALE_CHECK_SKIPPED"; then
  ok "C3: the log message begins STALE-CHECK: STALE_CHECK_SKIPPED"
else
  bad "C3: the log does not record STALE-CHECK: STALE_CHECK_SKIPPED"
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "==================================================="
echo "  test-stale-reset-follows-company-root: PASS=$PASS FAIL=$FAIL"
echo "==================================================="
if (( FAIL > 0 )); then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all BU-102 company-root stale-reset checks pass"
exit 0
