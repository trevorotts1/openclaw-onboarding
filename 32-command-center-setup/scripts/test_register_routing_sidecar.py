#!/usr/bin/env python3
"""
test_register_routing_sidecar.py — regression guard for register-routing-dept.py

THE BUG THIS GUARDS AGAINST (do not let it regress):
    register-routing-dept.py used to append an `extension_registry` block to the
    ROOT of openclaw.json. OpenClaw 2026.6.8 set the root schema to
    `additionalProperties: false`, so that unknown root key makes
    `openclaw config validate` fail ("<root>: Invalid input"), which BLOCKS
    `openclaw message send` (Telegram) on every box where a department was
    registered — a fleet-wide config-breaker.

WHAT THIS ENFORCES:
    1. Registering a department writes ONLY to the sidecar
       (<config-dir>/extension-registry.json), and NEVER adds a root key to
       openclaw.json (the root key set is unchanged after registration).
    2. Idempotency: registering the same dept twice does not duplicate.
    3. Migration / self-heal: a box that already has a root `extension_registry`
       gets it MOVED into the sidecar (merged) and DELETED from the root, so the
       box self-heals on next registration.
    4. The script never executes as root (caller responsibility; we assert the
       data path, not euid).

Run:  python3 -m pytest test_register_routing_sidecar.py -q
   or: python3 test_register_routing_sidecar.py        (no pytest required)
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "register-routing-dept.py"

# A minimal but realistic openclaw.json root + a tiny naming map.
BASE_CONFIG = {
    "meta": {"schema": "openclaw"},
    "agents": {"list": []},
    "models": {},
    "channels": {},
}
NAMING_MAP = {
    "mandatory": {
        "marketing": {"display_name": "Marketing", "director_title": "CMO", "emoji": "📣"},
        "sales": {"display_name": "Sales", "director_title": "CRO", "emoji": "💼"},
    },
    "vertical_packs": {},
}


def _run(config_path, registry_path, naming_map_path, dept, *extra):
    cmd = [
        sys.executable, str(SCRIPT),
        "--dept", dept,
        "--config", str(config_path),
        "--registry", str(registry_path),
        "--naming-map", str(naming_map_path),
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def _setup(tmp, config_overrides=None):
    tmp = Path(tmp)
    config_path = tmp / "openclaw.json"
    registry_path = tmp / "extension-registry.json"
    naming_map_path = tmp / "department-naming-map.json"
    cfg = json.loads(json.dumps(BASE_CONFIG))
    if config_overrides:
        cfg.update(config_overrides)
    config_path.write_text(json.dumps(cfg, indent=2))
    naming_map_path.write_text(json.dumps(NAMING_MAP, indent=2))
    return config_path, registry_path, naming_map_path


def test_register_writes_sidecar_not_root():
    """Registration writes the sidecar and adds NO root key to openclaw.json."""
    with tempfile.TemporaryDirectory() as tmp:
        config_path, registry_path, naming_map_path = _setup(tmp)
        root_keys_before = set(json.loads(config_path.read_text()).keys())

        res = _run(config_path, registry_path, naming_map_path, "marketing")
        assert res.returncode == 0, f"exit {res.returncode}\n{res.stderr}"

        # The openclaw.json ROOT must be unchanged (no extension_registry, no new key).
        cfg_after = json.loads(config_path.read_text())
        assert "extension_registry" not in cfg_after, "regression: root extension_registry was written"
        assert set(cfg_after.keys()) == root_keys_before, (
            f"regression: openclaw.json root key set changed: "
            f"{set(cfg_after.keys()) ^ root_keys_before}"
        )

        # The sidecar holds the entry.
        assert registry_path.exists(), "sidecar registry was not created"
        sidecar = json.loads(registry_path.read_text())
        slugs = [d.get("dept_slug") for d in sidecar["departments"]]
        assert slugs == ["marketing"], slugs


def test_idempotent_no_duplicate():
    """Registering twice does not duplicate and still adds no root key."""
    with tempfile.TemporaryDirectory() as tmp:
        config_path, registry_path, naming_map_path = _setup(tmp)
        assert _run(config_path, registry_path, naming_map_path, "sales").returncode == 0
        assert _run(config_path, registry_path, naming_map_path, "sales").returncode == 0
        sidecar = json.loads(registry_path.read_text())
        slugs = [d.get("dept_slug") for d in sidecar["departments"]]
        assert slugs == ["sales"], f"duplicate written: {slugs}"
        assert "extension_registry" not in json.loads(config_path.read_text())


def test_migration_self_heals_legacy_root_block():
    """A box with a legacy root extension_registry self-heals: the block is
    MOVED to the sidecar (merged) and DELETED from openclaw.json root."""
    legacy = {
        "extension_registry": {
            "departments": [
                {"dept_slug": "legacy-dept", "director_title": "Old Director"}
            ]
        }
    }
    with tempfile.TemporaryDirectory() as tmp:
        config_path, registry_path, naming_map_path = _setup(tmp, config_overrides=legacy)
        # Sanity: the legacy root key is present before we run.
        assert "extension_registry" in json.loads(config_path.read_text())

        res = _run(config_path, registry_path, naming_map_path, "marketing")
        assert res.returncode == 0, f"exit {res.returncode}\n{res.stderr}"
        assert "MIGRATION" in (res.stdout + res.stderr)

        # Root is now clean.
        cfg_after = json.loads(config_path.read_text())
        assert "extension_registry" not in cfg_after, "migration did not delete root key"

        # Sidecar carries BOTH the migrated legacy dept AND the newly registered one.
        sidecar = json.loads(registry_path.read_text())
        slugs = {d.get("dept_slug") for d in sidecar["departments"]}
        assert {"legacy-dept", "marketing"} <= slugs, f"sidecar missing entries: {slugs}"


def test_dry_run_writes_nothing():
    """--dry-run must not create the sidecar nor mutate openclaw.json."""
    with tempfile.TemporaryDirectory() as tmp:
        config_path, registry_path, naming_map_path = _setup(tmp)
        before = config_path.read_text()
        res = _run(config_path, registry_path, naming_map_path, "marketing", "--dry-run")
        assert res.returncode == 0, res.stderr
        assert not registry_path.exists(), "dry-run created the sidecar"
        assert config_path.read_text() == before, "dry-run mutated openclaw.json"


def _main():
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS: {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL: {name}: {e}", file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"ERROR: {name}: {e}", file=sys.stderr)
    if failures:
        print(f"\n{failures} test(s) failed", file=sys.stderr)
        sys.exit(1)
    print("\nall register-routing sidecar tests passed")


if __name__ == "__main__":
    _main()
