#!/usr/bin/env python3
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: ews_revert.py
# RESTORE A NAMED SNAPSHOT, AS THE BOX USER, VALIDATED, READ BACK (spec 4.4)
# -----------------------------------------------------------------------------
# The other half of "configuration changes are backed up and reversible": restore
# a named snapshot to the live config path. This is a CONFIG WRITE, so it HARD-
# REFUSES to run as root (a root-owned openclaw.json freezes the gateway - the
# exact S6 incident this system exists to catch); on VPS the operator wraps this
# in `docker exec -u node`.
#
# Sequence (every step fail-closed):
#   1. resolve the snapshot by its <utc-ts> token via the ledger;
#   2. VALIDATE the snapshot parses as JSON AND the S3 subtractive arithmetic is
#      sane on the restored bytes BEFORE anything is written (a snapshot that would
#      re-introduce a crash-config is refused);
#   3. write it to the live config path atomically, as the box user;
#   4. READ BACK byte-for-byte and confirm the sha matches the snapshot's sha;
#   5. record the revert in the ledger.
#
# STDLIB ONLY. DOCTRINE: never prints a secret value; the restored CONTENT is never
# echoed; config write as the box user, never root.
#
# EXIT CODES: 0 OK, 1 error, 2 usage, 3 snapshot-not-found, 4 REFUSED (root),
#             5 validation/read-back failure (NOTHING left half-written).
# =============================================================================
"""ews_revert.py - restore a config snapshot as the box user, validated, read back."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import ews_common as C  # noqa: E402
from ews_ledger import Ledger  # noqa: E402

EX_OK, EX_ERR, EX_USAGE, EX_NOTFOUND, EX_REFUSED, EX_VALIDATION = 0, 1, 2, 3, 4, 5


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def do_revert(ts_token, config_path=None, state_dir=None):
    """Restore the snapshot named by ts_token. Returns a result dict. Raises
    SystemExit(EX_REFUSED) if run as root. Never leaves a half-written config."""
    C.refuse_root_for_config("revert (config write)")

    sd = Path(state_dir) if state_dir else None
    with Ledger(sd) as led:
        snap = led.snapshot_by_ts(ts_token)
    if not snap:
        return (EX_NOTFOUND, {"ok": False, "error": "no snapshot for ts %r" % ts_token})
    snap_path = Path(snap["path"])
    if not snap_path.is_file():
        return (EX_NOTFOUND, {"ok": False, "error": "snapshot file missing on disk",
                              "path": str(snap_path)})

    raw = snap_path.read_bytes()
    # 2. validate parse + subtractive arithmetic BEFORE writing anything
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return (EX_VALIDATION, {"ok": False, "error": "snapshot does not parse as JSON: %s" % exc})
    ok, reasons = C.validate_config_sanity(parsed)
    if not ok:
        return (EX_VALIDATION, {"ok": False, "error": "snapshot fails pre-write validation",
                                "reasons": reasons})

    cfgp = Path(config_path) if config_path else C.default_config_path()
    # 3. atomic write as the box user
    fd, tmp = tempfile.mkstemp(prefix=".openclaw.", suffix=".revert", dir=str(cfgp.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, cfgp)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    # 4. read back byte-for-byte
    back = cfgp.read_bytes()
    if back != raw:
        return (EX_VALIDATION, {"ok": False, "error": "read-back mismatch after revert"})
    if snap.get("sha256") and _sha256_bytes(back) != snap["sha256"]:
        return (EX_VALIDATION, {"ok": False, "error": "restored sha does not match snapshot sha"})

    # 5. record the revert
    with Ledger(sd) as led:
        eid = led.record_event("S6", "INFO", key_path=str(cfgp), klass="revert",
                               detail="reverted to snapshot %s" % ts_token)
    return (EX_OK, {"ok": True, "action": "revert", "ts": ts_token, "config": str(cfgp),
                    "sha256": snap.get("sha256"), "event_id": eid})


def _emit(obj):
    sys.stdout.write(json.dumps(obj, sort_keys=True) + "\n")


def _cli(argv=None):
    ap = argparse.ArgumentParser(prog="ews_revert.py",
                                 description="Restore a config snapshot as the box user (Skill 60).")
    ap.add_argument("--state-dir")
    ap.add_argument("--config")
    ap.add_argument("--to", help="the <utc-ts> token of the snapshot to restore")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.to:
        ap.error("--to <utc-ts> is required")
    try:
        rc, res = do_revert(args.to, args.config, Path(args.state_dir) if args.state_dir else None)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else EX_REFUSED
    _emit(res)
    return rc


def self_test():
    import tempfile
    print("[ews_revert] self-test: snapshot round-trip byte-identical + validation refusals")
    sys.path.insert(0, str(_HERE))
    from ews_snapshot import take_snapshot
    os.environ["EWS_ALLOW_ROOT"] = "1"  # allow the write in a CI/root sandbox
    try:
        with tempfile.TemporaryDirectory() as td:
            os.environ["EWS_STATE_DIR"] = str(Path(td) / "ews")
            cfgp = Path(td) / "openclaw.json"
            good = {"agents": {"defaults": {"maxConcurrent": 16,
                    "compaction": {"memoryFlush": {"softThresholdTokens": 20000}}}},
                    "_contextWindow": 128000}
            cfgp.write_text(json.dumps(good, indent=2), encoding="utf-8")
            snap = take_snapshot(str(cfgp))
            ts = snap["ts"]

            # mutate the live config, then revert
            cfgp.write_text(json.dumps({"agents": {"defaults": {"maxConcurrent": 999}}}), encoding="utf-8")
            rc, res = do_revert(ts, str(cfgp))
            assert rc == EX_OK, res
            # byte-identical to the original snapshot
            assert cfgp.read_bytes() == Path(snap["path"]).read_bytes(), "revert not byte-identical"
            restored = json.loads(cfgp.read_text(encoding="utf-8"))
            assert restored["agents"]["defaults"]["maxConcurrent"] == 16
            print("  round-trip case: PASS (revert restored the exact original bytes)")

            # not-found
            rc2, _ = do_revert("99999999T999999", str(cfgp))
            assert rc2 == EX_NOTFOUND
            print("  not-found case: PASS (unknown ts refused with exit 3)")

            # validation refusal: a snapshot that would re-introduce a subtractive crash
            with Ledger() as led:
                badsnap = Path(td) / "openclaw.json.20260505T050505.deadbeef"
                badsnap.write_text(json.dumps({"agents": {"defaults": {"compaction":
                    {"memoryFlush": {"softThresholdTokens": 900000}}}}, "_contextWindow": 128000}),
                    encoding="utf-8")
                led.record_snapshot(str(badsnap), sha256=_sha256_bytes(badsnap.read_bytes()))
            pre = cfgp.read_bytes()
            rc3, res3 = do_revert("20260505T050505", str(cfgp))
            assert rc3 == EX_VALIDATION, res3
            assert cfgp.read_bytes() == pre, "live config was touched despite validation failure"
            print("  validation case: PASS (crash-config snapshot refused; live config untouched)")

        # root refusal (without the seam)
        os.environ.pop("EWS_ALLOW_ROOT", None)
        if C.is_root():
            try:
                do_revert("x", "/tmp/nope")
                print("  root-refuse case: FAIL (revert ran as root)")
                return EX_ERR
            except SystemExit as exc:
                assert exc.code == EX_REFUSED
                print("  root-refuse case: PASS (hard-refused as root)")
        else:
            print("  root-refuse case: SKIP (not root; refusal proven in ews_common self-test)")
    finally:
        os.environ.pop("EWS_ALLOW_ROOT", None)
        os.environ.pop("EWS_STATE_DIR", None)
    print("[ews_revert] self-test: PASS")
    return EX_OK


if __name__ == "__main__":
    sys.exit(_cli())
