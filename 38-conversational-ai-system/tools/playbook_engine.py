#!/usr/bin/env python3
"""playbook_engine.py - the canonical parser for Skill 38 Layer 2 conversation
workflow playbooks (U-16).

This module IS the playbook contract: parser, validator, declares block, and structure hash.
It owns any seam/build contract file exchanged by skills 38 and 44; that contract belongs here, NOT in tools/pb_contracts.py.

Python 3 standard library only, no pip installs.

Subcommands:
  parse <playbook.md>
      Emit JSON including header, declares (tools-used, exits-used, fields-used,
      tags-used, calendars, pipeline, stage-map), phases, exit rules, win action,
      escalation, examples, on-success actions, and original text.

  validate <playbook.md> [--crm-fields <path>] [--registry <path>]
      Full grammar check plus cross-validations. Exit 1 on defects.

  lint <playbook.md>
      Check conversational content: objection library, phase examples,
      conversational KPIs, golden transcript, and never-say leakage.

  hash <playbook.md>
      Print versioned U-11 structural SHA-256 hash.

  build-contract <playbook.md> [--out <path>] [--playbook-path <path as recorded>]
      Emit deterministic Skill 44 build-contract JSON.

  mermaid <playbook.md>
      Emit the diagram.mmd content.

  resolve --log <conversation-log.md> [--playbook <p.md> | --workflows-dir <d>]
      Resolve active workflow, phase, and enabled tools.

OPERATOR-ONLY SURFACE: this engine parses operator-authored playbook files.
It never reads customer message text and nothing a customer types can change
a tool grant, an exit rule, a calendar, a stage, or a persona.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


CORE_TOOLS = (
    "book_appointment",
    "check_availability",
    "cancel_reschedule",
    "update_tags",
    "update_contact",
    "reference_documents",
)

EXTENDED_TOOLS = (
    "send_invoice",
    "create_discount_code",
    "crm_field_write",
    "webhook_chain",
    "escalate_to_human",
)

TOOL_VOCABULARY = frozenset(CORE_TOOLS + EXTENDED_TOOLS)
ALWAYS_GRANTED = frozenset({"escalate_to_human"})
GLOBAL_TOOLS = frozenset({"reference_documents"})
SAFE_MINIMUM = frozenset({"reference_documents", "update_tags"})
EXIT_ACTIONS = frozenset({"end", "handoff", "route"})
MODEL_TIERS = frozenset({"realtime-light", "realtime-standard", "reasoning-max"})
DEFAULT_MODEL_TIER = "realtime-standard"


def _split_list(value):
    """Split a comma-separated value into a clean list of tokens."""
    if value is None:
        return []
    return [t.strip() for t in value.split(",") if t.strip()]


def _strip_fence(lines):
    """Drop markdown code-fence lines."""
    return [ln for ln in lines if not ln.lstrip().startswith("```")]


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_PHASE_RE = re.compile(
    "^\\s{0,3}#{2,4}\\s*Phase\\s*(\\d+)\\s*[-:\\u2014]?\\s*(.*?)\\s*$",
    re.IGNORECASE,
)


def _is_heading(line):
    return bool(_HEADING_RE.match(line))


def _kv(line):
    """Parse a key-value line."""
    m = re.match(
        r"^\s*(?:[-*]\s+)?\*{0,2}([A-Za-z][A-Za-z0-9 _-]*?)\*{0,2}\s*:\s*(.*)$",
        line,
    )
    if not m:
        return None, None
    return m.group(1).strip().lower(), m.group(2).strip()


def section_lines(lines, heading_lower):
    """Return raw lines below the first matching heading, up to next heading."""
    for i, line in enumerate(lines):
        if _is_heading(line) and line.lstrip().lstrip("#").strip().lower().startswith(
            heading_lower
        ):
            out = []
            for content in lines[i + 1:]:
                if _is_heading(content):
                    break
                out.append(content)
            return out
    return []


def _section_bounds(lines, heading_lower):
    """Return (start, end) indices for the first matching section, or None."""
    for i, line in enumerate(lines):
        if _is_heading(line) and line.lstrip().lstrip("#").strip().lower().startswith(
            heading_lower
        ):
            end = i + 1
            while end < len(lines) and not _is_heading(lines[end]):
                end += 1
            return i, end
    return None


def _is_placeholder(value):
    value = value.strip()
    return (
        not value
        or bool(re.match(r"^<.*>$", value))
        or value.lower() in {"n/a", "na", "tbd", "todo", "pending"}
    )


def _clean_content_line(line):
    return line.strip().lstrip("-*> ").strip()


def _non_placeholder_lines(lines):
    return [
        line for line in lines
        if not _is_placeholder(_clean_content_line(line))
    ]


def _section_content_lines(lines, heading_lower):
    """Return cleaned, meaningful section lines in document order, or None if absent."""
    bounds = _section_bounds(lines, heading_lower)
    if bounds is None:
        return None
    start, end = bounds
    return [
        cleaned
        for line in lines[start + 1:end]
        if (cleaned := _clean_content_line(line))
        and not _is_placeholder(cleaned)
        and cleaned not in ("<Action 1>", "<Action 2>")
    ]


def parse_tag_entry(entry):
    """Parse '<tag> (applies|reads)' or return (None, None)."""
    match = re.match(r"^(.+?)\s+\((applies|reads)\)$", entry, re.IGNORECASE)
    if not match:
        return None, None
    return match.group(1), match.group(2).lower()


def parse_playbook(text):
    """Parse a Layer 2 playbook markdown string into the canonical dict."""
    lines = _strip_fence(text.splitlines())
    result = {
        "header": {"persona": None, "model_tier": None},
        "declares": {
            "tools-used": [],
            "exits-used": [],
            "fields-used": [],
            "tags-used": [],
            "calendars": [],
            "pipeline": None,
            "stage-map": [],
        },
        "phases": [],
        "exit_rules": [],
        "win_action": None,
        "on_success_actions": [],
        "escalation": None,
        "_raw_text": text,
    }

    n = len(lines)
    i = 0

    for ln in lines:
        if _PHASE_RE.match(ln):
            break
        key, val = _kv(ln)
        if key == "persona" and result["header"]["persona"] is None and val:
            result["header"]["persona"] = val.strip()
        elif key == "model-tier" and result["header"]["model_tier"] is None and val:
            result["header"]["model_tier"] = val.strip()

    while i < n:
        if lines[i].strip().lower() == "declares":
            i += 1
            while i < n:
                cur = lines[i]
                if cur.strip() == "" or _is_heading(cur):
                    break
                key, val = _kv(cur)
                if key in (
                    "tools-used", "exits-used", "fields-used", "tags-used"
                ):
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

    i = 0
    while i < n:
        match = _PHASE_RE.match(lines[i])
        if not match:
            i += 1
            continue
        phase = {
            "number": int(match.group(1)),
            "name": match.group(2).strip(),
            "line": i + 1,
            "tools": None,
            "skip_if_field_filled": None,
            "max_attempts": None,
            "gate_if_not_met": None,
            "gate_closing": None,
            "disable_global": [],
            "examples": [],
        }
        i += 1
        while i < n:
            cur = lines[i]
            if _PHASE_RE.match(cur):
                break
            hm = _HEADING_RE.match(cur)
            if hm and len(hm.group(0).strip()) <= 3 and not cur.lstrip().startswith("####"):
                if cur.lstrip().startswith(("# ", "## ", "### ")):
                    break
            key, val = _kv(cur)
            if key == "tools":
                phase["tools"] = _split_list(val)
            elif key == "example":
                phase["examples"].append(val.strip().strip("'\""))
            elif key == "skip-if-field-filled":
                phase["skip_if_field_filled"] = val.strip() or None
            elif key == "max-attempts":
                phase["max_attempts"] = val.strip() or None
            elif key == "gate-if-not-met":
                closing = None
                criteria = val
                cm = re.search(r",\s*closing\s*:\s*(.*)$", val, re.IGNORECASE)
                if cm:
                    closing = cm.group(1).strip()
                    criteria = val[:cm.start()].strip()
                phase["gate_if_not_met"] = criteria.strip() or None
                phase["gate_closing"] = closing
            elif key == "disable-global":
                phase["disable_global"] = _split_list(val)
            i += 1
        result["phases"].append(phase)

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

    result["win_action"] = _first_content_after(lines, "on success")
    result["escalation"] = _first_content_after(lines, "on escalation")
    for line in section_lines(lines, "on success"):
        cleaned = _clean_content_line(line)
        if cleaned and not _is_placeholder(cleaned) and cleaned not in (
            "<Action 1>", "<Action 2>"
        ):
            result["on_success_actions"].append(cleaned)

    return result


_EXIT_CLAUSE_RE = re.compile(r",\s*(action|closing|target)\s*:\s*", re.IGNORECASE)


def _parse_exit_rule(val):
    """Parse tag and named exit-rule clauses in any order."""
    matches = list(_EXIT_CLAUSE_RE.finditer(val))
    if not matches:
        tag = val.strip()
        if not tag:
            return None
        return {"tag": tag, "action": None, "closing": None, "target": None}

    tag = val[:matches[0].start()].strip()
    segments = {}
    for idx, match in enumerate(matches):
        key = match.group(1).lower()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(val)
        segments.setdefault(key, val[start:end].strip())

    action = segments.get("action")
    if action:
        action = action.split(",", 1)[0].strip().lower()
    return {
        "tag": tag,
        "action": action or None,
        "closing": segments.get("closing") or None,
        "target": segments.get("target") or None,
    }


def _first_content_after(lines, heading_lower):
    """Return the first non-empty, non-placeholder content line in a section."""
    bounds = _section_bounds(lines, heading_lower)
    if bounds is None:
        return None
    start, end = bounds
    for line in lines[start + 1:end]:
        cleaned = _clean_content_line(line)
        if cleaned and cleaned not in ("<Action 1>", "<Action 2>"):
            return cleaned
    return None


def conversation_lint(parsed, text=None):
    """Return conversational content defects in fixed order."""
    if text is None:
        text = parsed.get("_raw_text") or ""
    lines = _strip_fence(text.splitlines())
    defects = []

    objection_lines = section_lines(lines, "objection library")
    table_indices = [
        i for i, line in enumerate(objection_lines)
        if line.strip().startswith("|")
    ]

    def is_separator(line):
        stripped = line.strip()
        return bool(re.match(r"^[|\s:-]+$", stripped) and "-" in stripped)

    separator_indices = {
        i for i in table_indices if is_separator(objection_lines[i])
    }
    header_index = None
    for i in table_indices:
        if i in separator_indices:
            continue
        next_index = i + 1
        if (
            next_index < len(objection_lines)
            and next_index in separator_indices
            and objection_lines[next_index].strip().startswith("|")
        ):
            header_index = i
            break

    objections = 0
    for i in table_indices:
        if i in separator_indices or i == header_index:
            continue
        cells = objection_lines[i].strip().strip("|").split("|")
        if len(cells) < 3:
            continue
        if all(
            not _is_placeholder(cell.strip().strip("`").strip())
            for cell in cells[:3]
        ):
            objections += 1

    if objections < 5:
        defects.append(
            "objection library has %d objection(s), minimum is 5" % objections
        )

    for phase in parsed["phases"]:
        if not any(
            not _is_placeholder(str(example))
            for example in (phase.get("examples") or [])
        ):
            defects.append(
                "Phase %s (%s) has no example: phrasing line"
                % (phase["number"], phase["name"] or "unnamed")
            )

    kpi_lines = section_lines(lines, "conversational kpis")

    def is_separator_row(line):
        return bool(re.match(
            r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$",
            line.strip(),
        ))

    meaningful_kpis = []
    for index, line in enumerate(kpi_lines):
        cleaned = _clean_content_line(line)
        if _is_placeholder(cleaned):
            continue
        if is_separator_row(line):
            continue
        if index + 1 < len(kpi_lines) and is_separator_row(kpi_lines[index + 1]):
            continue
        meaningful_kpis.append(cleaned)

    if not meaningful_kpis:
        defects.append(
            "no conversational KPI declared (expected a ## Conversational KPIs "
            "section with at least one measurable bar)"
        )
    else:
        number_word_re = re.compile(
            r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"eleven|twelve|dozen|half|hundred|thousand|percent)\b",
            re.IGNORECASE,
        )
        for cleaned in meaningful_kpis:
            if not re.search(r"\d", cleaned) and not number_word_re.search(cleaned):
                defects.append(
                    "conversational KPI line has no numeric target: '%s'" % cleaned
                )

    golden_lines = section_lines(lines, "golden transcript")
    good_start = next(
        (i for i, line in enumerate(golden_lines)
         if "good exchange" in line.lower()),
        None,
    )
    if good_start is None:
        golden_block = golden_lines
    else:
        bad_start = next(
            (i for i in range(good_start + 1, len(golden_lines))
             if "bad exchange" in golden_lines[i].lower()),
            len(golden_lines),
        )
        golden_block = golden_lines[good_start + 1:bad_start]

    turn_re = re.compile(
        r"^\s*>?\s*(customer|agent|prospect|user|lead|assistant)\s*:",
        re.IGNORECASE,
    )
    turns = [
        match.group(1).lower()
        for line in golden_block
        if (match := turn_re.match(line))
    ]

    if len(turns) < 4:
        defects.append(
            "no golden transcript (expected a ## Golden transcript section "
            "with a worked good exchange and a bad anti-pattern)"
        )
    elif len(set(turns)) < 2 or any(
        turns[i] == turns[i - 1] for i in range(1, len(turns))
    ):
        defects.append(
            "golden transcript turns do not alternate speakers: %s"
            % ", ".join(turns)
        )

    outcome_re = re.compile(
        r"\b(outcome|booked|confirmation|confirmed|scheduled|resolved|"
        r"completed|closed|next step)\b",
        re.IGNORECASE,
    )
    if not any(outcome_re.search(line) for line in golden_lines):
        defects.append(
            "golden transcript has no stated outcome (expected a confirmation, "
            "booking, resolution, or explicit next-step line)"
        )

    never_bounds = _section_bounds(lines, "never say")
    if never_bounds is not None:
        start, end = never_bounds
        outside_text = "\n".join(lines[:start] + lines[end:]).lower()
        for line in lines[start + 1:end]:
            stripped = line.strip()
            if not stripped or not (stripped.startswith(("- ", "* ", "|"))):
                continue
            phrase = stripped.strip("-*|` ").strip().strip("'\"").strip()
            phrase = phrase.strip("-*|` ").strip().strip("'\"").strip()
            if len(phrase) < 3:
                continue
            if phrase.lower() in outside_text:
                defects.append(
                    "never-say phrase '%s' also appears in the playbook copy" % phrase
                )

    return defects


def resolve_phase_tools(phase):
    """Resolve enabled tools with safe defaults and always-granted tools."""
    if phase is None:
        base = set(SAFE_MINIMUM)
        disabled = set()
    else:
        base = set(SAFE_MINIMUM) if phase.get("tools") is None else set(phase["tools"])
        disabled = set(phase.get("disable_global") or [])
    for tool in GLOBAL_TOOLS:
        if tool not in disabled:
            base.add(tool)
    base |= set(ALWAYS_GRANTED)
    return sorted(base)


def _find_phase(parsed, number):
    for phase in parsed["phases"]:
        if phase["number"] == number:
            return phase
    return None


def validate_playbook(parsed, crm_fields=None, registry_targets=None):
    """Return a list of grammar and cross-validation defects."""
    defects = []
    numbers = [phase["number"] for phase in parsed["phases"]]
    if len(numbers) != len(set(numbers)):
        duplicate_numbers = [
            number for number in dict.fromkeys(numbers)
            if numbers.count(number) > 1
        ]
        clauses = []
        for number in duplicate_numbers:
            occurrences = [
                str(phase.get("line", "?"))
                for phase in parsed["phases"]
                if phase["number"] == number
            ]
            clauses.append("%s (lines %s)" % (number, ", ".join(occurrences)))
        defects.append("duplicate phase numbers: %s" % "; ".join(clauses))
    if numbers != sorted(numbers):
        defects.append(
            "phases are out of order: %s (expected %s)"
            % (", ".join(map(str, numbers)), ", ".join(map(str, sorted(numbers))))
        )

    raw_lines = _strip_fence((parsed.get("_raw_text") or "").splitlines())
    for line_number, line in enumerate(raw_lines, start=1):
        if (
            _is_heading(line)
            and re.search(r"\bphase\b", line, re.IGNORECASE)
            and not _PHASE_RE.match(line)
        ):
            defects.append(
                "malformed phase header at line %d: '%s' "
                "(expected '### Phase N - Name')"
                % (line_number, line.strip())
            )

    mt = parsed["header"]["model_tier"]
    if mt is not None and mt not in MODEL_TIERS:
        defects.append(
            "header model-tier '%s' is not one of: %s"
            % (mt, ", ".join(sorted(MODEL_TIERS)))
        )

    if not parsed["phases"]:
        defects.append("no phases found (expected at least one '### Phase N - Name' block)")

    for phase in parsed["phases"]:
        label = "Phase %s (%s)" % (phase["number"], phase["name"] or "unnamed")
        if phase.get("tools") is not None:
            for tool in phase["tools"]:
                if tool not in TOOL_VOCABULARY:
                    defects.append(
                        "%s references out-of-vocabulary tool '%s'" % (label, tool)
                    )
        for tool in (phase.get("disable_global") or []):
            if tool in ALWAYS_GRANTED:
                defects.append(
                    "%s attempts to disable always-granted tool '%s' "
                    "(escalate_to_human can never be gated off)" % (label, tool)
                )
        attempts = phase.get("max_attempts")
        if attempts is not None:
            if not re.match(r"^\d+$", attempts) or int(attempts) < 1:
                defects.append(
                    "%s max-attempts '%s' must be a positive integer" % (label, attempts)
                )

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

    phase_tool_union = set()
    for phase in parsed["phases"]:
        if phase.get("tools"):
            phase_tool_union |= set(phase["tools"])
    for tool in parsed["declares"]["tools-used"]:
        if tool not in TOOL_VOCABULARY:
            defects.append("declares tools-used references out-of-vocabulary tool '%s'" % tool)
        elif tool not in phase_tool_union:
            defects.append(
                "declares tools-used '%s' does not appear in any phase tools line" % tool
            )

    exit_tags = {rule["tag"] for rule in parsed["exit_rules"] if rule.get("tag")}
    for tag in parsed["declares"]["exits-used"]:
        if tag not in exit_tags:
            defects.append(
                "declares exits-used '%s' does not appear in any Exit rules line" % tag
            )

    for entry in parsed["declares"].get("tags-used", []):
        tag, mode = parse_tag_entry(entry)
        if tag is None or mode is None:
            defects.append(
                "declares tags-used entry '%s' is not '<tag> (applies|reads)'" % entry
            )

    if registry_targets is not None:
        for target in seen_route_targets:
            if target not in registry_targets:
                defects.append(
                    "exit rule route target '%s' is not present in the registry" % target
                )

    if crm_fields is not None:
        known = set(crm_fields)
        for field in parsed["declares"]["fields-used"]:
            if field.startswith("ZHC_") and field not in known:
                defects.append(
                    "declares fields-used '%s' is not present in crm-field-mappings" % field
                )

    return defects


class BuildContractRefused(Exception):
    """Raised when a playbook cannot produce meaningful acceptance checks."""


def structure_hash(parsed):
    """Deterministic sha256 over versioned structural inputs."""
    lines = _strip_fence((parsed.get("_raw_text") or "").splitlines())
    skeleton = {
        "hash_version": 3,
        "model_tier": parsed["header"]["model_tier"] or DEFAULT_MODEL_TIER,
        "phases": [
            {
                "number": phase["number"],
                "name": phase["name"],
                "tools": sorted(resolve_phase_tools(phase)),
                "max_attempts": phase["max_attempts"],
                "gate_if_not_met": bool(phase["gate_if_not_met"]),
                "skip_if_field_filled": phase["skip_if_field_filled"],
            }
            for phase in parsed["phases"]
        ],
        "exit_rules": [
            {"tag": rule["tag"], "action": rule["action"], "target": rule["target"]}
            for rule in parsed["exit_rules"]
        ],
        "declares": {
            "tools-used": sorted(parsed["declares"]["tools-used"]),
            "exits-used": sorted(parsed["declares"]["exits-used"]),
            "fields-used": sorted(parsed["declares"]["fields-used"]),
            "tags-used": sorted(parsed["declares"]["tags-used"]),
            "calendars": sorted(parsed["declares"]["calendars"]),
            "pipeline": parsed["declares"]["pipeline"],
            "stage-map": sorted(parsed["declares"]["stage-map"]),
        },
        "win_action": parsed["win_action"],
        "escalation": _section_content_lines(lines, "on escalation"),
        "on_success": parsed.get("on_success_actions") or [],
    }
    blob = json.dumps(skeleton, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def write_build_contract(parsed, playbook_id, playbook_path):
    """Build Skill 44 contract using only values supported by playbook grammar."""
    warnings = []
    declares = parsed["declares"]

    tags = {"applies": [], "reads": []}
    for entry in declares["tags-used"]:
        tag, mode = parse_tag_entry(entry)
        if tag is None or mode is None:
            warnings.append(
                "tags-used entry %r is unparseable; omitted from contract" % entry
            )
        else:
            tags[mode].append(tag)

    fields = [
        {"name": name, "type": None, "create_if_missing": None}
        for name in declares["fields-used"]
    ]
    if fields:
        warnings.append(
            "fields: type/create_if_missing are not declared by the playbook grammar"
        )

    condition_keywords = frozenset({"if", "then", "else", "and", "or", "not"})
    calendars = []
    for entry in declares["calendars"]:
        if ":" not in entry:
            warnings.append("calendars entry %r has no colon; omitted" % entry)
            continue
        key, calendar_id = (part.strip() for part in entry.split(":", 1))
        if key.lower() in condition_keywords or calendar_id.lower() in condition_keywords:
            continue
        calendars.append({"key": key, "id": calendar_id})

    stages = []
    for entry in declares["stage-map"]:
        if ":" not in entry:
            warnings.append("stage-map entry %r has no colon; omitted" % entry)
            continue
        key, name = (part.strip() for part in entry.split(":", 1))
        stages.append({"key": key, "name": name})

    tools = set(declares["tools-used"])
    for phase in parsed["phases"]:
        tools.update(phase.get("tools") or [])

    for section in (
        "trigger",
        "custom_values",
        "channels",
        "workflow",
    ):
        warnings.append(
            "%s: no declares source in the playbook grammar; emitted empty" % section
        )

    trigger = {"kind": None, "tag": None}
    custom_values = []
    pipeline = {"id": declares["pipeline"], "stages": stages}

    must_pass = []
    if trigger.get("kind") or trigger.get("tag"):
        must_pass.append("trigger_wired")
    if tags["applies"] or tags["reads"]:
        must_pass.append("tags_exist")
    if tags["applies"]:
        must_pass.append("applies_tags_present_as_nodes")
    if fields:
        must_pass.append("fields_exist")
    if custom_values:
        must_pass.append("custom_values_exist")
    if calendars:
        must_pass.append("calendars_exist")
    if stages:
        must_pass.append("pipeline_stages_exist")

    if not must_pass:
        raise BuildContractRefused(
            "refusing to emit a vacuous build contract: the playbook declares no trigger, tags, fields, custom values, calendars or pipeline stages, so acceptance.must_pass would be empty and would validate nothing"
        )

    return {
        "contract_version": "1.0.0",
        "playbook_id": playbook_id,
        "playbook_path": playbook_path,
        "playbook_structure_hash": structure_hash(parsed),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "trigger": trigger,
        "tags": tags,
        "fields": fields,
        "custom_values": custom_values,
        "calendars": calendars,
        "pipeline": pipeline,
        "exit_rules": [
            {"tag": rule["tag"], "action": rule["action"]}
            for rule in parsed["exit_rules"]
        ],
        "tools": sorted(tools & TOOL_VOCABULARY),
        "channels": [],
        "model_tier": parsed["header"]["model_tier"] or DEFAULT_MODEL_TIER,
        "workflow": {
            "name": None,
            "folder": None,
            "draft_only": None,
            "reentry": None,
        },
        "acceptance": {"must_pass": must_pass},
        "warnings": warnings,
    }


def _mermaid_label(text):
    """Sanitize a label for a Mermaid node."""
    if not text:
        return ""
    return re.sub(r'["\[\]{}|<>\n]', " ", text).strip()


def to_mermaid(parsed):
    """Emit deterministic workflow Mermaid content."""
    out = ["flowchart TD", '  trigger(["Trigger"])']
    prev = "trigger"
    for phase in parsed["phases"]:
        node = "phase%d" % phase["number"]
        tools = resolve_phase_tools(phase)
        label = "Phase %d: %s" % (phase["number"], _mermaid_label(phase["name"]))
        toolstr = _mermaid_label(", ".join(tools))
        out.append('  %s["%s<br/>tools: %s"]' % (node, label, toolstr))
        out.append("  %s --> %s" % (prev, node))
        prev = node

    win = _mermaid_label(parsed["win_action"]) or "Win action"
    out.append('  win(["%s"])' % win)
    out.append("  %s --> win" % prev)

    if parsed["exit_rules"]:
        out.append('  exit{{"Workflow exit"}}')
        for rule in parsed["exit_rules"]:
            edge_label = _mermaid_label(
                "%s (%s)" % (rule.get("tag") or "tag", rule.get("action") or "exit")
            )
            for phase in parsed["phases"]:
                out.append('  phase%d -.->|%s| exit' % (phase["number"], edge_label))
            if rule.get("action") == "route" and rule.get("target"):
                out.append(
                    '  exit -.->|route| %s(["%s"])'
                    % (
                        "route_" + re.sub(r"[^A-Za-z0-9_]", "_", rule["target"]),
                        _mermaid_label(rule["target"]),
                    )
                )

    escalation = _mermaid_label(parsed["escalation"]) or "Escalate to human"
    out.append('  escalation["%s"]' % escalation)
    for phase in parsed["phases"]:
        out.append("  phase%d -.-> escalation" % phase["number"])
    return "\n".join(out) + "\n"


_HEADER_LINE_RE = {
    "active_workflow": re.compile(r"^\s*active_workflow\s*:\s*(.+?)\s*$", re.IGNORECASE),
    "active_phase": re.compile(r"^\s*active_phase\s*:\s*(.+?)\s*$", re.IGNORECASE),
    "phase_attempts": re.compile(r"^\s*phase_attempts\s*:\s*(.+?)\s*$", re.IGNORECASE),
}


def read_log_header(text):
    """Read machine-readable header lines from a conversation log."""
    header = {"active_workflow": None, "active_phase": None, "phase_attempts": None}
    for line in text.splitlines():
        for key, regex in _HEADER_LINE_RE.items():
            if header[key] is None:
                match = regex.match(line)
                if match:
                    header[key] = match.group(1).strip()
        if all(value is not None for value in header.values()):
            break
    return header


def resolve_from_log(log_text, playbook_text=None):
    """Resolve workflow, phase, attempts, and optionally enabled tools."""
    header = read_log_header(log_text)
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
        "active_workflow": header["active_workflow"],
        "active_phase": active_phase,
        "phase_attempts": header["phase_attempts"],
        "enabled_tools": enabled_tools,
    }


def _read(path):
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _load_registry_ids(path):
    """Extract registered playbook ids from table cells or bullet slugs."""
    ids = set()
    bullet = re.compile(r"^[-*]\s+([a-z0-9][a-z0-9-]*)\s*:")
    for line in _read(path).splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip().strip("`").strip() for cell in stripped.strip("|").split("|")]
            if cells:
                rid = cells[0]
                if rid and rid.lower() != "id" and not (set(rid) <= set("-: ")):
                    ids.add(rid)
        else:
            match = bullet.match(stripped)
            if match:
                ids.add(match.group(1))
    return ids


def _load_crm_fields(path):
    fields = set()
    for line in _read(path).splitlines():
        fields.update(re.findall(r"ZHC_[A-Za-z0-9_]+", line))
    return fields


def cmd_parse(args):
    print(json.dumps(parse_playbook(_read(args.playbook)), indent=2, ensure_ascii=False))
    return 0


def cmd_validate(args):
    parsed = parse_playbook(_read(args.playbook))
    crm = _load_crm_fields(args.crm_fields) if args.crm_fields else None
    registry = _load_registry_ids(args.registry) if args.registry else None
    defects = validate_playbook(parsed, crm_fields=crm, registry_targets=registry)
    if not defects:
        print(
            "OK: playbook is grammatically valid (%d phase(s), %d exit rule(s))"
            % (len(parsed["phases"]), len(parsed["exit_rules"]))
        )
        return 0
    print("INVALID: %d defect(s)" % len(defects))
    for idx, defect in enumerate(defects, start=1):
        print("  %d. %s" % (idx, defect))
    return 1


def cmd_lint(args):
    parsed = parse_playbook(_read(args.playbook))
    defects = conversation_lint(parsed)
    if not defects:
        print("OK: conversation lint clean")
        return 0
    print("LINT: %d defect(s)" % len(defects))
    for idx, defect in enumerate(defects, start=1):
        print("  %d. %s" % (idx, defect))
    return 1


def cmd_hash(args):
    print(structure_hash(parse_playbook(_read(args.playbook))))
    return 0


def cmd_build_contract(args):
    try:
        playbook_text = _read(args.playbook)
    except OSError as exc:
        print("build-contract: cannot read playbook %r: %s" % (args.playbook, exc), file=sys.stderr)
        return 2

    playbook = Path(args.playbook)
    parsed = parse_playbook(playbook_text)
    try:
        contract = write_build_contract(
            parsed,
            playbook.stem,
            args.playbook_path if args.playbook_path is not None else args.playbook,
        )
    except BuildContractRefused as exc:
        print("build-contract: " + str(exc), file=sys.stderr)
        return 1
    output_path = (
        Path(args.out)
        if args.out is not None
        else playbook.parent / (playbook.stem + "--build-contract.json")
    )
    try:
        output_path.write_text(
            json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print("build-contract: cannot write output %r: %s" % (str(output_path), exc), file=sys.stderr)
        return 2

    print(str(output_path))
    return 0


def cmd_mermaid(args):
    sys.stdout.write(to_mermaid(parse_playbook(_read(args.playbook))))
    return 0


def cmd_resolve(args):
    log_text = _read(args.log)
    playbook_text = None
    if args.playbook:
        playbook_text = _read(args.playbook)
    elif args.workflows_dir:
        workflow = read_log_header(log_text)["active_workflow"]
        if workflow:
            candidate = Path(args.workflows_dir) / ("%s.md" % workflow)
            if candidate.is_file():
                playbook_text = candidate.read_text(encoding="utf-8", errors="ignore")
    resolved = resolve_from_log(log_text, playbook_text)
    if args.json:
        print(json.dumps(resolved, indent=2, ensure_ascii=False))
    else:
        print("active_workflow: %s" % (resolved["active_workflow"] or "<none>"))
        print(
            "active_phase: %s"
            % (resolved["active_phase"] if resolved["active_phase"] is not None else "<none>")
        )
        print("phase_attempts: %s" % (resolved["phase_attempts"] or "<none>"))
        if resolved["enabled_tools"] is None:
            print("enabled_tools: <playbook not supplied>")
        else:
            print("enabled_tools: %s" % ", ".join(resolved["enabled_tools"]))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="playbook_engine.py",
        description="Canonical parser for Skill 38 Layer 2 conversation workflow playbooks (U-16).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    parse_cmd = sub.add_parser("parse", help="parse a playbook to JSON")
    parse_cmd.add_argument("playbook")
    parse_cmd.set_defaults(func=cmd_parse)

    validate_cmd = sub.add_parser("validate", help="grammar + cross-validation, exit 1 on defects")
    validate_cmd.add_argument("playbook")
    validate_cmd.add_argument("--crm-fields", default=None, help="path to crm-field-mappings.md")
    validate_cmd.add_argument("--registry", default=None, help="path to conversation-workflows registry.md")
    validate_cmd.set_defaults(func=cmd_validate)

    lint_cmd = sub.add_parser("lint", help="lint conversational playbook content")
    lint_cmd.add_argument("playbook")
    lint_cmd.set_defaults(func=cmd_lint)

    hash_cmd = sub.add_parser("hash", help="print the structure hash")
    hash_cmd.add_argument("playbook")
    hash_cmd.set_defaults(func=cmd_hash)

    contract_cmd = sub.add_parser(
        "build-contract",
        help="write Skill 44 build-contract JSON",
    )
    contract_cmd.add_argument("playbook")
    contract_cmd.add_argument("--out", default=None, help="output JSON path")
    contract_cmd.add_argument(
        "--playbook-path",
        default=None,
        help="playbook path string recorded in the contract",
    )
    contract_cmd.set_defaults(func=cmd_build_contract)

    mermaid_cmd = sub.add_parser("mermaid", help="emit diagram.mmd content")
    mermaid_cmd.add_argument("playbook")
    mermaid_cmd.set_defaults(func=cmd_mermaid)

    resolve_cmd = sub.add_parser("resolve", help="resolve active workflow/phase/tools from a log")
    resolve_cmd.add_argument("--log", required=True)
    resolve_cmd.add_argument("--playbook", default=None)
    resolve_cmd.add_argument("--workflows-dir", default=None)
    resolve_cmd.add_argument("--json", action="store_true")
    resolve_cmd.set_defaults(func=cmd_resolve)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

