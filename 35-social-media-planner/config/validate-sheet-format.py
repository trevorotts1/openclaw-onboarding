#!/usr/bin/env python3
"""validate-sheet-format.py — F25 formatting validator for the Social Media
Planner sheet template contract (config/sheet-template.schema.json).

Checks a template contract file (or, with --export, the formatting that the
n8n exports provision) for:
  - TEXT_EQ usage for text statuses: NUMBER_EQ for a status label is a FAIL,
  - every status value has BOTH a color AND a written label (color is never
    the only signal),
  - dropdown validation (setDataValidation / ONE_OF_LIST) present for status
    columns,
  - frozen headers declared per tab,
  - the compact This Week view present with its ~8 client-facing columns,
  - the example/demo tab marked never-copied.

Usage:
  python3 35-social-media-planner/config/validate-sheet-format.py            # validate sheet-template.schema.json
  python3 35-social-media-planner/config/validate-sheet-format.py --export   # + validate the n8n export wiring
  python3 35-social-media-planner/config/validate-sheet-format.py PATH.json  # validate another contract file

Exit 0 = valid. Violations print FAIL lines and exit 1.
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONTRACT = os.path.join(BASE, "sheet-template.schema.json")
N8N_DIR = os.path.join(BASE, "n8n")

EXPECTED_THIS_WEEK_COLUMNS = ["Week", "Client", "Next Action", "Drafting", "QC",
                              "Scheduled", "Published", "Needs Attention"]

failures = []
checks = 0


def check(cond, ok_msg, fail_msg):
    global checks
    checks += 1
    if not cond:
        failures.append(fail_msg)


def load(path):
    check(os.path.exists(path), f"{os.path.basename(path)} exists",
          f"FAIL {path}: file missing")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"FAIL {path}: invalid JSON ({exc})")
        return None


def walk_strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for item in obj:
            yield None, item
            yield from walk_strings(item)
    else:
        yield None, obj


def validate_contract(contract):
    statuses = contract.get("status_colors", {}).get("statuses", [])
    check(bool(statuses), "contract: status list present",
          "FAIL contract: status_colors.statuses missing or empty")
    labels = set()
    for st in statuses:
        label = st.get("label")
        if not label:
            failures.append("FAIL contract: a status entry has no written label")
            continue
        labels.add(label)
        # F25 — color AND label, never color as the only signal.
        check(bool(st.get("color")), f"status '{label}': color present",
              f"FAIL status '{label}': no color defined")
        check(bool(st.get("color_label")), f"status '{label}': written color label present",
              f"FAIL status '{label}': no written label describing the color — color must not be the only signal")
    # F25 — TEXT_EQ for text statuses; NUMBER_EQ is banned for text.
    # Prose mentions ("never NUMBER_EQ") are fine — the ban is on the EMITTED
    # condition type, so match a JSON condition shape: "type": "NUMBER_EQ".
    fmt = json.dumps(contract)
    check('NUMBER_EQ"' not in fmt.replace('NUMBER_EQ: statuses are text', '') or '"type": "NUMBER_EQ"' not in fmt,
          "contract: no NUMBER_EQ condition emitted for text statuses",
          "FAIL contract: NUMBER_EQ condition appears against text statuses — must be TEXT_EQ")
    check("TEXT_EQ" in fmt, "contract: TEXT_EQ rule type declared",
          "FAIL contract: no TEXT_EQ conditional format rule type declared")
    # Dropdown validation declared.
    check("setDataValidation" in fmt or "dropdown_validation" in fmt,
          "contract: dropdown validation declared",
          "FAIL contract: no setDataValidation dropdown contract")
    # Frozen headers declared.
    check("frozen_headings_row" in fmt, "contract: frozen headers declared",
          "FAIL contract: frozen headers not declared")
    # This Week view present with the expected columns.
    this_week = contract.get("tabs", {}).get("This Week", {})
    check(bool(this_week), "contract: This Week view present",
          "FAIL contract: This Week view tab missing")
    tw_headings = this_week.get("headings", [])
    for col in EXPECTED_THIS_WEEK_COLUMNS:
        check(col in tw_headings, f"This Week column '{col}'",
              f"FAIL This Week view: missing column '{col}'")
    check(this_week.get("width", len(tw_headings)) <= 9,
          "This Week stays compact (~8 columns)",
          f"FAIL This Week view: {len(tw_headings)} columns — keep the primary view compact")
    # Example tab: clearly separate, never copied.
    example_tabs = [t for t, v in contract.get("tabs", {}).items()
                    if isinstance(v, dict) and (v.get("example_tab") or "Example" in t)]
    check(bool(example_tabs), "contract: separate example tab declared",
          "FAIL contract: no separate example tab for demonstrations")
    for t in example_tabs:
        v = contract["tabs"][t]
        check(v.get("copied_to_clients") is False,
              f"tab '{t}': never copied to clients",
              f"FAIL tab '{t}': example tab must declare copied_to_clients=false")
    # Unique headings per tab.
    for tab, cfg in contract.get("tabs", {}).items():
        if not isinstance(cfg, dict):
            continue
        heads = cfg.get("headings") or []
        if heads:
            dupes = {h for h in heads if heads.count(h) > 1}
            check(not dupes, f"tab '{tab}': headings unique",
                  f"FAIL tab '{tab}': duplicate headings {sorted(dupes)} (U:AN pattern)")
    # Starter rows rule present.
    check(bool(contract.get("starter_rows_rule")),
          "contract: starter-rows-empty rule present",
          "FAIL contract: starter_rows_rule missing — template must start EMPTY of brand/campaign/publication content")


def validate_export(name, export):
    """The n8n export wiring must emit TEXT_EQ rules, dropdowns, freeze + This Week.
    F25 formatting provisions from sheet-create; the row-append export carries
    no formatting node by design (formatting is provisioning-time, not per-row)."""
    nodes = {n["name"]: n for n in export.get("nodes", [])}
    fmt_node = nodes.get("Build Formatting Requests (F25)")
    if name == "social-planner-sheet-create.json":
        check(fmt_node is not None, f"{name}: F25 formatting node present",
              f"FAIL {name}: no 'Build Formatting Requests (F25)' node")
    if fmt_node:
        js = fmt_node["parameters"].get("jsCode", "")
        check("TEXT_EQ" in js, f"{name}: TEXT_EQ conditional rules emitted",
              f"FAIL {name}: formatting node does not emit TEXT_EQ rules")
        # Ban the emitted condition shape, not prose mentions of the defect.
        check("type: 'NUMBER_EQ'" not in js and "type: \"NUMBER_EQ\"" not in js,
              f"{name}: no NUMBER_EQ condition emitted for text statuses",
              f"FAIL {name}: formatting node emits NUMBER_EQ against text")
        check("setDataValidation" in js or "ONE_OF_LIST" in js,
              f"{name}: dropdown validation emitted",
              f"FAIL {name}: formatting node emits no setDataValidation dropdown")
        check("frozenRowCount" in js, f"{name}: frozen headers emitted",
              f"FAIL {name}: formatting node does not freeze header rows")
        check("This Week" in js, f"{name}: This Week view provisioned",
              f"FAIL {name}: formatting node does not create the This Week view")
        labels = [s.get("label") for s in (
            [{"label": m} for m in re.findall(r"label: '([^']+)'", js)])]
        for st in ("Complete", "Failed", "QC Review", "Scheduled", "Published", "Needs Attention"):
            check(st in labels, f"{name}: status '{st}' has a color rule + label",
                  f"FAIL {name}: status '{st}' missing from the color/label rule list")
    batch = [n for n in export.get("nodes", [])
             if n["type"] == "n8n-nodes-base.httpRequest" and ":batchUpdate" in str(n["parameters"].get("url", ""))]
    check(bool(batch), f"{name}: formatting runs as a real batchUpdate",
          f"FAIL {name}: no spreadsheet.batchUpdate node carries the formatting requests")


def main():
    path = sys.argv[sys.argv.index("--export") + 1] if "--export" in sys.argv and len(sys.argv) > sys.argv.index("--export") + 1 else (
        sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else DEFAULT_CONTRACT)
    do_export = "--export" in sys.argv
    contract = load(path)
    if contract:
        validate_contract(contract)
    if do_export:
        for fname in ("social-planner-sheet-create.json", "social-planner-row-append.json"):
            export = load(os.path.join(N8N_DIR, fname))
            if export:
                validate_export(fname, export)
    print(f"validate-sheet-format.py: {checks} checks, {len(failures)} failures")
    for f in failures:
        print(f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()