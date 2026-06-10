#!/usr/bin/env python3
"""
generate-brand-css.py — v9.6.5

Reads the active company's brand colors from the Mission Control database
(or directly from ~/clawd/zero-human-company/<slug>/company-config.json
as a fallback) and writes a CSS file the Kanban frontend imports at runtime.

The frontend imports this from `/public/brand.css` (or whatever path the
Next.js app expects). When the file changes, the frontend hot-reloads.

USAGE:
  python3 generate-brand-css.py
  python3 generate-brand-css.py --company-slug blackceo --output ~/projects/command-center/public/brand.css

If --output is omitted, the script tries the standard Command Center repo
locations and writes to the first one it finds.

EXIT CODES:
  0 = brand.css written successfully
  1 = no company config found (write neutral defaults so dashboard isn't broken)
  2 = no Command Center frontend dir found to write to
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HOME = Path.home()


def find_db():
    for c in [
        HOME / "projects/command-center/mission-control.db",
        HOME / "projects/mission-control/mission-control.db",
        Path("/opt/mission-control/mission-control.db"),
        Path("/app/mission-control.db"),
    ]:
        if c.exists():
            return c
    return None


def find_zhc_company_config(slug=None):
    """Find company-config.json — most recent if slug is None."""
    # NOTE: pathlib does NOT auto-expand tilde paths — use Path.home() / "..." instead.
    roots = [
        HOME / "clawd" / "zero-human-company",
        HOME / "clawd" / "zhc",
        Path.home() / "clawd/zero-human-company",
        Path.home() / "clawd/zhc",
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
                candidates.append((cfg.stat().st_mtime, cfg, entry.name))
    if not candidates:
        return None, None
    candidates.sort(reverse=True)
    _, path, slug_found = candidates[0]
    return path, slug_found


def read_brand_from_db(db_path, slug):
    """Pull brand colors from companies.config blob."""
    if not db_path or not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        row = cur.execute("SELECT name, config FROM companies WHERE slug=?", (slug,)).fetchone()
        conn.close()
        if not row:
            return None
        name, config_json = row
        try:
            config = json.loads(config_json or "{}")
        except json.JSONDecodeError:
            config = {}
        brand = config.get("brand", {})
        return {
            "name": name,
            "primary": brand.get("primary", "#1f2937"),
            "accent":  brand.get("accent",  "#3b82f6"),
            "text":    brand.get("text",    "#f8fafc"),
        }
    except sqlite3.Error:
        return None


def read_brand_from_zhc(cfg_path):
    """Pull brand colors from company-config.json."""
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
        brand = cfg.get("brand", {})
        return {
            "name":    cfg.get("name", "My Company"),
            "primary": brand.get("primary", "#1f2937"),
            "accent":  brand.get("accent",  "#3b82f6"),
            "text":    brand.get("text",    "#f8fafc"),
        }
    except (json.JSONDecodeError, OSError):
        return None


def neutral_defaults():
    return {
        "name":    "Command Center",
        "primary": "#1f2937",
        "accent":  "#3b82f6",
        "text":    "#f8fafc",
    }


HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def sanitize_hex(value: str, fallback: str) -> str:
    """Force a value to a valid #RRGGBB. If invalid, return fallback."""
    if not value or not HEX_RE.match(value):
        return fallback
    if not value.startswith("#"):
        value = "#" + value
    return value.lower()


def find_output_path():
    """Best-effort default path. None = no Command Center frontend found."""
    for c in [
        HOME / "projects/command-center/public/brand.css",
        HOME / "projects/mission-control/public/brand.css",
        HOME / "clawd/projects/blackceo-command-center/public/brand.css",
        Path("/opt/mission-control/public/brand.css"),
        Path("/app/public/brand.css"),
    ]:
        if c.parent.is_dir():
            return c
    return None


def render_css(brand: dict) -> str:
    """Produce a CSS file the Next.js Kanban app can import.

    Strategy: CSS custom properties on :root + Tailwind-style utility classes.
    The frontend imports this once at app load; @layer overrides Tailwind defaults.
    """
    primary = sanitize_hex(brand.get("primary"), "#1f2937")
    accent  = sanitize_hex(brand.get("accent"),  "#3b82f6")
    text    = sanitize_hex(brand.get("text"),    "#f8fafc")
    name    = (brand.get("name") or "Command Center").replace("*/", "*\\/")

    return f"""/* brand.css — auto-generated by generate-brand-css.py
 * Company: {name}
 * Re-run after company-config.json or companies table changes.
 */

:root {{
  --brand-primary: {primary};
  --brand-accent:  {accent};
  --brand-text:    {text};

  /* Derived shades for hover / disabled / focus rings */
  --brand-primary-hover: color-mix(in srgb, {primary} 88%, white 12%);
  --brand-accent-hover:  color-mix(in srgb, {accent} 88%, white 12%);
  --brand-primary-muted: color-mix(in srgb, {primary} 70%, transparent);
  --brand-focus-ring:    color-mix(in srgb, {accent} 60%, transparent);
}}

/* Tailwind v3+ overrides via arbitrary-value syntax  */
.bg-brand-primary  {{ background-color: var(--brand-primary) !important; }}
.bg-brand-accent   {{ background-color: var(--brand-accent)  !important; }}
.text-brand        {{ color: var(--brand-text)              !important; }}
.text-brand-primary{{ color: var(--brand-primary)           !important; }}
.text-brand-accent {{ color: var(--brand-accent)            !important; }}
.border-brand-primary {{ border-color: var(--brand-primary) !important; }}
.border-brand-accent  {{ border-color: var(--brand-accent)  !important; }}

/* Header / top-bar reskins */
header.command-center-header,
nav.command-center-nav {{
  background-color: var(--brand-primary);
  color: var(--brand-text);
}}

/* Primary action buttons (Add Task, Save, etc.) */
button.btn-primary,
.button-primary,
[data-variant="primary"] {{
  background-color: var(--brand-accent);
  color: var(--brand-text);
}}
button.btn-primary:hover,
.button-primary:hover {{
  background-color: var(--brand-accent-hover);
}}

/* Kanban column headers — accent stripe on top */
.kanban-column-header,
[data-kanban-column-header] {{
  border-top: 3px solid var(--brand-accent);
}}

/* Cards in the active state */
.task-card.is-active,
[data-task-card][data-active="true"] {{
  border-color: var(--brand-accent);
  box-shadow: 0 0 0 3px var(--brand-focus-ring);
}}

/* CEO Performance Board grade pills */
.grade-pill {{
  background-color: var(--brand-primary-muted);
  color: var(--brand-text);
}}
"""


def main():
    parser = argparse.ArgumentParser(description="Generate brand.css for the Command Center.")
    parser.add_argument("--company-slug", default=None, help="ZHC company slug; auto-detect if omitted")
    parser.add_argument("--output", default=None, help="Path to write brand.css; auto-detect if omitted")
    parser.add_argument("--print", action="store_true", help="Print CSS to stdout instead of writing")
    args = parser.parse_args()

    # 1. Resolve company + brand
    brand = None
    slug = args.company_slug

    # Try DB first (most authoritative — seed-workspaces.py writes here)
    db = find_db()
    if db and slug:
        brand = read_brand_from_db(db, slug)

    # If no DB hit or no slug given, fall back to ZHC company-config.json
    if not brand:
        cfg_path, found_slug = find_zhc_company_config(slug)
        if cfg_path:
            brand = read_brand_from_zhc(cfg_path)
            slug = slug or found_slug

    if not brand:
        print("[BRAND-CSS] No company config found; using neutral defaults", file=sys.stderr)
        brand = neutral_defaults()
        result_code = 1
    else:
        result_code = 0

    css = render_css(brand)

    if args.print:
        print(css)
        return result_code

    # 2. Resolve output path
    output = Path(args.output) if args.output else find_output_path()
    if not output:
        print("[BRAND-CSS] No Command Center frontend public/ dir found.", file=sys.stderr)
        print("[BRAND-CSS] Pass --output explicitly, e.g.:", file=sys.stderr)
        print("[BRAND-CSS]   --output ~/projects/command-center/public/brand.css", file=sys.stderr)
        return 2

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(css)
    print(f"[BRAND-CSS] Wrote {output} ({len(css)} bytes)")
    print(f"[BRAND-CSS] Company: {brand['name']} | primary={brand['primary']} accent={brand['accent']}")
    print(f"[BRAND-CSS] Frontend must import this file. Add to app/layout.tsx (Next.js):")
    print(f"[BRAND-CSS]   import './brand.css'  // path may differ — typically /public/brand.css → /brand.css")
    return result_code


if __name__ == "__main__":
    sys.exit(main())
