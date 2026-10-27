#!/usr/bin/env bash
# qc-playbook-declares.sh (U-9 + U-12) - machine-enforce the playbook declares block.
#
# LEGACY CLASSIFICATION (content only; never mtime): A file is NEW when any
# line matches PHASE_RE. A file is BROKEN when it has NO phase line BUT has a
# bare 'declares' line (strip fences, ln.strip().lower()=='declares') OR a line
# matching MODEL_RE. Otherwise it is LEGACY.
#
# Mirrors CloseBot's removed-mention error in markdown form. Two layers:
#   (A) STATIC WIRING (always checked, CI-relevant): Section E.7 declares block
#       must be documented in protocols/conversation-workflows-protocol.md.
#       A missing piece is a FAIL.
#   (B) PLAYBOOK CONTENT (checked when a conversation-workflows dir is present):
#       every non-legacy playbook must pass canonical validation. For playbooks with declares:
#         U-9  tools-used   -> must appear in at least one phase tools line
#         U-9  exits-used   -> must appear in the Exit rules block
#         U-9  fields-used  -> every ZHC_ field must exist in crm-field-mappings.md
#         U-12 calendars    -> every calendar id must exist in the caf calendars export
#         tags-used applies -> every applied tag must exist in the caf tags export
#       A playbook without declares is FAIL when it contains a Phase heading or
#       model-tier line. Legacy playbooks require migration and are not PASS.
#       Missing required exports for declared values are REQUIRES_OPERATOR failures.
#       Skill 44 tools/export_deps.py is the producer for calendar dependency exports.
#
# This gate shells out to canonical parser tools/playbook_engine.py (U-16).
#
# Exit codes: 0 = pass or migration needed; 1 = violation or missing wiring;
#             2 = engine missing / python3 unavailable (cannot judge).
# UNINITIALISED means no playbooks could be verified; it is never a PASS.
# Discovery faults fail closed with verdict FAIL.
#
# STATUS FILE: --status-file PATH writes compact JSON with exactly these keys:
# gate, legacy_needs_migration, new_style_failures, verdict, legacy_files,
# workflows_dir. new_style_failures > 0 means FAIL; otherwise legacy_needs_migration
# > 0 means NEEDS-MIGRATION; otherwise PASS. Exit codes remain unchanged.
# NEEDS-MIGRATION exits 0 for fleet updates. Callers MUST treat missing or
# unparseable status files as failure, never PASS; completion depends on status.
#
# Usage:
#   bash scripts/qc-playbook-declares.sh
#   bash scripts/qc-playbook-declares.sh --dir <conversation-workflows>
#   bash scripts/qc-playbook-declares.sh --dir D --calendars-export cal.json --tags-export tags.json --crm-fields crm.md
#   bash scripts/qc-playbook-declares.sh --json

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"

WF_DIR=""
DIR_SUPPLIED=0
JSON_MODE=0
STATUS_FILE=""
CAL_EXPORT="${CAF_CALENDARS_EXPORT:-}"
TAGS_EXPORT="${CAF_TAGS_EXPORT:-}"
CRM_FIELDS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) WF_DIR="$2"; DIR_SUPPLIED=1; shift 2 ;;
    --calendars-export) CAL_EXPORT="$2"; shift 2 ;;
    --tags-export) TAGS_EXPORT="$2"; shift 2 ;;
    --crm-fields) CRM_FIELDS="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    --status-file) STATUS_FILE="$2"; shift 2 ;;
    -h|--help) sed -n '1,39p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$ENGINE" ] || ! command -v python3 >/dev/null 2>&1; then
  echo "qc-playbook-declares: canonical engine tools/playbook_engine.py or python3 not available."
  if [ -n "$STATUS_FILE" ] && command -v python3 >/dev/null 2>&1; then
    STATUS_FILE="$STATUS_FILE" python3 - <<'PYSTATUS'
import json, os
try:
    with open(os.environ["STATUS_FILE"], "w", encoding="utf-8") as f:
        f.write(json.dumps({"gate":"qc-playbook-declares","legacy_needs_migration":0,"new_style_failures":1,"verdict":"FAIL","legacy_files":[],"workflows_dir":""}, separators=(",",":")) + "\n")
except OSError:
    pass
PYSTATUS
  fi
  exit 2
fi

POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
WF_ORIGIN="none"
WF_FAULT=""
if [ "$DIR_SUPPLIED" -eq 1 ]; then
  WF_ORIGIN="arg"
  if [ ! -d "$WF_DIR" ]; then
    WF_FAULT="explicit --dir path does not exist: $WF_DIR"
  fi
elif [ -f "$POINTER" ]; then
  WF_ORIGIN="pointer"
  if ! MFD="$(cat "$POINTER")"; then
    WF_FAULT="pointer file $POINTER is unreadable"
  else
    MFD="${MFD%$'\n'}"
    MFD="${MFD%$'\r'}"
    if [ -z "$MFD" ]; then
      WF_FAULT="pointer file $POINTER is empty; cannot locate the master files dir"
    elif [ ! -d "$MFD/conversation-workflows" ]; then
      WF_FAULT="pointer file $POINTER points at $MFD/conversation-workflows, which does not exist"
    else
      WF_DIR="$MFD/conversation-workflows"
    fi
  fi
fi
if [ -n "$WF_DIR" ] && [ -d "$WF_DIR" ] && { [ ! -r "$WF_DIR" ] || [ ! -x "$WF_DIR" ]; }; then
  WF_FAULT="workflows dir $WF_DIR is present but unreadable (permission denied)"
fi

MFD_FROM_WF=""
[ -n "$WF_DIR" ] && MFD_FROM_WF="$(dirname "$WF_DIR")"

if [ -z "$CRM_FIELDS" ] && [ -n "$MFD_FROM_WF" ] && [ -f "$MFD_FROM_WF/crm-field-mappings.md" ]; then
  CRM_FIELDS="$MFD_FROM_WF/crm-field-mappings.md"
fi

if [ -z "$CAL_EXPORT" ]; then
  for c in "$MFD_FROM_WF/.caf-calendars-export.json" "$WF_DIR/.caf-calendars-export.json"; do
    if [ -n "$c" ] && [ -f "$c" ]; then CAL_EXPORT="$c"; break; fi
  done
fi

if [ -z "$TAGS_EXPORT" ]; then
  for c in "$MFD_FROM_WF/.caf-tags-export.json" "$WF_DIR/.caf-tags-export.json"; do
    if [ -n "$c" ] && [ -f "$c" ]; then TAGS_EXPORT="$c"; break; fi
  done
fi

export SKILL_ROOT ENGINE WF_DIR WF_ORIGIN WF_FAULT JSON_MODE CAL_EXPORT TAGS_EXPORT CRM_FIELDS MFD_FROM_WF STATUS_FILE

python3 - <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(os.environ["SKILL_ROOT"])
ENGINE = Path(os.environ["ENGINE"])
WF_DIR = os.environ.get("WF_DIR", "")
WF_ORIGIN = os.environ.get("WF_ORIGIN", "none")
WF_FAULT = os.environ.get("WF_FAULT", "")
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"
STATUS_FILE = os.environ.get("STATUS_FILE", "")
CAL_EXPORT = os.environ.get("CAL_EXPORT", "")
TAGS_EXPORT = os.environ.get("TAGS_EXPORT", "")
CRM_FIELDS = os.environ.get("CRM_FIELDS", "")
MFD_FROM_WF = os.environ.get("MFD_FROM_WF", "")

sys.path.insert(0, str(ENGINE.parent))
import playbook_engine as engine

PHASE_RE = re.compile(r'^\s{0,3}#{2,4}\s*Phase\s*\d', re.IGNORECASE)
MODEL_RE = re.compile(r'^\s*\*{0,2}model-tier\*{0,2}\s*:', re.IGNORECASE)

def classify_playbook(text):
    lines = engine._strip_fence(text.splitlines())
    has_phase = any(PHASE_RE.search(line) for line in lines)
    has_declares = any(line.strip().lower() == "declares" for line in lines)
    has_model = any(MODEL_RE.search(line) for line in lines)
    if has_phase:
        return "NEW"
    if has_declares or has_model:
        return "BROKEN"
    return "LEGACY"

failures = []
warnings = []
notes = []
legacy = []
if WF_FAULT:
    failures.append(WF_FAULT)

RESERVED_COND = {"if", "then", "else", "and", "or", "not"}

def has_declares_block(text):
    """True when file carries a literal bare 'declares' line (fences stripped)."""
    for ln in engine._strip_fence(text.splitlines()):
        if ln.strip().lower() == "declares":
            return True
    return False

def has_new_style_marker(text):
    """Detect Phase headings or model-tier declarations."""
    return any(PHASE_RE.search(line) or MODEL_RE.search(line)
               for line in engine._strip_fence(text.splitlines()))

def calendar_ids_from_map(entries):
    """Extract candidate calendar ids from declares.calendars entries."""
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
    seen = set()
    out = []
    for item in ids:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out

def load_known_ids(path):
    """Load IDs from JSON list, list of {id}, nested id keys, or plain token list."""
    raw = Path(path).read_text(encoding="utf-8", errors="ignore")
    ids = set()
    try:
        data = json.loads(raw)
    except Exception:
        ids.update(re.findall(r"[A-Za-z0-9_-]+", raw))
        return ids

    def walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key.lower() == "id" and isinstance(value, (str, int)):
                    ids.add(str(value))
                else:
                    walk(value)
        elif isinstance(obj, list):
            for element in obj:
                if isinstance(element, str):
                    ids.add(element)
                else:
                    walk(element)
    walk(data)
    return ids

proto = SKILL_ROOT / "protocols" / "conversation-workflows-protocol.md"
if not proto.is_file():
    failures.append("missing protocols/conversation-workflows-protocol.md")
else:
    try:
        ptext = proto.read_text(encoding="utf-8", errors="ignore")
        if "declares" not in ptext or "E.7" not in ptext:
            failures.append("Section E.7 declares block is not documented in conversation-workflows-protocol.md")
    except OSError as exc:
        failures.append("%s: unreadable (%s)" % (proto, exc.strerror or str(exc)))

crm_fields = None
if CRM_FIELDS and Path(CRM_FIELDS).is_file():
    try:
        crm_fields = engine._load_crm_fields(CRM_FIELDS)
    except OSError as exc:
        failures.append("%s: unreadable (%s)" % (CRM_FIELDS, exc.strerror or str(exc)))

known_cal_ids = None
if CAL_EXPORT and Path(CAL_EXPORT).is_file():
    try:
        known_cal_ids = load_known_ids(CAL_EXPORT)
    except OSError as exc:
        failures.append("%s: unreadable (%s)" % (CAL_EXPORT, exc.strerror or str(exc)))

known_tag_ids = None
if TAGS_EXPORT and Path(TAGS_EXPORT).is_file():
    try:
        known_tag_ids = load_known_ids(TAGS_EXPORT)
    except OSError as exc:
        failures.append("%s: unreadable (%s)" % (TAGS_EXPORT, exc.strerror or str(exc)))

RESERVED = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
            "--verification-checklist.md", "--ghl-side.md")

playbooks_checked = 0
declares_seen = 0
declares_calendars = False
declares_applied_tags = False
declares_zhc_fields = False

wf = Path(WF_DIR) if WF_DIR else None
if wf and wf.is_dir() and not WF_FAULT:
    try:
        candidates = sorted(wf.iterdir())
    except OSError as exc:
        failures.append("%s: unreadable (%s)" % (wf, exc.strerror or str(exc)))
        candidates = []
    for f in candidates:
        try:
            if not f.is_file() or not f.name.endswith(".md"):
                continue
            if f.name == "registry.md" or any(f.name.endswith(s) for s in RESERVED):
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            failures.append("%s: unreadable (%s)" % (f, exc.strerror or str(exc)))
            continue

        if classify_playbook(text) == "LEGACY":
            legacy.append(f.name)
            continue

        playbooks_checked += 1
        parsed = engine.parse_playbook(text)
        vdef = engine.validate_playbook(parsed)
        if vdef:
            failures.extend("%s: %s" % (f.name, d) for d in vdef)

        if not has_declares_block(text):
            if has_new_style_marker(text):
                failures.append(
                    "%s: no declares block (required: this playbook carries ### Phase blocks or a model-tier: line; legacy WARN is for playbooks with neither)"
                    % f.name
                )
            continue

        declares_seen += 1
        d = parsed["declares"]

        phase_tools = set()
        for ph in parsed["phases"]:
            if ph.get("tools"):
                phase_tools |= set(ph["tools"])
        for tool in d["tools-used"]:
            if tool not in engine.TOOL_VOCABULARY:
                failures.append("%s: declares tools-used '%s' is out of the tool vocabulary" % (f.name, tool))
            elif tool not in phase_tools:
                failures.append("%s: declares tools-used '%s' does not appear in any phase tools line" % (f.name, tool))

        exit_tags = {r["tag"] for r in parsed["exit_rules"] if r.get("tag")}
        for tag in d["exits-used"]:
            if tag not in exit_tags:
                failures.append("%s: declares exits-used '%s' does not appear in any Exit rules line" % (f.name, tag))

        zhc_fields = [field for field in d["fields-used"] if field.startswith("ZHC_")]
        if zhc_fields:
            declares_zhc_fields = True
            if crm_fields is None:
                failures.append(
                    "REQUIRES_OPERATOR: %s: declares ZHC_ fields but %s is missing."
                    % (f.name, CRM_FIELDS or os.path.join(MFD_FROM_WF, "crm-field-mappings.md"))
                )
            else:
                for field in zhc_fields:
                    if field not in crm_fields:
                        failures.append("%s: declares fields-used '%s' is not present in crm-field-mappings.md" % (f.name, field))

        cal_ids = calendar_ids_from_map(d["calendars"])
        if cal_ids:
            declares_calendars = True
            if known_cal_ids is None:
                failures.append(
                    "REQUIRES_OPERATOR: %s: declares calendars but the caf calendars export is missing. Export it to %s (or %s). Produce it with 44-convert-and-flow-operator/tools/export_deps.py."
                    % (
                        f.name,
                        os.path.join(MFD_FROM_WF, ".caf-calendars-export.json"),
                        os.path.join(WF_DIR, ".caf-calendars-export.json"),
                    )
                )
            else:
                for cid in cal_ids:
                    if cid not in known_cal_ids:
                        failures.append("%s: declares calendars references calendar id '%s' absent from the caf calendars export" % (f.name, cid))

        applies_tags = []
        for entry in d["tags-used"]:
            tag, mode = engine.parse_tag_entry(entry)
            if tag is None or mode is None:
                failures.append("%s: declares tags-used entry '%s' is not '<tag> (applies|reads)'" % (f.name, entry))
            elif mode == "applies":
                applies_tags.append(tag)

        if applies_tags:
            declares_applied_tags = True
            if known_tag_ids is None:
                failures.append(
                    "REQUIRES_OPERATOR: %s: declares tags-used (applies) but the caf tags export is missing; cannot verify %s. Export it to %s (or %s). Produce it with 44-convert-and-flow-operator/tools/export_deps.py (caf tags export)."
                    % (
                        f.name,
                        ", ".join(sorted(applies_tags)),
                        os.path.join(MFD_FROM_WF, ".caf-tags-export.json"),
                        os.path.join(WF_DIR, ".caf-tags-export.json"),
                    )
                )
            else:
                for tag in applies_tags:
                    if tag not in known_tag_ids:
                        failures.append("%s: declares tags-used applies tag '%s' absent from the caf tags export" % (f.name, tag))

if not declares_calendars:
    notes.append("no checked playbook declares calendar ids")
if not declares_applied_tags:
    notes.append("no checked playbook declares tags-used entries with mode applies")
if not declares_zhc_fields:
    notes.append("no checked playbook declares ZHC_ fields")

if WF_FAULT:
    DISCOVERY = "FAULT"
elif WF_ORIGIN == "none" or not wf or not wf.is_dir():
    DISCOVERY = "UNINITIALISED"
elif playbooks_checked == 0 and not legacy and not failures:
    DISCOVERY = "UNINITIALISED"
else:
    DISCOVERY = "OK"

resolved_wf = str(Path(WF_DIR).resolve()) if WF_DIR else ""
migration_command = "bash scripts/33-migrate-legacy-playbooks.sh %s --write" % (resolved_wf or "<ABSOLUTE_WORKFLOWS_DIR>")
verdict = "FAIL" if failures else ("UNINITIALISED" if DISCOVERY == "UNINITIALISED" else ("NEEDS-MIGRATION" if legacy else "PASS"))
if STATUS_FILE:
    status = {"gate":"qc-playbook-declares","legacy_needs_migration":len(legacy) if verdict != "UNINITIALISED" else 0,"new_style_failures":len(failures),"verdict":verdict,"legacy_files":sorted(Path(n).name for n in legacy) if verdict != "UNINITIALISED" else [],"workflows_dir":resolved_wf}
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            f.write(json.dumps(status, separators=(",",":")) + "\n")
    except OSError:
        pass

if JSON_MODE:
    print(json.dumps({
        "gate": "qc-playbook-declares",
        "verdict": verdict,
        "discovery": DISCOVERY,
        "playbooks_checked": playbooks_checked,
        "declares_blocks_seen": declares_seen,
        "workflows_dir": WF_DIR or None,
        "calendars_export": CAL_EXPORT or None,
        "tags_export": TAGS_EXPORT or None,
        "crm_fields": CRM_FIELDS or None,
        "failures": failures,
        "warnings": warnings,
        "notes": notes,
        "legacy": legacy,
        "needs_migration": len(legacy),
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
    for name in legacy:
        print("[NEEDS-MIGRATION] %s — legacy playbook (no '### Phase N', no declares, no model-tier:); NOT a pass. Fix: %s" % (name, migration_command))
    print("legacy playbooks NEEDS-MIGRATION: %d" % len(legacy))
    print("")
    if failures:
        for msg in failures:
            print("  [FAIL] %s" % msg)
        print("")
        print("RESULT: FAIL - %d declares violation(s)." % len(failures))
    elif DISCOVERY == "UNINITIALISED":
        if WF_ORIGIN == "none":
            print("discovery cause: absent pointer file at %s" % (Path.home() / ".openclaw" / ".skill-38-master-files-dir"))
        elif wf and wf.is_dir():
            print("discovery cause: directory %s contains no candidate playbooks" % wf)
        else:
            print("discovery cause: absent directory %s" % (WF_DIR or "<unset>"))
        print("RESULT: UNINITIALISED - 0 playbooks examined; nothing was verified on this box; this is NOT a PASS.")
    elif legacy:
        print("RESULT: NEEDS-MIGRATION - %d legacy playbook(s) need migration; nothing else failed. They are not PASS." % len(legacy))
    else:
        print("RESULT: PASS - declares block documented and every declared reference resolves.")

sys.exit(1 if failures else (2 if DISCOVERY == "UNINITIALISED" else 0))
PYEOF
