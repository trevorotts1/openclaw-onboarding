#!/usr/bin/env python3
"""
register-routing-dept.py — Skill 32 Command Center Setup

PURPOSE
    Registers a new department into the routing-extension LEDGER. Looks up the
    department's metadata from department-naming-map.json, then appends a minimal
    routing entry to a SIDECAR ledger file that lives BESIDE openclaw.json
    (default: <config-dir>/extension-registry.json). Idempotent — safe to run
    twice without creating duplicates.

WHY A SIDECAR (do not regress this)
    OpenClaw 2026.6.8 tightened the openclaw.json ROOT schema to
    `additionalProperties: false`. Any unknown root key (such as the old
    `extension_registry` block this script used to write) makes
    `openclaw config validate` fail with "<root>: Invalid input", which in turn
    BLOCKS `openclaw message send` (Telegram) on every box where a department was
    registered. The registry is OUR bookkeeping, not OpenClaw config — so it MUST
    NOT live in the openclaw.json root. It lives in a sidecar file that OpenClaw
    never reads or schema-checks. This script NEVER writes a key into the
    openclaw.json root.

    For any box already broken by the old behaviour, this script SELF-HEALS on
    next run: if openclaw.json has a root `extension_registry`, it is migrated
    (merged) into the sidecar and DELETED from the config root via a safe,
    backed-up, atomic JSON round-trip (never run as root).

USAGE
    python3 register-routing-dept.py \\
        --dept  <dept-slug> \\
        --config /path/to/openclaw.json \\
        [--registry /path/to/extension-registry.json] \\
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


def _atomic_write_json(path: Path, data) -> None:
    """Back up (if the file exists) → write temp → atomic rename. Never partial."""
    if path.exists():
        backup = str(path) + f".bak-reg-{int(datetime.now().timestamp())}"
        shutil.copy2(path, backup)
        info(f"Backed up {path.name} to {backup}")
    tmp = str(path) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def default_registry_path(config_path: Path) -> Path:
    """The sidecar ledger lives beside openclaw.json, NOT inside it."""
    return config_path.parent / "extension-registry.json"


def load_registry(registry_path: Path) -> dict:
    """Load the sidecar ledger, tolerating a missing/empty/legacy file."""
    if not registry_path.exists():
        return {"departments": []}
    try:
        data = _load_json(registry_path)
    except Exception as e:
        die(f"Cannot parse sidecar registry {registry_path}: {e}")
    if not isinstance(data, dict):
        die(f"Sidecar registry {registry_path} is not a JSON object")
    data.setdefault("departments", [])
    if not isinstance(data["departments"], list):
        die(f"Sidecar registry {registry_path} has a non-list 'departments'")
    return data


def migrate_root_registry(config_path: Path, registry_path: Path, dry_run: bool) -> dict:
    """SELF-HEAL: if openclaw.json has a root `extension_registry`, move it into
    the sidecar (merge, dedup by dept_slug) and DELETE it from the config root.

    Returns the (possibly updated) sidecar registry dict. Performs a safe,
    backed-up, atomic round-trip on BOTH files. Never runs as root.
    """
    sidecar = load_registry(registry_path)

    try:
        config = _load_json(config_path)
    except Exception as e:
        die(f"Cannot parse openclaw.json: {e}")

    root_reg = config.get("extension_registry")
    if root_reg is None:
        return sidecar  # nothing to migrate

    info("MIGRATION: found legacy `extension_registry` in openclaw.json root — "
         "moving it to the sidecar and removing it from config (2026.6.8 schema).")

    # Merge the legacy departments into the sidecar, deduping by dept_slug.
    legacy_depts = []
    if isinstance(root_reg, dict):
        legacy_depts = root_reg.get("departments", []) or []
    elif isinstance(root_reg, list):
        legacy_depts = root_reg
    seen = {d.get("dept_slug") for d in sidecar["departments"] if isinstance(d, dict)}
    for entry in legacy_depts:
        if isinstance(entry, dict) and entry.get("dept_slug") not in seen:
            sidecar["departments"].append(entry)
            seen.add(entry.get("dept_slug"))

    # Preserve any non-"departments" keys the legacy block carried.
    if isinstance(root_reg, dict):
        for k, v in root_reg.items():
            if k != "departments" and k not in sidecar:
                sidecar[k] = v

    sidecar.setdefault("_migrated_from_root_at", datetime.now(timezone.utc).isoformat())

    if dry_run:
        info("[DRY-RUN] Would migrate root extension_registry into the sidecar "
             "and delete it from openclaw.json.")
        return sidecar

    # 1) Write the merged sidecar first (so data is never lost if step 2 fails).
    _atomic_write_json(registry_path, sidecar)
    # 2) Remove the root key from openclaw.json via a safe atomic round-trip.
    del config["extension_registry"]
    _atomic_write_json(config_path, config)
    info(f"MIGRATION complete: openclaw.json root is clean; ledger now at {registry_path}")
    return sidecar


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a department into the routing extension ledger")
    parser.add_argument("--dept",       required=True, help="Department slug")
    parser.add_argument("--config",     required=True, help="Path to openclaw.json")
    parser.add_argument("--registry",   default=None,
                        help="Path to the sidecar extension-registry.json "
                             "(default: <config-dir>/extension-registry.json)")
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
        home = Path(os.environ.get("HOME", "/tmp"))
        candidates = [
            script_dir / "../../23-ai-workforce-blueprint/department-naming-map.json",
            home / ".openclaw/skills/23-ai-workforce-blueprint/department-naming-map.json",
            Path("/data/.openclaw/skills/23-ai-workforce-blueprint/department-naming-map.json"),
            home / "Downloads/openclaw-onboarding/23-ai-workforce-blueprint/department-naming-map.json",
            home / "Downloads/openclaw-master-files/23-ai-workforce-blueprint/department-naming-map.json",
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

    # Build slug -> metadata index.  The naming map stores depts as DICTS keyed
    # by slug (not arrays), and vertical_packs nests depts inside each pack's
    # auto_add_departments list.  Handle both forms so mandatory (dict-keyed)
    # and vertical-pack entries (list with "id") are found without crashing.
    dept_meta: dict = {}

    # mandatory: dict keyed by slug (entry carries no slug/id field)
    mandatory = naming_map.get("mandatory", {})
    if isinstance(mandatory, dict):
        for slug, entry in mandatory.items():
            if isinstance(entry, dict):
                dept_meta[slug] = entry
    elif isinstance(mandatory, list):          # tolerate legacy array form
        for entry in mandatory:
            s = entry.get("slug") or entry.get("id")
            if s:
                dept_meta[s] = entry

    # vertical_packs: dict of packs, each with auto_add_departments[] carrying "id"
    packs = naming_map.get("vertical_packs", {})
    pack_iter = packs.values() if isinstance(packs, dict) else packs
    for pack in pack_iter:
        for entry in (pack.get("auto_add_departments", []) if isinstance(pack, dict) else []):
            s = entry.get("id") or entry.get("slug")
            if s:
                dept_meta[s] = entry

    if args.dept not in dept_meta:
        die(f"Department '{args.dept}' not found in naming map at {naming_map_path}")

    meta = dept_meta[args.dept]
    director_title = meta.get("director_title") or meta.get("head", "Director")
    emoji = meta.get("emoji", "")
    # human name lives in display_name (mandatory) or name (vertical-pack entries)
    description = (meta.get("description") or meta.get("one_liner")
                   or meta.get("display_name") or meta.get("name")
                   or f"{args.dept} department")

    info(f"Dept: {args.dept} | Director: {director_title} | Emoji: {emoji}")

    # ── Resolve config + sidecar paths ───────────────────────────────────────
    config_path = Path(args.config)
    if not config_path.exists():
        die(f"openclaw.json not found at {args.config}")

    registry_path = Path(args.registry) if args.registry else default_registry_path(config_path)

    # ── SELF-HEAL: migrate any legacy root extension_registry → sidecar ──────
    # (Removes the root key that breaks `openclaw config validate` on 2026.6.8+.)
    registry = migrate_root_registry(config_path, registry_path, args.dry_run)

    # ── Idempotency: already registered? ─────────────────────────────────────
    # 1) An agent whose id contains the dept slug means the dept is live already.
    try:
        config = _load_json(config_path)
    except Exception as e:
        die(f"Cannot parse openclaw.json: {e}")
    agents_list = config.get("agents", {}).get("list", [])
    for agent in agents_list:
        if isinstance(agent, dict) and args.dept in str(agent.get("id", "")):
            info(f"Department '{args.dept}' already registered (agent id: {agent.get('id')}). Skipping.")
            sys.exit(0)

    # 2) Already in the sidecar ledger.
    for existing in registry["departments"]:
        if isinstance(existing, dict) and existing.get("dept_slug") == args.dept:
            info(f"Department '{args.dept}' already in extension-registry sidecar. Skipping.")
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

    registry["departments"].append(new_routing_entry)

    if args.dry_run:
        info(f"[DRY-RUN] Would add to extension-registry sidecar ({registry_path}):")
        print(json.dumps(new_routing_entry, indent=2))
        sys.exit(0)

    # ── Write the sidecar ledger (atomic; NEVER touches openclaw.json root) ──
    try:
        _atomic_write_json(registry_path, registry)
    except Exception as e:
        die(f"Write failed for sidecar {registry_path}: {e}")

    info(f"Registered '{args.dept}' into extension-registry sidecar at {registry_path}")
    info("openclaw.json root left untouched (config validate stays VALID).")


if __name__ == "__main__":
    main()
