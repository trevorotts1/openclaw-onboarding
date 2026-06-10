#!/usr/bin/env python3
"""
resolve_injected_core_files.py — PRD 1.11 Layer-3 prevention helper.

The ONE sanctioned way any script learns where to write CEO / agent core files.

WHY this exists (the duck-saga v11.3.2 bug):
    build-workforce.py was writing the PRIME DIRECTIVE to
    DEPARTMENTS_DIR/ceo/SOUL.md (the dept-ceo *sub-agent* workspace).
    The gateway injects the MAIN agent's workspace/SOUL.md — a different path.
    The directive was on disk but never in context (Layer-3 failure).

    This helper encodes the correct 3-step resolution priority once, here.
    Every script that writes CEO/agent core files MUST use the paths returned
    by this function rather than constructing paths itself.

The 3-step injected-workspace priority (mirrors the OpenClaw gateway):
    1. openclaw.json agents.list[id==agent_id].workspace  (per-agent override)
    2. openclaw.json agents.defaults.workspace             (fleet default)
    3. <openclaw_root>/workspace                           (canonical default)

Usage:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))   # shared-utils
    from resolve_injected_core_files import resolve_injected_core_files

    paths = resolve_injected_core_files("main")
    # Write the CEO directive to paths["soul_md"] — always correct.

IMPORTANT: this is DISTINCT from a department/sub-agent workspace
    (DEPARTMENTS_DIR/<dept>/SOUL.md). Writing to a dept workspace was the
    v11.3.2 Layer-3 bug. Any script affecting what the MAIN agent loads MUST
    use the paths returned here.

PRD 1.11 — v11.5.0
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_injected_core_files(
    agent_id: str = "main",
    openclaw_config: Optional[Path] = None,
    openclaw_root: Optional[Path] = None,
) -> dict:
    """
    Return the gateway-INJECTED bootstrap file paths for an agent — i.e. the
    files the gateway actually reads into the system prompt — resolved per
    platform and per openclaw.json, NEVER guessed.

    Injected workspace resolution (the 3-step priority that the gateway uses):
        1. openclaw.json agents.list[id==agent_id].workspace  (per-agent override, expanduser)
        2. openclaw.json agents.defaults.workspace             (expanduser)
        3. <openclaw_root>/workspace                           (canonical default;
                                                               root from detect_platform or env)

    Args:
        agent_id:        The agent to resolve for (default: "main").
        openclaw_config: Path to openclaw.json. If None, auto-detected.
        openclaw_root:   Path to the .openclaw root dir. If None, auto-detected.

    Returns:
        {
          "agent_id":    "main",
          "workspace":   Path(...),          # the injected workspace dir
          "soul_md":     workspace/"SOUL.md",
          "identity_md": workspace/"IDENTITY.md",
          "memory_md":   workspace/"MEMORY.md",
          "agents_md":   workspace/"AGENTS.md",
          "tools_md":    workspace/"TOOLS.md",
          "user_md":     workspace/"USER.md",
          "heartbeat_md":workspace/"HEARTBEAT.md",
          "resolved_from": "agents.list[main].workspace"
                         | "agents.defaults.workspace"
                         | "default"
        }

    NOTE: this is DISTINCT from a department/sub-agent workspace
    (DEPARTMENTS_DIR/<dept>/SOUL.md). Writing a CEO directive to a dept-ceo
    workspace was the v11.3.2 duck-saga Layer-3 bug. Any script that needs to
    affect what the MAIN agent loads MUST use the paths returned here.
    """
    # --- Step 0: resolve config path ---
    if openclaw_config is None:
        openclaw_config = _find_openclaw_config(openclaw_root)

    # --- Step 0b: resolve root ---
    if openclaw_root is None:
        openclaw_root = _find_openclaw_root()

    workspace: Optional[Path] = None
    resolved_from = "default"

    # --- Step 1: per-agent workspace override ---
    if openclaw_config is not None and openclaw_config.is_file():
        try:
            cfg = json.loads(openclaw_config.read_text())
            for ag in (cfg.get("agents", {}).get("list") or []):
                if isinstance(ag, dict) and ag.get("id") == agent_id:
                    ws_str = ag.get("workspace")
                    if ws_str:
                        workspace = Path(os.path.expanduser(ws_str))
                        resolved_from = f"agents.list[{agent_id}].workspace"
                    break
        except Exception:
            pass

    # --- Step 2: agents.defaults.workspace ---
    if workspace is None and openclaw_config is not None and openclaw_config.is_file():
        try:
            cfg = json.loads(openclaw_config.read_text())
            dw = cfg.get("agents", {}).get("defaults", {}).get("workspace")
            if dw:
                workspace = Path(os.path.expanduser(dw))
                resolved_from = "agents.defaults.workspace"
        except Exception:
            pass

    # --- Step 3: canonical default ---
    if workspace is None:
        workspace = openclaw_root / "workspace"
        resolved_from = "default"

    workspace = workspace.resolve() if workspace.exists() else workspace

    # Build return dict
    result = {
        "agent_id":     agent_id,
        "workspace":    workspace,
        "soul_md":      workspace / "SOUL.md",
        "identity_md":  workspace / "IDENTITY.md",
        "memory_md":    workspace / "MEMORY.md",
        "agents_md":    workspace / "AGENTS.md",
        "tools_md":     workspace / "TOOLS.md",
        "user_md":      workspace / "USER.md",
        "heartbeat_md": workspace / "HEARTBEAT.md",
        "resolved_from": resolved_from,
    }
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_openclaw_root() -> Path:
    """
    Find the OpenClaw root directory using the same priority as detect_platform.
    Returns the first existing root found; defaults to ~/.openclaw if none exist
    (may not exist yet — caller should handle).
    """
    # FLEET_REFRESH_ROOT env var: allows fixture tests to redirect
    env_root = os.environ.get("FLEET_REFRESH_ROOT", "").strip()
    if env_root:
        return Path(env_root)

    # VPS
    vps = Path("/data/.openclaw")
    if vps.exists():
        return vps

    # Mac new
    mac_new = Path.home() / ".openclaw"
    if mac_new.exists():
        return mac_new

    # Mac legacy
    mac_legacy = Path.home() / "clawd"
    if mac_legacy.exists():
        return mac_legacy

    # Default (may not exist — Step 3 in the caller will use it anyway)
    return Path.home() / ".openclaw"


def _find_openclaw_config(openclaw_root: Optional[Path] = None) -> Optional[Path]:
    """Resolve the path to openclaw.json."""
    # OC_JSON env var (used by apply-fleet-standards.sh and tests)
    env_cfg = os.environ.get("OC_JSON", "").strip()
    if env_cfg:
        p = Path(env_cfg)
        return p if p.is_file() else None

    if openclaw_root is None:
        openclaw_root = _find_openclaw_root()

    candidates = [
        openclaw_root / "openclaw.json",
        openclaw_root / "workspace" / "openclaw.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


# ---------------------------------------------------------------------------
# Thin shim kept for back-compat with build-workforce.py
# ---------------------------------------------------------------------------

def resolve_main_agent_workspace() -> Path:
    """
    Back-compat shim: returns the workspace Path for the 'main' agent.

    build-workforce.py's _resolve_main_agent_workspace() is migrated to call
    this one-liner so there is only one implementation.
    """
    return resolve_injected_core_files("main")["workspace"]


# ---------------------------------------------------------------------------
# CLI self-test / fixture usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("resolve_injected_core_files self-test:")
    paths = resolve_injected_core_files("main")
    for k, v in paths.items():
        print(f"  {k:<15} {v}")

    # Verify 3-step priority respects OC_JSON env var override
    import tempfile, json as _json
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cfg_path = td / "openclaw.json"
        ws_path = td / "custom-workspace"
        ws_path.mkdir()
        cfg_path.write_text(_json.dumps({
            "agents": {
                "defaults": {"workspace": str(ws_path)},
                "list": []
            }
        }))
        os.environ["OC_JSON"] = str(cfg_path)
        result = resolve_injected_core_files("main")
        # Use .resolve() to normalize macOS /var→/private/var symlinks
        assert result["workspace"].resolve() == ws_path.resolve(), \
            f"Expected {ws_path}, got {result['workspace']}"
        assert result["resolved_from"] == "agents.defaults.workspace"
        del os.environ["OC_JSON"]

        # Per-agent override wins over defaults
        ws2 = td / "per-agent-workspace"
        ws2.mkdir()
        cfg_path.write_text(_json.dumps({
            "agents": {
                "defaults": {"workspace": str(ws_path)},
                "list": [{"id": "main", "workspace": str(ws2)}]
            }
        }))
        os.environ["OC_JSON"] = str(cfg_path)
        result2 = resolve_injected_core_files("main")
        assert result2["workspace"].resolve() == ws2.resolve(), \
            f"Expected {ws2}, got {result2['workspace']}"
        assert result2["resolved_from"] == "agents.list[main].workspace"
        del os.environ["OC_JSON"]

    print("resolve_injected_core_files self-test PASSED")
