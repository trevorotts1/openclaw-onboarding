#!/usr/bin/env python3
"""ghl_vps_mount_proof.py — B-U15 item 1: the mechanism behind ENV-MATRIX.md's
ONE remaining `[ASSUMED, spec-carried]` row.

WHY THIS EXISTS
----------------
ENV-MATRIX.md's "Session persistence" row reads: `~/.agent-browser` "persist[s]
only if the workdir is on a mounted volume" on a VPS/Docker box —
"[ASSUMED, spec-carried]: confirm per-box on first VPS live run (§9.4 step
10)". This module turns that one-off manual confirmation into a repeatable,
receipt-backed procedure instead of an assumption that quietly stays
unconfirmed forever:

  1. ``classify_mount()`` — statically classify what filesystem actually
     backs a path by parsing the mount table (injectable reader — hermetic,
     no real ``/proc/mounts`` or ``/data`` touched in tests). This alone
     cannot PROVE persistence (a misconfigured or unrecognized volume driver
     could still lie), so it is never the sole basis of a PASS.
  2. ``write_marker()`` / ``verify_marker()`` — the actual round-trip proof:
     stamp a run-id-tagged marker file INTO the path (pre-phase), then read
     it back (post-phase) after whatever happened in between. A marker that
     survives an ephemeral wipe is impossible; a marker that vanishes despite
     a "persistent"-classified mount is the exact false-assumption this unit
     exists to catch.
  3. ``build_receipt()`` / ``write_receipt()`` — the single JSON artifact
     B-U15's BINARY acceptance (a) points at: "the receipt records the mount
     type". A receipt with ``post=None`` is honestly marked
     ``live_leg_status="PRE-ONLY"`` — it is never upgraded to a PASS by this
     module alone.

THE LIVE LEG THIS DOES NOT AND CANNOT CLOSE (operator-gated, owed):
    The actual `docker compose up -d --force-recreate` between the pre- and
    post- calls requires a REAL VPS with REAL Docker — this module can prove
    its OWN classify/marker/receipt logic offline (this unit's tests do,
    hermetically, with fixture directories and an injected mount table), but
    it cannot fabricate what only a real container recreate on a real box can
    prove. `scripts/vps-mount-proof.sh` is the orchestration wrapper an
    operator runs on a real VPS to close it (mirrors the U22/U84
    "OFFLINE/FIXTURE tier ships now, LIVE tier owed" pattern already in this
    ledger) — it refuses cleanly (never fabricates a PASS) when docker/a real
    container is not actually reachable.

CLI
---
    python3 ghl_vps_mount_proof.py classify <path>
    python3 ghl_vps_mount_proof.py pre <path> --run-id <id> [--evidence-root <dir>] [--box-label <name>]
    python3 ghl_vps_mount_proof.py post <path> --run-id <id> [--evidence-root <dir>] [--box-label <name>]
    python3 ghl_vps_mount_proof.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Callable, List, Optional, Tuple

VPS_MOUNT_PROOF_VERSION = "v1.0.0"

# Filesystem types that mean "this is a container's ephemeral writable layer
# (or an unmounted tmpfs)", never a durable bind/volume mount. `aufs` is the
# legacy Docker storage-driver equivalent of `overlay`; both are listed here
# for the same reason.
_EPHEMERAL_FSTYPES = frozenset({"overlay", "aufs", "tmpfs"})

_MARKER_FILENAME = ".b-u15-mount-marker.json"

# device, mountpoint, fstype, options
MountEntry = Tuple[str, str, str, str]


def _read_proc_mounts(mounts_path: str = "/proc/mounts") -> List[MountEntry]:
    """Real reader: parse ``/proc/mounts`` (present on Linux/Docker boxes,
    absent on macOS). Returns ``[]`` on any read failure — never raises —
    so an absent mount table is reported as "undeterminable" by
    ``classify_mount``, never silently treated as ephemeral."""
    entries: List[MountEntry] = []
    try:
        with open(mounts_path, encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 4:
                    continue
                entries.append((parts[0], parts[1], parts[2], parts[3]))
    except OSError:
        return []
    return entries


def classify_mount(
    path: str,
    *,
    mounts_reader: Optional[Callable[[], List[MountEntry]]] = None,
    platform: Optional[str] = None,
) -> dict:
    """Classify what backs ``path``.

    Mac (``platform == 'darwin'``): real hardware — no container-overlay
    question exists at all, so this is trivially persistent by construction.

    Linux/VPS: find the mount-table entry with the LONGEST mountpoint that is
    a prefix of ``path`` (mirrors how ``findmnt --target`` / the kernel
    itself resolves "what filesystem backs this path" — the closest mount
    ABOVE the path wins, not necessarily ``/``). A match whose filesystem
    type is ``overlay``/``aufs``/``tmpfs`` is the container's own ephemeral
    writable layer (or an unmounted tmpfs) — NOT persistent. Any other
    filesystem type is treated as durable (a real disk, a bind mount, or a
    named volume backed by real storage).

    Never guesses: when the mount table cannot be read at all (no
    ``/proc/mounts`` and no injected reader with data), ``is_persistent`` is
    ``None`` — "undeterminable", not a fabricated answer either way.
    """
    plat = platform if platform is not None else sys.platform
    if plat == "darwin":
        return {
            "path": path,
            "mount_type": "mac-native",
            "fs_type": None,
            "matched_mountpoint": None,
            "device": None,
            "is_persistent": True,
            "basis": "darwin: real filesystem hardware, no container overlay question exists",
        }

    reader = mounts_reader if mounts_reader is not None else _read_proc_mounts
    entries = reader()
    if not entries:
        return {
            "path": path,
            "mount_type": "undeterminable",
            "fs_type": None,
            "matched_mountpoint": None,
            "device": None,
            "is_persistent": None,
            "basis": "no mount table readable on this box — cannot classify, never guessed",
        }

    norm_path = os.path.normpath(path)
    best: Optional[MountEntry] = None
    best_len = -1
    for entry in entries:
        mountpoint = os.path.normpath(entry[1])
        prefix = mountpoint if mountpoint.endswith("/") else mountpoint + "/"
        matches = norm_path == mountpoint or norm_path.startswith(prefix)
        if matches and len(mountpoint) > best_len:
            best = entry
            best_len = len(mountpoint)

    if best is None:
        return {
            "path": path,
            "mount_type": "undeterminable",
            "fs_type": None,
            "matched_mountpoint": None,
            "device": None,
            "is_persistent": None,
            "basis": "no mount-table entry's mountpoint is a prefix of path — cannot classify",
        }

    device, mountpoint, fstype, _options = best
    persistent = fstype not in _EPHEMERAL_FSTYPES
    if persistent:
        basis = (
            f"path is backed by mount {mountpoint!r} of type {fstype!r} — "
            f"not an ephemeral overlay/aufs/tmpfs, treated as durable"
        )
    else:
        basis = (
            f"path is backed by mount {mountpoint!r} of type {fstype!r} — "
            f"an ephemeral container layer / unmounted tmpfs, NOT persistent"
        )

    return {
        "path": path,
        "mount_type": fstype,
        "fs_type": fstype,
        "matched_mountpoint": mountpoint,
        "device": device,
        "is_persistent": persistent,
        "basis": basis,
    }


def _atomic_write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def write_marker(
    path: str,
    run_id: str,
    *,
    mounts_reader: Optional[Callable[[], List[MountEntry]]] = None,
    platform: Optional[str] = None,
) -> dict:
    """PRE-phase: ensure ``path`` exists, stamp a run-id-tagged marker file
    inside it, return the marker payload. Whatever happens between this call
    and ``verify_marker()`` (nothing, in a fixture test; a real
    ``docker compose up -d --force-recreate`` on a live VPS) is the actual
    proof — this function only plants the flag."""
    os.makedirs(path, exist_ok=True)
    marker = {
        "run_id": run_id,
        "written_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "classify_at_write": classify_mount(path, mounts_reader=mounts_reader, platform=platform),
        "vps_mount_proof_version": VPS_MOUNT_PROOF_VERSION,
    }
    _atomic_write_json(os.path.join(path, _MARKER_FILENAME), marker)
    return marker


def verify_marker(path: str, expected_run_id: str) -> dict:
    """POST-phase: read the marker back. NEVER raises — an absent or corrupt
    marker after whatever happened in between is exactly the failure mode
    this proof exists to surface, not crash on."""
    marker_path = os.path.join(path, _MARKER_FILENAME)
    if not os.path.exists(marker_path):
        return {
            "present": False, "run_id_matches": False, "marker": None,
            "error": f"marker file absent at {marker_path!r} — the path did NOT survive",
        }
    try:
        with open(marker_path, encoding="utf-8") as fh:
            marker = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "present": True, "run_id_matches": False, "marker": None,
            "error": f"marker file present but unreadable: {exc}",
        }
    matches = marker.get("run_id") == expected_run_id
    return {
        "present": True,
        "run_id_matches": matches,
        "marker": marker,
        "error": None if matches else (
            f"run_id mismatch: expected {expected_run_id!r}, found {marker.get('run_id')!r}"
        ),
    }


def build_receipt(
    path: str,
    pre: dict,
    post: Optional[dict],
    *,
    box_label: Optional[str] = None,
) -> dict:
    """Assemble the single receipt B-U15 acceptance (a) requires: "the
    receipt records the mount type". ``post=None`` produces an honestly
    PRE-ONLY receipt — never fabricated into a PASS by this function."""
    classify = pre.get("classify_at_write", {})
    survived = bool(post) and bool(post.get("present")) and bool(post.get("run_id_matches"))
    return {
        "path": path,
        "box_label": box_label,
        "run_id": pre.get("run_id"),
        "mount_type": classify.get("mount_type"),
        "is_persistent_by_classification": classify.get("is_persistent"),
        "classification_basis": classify.get("basis"),
        "pre": pre,
        "post": post,
        "survived_recreate": survived if post is not None else None,
        "live_leg_status": (
            "complete" if post is not None else
            "PRE-ONLY — live `docker compose up -d --force-recreate` round trip owed (operator VPS)"
        ),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "vps_mount_proof_version": VPS_MOUNT_PROOF_VERSION,
    }


def receipt_path(evidence_root: str) -> str:
    return os.path.join(evidence_root, "routing", "vps-mount-receipt.json")


def write_receipt(evidence_root: str, receipt: dict) -> str:
    path = receipt_path(evidence_root)
    _atomic_write_json(path, receipt)
    return path


def read_receipt(evidence_root: str) -> Optional[dict]:
    path = receipt_path(evidence_root)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Self-test — no network, no Docker, no live browser (tmp dirs only)
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile

    errors: List[str] = []

    # 1. classify_mount: darwin is always mac-native/persistent regardless of
    #    what a (never-consulted) mounts_reader would say.
    c = classify_mount("/Users/fixture/.agent-browser", platform="darwin",
                        mounts_reader=lambda: (_ for _ in ()).throw(AssertionError("must not be called")))
    if c["mount_type"] != "mac-native" or c["is_persistent"] is not True:
        errors.append(f"darwin classify should be mac-native/persistent, got {c}")

    # 2. classify_mount: overlay at root ("/") on a VPS -> NOT persistent.
    def overlay_root():
        return [("overlay", "/", "overlay", "rw,relatime")]
    c = classify_mount("/data/.openclaw/.agent-browser", platform="linux", mounts_reader=overlay_root)
    if c["is_persistent"] is not False or c["fs_type"] != "overlay":
        errors.append(f"overlay-root path should be NOT persistent, got {c}")

    # 3. classify_mount: an explicit real-fs bind/volume mount deeper than /
    #    on the exact target path -> persistent.
    def bind_mount():
        return [
            ("overlay", "/", "overlay", "rw,relatime"),
            ("/dev/vda1", "/data", "ext4", "rw,relatime"),
        ]
    c = classify_mount("/data/.openclaw/.agent-browser", platform="linux", mounts_reader=bind_mount)
    if c["is_persistent"] is not True or c["matched_mountpoint"] != "/data":
        errors.append(f"ext4-backed /data mount should be persistent, got {c}")

    # 4. classify_mount: a tmpfs mounted deeper than / is STILL ephemeral by type.
    def tmpfs_deep():
        return [
            ("overlay", "/", "overlay", "rw,relatime"),
            ("tmpfs", "/data", "tmpfs", "rw,relatime"),
        ]
    c = classify_mount("/data/.openclaw/.agent-browser", platform="linux", mounts_reader=tmpfs_deep)
    if c["is_persistent"] is not False:
        errors.append(f"tmpfs-backed /data mount should be NOT persistent, got {c}")

    # 5. classify_mount: no mount table at all -> undeterminable (None), never guessed.
    c = classify_mount("/data/.openclaw/.agent-browser", platform="linux", mounts_reader=lambda: [])
    if c["is_persistent"] is not None or c["mount_type"] != "undeterminable":
        errors.append(f"empty mount table should be undeterminable, got {c}")

    # 6. write_marker / verify_marker round trip on the SAME dir (simulates a
    #    persistent mount surviving whatever happened in between).
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "agent-browser")
        pre = write_marker(target, "run-abc123", platform="darwin")
        if not os.path.isdir(target):
            errors.append("write_marker did not create the target dir")
        post = verify_marker(target, "run-abc123")
        if not (post["present"] and post["run_id_matches"]):
            errors.append(f"same-dir round trip should present+match, got {post}")

        # 7. Wrong run_id -> matches False, present True (marker exists but is stale).
        bad = verify_marker(target, "run-DIFFERENT")
        if bad["present"] is not True or bad["run_id_matches"] is not False:
            errors.append(f"wrong run_id should be present but not-matching, got {bad}")

        # 8. A DIFFERENT, never-marked dir simulates the ephemeral-wipe failure
        #    mode (the container recreated and the path did NOT survive).
        wiped = os.path.join(tmp, "agent-browser-wiped-simulated")
        os.makedirs(wiped)
        gone = verify_marker(wiped, "run-abc123")
        if gone["present"] is not False:
            errors.append(f"never-marked dir should report present=False, got {gone}")

        # 9. build_receipt: pre-only (post=None) is honestly PRE-ONLY, never a PASS.
        r_pre_only = build_receipt(target, pre, None, box_label="fixture-box")
        if r_pre_only["survived_recreate"] is not None or "PRE-ONLY" not in r_pre_only["live_leg_status"]:
            errors.append(f"pre-only receipt must be honestly PRE-ONLY, got {r_pre_only}")
        if r_pre_only["mount_type"] != "mac-native":
            errors.append(f"receipt must record the mount_type from pre-phase classify, got {r_pre_only}")

        # 10. build_receipt: a full round trip with post present+matching -> survived True.
        r_full = build_receipt(target, pre, post, box_label="fixture-box")
        if r_full["survived_recreate"] is not True or r_full["live_leg_status"] != "complete":
            errors.append(f"full round-trip receipt should survive=True/complete, got {r_full}")

        # 11. build_receipt: a full round trip with post absent -> survived False, still 'complete'
        #     shape (the round trip WAS attempted, it just failed — distinct from PRE-ONLY).
        r_failed = build_receipt(target, pre, gone, box_label="fixture-box")
        if r_failed["survived_recreate"] is not False or r_failed["live_leg_status"] != "complete":
            errors.append(f"failed-but-attempted round trip should be survived=False/complete, got {r_failed}")

        # 12. write_receipt / read_receipt round trip.
        evidence_root = os.path.join(tmp, "evidence")
        out_path = write_receipt(evidence_root, r_full)
        if not os.path.exists(out_path):
            errors.append("write_receipt did not create a file")
        loaded = read_receipt(evidence_root)
        if not loaded or loaded["run_id"] != "run-abc123":
            errors.append(f"read_receipt round-trip broken: {loaded}")

        # 13. read_receipt on an evidence root with no receipt yet -> None, never a crash.
        empty_root = os.path.join(tmp, "no-receipt-here")
        if read_receipt(empty_root) is not None:
            errors.append("read_receipt on an empty root should return None")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — VPS mount classify/marker/receipt mechanism verified "
          "(no network, no Docker, no live browser)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_vps_mount_proof",
        description="B-U15 item 1: VPS session-persistence mount classify + marker proof + receipt.",
    )
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("classify", help="Print the mount classification for a path as JSON.").add_argument("path")

    for verb in ("pre", "post"):
        sp = sub.add_parser(verb, help=f"{verb.upper()}-phase marker proof.")
        sp.add_argument("path")
        sp.add_argument("--run-id", required=True)
        sp.add_argument("--evidence-root", default=None,
                         help="If given, write/update routing/vps-mount-receipt.json under this root.")
        sp.add_argument("--box-label", default=None)

    p.add_argument("--selftest", action="store_true", help="Run the no-network self-test and exit.")

    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.cmd == "classify":
        print(json.dumps(classify_mount(args.path), indent=2))
        return 0

    if args.cmd == "pre":
        marker = write_marker(args.path, args.run_id)
        print(json.dumps(marker, indent=2))
        if args.evidence_root:
            receipt = build_receipt(args.path, marker, None, box_label=args.box_label)
            out = write_receipt(args.evidence_root, receipt)
            print(f"[ghl_vps_mount_proof] PRE receipt written: {out}", file=sys.stderr)
        return 0

    if args.cmd == "post":
        result = verify_marker(args.path, args.run_id)
        # Re-derive the pre-phase classify from the marker itself if present,
        # so `post` alone (no separately-passed `pre` dict) can still build a
        # complete receipt when called from the shell wrapper as a second,
        # separate process invocation.
        pre_for_receipt = (result.get("marker") or {}) if result["present"] else {"run_id": args.run_id, "classify_at_write": {}}
        print(json.dumps(result, indent=2))
        if args.evidence_root:
            receipt = build_receipt(args.path, pre_for_receipt, result, box_label=args.box_label)
            out = write_receipt(args.evidence_root, receipt)
            print(f"[ghl_vps_mount_proof] POST receipt written: {out}", file=sys.stderr)
        return 0 if (result["present"] and result["run_id_matches"]) else 1

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
