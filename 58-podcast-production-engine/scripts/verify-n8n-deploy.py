#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: n8n deployment drift detector (onb-4)
# -----------------------------------------------------------------------------
# READ-ONLY reconciliation against the live n8n instance. For each workflow
# exported under config/n8n/*.workflow.json, find the live counterpart by
# webhook path or name, compare node count, connection count, active state,
# and webhook paths; print a per-workflow MATCH/DRIFT report.
#
# Exit codes:
#   0 = all checked workflows MATCH
#   1 = one or more DRIFT
#   2 = n8n instance unreachable (non-fatal)
#
# Secrets by label only -- the API key is read from N8N_API_KEY env and NEVER
# printed. Deterministic; no model calls.
#
# Usage:
#   N8N_API_URL=https://main.blackceoautomations.com/api/v1 \
#   N8N_API_KEY=... \
#   python3 scripts/verify-n8n-deploy.py [--config-dir config/n8n]
# =============================================================================
"""n8n deployment drift detector -- read-only reconciliation (onb-4)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any


def _redacted(val: str) -> str:
    """Return a safe label for a secret -- never the value."""
    if not val:
        return "(not set)"
    return f"[{len(val)} chars, set]"


def _call_n8n_api(
    api_url: str,
    api_key: str,
    path: str,
    *,
    timeout: int = 15,
) -> tuple[int, Any]:
    """Call the n8n REST API and return (status, parsed JSON or error dict).

    Returns (0, data) on success, (status, {"error": msg}) on failure.
    """
    url = f"{api_url.rstrip('/')}/{path.lstrip('/')}"
    req = urllib.request.Request(url)
    req.add_header("X-N8N-API-KEY", api_key)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return (0, json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as exc:
        return (exc.code, {"error": f"HTTP {exc.code}: {exc.reason}"})
    except urllib.error.URLError as exc:
        return (-1, {"error": f"connection failed: {exc.reason}"})
    except OSError as exc:
        return (-1, {"error": f"network error: {exc}"})


def _extract_webhook_paths(workflow: dict) -> list[str]:
    """Extract webhook paths from a workflow dict (nodes array)."""
    paths: list[str] = []
    for node in workflow.get("nodes", []):
        if node.get("type") == "n8n-nodes-base.webhook":
            p = node.get("parameters", {}).get("path", "").strip()
            if p:
                paths.append(p)
    return sorted(paths)


def _count_connections(workflow: dict) -> int:
    """Count connection keys in a workflow dict."""
    conns = workflow.get("connections", {})
    if isinstance(conns, dict):
        return len(conns)
    return 0


def _find_live_workflow(
    live_workflows: list[dict],
    exported_workflow: dict,
) -> dict | None:
    """Find the live workflow that matches an exported one.

    Matches in priority order:
      1. By webhook path (any exported webhook path === any live webhook path)
      2. By name (case-insensitive)
    """
    exported_paths = set(_extract_webhook_paths(exported_workflow))
    exported_name = (exported_workflow.get("name") or "").strip().lower()

    # Priority 1: webhook path match
    if exported_paths:
        for live in live_workflows:
            live_paths = set(_extract_webhook_paths(live))
            if exported_paths & live_paths:
                return live

    # Priority 2: name match
    if exported_name:
        for live in live_workflows:
            live_name = (live.get("name") or "").strip().lower()
            if live_name == exported_name:
                return live

    return None


def _load_workflow_file(filepath: Path) -> dict | None:
    """Load a workflow JSON file, returning None on parse failure."""
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError) as exc:
        print(f"  SKIP -- cannot parse {filepath.name}: {exc}", file=sys.stderr)
        return None


def _report(label: str, status: str, details: str) -> int:
    """Print a per-workflow line and return the exit-significant code.

    status is one of MATCH, DRIFT, SKIP.
    Returns 0 for MATCH/SKIP, 1 for DRIFT, 2 for unreachable.
    """
    marker = {"MATCH": "\033[32mMATCH\033[0m",
              "DRIFT": "\033[31mDRIFT\033[0m",
              "SKIP": "\033[33mSKIP\033[0m",
              "UNREACHABLE": "\033[33mUNREACHABLE\033[0m"}.get(status, status)
    print(f"  [{marker}] {label} -- {details}")
    if status == "DRIFT":
        return 1
    if status == "UNREACHABLE":
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="n8n deployment drift detector -- read-only reconciliation (onb-4)"
    )
    p.add_argument(
        "--config-dir",
        default=None,
        help="directory containing *.workflow.json files (default: <script_dir>/../config/n8n)",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="API request timeout in seconds (default: 15)",
    )
    args = p.parse_args(argv)

    # Resolve config directory
    if args.config_dir:
        config_dir = Path(args.config_dir)
    else:
        script_dir = Path(__file__).resolve().parent
        config_dir = script_dir.parent / "config" / "n8n"

    # Environment
    api_url = os.environ.get("N8N_API_URL", "").strip()
    api_key = os.environ.get("N8N_API_KEY", "").strip()

    if not api_url or not api_key:
        print(
            f"N8N_API_URL={_redacted(api_url)} N8N_API_KEY={_redacted(api_key)} "
            f"-- both must be set; cannot verify n8n deployment",
            file=sys.stderr,
        )
        return 2

    # Discover exported workflows
    workflow_files = sorted(config_dir.glob("*.workflow.json"))
    if not workflow_files:
        print(f"No *.workflow.json files found in {config_dir}", file=sys.stderr)
        return 2

    # Fetch live workflow list from n8n
    print(f"n8n deployment drift check -- {api_url} (API key {_redacted(api_key)})")
    print(f"Comparing {len(workflow_files)} exported workflow(s) against live instance\n")

    code, data = _call_n8n_api(api_url, api_key, "/workflows", timeout=args.timeout)
    if code != 0:
        print(f"UNREACHABLE -- cannot fetch live workflows: {data.get('error', 'unknown error')}")
        return 2
    live_workflows: list[dict] = data.get("data", []) if isinstance(data, dict) else []

    print(f"Live instance has {len(live_workflows)} workflow(s)\n")

    exit_code = 0

    for wf_file in workflow_files:
        label = wf_file.name

        exported = _load_workflow_file(wf_file)
        if exported is None:
            exit_code = max(exit_code, 1)
            continue

        live = _find_live_workflow(live_workflows, exported)

        if live is None:
            exported_name = exported.get("name", "(unnamed)")
            exported_paths = _extract_webhook_paths(exported)
            exported_webhook = f"webhook(s): {', '.join(exported_paths)}" if exported_paths else "no webhook"
            exit_code = max(
                exit_code,
                _report(label, "DRIFT",
                        f"not found on live instance (exported name='{exported_name}', {exported_webhook})"),
            )
            continue

        # Compare structural properties
        exported_nodes = len(exported.get("nodes", []))
        exported_conns = _count_connections(exported)
        exported_active = bool(exported.get("active", False))
        exported_paths = _extract_webhook_paths(exported)

        live_nodes = len(live.get("nodes", []))
        live_conns = _count_connections(live)
        live_active = bool(live.get("active", False))
        live_paths = _extract_webhook_paths(live)

        diffs: list[str] = []
        if exported_nodes != live_nodes:
            diffs.append(f"nodes: exported={exported_nodes} live={live_nodes}")
        if exported_conns != live_conns:
            diffs.append(f"connections: exported={exported_conns} live={live_conns}")
        if exported_active != live_active:
            diffs.append(f"active: exported={exported_active} live={live_active}")
        if exported_paths != live_paths:
            diffs.append(f"webhooks: exported={exported_paths} live={live_paths}")

        if diffs:
            exit_code = max(exit_code, _report(label, "DRIFT", "; ".join(diffs)))
        else:
            exit_code = max(
                exit_code,
                _report(label, "MATCH",
                        f"nodes={exported_nodes} connections={exported_conns} "
                        f"active={exported_active} webhooks={exported_paths}"),
            )

    print(f"\nResult: exit {exit_code} "
          f"({'MATCH' if exit_code == 0 else 'DRIFT' if exit_code == 1 else 'UNREACHABLE'})")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
