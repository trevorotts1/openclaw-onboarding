#!/usr/bin/env python3
"""
persona_embedding_drift_probe.py — A-U8 (Skill 6 v2) scheduled live drift check.

OPERATOR-SIDE ONLY. Mirrors fleet-heartbeat-persona-probe.sh's doctrine: this
probe performs NO messaging of any kind. It writes a report to stdout/JSON and
sets an exit code; the fleet heartbeat / operator living-status doc (which
already reads shared-utils/embedding_health.py and
fleet-heartbeat-persona-probe.sh the same way) decides where the operator
sees it. MUST NEVER be wired to a client-visible channel (Telegram/GHL).

WHAT IT CHECKS
--------------
Compares the personas/ directory on disk (this box's live workspace) against
the gemini-index.sqlite embedding index. A persona present on disk that is
NEITHER indexed NOR covered by an honest embedding-receipt.json (status
'deferred' — written by 22-.../pipeline/orchestrator.py Phase 5 when this
box's own Gemini key is absent/invalid, see A-U8) is UNEXPLAINED drift. A
deferred persona is an EXPECTED, already-receipted state — never flagged.

Emits exactly ONE card/alert record per run (never one per persona) so a
seeded N-persona divergence surfaces as ONE operator signal, not a flood.

Usage:
    persona_embedding_drift_probe.py [--personas-dir DIR] [--db PATH]
                                      [--box LABEL] [--json]

Exit codes:
    0  healthy   — no unexplained divergence
    1  degraded  — unexplained disk-vs-index divergence (operator card)
    2  n/a       — personas dir not found on this box (not yet provisioned)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

try:
    from detect_platform import get_openclaw_paths as _get_paths
except Exception:  # pragma: no cover — graceful fallback, mirrors embedding_engine.py
    _get_paths = None


def _default_personas_and_db() -> tuple:
    """Resolve the canonical live personas dir + gemini-index.sqlite path,
    mirroring embedding_engine.py's own resolution so this probe can never
    disagree with what search()/cmd_index() actually read/write."""
    if _get_paths is not None:
        try:
            paths = _get_paths()
            coaching_personas = Path(paths["coaching_personas"])
            return coaching_personas / "personas", Path(paths["gemini_index"])
        except (Exception, SystemExit):
            pass
    workspace_root = Path(os.environ.get(
        "WORKSPACE_ROOT", os.path.expanduser("~/.openclaw/workspace")))
    coaching_personas = workspace_root / "data" / "coaching-personas"
    return coaching_personas / "personas", coaching_personas / "gemini-index.sqlite"


def _persona_name_from_file_path(file_path: str) -> str:
    return Path(file_path).parent.name


def _disk_slugs(personas_dir: Path) -> set:
    if not personas_dir.is_dir():
        return set()
    return {p.name for p in personas_dir.iterdir()
            if p.is_dir() and (p / "persona-blueprint.md").is_file()}


def _deferred_slugs(personas_dir: Path) -> set:
    out = set()
    if not personas_dir.is_dir():
        return out
    for p in personas_dir.iterdir():
        receipt = p / "embedding-receipt.json"
        if not receipt.is_file():
            continue
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("status") == "deferred":
            out.add(p.name)
    return out


def _indexed_slugs(db_path: Path) -> set:
    if not db_path.is_file():
        return set()
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT file_path FROM embeddings "
            "WHERE file_path LIKE '%coaching-personas/personas/%'"
        )
        rows = cur.fetchall()
        conn.close()
    except sqlite3.Error:
        return set()
    return {_persona_name_from_file_path(r[0]) for r in rows}


def _hostname() -> str:
    try:
        import socket
        return socket.gethostname().split(".")[0]
    except Exception:
        return "unknown"


def run_drift_check(personas_dir: Optional[Path] = None,
                     db_path: Optional[Path] = None,
                     box: Optional[str] = None) -> dict:
    """The one entry point. Returns EXACTLY ONE result dict — never a
    per-persona list — regardless of how many personas are missing. This is
    what makes a seeded N-persona divergence surface as ONE operator card
    (A-U8 acceptance (d)), not a flood."""
    default_personas, default_db = _default_personas_and_db()
    personas_dir = Path(personas_dir) if personas_dir else default_personas
    db_path = Path(db_path) if db_path else default_db
    box = box or os.environ.get("OPENCLAW_BOX_LABEL") or _hostname()

    base = {
        "probe": "persona-embedding-drift",
        "box": box,
        "personas_dir": str(personas_dir),
        "db_path": str(db_path),
        "operator_side_only": True,
    }

    if not personas_dir.is_dir():
        base.update({
            "verdict": "n/a",
            "reason": f"personas dir not found: {personas_dir} (not yet provisioned on this box)",
        })
        return base

    disk = _disk_slugs(personas_dir)
    indexed = _indexed_slugs(db_path)
    deferred = _deferred_slugs(personas_dir)
    accounted = indexed | deferred
    missing = sorted(disk - accounted)

    base.update({
        "disk_count": len(disk),
        "indexed_count": len(indexed),
        "deferred_count": len(deferred),
        "missing_count": len(missing),
        "missing_personas": missing[:50],
    })

    if missing:
        base["verdict"] = "degraded"
        shown = ", ".join(missing[:10]) + (" ..." if len(missing) > 10 else "")
        base["message"] = (
            f"{len(missing)} persona(s) on disk are neither indexed nor "
            f"covered by an honest embedding-receipt.json deferred marker: "
            f"{shown}"
        )
    else:
        base["verdict"] = "healthy"
        base["message"] = (
            f"{len(disk)} persona(s) on disk, {len(indexed)} indexed, "
            f"{len(deferred)} honestly deferred — no unexplained divergence"
        )
    return base


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--personas-dir", default=None,
                    help="Explicit personas dir (default: canonical live "
                         "coaching-personas/personas)")
    ap.add_argument("--db", default=None,
                    help="Explicit gemini-index.sqlite path (default: canonical "
                         "live index)")
    ap.add_argument("--box", default=None, help="Box label override")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = run_drift_check(
        personas_dir=Path(args.personas_dir) if args.personas_dir else None,
        db_path=Path(args.db) if args.db else None,
        box=args.box,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"── persona-embedding-drift probe [box: {result['box']}] ──")
        print(f"  verdict: {result['verdict']}")
        print(f"  {result.get('message', result.get('reason', ''))}")
        print("  (operator-side only — this probe sends no messages)")

    exit_map = {"healthy": 0, "degraded": 1, "n/a": 2}
    sys.exit(exit_map.get(result["verdict"], 1))


if __name__ == "__main__":
    main()
