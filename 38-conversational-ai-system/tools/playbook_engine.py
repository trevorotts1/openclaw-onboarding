#!/usr/bin/env python3
"""playbook_engine.py - the canonical parser for Skill 38 Layer 2 conversation
workflow playbooks (U-16).

One Python module is the single source of truth for reading and validating
Layer 2 playbooks, replacing per-gate regex parsing. Python 3 standard library
only, no pip installs.

Subcommands:
  parse <playbook.md>
      Emit JSON: header (persona, model-tier), declares (tools-used,
      exits-used, fields-used, calendars, pipeline, stage-map), phases (name,
      tools line, skip-if-field-filled, max-attempts, gate-if-not-met), exit
      rules, win action, escalation branch.

  validate <playbook.md> [--crm-fields <path>] [--registry <path>]
      Full grammar check plus the U-9 cross-validations. Exit 0 clean, exit 1
      with a numbered defect list. The engine only parses and validates; each
      consuming gate keeps its own pass/fail policy.

  hash <playbook.md>
      The U-11 structure hash: stable across copy edits, changes on structural
      edits (phases, tools, exits, win action, declares structure).

  mermaid <playbook.md>
      Emit the diagram.mmd content per the U-11 mapping rules.

  resolve --log <conversation-log.md> [--playbook <p.md> | --workflows-dir <d>]
      Read the U-4 header lines and print active_workflow, active_phase, and
      that phase's enabled tools, the exact lookup the runtime brain and tests
      perform.

OPERATOR-ONLY SURFACE: this engine parses operator-authored playbook files. It
never reads customer message text and nothing a customer types can change a
tool grant, an exit rule, a calendar, a stage, or a persona.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Vocabulary and grammar constants (single source of truth, U-1 / U-2 / U-10).
# ---------------------------------------------------------------------------

# The six CloseBot-parity gated tools.
CORE_TOOLS = (
    "book_appointment",
    "check_availability",
    "cancel_reschedule",
    "update_tags",
    "update_contact",
    "reference_documents",
)

# Additional gateable tools from Skill 38's existing allow-list.
EXTENDED_TOOLS = (
    "send_invoice",
    "create_discount_code",
    "crm_field_write",
    "webhook_chain",
    "escalate_to_human",
)

TOOL_VOCABULARY = frozenset(CORE_TOOLS + EXTENDED_TOOLS)

# escalate_to_human is ALWAYS granted and can never be gated off.
ALWAYS_GRANTED = frozenset({"escalate_to_human"})

# Global tools: active in every phase unless a phase explicitly disables them.
GLOBAL_TOOLS = frozenset({"reference_documents"})

# Default enabled set when a phase carries no tools line (the safe minimum).
SAFE_MINIMUM = frozenset({"reference_documents", "update_tags"})

# U-2 exit-rule actions.
EXIT_ACTIONS = frozenset({"end", "handoff", "route"})

# U-10 per-workflow model tier enum.
MODEL_TIERS = frozenset({"realtime-light", "realtime-standard", "reasoning-max"})
DEFAULT_MODEL_TIER = "realtime-standard"


# ---------------------------------------------------------------------------
# Small helpers.
# ---------------------------------------------------------------------------

def _split_list(value):
    """Split a comma-separated value into a clean list of tokens."""
    if value is None:
        return []
    return [t.strip() for t in value.split(",") if t.strip()]


def _strip_fence(lines):
    """Drop markdown code-fence lines so a template shown inside a fenced block
    parses identically to a live on-disk playbook."""
    out = []
    for ln in lines:
        if ln.lstrip().startswith("```"):
            continue
        out.append(ln)
    return out


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
# The em dash (U+2014) is written as an escape so this source file carries zero
# literal em dash characters (operator formatting law) while the parser still
# matches em-dash-separated phase headings in real on-disk playbooks.
_PHASE_RE = re.compile(
    "^\\s{0,3}#{2,4}\\s*Phase\\s*(\\d+)\\s*[-:\\u2014]?\\s*(.*?)\\s*$",
    re.IGNORECASE,
)


def _is_heading(line):
    return bool(_HEADING_RE.match(line))


def _kv(line):
    """Parse a 'key: value' line. Return (key_lower, value) or (None, None).
    Tolerates leading list markers and bold markdown around the key."""
    m = re.match(r"^\s*(?:[-*]\s+)?\*{0,2}([A-Za-z][A-Za-z0-9 _-]*?)\*{0,2}\s*:\s*(.*)$", line)
    if not m:
        return None, None
    return m.group(1).strip().lower(), m.group(2).strip()


# ---------------------------------------------------------------------------
# Parser.
# ---------------------------------------------------------------------------

def parse_playbook(text):
    """Parse a Layer 2 playbook markdown string into the canonical dict."""
    raw_lines = text.splitlines()
    lines = _strip_fence(raw_lines)

    result = {
        "header": {"persona": None, "model_tier": None},
        "declares": {
            "tools-used": [],
            "exits-used": [],
            "fields-used": [],
            "calendars": [],
            "pipeline": None,
            "stage-map": [],
        },
        "phases": [],
        "exit_rules": [],
        "win_action": None,
        "escalation": None,
    }

    n = len(lines)
    i = 0

    # --- Header lines (persona, model-tier). Scan the region before the first
    #     phase heading; these are top-of-file front-matter-style lines.
    for ln in lines:
        if _PHASE_RE.match(ln):
            break
        key, val = _kv(ln)
        if key == "persona" and result["header"]["persona"] is None and val:
            result["header"]["persona"] = val.strip()
        elif key == "model-tier" and result["header"]["model_tier"] is None and val:
            result["header"]["model_tier"] = val.strip()

    # --- Declares block: a line that is exactly 'declares', then key: value
    #     lines until a blank line or a heading.
    while i < n:
        if lines[i].strip().lower() == "declares":
            i += 1
            while i < n:
                cur = lines[i]
                if cur.strip() == "" or _is_heading(cur):
                    break
                key, val = _kv(cur)
                if key in ("tools-used", "exits-used", "fields-used"):
                    result["declares"][key] = _split_list(val)
                elif key == "calendars":
                    result["declares"]["calendars"] = _split_list(val)
                elif key == "pipeline":
                    result["declares"]["pipeline"] = val.strip() or None
                elif key == "stage-map":
                    result["declares"]["stage-map"] = _split_list(val)
                i += 1
            break
        i += 1

    # --- Phases: each '### Phase N - Name' heading opens a block that runs to
    #     the next phase heading or the next '##'/'#' section heading.
    i = 0
    while i < n:
        m = _PHASE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        phase = {
            "number": int(m.group(1)),
            "name": m.group(2).strip(),
            "tools": None,           # None => no explicit tools line (default applies)
            "skip_if_field_filled": None,
            "max_attempts": None,
            "gate_if_not_met": None,
            "gate_closing": None,
            "disable_global": [],
        }
        i += 1
        while i < n:
            cur = lines[i]
            if _PHASE_RE.match(cur):
                break
            # A top-level section heading (## or #) closes the phase block; a
            # deeper heading inside the phase (#### edge) does not.
            hm = _HEADING_RE.match(cur)
            if hm and len(hm.group(0).strip()) <= 3 and not cur.lstrip().startswith("####"):
                # '#', '##', or '###' non-phase heading closes phases only when
                # it is not itself a Phase heading (checked above).
                if cur.lstrip().startswith(("# ", "## ")):
                    break
            key, val = _kv(cur)
            if key == "tools":
                phase["tools"] = _split_list(val)
            elif key == "skip-if-field-filled":
                phase["skip_if_field_filled"] = val.strip() or None
            elif key == "max-attempts":
                phase["max_attempts"] = val.strip() or None
            elif key == "gate-if-not-met":
                # 'gate-if-not-met: <criteria>, closing: <message>'
                closing = None
                criteria = val
                cm = re.search(r",\s*closing\s*:\s*(.*)$", val, re.IGNORECASE)
                if cm:
                    closing = cm.group(1).strip()
                    criteria = val[: cm.start()].strip()
                phase["gate_if_not_met"] = criteria.strip() or None
                phase["gate_closing"] = closing
            elif key == "disable-global":
                phase["disable_global"] = _split_list(val)
            i += 1
        result["phases"].append(phase)

    # --- Exit rules block: a line 'Exit rules' (heading or plain), then
    #     'exit-when-tag: TAG, action: ACTION[, closing: MSG][, target: T]'.
    i = 0
    while i < n:
        bare = lines[i].strip().lstrip("#").strip().lower()
        if bare == "exit rules":
            i += 1
            while i < n:
                cur = lines[i]
                if _is_heading(cur) or _PHASE_RE.match(cur):
                    break
                key, val = _kv(cur)
                if key == "exit-when-tag":
                    rule = _parse_exit_rule(val)
                    if rule is not None:
                        result["exit_rules"].append(rule)
                i += 1
            break
        i += 1

    # --- Win action (from '## On success') and escalation (from '## On
    #     escalation'): capture the first meaningful content line.
    result["win_action"] = _first_content_after(lines, "on success")
    result["escalation"] = _first_content_after(lines, "on escalation")

    return result


def _parse_exit_rule(val):
    """Parse the tail of an 'exit-when-tag:' line into an exit-rule dict.

    Grammar: <tag>, action: <end|handoff|route>[, closing: <msg>][, target: <id>]
    The tag is everything up to the first ', action:'. Returns None if no tag.
    """
    m = re.match(r"^(.*?),\s*action\s*:\s*(.*)$", val, re.IGNORECASE)
    if not m:
        # A tag with no action clause: record the tag, action unknown.
        tag = val.strip()
        if not tag:
            return None
        return {"tag": tag, "action": None, "closing": None, "target": None}
    tag = m.group(1).strip()
    rest = m.group(2).strip()
    action = rest
    closing = None
    target = None
    cm = re.search(r",\s*closing\s*:\s*(.*?)(?:,\s*target\s*:|$)", rest, re.IGNORECASE)
    if cm:
        closing = cm.group(1).strip()
    tm = re.search(r",\s*target\s*:\s*(.*)$", rest, re.IGNORECASE)
    if tm:
        target = tm.group(1).strip()
    # action word is the first token before any comma.
    action = rest.split(",", 1)[0].strip().lower()
    return {
        "tag": tag,
        "action": action or None,
        "closing": closing,
        "target": target,
    }


def _first_content_after(lines, heading_lower):
    """Return the first non-empty, non-placeholder content line that appears
    under a '## <heading>' section, or None."""
    n = len(lines)
    i = 0
    while i < n:
        hm = _HEADING_RE.match(lines[i])
        if hm and lines[i].lstrip("#").strip().lower().startswith(heading_lower):
            i += 1
            while i < n:
                cur = lines[i].strip()
                if _is_heading(lines[i]):
                    return None
                if cur:
                    cleaned = cur.lstrip("-*> ").strip()
                    if cleaned and cleaned not in ("<Action 1>", "<Action 2>"):
                        return cleaned
                i += 1
            return None
        i += 1
    return None


# ---------------------------------------------------------------------------
# Enabled-tool resolution (U-1 gate semantics).
# ---------------------------------------------------------------------------

def resolve_phase_tools(phase):
    """Resolve the enabled tool set for a phase, applying the safe-minimum
    default, the always-granted rule, and the global-tools rule."""
    if phase is None:
        base = set(SAFE_MINIMUM)
        disabled = set()
    else:
        if phase.get("tools") is None:
            base = set(SAFE_MINIMUM)
        else:
            base = set(phase["tools"])
        disabled = set(phase.get("disable_global") or [])
    # Global tools are always on unless the phase explicitly disables them.
    for g in GLOBAL_TOOLS:
        if g not in disabled:
            base.add(g)
    # escalate_to_human is ALWAYS granted and can never be gated off.
    base |= set(ALWAYS_GRANTED)
    return sorted(base)


def _find_phase(parsed, number):
    for ph in parsed["phases"]:
        if ph["number"] == number:
            return ph
    return None


# ---------------------------------------------------------------------------
# Validation (grammar + U-9 cross-validation).
# ---------------------------------------------------------------------------

def validate_playbook(parsed, crm_fields=None, registry_targets=None):
    """Return a list of defect strings (empty => clean)."""
    defects = []

    # Header: model-tier enum.
    mt = parsed["header"]["model_tier"]
    if mt is not None and mt not in MODEL_TIERS:
        defects.append(
            "header model-tier '%s' is not one of: %s"
            % (mt, ", ".join(sorted(MODEL_TIERS)))
        )

    # Phases must exist.
    if not parsed["phases"]:
        defects.append("no phases found (expected at least one '### Phase N - Name' block)")

    # Per-phase tool vocabulary + escalate-never-gated-off.
    for ph in parsed["phases"]:
        label = "Phase %s (%s)" % (ph["number"], ph["name"] or "unnamed")
        if ph.get("tools") is not None:
            for tool in ph["tools"]:
                if tool not in TOOL_VOCABULARY:
                    defects.append(
                        "%s references out-of-vocabulary tool '%s'" % (label, tool)
                    )
        # A phase may never gate off escalate_to_human.
        for g in (ph.get("disable_global") or []):
            if g in ALWAYS_GRANTED:
                defects.append(
                    "%s attempts to disable always-granted tool '%s' (escalate_to_human can never be gated off)"
                    % (label, g)
                )
        # max-attempts, when present, must be a positive integer.
        ma = ph.get("max_attempts")
        if ma is not None:
            if not re.match(r"^\d+$", ma) or int(ma) < 1:
                defects.append("%s max-attempts '%s' must be a positive integer" % (label, ma))

    # Exit rules grammar (U-2).
    seen_route_targets = []
    for idx, rule in enumerate(parsed["exit_rules"], start=1):
        if not rule.get("tag"):
            defects.append("exit rule %d has no tag" % idx)
        action = rule.get("action")
        if action not in EXIT_ACTIONS:
            defects.append(
                "exit rule %d ('%s') action '%s' is not one of: %s"
                % (idx, rule.get("tag"), action, ", ".join(sorted(EXIT_ACTIONS)))
            )
        if action == "route":
            if not rule.get("target"):
                defects.append(
                    "exit rule %d ('%s') action route requires a target playbook id"
                    % (idx, rule.get("tag"))
                )
            else:
                seen_route_targets.append(rule["target"])

    # U-9 cross-validation: declares.tools-used must appear in a phase tools line.
    phase_tool_union = set()
    for ph in parsed["phases"]:
        if ph.get("tools"):
            phase_tool_union |= set(ph["tools"])
    for tool in parsed["declares"]["tools-used"]:
        if tool not in TOOL_VOCABULARY:
            defects.append("declares tools-used references out-of-vocabulary tool '%s'" % tool)
        elif tool not in phase_tool_union:
            defects.append(
                "declares tools-used '%s' does not appear in any phase tools line" % tool
            )

    # U-9 cross-validation: declares.exits-used must appear in an Exit rules tag.
    exit_tags = {r["tag"] for r in parsed["exit_rules"] if r.get("tag")}
    for tag in parsed["declares"]["exits-used"]:
        if tag not in exit_tags:
            defects.append("declares exits-used '%s' does not appear in any Exit rules line" % tag)

    # Optional cross-file: route targets present in a supplied registry list.
    if registry_targets is not None:
        for tgt in seen_route_targets:
            if tgt not in registry_targets:
                defects.append(
                    "exit rule route target '%s' is not present in the registry" % tgt
                )

    # Optional cross-file: ZHC_ fields declared must exist in crm-field-mappings.
    if crm_fields is not None:
        known = set(crm_fields)
        for field in parsed["declares"]["fields-used"]:
            if field.startswith("ZHC_") and field not in known:
                defects.append(
                    "declares fields-used '%s' is not present in crm-field-mappings" % field
                )

    return defects


# ---------------------------------------------------------------------------
# Structure hash (U-11): stable across copy edits, changes on structural edits.
# ---------------------------------------------------------------------------

def structure_hash(parsed):
    """Deterministic sha256 over the STRUCTURE only (not prose/tone/examples)."""
    skeleton = {
        "model_tier": parsed["header"]["model_tier"] or DEFAULT_MODEL_TIER,
        "phases": [
            {
                "number": ph["number"],
                "name": ph["name"],
                "tools": sorted(resolve_phase_tools(ph)),
                "max_attempts": ph["max_attempts"],
                "gate_if_not_met": bool(ph["gate_if_not_met"]),
                "skip_if_field_filled": ph["skip_if_field_filled"],
            }
            for ph in parsed["phases"]
        ],
        "exit_rules": [
            {"tag": r["tag"], "action": r["action"], "target": r["target"]}
            for r in parsed["exit_rules"]
        ],
        "declares": {
            "tools-used": sorted(parsed["declares"]["tools-used"]),
            "exits-used": sorted(parsed["declares"]["exits-used"]),
            "calendars": sorted(parsed["declares"]["calendars"]),
            "pipeline": parsed["declares"]["pipeline"],
            "stage-map": sorted(parsed["declares"]["stage-map"]),
        },
        "win_action": parsed["win_action"],
    }
    blob = json.dumps(skeleton, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Mermaid emitter (U-11 mapping rules).
# ---------------------------------------------------------------------------

def _mermaid_label(text):
    """Sanitize a label for a Mermaid node (no quotes/newlines/brackets)."""
    if not text:
        return ""
    return re.sub(r'["\[\]{}|<>\n]', " ", text).strip()


def to_mermaid(parsed):
    """Emit the diagram.mmd content. Each phase becomes a node labeled with the
    phase name and its tools line; exit rules become dashed edges to an exit
    node; the win action is the terminal node; escalation is a distinct branch."""
    out = ["flowchart TD"]
    out.append('  trigger(["Trigger"])')

    prev = "trigger"
    for ph in parsed["phases"]:
        node = "phase%d" % ph["number"]
        tools = resolve_phase_tools(ph)
        label = "Phase %d: %s" % (ph["number"], _mermaid_label(ph["name"]))
        toolstr = _mermaid_label(", ".join(tools))
        out.append('  %s["%s<br/>tools: %s"]' % (node, label, toolstr))
        out.append("  %s --> %s" % (prev, node))
        prev = node

    # Win action terminal node.
    win = _mermaid_label(parsed["win_action"]) or "Win action"
    out.append('  win(["%s"])' % win)
    out.append("  %s --> win" % prev)

    # Exit rules: dashed edges from every phase to a shared exit node.
    if parsed["exit_rules"]:
        out.append('  exit{{"Workflow exit"}}')
        for rule in parsed["exit_rules"]:
            edge_label = _mermaid_label(
                "%s (%s)" % (rule.get("tag") or "tag", rule.get("action") or "exit")
            )
            for ph in parsed["phases"]:
                out.append('  phase%d -.->|%s| exit' % (ph["number"], edge_label))
            if rule.get("action") == "route" and rule.get("target"):
                out.append('  exit -.->|route| %s(["%s"])'
                           % ("route_" + re.sub(r"[^A-Za-z0-9_]", "_", rule["target"]),
                              _mermaid_label(rule["target"])))

    # Escalation: a distinct branch.
    esc = _mermaid_label(parsed["escalation"]) or "Escalate to human"
    out.append('  escalation["%s"]' % esc)
    for ph in parsed["phases"]:
        out.append("  phase%d -.-> escalation" % ph["number"])

    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Resolve (U-4 header lookup).
# ---------------------------------------------------------------------------

_HEADER_LINE_RE = {
    "active_workflow": re.compile(r"^\s*active_workflow\s*:\s*(.+?)\s*$", re.IGNORECASE),
    "active_phase": re.compile(r"^\s*active_phase\s*:\s*(.+?)\s*$", re.IGNORECASE),
    "phase_attempts": re.compile(r"^\s*phase_attempts\s*:\s*(.+?)\s*$", re.IGNORECASE),
}


def read_log_header(text):
    """Read the U-4 machine-readable header lines from a conversation log."""
    header = {"active_workflow": None, "active_phase": None, "phase_attempts": None}
    for ln in text.splitlines():
        for key, rx in _HEADER_LINE_RE.items():
            if header[key] is None:
                m = rx.match(ln)
                if m:
                    header[key] = m.group(1).strip()
        if all(v is not None for v in header.values()):
            break
    return header


def resolve_from_log(log_text, playbook_text=None):
    """Return {active_workflow, active_phase, enabled_tools} for the runtime
    brain and tests. enabled_tools is resolved from the playbook when supplied."""
    header = read_log_header(log_text)
    active_workflow = header["active_workflow"]
    active_phase_raw = header["active_phase"]
    active_phase = None
    if active_phase_raw is not None and re.match(r"^\d+$", active_phase_raw.strip()):
        active_phase = int(active_phase_raw.strip())

    enabled_tools = None
    if playbook_text is not None:
        parsed = parse_playbook(playbook_text)
        phase = _find_phase(parsed, active_phase) if active_phase is not None else None
        enabled_tools = resolve_phase_tools(phase)

    return {
        "active_workflow": active_workflow,
        "active_phase": active_phase,
        "phase_attempts": header["phase_attempts"],
        "enabled_tools": enabled_tools,
    }


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------

def _read(path):
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _load_registry_ids(path):
    """Extract registered playbook ids (first table cell / bullet slug) so a
    route target can be checked against the registry."""
    ids = set()
    bullet = re.compile(r"^[-*]\s+([a-z0-9][a-z0-9-]*)\s*:")
    for line in _read(path).splitlines():
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip().strip("`").strip() for c in s.strip("|").split("|")]
            if cells:
                rid = cells[0]
                if rid and rid.lower() != "id" and not (set(rid) <= set("-: ")):
                    ids.add(rid)
        else:
            m = bullet.match(s)
            if m:
                ids.add(m.group(1))
    return ids


def _load_crm_fields(path):
    fields = set()
    for line in _read(path).splitlines():
        for m in re.findall(r"ZHC_[A-Za-z0-9_]+", line):
            fields.add(m)
    return fields


def cmd_parse(args):
    parsed = parse_playbook(_read(args.playbook))
    print(json.dumps(parsed, indent=2, ensure_ascii=False))
    return 0


def cmd_validate(args):
    parsed = parse_playbook(_read(args.playbook))
    crm = _load_crm_fields(args.crm_fields) if args.crm_fields else None
    reg = _load_registry_ids(args.registry) if args.registry else None
    defects = validate_playbook(parsed, crm_fields=crm, registry_targets=reg)
    if not defects:
        print("OK: playbook is grammatically valid (%d phase(s), %d exit rule(s))"
              % (len(parsed["phases"]), len(parsed["exit_rules"])))
        return 0
    print("INVALID: %d defect(s)" % len(defects))
    for idx, d in enumerate(defects, start=1):
        print("  %d. %s" % (idx, d))
    return 1


def cmd_hash(args):
    parsed = parse_playbook(_read(args.playbook))
    print(structure_hash(parsed))
    return 0


def cmd_mermaid(args):
    parsed = parse_playbook(_read(args.playbook))
    sys.stdout.write(to_mermaid(parsed))
    return 0


def cmd_resolve(args):
    log_text = _read(args.log)
    playbook_text = None
    if args.playbook:
        playbook_text = _read(args.playbook)
    elif args.workflows_dir:
        header = read_log_header(log_text)
        wf = header["active_workflow"]
        if wf:
            candidate = Path(args.workflows_dir) / ("%s.md" % wf)
            if candidate.is_file():
                playbook_text = candidate.read_text(encoding="utf-8", errors="ignore")
    resolved = resolve_from_log(log_text, playbook_text)
    if args.json:
        print(json.dumps(resolved, indent=2, ensure_ascii=False))
    else:
        print("active_workflow: %s" % (resolved["active_workflow"] or "<none>"))
        print("active_phase: %s" % (resolved["active_phase"]
                                    if resolved["active_phase"] is not None else "<none>"))
        print("phase_attempts: %s" % (resolved["phase_attempts"] or "<none>"))
        if resolved["enabled_tools"] is None:
            print("enabled_tools: <playbook not supplied>")
        else:
            print("enabled_tools: %s" % ", ".join(resolved["enabled_tools"]))
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="playbook_engine.py",
        description="Canonical parser for Skill 38 Layer 2 conversation workflow playbooks (U-16).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("parse", help="parse a playbook to JSON")
    sp.add_argument("playbook")
    sp.set_defaults(func=cmd_parse)

    sv = sub.add_parser("validate", help="grammar + cross-validation, exit 1 on defects")
    sv.add_argument("playbook")
    sv.add_argument("--crm-fields", default=None, help="path to crm-field-mappings.md")
    sv.add_argument("--registry", default=None, help="path to conversation-workflows registry.md")
    sv.set_defaults(func=cmd_validate)

    sh = sub.add_parser("hash", help="print the structure hash")
    sh.add_argument("playbook")
    sh.set_defaults(func=cmd_hash)

    sm = sub.add_parser("mermaid", help="emit diagram.mmd content")
    sm.add_argument("playbook")
    sm.set_defaults(func=cmd_mermaid)

    sr = sub.add_parser("resolve", help="resolve active workflow/phase/tools from a log")
    sr.add_argument("--log", required=True)
    sr.add_argument("--playbook", default=None)
    sr.add_argument("--workflows-dir", default=None)
    sr.add_argument("--json", action="store_true")
    sr.set_defaults(func=cmd_resolve)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
