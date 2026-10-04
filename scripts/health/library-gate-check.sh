#!/usr/bin/env bash
# library-gate-check.sh -- does THIS box meet the library standard? Read-only.
#
# A box passes only when ALL of these hold (each prints its own verdict line):
#   placeholder-files  0 role playbooks / SOP files that are empty, thin or still
#                      installer placeholder text
#   directors          every department has a director (the AI CEO department's
#                      director is the AI CEO)
#   user-md-links      0 broken USER.md symlinks under the departments tree
# Missing yearly revenue goal is a WARNING, never a failure:
#   revenue-goal       company-config.json carries yearlyRevenueGoal
#
# Reuses the verify-library-gate.sh / qc-completeness.sh logic (same placeholder
# signatures, same 3072-byte playbook floor, same live-departments-tree rule as
# 23-ai-workforce-blueprint/scripts/_qc_paths.py, same .bak-dir and role-folder
# definitions). It deliberately does NOT call verify-library-gate.sh: that script
# writes the build-state file and can send the owner a welcome message on a pass.
# A health check must change nothing. This one writes nothing and sends nothing.
#
# Exit: 0 = pass (warnings allowed)  1 = at least one item failed
#       2 = bad usage               5 = cannot tell (no departments tree / no python3)
#       "cannot tell" is never a pass.
#
# Usage: library-gate-check.sh [--departments-dir DIR] [--workspace DIR]
#                              [--company-config FILE]
set -uo pipefail

PY="${WORKFORCE_PYTHON:-$(command -v python3 || true)}"
if [ -z "$PY" ] || ! "$PY" -c 'import sys' >/dev/null 2>&1; then
  echo "[library-gate-check] UNDETERMINED: python3 not usable -- cannot check (exit 5)" >&2
  exit 5
fi

exec "$PY" - "$@" <<'PYEOF'
import argparse, json, os, re, sys
from pathlib import Path

MIN_BYTES = 3072   # = LIBRARY_MIN_BYTES in qc-completeness.sh / HOW_TO_MIN_BYTES in verify-wiring.sh
HEAD = 600         # role playbooks: placeholder text counts only in the first 600 bytes, as in
                   # fill-pending-howtos.is_pending (a real playbook may QUOTE a stub phrase as doctrine)
WHOLE = 262144     # SOP files: whole-file check, as in qc-completeness.sop_is_substantive
# Same signatures as qc-completeness.sh (STUB_PATTERN, PLACEHOLDER_STEP),
# fill-pending-howtos.py (PENDING markers + routing notice).
SIG = re.compile(
    r"PENDING\W{0,4}FILL FROM LIBRARY"
    r"|how-to\.md \(stub\)"
    r"|to be personalized based on research"
    r"|\[\s*step\s+\d+\s*[-–—]\s*to be personalized"
    r"|\[ROUTED\W{1,6}WORK HANDLED BY GENERAL-TASK\]",
    re.IGNORECASE)
BAK = re.compile(r"\.(bak|backup)(\b|[-._]|$)", re.IGNORECASE)   # backup snapshot dirs are not departments
NONROLE = {"sops", "_sops", "scripts", "memory", "roles"}        # not role folders ("roles" holds flat role files)
SOPDIRS = {"sops", "_sops", "sop"}
CORE = {"AGENTS.md", "TOOLS.md", "USER.md", "IDENTITY.md", "SOUL.md", "MEMORY.md", "HEARTBEAT.md", "DREAMS.md", "ROSTER.md"}
DIRECTOR = re.compile(r"director|head-of|chief-.+-officer|ai-ceo", re.IGNORECASE)
SHOW = 15

ap = argparse.ArgumentParser(prog="library-gate-check.sh")
ap.add_argument("--departments-dir")
ap.add_argument("--workspace")
ap.add_argument("--company-config")
args = ap.parse_args()


def head_text(p, n=HEAD):
    with open(str(p), "rb") as f:
        return f.read(n).decode("utf-8", "ignore")


def bad_reason(p, floor, whole=False):
    """Why this file is not a real playbook, or None. floor=True adds the 3072-byte minimum."""
    try:
        size = p.stat().st_size
        txt = head_text(p, WHOLE if whole else HEAD)
    except OSError:
        return "unreadable"
    if size == 0 or not txt.strip():
        return "empty"
    if SIG.search(txt):
        return "placeholder text"
    if floor and size < MIN_BYTES:
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

depts = []
if dd.is_dir():
    depts = [d for d in sorted(dd.iterdir())
             if d.is_dir() and not d.name.startswith((".", "_")) and not BAK.search(d.name)]
if not depts:
    print("[library-gate-check] UNDETERMINED: no departments found under %s -- cannot check (exit 5)" % dd, file=sys.stderr)
    sys.exit(5)

# ---- 1. placeholder files + 2. directors ----
files = {}          # path -> reason (None = fine); one entry per file examined
residue = []        # other dept-level .md files (ROSTER.md ...) still carrying placeholder text
no_director = []
for dept in depts:
    names = []
    for r in sorted(dept.iterdir()):
        if r.is_dir() and not r.name.startswith((".", "_")) and r.name.lower() not in NONROLE \
                and ((r / "how-to.md").is_file() or (r / "IDENTITY.md").is_file()):
            names.append(r.name)
            h = r / "how-to.md"
            files[h] = bad_reason(h, True) if h.is_file() else "missing how-to.md"
    roles_sub = dept / "roles"
    if roles_sub.is_dir():
        for f in sorted(roles_sub.glob("*.md")):
            names.append(f.stem)
            files.setdefault(f, bad_reason(f, False))
    top = dept / "how-to.md"
    if top.is_file():
        files.setdefault(top, bad_reason(top, False))
    for f in sorted(dept.glob("*.md")):
        if f.is_file() and not f.is_symlink() and f.name != "how-to.md" and SIG.search(head_text(f)):
            residue.append(f)
    for root, dirs, fs in os.walk(str(dept)):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() != "memory"]
        if any(part.lower() in SOPDIRS for part in Path(root).relative_to(dept).parts):
            for n in fs:
                p = Path(root) / n
                # inherited core files (USER.md, TOOLS.md ...) are shared copies/links, not SOPs
                if n.endswith(".md") and n not in CORE and p.is_file() and not p.is_symlink():
                    files.setdefault(p, bad_reason(p, False, True))
    if not any(DIRECTOR.search(n) for n in names):
        no_director.append(dept.name)

placeholders = sorted((p, why) for p, why in files.items() if why)

# ---- 3. broken USER.md links ----
links = broken = 0
broken_list = []
for root, dirs, fs in os.walk(str(dd)):
    dirs[:] = [d for d in dirs if not d.startswith(".") and not BAK.search(d)]
    if "USER.md" in fs:
        p = os.path.join(root, "USER.md")
        if os.path.islink(p):
            links += 1
            if not os.path.exists(p):
                broken += 1
                broken_list.append(p)

# ---- 4. revenue goal (warning only) ----
cands = []
if args.company_config:
    cands.append(Path(args.company_config))
else:
    if os.environ.get("OPENCLAW_COMPANY_CONFIG"):
        cands.append(Path(os.environ["OPENCLAW_COMPANY_CONFIG"]))
    if isinstance(company_root, str) and os.path.isabs(company_root):
        cands.append(Path(company_root) / "company-config.json")
    masters = [Path("/data/openclaw-master-files")] if oc.is_dir() else [Path.home() / "Downloads" / "openclaw-master-files"]
    masters.append(Path.home() / ".openclaw" / "openclaw-master-files")
    found = [p for m in masters for p in (m / "zero-human-company").glob("*/company-config.json")]
    cands += sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)   # several companies: newest wins
cfg = next((c for c in cands if c.is_file()), None)
goal_msg = None
if cfg is None:
    goal_msg = "no company-config.json found"
else:
    try:
        v = json.loads(cfg.read_text(encoding="utf-8")).get("yearlyRevenueGoal")
        # ponytail: any positive number or non-empty text counts as "answered"; no currency parsing
        ok = (isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0) or \
             (isinstance(v, str) and v.strip().lower() not in ("", "null", "none", "n/a", "unknown", "tbd"))
        if not ok:
            goal_msg = "yearlyRevenueGoal is not set in %s" % cfg
    except (OSError, ValueError, AttributeError):
        goal_msg = "cannot read %s" % cfg


def show(items, fmt):
    for it in items[:SHOW]:
        print("    - " + fmt(it))
    if len(items) > SHOW:
        print("    ... and %d more" % (len(items) - SHOW))


def line(item, verdict, msg):
    print("[library-gate-check] %s: %s - %s" % (item, verdict, msg))


print("[library-gate-check] departments tree: %s (%d departments)" % (dd, len(depts)))
failed = 0
warned = 0
if placeholders:
    failed += 1
    line("placeholder-files", "FAIL", "%d of %d role playbooks / SOP files are empty, thin or placeholder" % (len(placeholders), len(files)))
    show(placeholders, lambda x: "%s (%s)" % (x[0].relative_to(dd), x[1]))
else:
    line("placeholder-files", "PASS", "0 of %d role playbooks / SOP files are placeholders" % len(files))
if no_director:
    failed += 1
    line("directors", "FAIL", "%d of %d departments have no director" % (len(no_director), len(depts)))
    show(no_director, str)
else:
    line("directors", "PASS", "all %d departments have a director" % len(depts))
if broken:
    failed += 1
    line("user-md-links", "FAIL", "%d of %d USER.md links are broken" % (broken, links))
    show(broken_list, lambda p: os.path.relpath(p, str(dd)))
else:
    line("user-md-links", "PASS", "0 of %d USER.md links are broken" % links)
if goal_msg:
    warned += 1
    line("revenue-goal", "WARN", goal_msg + " (warning only; the box's own agent asks its owner)")
else:
    line("revenue-goal", "PASS", "yearlyRevenueGoal is set")
if residue:
    warned += 1
    line("placeholder-residue", "WARN", "%d other department files still carry placeholder text (warning only)" % len(residue))
    show(residue, lambda p: str(p.relative_to(dd)))
if failed:
    print("[library-gate-check] RESULT: FAIL (%d item%s failed, %d warning%s)" % (failed, "" if failed == 1 else "s", warned, "" if warned == 1 else "s"))
    sys.exit(1)
print("[library-gate-check] RESULT: PASS (%d warning%s)" % (warned, "" if warned == 1 else "s"))
PYEOF
