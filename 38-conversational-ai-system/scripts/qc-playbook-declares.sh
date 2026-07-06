#!/usr/bin/env bash
# qc-playbook-declares.sh (U-9 + U-12) - machine-enforce the playbook declares block.
#
# Mirrors CloseBot's removed-mention error in markdown form. Two layers:
#   (A) STATIC WIRING (always checked, CI-relevant): the Section E.7 declares block
#       must be documented in protocols/conversation-workflows-protocol.md. A missing
#       piece is a FAIL.
#   (B) PLAYBOOK CONTENT (checked when a conversation-workflows dir is present):
#       for every playbook that carries a declares block, cross-validate
#         U-9  tools-used   -> must appear in at least one phase tools line
#         U-9  exits-used   -> must appear in the Exit rules block
#         U-9  fields-used  -> every ZHC_ field must exist in crm-field-mappings.md
#         U-12 calendars    -> every calendar id must exist in the caf calendars export
#       A playbook that predates this update and carries NO declares block gets a
#       WARN (legacy), not a FAIL. A declared reference that dangles is a FAIL.
#
# This gate does NOT parse playbook markdown itself. It shells out to the canonical
# parser tools/playbook_engine.py (U-16) and applies the declares pass/fail policy.
#
# Exit codes: 0 = pass (may carry warnings); 1 = a declares violation or missing
#             wiring; 2 = the engine is missing / python3 unavailable (cannot judge).
#
# Usage:
#   bash scripts/qc-playbook-declares.sh                       # auto-locate via pointer
#   bash scripts/qc-playbook-declares.sh --dir <conversation-workflows>
#   bash scripts/qc-playbook-declares.sh --dir D --calendars-export cal.json --crm-fields crm.md
#   bash scripts/qc-playbook-declares.sh --json

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"

WF_DIR=""
JSON_MODE=0
CAL_EXPORT="${CAF_CALENDARS_EXPORT:-}"
CRM_FIELDS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) WF_DIR="$2"; shift 2 ;;
    --calendars-export) CAL_EXPORT="$2"; shift 2 ;;
    --crm-fields) CRM_FIELDS="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,32p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$ENGINE" ] || ! command -v python3 >/dev/null 2>&1; then
  echo "qc-playbook-declares: canonical engine tools/playbook_engine.py or python3 not available."
  exit 2
fi

# Auto-locate the workflows dir (and its master-files parent) via the pointer.
if [ -z "$WF_DIR" ]; then
  POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
  if [ -f "$POINTER" ]; then
    MFD="$(cat "$POINTER")"; MFD="${MFD%$'\n'}"
    [ -n "$MFD" ] && WF_DIR="$MFD/conversation-workflows"
  fi
fi

# Derive the master-files dir from the workflows dir for crm/calendars auto-locate.
MFD_FROM_WF=""
[ -n "$WF_DIR" ] && MFD_FROM_WF="$(dirname "$WF_DIR")"

# Auto-locate crm-field-mappings.md when not overridden.
if [ -z "$CRM_FIELDS" ] && [ -n "$MFD_FROM_WF" ] && [ -f "$MFD_FROM_WF/crm-field-mappings.md" ]; then
  CRM_FIELDS="$MFD_FROM_WF/crm-field-mappings.md"
fi

# Auto-locate the caf calendars export when not overridden.
if [ -z "$CAL_EXPORT" ]; then
  for c in "$MFD_FROM_WF/.caf-calendars-export.json" "$WF_DIR/.caf-calendars-export.json"; do
    if [ -n "$c" ] && [ -f "$c" ]; then CAL_EXPORT="$c"; break; fi
  done
fi

export SKILL_ROOT ENGINE WF_DIR JSON_MODE CAL_EXPORT CRM_FIELDS

python3 - <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(os.environ["SKILL_ROOT"])
ENGINE = Path(os.environ["ENGINE"])
WF_DIR = os.environ.get("WF_DIR", "")
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"
CAL_EXPORT = os.environ.get("CAL_EXPORT", "")
CRM_FIELDS = os.environ.get("CRM_FIELDS", "")

sys.path.insert(0, str(ENGINE.parent))
import playbook_engine as engine  # canonical parser (U-16)

failures = []
warnings = []
notes = []

RESERVED_COND = {"if", "then", "else", "and", "or", "not"}

def has_declares_block(text):
    """True when the file carries a literal bare 'declares' line (fences stripped)."""
    for ln in engine._strip_fence(text.splitlines()):
        if ln.strip().lower() == "declares":
            return True
    return False

def calendar_ids_from_map(entries):
    """Extract candidate calendar ids from a declares.calendars entry list.
    Each entry is '<purpose>: <value>'; the value may be a plain id or a
    conditional 'if <tag> then CAL_X else CAL_Y'. Reserved words and CRM tags
    (ZHC-/ZHC_) are not calendar ids."""
    ids = []
    for entry in entries:
        if ":" not in entry:
            continue
        value = entry.split(":", 1)[1]
        for tok in re.findall(r"[A-Za-z0-9_-]+", value):
            if tok.lower() in RESERVED_COND:
                continue
            if tok.startswith("ZHC-") or tok.startswith("ZHC_"):
                continue
            ids.append(tok)
    # de-dupe, keep order
    seen = set()
    out = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out

def load_known_calendar_ids(path):
    """Parse a caf calendars export into a set of known calendar ids.
    Accepts JSON (list of ids, list of {id}, {calendars:[{id}]}, or any nested
    structure with 'id' keys) or a plain token list."""
    raw = Path(path).read_text(encoding="utf-8", errors="ignore")
    ids = set()
    try:
        data = json.loads(raw)
    except Exception:
        for tok in re.findall(r"[A-Za-z0-9_-]+", raw):
            ids.add(tok)
        return ids

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() == "id" and isinstance(v, (str, int)):
                    ids.add(str(v))
                else:
                    walk(v)
        elif isinstance(obj, list):
            for el in obj:
                if isinstance(el, str):
                    ids.add(el)
                else:
                    walk(el)
    walk(data)
    return ids

# --- (A) Static wiring: the Section E.7 declares block must be documented. -----
proto = SKILL_ROOT / "protocols" / "conversation-workflows-protocol.md"
if not proto.is_file():
    failures.append("missing protocols/conversation-workflows-protocol.md")
else:
    ptext = proto.read_text(encoding="utf-8", errors="ignore")
    if "declares" not in ptext or "E.7" not in ptext:
        failures.append("Section E.7 declares block is not documented in conversation-workflows-protocol.md")

# --- Load cross-file inputs. --------------------------------------------------
crm_fields = None
if CRM_FIELDS and Path(CRM_FIELDS).is_file():
    crm_fields = engine._load_crm_fields(CRM_FIELDS)
else:
    notes.append("crm-field-mappings.md not found - ZHC_ field validation skipped")

known_cal_ids = None
if CAL_EXPORT and Path(CAL_EXPORT).is_file():
    known_cal_ids = load_known_calendar_ids(CAL_EXPORT)
else:
    notes.append("caf calendars export not found - calendar-id validation skipped")

# --- (B) Playbook content checks. --------------------------------------------
RESERVED = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
            "--verification-checklist.md", "--ghl-side.md")

playbooks_checked = 0
declares_seen = 0
wf = Path(WF_DIR) if WF_DIR else None
if wf and wf.is_dir():
    for f in sorted(wf.iterdir()):
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        if f.name == "registry.md" or any(f.name.endswith(s) for s in RESERVED):
            continue
        playbooks_checked += 1
        text = f.read_text(encoding="utf-8", errors="ignore")
        parsed = engine.parse_playbook(text)
        if not has_declares_block(text):
            warnings.append("%s: no declares block (legacy playbook - WARN)" % f.name)
            continue
        declares_seen += 1
        d = parsed["declares"]

        # U-9: tools-used must appear in a phase tools line.
        phase_tools = set()
        for ph in parsed["phases"]:
            if ph.get("tools"):
                phase_tools |= set(ph["tools"])
        for tool in d["tools-used"]:
            if tool not in engine.TOOL_VOCABULARY:
                failures.append("%s: declares tools-used '%s' is out of the tool vocabulary" % (f.name, tool))
            elif tool not in phase_tools:
                failures.append("%s: declares tools-used '%s' does not appear in any phase tools line" % (f.name, tool))

        # U-9: exits-used must appear in an Exit rules tag.
        exit_tags = {r["tag"] for r in parsed["exit_rules"] if r.get("tag")}
        for tag in d["exits-used"]:
            if tag not in exit_tags:
                failures.append("%s: declares exits-used '%s' does not appear in any Exit rules line" % (f.name, tag))

        # U-9: ZHC_ fields-used must exist in crm-field-mappings (when available).
        if crm_fields is not None:
            for field in d["fields-used"]:
                if field.startswith("ZHC_") and field not in crm_fields:
                    failures.append("%s: declares fields-used '%s' is not present in crm-field-mappings.md" % (f.name, field))

        # U-12: calendar ids must exist in the caf calendars export (when available).
        cal_ids = calendar_ids_from_map(d["calendars"])
        if known_cal_ids is not None:
            for cid in cal_ids:
                if cid not in known_cal_ids:
                    failures.append("%s: declares calendars references calendar id '%s' absent from the caf calendars export" % (f.name, cid))

verdict = "PASS" if not failures else "FAIL"

if JSON_MODE:
    print(json.dumps({
        "gate": "qc-playbook-declares",
        "verdict": verdict,
        "playbooks_checked": playbooks_checked,
        "declares_blocks_seen": declares_seen,
        "workflows_dir": WF_DIR or None,
        "calendars_export": CAL_EXPORT or None,
        "crm_fields": CRM_FIELDS or None,
        "failures": failures,
        "warnings": warnings,
        "notes": notes,
    }, indent=2))
else:
    print("=== qc-playbook-declares: machine-readable declares block (U-9 + U-12) ===")
    print("skill root: %s" % SKILL_ROOT)
    print("workflows dir: %s" % (WF_DIR or "<none - static wiring only>"))
    print("playbooks checked: %d (declares blocks: %d)" % (playbooks_checked, declares_seen))
    for nt in notes:
        print("  [note] %s" % nt)
    for w in warnings:
        print("  [WARN] %s" % w)
    print("")
    if failures:
        for msg in failures:
            print("  [FAIL] %s" % msg)
        print("")
        print("RESULT: FAIL - %d declares violation(s)." % len(failures))
    else:
        print("RESULT: PASS - declares block documented and every declared reference resolves.")

sys.exit(1 if failures else 0)
PYEOF
