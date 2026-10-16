#!/usr/bin/env python3
"""ghl_vps_provision_check.py — S06-05: the VPS provisioning VERIFIER.

WHY THIS EXISTS
---------------
Packet spec 05 section 6 names the Docker-secrets shape for a VPS/container
box: credentials arrive as FILES (the ``*_FILE`` indirection), owned by the
service identity, mode 0600, on a filesystem that survives a container
recreate. S06-04 landed the consumption half (``tools/ghl_secret_resolver.py``
— the one shared resolver). This module is the provisioning half's VERIFIER:
it proves a box's layout actually matches the contract before a build trusts
it, and names the exact repair when it does not.

THE Q1 SPLIT (decided by S06-04's landed code — do not re-litigate)
-------------------------------------------------------------------
* The RESOLVER owns the READ-TIME refusal: a ``*_FILE`` target that is
  missing, unreadable, empty, or carries ANY group/other permission bit
  (``mode & 0o077``) raises ``SecretFileError`` at resolution time.
* THIS VERIFIER owns the PROVISIONING verdicts the resolver deliberately
  does not make: file/dir existence, owner UID vs the service/process UID,
  whether the service runs as root, directory modes (0700), the mount
  classification of every persistence path, and the storage label. A loose
  mode is an ERROR here too (same invariant, earlier catch), and every
  repair NARROWS access (``chmod 600`` / ``chown``) — no repair ever widens
  a mode to compensate for an ownership mismatch.

WHAT IT CHECKS (names, paths, modes, UIDs, mount types — NEVER values)
---------------------------------------------------------------------
* The three ``*_FILE`` variables (``GHL_REFRESH_TOKEN_FILE``,
  ``GHL_LOCATION_PIT_FILE``, ``GHL_LOCATION_ID_FILE`` — the location-ID
  file is held to the same refusal as the two secret files, exactly as the
  resolver applies it): when set, the target must exist, be non-empty,
  carry no group/other bit, be owned by the service UID, and sit on a
  persistent (non-overlay/aufs/tmpfs) mount.
* The canonical env stores (``ghl_secret_resolver.ENV_STORES`` — the first
  is also the Tier-2 self-heal's live read/write store since S06-04):
  when present, no group/other bit; ownership reported.
* The five persistence paths of the mount-proof PATH SET
  (``ghl_vps_mount_proof.PATHSET_KEYS``): each classified via the shared
  ``classify_mount()`` — ephemeral backing is an ERROR, an unreadable mount
  table is UNDETERMINABLE (never guessed).
* The service identity: running as root (uid 0) is an ERROR.
* The storage label: ``permission-protected plaintext`` by default for every
  fleet type until an operator names an encrypted disk/backup policy for
  the box (``GHL_VPS_STORAGE_LABEL`` / ``--storage-label``).

RECEIPT
-------
A full run writes a value-free receipt (schema
``skill6-vps-provisioning/1``) namespaced per client under the durable
root: ``<durable_root>/skill6-provisioning/<client>/provisioning-receipt.json``
— S06-05-created state is namespaced by client identity even though the
per-client container is the isolation boundary (ENV-MATRIX.md provisioning
contract). With ``--evidence-root`` a copy also lands at
``<evidence-root>/routing/provisioning-receipt.json``. ``--advisory`` (the
``bm_ensure`` wiring) prints finding lines only, writes nothing, and
always exits 0.

Hermetic by construction: stat / mount-table / platform / UID inputs are
all injectable; the test suite drives every verdict from fixtures.

CLI
---
    python3 ghl_vps_provision_check.py --client <location-id> [--evidence-root <dir>] [--storage-label <label>] [--service-uid <uid>] [--json]
    python3 ghl_vps_provision_check.py --client <location-id> --advisory
    python3 ghl_vps_provision_check.py --selftest

Exit codes (full mode): 0 = no ERROR findings; 1 = at least one ERROR
(each printed with its exact repair); 2 = usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Callable, List, Mapping, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROVISION_SCHEMA = "skill6-vps-provisioning/1"

# Packet section 6 default (prep Q5 disposition): until an operator names an
# encrypted disk/backup policy for a specific box, every store on every
# fleet type carries this label — the protection is the filesystem
# permissions (0600/0700, owner-only), and the label says so honestly.
DEFAULT_STORAGE_LABEL = "permission-protected plaintext"
STORAGE_LABEL_ENV = "GHL_VPS_STORAGE_LABEL"

# The three *_FILE variables (delta-check C3): the packet's two secret
# files plus the location-ID file S06-04 added for symmetry. The resolver
# applies the identical 0o077 refusal to all three.
FILE_VARS = (
    "GHL_REFRESH_TOKEN_FILE",
    "GHL_LOCATION_PIT_FILE",
    "GHL_LOCATION_ID_FILE",
)

# Row severities. ERROR fails the gate (exit 1 in full mode); WARN and
# UNDETERMINABLE are reported but never fail it and never guess.
ERROR = "ERROR"
WARN = "WARN"
INFO = "INFO"
UNDETERMINABLE = "UNDETERMINABLE"
PASS = "PASS"


def _row(name: str, kind: str, path: str, status: str, detail: str,
         repair: str = "", **extra) -> dict:
    row = {
        "name": name,
        "kind": kind,
        "path": path,
        "status": status,
        "detail": detail,
        "repair": repair,
    }
    row.update(extra)
    return row


def _mode_bits(st) -> int:
    return st.st_mode & 0o777


def _classify(path: str, mounts_reader, platform) -> dict:
    from ghl_vps_mount_proof import classify_mount

    return classify_mount(path, mounts_reader=mounts_reader, platform=platform)


def _mount_verdict(classify: dict) -> str:
    """PASS / ERROR / UNDETERMINABLE for one classification."""
    if classify.get("is_persistent") is True:
        return PASS
    if classify.get("is_persistent") is False:
        return ERROR
    return UNDETERMINABLE


def verify_provisioning(
    *,
    client: str,
    env: Optional[Mapping[str, str]] = None,
    paths: Optional[dict] = None,
    stores: Optional[List[str]] = None,
    service_uid: Optional[int] = None,
    service_gid: Optional[int] = None,
    stat_reader: Callable = os.stat,
    mounts_reader=None,
    platform: Optional[str] = None,
    storage_label: str = "",
    box: Optional[dict] = None,
) -> dict:
    """Run every provisioning check and return the receipt dict.

    Hermetic seams: ``env`` (the mapping ``*_FILE`` variables are read
    from), ``paths`` (the mount-proof path set; assembled from the sibling
    modules when None), ``stores`` (store file paths; the resolver's
    ENV_STORES expanded when None), ``stat_reader``, ``mounts_reader``,
    ``platform``, and the service UID/GID all inject.
    """
    env = env if env is not None else os.environ
    if service_uid is None:
        service_uid = os.getuid()
    if service_gid is None:
        service_gid = os.getegid()
    if box is None:
        box = _default_box()
    if paths is None:
        paths = _default_paths(box)
    if stores is None:
        stores = _default_stores()
    label = (
        storage_label
        or (env.get(STORAGE_LABEL_ENV) or "").strip()
        or DEFAULT_STORAGE_LABEL
    )

    rows: List[dict] = []

    # ── service identity ────────────────────────────────────────────────────
    if service_uid == 0:
        rows.append(_row(
            "service-identity", "identity", "", ERROR,
            "the service process runs as root (uid 0): ownership verdicts "
            "are meaningless and the packet's non-root container contract "
            "is violated",
            repair="run the OpenClaw service as its non-root service user "
                   "(in a container, the node user) and re-run this check "
                   "as that user",
        ))
    else:
        rows.append(_row(
            "service-identity", "identity", "", PASS,
            f"service uid {service_uid} (non-root)",
        ))

    # ── durable root ────────────────────────────────────────────────────────
    durable_root = (box or {}).get("durable_root") or ""
    if durable_root:
        rows.append(_row(
            "durable-root", "root", durable_root, PASS,
            "durable_root() resolves on this box",
        ))
    else:
        rows.append(_row(
            "durable-root", "root", "", ERROR,
            "durable_root() resolves to \"\" on this box — durable state "
            "has no home and would fall back to ephemeral paths",
            repair="onboard the box so the durable root exists on the "
                   "persistent volume (/data/.openclaw on a VPS container, "
                   "~/.openclaw on a Mac) before provisioning secrets",
        ))

    # ── storage label ───────────────────────────────────────────────────────
    rows.append(_row(
        "storage-label", "label", "", INFO,
        f"storage label: {label}"
        + (" (fleet default — no operator-named encrypted disk/backup "
           "policy for this box)" if label == DEFAULT_STORAGE_LABEL
           else " (operator-named policy label)"),
    ))

    # ── *_FILE targets ──────────────────────────────────────────────────────
    checked_dirs: set = set()
    for var in FILE_VARS:
        target = (env.get(var) or "").strip()
        if not target:
            rows.append(_row(
                var, "secret-file", "", INFO,
                f"{var} is not set (the *_FILE indirection is optional; "
                "the value may resolve from the env or the stores)",
            ))
            continue
        rows.append(_check_secret_file(
            var, target,
            service_uid=service_uid, stat_reader=stat_reader,
            mounts_reader=mounts_reader, platform=platform,
        ))
        parent = os.path.dirname(target)
        if parent and parent not in checked_dirs:
            checked_dirs.add(parent)
            rows.append(_check_secret_dir(
                parent, service_uid=service_uid, stat_reader=stat_reader,
            ))

    # ── canonical stores ────────────────────────────────────────────────────
    for store in stores:
        rows.append(_check_store(
            store, service_uid=service_uid, service_gid=service_gid,
            stat_reader=stat_reader, mounts_reader=mounts_reader,
            platform=platform,
        ))
        parent = os.path.dirname(store)
        if parent and parent not in checked_dirs:
            checked_dirs.add(parent)
            rows.append(_check_secret_dir(
                parent, service_uid=service_uid, stat_reader=stat_reader,
            ))

    # ── persistence path set (mount classification) ─────────────────────────
    for key, p in paths.items():
        if not p:
            rows.append(_row(
                f"pathset:{key}", "pathset", "", UNDETERMINABLE,
                "no path resolved for this entry on this box — reported, "
                "never guessed",
            ))
            continue
        classify = _classify(p, mounts_reader, platform)
        verdict = _mount_verdict(classify)
        exists = os.path.exists(p) if stat_reader is os.stat else None
        detail = (
            f"backing mount: {classify.get('mount_type')} "
            f"({classify.get('basis')})"
        )
        if exists is False:
            detail += "; path does not exist yet"
        repair = ""
        if verdict == ERROR:
            repair = (
                f"move {key} onto the persistent volume under the durable "
                f"root ({durable_root or '<durable root>'}) — state placed "
                "on an ephemeral overlay/tmpfs is wiped by a container "
                "recreate"
            )
        rows.append(_row(
            f"pathset:{key}", "pathset", p, verdict, detail, repair=repair,
            mount_type=classify.get("mount_type"),
            is_persistent=classify.get("is_persistent"),
        ))

    errors = sum(1 for r in rows if r["status"] == ERROR)
    warnings = sum(1 for r in rows if r["status"] in (WARN, UNDETERMINABLE))
    return {
        "schema": PROVISION_SCHEMA,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "client": client,
        "box": box,
        "service": {"uid": service_uid, "gid": service_gid,
                    "runs_as_root": service_uid == 0},
        "storage_label": label,
        "rows": rows,
        "errors": errors,
        "warnings": warnings,
        "ok": errors == 0,
    }


def _check_secret_file(var: str, target: str, *, service_uid: int,
                       stat_reader, mounts_reader, platform) -> dict:
    """One ``*_FILE`` target: existence, non-empty, mode, owner, mount."""
    try:
        st = stat_reader(target)
    except FileNotFoundError:
        return _row(
            var, "secret-file", target, ERROR,
            f"{var} names {target}, which does not exist",
            repair=f"provision the secret file at {target} (operator, via "
                   "the trusted secret manager or a host-authenticated "
                   f"SSH/Tailscale session), mode 0600, owned by uid "
                   f"{service_uid} — names and paths only, never commit "
                   "the value",
        )
    except OSError as exc:
        return _row(
            var, "secret-file", target, ERROR,
            f"{var} names {target}, which cannot be stat-ed ({exc})",
            repair=f"make {target} stat-able by the service user, mode "
                   "0600, owned by the service uid",
        )
    mode = _mode_bits(st)
    classify = _classify(target, mounts_reader, platform)
    extra = {
        "mode": oct(mode),
        "owner_uid": st.st_uid,
        "mount_type": classify.get("mount_type"),
        "is_persistent": classify.get("is_persistent"),
    }
    if st.st_size == 0:
        return _row(
            var, "secret-file", target, ERROR,
            f"{var} names {target}, which is empty — the shared resolver "
            "refuses an empty *_FILE target",
            repair=f"provision a non-empty secret file at {target} "
                   "(operator, via the trusted secret manager or a "
                   "host-authenticated session)",
            **extra,
        )
    if mode & 0o077:
        return _row(
            var, "secret-file", target, ERROR,
            f"{var} target {target} has mode {oct(mode)} — any group/other "
            "permission bit makes the shared resolver refuse it and leaks "
            "the secret to other local users",
            repair=f"chmod 600 {target}",
            **extra,
        )
    if st.st_uid != service_uid:
        return _row(
            var, "secret-file", target, ERROR,
            f"{var} target {target} is owned by uid {st.st_uid} but the "
            f"service runs as uid {service_uid} — with mode 0600 the "
            "service cannot read its own secret file",
            repair=f"chown {service_uid} {target} (fix the OWNERSHIP — "
                   "never widen the mode to compensate)",
            **extra,
        )
    verdict = _mount_verdict(classify)
    if verdict == ERROR:
        return _row(
            var, "secret-file", target, ERROR,
            f"{var} target {target} sits on an ephemeral "
            f"{classify.get('mount_type')} mount — a container recreate "
            "wipes it and the resolver then fails loud on the missing file",
            repair=f"move the secret file onto the persistent volume and "
                   f"point {var} at the new path",
            **extra,
        )
    if verdict == UNDETERMINABLE:
        return _row(
            var, "secret-file", target, UNDETERMINABLE,
            f"{var} target {target}: mode {oct(mode)}, owner uid "
            f"{st.st_uid} — but the backing mount could not be classified "
            "on this box (no readable mount table); persistence is "
            "UNDETERMINABLE, never guessed",
            **extra,
        )
    return _row(
        var, "secret-file", target, PASS,
        f"{var} target {target}: mode {oct(mode)}, owner uid {st.st_uid}, "
        f"backing mount {classify.get('mount_type')} (persistent)",
        **extra,
    )


def _check_secret_dir(path: str, *, service_uid: int, stat_reader) -> dict:
    """A directory holding secret files: mode 0700 (no group/other bits),
    owned by the service UID (D-P1 cure: ownership is verdicted here,
    mirroring _check_secret_file — a 0700 directory owned by another
    identity cannot be traversed by the service, so PASS on mode alone
    was a false pass)."""
    try:
        st = stat_reader(path)
    except OSError:
        return _row(
            f"dir:{path}", "secret-dir", path, INFO,
            "directory does not exist yet (nothing provisioned under it)",
        )
    mode = _mode_bits(st)
    if mode & 0o077:
        return _row(
            f"dir:{path}", "secret-dir", path, ERROR,
            f"secrets directory {path} has mode {oct(mode)} — group/other "
            "access exposes every secret file name and metadata under it",
            repair=f"chmod 700 {path}",
            mode=oct(mode), owner_uid=st.st_uid,
        )
    if st.st_uid != service_uid:
        return _row(
            f"dir:{path}", "secret-dir", path, ERROR,
            f"secrets directory {path} is owned by uid {st.st_uid} but "
            f"the service runs as uid {service_uid} — at mode 0700 a "
            "directory owned by another identity cannot be traversed, "
            "listed, or written by the service, so every secret file "
            "under it is unreachable",
            repair=f"chown {service_uid} {path} (fix the OWNERSHIP — "
                   "never widen the mode to compensate)",
            mode=oct(mode), owner_uid=st.st_uid,
        )
    return _row(
        f"dir:{path}", "secret-dir", path, PASS,
        f"secrets directory {path}: mode {oct(mode)}, owner uid {st.st_uid}",
        mode=oct(mode), owner_uid=st.st_uid,
    )


def _check_store(store: str, *, service_uid: int, service_gid: int,
                 stat_reader, mounts_reader, platform) -> dict:
    """One canonical env store: presence is optional; a PRESENT store must
    carry no group/other bit (the QC gate hard-asserts exactly 600 on the
    canonical store) and must not sit on an ephemeral mount."""
    try:
        st = stat_reader(store)
    except OSError:
        return _row(
            f"store:{store}", "store", store, INFO,
            "store absent (not a failure — values may live in another "
            "store or behind a *_FILE variable)",
        )
    mode = _mode_bits(st)
    classify = _classify(store, mounts_reader, platform)
    extra = {
        "mode": oct(mode),
        "owner_uid": st.st_uid,
        "mount_type": classify.get("mount_type"),
        "is_persistent": classify.get("is_persistent"),
    }
    if mode & 0o077:
        return _row(
            f"store:{store}", "store", store, ERROR,
            f"store {store} has mode {oct(mode)} — a plaintext credential "
            "store must be owner-only (the QC gate hard-asserts mode 600)",
            repair=f"chmod 600 {store}",
            **extra,
        )
    if classify.get("is_persistent") is False:
        return _row(
            f"store:{store}", "store", store, ERROR,
            f"store {store} sits on an ephemeral "
            f"{classify.get('mount_type')} mount — a container recreate "
            "wipes the box's credential store",
            repair="move the store under the durable root's persistent "
                   "volume and keep mode 0600",
            **extra,
        )
    if st.st_uid != service_uid:
        return _row(
            f"store:{store}", "store", store, WARN,
            f"store {store} is owned by uid {st.st_uid}; the service "
            f"(uid {service_uid}) cannot read a 0600 file it does not own "
            "— fine if this store is operator-only, a fault if the service "
            "is expected to resolve credentials from it",
            repair=f"if the service must read this store: chown "
                   f"{service_uid} {store} (never widen the mode)",
            **extra,
        )
    return _row(
        f"store:{store}", "store", store, PASS,
        f"store {store}: mode {oct(mode)}, owner uid {st.st_uid}, "
        f"backing mount {classify.get('mount_type')}",
        **extra,
    )


# ---------------------------------------------------------------------------
# Default (CLI) input assembly — sibling modules, lazily imported
# ---------------------------------------------------------------------------

def _default_box() -> dict:
    try:
        import browser_manager as bm

        return {
            "durable_root": bm.durable_root(),
            "is_vps": bm.is_vps(),
            "supervisor": bm.supervisor(),
            "platform": sys.platform,
        }
    except Exception:  # noqa: BLE001 - the verifier reports, never dies
        return {"durable_root": "", "is_vps": None, "supervisor": "",
                "platform": sys.platform}


def _default_paths(box: dict) -> dict:
    from ghl_vps_mount_proof import default_pathset

    paths = default_pathset(
        durable_root=box.get("durable_root") or "",
        secrets_dir=os.path.join(
            os.path.expanduser("~"), ".openclaw", "secrets"),
    )
    try:
        import cc_board

        paths["evidence_base"] = cc_board.resolve_evidence_base()
    except Exception:  # noqa: BLE001
        paths["evidence_base"] = ""
    try:
        import ghl_run_state

        # The ACTUAL run-state root (env override + durable resolution
        # included), not a re-derived formula.
        paths["run_state_root"] = ghl_run_state.default_state_root()
    except Exception:  # noqa: BLE001
        pass
    return paths


def _default_stores() -> List[str]:
    try:
        import ghl_secret_resolver as resolver

        return [os.path.expanduser(p) for p in resolver.ENV_STORES]
    except Exception:  # noqa: BLE001
        return [os.path.expanduser("~/.openclaw/secrets/.env")]


def _client_slug(client: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", (client or "").lower()).strip("-")
    return slug or "default"


def _atomic_write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def receipt_paths(receipt: dict, *, evidence_root: str = "") -> List[str]:
    """Where a full run writes the receipt: namespaced per client under the
    durable root (S06-05 step 4), plus the evidence-root routing copy when
    an evidence root is supplied (step 5)."""
    out: List[str] = []
    durable_root = (receipt.get("box") or {}).get("durable_root") or ""
    if durable_root:
        out.append(os.path.join(
            durable_root, "skill6-provisioning",
            _client_slug(receipt.get("client") or ""),
            "provisioning-receipt.json",
        ))
    if evidence_root:
        out.append(os.path.join(
            evidence_root, "routing", "provisioning-receipt.json"))
    return out


def write_receipts(receipt: dict, *, evidence_root: str = "") -> List[str]:
    written = []
    for path in receipt_paths(receipt, evidence_root=evidence_root):
        _atomic_write_json(path, receipt)
        written.append(path)
    return written


def finding_lines(receipt: dict) -> List[str]:
    """The advisory surface: one WARN-prefixed line per non-PASS row,
    mirroring the stale-env preflight's line shape."""
    lines = []
    for row in receipt.get("rows", []):
        if row["status"] == PASS:
            continue
        line = (f"WARN (provision preflight, S06-05): "
                f"[{row['status']}] {row['name']}: {row['detail']}")
        if row.get("repair"):
            line += f" Repair: {row['repair']}"
        lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# Self-test — hermetic fixtures only (injected stat / mounts / uid)
# ---------------------------------------------------------------------------

def _selftest() -> int:
    import collections

    errors: List[str] = []
    fake_stat = collections.namedtuple(
        "FakeStat", ["st_mode", "st_uid", "st_gid", "st_size"])

    def reader_for(table):
        def _read(path):
            if path not in table:
                raise FileNotFoundError(path)
            return table[path]
        return _read

    def mounts_ext4():
        return [("/dev/vda1", "/", "ext4", "rw,relatime")]

    base_paths = {
        "agent_browser_state": "/home/node/.agent-browser",
        "evidence_base": "",
        "run_state_root": "/data/.openclaw/skill6-runs",
        "playwright_data_dir": "/data/.openclaw/playwright-data/ghl-install-pages",
        "secrets_dir": "/home/node/.openclaw/secrets",
    }
    box = {"durable_root": "/data/.openclaw", "is_vps": True,
           "supervisor": "pm2-or-systemd", "platform": "linux"}

    # 1. Happy path: file 0600 owned by the service uid on a durable mount.
    table = {
        "/run/secrets/refresh": fake_stat(0o100600, 1000, 1000, 42),
        "/run/secrets": fake_stat(0o40700, 1000, 1000, 0),
        "/home/node/.openclaw/secrets/.env": fake_stat(0o100600, 1000, 1000, 10),
        "/home/node/.openclaw/secrets": fake_stat(0o40700, 1000, 1000, 0),
    }
    receipt = verify_provisioning(
        client="fixtureloc",
        env={"GHL_REFRESH_TOKEN_FILE": "/run/secrets/refresh"},
        paths=base_paths,
        stores=["/home/node/.openclaw/secrets/.env"],
        service_uid=1000, service_gid=1000,
        stat_reader=reader_for(table), mounts_reader=mounts_ext4,
        platform="linux", box=box,
    )
    if not receipt["ok"]:
        errors.append(f"happy path must be ok: {receipt['rows']}")

    # 2. Loose mode (0644) is an ERROR whose repair narrows (chmod 600).
    table["/run/secrets/refresh"] = fake_stat(0o100644, 1000, 1000, 42)
    receipt = verify_provisioning(
        client="fixtureloc",
        env={"GHL_REFRESH_TOKEN_FILE": "/run/secrets/refresh"},
        paths=base_paths, stores=[], service_uid=1000, service_gid=1000,
        stat_reader=reader_for(table), mounts_reader=mounts_ext4,
        platform="linux", box=box,
    )
    row = next(r for r in receipt["rows"] if r["name"] == "GHL_REFRESH_TOKEN_FILE")
    if row["status"] != ERROR or "chmod 600" not in row["repair"]:
        errors.append(f"loose mode must ERROR with a chmod 600 repair: {row}")
    if receipt["ok"]:
        errors.append("loose mode must fail the gate")

    # 3. Root service is an ERROR row.
    receipt = verify_provisioning(
        client="fixtureloc", env={}, paths=base_paths, stores=[],
        service_uid=0, service_gid=0, stat_reader=reader_for({}),
        mounts_reader=mounts_ext4, platform="linux", box=box,
    )
    row = next(r for r in receipt["rows"] if r["name"] == "service-identity")
    if row["status"] != ERROR:
        errors.append(f"root service must be an ERROR row: {row}")

    # 4. No mount table -> UNDETERMINABLE pathset rows, never guessed.
    receipt = verify_provisioning(
        client="fixtureloc", env={}, paths=base_paths, stores=[],
        service_uid=1000, service_gid=1000, stat_reader=reader_for({}),
        mounts_reader=lambda: [], platform="linux", box=box,
    )
    row = next(r for r in receipt["rows"] if r["name"] == "pathset:run_state_root")
    if row["status"] != UNDETERMINABLE:
        errors.append(f"empty mount table must be UNDETERMINABLE: {row}")

    # 5. Tripwire only: a value-shaped string must not appear in the
    #    receipt JSON. This assertion is NOT the no-secret evidence (the
    #    string is not an input to anything here) — the guarantee is
    #    structural: this module only stats its targets and never opens
    #    one for reading. The planted-content proof (real value-shaped
    #    content at a *_FILE target and in a store, asserted absent from
    #    receipt, finding lines, and the written receipt) lives in
    #    tests/test_ghl_vps_provision_check.py (D-P2 cure).
    blob = json.dumps(receipt)
    if "fixture-secret-value" in blob:
        errors.append("receipt leaked a value-shaped string")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — VPS provisioning verifier mechanism verified "
          "(hermetic fixtures, no network, no real secrets)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_vps_provision_check",
        description="S06-05: verify a box's VPS provisioning (secret-file "
                    "layout, ownership, modes, mounts, storage label) "
                    "against the ENV-MATRIX provisioning contract.",
    )
    p.add_argument("--client", default="",
                   help="Client/location identity the receipt is namespaced "
                        "under (required unless --selftest).")
    p.add_argument("--evidence-root", default="",
                   help="Also write the receipt to "
                        "<evidence-root>/routing/provisioning-receipt.json.")
    p.add_argument("--storage-label", default="",
                   help=f"Operator-named storage policy label (default: "
                        f"{DEFAULT_STORAGE_LABEL!r}).")
    p.add_argument("--service-uid", type=int, default=None,
                   help="Assert ownership against this service uid "
                        "(default: the current process uid).")
    p.add_argument("--advisory", action="store_true",
                   help="Print finding lines only, write nothing, always "
                        "exit 0 (the bm_ensure wiring mode).")
    p.add_argument("--json", action="store_true",
                   help="Print the full receipt JSON to stdout.")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.client:
        p.error("--client is required (the receipt is namespaced by it)")

    if args.advisory:
        try:
            receipt = verify_provisioning(
                client=args.client, service_uid=args.service_uid,
                storage_label=args.storage_label,
            )
            for line in finding_lines(receipt):
                print(line)
        except Exception as exc:  # noqa: BLE001 - advisory never blocks
            print(f"WARN (provision preflight, S06-05): [UNDETERMINABLE] "
                  f"verifier could not run: {type(exc).__name__}: {exc}")
        return 0

    receipt = verify_provisioning(
        client=args.client, service_uid=args.service_uid,
        storage_label=args.storage_label,
    )
    written = write_receipts(receipt, evidence_root=args.evidence_root)
    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        for row in receipt["rows"]:
            print(f"[{row['status']}] {row['name']}: {row['detail']}")
            if row.get("repair"):
                print(f"    repair: {row['repair']}")
        print(f"provision check: {'OK' if receipt['ok'] else 'FAILED'} "
              f"({receipt['errors']} error(s), {receipt['warnings']} "
              f"warning(s)) — storage label: {receipt['storage_label']}")
    for path in written:
        print(f"[ghl_vps_provision_check] receipt written: {path}",
              file=sys.stderr)
    if not written:
        print("[ghl_vps_provision_check] no durable root and no "
              "--evidence-root — receipt printed only, not persisted",
              file=sys.stderr)
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
