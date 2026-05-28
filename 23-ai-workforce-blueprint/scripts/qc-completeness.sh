#!/usr/bin/env bash
# qc-completeness.sh - v10.15.4 (Mac) / v10.16.4 (VPS)
#
# First-class "are you done?" check for the active workforce. Runs after every
# build / install / update. Reports PASS / PARTIAL / FAIL per dept and emits a
# JSON + human-readable artifact. On != PASS, Telegrams the operator with a
# per-dept gap breakdown.
#
# Read-only. Safe to re-run any number of times.
#
# Usage:
#   bash qc-completeness.sh                 # default: Telegram on != PASS
#   bash qc-completeness.sh --quiet         # log-only, no Telegram even on FAIL
#   bash qc-completeness.sh --no-telegram   # alias for --quiet
#
# Exit codes:
#   0 = PASS  (>= 95% coverage on every dept across all metrics)
#   2 = PARTIAL  (one or more dept below threshold but non-zero)
#   3 = FAIL  (any dept at zero materialization or library missing)
#   4 = NO_WORKFORCE_FOUND  (cannot resolve active company)

set -uo pipefail

QUIET=0
for arg in "$@"; do
  case "$arg" in
    --quiet|--no-telegram) QUIET=1 ;;
    -h|--help)
      sed -n '1,25p' "$0"
      exit 0 ;;
  esac
done

# Resolve the skill 23 directory robustly. Two known canonical install layouts:
#   ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-completeness.sh   (Mac)
#   /data/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-completeness.sh  (VPS)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LIB_DIR="$SKILL_DIR/lib"
INDEX_JSON="$SKILL_DIR/templates/role-library/_index.json"

TS="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="$HOME/.openclaw/logs"
[ -d "/data/.openclaw" ] && LOG_DIR="/data/.openclaw/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/qc-completeness-${TS}.log"
JSON_FILE="$LOG_DIR/qc-completeness-${TS}.json"

log() { printf '%s\n' "$*" | tee -a "$LOG_FILE"; }

log "============================================"
log "qc-completeness.sh — ts=${TS}"
log "skill_dir=${SKILL_DIR}"
log "log_file=${LOG_FILE}"
log "json_file=${JSON_FILE}"
log "============================================"

# ----- Resolve active company via vendored detect_platform -----
COMPANY_INFO="$(python3 - <<'PYEOF' 2>>"$LOG_FILE"
import json
import os
import sys
from pathlib import Path
script_dir = Path(os.environ.get("SCRIPT_DIR", "."))
skill_dir = script_dir.parent
for p in (skill_dir / "lib", skill_dir.parent.parent / "shared-utils", skill_dir / "shared-utils"):
    sys.path.insert(0, str(p))
try:
    from detect_platform import get_openclaw_paths
except ImportError:
    print(json.dumps({"error": "detect_platform import failed"}))
    sys.exit(0)
try:
    paths = get_openclaw_paths()
except Exception as e:
    print(json.dumps({"error": f"detect_platform: {e}"}))
    sys.exit(0)
zhc_root = paths.get("active_zhc_company") or paths.get("zhc_company_root")
if not zhc_root:
    # Fall back to picking the most recently modified company dir under ~/clawd/zero-human-company/
    workspace = paths.get("workspace_root") or paths.get("clawd_root") or os.path.expanduser("~/clawd")
    zhc_dir = Path(workspace) / "zero-human-company"
    if zhc_dir.is_dir():
        candidates = sorted(
            (d for d in zhc_dir.iterdir() if d.is_dir() and not d.name.startswith("_")),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            zhc_root = str(candidates[0])
print(json.dumps({
    "company_root": zhc_root,
    "departments_dir": str(Path(zhc_root) / "departments") if zhc_root else None,
    "departments_json": str(Path(zhc_root) / "departments.json") if zhc_root else None,
}))
PYEOF
)"

SCRIPT_DIR="$SCRIPT_DIR" # ensure exported into python heredoc above? actually above used os.environ, env not exported — patch:
# (re-run if needed via env-prefix)
if echo "$COMPANY_INFO" | grep -q '"error"'; then
  # Try once more with SCRIPT_DIR exported
  export SCRIPT_DIR
  COMPANY_INFO="$(python3 - <<'PYEOF' 2>>"$LOG_FILE"
import json, os, sys
from pathlib import Path
script_dir = Path(os.environ.get("SCRIPT_DIR", "."))
skill_dir = script_dir.parent
for p in (skill_dir / "lib", skill_dir.parent.parent / "shared-utils", skill_dir / "shared-utils"):
    sys.path.insert(0, str(p))
try:
    from detect_platform import get_openclaw_paths
    paths = get_openclaw_paths()
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(0)
zhc_root = paths.get("active_zhc_company") or paths.get("zhc_company_root")
print(json.dumps({
    "company_root": zhc_root,
    "departments_dir": str(Path(zhc_root) / "departments") if zhc_root else None,
    "departments_json": str(Path(zhc_root) / "departments.json") if zhc_root else None,
}))
PYEOF
)"
fi

COMPANY_ROOT="$(printf '%s' "$COMPANY_INFO" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('company_root') or '')" 2>>"$LOG_FILE")"
DEPARTMENTS_DIR="$(printf '%s' "$COMPANY_INFO" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('departments_dir') or '')" 2>>"$LOG_FILE")"
DEPARTMENTS_JSON="$(printf '%s' "$COMPANY_INFO" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('departments_json') or '')" 2>>"$LOG_FILE")"

log "company_root=${COMPANY_ROOT:-<not-found>}"
log "departments_dir=${DEPARTMENTS_DIR:-<not-found>}"
log "departments_json=${DEPARTMENTS_JSON:-<not-found>}"

if [ -z "$COMPANY_ROOT" ] || [ ! -d "$DEPARTMENTS_DIR" ]; then
  log "NO_WORKFORCE_FOUND — no active zero-human-company on disk. Nothing to QC."
  printf '{"status":"NO_WORKFORCE_FOUND","ts":"%s"}\n' "$TS" > "$JSON_FILE"
  exit 4
fi

# ----- Run the analysis in Python (single process, single JSON output) -----
export SKILL_DIR COMPANY_ROOT DEPARTMENTS_DIR DEPARTMENTS_JSON INDEX_JSON LOG_FILE JSON_FILE TS

python3 - <<'PYEOF' 2>>"$LOG_FILE"
import json
import os
import re
import sys
from pathlib import Path

SKILL_DIR = Path(os.environ["SKILL_DIR"])
COMPANY_ROOT = Path(os.environ["COMPANY_ROOT"])
DEPARTMENTS_DIR = Path(os.environ["DEPARTMENTS_DIR"])
DEPARTMENTS_JSON = Path(os.environ["DEPARTMENTS_JSON"])
INDEX_JSON = Path(os.environ["INDEX_JSON"])
LOG_FILE = Path(os.environ["LOG_FILE"])
JSON_FILE = Path(os.environ["JSON_FILE"])
TS = os.environ["TS"]

LIBRARY_MARKER = re.compile(r"<!--\s*Filled from role-library v", re.IGNORECASE)
STUB_PATTERN = re.compile(r"to be personalized based on research", re.IGNORECASE)


def emit(line):
    with LOG_FILE.open("a") as fh:
        fh.write(line + "\n")
    print(line)


# Load library expectations (source of truth for "what does done look like")
library_depts = {}
library_total_roles = 0
if INDEX_JSON.is_file():
    try:
        idx = json.load(INDEX_JSON.open())
        library_total_roles = idx.get("total_roles", 0)
        for dept_id, dept in idx.get("departments", {}).items():
            library_depts[dept_id] = {
                "expected_roles": dept.get("role_count", 0),
                "library_version": idx.get("version", "unknown"),
            }
    except Exception as e:
        emit(f"[WARN] Could not parse {INDEX_JSON}: {e}")

# Load operator-selected departments
selected_depts = {}
if DEPARTMENTS_JSON.is_file():
    try:
        raw = json.load(DEPARTMENTS_JSON.open())
        if isinstance(raw, dict):
            selected_depts = raw
        elif isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict):
                    key = entry.get("id") or entry.get("dept_id") or entry.get("name", "")
                    if key:
                        selected_depts[key] = entry
    except Exception as e:
        emit(f"[WARN] Could not parse {DEPARTMENTS_JSON}: {e}")

# Walk DEPARTMENTS_DIR to discover what's actually on disk
on_disk_depts = []
for d in sorted(DEPARTMENTS_DIR.iterdir()):
    if d.is_dir() and not d.name.startswith("_") and not d.name.startswith("."):
        on_disk_depts.append(d)

# Per-dept analysis
dept_reports = []
overall_status = "PASS"
for dept_dir in on_disk_depts:
    dept_id = dept_dir.name
    library_lookup = dept_id
    if dept_id not in library_depts:
        for cand in library_depts:
            if cand.replace("-", "") == dept_id.replace("-", ""):
                library_lookup = cand
                break
    expected = library_depts.get(library_lookup, {}).get("expected_roles", 0)
    role_folders = [r for r in dept_dir.iterdir()
                    if r.is_dir() and not r.name.startswith(".") and not r.name.startswith("_")]
    role_count = len(role_folders)
    identity_count = sum(1 for r in role_folders if (r / "IDENTITY.md").is_file())
    library_filled_count = 0
    sop_total = 0
    stub_remaining = 0
    for r in role_folders:
        howto = r / "how-to.md"
        if howto.is_file():
            try:
                head = howto.open().read(4096)
                if LIBRARY_MARKER.search(head):
                    library_filled_count += 1
            except Exception:
                pass
        sop_files = sorted(r.glob("0[1-9]-*.md"))
        sop_total += len(sop_files)
        for sf in sop_files:
            try:
                if STUB_PATTERN.search(sf.read_text(errors="ignore")):
                    stub_remaining += 1
            except Exception:
                pass
    materialized_pct = (role_count / expected * 100.0) if expected else 0.0
    library_pct = (library_filled_count / role_count * 100.0) if role_count else 0.0
    identity_pct = (identity_count / role_count * 100.0) if role_count else 0.0
    avg_sop_per_role = (sop_total / role_count) if role_count else 0.0
    # Per-dept status
    if role_count == 0:
        dept_status = "FAIL"
    elif expected and (materialized_pct < 25 or library_pct < 25 or identity_pct < 25):
        dept_status = "FAIL"
    elif expected and (materialized_pct < 95 or library_pct < 95 or identity_pct < 95):
        dept_status = "PARTIAL"
    elif not expected and role_count > 0:
        dept_status = "PARTIAL"  # library has no expected count for this dept
    else:
        dept_status = "PASS"
    if dept_status == "FAIL":
        overall_status = "FAIL"
    elif dept_status == "PARTIAL" and overall_status == "PASS":
        overall_status = "PARTIAL"
    dept_reports.append({
        "dept_id": dept_id,
        "expected_roles": expected,
        "role_folders": role_count,
        "library_filled": library_filled_count,
        "identity_md": identity_count,
        "sop_files_total": sop_total,
        "avg_sop_per_role": round(avg_sop_per_role, 2),
        "sop_stubs_remaining": stub_remaining,
        "materialized_pct": round(materialized_pct, 1),
        "library_pct": round(library_pct, 1),
        "identity_pct": round(identity_pct, 1),
        "status": dept_status,
    })

# Legacy tree detection (Angeleen pattern)
legacy_detected = []
for candidate in [
    Path("/data/clawd/departments"),
    Path.home() / "clawd" / "departments",
]:
    if candidate.is_dir():
        try:
            workspace_dept_dir = DEPARTMENTS_DIR.resolve()
            if candidate.resolve() != workspace_dept_dir:
                legacy_detected.append(str(candidate))
        except Exception:
            legacy_detected.append(str(candidate))

# Build the final report
report = {
    "status": overall_status,
    "ts": TS,
    "company_root": str(COMPANY_ROOT),
    "library_version": (library_depts[next(iter(library_depts))]["library_version"]
                        if library_depts else "missing"),
    "library_total_roles_expected": library_total_roles,
    "depts_on_disk": len(on_disk_depts),
    "depts_passing": sum(1 for d in dept_reports if d["status"] == "PASS"),
    "depts_partial": sum(1 for d in dept_reports if d["status"] == "PARTIAL"),
    "depts_failing": sum(1 for d in dept_reports if d["status"] == "FAIL"),
    "legacy_tree_present": legacy_detected,
    "departments": dept_reports,
}
JSON_FILE.write_text(json.dumps(report, indent=2))

# Human readable
emit("")
emit(f"Library version expected: {report['library_version']} ({library_total_roles} roles across {len(library_depts)} depts)")
emit(f"On disk: {report['depts_on_disk']} depts ({report['depts_passing']} PASS, "
     f"{report['depts_partial']} PARTIAL, {report['depts_failing']} FAIL)")
emit("")
emit(f"{'DEPT':<28} {'ROLES':>6} {'EXPECT':>7} {'LIB%':>6} {'ID%':>6} {'SOP/role':>9} {'STATUS':>8}")
emit("-" * 80)
for d in dept_reports:
    emit(f"{d['dept_id']:<28} {d['role_folders']:>6} {d['expected_roles']:>7} "
         f"{d['library_pct']:>6.1f} {d['identity_pct']:>6.1f} "
         f"{d['avg_sop_per_role']:>9.2f} {d['status']:>8}")
if legacy_detected:
    emit("")
    emit(f"LEGACY TREE PRESENT (Angeleen pattern):")
    for p in legacy_detected:
        emit(f"  - {p}  (run reconcile-legacy-tree.py from Release 2 to merge)")
emit("")
emit(f"STATUS: {overall_status}")
PYEOF

RC=$?
if [ "$RC" -ne 0 ]; then
  log "Python analyzer returned non-zero exit $RC. See $LOG_FILE."
fi

# Read final status from JSON
STATUS="$(python3 -c "import json,sys; d=json.load(open('$JSON_FILE')); print(d.get('status','UNKNOWN'))" 2>>"$LOG_FILE")"
log "Final status: ${STATUS}"

# Telegram on != PASS (unless --quiet)
if [ "$QUIET" = "0" ] && [ "$STATUS" != "PASS" ] && [ "$STATUS" != "NO_WORKFORCE_FOUND" ]; then
  # Resolve openclaw binary across the 6 known locations
  OC_BIN=""
  for cand in "${OPENCLAW_BIN:-}" "$(command -v openclaw 2>/dev/null)" \
              "/opt/homebrew/bin/openclaw" "/usr/local/bin/openclaw" \
              "$HOME/.openclaw/bin/openclaw" "/data/.npm-global/bin/openclaw" \
              "/data/linuxbrew/.linuxbrew/bin/openclaw"; do
    if [ -n "$cand" ] && [ -x "$cand" ]; then OC_BIN="$cand"; break; fi
  done
  # Resolve owner chat id from openclaw.json
  OCJSON="$HOME/.openclaw/openclaw.json"
  [ -f "/data/.openclaw/openclaw.json" ] && OCJSON="/data/.openclaw/openclaw.json"
  OWNER_CHAT="$(python3 - <<PYEOF 2>>"$LOG_FILE"
import json
try:
    cfg = json.load(open("$OCJSON"))
    allow = cfg.get("channels", {}).get("telegram", {}).get("allowFrom", []) \
        or cfg.get("channels", {}).get("telegram", {}).get("ownerAllowFrom", [])
    if allow:
        print(allow[0])
except Exception:
    pass
PYEOF
)"
  if [ -n "$OC_BIN" ] && [ -n "$OWNER_CHAT" ]; then
    SUMMARY="$(python3 - <<PYEOF 2>>"$LOG_FILE"
import json
d = json.load(open("$JSON_FILE"))
lines = [f"OpenClaw QC: {d['status']} on workforce {d.get('company_root','')}"]
lines.append(f"depts: PASS={d['depts_passing']} PARTIAL={d['depts_partial']} FAIL={d['depts_failing']}")
gaps = [dd for dd in d.get("departments", []) if dd["status"] != "PASS"]
for dd in gaps[:8]:
    lines.append(f"- {dd['dept_id']}: {dd['role_folders']}/{dd['expected_roles']} roles, "
                 f"lib%={dd['library_pct']}, id%={dd['identity_pct']}, status={dd['status']}")
if d.get("legacy_tree_present"):
    lines.append("legacy tree present: " + ", ".join(d["legacy_tree_present"]))
lines.append("Full report: $JSON_FILE")
lines.append("Fix: run migrate-existing-workforce.sh (R2) once available.")
print("\n".join(lines))
PYEOF
)"
    "$OC_BIN" message send --channel telegram -t "$OWNER_CHAT" -m "$SUMMARY" >>"$LOG_FILE" 2>&1 \
      && log "Telegram alert sent to ${OWNER_CHAT}" \
      || log "Telegram send FAILED (see log)"
  else
    log "Telegram skip: openclaw_bin=${OC_BIN:-MISSING} owner_chat=${OWNER_CHAT:-MISSING}"
  fi
fi

case "$STATUS" in
  PASS) exit 0 ;;
  PARTIAL) exit 2 ;;
  FAIL) exit 3 ;;
  NO_WORKFORCE_FOUND) exit 4 ;;
  *) exit 1 ;;
esac
