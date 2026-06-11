#!/usr/bin/env python3
# _qc_summary.py — extracted from qc-completeness.sh SUMMARY heredoc.
#
# Externalized v11.18.4 for stock-macOS bash 3.2.57 compatibility (python-in-$()
# parse hazard). Logic byte-equivalent to the former inline heredoc; the QC JSON
# report path is now argv[1] instead of the shell-interpolated $JSON_FILE.
# Prints the per-dept Telegram gap-breakdown summary for a != PASS workforce.
import json
import sys

json_file = sys.argv[1]
d = json.load(open(json_file))
lines = [f"OpenClaw QC: {d['status']} on workforce {d.get('company_root','')}"]
lines.append(f"depts: PASS={d['depts_passing']} PARTIAL={d['depts_partial']} FAIL={d['depts_failing']}")
gaps = [dd for dd in d.get("departments", []) if dd["status"] != "PASS"]
for dd in gaps[:8]:
    lines.append(f"- {dd['dept_id']}: {dd['role_folders']}/{dd['expected_roles']} roles, "
                 f"lib%={dd['library_pct']}, id%={dd['identity_pct']}, status={dd['status']}")
if d.get("legacy_tree_present"):
    lines.append("legacy tree present: " + ", ".join(d["legacy_tree_present"]))
lines.append(f"Full report: {json_file}")
lines.append("Fix: run migrate-existing-workforce.sh (R2) once available.")
print("\n".join(lines))
