#!/usr/bin/env python3
"""
generate-kpi-rollup.py — v9.6.5

Builds the company-level KPI rollup the CEO Performance Board displays.
Reads:
  - ~/clawd/zero-human-company/<slug>/company-config.json
      → declares company-level KPIs (e.g. monthly recurring revenue, NPS,
        customer count)
  - ~/clawd/zero-human-company/<slug>/departments/<dept>/department-config.json
      → declares per-dept KPIs and which company KPIs they roll up to

Writes:
  - ~/clawd/zero-human-company/<slug>/kpi-rollup.json
      The dashboard frontend (or any agent) reads this. Schema:
      {
        "company": "BlackCEO",
        "generated": "2026-05-13T...",
        "company_kpis": [
          {
            "id": "monthly_recurring_revenue",
            "label": "Monthly Recurring Revenue",
            "target": 50000,
            "actual": 38500,
            "unit": "$",
            "grade": "B",
            "contributing_departments": [
              {"dept": "sales", "weight": 0.6, "dept_kpi": "new_mrr"},
              {"dept": "marketing", "weight": 0.4, "dept_kpi": "qualified_leads_x_close_rate"}
            ]
          },
          ...
        ],
        "department_grades": [
          {"dept": "marketing", "grade": "A-", "kpis_hit": 4, "kpis_total": 5},
          {"dept": "sales", "grade": "B", "kpis_hit": 3, "kpis_total": 5},
          ...
        ]
      }

Grade thresholds:
  100%+ of target = A
  85-99%          = A-
  70-84%          = B
  55-69%          = C
  <55%            = D

USAGE:
  python3 generate-kpi-rollup.py
  python3 generate-kpi-rollup.py --company-slug blackceo
  python3 generate-kpi-rollup.py --print            # don't write, just print

EXIT CODES:
  0 = rollup written
  1 = no company config found
  2 = no department configs found
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()


def find_zhc_company_dir(slug=None):
    roots = [
        HOME / "clawd" / "zero-human-company",
        HOME / "clawd" / "zhc",
        Path(os.path.expanduser("~/clawd/zero-human-company")),  # PRD item 1.7: expanduser
        Path(os.path.expanduser("~/clawd/zhc")),                  # PRD item 1.7: expanduser
    ]
    candidates = []
    for root in roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if slug and entry.name != slug:
                continue
            cfg = entry / "company-config.json"
            if cfg.exists():
                candidates.append((cfg.stat().st_mtime, entry))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def grade(percent: float) -> str:
    if percent >= 1.0:    return "A"
    if percent >= 0.85:   return "A-"
    if percent >= 0.70:   return "B"
    if percent >= 0.55:   return "C"
    return "D"


def main():
    parser = argparse.ArgumentParser(description="Generate KPI rollup for the CEO Performance Board.")
    parser.add_argument("--company-slug", default=None)
    parser.add_argument("--print", action="store_true", help="Print JSON, don't write")
    args = parser.parse_args()

    company_dir = find_zhc_company_dir(args.company_slug)
    if not company_dir:
        print("[KPI-ROLLUP] No ZHC company folder found.", file=sys.stderr)
        return 1

    company_cfg_path = company_dir / "company-config.json"
    with open(company_cfg_path) as f:
        company_cfg = json.load(f)

    departments_dir = company_dir / "departments"
    if not departments_dir.is_dir():
        print(f"[KPI-ROLLUP] No departments folder at {departments_dir}", file=sys.stderr)
        return 2

    # ─── Collect company-level KPI declarations ─────────────────────────────
    company_kpis = company_cfg.get("kpis", [])
    if not isinstance(company_kpis, list):
        company_kpis = []

    # ─── Collect dept-level KPIs ─────────────────────────────────────────────
    dept_data = {}
    for dept_dir in sorted(departments_dir.iterdir()):
        if not dept_dir.is_dir() or dept_dir.name.startswith("."):
            continue
        dept_id = dept_dir.name
        dc_path = dept_dir / "department-config.json"
        if not dc_path.exists():
            # No config = no KPIs yet; mark as INDETERMINATE
            dept_data[dept_id] = {"kpis": [], "indeterminate": True}
            continue
        try:
            with open(dc_path) as f:
                dc = json.load(f)
            dept_data[dept_id] = {
                "kpis": dc.get("kpis", []) if isinstance(dc.get("kpis"), list) else [],
                "indeterminate": False,
            }
        except (json.JSONDecodeError, OSError) as e:
            print(f"[KPI-ROLLUP] Skip {dept_id}: {e}", file=sys.stderr)
            dept_data[dept_id] = {"kpis": [], "indeterminate": True}

    # ─── Build rollup ────────────────────────────────────────────────────────
    rollup_company_kpis = []
    for ck in company_kpis:
        ck_id = ck.get("id", "")
        ck_target = ck.get("target", 0) or 0
        ck_actual = ck.get("actual", 0) or 0
        # Find contributing dept KPIs (those that declare "rolls_up_to": ck_id)
        contributors = []
        for dept_id, info in dept_data.items():
            for dkpi in info["kpis"]:
                if dkpi.get("rolls_up_to") == ck_id:
                    contributors.append({
                        "dept": dept_id,
                        "weight": dkpi.get("weight", 1.0),
                        "dept_kpi": dkpi.get("id", ""),
                        "dept_actual": dkpi.get("actual", 0),
                        "dept_target": dkpi.get("target", 0),
                    })
        # Compute grade from actual/target ratio
        if ck_target > 0:
            pct = float(ck_actual) / float(ck_target)
        else:
            pct = 0.0
        rollup_company_kpis.append({
            "id": ck_id,
            "label": ck.get("label", ck_id),
            "unit": ck.get("unit", ""),
            "target": ck_target,
            "actual": ck_actual,
            "percent_of_target": round(pct * 100, 1),
            "grade": grade(pct),
            "contributing_departments": contributors,
        })

    # Per-department grade summary
    dept_grades = []
    for dept_id, info in dept_data.items():
        if info["indeterminate"]:
            dept_grades.append({
                "dept": dept_id, "grade": "?", "kpis_hit": 0,
                "kpis_total": 0, "indeterminate": True,
                "note": "department-config.json missing or kpis not declared"
            })
            continue
        kpis = info["kpis"]
        if not kpis:
            dept_grades.append({"dept": dept_id, "grade": "?", "kpis_hit": 0, "kpis_total": 0, "indeterminate": True})
            continue
        hits = 0
        for k in kpis:
            t = k.get("target", 0) or 0
            a = k.get("actual", 0) or 0
            if t > 0 and a >= t * 0.85:
                hits += 1
        ratio = hits / len(kpis) if kpis else 0
        dept_grades.append({
            "dept": dept_id,
            "grade": grade(ratio),
            "kpis_hit": hits,
            "kpis_total": len(kpis),
            "indeterminate": False,
        })

    rollup = {
        "company": company_cfg.get("name", "Company"),
        "slug": company_cfg.get("slug", company_dir.name),
        "generated": datetime.utcnow().isoformat() + "Z",
        "company_kpis": rollup_company_kpis,
        "department_grades": dept_grades,
        "schema_version": "1.0",
    }

    output_path = company_dir / "kpi-rollup.json"
    if args.print:
        print(json.dumps(rollup, indent=2))
    else:
        with open(output_path, "w") as f:
            json.dump(rollup, f, indent=2)
        print(f"[KPI-ROLLUP] Wrote {output_path}")
        print(f"[KPI-ROLLUP] Company KPIs: {len(rollup_company_kpis)} | Departments: {len(dept_grades)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
