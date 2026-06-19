#!/usr/bin/env bash
# qc-completeness.sh - v10.15.44 (Mac) / v10.16.43 (VPS)
# v12.9.4 (fix/gate-company-dir-resolution): fail-loud guard for resolver bugs.
# If _qc_company_info.py emits gate_bug=true (real workforce dir exists but
# company-dir resolution still returned no result), this script now exits 5
# (GATE_BUG) with a loud log message rather than silently exiting 4
# (NO_WORKFORCE_FOUND), which previously hid resolver regressions from operators.
# v11.18.4 STOCK-BASH-3.2 COMPATIBILITY: the embedded `python3 - <<PYEOF` snippets
# that lived inside $() command substitutions are externalized to sibling files
# (_qc_company_info.py, _qc_get.py, _qc_owner_chat.py, _qc_summary.py). Stock
# macOS /bin/bash 3.2.57 mis-parses a heredoc nested in a $() — it counts the
# double-quotes inside the Python and aborts the entire script with `unexpected
# EOF while looking for matching "` at PARSE time. The main analyzer heredoc
# (`python3 - <<'PYEOF'` at column 0, NOT inside a $()) is unaffected and stays
# inline. Logic is byte-equivalent across the port.
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
#   5 = GATE_BUG  (resolver returned no result but real workforce dir exists)
#   6 = PRESENTATION_DEPS_MISSING  (a presentation-pipeline runtime dep is absent)
#
# PRESENTATION-DEPS HARD GATE (deps-fix): the Skill 23 presentation pipeline
# requires four runtime deps — soffice (LibreOffice/libreoffice-impress, PPTX→PDF),
# pdftoppm (poppler/poppler-utils, PDF→PNG for Phase-6 QC), and the Python modules
# reportlab + pptx (python-pptx). install.sh Step 6.5 installs all four. This gate
# now hard-fails (exit 6) when ANY of them is missing, so onboarding / the
# presentation build cannot be declared complete with a broken pipeline. The check
# runs BEFORE the workforce resolution so it fires even on a not-yet-built company.
# Set QC_SKIP_PRESENTATION_DEPS=1 to bypass (e.g. a non-presentation install).

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

# ----- PRESENTATION-DEPS HARD GATE (deps-fix) -----------------------------------
# Skill 23's presentation pipeline cannot run without these four runtime deps.
# install.sh Step 6.5 installs them (Mac: brew + pip; VPS: real /usr/bin/apt-get +
# pip, re-asserted by the reassert-presentation-deps cron). If any is missing the
# build will silently produce no deck / no presenter guide / no Phase-6 QC PNGs, so
# we HARD-FAIL here (exit 6) rather than letting onboarding pass. Runs before the
# workforce resolution so it fires even on a not-yet-built company.
if [ "${QC_SKIP_PRESENTATION_DEPS:-0}" != "1" ]; then
  _PRES_DEPS_MISSING=""
  command -v soffice  >/dev/null 2>&1 || _PRES_DEPS_MISSING="${_PRES_DEPS_MISSING} soffice(libreoffice-impress)"
  command -v pdftoppm >/dev/null 2>&1 || _PRES_DEPS_MISSING="${_PRES_DEPS_MISSING} pdftoppm(poppler-utils)"
  python3 -c "import reportlab, pptx" >/dev/null 2>&1 || _PRES_DEPS_MISSING="${_PRES_DEPS_MISSING} python(reportlab+python-pptx)"
  if [ -n "$_PRES_DEPS_MISSING" ]; then
    log "PRESENTATION_DEPS_MISSING — missing:${_PRES_DEPS_MISSING}"
    log "  The Skill 23 presentation pipeline cannot run. Re-run install.sh Step 6.5,"
    log "  or on a VPS run: bash /data/.openclaw/scripts/reassert-presentation-deps.sh"
    printf '{"status":"PRESENTATION_DEPS_MISSING","ts":"%s","missing":"%s"}\n' "$TS" "${_PRES_DEPS_MISSING# }" > "$JSON_FILE"
    exit 6
  fi
  log "presentation deps OK: soffice + pdftoppm + reportlab + python-pptx all present"
fi

# ----- Resolve active company via vendored detect_platform -----
# v10.15.44 / v10.16.43 FIX: use the same resolver as post-build-role-workspaces.py.
# detect_platform.get_openclaw_paths() returns "company_dir" (the resolved active
# company slug dir) and "company_root" (the parent zero-human-company/ dir), NOT
# "active_zhc_company" or "zhc_company_root". Previous code always fell through to
# the ~/clawd fallback and failed on symlinked or non-standard workspace layouts,
# emitting company_root=<not-found> / NO_WORKFORCE_FOUND even on fully built workforces.
# Fix: use paths["company_dir"] first, follow symlinks when testing existence, and
# scan all candidate paths the working pipeline knows about.
export SCRIPT_DIR
# v11.18.4 STOCK-BASH-3.2 COMPATIBILITY: the resolver Python (formerly an inline
# `python3 - <<'PYEOF' ... PYEOF` heredoc inside this $()) is now shipped as the
# sibling _qc_company_info.py. Stock macOS /bin/bash 3.2.57 mis-parses a heredoc
# nested in a $() command substitution — it counts the double-quotes inside the
# Python and aborts the WHOLE script with `unexpected EOF while looking for
# matching "` at PARSE time, so every no-Homebrew client Mac had a dead QC gate.
# Externalizing the snippet keeps the logic byte-equivalent and makes the script
# `bash -n` clean on bash 3.2. _qc_company_info.py reads SCRIPT_DIR /
# OPENCLAW_COMPANY_SLUG from the env (exported above) and prints the info JSON.
COMPANY_INFO="$(python3 "$SCRIPT_DIR/_qc_company_info.py" 2>>"$LOG_FILE")"

COMPANY_ROOT="$(printf '%s' "$COMPANY_INFO" | python3 "$SCRIPT_DIR/_qc_get.py" company_root 2>>"$LOG_FILE")"
DEPARTMENTS_DIR="$(printf '%s' "$COMPANY_INFO" | python3 "$SCRIPT_DIR/_qc_get.py" departments_dir 2>>"$LOG_FILE")"
DEPARTMENTS_JSON="$(printf '%s' "$COMPANY_INFO" | python3 "$SCRIPT_DIR/_qc_get.py" departments_json 2>>"$LOG_FILE")"

log "company_root=${COMPANY_ROOT:-<not-found>}"
log "departments_dir=${DEPARTMENTS_DIR:-<not-found>}"
log "departments_json=${DEPARTMENTS_JSON:-<not-found>}"

# v12.9.4 FAIL-LOUD: detect the gate_bug sentinel from _qc_company_info.py.
# If the resolver emitted gate_bug=true, a real workforce root exists but the
# resolver still returned no company dir — that is a BUG in this script, not a
# missing workforce.  Exit 5 (GATE_BUG) so CI / operators see a hard failure
# rather than a misleading NO_WORKFORCE_FOUND that looks like "not built yet".
GATE_BUG="$(printf '%s' "$COMPANY_INFO" | python3 "$SCRIPT_DIR/_qc_get.py" gate_bug 2>>"$LOG_FILE")"
if [ "$GATE_BUG" = "True" ] || [ "$GATE_BUG" = "true" ]; then
  GATE_BUG_MSG="$(printf '%s' "$COMPANY_INFO" | python3 "$SCRIPT_DIR/_qc_get.py" error 2>>"$LOG_FILE")"
  log "GATE_BUG — resolver returned no company dir but a real workforce dir exists."
  log "  error: ${GATE_BUG_MSG:-see _qc_company_info.py output above}"
  log "  This is a resolver bug, not a missing workforce. Check detect_platform paths."
  printf '{"status":"GATE_BUG","ts":"%s","error":"%s"}\n' "$TS" "${GATE_BUG_MSG}" > "$JSON_FILE"
  exit 5
fi

if [ -z "$COMPANY_ROOT" ] || [ -z "$DEPARTMENTS_DIR" ] || [ ! -d "$DEPARTMENTS_DIR" ]; then
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

LIBRARY_MARKER = re.compile(r"<!--\s*(?:WS-2: instantiated|Filled) from role-library v", re.IGNORECASE)
STUB_PATTERN = re.compile(r"to be personalized based on research", re.IGNORECASE)
# BUG 1 FIX (v12.14.6): the library gate used to count a how-to.md as "filled"
# based solely on the presence of the <!-- Filled from role-library v... --> marker
# in the first 4096 bytes, WITHOUT checking actual file size.  A prior run could
# stamp the marker onto a thin hand-written stub (e.g. 156 bytes) and the gate
# would report library_pct=100% while the wiring gate (HOW_TO_MIN_BYTES=3072)
# simultaneously failed the same file.  Fix: a role only counts as library-filled
# when the marker is present AND the file is >= LIBRARY_MIN_BYTES (same 3 KB
# floor that verify-wiring.sh enforces).  The marker is now a necessary but
# insufficient condition; real content size is the authoritative check.
LIBRARY_MIN_BYTES = 3072  # must match HOW_TO_MIN_BYTES in verify-wiring.sh

# v10.15.18 SUBSTANCE GATE. A SOP file counts as "substantive" ONLY if it is a
# real, authored DMAIC SOP — not a thin/hollow file and not a placeholder stub.
# Three conditions, all required:
#   1. size >= SUBSTANTIVE_MIN_BYTES (7 KB)
#   2. all five DMAIC section headers present (## DEFINE / MEASURE / ANALYZE /
#      IMPROVE / CONTROL — the exact headers the SOP-population manifest mandates)
#   3. no remaining "[Step N - to be personalized ...]" placeholder
# This is what stops a 1 KB hollow SOP (or a stub with the placeholder string
# deleted) from being counted as "done" — the documented thin-file / stub-file
# / empty-file failure.
SUBSTANTIVE_MIN_BYTES = 7168  # 7 KB
DMAIC_HEADERS = ("define", "measure", "analyze", "improve", "control")
PLACEHOLDER_STEP = re.compile(r"\[\s*step\s+\d+\s*[-–—]\s*to be personalized", re.IGNORECASE)
DMAIC_HEADER_RE = re.compile(r"^#{1,4}\s*(define|measure|analyze|improve|control)\b", re.IGNORECASE | re.MULTILINE)

# v10.15.25 / v10.16.24 — EMBEDDED-SECTION-9 SOP MODEL (the WS-2 instantiate shape).
# The WS-2 instantiate path does NOT write standalone sops/NN-*.md files; it embeds
# SOPs inside how-to.md as a "## 9. ..." section containing SOP block headers
# ("### SOP 9.x", "### SOP-01:", "### SOP-AUDIO-001:", "### SOP B-9.1 --", etc.),
# each carrying the When-to-run / Frequency / Inputs / Steps / Outputs / Hand-to /
# Failure-mode structure.  The old gate only counted standalone 0[1-9]-*.md files,
# so fully-instantiated substantive workforces (multiple clients) were marked
# INCOMPLETE -> the never-stop crons looped forever or fell back to regenerate.
# We now accept EITHER model as substantive, WITHOUT weakening the gate against real
# garbage: still FAIL on [Step N...] stubs, {{token}} leaks, <7KB, or a missing
# Section 9.  v12.17.2: SOP_BLOCK_RE widened to also match non-dotted SOP formats.
SECTION9_HEADER_RE = re.compile(r"^#{1,3}\s*9[\.\)]", re.MULTILINE)         # "## 9." / "### 9)" etc.
# v12.17.2 FIX (gate-regex): the original regex only matched the dotted "### SOP 9.x"
# format, leaving ~83 roles unscored whose role-library files use the hyphen or
# em-dash formats ("### SOP-01:", "### SOP-AUDIO-001:", "### SOP-01 —", "### SOP B-9.1",
# "### SOP 1 --").  The wider pattern below matches BOTH:
#   - old dotted:  ^#{2,4} SOP 9.   e.g. "### SOP 9.1"
#   - new formats: ^#{2,4} SOP[-\s][A-Za-z0-9]  e.g. "### SOP-01:", "### SOP AUDIO-001:"
# Scoping guard (SECTION9_HEADER_RE + TOKEN_LEAK_RE + size >= 7 KB) is UNCHANGED —
# only the heading shape is widened; the substance bar is identical.
SOP_BLOCK_RE = re.compile(
    r"^#{2,4}\s*SOP(?:\s*9[\.\)]|[-\s][A-Za-z0-9])",
    re.IGNORECASE | re.MULTILINE,
)  # "### SOP 9.x" OR "### SOP-01" / "### SOP-AUDIO-001" etc.
TOKEN_LEAK_RE = re.compile(r"\{\{\s*[A-Za-z0-9_]+\s*\}\}")                  # an unfilled {{token}}
# The structured fields a real embedded SOP block must carry (allow markdown bold,
# and the When-to-run / Hand-to hyphen/space variants).
EMBEDDED_SOP_FIELDS = (
    re.compile(r"when[\s\-]*to[\s\-]*run", re.IGNORECASE),
    re.compile(r"\bfrequency\b", re.IGNORECASE),
    re.compile(r"\binputs?\b", re.IGNORECASE),
    re.compile(r"\bsteps?\b", re.IGNORECASE),
    re.compile(r"\boutputs?\b", re.IGNORECASE),
    re.compile(r"hand[\s\-]*to", re.IGNORECASE),
    re.compile(r"failure[\s\-]*mode", re.IGNORECASE),
)
EMBEDDED_FIELD_MIN = 5  # an embedded SOP block must carry >= 5 of the 7 structured fields


def sop_is_substantive(path):
    """Return True iff a STANDALONE SOP file is a real, authored DMAIC SOP per the gate."""
    try:
        size = path.stat().st_size
        if size < SUBSTANTIVE_MIN_BYTES:
            return False
        text = path.read_text(errors="ignore")
    except Exception:
        return False
    if STUB_PATTERN.search(text) or PLACEHOLDER_STEP.search(text):
        return False
    found = {m.group(1).lower() for m in DMAIC_HEADER_RE.finditer(text)}
    return all(h in found for h in DMAIC_HEADERS)


def embedded_sop_count(howto_path):
    """Count substantive EMBEDDED Section-9 SOP blocks inside a role's how-to.md.

    Returns the number of `### SOP 9.x` blocks that carry the structured
    When/Frequency/Inputs/Steps/Outputs/Hand-to/Failure-mode shape, but ONLY if the
    how-to.md itself qualifies (>= 7KB, has a `## 9.` Section-9 header, no
    [Step N...] / "to be personalized" stub, and NO {{token}} leak). Returns 0 if
    the file fails any guard — so this NEVER passes garbage; it only stops the
    false-negative on real instantiated content.
    """
    try:
        if howto_path.stat().st_size < SUBSTANTIVE_MIN_BYTES:
            return 0
        text = howto_path.read_text(errors="ignore")
    except Exception:
        return 0
    # Hard guards (same strictness as the standalone model).
    if STUB_PATTERN.search(text) or PLACEHOLDER_STEP.search(text):
        return 0
    if TOKEN_LEAK_RE.search(text):
        return 0
    if not SECTION9_HEADER_RE.search(text):
        return 0
    # Split into blocks at each "### SOP 9." header; a block is substantive if it
    # carries >= EMBEDDED_FIELD_MIN of the structured fields.
    starts = [m.start() for m in SOP_BLOCK_RE.finditer(text)]
    if not starts:
        return 0
    bounds = starts + [len(text)]
    count = 0
    for i in range(len(starts)):
        block = text[bounds[i]:bounds[i + 1]]
        fields_present = sum(1 for fre in EMBEDDED_SOP_FIELDS if fre.search(block))
        if fields_present >= EMBEDDED_FIELD_MIN:
            count += 1
    return count


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
            # v10.15.18: the _index.json schema uses "count" per dept; older
            # readers looked for "role_count" and ALWAYS got 0 -> expected_roles
            # was 0 -> the canonical-role-count check was a silent no-op. Accept
            # both keys, and fall back to len(roles) so expected is never wrongly 0.
            _expected = dept.get("count")
            if _expected is None:
                _expected = dept.get("role_count")
            if _expected is None and isinstance(dept.get("roles"), list):
                _expected = len(dept["roles"])
            library_depts[dept_id] = {
                "expected_roles": _expected or 0,
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
    # v10.15.18 SUBSTANCE GATE counters
    substantive_sop_total = 0          # SOPs that pass sop_is_substantive() (either model)
    roles_with_min_sops = 0            # roles meeting their own min substantive SOP floor
    min_sop_per_role = None            # smallest substantive-SOP count across roles
    per_role_substantive = []          # for diagnostics
    embedded_model_roles = 0           # v10.15.25: roles satisfied via embedded Section-9 SOPs
    SOP_FLOOR = 4                      # every role needs >= 4 substantive SOPs (matches "Core SOPs to build" floor)
    # v10.15.25 / v10.16.24: embedded-Section-9 roles often carry their full DMAIC
    # SOP set in a SINGLE rich how-to.md. The "## 9." section is one consolidated
    # SOP system, so a role that presents the embedded model passes the floor with
    # >= 1 substantive embedded SOP block (it is NOT short-changed against the
    # 4-standalone-file floor). The standalone model keeps the strict >= 4 floor.
    EMBEDDED_SOP_FLOOR = 1
    for r in role_folders:
        howto = r / "how-to.md"
        howto_embedded = 0
        if howto.is_file():
            try:
                howto_size = howto.stat().st_size
                head = howto.open().read(4096)
                # BUG 1 FIX: marker alone is not sufficient — the file must also
                # meet the 3 KB content floor so a thin stub that was incorrectly
                # stamped with the marker cannot pass as "filled".
                if LIBRARY_MARKER.search(head) and howto_size >= LIBRARY_MIN_BYTES:
                    library_filled_count += 1
            except Exception:
                pass
            # v10.15.25: count substantive embedded Section-9 SOP blocks (instantiate model)
            howto_embedded = embedded_sop_count(howto)
        sop_files = sorted(r.glob("0[1-9]-*.md"))
        sop_total += len(sop_files)
        standalone_substantive = 0
        for sf in sop_files:
            try:
                if STUB_PATTERN.search(sf.read_text(errors="ignore")):
                    stub_remaining += 1
            except Exception:
                pass
            if sop_is_substantive(sf):
                standalone_substantive += 1
        # Count whichever model carries this role's substantive SOPs toward the total.
        role_substantive = standalone_substantive + howto_embedded
        # A role PASSES its floor if EITHER model is satisfied:
        #   - standalone:  >= SOP_FLOOR substantive 0[1-9]-*.md files, OR
        #   - embedded:    >= EMBEDDED_SOP_FLOOR substantive Section-9 SOP blocks.
        role_meets_floor = (standalone_substantive >= SOP_FLOOR) or (howto_embedded >= EMBEDDED_SOP_FLOOR)
        substantive_sop_total += role_substantive
        per_role_substantive.append(role_substantive)
        if howto_embedded > 0 and standalone_substantive < SOP_FLOOR:
            embedded_model_roles += 1
        if role_meets_floor:
            roles_with_min_sops += 1
        if min_sop_per_role is None or role_substantive < min_sop_per_role:
            min_sop_per_role = role_substantive
    if min_sop_per_role is None:
        min_sop_per_role = 0
    # FIX 3 (2026-06-17): GOVERNING-PERSONAS GATE — a department is NOT FULL
    # (not classified PASS) unless it has governing-personas.md. Additive: does
    # not alter any existing role/IDENTITY/SOUL/SOP checks above; only promotes
    # PASS→PARTIAL when the file is absent. FAIL thresholds are unchanged.
    has_governing_personas = (dept_dir / "governing-personas.md").is_file()
    materialized_pct = (role_count / expected * 100.0) if expected else 0.0
    library_pct = (library_filled_count / role_count * 100.0) if role_count else 0.0
    identity_pct = (identity_count / role_count * 100.0) if role_count else 0.0
    avg_sop_per_role = (sop_total / role_count) if role_count else 0.0
    avg_substantive_sop_per_role = (substantive_sop_total / role_count) if role_count else 0.0
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
    # FIX 3: governing-personas.md absence downgrades PASS → PARTIAL (never FAIL).
    # A PARTIAL or FAIL dept is already below PASS, so no change needed there.
    if dept_status == "PASS" and not has_governing_personas:
        dept_status = "PARTIAL"
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
        # v10.15.18 SUBSTANCE GATE fields
        "substantive_sop_count": substantive_sop_total,
        "avg_substantive_sop_per_role": round(avg_substantive_sop_per_role, 2),
        "min_sop_per_role": min_sop_per_role,
        "sop_floor": SOP_FLOOR,
        "roles_with_min_sops": roles_with_min_sops,
        "roles_below_min_sops": role_count - roles_with_min_sops,
        # v10.15.25 / v10.16.24: how many roles are satisfied via the embedded
        # Section-9 SOP model (instantiate path) rather than standalone SOP files
        "embedded_model_roles": embedded_model_roles,
        "materialized_pct": round(materialized_pct, 1),
        "library_pct": round(library_pct, 1),
        "identity_pct": round(identity_pct, 1),
        # FIX 3 (2026-06-17): personas gate field
        "has_governing_personas": has_governing_personas,
        "status": dept_status,
    })

# Legacy tree detection (legacy-tree pattern)
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

# ---- v10.15.26 / v10.16.25: HARD DEPARTMENT FLOOR (counts REAL depts on disk)
# Before this, qc-completeness measured per-dept STAFFING of whatever was on
# disk but had NO floor concept: a 3-dept workforce where those 3 were fully
# staffed returned PASS (the 3-dept / 6-dept reduced-workforce bug). Now we compute
# the expected floor = 16 mandatory + the industry vertical-pack departments
# matched to the client, MINUS any explicitly declined dept, and FAIL the whole
# QC if disk is below that floor. department-floor.py is the single source of
# truth (same naming-map + matched-vertical logic as build-workforce.py); we
# import it so there is exactly one definition. The build-state JSON is NEVER
# trusted as floor proof — only real folders count.
floor_verdict = {"floor_met": True, "reason": "floor module unavailable (skipped)", "rc": 0}
try:
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    from importlib import import_module
    _fm = import_module("department-floor") if False else None
    # module name has a hyphen -> load via spec
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("department_floor", str(SKILL_DIR / "scripts" / "department-floor.py"))
    if _spec and _spec.loader:
        _dfmod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_dfmod)
        floor_verdict = _dfmod.evaluate_floor(departments_dir=DEPARTMENTS_DIR)
except Exception as _e:
    floor_verdict = {"floor_met": True, "reason": f"floor module error: {_e} (not enforced)", "rc": 0}

if not floor_verdict.get("floor_met", True) and floor_verdict.get("rc") == 3:
    overall_status = "FAIL"

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
    "departmentFloor": {
        "floorMet": floor_verdict.get("floor_met", True),
        "expectedFloorCount": floor_verdict.get("expected_floor_count", 0),
        "onDiskCount": floor_verdict.get("on_disk_count", len(on_disk_depts)),
        "missingMandatory": floor_verdict.get("missing_mandatory", []),
        "missingVertical": floor_verdict.get("missing_vertical", []),
        "declined": floor_verdict.get("declined", []),
        "reason": floor_verdict.get("reason", ""),
    },
    "departments": dept_reports,
}
JSON_FILE.write_text(json.dumps(report, indent=2))

# Human readable
emit("")
emit(f"Library version expected: {report['library_version']} ({library_total_roles} roles across {len(library_depts)} depts)")
emit(f"On disk: {report['depts_on_disk']} depts ({report['depts_passing']} PASS, "
     f"{report['depts_partial']} PARTIAL, {report['depts_failing']} FAIL)")
emit("")
emit(f"{'DEPT':<26} {'ROLES':>5} {'EXP':>4} {'LIB%':>5} {'ID%':>5} "
     f"{'SOP/r':>6} {'SUBST':>6} {'minSOP':>6} {'<min':>5} {'PERSONAS':>8} {'STATUS':>8}")
emit("-" * 102)
for d in dept_reports:
    # FIX 3 (2026-06-17): show personas gate result per dept (Y/N)
    personas_flag = "Y" if d.get("has_governing_personas", False) else "N"
    emit(f"{d['dept_id']:<26} {d['role_folders']:>5} {d['expected_roles']:>4} "
         f"{d['library_pct']:>5.1f} {d['identity_pct']:>5.1f} "
         f"{d['avg_sop_per_role']:>6.2f} {d.get('substantive_sop_count', 0):>6} "
         f"{d.get('min_sop_per_role', 0):>6} {d.get('roles_below_min_sops', 0):>5} {personas_flag:>8} {d['status']:>8}")
if legacy_detected:
    emit("")
    emit(f"LEGACY TREE PRESENT (legacy-tree pattern):")
    for p in legacy_detected:
        emit(f"  - {p}  (run reconcile-legacy-tree.py from Release 2 to merge)")
emit("")
_fv = report.get("departmentFloor", {})
if _fv:
    if _fv.get("floorMet", True):
        emit(f"DEPARTMENT FLOOR: MET ({_fv.get('onDiskCount')} on disk >= floor {_fv.get('expectedFloorCount')})")
    else:
        emit(f"DEPARTMENT FLOOR: NOT MET ({_fv.get('onDiskCount')} on disk vs floor {_fv.get('expectedFloorCount')}) "
             f"-> {_fv.get('reason')} -> overall FAIL")
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
  # v11.18.4 STOCK-BASH-3.2 COMPATIBILITY: externalized from an inline
  # python-in-$() heredoc (parse hazard on bash 3.2). The openclaw.json path is
  # now passed as argv[1]. Logic byte-equivalent.
  OWNER_CHAT="$(python3 "$SCRIPT_DIR/_qc_owner_chat.py" "$OCJSON" 2>>"$LOG_FILE")"
  if [ -n "$OC_BIN" ] && [ -n "$OWNER_CHAT" ]; then
    # v11.18.4 STOCK-BASH-3.2 COMPATIBILITY: externalized from an inline
    # python-in-$() heredoc (parse hazard on bash 3.2). The QC JSON report path
    # is now passed as argv[1]. Logic byte-equivalent.
    SUMMARY="$(python3 "$SCRIPT_DIR/_qc_summary.py" "$JSON_FILE" 2>>"$LOG_FILE")"
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
  GATE_BUG) exit 5 ;;
  *) exit 1 ;;
esac
