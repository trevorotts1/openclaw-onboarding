#!/usr/bin/env bash
# qc-workflow-exits.sh (U-2) - machine-enforce tag-driven workflow exit rules.
#
# LEGACY CLASSIFICATION (content only; never mtime): A file is NEW when any
# line matches PHASE_RE. A file is BROKEN when it has NO phase line BUT has a
# bare 'declares' line (strip fences, ln.strip().lower()=='declares') OR a line
# matching MODEL_RE. Otherwise it is LEGACY.
#
# Two layers of enforcement:
#   (A) STATIC WIRING (always checked, CI-relevant): the workflow-exit-rules
#       protocol file, the AGENTS marker, the MEMORY rule, and the JSONL sink seed
#       must all exist in the skill repo. A missing piece is a FAIL.
#   (B) PLAYBOOK CONTENT (checked when a conversation-workflows dir is present):
#       every non-legacy playbook must pass canonical validation; every exit rule
#       must use an action in {end, handoff, route}; route actions require a
#       registered target.
#
# This gate shells out to canonical parser tools/playbook_engine.py (U-16).
# Canonical validation runs once per playbook before per-exit-rule checks.
#
# Exit codes: 0 = pass or migration needed; 1 = a violation or missing wiring;
#             2 = cannot judge. NEEDS-MIGRATION remains exit 0 for fleet updates.
# UNINITIALISED means no playbooks could be verified; it is never a PASS.
# Discovery faults and unresolvable route targets fail closed with verdict FAIL.
#
# STATUS FILE: --status-file PATH writes compact JSON with exactly these keys:
# gate, legacy_needs_migration, new_style_failures, verdict, legacy_files,
# workflows_dir. new_style_failures > 0 means FAIL; otherwise legacy_needs_migration
# > 0 means NEEDS-MIGRATION; otherwise PASS. Exit codes remain unchanged.
# Callers MUST treat missing or unparseable status files as failure, never PASS;
# completion depends on status, not exit code.
#
# Usage:
#   bash scripts/qc-workflow-exits.sh                 # auto-locate workflows via pointer
#   bash scripts/qc-workflow-exits.sh --dir <conversation-workflows>
#   bash scripts/qc-workflow-exits.sh --json

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"

WF_DIR=""
DIR_SUPPLIED=0
JSON_MODE=0
STATUS_FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) WF_DIR="$2"; DIR_SUPPLIED=1; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    --status-file) STATUS_FILE="$2"; shift 2 ;;
    -h|--help) sed -n '1,39p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$ENGINE" ] || ! command -v python3 >/dev/null 2>&1; then
  echo "qc-workflow-exits: canonical engine tools/playbook_engine.py or python3 not available."
  if [ -n "$STATUS_FILE" ] && command -v python3 >/dev/null 2>&1; then
    STATUS_FILE="$STATUS_FILE" python3 - <<'PYSTATUS'
import json, os
try:
    with open(os.environ["STATUS_FILE"], "w", encoding="utf-8") as f:
        f.write(json.dumps({"gate":"qc-workflow-exits","legacy_needs_migration":0,"new_style_failures":1,"verdict":"FAIL","legacy_files":[],"workflows_dir":""}, separators=(",",":")) + "\n")
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

if [ -z "${AGENTS_MD:-}" ]; then
  if [ "$(uname -s)" = "Darwin" ]; then AGENTS_MD="$HOME/clawd/AGENTS.md"; else AGENTS_MD="/data/clawd/AGENTS.md"; fi
fi

export SKILL_ROOT ENGINE WF_DIR WF_ORIGIN WF_FAULT JSON_MODE AGENTS_MD STATUS_FILE

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
AGENTS_MD = os.environ.get("AGENTS_MD", "")

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
legacy = []
if WF_FAULT:
    failures.append(WF_FAULT)

def contains(path, needle):
    p = SKILL_ROOT / path
    try:
        return p.is_file() and needle in p.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        failures.append("%s: unreadable (%s)" % (p, exc.strerror or str(exc)))
        return False

def contains_live_agents(needle):
    if not AGENTS_MD or not os.path.isfile(AGENTS_MD):
        return None
    try:
        return needle in Path(AGENTS_MD).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

if not (SKILL_ROOT / "protocols" / "workflow-exit-rules-protocol.md").is_file():
    failures.append("missing protocols/workflow-exit-rules-protocol.md")
if not contains("scripts/05-update-agents-md.sh", "STEP_1_30_EXIT_RULES"):
    failures.append("SOURCE scripts/05-update-agents-md.sh is missing the STEP_1_30_EXIT_RULES marker text")
_live = contains_live_agents("STEP_1_30_EXIT_RULES")
if _live is None:
    print("  [SKIP] no live AGENTS.md found at %r — cannot verify the box actually received the STEP_1_30_EXIT_RULES marker (set AGENTS_MD to override)" % AGENTS_MD, file=sys.stderr)
elif not _live:
    failures.append("LIVE AGENTS.md (%s) is MISSING the STEP_1_30_EXIT_RULES marker — the pointer-stanza writer (05-update-agents-md.sh) has not run on this box; a shipped-source check alone cannot prove this" % AGENTS_MD)
else:
    print("  [PASS] LIVE AGENTS.md (%s) carries the STEP_1_30_EXIT_RULES marker — 05-update-agents-md.sh has actually run on this box" % AGENTS_MD, file=sys.stderr)
if not contains("references/memory-design-rules.md", "v1.8.0-rules-workflow-exits"):
    failures.append("missing MEMORY Rule 33 (workflow exits) in references/memory-design-rules.md")
if not contains("scripts/25-seed-round3-feature-files.sh", "workflow-exit-events.jsonl"):
    failures.append("missing workflow-exit-events.jsonl seed in scripts/25-seed-round3-feature-files.sh")

RESERVED = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
            "--verification-checklist.md", "--ghl-side.md")

def registry_ids(reg_path):
    ids = set()
    try:
        for line in reg_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("|"):
                cells = [c.strip().strip("`").strip() for c in s.strip("|").split("|")]
                if cells:
                    rid = cells[0]
                    if rid and rid.lower() != "id" and not (set(rid) <= set("-: ")):
                        ids.add(rid)
    except OSError:
        raise
    return ids

playbooks_checked = 0
wf = Path(WF_DIR) if WF_DIR else None
if wf and wf.is_dir() and not WF_FAULT:
    try:
        candidates = sorted(wf.iterdir())
    except OSError as exc:
        failures.append("%s: unreadable (%s)" % (wf, exc.strerror or str(exc)))
        candidates = []
    reg_path = wf / "registry.md"
    reg_ids = None
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
        for idx, rule in enumerate(parsed["exit_rules"], start=1):
            label = "%s exit rule %d ('%s')" % (f.name, idx, rule.get("tag") or "?")
            action = rule.get("action")
            if action not in engine.EXIT_ACTIONS:
                failures.append("%s action '%s' is not one of end/handoff/route" % (label, action))
                continue
            if action == "route":
                tgt = rule.get("target")
                if not tgt:
                    failures.append("%s action route requires a target playbook id" % label)
                    continue
                if not reg_path.is_file():
                    failures.append("route target '%s' cannot be resolved: registry.md is absent from %s" % (tgt, wf))
                    continue
                if reg_ids is None:
                    try:
                        reg_ids = registry_ids(reg_path)
                    except OSError as exc:
                        failures.append("registry.md is unreadable: %s (%s)" % (reg_path, exc.strerror or str(exc)))
                        continue
                if not reg_ids:
                    failures.append("registry.md at %s is malformed: no parseable id rows; cannot resolve route target '%s'" % (reg_path, tgt))
                elif tgt not in reg_ids:
                    failures.append("%s routes to target '%s' which is absent from registry.md" % (label, tgt))

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
    status = {"gate":"qc-workflow-exits","legacy_needs_migration":len(legacy) if verdict != "UNINITIALISED" else 0,"new_style_failures":len(failures),"verdict":verdict,"legacy_files":sorted(Path(n).name for n in legacy) if verdict != "UNINITIALISED" else [],"workflows_dir":resolved_wf}
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            f.write(json.dumps(status, separators=(",",":")) + "\n")
    except OSError:
        pass

if JSON_MODE:
    print(json.dumps({
        "gate": "qc-workflow-exits",
        "verdict": verdict,
        "discovery": DISCOVERY,
        "playbooks_checked": playbooks_checked,
        "workflows_dir": WF_DIR or None,
        "failures": failures,
        "legacy": legacy,
        "needs_migration": len(legacy),
    }, indent=2))
else:
    print("=== qc-workflow-exits: tag-driven workflow exits (U-2) ===")
    print("skill root: %s" % SKILL_ROOT)
    print("workflows dir: %s" % (WF_DIR or "<none - static wiring only>"))
    print("playbooks checked: %d" % playbooks_checked)
    for name in legacy:
        print("[NEEDS-MIGRATION] %s — legacy playbook (no '### Phase N', no declares, no model-tier:); NOT a pass. Fix: %s" % (name, migration_command))
    print("legacy playbooks NEEDS-MIGRATION: %d" % len(legacy))
    print("")
    if failures:
        for msg in failures:
            print("  [FAIL] %s" % msg)
        print("")
        print("RESULT: FAIL - %d workflow-exit violation(s)." % len(failures))
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
        print("RESULT: PASS - exit rules wired and every checked rule has a valid action and resolvable route target.")

sys.exit(1 if failures else (2 if DISCOVERY == "UNINITIALISED" else 0))
PYEOF
