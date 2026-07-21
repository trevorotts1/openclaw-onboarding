#!/usr/bin/env python3
"""
p207-general-task-catchall-probe.py — P2-07 (c) steps 1 + 3: per-box
`general-task` catch-all presence probe + routing-doctrine confirmation.

SHIPS IN P6-01 (built and QC'd now; run against live fleet boxes only in the
final rollout phase per meta-rule 2.1/2.7 — no canary, evidence-backed QC now,
post-deploy per-box validation in the real rollout).

WHAT THIS CLOSES
-----------------
P2-07 (c) step 2 (mc_board.py never silently drops an unrecognized
department_slug — it re-routes to `general-task`, annotated) already shipped
at v19.52.0 (commit a7a14d54). What that step does NOT prove is that
`general-task` itself is actually PRESENT and WIRED on a given live box — the
re-route target existing is the whole safety net's precondition. This probe
closes the remaining two checks named in P2-07 (c):

  1. `general-task` exists as a workspace/department row in mission-control.db
     AND has a matching runtime entry in openclaw.json's agents.list[] — reusing
     the SAME 6-variant resolution 32-command-center-setup's
     guard-department-runtime-parity.py already uses (imported directly, never
     re-implemented, so this probe can never drift from that guard's logic).
     Missing → per spec: "the P2-06 re-materialization covers it" (this probe
     names the gap; remediation is P2-06's materialize-missing-departments.py,
     not duplicated here).
  2. The routing doctrine text (the CEO_ROUTING_NO_LOOPHOLES marker + the
     "route unknown department to general-task" rule apply-routing-fix.sh
     stamps) is present in the RESOLVED AGENTS.md — resolved via
     shared-utils/resolve_injected_core_files.py's 3-step injected-workspace
     priority, the SAME resolver the gateway itself uses, never a guessed path.

ON THE "LLM READ, NOT GREP" INSTRUCTION (meta-rule 2.4)
--------------------------------------------------------
Meta-rule 2.4 forbids grep deciding whether content is correct, complete, or
present-IN-MEANING. What this script's doctrine check does is narrower: it
confirms the presence of an EXACT, KNOWN, byte-stamped literal that
apply-routing-fix.sh writes verbatim (the same class of check p208's
skill-version.txt string-equality comparison already performs, not a semantic
judgment about content quality). That is a deterministic presence check on a
known constant, not "does this file mean X" — safe for scripted automation.
This script therefore emits the MATCHED/MISSING excerpt structurally in its
JSON report (never a bare pass/fail with no evidence) so that the actual
[Haiku 4.5] LLM read the spec calls for — done when a human/agent CONSUMES
this probe's output during the P6-01 fleet run, per the model tiering in
meta-rule 2.2 ("Haiku ... per-box probe result collection") — has the exact
quoted text to confirm in meaning, not just in bytes.

USAGE
  p207-general-task-catchall-probe.py [--json] [--box <label>]
      [--db PATH] [--config PATH] [--oc-root DIR]
      [--agents-md PATH] [--agent-id ID]

EXIT CODES
  0  ARMED       (both checks pass)
  1  DEGRADED    (one or both checks failed)
  2  UNRESOLVABLE (openclaw.json missing/unreadable while a general-task
                   workspace row exists — cannot verify runtime parity;
                   mirrors guard-department-runtime-parity.py's own EX_CONFIG_UNREADABLE)
================================================================================
"""
import argparse
import importlib.util as _ilu
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SHARED_UTILS = REPO_ROOT / "shared-utils"
GUARD_SCRIPT = REPO_ROOT / "32-command-center-setup" / "scripts" / "guard-department-runtime-parity.py"

GENERAL_TASK_SLUG = "general-task"

# The exact literal apply-routing-fix.sh stamps into the CEO_ROUTING_NO_LOOPHOLES
# block (both the V2 heredoc row and the compact no-ROLE_DISCIPLINE-anchor
# fallback). A box carrying either counts as the doctrine being present.
_DOCTRINE_RULE_TEXT = 'department_slug: "general-task"'


def _load_module(mod_name, path):
    spec = _ilu.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {path}")
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def _hostname():
    try:
        return socket.gethostname().split(".")[0]
    except OSError:
        return "unknown"


# ---------------------------------------------------------------------------
# Check 1 — general-task workspace row + runtime parity
# ---------------------------------------------------------------------------

def check_general_task_runtime(db_path, config_path, oc_root):
    """
    Returns a dict:
      {
        "workspace_row_present": bool,
        "runtime_matched": bool | None,   # None when there was no row to check
        "variants_tried": [...],
        "note": str,
        "rc": 0 | 1 | 2,
      }
    """
    if not GUARD_SCRIPT.is_file():
        return {
            "workspace_row_present": False,
            "runtime_matched": None,
            "variants_tried": [],
            "note": f"guard-department-runtime-parity.py not found at {GUARD_SCRIPT} "
                    f"(skill 32 not installed on this box)",
            "rc": 2,
        }

    guard = _load_module("guard_department_runtime_parity__p207probe", GUARD_SCRIPT)

    resolved_db = db_path or guard._resolve_db_path(None)
    resolved_config = config_path or guard._resolve_config_path(None, oc_root)

    # load_departments returns a 4-tuple: the 4th element lists the workspaces
    # rows that are NOT departments (the structural 'default' FK-DEFAULT target
    # and soft-archived rows) with the reason each was excluded. This probe only
    # looks for the general-task row, which is never one of those, so the list is
    # bound and ignored rather than dropped silently.
    found_db, departments, db_note, _excluded = guard.load_departments(resolved_db)
    if not found_db:
        return {
            "workspace_row_present": False,
            "runtime_matched": None,
            "variants_tried": [],
            "note": db_note or "mission-control.db not found",
            "rc": 1,
        }

    gt_row = None
    for d in departments:
        if guard.canonical_dept_slug(d.get("slug") or d.get("name") or "") == GENERAL_TASK_SLUG:
            gt_row = d
            break

    if gt_row is None:
        return {
            "workspace_row_present": False,
            "runtime_matched": None,
            "variants_tried": [],
            "note": "no workspace row with canonical slug 'general-task' found in "
                    "mission-control.db -- box predates floor materialization or hit "
                    "the wipe; the P2-06 re-materialization (materialize-missing-departments.py) "
                    "covers closing this gap, not this probe",
            "rc": 1,
        }

    ok, agent_ids, cfg_err = guard.load_agent_ids(resolved_config)
    if not ok:
        return {
            "workspace_row_present": True,
            "runtime_matched": None,
            "variants_tried": [],
            "note": f"general-task workspace row IS present but openclaw.json could not "
                    f"be read ({cfg_err}) -- cannot verify runtime parity",
            "rc": 2,
        }

    agent_rows = gt_row["agents"] or [{"name": None, "role": None}]
    matched = False
    variants_tried = []
    for a in agent_rows:
        variants = guard.candidate_variants(gt_row["slug"], a.get("name"), a.get("role"))
        variants_tried = variants
        if any(v in agent_ids for v in variants):
            matched = True
            break

    if matched:
        return {
            "workspace_row_present": True,
            "runtime_matched": True,
            "variants_tried": variants_tried,
            "note": "general-task has both a workspace row and a matching "
                    "openclaw.json agents.list[] runtime entry",
            "rc": 0,
        }

    return {
        "workspace_row_present": True,
        "runtime_matched": False,
        "variants_tried": variants_tried,
        "note": "general-task has a workspace row but NO matching runtime entry in "
                "agents.list[] under any of the 6 resolveSpecialistSessionKey() slug "
                "variants (no_specialist_runtime class) -- tasks re-routed to "
                "general-task by mc_board.py would land on a board column with no "
                "agent behind it",
        "rc": 1,
    }


# ---------------------------------------------------------------------------
# Check 2 — routing doctrine text present in the RESOLVED AGENTS.md
# ---------------------------------------------------------------------------

def check_routing_doctrine(agents_md_override, agent_id):
    """
    Returns:
      {
        "agents_md_path": str,
        "resolved_from": str,
        "marker_present": bool,
        "rule_text_present": bool,
        "excerpt": str,          # the matched line(s), for the human/Haiku LLM read
        "note": str,
        "rc": 0 | 1,
      }
    """
    if agents_md_override:
        agents_md_path = Path(agents_md_override)
        resolved_from = "explicit --agents-md override"
    else:
        sys.path.insert(0, str(SHARED_UTILS))
        try:
            from resolve_injected_core_files import resolve_injected_core_files  # type: ignore
        except ImportError as exc:
            return {
                "agents_md_path": None,
                "resolved_from": None,
                "marker_present": False,
                "rule_text_present": False,
                "excerpt": "",
                "note": f"could not import resolve_injected_core_files.py: {exc}",
                "rc": 1,
            }
        paths = resolve_injected_core_files(agent_id)
        agents_md_path = paths["agents_md"]
        resolved_from = paths["resolved_from"]

    if not agents_md_path or not Path(agents_md_path).is_file():
        return {
            "agents_md_path": str(agents_md_path) if agents_md_path else None,
            "resolved_from": resolved_from,
            "marker_present": False,
            "rule_text_present": False,
            "excerpt": "",
            "note": f"RESOLVED AGENTS.md not found at {agents_md_path} -- "
                    f"apply-routing-fix.sh may not have run on this box yet",
            "rc": 1,
        }

    text = Path(agents_md_path).read_text(encoding="utf-8", errors="replace")

    marker_present = ("CEO_ROUTING_NO_LOOPHOLES_V1" in text) or ("CEO_ROUTING_NO_LOOPHOLES_V2" in text)
    rule_text_present = _DOCTRINE_RULE_TEXT in text

    excerpt = ""
    if rule_text_present:
        idx = text.index(_DOCTRINE_RULE_TEXT)
        start = max(0, idx - 80)
        end = min(len(text), idx + len(_DOCTRINE_RULE_TEXT) + 20)
        excerpt = text[start:end].strip()

    both_present = marker_present and rule_text_present
    if both_present:
        note = "CEO_ROUTING_NO_LOOPHOLES marker + the general-task routing rule are both present"
    elif marker_present and not rule_text_present:
        note = "CEO_ROUTING_NO_LOOPHOLES marker present but the general-task rule text is MISSING"
    elif rule_text_present and not marker_present:
        note = "the general-task rule text is present but no CEO_ROUTING_NO_LOOPHOLES marker was found"
    else:
        note = "neither the CEO_ROUTING_NO_LOOPHOLES marker nor the general-task rule text was found"

    return {
        "agents_md_path": str(agents_md_path),
        "resolved_from": resolved_from,
        "marker_present": marker_present,
        "rule_text_present": rule_text_present,
        "excerpt": excerpt,
        "note": note,
        "rc": 0 if both_present else 1,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--box", default=os.environ.get("OPENCLAW_BOX_LABEL") or _hostname())
    ap.add_argument("--db", default=None, help="override mission-control.db path (test isolation)")
    ap.add_argument("--config", default=None, help="override openclaw.json path (test isolation)")
    ap.add_argument("--oc-root", default=None, help="override OC_ROOT for --config auto-detection")
    ap.add_argument("--agents-md", default=None, help="override the RESOLVED AGENTS.md path (test isolation)")
    ap.add_argument("--agent-id", default="main", help="agent id to resolve the injected workspace for (default: main)")
    args = ap.parse_args(argv)

    runtime_check = check_general_task_runtime(args.db, args.config, args.oc_root)
    doctrine_check = check_routing_doctrine(args.agents_md, args.agent_id)

    overall_rc = max(runtime_check["rc"], doctrine_check["rc"])
    overall_armed = overall_rc == 0

    verdict = {
        "box": args.box,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "general_task_runtime": runtime_check,
        "routing_doctrine": doctrine_check,
        "overall_armed": overall_armed,
        "overall_rc": overall_rc,
    }

    _emit(verdict, args.json)
    return overall_rc


def _emit(verdict, as_json):
    if as_json:
        print(json.dumps(verdict, indent=2))
        return
    box = verdict.get("box", "unknown")
    checked_at = verdict.get("checked_at", "")
    print(f"P2-07 general-task catch-all probe — box: {box}  ({checked_at})")

    rt = verdict["general_task_runtime"]
    tag = "[OK]  " if rt["rc"] == 0 else ("[MISS]" if rt["rc"] == 1 else "[ERROR]")
    print(f"  {tag} general-task runtime: {rt['note']}")

    dc = verdict["routing_doctrine"]
    tag = "[OK]  " if dc["rc"] == 0 else "[MISS]"
    print(f"  {tag} routing doctrine ({dc.get('agents_md_path')}): {dc['note']}")
    if dc.get("excerpt"):
        print(f"         excerpt: {dc['excerpt']!r}")

    print(f"  VERDICT: {'ARMED' if verdict['overall_armed'] else 'DEGRADED'}")


if __name__ == "__main__":
    sys.exit(main())
