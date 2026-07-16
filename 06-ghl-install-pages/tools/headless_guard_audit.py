#!/usr/bin/env python3
"""headless_guard_audit.py — U28 (B-U14): static D6 coverage audit of every
Skill-6 browser-LAUNCH site.

WHY THIS EXISTS
----------------
``browser_manager.py`` claims (its own module docstring): "ghl_builder.py and
ghl_rest_canvas.py are pure EMITTERS ... no chromium.launch / launchPersistent
Context anywhere in the repo Python." B-U14's own spec text says this same
class of claim was "UNVERIFIED until the audit runs" for the form/survey/
iframe-drag paths. This module is that audit, run PROGRAMMATICALLY (AST, not
a hand-maintained table) so it cannot silently go stale the way the prior
claim did.

WHAT COUNTS AS A "LAUNCH SITE"
-------------------------------
Two distinct things, both audited:

  1. ``browser_manager.browser_session(...)`` calls — the SINGLETON POOLED
     BROWSER chokepoint every builder (community/course/pipeline/form/survey)
     funnels through. ``browser_session()`` calls ``headless_guard()`` as its
     OWN first statement (browser_manager.py, verified at the pinned line the
     ``chokepoint_guarded()`` check below re-verifies every run) — so a call
     SITE is safe-by-construction as long as the chokepoint itself still
     guards. This audit both (a) re-verifies the chokepoint invariant and
     (b) enumerates every call site, so a future refactor that bypasses the
     chokepoint (calls a browser directly, skipping ``browser_session()``)
     cannot land silently.

  2. Raw Playwright ``chromium.launch(...)`` / ``chromium.launch_persistent_
     context(...)`` calls — the ONE class of call that can open a browser
     WITHOUT going through the chokepoint at all. Grounded finding (this
     audit, 2026-07): exactly one such site exists,
     ``ghl_iframe_drag.py``'s offline cross-origin-drag self-test, which
     hardcodes ``headless=True`` as a Python literal (never reads
     ``AGENT_BROWSER_HEADED``) — COMPLIANT-BY-CONSTRUCTION, listed rather than
     silently exempted. Any NEW raw launch site without a literal
     ``headless=True`` is a GAP.

WHAT THIS DOES **NOT** CLAIM
-----------------------------
This is a same-function, lineno-order static sweep (AST, not a real
control-flow analysis) — it can be fooled by a launch inside a nested
closure defined earlier but called later, or by a guard call that is itself
unreachable. It is a coverage FLOOR (matches the house style of the existing
static guard tests in tests/test_browser_manager_singleton.py), not a proof
of runtime correctness — the dynamic exit-75 CI test
(tests/test_u28_headless_guard_coverage.py) is what proves the RUNTIME
contract for the CLI entry points.

Run directly: prints the audit table as JSON. ``--check`` exits 1 if any site
is an uncovered GAP (never exits non-zero for a merely-informational site).
"""
from __future__ import annotations

import argparse
import ast
import glob
import json
import os
import sys
from typing import Any, Dict, List, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

# Directories under tools/ that hold fixtures/examples, never launch sites of
# their own — excluded so the sweep stays signal, not noise.
_EXCLUDE_DIRNAMES = {"examples", "__pycache__"}

_HEADLESS_GUARD_NAMES = {"headless_guard"}
_BROWSER_SESSION_ATTR = "browser_session"
_CHROMIUM_LAUNCH_ATTRS = {"launch", "launch_persistent_context"}


def _iter_tool_files() -> List[str]:
    files = []
    for path in sorted(glob.glob(os.path.join(_TOOLS_DIR, "*.py"))):
        files.append(path)
    for sub in sorted(os.listdir(_TOOLS_DIR)):
        subdir = os.path.join(_TOOLS_DIR, sub)
        if os.path.isdir(subdir) and sub not in _EXCLUDE_DIRNAMES:
            for path in sorted(glob.glob(os.path.join(subdir, "*.py"))):
                files.append(path)
    return files


def _call_attr_name(node: ast.Call) -> Optional[str]:
    """Return the attribute name of a ``Call`` whose func is ``x.attr(...)``,
    or the bare name for ``attr(...)``. None for anything else."""
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return None


def _call_chain_source(node: ast.Call) -> str:
    """Best-effort textual reconstruction of the call target (e.g.
    'p.chromium.launch_persistent_context') without requiring ast.unparse
    (Python < 3.9 fallback)."""
    try:
        return ast.unparse(node.func)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — ast.unparse is 3.9+; fall back below
        parts: List[str] = []
        cur: Any = node.func
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))


def _has_literal_headless_true(node: ast.Call) -> bool:
    for kw in node.keywords:
        if kw.arg == "headless" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


def _functions_in(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def audit_file(path: str) -> List[Dict[str, Any]]:
    """Return one audit-table row per launch site found in ``path``."""
    rel = os.path.relpath(path, os.path.dirname(_TOOLS_DIR))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src, filename=path)
    except (OSError, SyntaxError) as exc:
        return [{"file": rel, "line": 0, "site": "(parse error)", "kind": "ERROR",
                 "status": "GAP", "detail": str(exc)}]

    rows: List[Dict[str, Any]] = []
    for fn in _functions_in(tree):
        calls = sorted(
            (n for n in ast.walk(fn) if isinstance(n, ast.Call)),
            key=lambda n: (n.lineno, n.col_offset),
        )
        guard_linenos = [
            c.lineno for c in calls if _call_attr_name(c) in _HEADLESS_GUARD_NAMES
        ]
        for c in calls:
            attr = _call_attr_name(c)
            chain = _call_chain_source(c)
            is_session = attr == _BROWSER_SESSION_ATTR and "browser_session" in chain
            is_raw_launch = attr in _CHROMIUM_LAUNCH_ATTRS and "chromium" in chain
            if not (is_session or is_raw_launch):
                continue
            preceding_guard = any(g < c.lineno for g in guard_linenos)
            if is_session:
                # Self-guarded by construction: browser_session() calls
                # headless_guard() as its own first statement (re-verified by
                # chokepoint_guarded() below) — every call site is safe
                # regardless of whether the CALLER also re-guards.
                status = "COVERED (chokepoint self-guards)"
                if preceding_guard:
                    status = "COVERED (explicit + chokepoint)"
            elif _has_literal_headless_true(c):
                status = "COMPLIANT-BY-CONSTRUCTION (headless=True literal)"
            elif preceding_guard:
                status = "COVERED (explicit guard precedes)"
            else:
                status = "GAP"
            rows.append({
                "file": rel, "line": c.lineno, "function": fn.name,
                "site": chain, "kind": "browser_session" if is_session else "raw_chromium_launch",
                "status": status,
            })
    return rows


def chokepoint_guarded() -> Dict[str, Any]:
    """Re-verify the ROOT invariant every call-site COVERED verdict depends
    on: ``browser_manager.browser_session()``'s own body calls
    ``headless_guard()`` before it does anything else browser-related."""
    path = os.path.join(_TOOLS_DIR, "browser_manager.py")
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "browser_session":
            calls = sorted(
                (n for n in ast.walk(node) if isinstance(n, ast.Call)),
                key=lambda n: (n.lineno, n.col_offset),
            )
            for c in calls:
                if _call_attr_name(c) in _HEADLESS_GUARD_NAMES:
                    return {"ok": True, "file": "06-ghl-install-pages/tools/browser_manager.py",
                            "function": "browser_session", "guard_line": c.lineno}
            return {"ok": False, "file": "06-ghl-install-pages/tools/browser_manager.py",
                    "function": "browser_session",
                    "detail": "browser_session() no longer calls headless_guard()"}
    return {"ok": False, "detail": "browser_session() not found in browser_manager.py"}


def build_audit_table() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for path in _iter_tool_files():
        rows.extend(audit_file(path))
    chokepoint = chokepoint_guarded()
    gaps = [r for r in rows if r["status"] == "GAP"]
    return {
        "chokepoint": chokepoint,
        "launch_sites": rows,
        "gap_count": len(gaps),
        "gaps": gaps,
        "ok": chokepoint.get("ok", False) and not gaps,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="headless_guard_audit",
        description="U28 (B-U14): static D6 headless-guard coverage audit of every "
                    "Skill-6 browser-launch site.",
    )
    p.add_argument("--check", action="store_true",
                   help="Exit 1 if the chokepoint invariant fails or any site is a GAP.")
    args = p.parse_args(argv)
    table = build_audit_table()
    print(json.dumps(table, indent=2))
    if args.check and not table["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
