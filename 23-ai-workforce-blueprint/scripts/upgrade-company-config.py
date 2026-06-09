#!/usr/bin/env python3
"""
upgrade-company-config.py — runtime D: generate or upgrade company-config.json to schema v2.0.

Usage
-----
# Generate from scratch (reads interview answers + departments.json):
    python3 upgrade-company-config.py

# Upgrade an existing v1.0 file in-place:
    python3 upgrade-company-config.py --upgrade /path/to/company-config.json

# Explicit output path:
    python3 upgrade-company-config.py --output /path/to/company-config.json

Standalone upgrade path (for existing clients):
    python3 upgrade-company-config.py --upgrade

The script is idempotent: running it on an already-v2.0 file is a no-op
(it verifies all required fields are present and exits 0).

Exit codes:
    0 = success (generated or already v2.0)
    1 = fatal error (no ZHC tree, bad JSON, etc.)
    2 = soft warning (wrote v2.0 but some fields are empty — scoring will degrade)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

REQUIRED_V2_FIELDS = ("name", "industry", "mission", "owner_values",
                      "company_kpis", "dept_kpis", "schema_version")


# ─── Path discovery ──────────────────────────────────────────────────────────

def find_zhc_company_dir() -> Path | None:
    """Return the most-recently-modified ZHC company folder, or None."""
    home = Path.home()
    roots = [
        home / "clawd" / "zero-human-company",
        Path("/data/clawd/zero-human-company"),
        home / "clawd" / "zhc",
        Path("/data/clawd/zhc"),
    ]
    target_slug = os.environ.get("COMPANY_SLUG", "").strip()
    best: tuple[float, Path] | None = None
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if target_slug and child.name != target_slug:
                continue
            mtime = child.stat().st_mtime
            if best is None or mtime > best[0]:
                best = (mtime, child)
    return best[1] if best else None


def find_departments_json(company_dir: Path | None) -> list:
    """Try to load departments.json. Returns list of dept entry dicts."""
    candidates: list[Path] = []
    if company_dir:
        candidates.append(company_dir / "departments.json")
    home = Path.home()
    candidates.extend([
        home / "Downloads/openclaw-master-files/company-discovery/departments.json",
        Path("/data/.openclaw/master-files/company-discovery/departments.json"),
        home / "clawd/departments/departments.json",
    ])
    for p in candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if isinstance(data, list) and data:
                    return data
            except Exception:
                pass
    return []


def find_interview_answers(company_dir: Path | None) -> str:
    """Return raw markdown of workforce-interview-answers.md, or ''."""
    candidates: list[Path] = []
    if company_dir:
        candidates.append(company_dir / "workforce-interview-answers.md")
    home = Path.home()
    candidates.extend([
        home / "Downloads/openclaw-master-files/company-discovery/workforce-interview-answers.md",
        Path("/data/.openclaw/master-files/company-discovery/workforce-interview-answers.md"),
        home / ".openclaw/workspace/company-discovery/workforce-interview-answers.md",
    ])
    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
    return ""


def scrape_answer(text: str, question_pattern: str) -> str:
    """Pull the answer from an interview-answers.md line."""
    m = re.search(question_pattern, text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


# ─── Config generation ────────────────────────────────────────────────────────

def build_v2_config(existing: dict | None, company_dir: Path | None) -> dict:
    """Build (or upgrade) a v2.0 company-config payload."""
    departments = find_departments_json(company_dir)
    interview = find_interview_answers(company_dir)

    # Start from existing if upgrading
    base = dict(existing) if existing else {}

    # --- name ---
    name = base.get("name") or os.environ.get("COMPANY_NAME", "").strip()
    if not name and interview:
        name = scrape_answer(interview,
            r'\*\*Q:\*\*\s+What is the name of your business\?\s*\n+\*\*A:\*\*\s+(.+?)(?:\n|$)')
    if not name and company_dir:
        name = company_dir.name.replace("-", " ").replace("_", " ").title()
    base["name"] = name or "My Company"

    # --- slug ---
    if not base.get("slug"):
        base["slug"] = re.sub(r"[^a-z0-9]+", "-", base["name"].lower()).strip("-") or "my-company"

    # --- industry ---
    industry = base.get("industry") or os.environ.get("COMPANY_INDUSTRY", "").strip()
    if not industry and interview:
        industry = scrape_answer(interview,
            r'\*\*Q:\*\*\s+What industry.+?\*\*A:\*\*\s+(.+?)(?:\n|$)')
    base["industry"] = industry or ""

    # --- mission ---
    mission = base.get("mission") or base.pop("company_mission", "") or base.pop("company_description", "")
    if not mission and interview:
        mission = scrape_answer(interview,
            r'\*\*Q:\*\*\s+In one sentence.+?\*\*A:\*\*\s+(.+?)(?:\n|$)')
    base["mission"] = mission or ""

    # --- owner_values ---
    owner_values = base.get("owner_values") or []
    if isinstance(owner_values, str):
        owner_values = [v.strip() for v in owner_values.split(",") if v.strip()]
    base["owner_values"] = owner_values

    # --- company_kpis ---
    company_kpis = base.get("company_kpis") or []
    if isinstance(company_kpis, str):
        company_kpis = [k.strip() for k in company_kpis.split(",") if k.strip()]
    base["company_kpis"] = company_kpis

    # --- dept_kpis (aggregate from departments.json) ---
    dept_kpis = base.get("dept_kpis") or {}
    if not isinstance(dept_kpis, dict):
        dept_kpis = {}
    for dept_entry in departments:
        if not isinstance(dept_entry, dict):
            continue
        raw_id = dept_entry.get("id", "")
        dept_id = raw_id[5:] if raw_id.startswith("dept-") else raw_id
        if dept_id and dept_id not in dept_kpis:
            dept_kpis[dept_id] = []  # empty placeholder — real KPIs come from interview
    base["dept_kpis"] = dept_kpis

    # --- brand ---
    brand = base.get("brand") or {}
    if not isinstance(brand, dict):
        brand = {}
    brand.setdefault("primary", "#1f2937")
    brand.setdefault("accent", "#3b82f6")
    brand.setdefault("text", "#f8fafc")
    base["brand"] = brand

    # --- connected_systems ---
    base.setdefault("connected_systems", [])

    # --- metadata ---
    base.setdefault("created", datetime.now().isoformat())
    base["updated"] = datetime.now().isoformat()
    base["schema_version"] = "2.0"

    return base


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or upgrade company-config.json to schema v2.0")
    parser.add_argument("--upgrade", nargs="?", const="AUTO",
                        metavar="PATH",
                        help="Upgrade an existing company-config.json in-place. "
                             "Pass a path or omit for auto-discovery.")
    parser.add_argument("--output", metavar="PATH",
                        help="Write the generated config to this path (default: auto)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the generated config without writing it")
    args = parser.parse_args()

    company_dir = find_zhc_company_dir()
    existing: dict | None = None
    output_path: Path | None = None

    # --- Resolve input path for --upgrade ---
    if args.upgrade is not None:
        if args.upgrade == "AUTO":
            # Auto-discover
            for cand in (
                [company_dir / "company-config.json"] if company_dir else []
            ) + [
                Path.home() / "Downloads/openclaw-master-files/company-discovery/company-config.json",
                Path("/data/.openclaw/master-files/company-config.json"),
            ]:
                if cand.exists():
                    output_path = cand
                    break
        else:
            p = Path(args.upgrade)
            if not p.exists():
                print(f"[upgrade-company-config] FATAL: {p} not found", file=sys.stderr)
                return 1
            output_path = p
        if output_path and output_path.exists():
            try:
                existing = json.loads(output_path.read_text())
            except Exception as e:
                print(f"[upgrade-company-config] WARN: could not parse existing file: {e}", file=sys.stderr)
                existing = None
            # Check if already v2.0
            if isinstance(existing, dict) and existing.get("schema_version") == "2.0":
                missing = [f for f in REQUIRED_V2_FIELDS if not existing.get(f) and f not in ("owner_values", "company_kpis", "dept_kpis")]
                if not missing:
                    print(f"[upgrade-company-config] Already v2.0 at {output_path} — no changes needed")
                    return 0

    # --- Resolve output path ---
    if args.output:
        output_path = Path(args.output)
    elif output_path is None:
        if company_dir:
            output_path = company_dir / "company-config.json"
        else:
            print("[upgrade-company-config] FATAL: cannot determine output path; "
                  "pass --output or set COMPANY_SLUG", file=sys.stderr)
            return 1

    # --- Build config ---
    cfg = build_v2_config(existing, company_dir)

    # --- Dry run ---
    if args.dry_run:
        print(json.dumps(cfg, indent=2))
        return 0

    # --- Write ---
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        print(f"[upgrade-company-config] Wrote company-config.json v2.0 → {output_path}")
    except OSError as e:
        print(f"[upgrade-company-config] FATAL: could not write {output_path}: {e}", file=sys.stderr)
        return 1

    # --- Warn if fields are empty ---
    empty_fields = [f for f in ("mission", "owner_values", "company_kpis")
                    if not cfg.get(f)]
    if empty_fields:
        print(f"[upgrade-company-config] WARN: empty fields {empty_fields} — "
              f"persona scoring Layers 1-3 will fall back to neutral defaults. "
              f"Re-run after completing the Skill 23 interview.", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
