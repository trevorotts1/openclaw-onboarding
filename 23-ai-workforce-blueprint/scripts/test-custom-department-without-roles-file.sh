#!/usr/bin/env bash
# test-custom-department-without-roles-file.sh — BU-66 acceptance test (WF-086).
#
# An owner-added department with no roles file of its own must be scaffolded
# (director role only), not a fatal build failure — and a platform-owned
# department still hard-fails when its roles file is missing.
#
#   C1  a non-floor, non-pack owner-added department with no map entry and no
#       <id>-suggested-roles.md returns non-fatal, lands in `scaffolded`, and
#       parse_suggested_roles() returns [] for it
#   C2  C1's department workspace holds exactly ONE role folder, that folder
#       carries how-to.md, and it is the director scaffold — no role folder
#       copied from another department's roster
#   C3  floor department `marketing` with its roles file moved away exits 78
#   C4  pack department `client-coaches` (personal-pro-dev) with its base roles
#       file moved away exits 78
#   C5  the same pack department with its base roles file present still resolves
#       to that base roster (it is platform-owned, never scaffolded)
#
# Fixture note: the build spec names `client-coaches` as the owner-added custom
# department, but `department-naming-map.json` registers it as
# vertical_packs.personal-pro-dev.auto_add_departments[1] with
# base_suggested_roles "customer-support-suggested-roles.md". It is therefore a
# PACK department, which the same spec block keeps hard-failing and roster
# backed. The pack behaviour is proved with that exact id (C4, C5); the
# owner-added behaviour is proved with an id that is genuinely not on the
# platform floor or in any pack (C1, C2).
#
# Hermetic: sandboxed $HOME, sandboxed master-files tree, scratch build-state
# and scratch departments root. Nothing outside the sandbox is read or written.
# Exit 0 = every guard passed; non-zero = at least one guard failed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BW="$SCRIPT_DIR/build-workforce.py"

PASS=0
FAIL=0
good() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL: $1" >&2; }

if [ ! -f "$BW" ]; then bad "required file missing: $BW"; echo "ABORT"; exit 1; fi
if [ ! -d "$SKILL_DIR/suggested-roles" ]; then bad "suggested-roles/ missing"; echo "ABORT"; exit 1; fi

# Every scratch byte stays in TMPDIR (the caller keeps it on the portable drive).
if [ -z "${TMPDIR:-}" ] || [ ! -d "${TMPDIR:-}" ]; then
  bad "TMPDIR is not set to an existing directory"; echo "ABORT"; exit 2
fi
TMP="$(mktemp -d "$TMPDIR/bu66-custom-dept-XXXXXX")" || { bad "mktemp failed"; exit 2; }
trap 'rm -rf "$TMP"' EXIT
SB_HOME="$TMP/home"
mkdir -p "$SB_HOME"

env -i HOME="$SB_HOME" PATH="$PATH" TMPDIR="$TMP" OPENCLAW_PLATFORM="mac-legacy" \
  PYTHONDONTWRITEBYTECODE=1 \
  python3 -I - "$SKILL_DIR" "$TMP" <<'PY'
import importlib.util, json, os, shutil, sys

SKILL, TMP = sys.argv[1:3]
BW = os.path.join(SKILL, "scripts", "build-workforce.py")
ROLES_SRC = os.path.join(SKILL, "suggested-roles")
MAP_PATH = os.path.join(SKILL, "department-naming-map.json")

PASS = [0]
FAIL = [0]

def ok(msg):
    PASS[0] += 1
    print(f"PASS: {msg}")

def bad(msg):
    FAIL[0] += 1
    print(f"FAIL: {msg}", file=sys.stderr)

def fresh_tree(name):
    """A master-files tree with its own copy of suggested-roles/."""
    master = os.path.join(TMP, name)
    dst = os.path.join(master, "23-ai-workforce-blueprint", "suggested-roles")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(ROLES_SRC, dst)
    return master, dst

# ── sandbox every path BEFORE the module is imported ────────────────────────
master0, roles0 = fresh_tree("master")
home = os.path.join(TMP, "home")
state_path = os.path.join(TMP, "state.json")
os.environ["HOME"] = home
os.environ["MASTER_FILES_DIR"] = master0
os.environ["WORKFORCE_BUILD_STATE_FILE"] = state_path
os.environ.pop("MC_COMPANY_ID", None)
os.environ.pop("ZERO_HUMAN_COMPANY_DIR", None)

sys.path.insert(0, os.path.join(SKILL, "scripts"))
spec = importlib.util.spec_from_file_location("bw", BW)
bw = importlib.util.module_from_spec(spec)
sys.modules["bw"] = bw
spec.loader.exec_module(bw)

bw.HOME = home
bw.MASTER_FILES = master0
bw.COMPANY_DISCOVERY_DIR = os.path.join(master0, "company-discovery")
bw.WORKSPACE_ROOT = os.path.join(TMP, "ws")
bw.DEPARTMENTS_DIR = os.path.join(TMP, "ws", "departments")
bw.LEGACY_DEPARTMENTS_DIR = bw.DEPARTMENTS_DIR
os.makedirs(bw.DEPARTMENTS_DIR, exist_ok=True)
bw._build_state_path = lambda: state_path

def use_tree(master):
    bw.MASTER_FILES = master
    bw.COMPANY_DISCOVERY_DIR = os.path.join(master, "company-discovery")

CUSTOM = "owner-client-coaches"

# ── C1: owner-added department with no map entry / no roles file ────────────
platform = bw._platform_department_norms()
known = (
    "CUSTOM was not classified as a platform department"
    if bw._decline_norm(CUSTOM) not in platform else
    "CUSTOM was wrongly classified as a platform department"
)
if bw._decline_norm(CUSTOM) not in platform and \
        not bw.DEPT_TO_SUGGESTED_ROLES.get(CUSTOM) and \
        not os.path.isfile(os.path.join(roles0, f"{CUSTOM}-suggested-roles.md")):
    ok(known + "; no map entry; no <id>-suggested-roles.md")
else:
    bad("fixture precondition broken: " + known)

try:
    resolved, scaffolded = bw.assert_dept_map_resolves([CUSTOM])
    ok("assert_dept_map_resolves does not exit for the owner-added department")
except SystemExit as exc:
    resolved, scaffolded = {}, []
    bad(f"assert_dept_map_resolves exited {exc.code!r} for the owner-added department")

if CUSTOM in scaffolded and CUSTOM not in resolved:
    ok("the owner-added department is recorded in the returned scaffolded list")
else:
    bad(f"scaffolded={scaffolded!r} resolved keys={sorted(resolved)!r} — expected "
        f"{CUSTOM!r} scaffolded and unresolved")

roles = bw.parse_suggested_roles(CUSTOM)
if roles == []:
    ok("parse_suggested_roles returns [] for the owner-added department")
else:
    bad(f"parse_suggested_roles returned {len(roles)} borrowed role(s) for the owner-added department")

# ── C2: one role folder, how-to.md, no borrowed roster ─────────────────────
info = {"name": "Owner Client Coaches", "emoji": "\U0001f4c1", "head": "Director of Owner Client Coaches",
        "description": "Coaching for the owner's own clients."}
answers = {"company_name": "Scratch Co", "industry": "coaching"}
dept_dir = ""
try:
    dept_dir = bw.create_department_workspace(CUSTOM, info, answers) or ""
    bw.create_role_workspace(CUSTOM, info, answers)
except Exception as exc:  # noqa: BLE001 - any exception is the failure under test
    bad(f"materialising the owner-added department raised: {exc!r}")

if not dept_dir or not os.path.isdir(dept_dir):
    dept_dir = os.path.join(bw.DEPARTMENTS_DIR, CUSTOM)

role_dirs = []
if os.path.isdir(dept_dir):
    role_dirs = sorted(
        n for n in os.listdir(dept_dir)
        if os.path.isdir(os.path.join(dept_dir, n))
        and os.path.isfile(os.path.join(dept_dir, n, "how-to.md"))
    )
if len(role_dirs) == 1:
    ok(f"department folder holds exactly one role folder with how-to.md ({role_dirs[0]})")
else:
    bad(f"expected one role folder with how-to.md, found {len(role_dirs)}: {role_dirs}")

if role_dirs and role_dirs[0].split("-", 1)[-1].startswith("director-of-owner-client-coaches"):
    ok("the single role folder is the director scaffold, not another department's roster role")
else:
    bad(f"the single role folder is not the director scaffold: {role_dirs!r}")

# ── C3: floor department with its roles file moved away ────────────────────
master_f, roles_f = fresh_tree("master-floor")
use_tree(master_f)
floor_file = bw.DEPT_TO_SUGGESTED_ROLES.get("marketing") or "marketing-suggested-roles.md"
floor_path = os.path.join(roles_f, floor_file)
if os.path.isfile(floor_path):
    os.remove(floor_path)
    try:
        bw.assert_dept_map_resolves(["marketing"])
        bad("floor department 'marketing' with no roles file did NOT exit")
    except SystemExit as exc:
        if exc.code == 78:
            ok("floor department 'marketing' with its roles file moved away exits 78")
        else:
            bad(f"floor department 'marketing' exited {exc.code!r}, expected 78")
else:
    bad(f"fixture precondition broken: {floor_file} not found in the scratch roles dir")

# ── C4/C5: pack department `client-coaches` (the spec's literal id) ────────
pack_id = "client-coaches"
pack_file = bw.DEPT_TO_SUGGESTED_ROLES.get(pack_id) or ""
pack_owner = bw._decline_norm(pack_id) in bw._platform_department_norms()
if pack_file and pack_owner:
    ok(f"'{pack_id}' is platform-owned and maps to {pack_file} (a pack department)")
else:
    bad(f"fixture precondition broken: '{pack_id}' is not a mapped pack department")

master_p, roles_p = fresh_tree("master-pack")
use_tree(master_p)
pack_path = os.path.join(roles_p, pack_file) if pack_file else ""
if pack_path and os.path.isfile(pack_path):
    try:
        resolved_p, scaffolded_p = bw.assert_dept_map_resolves([pack_id])
        if pack_id in resolved_p and pack_id not in scaffolded_p:
            ok(f"'{pack_id}' with its pack roles file present resolves to that roster")
        else:
            bad(f"'{pack_id}' with its roles file present was not resolved: "
                f"resolved={sorted(resolved_p)!r} scaffolded={scaffolded_p!r}")
    except SystemExit as exc:
        bad(f"'{pack_id}' with its roles file present exited {exc.code!r}")
    os.remove(pack_path)
    try:
        bw.assert_dept_map_resolves([pack_id])
        bad(f"pack department '{pack_id}' with no roles file did NOT exit")
    except SystemExit as exc:
        if exc.code == 78:
            ok(f"pack department '{pack_id}' with its roles file moved away exits 78")
        else:
            bad(f"pack department '{pack_id}' exited {exc.code!r}, expected 78")
else:
    bad(f"fixture precondition broken: pack roles file {pack_file!r} not found")

print(f"test-custom-department-without-roles-file: PASS={PASS[0]} FAIL={FAIL[0]}")
sys.exit(1 if FAIL[0] else 0)
PY
PY_EXIT=$?

if [ "$PY_EXIT" -eq 0 ]; then
  good "all custom-department guards pass"
else
  bad "custom-department guards failed (exit $PY_EXIT)"
fi

echo "=============================================="
echo "test-custom-department-without-roles-file: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
