#!/usr/bin/env python3
"""
register-routing-dept.py — Skill 32 Command Center Setup

PURPOSE
    Registers a new department into the openclaw.json routing configuration.
    Looks up the department's metadata from department-naming-map.json, then
    writes a minimal routing entry into the config. Idempotent — safe to run
    twice without creating duplicates.

USAGE
    python3 register-routing-dept.py \\
        --dept  <dept-slug> \\
        --config /path/to/openclaw.json \\
        [--naming-map /path/to/department-naming-map.json] \\
        [--dry-run]

EXIT CODES
    0 — success (or already registered, idempotent)
    1 — error (dept not found in naming map, bad JSON, write failure)
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def die(msg: str) -> None:
    print(f"[register-routing] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg: str) -> None:
    print(f"[register-routing] {msg}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a department into routing config")
    parser.add_argument("--dept",       required=True, help="Department slug")
    parser.add_argument("--config",     required=True, help="Path to openclaw.json")
    parser.add_argument("--naming-map", default=None,
                        help="Path to department-naming-map.json (auto-resolved if omitted)")
    parser.add_argument("--dry-run",    action="store_true", help="Print changes, do not write")
    args = parser.parse_args()

    # ── Resolve naming map ───────────────────────────────────────────────────
    if args.naming_map:
        naming_map_path = args.naming_map
    else:
        # Try to auto-resolve from known relative paths
        script_dir = Path(__file__).parent
        candidates = [
            script_dir / "../../../23-ai-workforce-blueprint/department-naming-map.json",
            Path(os.environ.get("HOME", "/tmp")) / "Downloads/openclaw-onboarding/23-ai-workforce-blueprint/department-naming-map.json",
            Path(os.environ.get("HOME", "/tmp")) / "Downloads/openclaw-master-files/23-ai-workforce-blueprint/department-naming-map.json",
        ]
        naming_map_path = None
        for c in candidates:
            if c.exists():
                naming_map_path = str(c.resolve())
                break
        if not naming_map_path:
            die(f"Cannot find department-naming-map.json. Pass --naming-map explicitly.")

    # ── Load naming map ──────────────────────────────────────────────────────
    try:
        with open(naming_map_path) as f:
            naming_map = json.load(f)
    except Exception as e:
        die(f"Cannot load naming map from {naming_map_path}: {e}")

    # Build slug → metadata index from both mandatory and vertical_packs
    dept_meta = {}
    for section in ("mandatory", "vertical_packs", "universal_primary", "vertical_secondary"):
        for entry in naming_map.get(section, []):
            slug = entry.get("slug") or entry.get("id")
            if slug:
                dept_meta[slug] = entry

    if args.dept not in dept_meta:
        die(f"Department '{args.dept}' not found in naming map at {naming_map_path}")

    meta = dept_meta[args.dept]
    director_title = meta.get("director_title") or meta.get("head", "Director")
    emoji = meta.get("emoji", "")
    description = meta.get("description", f"{args.dept} department")

    info(f"Dept: {args.dept} | Director: {director_title} | Emoji: {emoji}")

    # ── Load openclaw.json ───────────────────────────────────────────────────
    config_path = Path(args.config)
    if not config_path.exists():
        die(f"openclaw.json not found at {args.config}")

    try:
        with open(config_path) as f:
            config = json.load(f)
    except Exception as e:
        die(f"Cannot parse openclaw.json: {e}")

    # ── Check if already registered ──────────────────────────────────────────
    # We look for an agent whose id contains the dept slug
    agents_list = config.get("agents", {}).get("list", [])
    for agent in agents_list:
        if isinstance(agent, dict) and args.dept in str(agent.get("id", "")):
            info(f"Department '{args.dept}' already registered (agent id: {agent.get('id')}). Skipping.")
            sys.exit(0)

    # ── Build routing entry ──────────────────────────────────────────────────
    # N31 compliant: model MUST be an object with primary + fallbacks
    new_routing_entry = {
        "dept_slug": args.dept,
        "director_title": director_title,
        "emoji": emoji,
        "description": description,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "model": {
            "primary": "ollama/kimi-k2.6:cloud",
            "fallbacks": [
                "openrouter/moonshotai/kimi-k2.6",
                "ollama/deepseek-v4-pro:cloud",
                "openrouter/deepseek/deepseek-v4-pro",
            ],
        },
    }

    # Write into the extension_registry block (create if missing)
    if "extension_registry" not in config:
        config["extension_registry"] = {"departments": []}
    registry = config["extension_registry"].setdefault("departments", [])

    # Idempotent: check registry too
    for existing in registry:
        if existing.get("dept_slug") == args.dept:
            info(f"Department '{args.dept}' already in extension_registry. Skipping.")
            sys.exit(0)

    registry.append(new_routing_entry)

    if args.dry_run:
        info(f"[DRY-RUN] Would add to extension_registry:")
        print(json.dumps(new_routing_entry, indent=2))
        sys.exit(0)

    # ── Write back ───────────────────────────────────────────────────────────
    # Atomic write: backup → write temp → rename
    backup_path = str(config_path) + f".bak-reg-{int(datetime.now().timestamp())}"
    shutil.copy2(config_path, backup_path)
    info(f"Backed up openclaw.json to {backup_path}")

    tmp_path = str(config_path) + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(config, f, indent=2)
        os.replace(tmp_path, config_path)
    except Exception as e:
        # Restore backup on failure
        shutil.copy2(backup_path, config_path)
        die(f"Write failed, restored backup: {e}")

    info(f"Registered '{args.dept}' into extension_registry in {config_path}")


if __name__ == "__main__":
    main()
