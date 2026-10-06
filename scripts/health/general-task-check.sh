#!/usr/bin/env bash
# general-task-check.sh -- does THIS box have a working general-task department? Read-only.
#
# general-task is the catch-all every unroutable task lands in (the router's "no match"
# target in every decision-engine mode). The box passes only when ALL hold; each prints
# its own verdict line:
#   department-present   a general-task department folder exists under the departments tree
#   real-playbook        at least one general-task role has a real how-to.md
#                        (>= 3072 bytes, no installer placeholder text)
#   no-placeholders      0 general-task role playbooks that are missing, empty, thin or placeholder
#
# Same placeholder signatures, 3072-byte floor, live-departments-tree rule and department-name
# matching as library-gate-check.sh / create_role_workspaces.py. Writes nothing, sends nothing.
# Runs on its own. The box health gate (library-gate-check.sh) is to call it at this path
# (scripts/health/general-task-check.sh) and treat a non-zero exit as a failed item.
#
# Exit: 0 = pass   1 = at least one item failed
#       2 = bad usage   5 = cannot tell (no departments tree / no python3) -- never a pass
#
# Repair: 23-ai-workforce-blueprint/scripts/repair/ensure-general-task-dept.py
#
# Usage: general-task-check.sh [--departments-dir DIR] [--workspace DIR]
set -uo pipefail

PY="${WORKFORCE_PYTHON:-$(command -v python3 || true)}"
if [ -z "$PY" ] || ! "$PY" -c 'import sys' >/dev/null 2>&1; then
  echo "[general-task-check] UNDETERMINED: python3 not usable -- cannot check (exit 5)" >&2
  exit 5
fi

exec "$PY" - "$@" <<'PYEOF'
import argparse, json, os, re, sys
from pathlib import Path

MIN_BYTES = 3072   # = LIBRARY_MIN_BYTES in qc-completeness.sh / HOW_TO_MIN_BYTES in verify-wiring.sh
HEAD = 600         # placeholder text counts only in the first 600 bytes (a real playbook may quote a stub phrase)
SIG = re.compile(
    r"PENDING\W{0,4}FILL FROM LIBRARY"
    r"|how-to\.md \(stub\)"
    r"|to be personalized based on research"
    r"|\[\s*step\s+\d+\s*[-–—]\s*to be personalized"
    r"|\[ROUTED\W{1,6}WORK HANDLED BY GENERAL-TASK\]",
    re.IGNORECASE)
BAK = re.compile(r"\.(bak|backup)(\b|[-._]|$)", re.IGNORECASE)
NONROLE = {"sops", "_sops", "scripts", "memory", "roles"}
DECOR = re.compile(r"^dept[-_]|[-_]dept$")
SHOW = 15

ap = argparse.ArgumentParser(prog="general-task-check.sh")
ap.add_argument("--departments-dir")
ap.add_argument("--workspace")
args = ap.parse_args()

def norm(name):
    return re.sub(r"[-_\s]+", "-", DECOR.sub("", str(name or "").strip().lower())).strip("-")

def bad_reason(p):
    try:
        size = p.stat().st_size
        with open(str(p), "rb") as f:
            head = f.read(HEAD).decode("utf-8", "ignore")
    except OSError:
        return "missing" if not p.exists() else "unreadable"
    if size == 0 or not head.strip():
        return "empty"
    if SIG.search(head):
        return "placeholder text"
    if size < MIN_BYTES:
        return "thin (%d bytes)" % size
    return None

# ---- locate the departments tree: same rule as _qc_paths.live_departments_dir ----
oc = Path("/data/.openclaw")
ws = Path(args.workspace) if args.workspace else (
    oc / "workspace" if oc.is_dir() else Path.home() / ".openclaw" / "workspace")
state_file = os.environ.get("WORKFORCE_BUILD_STATE_FILE", "").strip() or str(ws / ".workforce-build-state.json")
company_root = None
try:
    company_root = json.loads(Path(state_file).read_text(encoding="utf-8")).get("companyRoot")
except (OSError, ValueError, AttributeError):
    pass
if args.departments_dir:
    dd = Path(args.departments_dir)
elif isinstance(company_root, str) and os.path.isabs(company_root) and (Path(company_root) / "departments").is_dir():
    dd = Path(company_root) / "departments"
else:
    dd = ws / "departments"

try:
    entries = sorted(d for d in dd.iterdir() if d.is_dir() and not d.name.startswith((".", "_")) and not BAK.search(d.name)) \
        if dd.is_dir() else []
except OSError:
    entries = []
if not entries:
    print("[general-task-check] UNDETERMINED: no departments found under %s -- cannot check (exit 5)" % dd, file=sys.stderr)
    sys.exit(5)

def line(item, verdict, msg):
    print("[general-task-check] %s: %s - %s" % (item, verdict, msg))

def show(items):
    for it in items[:SHOW]:
        print("    - " + it)
    if len(items) > SHOW:
        print("    ... and %d more" % (len(items) - SHOW))

print("[general-task-check] departments tree: %s (%d departments)" % (dd, len(entries)))
dept = next((d for d in entries if norm(d.name) == "general-task"), None)
failed = 0
if dept is None:
    failed += 3
    line("department-present", "FAIL", "no general-task department under %s (repair: ensure-general-task-dept.py)" % dd)
    line("real-playbook", "FAIL", "no general-task department, so no playbook")
    line("no-placeholders", "FAIL", "no general-task department to check")
else:
    line("department-present", "PASS", "general-task found at %s" % dept.name)
    roles = [r for r in sorted(dept.iterdir())
             if r.is_dir() and not r.name.startswith((".", "_")) and r.name.lower() not in NONROLE
             and ((r / "how-to.md").is_file() or (r / "IDENTITY.md").is_file())]
    verdicts = [(r, bad_reason(r / "how-to.md")) for r in roles]
    real = [r for r, why in verdicts if why is None]
    bad = [(r, why) for r, why in verdicts if why]
    if real:
        line("real-playbook", "PASS", "%d of %d general-task role playbook(s) are real" % (len(real), len(roles)))
    else:
        failed += 1
        line("real-playbook", "FAIL", "general-task has %d role folder(s) but 0 real playbooks" % len(roles))
    if bad:
        failed += 1
        line("no-placeholders", "FAIL", "%d of %d general-task role playbooks are missing, empty, thin or placeholder" % (len(bad), len(roles)))
        show(["%s/how-to.md (%s)" % (r.name, why) for r, why in bad])
    else:
        line("no-placeholders", "PASS", "0 of %d general-task role playbooks are placeholders" % len(roles))
if failed:
    print("[general-task-check] RESULT: FAIL (%d item%s failed)" % (failed, "" if failed == 1 else "s"))
    sys.exit(1)
print("[general-task-check] RESULT: PASS")
PYEOF
