#!/usr/bin/env python3
"""agent_browser_orphan_audit.py — U28 (B-U14) acceptance criterion (d):
"a live Skill-6 fixture run leaves ZERO *.engine descriptors without
matching live processes 10 minutes after completion — PASS/FAIL."

WHAT THIS IS: a READ-ONLY measurement tool, deliberately separate from
scripts/agent-browser-reaper.sh (which REMOVES orphans; this only REPORTS
them). It is meant to be run as a post-build assertion — e.g. ten minutes
after a live Skill-6 fixture build completes — to PROVE the reaper's
guarantee held, rather than to enforce it (the reaper already does that).

MATCHING LOGIC mirrors scripts/agent-browser-reaper.sh's own definition of
"live" so the two tools can never disagree about what counts as orphaned:
  - a ``.engine`` descriptor is NOT orphaned if a lease file for the same
    session name exists under ``$LOCKDIR/leases/`` and has not expired
    (``started_epoch + ttl_sec > now``) — mirrors the reaper's item (1).
  - a ``.engine`` descriptor is NOT orphaned if a Chromium/headless_shell
    process is running with ``--user-data-dir``/``--profile``/
    ``profile-directory`` referencing the agent-browser engine dir or the
    Playwright fallback dir — mirrors the reaper's item (4) scoping (NEVER a
    bare `chrome`/`Chrome`/`Claude` process name).
  - everything else is an ORPHAN, reported by name + age only (never a
    payload/secret dump).

THE LIVE LEG THIS TOOL DOES NOT ITSELF PROVE: running an actual live
Skill-6 fixture build (dispatch -> build -> verify) against a real,
operator-authorized GHL test location, waiting ten minutes, and running this
audit against the box that build ran on. That requires real GHL credentials
and a real test location — genuinely operator-gated, and this repo-side tool
deliberately does not fabricate that run. See the U28 ledger note for the
owed live leg. What IS proven here (test_u28_orphan_descriptor_audit.py):
the matching logic itself, hermetically, against seeded fixtures — the exact
same technique the reaper's own test suite already uses.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _read_lease(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {
            "started_epoch": int(data.get("started_epoch", 0)),
            "ttl_sec": int(data.get("ttl_sec", 1800)),
        }
    except (OSError, ValueError, TypeError):
        return {"started_epoch": 0, "ttl_sec": 1800}


def _live_session_names_from_leases(lease_dir: str, *, now: Optional[float] = None) -> set:
    now = now if now is not None else time.time()
    live: set = set()
    if not os.path.isdir(lease_dir):
        return live
    for name in os.listdir(lease_dir):
        if not name.endswith(".lease"):
            continue
        session = name[: -len(".lease")]
        lease = _read_lease(os.path.join(lease_dir, name))
        started = lease["started_epoch"]
        ttl = lease["ttl_sec"]
        if started > 0 and now <= started + ttl:
            live.add(session)
    return live


def _scoped_chromium_running(
    engine_dir: str,
    playwright_dir: str,
    *,
    ps_output_provider: Optional[Callable[[], str]] = None,
) -> bool:
    """True iff ANY Chromium/headless_shell process references the
    agent-browser engine dir or the Playwright fallback dir in its command
    line — mirrors the reaper's AB_MAX_LIVE scoping (never a bare
    chrome/Chrome/Claude match)."""
    if ps_output_provider is not None:
        out = ps_output_provider()
    else:
        try:
            out = subprocess.run(
                ["ps", "-axww", "-o", "pid=,command="],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            return False
    profile_pat = re.escape(engine_dir)
    if playwright_dir:
        profile_pat = f"({profile_pat}|{re.escape(playwright_dir)})"
    pattern = re.compile(
        r"(--user-data-dir|--profile|profile-directory)[= ]?\S*" + profile_pat,
    )
    chrom_pat = re.compile(r"chrom|headless_shell", re.IGNORECASE)
    for line in out.splitlines():
        if pattern.search(line) and chrom_pat.search(line) and "grep" not in line.lower():
            return True
    return False


def find_orphans(
    *,
    home: Optional[str] = None,
    tmpdir: Optional[str] = None,
    grace_sec: int = 600,
    now: Optional[float] = None,
    ps_output_provider: Optional[Callable[[], str]] = None,
    playwright_dir_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Enumerate ``.engine`` descriptors under ``$HOME/.agent-browser`` and
    classify each as LIVE (matching lease or matching scoped Chromium
    process) or ORPHAN (neither, and older than ``grace_sec`` — default 600s
    = the "10 minutes after completion" window acceptance criterion (d)
    names verbatim)."""
    home = home if home is not None else os.environ.get("HOME", "")
    tmpdir = tmpdir if tmpdir is not None else os.environ.get("TMPDIR", "/tmp")
    now = now if now is not None else time.time()

    engine_dir = os.path.join(home, ".agent-browser")
    lockdir = os.path.join(tmpdir, "agent-browser")
    lease_dir = os.path.join(lockdir, "leases")
    playwright_dir = (
        playwright_dir_override
        if playwright_dir_override is not None
        else os.environ.get("AB_REAPER_PLAYWRIGHT_DIR", os.path.join(home, ".cache", "ms-playwright-ghl"))
    )

    live_sessions = _live_session_names_from_leases(lease_dir, now=now)
    scoped_chromium_alive = _scoped_chromium_running(
        engine_dir, playwright_dir, ps_output_provider=ps_output_provider,
    )

    descriptors: List[str] = []
    if os.path.isdir(engine_dir):
        descriptors = sorted(
            f for f in os.listdir(engine_dir) if f.endswith(".engine")
        )

    orphans: List[Dict[str, Any]] = []
    live: List[Dict[str, Any]] = []
    for fname in descriptors:
        session = fname[: -len(".engine")]
        full = os.path.join(engine_dir, fname)
        age_sec = max(0.0, now - _mtime(full))
        entry = {"session": session, "age_sec": round(age_sec, 1)}
        if session in live_sessions:
            live.append({**entry, "reason": "matching non-expired lease"})
            continue
        if age_sec < grace_sec:
            live.append({**entry, "reason": f"younger than grace window ({grace_sec}s)"})
            continue
        if scoped_chromium_alive:
            # Conservative: we cannot cheaply attribute a scoped Chromium pid
            # to ONE specific session name (matches the reaper's own
            # conservative "any live lease -> don't kill" stance) — if ANY
            # scoped Chromium is alive, treat aged-but-unleased descriptors as
            # possibly-owned rather than false-flagging them.
            live.append({**entry, "reason": "a scoped Chromium process is alive (conservative)"})
            continue
        orphans.append(entry)

    return {
        "engine_dir": engine_dir,
        "checked_at": now,
        "grace_sec": grace_sec,
        "total_descriptors": len(descriptors),
        "live": live,
        "orphans": orphans,
        "ok": len(orphans) == 0,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="agent_browser_orphan_audit",
        description="U28 (B-U14) acceptance (d): report .engine descriptors with no "
                    "matching live process/lease, by name + age only.",
    )
    p.add_argument("--grace-sec", type=int, default=600,
                   help="Descriptors younger than this are never flagged (default 600s "
                        "= the acceptance criterion's '10 minutes after completion').")
    p.add_argument("--check", action="store_true", help="Exit 1 if any orphan is found.")
    args = p.parse_args(argv)
    result = find_orphans(grace_sec=args.grace_sec)
    print(json.dumps(result, indent=2))
    if args.check and not result["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
