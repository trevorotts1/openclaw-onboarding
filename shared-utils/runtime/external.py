#!/usr/bin/env python3
"""external.py - verified external storage, destinations and child propagation.

Contract basis: Purple Billboard STORAGE.md, DEC-09/DEC-20, and the T-38
acceptance clause "engineering project temp/output/cache propagation is external
and verified; no assumed browser or internal fallback". Python 3 stdlib only.

Doctrine, enforced in code:

  * A bind is verified, never assumed. The mount must exist as a mount; a
    declared media UUID is only ever confirmed by an actual probe, and when no
    probe exists the result is a refusal, not a claim.
  * Every destination is resolved through ONE function that rejects a symlink
    component, a path outside the approved root, a path on the internal disk
    family and a path on a different device. There is no "try /tmp" branch:
    `temp_env`, `probe_child` and `resolve_destinations` run the same admission
    as the adapters, so an internal target is refused before anything is
    created or launched.
  * A destination handle is opened with O_NOFOLLOW and fstat'd. Its device and
    inode are rechecked against the visible path immediately before a write and
    again after publication; a rebound directory is a named refusal.
  * Publication never replaces an existing ledger file, and updates are atomic
    (temp file in the same directory + os.replace) after the same recheck.
  * Child propagation is proven by launching an actual child process with the
    intended TMPDIR/TMP/TEMP and observing its tempfile directory, the real
    parent of a file it created and that file's device. A Python probe proves
    that process path only; tool-specific cache/output settings are returned
    for tools this module can name, and an unknown tool is refused rather than
    silently assumed controlled.
  * The variables do not control every OS/library write. That ceiling is stated
    in `tool_output_options` and in the receipt, never papered over.

Import from a sibling checkout::

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from runtime.external import verify_mount, resolve_destinations, probe_child

Assert-based self-check:  python3 -I external.py
"""

from __future__ import annotations

import ast
import errno
import inspect
import json
import os
import re
import shutil
import stat as stat_module
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ── refusals ────────────────────────────────────────────────────────────────

class StorageError(RuntimeError):
    """Storage contract violation. Every subclass names the failed clause."""

class MissingMount(StorageError):
    """The approved external volume is not present. No internal fallback."""

class PathRejected(StorageError):
    """A destination is linked, internal, escaping or otherwise not admissible."""

class CapacityError(StorageError):
    """Verified free space does not cover the measured demand."""

class ReboundDestination(StorageError):
    """The visible path no longer resolves to the opened directory."""

class PropagationError(StorageError):
    """A child process did not inherit the verified external temp directory."""

class UnsupportedTool(StorageError):
    """No verified tool-specific cache/output configuration is known."""

# Internal-storage families. Writing project output here is never a fallback.
INTERNAL_ROOTS: Tuple[str, ...] = (
    "/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp", "/dev/shm",
)
INTERNAL_TEMP_MARKERS: Tuple[str, ...] = (
    "/var/folders/", "/private/var/folders/",
)

# roles -> directory under the approved root, exactly as STORAGE.md "Required
# per-run layout" names them: worktrees/<run-id>/<repository>/<unit>,
# scratch/<run-id>/<unit>, tmp/purple-billboard/<run-id>,
# tmp/purple-billboard-caches/<run-id>, plus the retained control/evidence
# directory outside the disposable trees. The <repository>/<unit> depth under
# worktree and scratch is created by the caller that knows those names; this
# mapping owns the per-run directory itself.
#   output is the one role STORAGE.md does not name ("test/build outputs use
#   that layout"); it lives beside the contracted tmp trees instead of
#   inventing a fourth top-level root.
LAYOUT: Mapping[str, str] = {
    "worktree": "worktrees",
    "scratch": "scratch",
    "temp": "tmp/purple-billboard",
    "cache": "tmp/purple-billboard-caches",
    "output": "tmp/purple-billboard-outputs",
    "ledger": "ledgers",
}
DISPOSABLE_ROLES = frozenset({"worktree", "scratch", "temp", "cache", "output"})

# One run id, one path segment: no separators, no whitespace, no control
# characters, no leading dot. A name that is not this shape is refused rather
# than half-sanitised.
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


# ── identity ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MountIdentity:
    """What was actually observed about an approved external root."""

    path: str
    device: int
    media_uuid: Optional[str] = None
    filesystem: Optional[str] = None
    limitations: Tuple[str, ...] = ()

@dataclass(frozen=True)
class Destination:
    """A resolved destination. inode is 0 until it has been created."""

    role: str
    path: str
    device: int
    inode: int = 0

@dataclass(frozen=True)
class ChildProbe:
    """Receipt for an actual child-process propagation probe."""

    command: Tuple[str, ...]
    exit_code: int
    expected_temp: str
    observed: Mapping[str, Any]

    @property
    def verified(self) -> bool:  # only constructed on success
        return True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "command": list(self.command),
            "exit_code": self.exit_code,
            "expected_temp": self.expected_temp,
            "observed": dict(self.observed),
        }


# ── mount verification ──────────────────────────────────────────────────────

_MEDIA_CACHE: Dict[int, Dict[str, Any]] = {}

def _darwin_media_probe(path: str) -> Optional[Dict[str, Any]]:
    """What diskutil observes about the volume holding `path`.

    Offline; no network. Cached per device so a repeated admission costs one
    probe. Returns None when this host cannot observe the media identity at
    all - which is a fact about the host, never a licence to claim one.
    """
    try:
        device = os.stat(path).st_dev
    except OSError:
        return None
    if device in _MEDIA_CACHE:
        return _MEDIA_CACHE[device]
    try:
        out = subprocess.run(
            ["/usr/sbin/diskutil", "info", "-plist", path],
            capture_output=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout:
        return None
    try:
        import plistlib
        info = plistlib.loads(out.stdout)
    except Exception:
        return None
    facts: Dict[str, Any] = {"uuid": None, "internal": bool(info.get("Internal"))}
    for key in ("VolumeUUID", "MediaUUID", "DiskUUID"):
        value = info.get(key)
        if value:
            facts["uuid"] = str(value)
            break
    _MEDIA_CACHE[device] = facts
    return facts

def _darwin_uuid_probe(path: str) -> Optional[str]:
    """Read the volume UUID from diskutil. Offline; no network."""
    facts = _darwin_media_probe(path)
    return facts.get("uuid") if facts else None

def verify_mount(path: str, *, expected_uuid: Optional[str] = None,
                 required_bytes: int = 0,
                 uuid_probe: Optional[Any] = None,
                 require_mount: bool = True,
                 require_media_uuid: bool = False) -> MountIdentity:
    """Verify the approved root. Raises instead of assuming anything.

    `require_mount=False` is only for a caller verifying a directory it has
    already proven is reached through a bind (the Docker adapter does its own
    mount-info check); the default refuses a non-mount root. It relaxes the
    mount-point test only - it never relaxes anything else.

    Media identity (STORAGE.md admission step 1, "media UUID matches"): when
    this host can observe the volume identity it is recorded on the result even
    if the contract declares none, and a declared UUID is confirmed by a real
    probe only. `require_media_uuid=True` refuses admission when no identity
    could be observed at all.
    """
    if not path or not os.path.isabs(path):
        raise PathRejected("path_not_absolute: %r" % (path,))
    if not os.path.exists(path):
        raise MissingMount(
            "missing_mount: %s is absent; mount the external volume and retry "
            "(no /tmp, internal-disk or anonymous-volume fallback)" % path)
    if not os.path.isdir(path):
        raise PathRejected("not_a_directory: %s" % path)
    if require_mount and not os.path.ismount(path):
        raise PathRejected("not_a_mount_point: %s" % path)

    limitations = []
    st = os.stat(path)
    if required_bytes:
        free = shutil.disk_usage(path).free
        if free < required_bytes:
            raise CapacityError(
                "insufficient_space: %s has %d free bytes, %d required"
                % (path, free, required_bytes))

    media_uuid = None
    internal_media = None
    probe_available = True
    if uuid_probe is not None:
        media_uuid = uuid_probe(path)
    else:
        facts = _darwin_media_probe(path) if sys.platform == "darwin" else None
        probe_available = facts is not None
        if facts is not None:
            media_uuid = facts.get("uuid")
            internal_media = facts.get("internal")
    if expected_uuid is not None:
        if not probe_available:
            raise StorageError(
                "media_uuid_unverified: %s declares %r but this host has no "
                "identity probe; refusing to claim the volume"
                % (path, expected_uuid))
        if not media_uuid:
            raise StorageError(
                "media_uuid_unverified: probe returned no identity for %s" % path)
        if str(media_uuid).lower() != str(expected_uuid).lower():
            raise StorageError(
                "media_uuid_mismatch: %s reports %r, contract declares %r"
                % (path, media_uuid, expected_uuid))
    elif media_uuid:
        limitations.append(
            "media_uuid_not_declared: observed %s; the contract declares none, "
            "so this is an observation and not a claimed match" % media_uuid)
    else:
        limitations.append("media_uuid_not_declared: identity not claimed")
    if require_media_uuid and not media_uuid:
        raise StorageError(
            "media_uuid_unverified: %s has no observed media identity; "
            "admission step 1 (media UUID matches) cannot be claimed" % path)
    if internal_media:
        limitations.append(
            "media_on_internal_disk: diskutil reports Internal=true for %s; "
            "device inequality against the root disk is the externality proof"
            % path)

    return MountIdentity(path=path, device=st.st_dev, media_uuid=media_uuid,
                         filesystem=None,
                         limitations=tuple(limitations))


# ── destination resolution and rejection ────────────────────────────────────

def _symlink_component(path: str) -> Optional[str]:
    """First symlink component of an absolute path, root-down. None if clean."""
    current = os.path.sep
    for part in os.path.abspath(path).strip(os.sep).split(os.sep):
        if not part:
            continue
        current = os.path.join(current, part)
        if os.path.islink(current):
            return current
    return None

def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path),
                                   os.path.abspath(root)]) == os.path.abspath(root)
    except ValueError:
        return False

def _nearest_existing(path: str) -> str:
    probe = os.path.abspath(path)
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    return probe

def _on_external_device(path: str) -> bool:
    """True when `path` is not on the internal root disk.

    Device inequality is this module's proof of "external": a mount point on
    the internal root disk is still internal storage.
    """
    probe = _nearest_existing(path)
    if not probe or not os.path.exists(probe):
        return False
    return os.stat(probe).st_dev != os.stat(os.sep).st_dev

def _reject_internal(path: str, *, home_roots: Sequence[str],
                     lift_home: bool,
                     internal_roots: Sequence[str],
                     internal_temp_markers: Sequence[str]) -> None:
    for internal in internal_roots:
        if path == internal or path.startswith(internal.rstrip(os.sep) + os.sep):
            raise PathRejected(
                "internal_fallback: %s is internal storage (%s)" % (path, internal))
    for marker in internal_temp_markers:
        if path.startswith(marker):
            raise PathRejected(
                "internal_temp: %s is an OS temp tree (%s)" % (path, marker))
    for home in home_roots:
        if path == home or path.startswith(home.rstrip(os.sep) + os.sep):
            if not lift_home:
                raise PathRejected(
                    "internal_home: %s is inside a home directory; project work "
                    "belongs on the approved external root" % path)

def _home_default() -> Tuple[str, ...]:
    return (os.path.abspath(os.path.expanduser("~")),)

def _admit_root(root: str, *, bind_proven: bool,
                internal_roots: Sequence[str] = INTERNAL_ROOTS,
                internal_temp_markers: Sequence[str] = INTERNAL_TEMP_MARKERS,
                home_roots: Optional[Sequence[str]] = None) -> str:
    """Admit an approved root, or raise. `bind_proven` is REQUIRED, not
    defaulted, on this and on every entry point that reaches it: the proof of
    binding is an argument a caller cannot forget to pass, so no wrapper can
    silently re-run the admission with the proof dropped (the defect class that
    has shipped three times). It is the caller stating it
    has already proven this root is an approved host bind (Docker mount-info
    proof, an operator-declared dedicated VPS volume); it never excuses an
    internal temp tree. `home_roots` defaults to the real user home and is
    caller-tunable exactly like `internal_roots`, for the caller that has
    already proven an approved root that happens to live under a home.
    """
    if not root or not os.path.isabs(root):
        raise PathRejected("path_not_absolute: %r" % (root,))
    normal = os.path.normpath(root)
    linked = _symlink_component(normal)
    if linked is not None:
        raise PathRejected("symlink_component: %s (component %s)" % (normal, linked))
    homes = _home_default() if home_roots is None else tuple(home_roots)
    _reject_internal(normal, home_roots=homes,
                     lift_home=_on_external_device(normal) or bind_proven,
                     internal_roots=internal_roots,
                     internal_temp_markers=internal_temp_markers)
    if not bind_proven and not _on_external_device(normal):
        raise PathRejected(
            "internal_fallback: %s is on the internal root disk (device %d); an "
            "approved root must be a proven external destination and there is "
            "no internal fallback" % (normal, os.stat(os.sep).st_dev))
    return normal

def assert_external(path: str, root: Optional[str] = None, *,
                    bind_proven: bool,
                    internal_roots: Sequence[str] = INTERNAL_ROOTS,
                    internal_temp_markers: Sequence[str] = INTERNAL_TEMP_MARKERS,
                    home_roots: Optional[Sequence[str]] = None,
                    check_device: bool = True) -> str:
    """Admit one destination path or raise a named refusal.

    `bind_proven` has NO default: it is the required proof-of-binding argument
    on the admission path. Omitting it is a `TypeError`, so a call that drops
    the proof cannot run at all; the omission is structurally impossible rather
    than merely discouraged. Every public entry point that reaches this
    function takes the same required argument and forwards it.

    Internal storage is named first, on the text AND on the OS resolution of the
    raw path, so neither a literal /tmp nor a symlink into one can be admitted.
    The raw path and its real target must then agree, so a symlink cannot be
    laundered through an interior "..". A path under a home directory is refused
    unless it is inside an approved root on proven external storage - the
    inverse case of a legitimately approved external mount that happens to live
    under a home. With no `root`, the path itself has to be proven external;
    `assert_external` is therefore also the admission used by `temp_env` and
    `probe_child`.
    """
    if not path or not os.path.isabs(path):
        raise PathRejected("path_not_absolute: %r" % (path,))
    normal = os.path.normpath(path)
    resolved = os.path.realpath(path)
    homes = _home_default() if home_roots is None else tuple(home_roots)
    if root is not None:
        root_normal = _admit_root(root, bind_proven=bind_proven,
                                  internal_roots=internal_roots,
                                  internal_temp_markers=internal_temp_markers,
                                  home_roots=homes)
        lift_home = _inside(normal, root_normal) and (
            _on_external_device(root_normal) or bind_proven)
    else:
        root_normal = None
        lift_home = _on_external_device(normal) or bind_proven
    for candidate in (normal, resolved):
        _reject_internal(candidate, home_roots=homes, lift_home=lift_home,
                         internal_roots=internal_roots,
                         internal_temp_markers=internal_temp_markers)
    linked = _symlink_component(normal)
    if linked is not None:
        raise PathRejected("symlink_component: %s (component %s)" % (normal, linked))
    if os.path.abspath(resolved) != os.path.abspath(normal):
        raise PathRejected(
            "outside_approved_root: %s resolves to %s; a path whose text and its "
            "OS resolution disagree is refused (no symlink laundering)"
            % (path, resolved))
    if root_normal is not None:
        if not _inside(normal, root_normal):
            raise PathRejected("outside_approved_root: %s not under %s" % (normal, root_normal))
        if os.path.abspath(normal) == os.path.abspath(root_normal):
            raise PathRejected("destination_is_root: %s" % normal)
        if check_device and os.path.exists(normal):
            if os.stat(normal).st_dev != os.stat(root).st_dev:
                raise PathRejected(
                    "different_device: %s is on device %d, root %s on %d"
                    % (normal, os.stat(normal).st_dev, root, os.stat(root).st_dev))
    elif not _on_external_device(normal):
        raise PathRejected(
            "internal_fallback: %s is on the internal root disk (device %d); a "
            "destination must be on proven external storage" % (normal, os.stat(os.sep).st_dev))
    return normal

def resolve_destinations(root: str, run_id: str, *, bind_proven: bool,
                         create: bool = False,
                         required_bytes: int = 0,
                         expected_uuid: Optional[str] = None,
                         uuid_probe: Optional[Any] = None,
                         require_mount: bool = True,
                         require_media_uuid: bool = False,
                         ) -> Dict[str, Destination]:
    """Resolve the required per-run layout. Writes nothing unless create=True.

    Roles: worktree, scratch, temp, cache, output, ledger. Every one is
    admitted through assert_external; a refusal names the clause. The root is
    admitted first: `require_mount=False` only relaxes the mount-point test,
    it never admits a root on the internal disk. `bind_proven` is required and
    is forwarded on every re-check inside the loop.
    """
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.match(run_id):
        raise PathRejected("bad_run_id: %r" % (run_id,))
    root = _admit_root(root, bind_proven=bind_proven)
    identity = verify_mount(root, expected_uuid=expected_uuid,
                            required_bytes=required_bytes, uuid_probe=uuid_probe,
                            require_mount=require_mount,
                            require_media_uuid=require_media_uuid)
    out: Dict[str, Destination] = {}
    for role, dirname in LAYOUT.items():
        path = os.path.join(identity.path, dirname, run_id)
        assert_external(path, identity.path, bind_proven=bind_proven)
        if create:
            try:
                os.makedirs(path, exist_ok=False)
            except FileExistsError:
                observed = os.lstat(path)
                if not stat_module.S_ISDIR(observed.st_mode):
                    raise PathRejected(
                        "non_regular_destination: %s exists and is not a "
                        "directory; an existing non-regular destination is "
                        "blocked" % path) from None
            assert_external(path, identity.path, bind_proven=bind_proven)
            st = os.stat(path)
            out[role] = Destination(role, path, st.st_dev, st.st_ino)
        else:
            out[role] = Destination(role, path, identity.device, 0)
    return out


# ── no-follow destination handle ────────────────────────────────────────────

class DestinationHandle:
    """An opened destination directory, rechecked around every write."""

    def __init__(self, path: str, fd: int, device: int, inode: int) -> None:
        self.path = path
        self._fd = fd
        self.device = device
        self.inode = inode
        self._closed = False

    def __enter__(self) -> "DestinationHandle":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False

    def verify(self) -> None:
        """The visible path must still be this directory. No symlink, no rebind."""
        if self._closed:
            raise ReboundDestination("handle_closed: %s" % self.path)
        try:
            st = os.lstat(self.path)
        except FileNotFoundError:
            raise ReboundDestination("destination_missing: %s" % self.path) from None
        if stat_module.S_ISLNK(st.st_mode):
            raise ReboundDestination(
                "destination_became_symlink: %s" % self.path)
        fd_st = os.fstat(self._fd)
        if (st.st_dev, st.st_ino) != (self.device, self.inode):
            raise ReboundDestination(
                "destination_rebound: %s now (%d,%d), handle (%d,%d)"
                % (self.path, st.st_dev, st.st_ino, self.device, self.inode))
        if (fd_st.st_dev, fd_st.st_ino) != (self.device, self.inode):
            raise ReboundDestination(
                "handle_rebound: fd (%d,%d) handle (%d,%d)"
                % (fd_st.st_dev, fd_st.st_ino, self.device, self.inode))

    def _write_temp(self, name: str, data: bytes, mode: int = 0o600) -> str:
        tmp_name = ".%s.tmp-%d-%s" % (name, os.getpid(), uuid.uuid4().hex)
        tmp_path = os.path.join(self.path, tmp_name)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW
        fd = os.open(tmp_path, flags, mode)
        try:
            with os.fdopen(fd, "wb", closefd=True) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return tmp_path

    def publish(self, name: str, data: bytes, mode: int = 0o600) -> str:
        """Create `name` without ever replacing an existing entry."""
        self.verify()
        final = os.path.join(self.path, name)
        tmp_path = self._write_temp(name, data, mode)
        try:
            os.link(tmp_path, final)
        except FileExistsError:
            raise PathRejected(
                "destination_exists: %s already exists; refusing to replace"
                % final) from None
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        self.verify()
        st = os.stat(final)
        if st.st_dev != self.device:
            raise ReboundDestination(
                "published_on_other_device: %s device %d, handle %d"
                % (final, st.st_dev, self.device))
        self._fsync_dir()
        return final

    def replace(self, name: str, data: bytes, mode: int = 0o600) -> str:
        """Atomic update of `name` after the same pre-write recheck."""
        self.verify()
        final = os.path.join(self.path, name)
        tmp_path = self._write_temp(name, data, mode)
        os.replace(tmp_path, final)
        self.verify()
        if os.stat(final).st_dev != self.device:
            raise ReboundDestination(
                "replaced_on_other_device: %s" % final)
        self._fsync_dir()
        return final

    def read(self, name: str) -> bytes:
        self.verify()
        path = os.path.join(self.path, name)
        fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
        try:
            st = os.fstat(fd)
            if st.st_dev != self.device:
                raise ReboundDestination(
                    "read_other_device: %s device %d, handle %d"
                    % (path, st.st_dev, self.device))
            chunks = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)

    def _fsync_dir(self) -> None:
        try:
            os.fsync(self._fd)
        except OSError as exc:  # some filesystems refuse; disclose, never fake
            if exc.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EBADF):
                raise

    def close(self) -> None:
        if not self._closed:
            os.close(self._fd)
            self._closed = True

def open_destination(path: str, *, bind_proven: bool,
                     expected: Optional[Destination] = None,
                     root: Optional[str] = None) -> DestinationHandle:
    """Open a destination without following links and hold its identity.

    `bind_proven` is REQUIRED and is forwarded to the admission, so this entry
    point can no longer re-run the check with the proof dropped while every
    other surface forwards it. With `root` the destination is admitted exactly
    like `assert_external`; without one, `expected` must be a `Destination`
    that `resolve_destinations` already admitted - that resolution is the
    documented trust anchor and its device/inode identity is re-checked below.
    A call with neither `root` nor `expected` is refused by name: there is no
    un-proven public open and no internal fallback.
    """
    if root is None and expected is None:
        raise PathRejected(
            "unproven_open: %s was opened with no approved root and no "
            "already-admitted Destination; there is no un-proven open and no "
            "internal fallback" % (path,))
    if root is not None:
        assert_external(path, root, bind_proven=bind_proven)
    linked = _symlink_component(path)
    if linked is not None:
        raise PathRejected("symlink_component: %s (component %s)" % (path, linked))
    if os.path.lexists(path):
        observed = os.lstat(path)
        if not stat_module.S_ISDIR(observed.st_mode):
            raise PathRejected(
                "non_regular_destination: %s exists and is not a directory; an "
                "existing non-regular destination is blocked" % path)
    fd = os.open(path, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW)
    st = os.fstat(fd)
    if expected is not None:
        if expected.inode and (st.st_dev, st.st_ino) != (expected.device, expected.inode):
            os.close(fd)
            raise ReboundDestination(
                "destination_changed_since_resolution: %s observed (%d,%d), "
                "resolved (%d,%d)"
                % (path, st.st_dev, st.st_ino, expected.device, expected.inode))
        if st.st_dev != expected.device:
            os.close(fd)
            raise ReboundDestination(
                "destination_wrong_device: %s observed %d, resolved %d"
                % (path, st.st_dev, expected.device))
    return DestinationHandle(os.path.abspath(path), fd, st.st_dev, st.st_ino)


# ── process environment and child propagation ───────────────────────────────

CHILD_PROBE_SOURCE = r"""
import json, os, tempfile
tmpdir = tempfile.gettempdir()
d = os.path.realpath(tmpdir)
handle = tempfile.NamedTemporaryFile(prefix="pbb-probe-", delete=False)
handle.write(b"pbb-propagation-probe")
handle.flush()
os.fsync(handle.fileno())
path = handle.name
handle.close()
st = os.stat(path)
parent = os.path.dirname(os.path.realpath(path))
os.unlink(path)
print(json.dumps({
    "TMPDIR": os.environ.get("TMPDIR"),
    "TMP": os.environ.get("TMP"),
    "TEMP": os.environ.get("TEMP"),
    "gettempdir": tmpdir,
    "gettempdir_real": d,
    "file_parent_real": parent,
    "file_device": st.st_dev,
    "file_created": True,
    "file_removed": not os.path.exists(path),
}))
"""

def temp_env(temp_dir: str, *, bind_proven: bool,
             root: Optional[str] = None) -> Dict[str, str]:
    """The per-process environment every engineering worker must be launched with.

    The directory is admitted exactly like a destination: an internal temp
    tree, an internal-disk path or the user home is a named refusal, so this
    function can never be the "try /tmp" branch of someone else's launcher.
    `bind_proven` is required and forwarded, exactly as on `assert_external`.
    """
    admitted = assert_external(temp_dir, root, bind_proven=bind_proven)
    return {"TMPDIR": admitted, "TMP": admitted, "TEMP": admitted}

def probe_child(temp_dir: str, *, bind_proven: bool,
                python: str = sys.executable,
                env: Optional[Mapping[str, str]] = None,
                timeout: int = 60,
                runner: Any = None,
                root: Optional[str] = None) -> ChildProbe:
    """Launch a real child with the intended temp environment and verify it.

    Proves: the three variables are the external directory, tempfile.gettempdir()
    resolves there, a file the child actually created has that real parent and
    the destination's device, and the child removed it. A failure names the
    failing clause with the observed value.

    The target is admitted before any child starts, so this probe can never
    certify propagation into internal storage.
    """
    admitted = assert_external(temp_dir, root, bind_proven=bind_proven)
    if not os.path.isdir(admitted):
        raise MissingMount("missing_temp_dir: %s" % admitted)
    real_expected = os.path.realpath(admitted)
    child_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    child_env.update(temp_env(admitted, root=root, bind_proven=bind_proven))
    if env:
        child_env.update(env)
    command = [python, "-I", "-c", CHILD_PROBE_SOURCE]
    run = runner or subprocess.run
    try:
        completed = run(command, capture_output=True, env=child_env,
                        timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PropagationError(
            "child_probe_failed: %s: %s" % (type(exc).__name__, exc)) from None
    if completed.returncode != 0:
        stderr = (completed.stderr or b"").decode("utf-8", "replace").strip()
        raise PropagationError(
            "child_probe_exit_%d: %s" % (completed.returncode, stderr[:400]))
    try:
        observed = json.loads((completed.stdout or b"").decode("utf-8"))
    except Exception:
        raise PropagationError(
            "child_probe_unreadable_output: %r" % (completed.stdout,)) from None

    for var in ("TMPDIR", "TMP", "TEMP"):
        value = observed.get(var)
        if not value or os.path.realpath(value) != real_expected:
            raise PropagationError(
                "child_env_%s: observed %r, expected %r" % (var, value, real_expected))
    if observed.get("gettempdir_real") != real_expected:
        raise PropagationError(
            "child_gettempdir: observed %r, expected %r"
            % (observed.get("gettempdir_real"), real_expected))
    if observed.get("file_parent_real") != real_expected:
        raise PropagationError(
            "child_file_parent: observed %r, expected %r"
            % (observed.get("file_parent_real"), real_expected))
    if not observed.get("file_created"):
        raise PropagationError("child_file_not_created: probe created nothing")
    expected_device = os.stat(admitted).st_dev
    if observed.get("file_device") != expected_device:
        raise PropagationError(
            "child_file_device: observed %r, expected %d"
            % (observed.get("file_device"), expected_device))
    if not observed.get("file_removed"):
        raise PropagationError("child_file_left_behind: probe could not remove it")
    return ChildProbe(command=tuple(command), exit_code=completed.returncode,
                      expected_temp=real_expected, observed=observed)

# Tools whose project cache/output paths this module can name. Anything else is
# refused: claiming the variables control an unnamed tool would be a false pass.
def tool_output_options(tool: str, destinations: Mapping[str, Destination],
                        *, bind_proven: bool,
                        root: Optional[str] = None) -> Dict[str, Any]:
    """Tool-specific cache/output configuration pointing at external paths.

    Ceiling, stated once: TMPDIR/TMP/TEMP and these settings cover the named
    tool's own project outputs. OS and library writes outside project control
    are disclosed by the caller's receipt, not silently included in a guarantee.

    `bind_proven` is REQUIRED and is forwarded on every re-check so an
    operator-declared dedicated volume is not re-refused here after it was
    admitted upstream - and so this surface cannot become the next place the
    proof gets dropped.
    """
    try:
        temp_dir = destinations["temp"].path
        cache_dir = destinations["cache"].path
        output_dir = destinations["output"].path
    except KeyError as exc:
        raise StorageError("missing_destination_role: %s" % exc) from None
    if root is not None:
        for path in (temp_dir, cache_dir, output_dir):
            assert_external(path, root, bind_proven=bind_proven)
    name = (tool or "").strip().lower()
    if name == "pytest":
        return {"env": {"PYTEST_ADDOPTS":
                        "--basetemp=%s -o cache_dir=%s"
                        % (os.path.join(temp_dir, "pytest"),
                           os.path.join(cache_dir, "pytest"))}}
    if name in ("npm", "pnpm", "yarn"):
        return {"env": {"npm_config_cache": os.path.join(cache_dir, name)}}
    if name == "pip":
        return {"env": {"PIP_CACHE_DIR": os.path.join(cache_dir, "pip")}}
    if name == "go":
        return {"env": {"GOCACHE": os.path.join(cache_dir, "go"),
                        "GOTMPDIR": os.path.join(temp_dir, "go")}}
    if name == "cargo":
        return {"env": {"CARGO_TARGET_DIR": os.path.join(output_dir, "cargo")}}
    raise UnsupportedTool(
        "tool_specific_options_unverified: %r has no verified external cache/"
        "output configuration in this adapter; add it before admitting the tool"
        % (tool,))


# ── the admission surface, derived not typed ────────────────────────────────

def admission_surfaces(exported: Sequence[str]) -> Tuple[Tuple[str, ...],
                                                         Tuple[str, ...]]:
    """(reaches_the_admission, carries_the_proof) over `exported`, derived.

    A name is an admission surface exactly when its own bytecode references
    `assert_external` or `_admit_root` - there is one admission path and this
    finds every way into it. A name is proof-carrying exactly when its
    signature has `bind_proven`. The two sets must be equal: a surface that
    reaches the admission without a required proof argument, or a proof
    argument on something that never admits, is the omission this module must
    not be able to ship again. No typed list of surface names is kept anywhere,
    because a typed list is what let a third instance reach `origin/main`.
    """
    reaches: List[str] = []
    carries: List[str] = []
    for name in exported:
        obj = globals().get(name)
        if obj is None or not callable(obj):
            continue
        code = getattr(obj, "__code__", None)
        if code is not None and ("assert_external" in code.co_names
                                 or "_admit_root" in code.co_names):
            reaches.append(name)
        try:
            params = inspect.signature(obj).parameters
        except (TypeError, ValueError):
            continue
        if "bind_proven" in params:
            carries.append(name)
    return tuple(sorted(reaches)), tuple(sorted(carries))

def _selfcheck_proof_is_required() -> None:
    """Every surface that admits must require the proof, with no default."""
    exported = [name for name in globals() if not name.startswith("_")]
    reaches, carries = admission_surfaces(exported)
    assert reaches == carries, (reaches, carries)
    assert reaches, "no admission surface was derived"
    for name in reaches:
        param = inspect.signature(globals()[name]).parameters["bind_proven"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY, name
        assert param.default is inspect.Parameter.empty, (
            "%s still gives bind_proven a default, so the proof can be dropped"
            % name)
    with open(__file__, encoding="utf-8") as source:
        tree = ast.parse(source.read())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", getattr(node.func, "attr", None))
        if name in ("assert_external", "_admit_root"):
            assert "bind_proven" in [kw.arg for kw in node.keywords], (
                "line %d calls %s without forwarding bind_proven"
                % (node.lineno, name))


# ── assert-based self-check (stdlib only) ───────────────────────────────────

def _selfcheck() -> None:
    """Run against the real external temp dir; refuses an internal one."""
    base = os.environ.get("TMPDIR") or tempfile.gettempdir()
    if any(base.startswith(marker) for marker in INTERNAL_TEMP_MARKERS):
        raise SystemExit(
            "selfcheck: TMPDIR %r is internal; set the verified external temp "
            "directory first (no internal fallback)" % base)
    work = tempfile.mkdtemp(prefix="pbb-external-selfcheck-")
    try:
        link = os.path.join(work, "link")
        os.symlink(work, link)
        try:
            assert_external(os.path.join(link, "x"), work, bind_proven=False)
        except PathRejected as exc:
            assert str(exc).startswith("symlink_component:"), exc
        else:
            raise AssertionError("a symlink component was admitted")
        try:
            assert_external("/private/tmp/pbb-nope", work, bind_proven=False)
        except PathRejected as exc:
            assert "internal" in str(exc), exc
        else:
            raise AssertionError("/private/tmp was admitted")
        try:
            open_destination("/Users/Shared/pbb-nope", bind_proven=False)
        except PathRejected as exc:
            assert str(exc).startswith("unproven_open:"), exc
        else:
            raise AssertionError("a bare open with no root and no admitted "
                                 "Destination was admitted")
        with open_destination(work, root=os.path.dirname(work),
                              bind_proven=False) as handle:
            handle.publish("one.txt", b"first")
            try:
                handle.publish("one.txt", b"second")
            except PathRejected as exc:
                assert str(exc).startswith("destination_exists:"), exc
            else:
                raise AssertionError("publication replaced an existing file")
            assert handle.read("one.txt") == b"first"
            handle.replace("one.txt", b"second")
            assert handle.read("one.txt") == b"second"
        probe = probe_child(base, bind_proven=False)
        assert probe.observed["file_created"] is True
        _selfcheck_proof_is_required()
        print("external.py self-check OK: %s" % probe.expected_temp)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    _selfcheck()
