#!/usr/bin/env python3
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: ews_snapshot.py
# CONFIG SNAPSHOT + REVERT-COMMAND EMISSION (spec 4.4)
# -----------------------------------------------------------------------------
# On EVERY config.write audit event (and before the sentinel's own two sanctioned
# writes), snapshot the live openclaw.json so "configuration changes are backed up
# and reversible" is a revert COMMAND in the operator's hand, not merely a backup.
#
#   snapshot   copy openclaw.json -> snapshots/openclaw.json.<utc-ts>.<sha8>
#              (0600, box user; the file contains live tokens, so it lives OUTSIDE
#              any repo, is never committed, never uploaded, never quoted), record
#              a ledger row linking it to the audit line's previousHash + argv, and
#              emit the one-line revert command (platform-aware; -u node on VPS).
#   prune      enforce D7 retention (LARGER of 60 snapshots / 45 days) and unlink
#              the pruned files.
#
# STDLIB ONLY. DOCTRINE: never prints a secret VALUE (a snapshot's CONTENT is never
# echoed); the snapshot file is 0600; move in silence. Snapshotting READS the live
# config and WRITES only to the state dir - it never writes the live config, so it
# warns (does not hard-refuse) as root; the box-user law is enforced hard in
# ews_revert.py (which DOES write the live config).
#
# EXIT CODES: 0 OK, 1 error, 2 usage, 3 not-found.
# =============================================================================
"""ews_snapshot.py - config snapshot + revert-command emission for Skill 60."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import ews_common as C  # noqa: E402
from ews_ledger import Ledger, default_state_dir, now_utc  # noqa: E402

EX_OK, EX_ERR, EX_USAGE, EX_NOTFOUND = 0, 1, 2, 3


def _ts_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshots_dir(state_dir: Path | None = None) -> Path:
    d = (state_dir or default_state_dir()) / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def take_snapshot(config_path=None, state_dir=None, trigger_event_id=None,
                  previous_hash=None, argv=None):
    """Copy the live config into the snapshots dir (0600), record a ledger row, and
    return a dict with the snapshot path, ts token, sha256, and the revert command."""
    cfgp = Path(config_path) if config_path else C.default_config_path()
    if not cfgp.is_file():
        raise FileNotFoundError(str(cfgp))
    sd = Path(state_dir) if state_dir else None
    snaps = snapshots_dir(sd)
    ts = _ts_token()
    sha = _sha256_file(cfgp)
    dest = snaps / ("openclaw.json.%s.%s" % (ts, sha[:8]))
    # copy content, then lock down permissions (0600) - the copy holds live tokens
    shutil.copyfile(cfgp, dest)
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass
    revert_cmd = C.revert_command_for(ts)
    with Ledger(sd) as led:
        sid = led.record_snapshot(str(dest), sha256=sha, trigger_event_id=trigger_event_id,
                                  revert_cmd=revert_cmd, previous_hash=previous_hash, argv=argv)
    return {"snapshot_id": sid, "path": str(dest), "ts": ts, "sha256": sha,
            "revert_cmd": revert_cmd}


def cmd_snapshot(args) -> int:
    try:
        res = take_snapshot(args.config, Path(args.state_dir) if args.state_dir else None,
                            trigger_event_id=args.trigger_event_id,
                            previous_hash=args.previous_hash, argv=args.argv)
    except FileNotFoundError as exc:
        _emit({"ok": False, "error": "config not found: %s" % exc})
        return EX_NOTFOUND
    _emit({"ok": True, "action": "snapshot", **res})
    return EX_OK


def cmd_prune(args) -> int:
    th = C.load_skill_config("thresholds.json").get("snapshots", {})
    keep_count = int(args.keep_count if args.keep_count is not None else th.get("retention_count", 60))
    keep_days = int(args.keep_days if args.keep_days is not None else th.get("retention_days", 45))
    sd = Path(args.state_dir) if args.state_dir else None
    with Ledger(sd) as led:
        pruned = led.prune_snapshots(keep_count, keep_days)
    removed = []
    for p in pruned:
        try:
            Path(p).unlink()
            removed.append(p)
        except OSError:
            pass
    _emit({"ok": True, "action": "prune", "keep_count": keep_count, "keep_days": keep_days,
           "rows_pruned": len(pruned), "files_removed": len(removed)})
    return EX_OK


def _emit(obj):
    sys.stdout.write(json.dumps(obj, sort_keys=True) + "\n")


def _cli(argv=None):
    ap = argparse.ArgumentParser(prog="ews_snapshot.py",
                                 description="Config snapshot + revert-command emission (Skill 60).")
    ap.add_argument("--state-dir")
    ap.add_argument("--config")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=False)
    sp = sub.add_parser("snapshot")
    sp.add_argument("--trigger-event-id", type=int)
    sp.add_argument("--previous-hash")
    sp.add_argument("--argv")
    sp = sub.add_parser("prune")
    sp.add_argument("--keep-count", type=int)
    sp.add_argument("--keep-days", type=int)
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.cmd:
        ap.error("a subcommand is required (or use --self-test)")
    if C.is_root():
        sys.stderr.write("WARN [ews_snapshot]: running as root; snapshot files should be "
                         "owned by the box user.\n")
    try:
        if args.cmd == "snapshot":
            return cmd_snapshot(args)
        if args.cmd == "prune":
            return cmd_prune(args)
    except OSError as exc:
        _emit({"ok": False, "error": str(exc)})
        return EX_ERR
    return EX_USAGE


def self_test():
    import tempfile
    print("[ews_snapshot] self-test: byte-identical snapshot, revert command, retention prune")
    with tempfile.TemporaryDirectory() as td:
        os.environ["EWS_STATE_DIR"] = str(Path(td) / "ews")
        cfgp = Path(td) / "openclaw.json"
        payload = {"agents": {"defaults": {"maxConcurrent": 16}}, "note": "synthetic"}
        cfgp.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        res = take_snapshot(str(cfgp))
        snap = Path(res["path"])
        # byte-identical copy
        assert snap.read_bytes() == cfgp.read_bytes(), "snapshot is not byte-identical"
        # sha matches
        assert res["sha256"] == _sha256_file(cfgp)
        # 0600 perms
        assert (snap.stat().st_mode & 0o777) == 0o600, oct(snap.stat().st_mode & 0o777)
        # revert command present and mentions the ts
        assert res["ts"] in res["revert_cmd"] and "revert --to" in res["revert_cmd"]
        print("  snapshot case: PASS (byte-identical, sha match, 0600, revert cmd emitted)")

        # ledger row + lookup by ts
        with Ledger() as led:
            assert led.snapshot_by_ts(res["ts"]) is not None
            assert len(led.list_snapshots()) == 1
        print("  ledger case: PASS (row recorded, lookup by ts works)")

        # prune retention (D7 larger-of): create several with distinct ts tokens
        with Ledger() as led:
            for i in range(4):
                fake = Path(td) / ("openclaw.json.2026010%dT000000.aabbccdd" % (i + 1))
                fake.write_text("x", encoding="utf-8")
                led.record_snapshot(str(fake), sha256="x")
        # keep_count=1, keep_days=0 -> count wins; keeps only newest, prunes the rest
        with Ledger() as led:
            pruned = led.prune_snapshots(1, 0)
        for p in pruned:
            Path(p).unlink(missing_ok=True)
        with Ledger() as led:
            assert len(led.list_snapshots()) == 1
        print("  prune case: PASS (D7 retention prunes rows and files)")

        os.environ.pop("EWS_STATE_DIR", None)
    print("[ews_snapshot] self-test: PASS")
    return EX_OK


if __name__ == "__main__":
    sys.exit(_cli())
