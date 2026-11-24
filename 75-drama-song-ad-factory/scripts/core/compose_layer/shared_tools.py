"""Shared video tools on Contabo (row N-111, section 3D.9).

- ONE pinned bundle is the master copy, kept in object storage:
  HyperFrames, Remotion, the pinned ``chrome-headless-shell``, ffmpeg and
  their fixed versions, with a fingerprint.
- Each server pulls the bundle once to ``/opt/shared-video-tools`` and
  checks the fingerprint. A new pinned version is pulled the same way; the
  old one is removed only after the new one passes its health check.
- Containers mount it READ-ONLY.
- Only programs are shared, never client data: run folders, locks,
  pictures, clips, temp profile folders and credentials stay inside that
  client's own container. A temp profile folder is never created under the
  shared path.
- Pre-flight checks the mounted bundle's fingerprint and records the
  versions in the run lock.

Stdlib only. This module never downloads and never mounts; it returns the
plan and checks what the box reports.
"""
from __future__ import annotations

import hashlib
import json
import os

from .wrapper import SHARED_ROOT, WRAPPER_TAG

TOOL_NAME = "compose_shared_tools"
TOOL_VERSION = "1.0.0"

#: The one server-side path is defined with the wrapper so the temp-folder
#: guard and the bundle checks can never disagree (3D.9).
CONTAINER_ROOT = "/opt/shared-video-tools"
BUNDLE_URL_ENV = "DSAF_VIDEO_TOOLS_BUNDLE_URL"

SHARED_PROGRAMS = ("hyperframes", "remotion", "chrome-headless-shell", "ffmpeg")

FINGERPRINT_MISMATCH = "SHARED_TOOLS_FINGERPRINT_MISMATCH"
CLIENT_DATA_IN_SHARED_TOOLS = "CLIENT_DATA_IN_SHARED_TOOLS"
MOUNT_NOT_READ_ONLY = "SHARED_TOOLS_MOUNT_NOT_READ_ONLY"
BUNDLE_INCOMPLETE = "SHARED_TOOLS_BUNDLE_INCOMPLETE"
BUNDLE_URL_MISSING = "SHARED_TOOLS_BUNDLE_URL_MISSING"


class SharedToolsError(RuntimeError):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def _is_inside(path, root):
    path = os.path.abspath(path)
    root = os.path.abspath(root)
    return path == root or path.startswith(root + os.sep)


def fingerprint_tree(root, skip_tags=(WRAPPER_TAG,)):
    """Deterministic sha256 over relative paths and bytes.

    Tagged temp profile folders are never part of the bundle; a symlink that
    leaves the root is refused rather than followed.
    """
    digest = hashlib.sha256()
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise SharedToolsError(BUNDLE_INCOMPLETE, "not a directory: %s" % root)
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs
                         if not any(d.startswith(tag) for tag in skip_tags))
        for name in sorted(files):
            full = os.path.join(current, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            digest.update(rel.encode("utf-8") + b"\0")
            if os.path.islink(full):
                target = os.path.realpath(full)
                if not _is_inside(target, root):
                    raise SharedToolsError(
                        FINGERPRINT_MISMATCH,
                        "symlink leaves the bundle: %s" % rel)
                digest.update(b"link\0" + os.readlink(full).encode("utf-8"))
            else:
                with open(full, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1 << 20), b""):
                        digest.update(chunk)
    return digest.hexdigest()


def verify_bundle(root, expected_fingerprint, fingerprint=None):
    actual = (fingerprint or fingerprint_tree)(root)
    ok = bool(expected_fingerprint) and actual == expected_fingerprint
    return {"ok": ok, "root": os.path.abspath(root),
            "expected": expected_fingerprint, "actual": actual,
            "code": None if ok else FINGERPRINT_MISMATCH}


def pull_plan(target=None, staging=None, bundle_url=None, expected_fingerprint=None,
              health_argv=None):
    """The pull, verify, health-check, publish, remove-old sequence (3D.9)."""
    url = bundle_url or os.environ.get(BUNDLE_URL_ENV)
    if not url:
        raise SharedToolsError(BUNDLE_URL_MISSING,
                               "%s is not set" % BUNDLE_URL_ENV)
    target = target or SHARED_ROOT
    staging = staging or target + ".incoming"
    old = target + ".old"
    return {
        "bundle_url": url,
        "target": target,
        "staging": staging,
        "old": old,
        "expected_fingerprint": expected_fingerprint,
        "steps": [
            {"step": "download", "to": staging},
            {"step": "verify-fingerprint", "root": staging,
             "expected": expected_fingerprint},
            {"step": "health-check", "root": staging,
             "argv": health_argv or ["ffmpeg", "-version"]},
            {"step": "move-current-aside", "from": target, "to": old},
            {"step": "publish", "from": staging, "to": target},
            {"step": "remove-old", "path": old,
             "only_after": "health-check passed"},
        ],
        "note": "the old bundle is removed only after the new one answers "
                "its health check",
    }


def mount_argv(host_root=None, container_root=CONTAINER_ROOT):
    """Read-only mount; no container can change another client's tools."""
    host = host_root or SHARED_ROOT
    return ["-v", "%s:%s:ro" % (host, container_root)]


def mount_is_read_only(mountinfo_text, mount_point=CONTAINER_ROOT):
    """Read a Linux mountinfo dump; None when the mount is not listed."""
    wanted = os.path.abspath(mount_point)
    for line in (mountinfo_text or "").splitlines():
        fields = line.split()
        if len(fields) < 6:
            continue
        # mountinfo: id parent major:minor root mountpoint options ...
        if os.path.abspath(fields[4]) != wanted:
            continue
        options = fields[5].split(",")
        return "ro" in options
    return None


def require_read_only(mountinfo_text, mount_point=CONTAINER_ROOT):
    state = mount_is_read_only(mountinfo_text, mount_point)
    if state is not True:
        raise SharedToolsError(MOUNT_NOT_READ_ONLY,
                               "%s is not mounted read-only" % mount_point)
    return True


def guard_no_client_data(run_dir, extra_paths=(), shared_root=None):
    """Client paths never live under the shared tools path (3D.9)."""
    root = shared_root or SHARED_ROOT
    offenders = [p for p in (run_dir, *extra_paths)
                 if p and _is_inside(p, root)]
    if offenders:
        raise SharedToolsError(
            CLIENT_DATA_IN_SHARED_TOOLS,
            "client data under the shared tools path: %s" % ", ".join(offenders))
    return True


def tagged_temp_folders(root=None):
    """Temp profile folders left under the shared path: never allowed there."""
    root = root or SHARED_ROOT
    found = []
    try:
        for name in os.listdir(root):
            if name.startswith(WRAPPER_TAG):
                found.append(os.path.join(root, name))
    except OSError:
        return found
    return found


def bundle_versions(root=None):
    """The versions recorded with the pinned bundle, when it ships them."""
    root = root or SHARED_ROOT
    for name in ("versions.json", "manifest.json"):
        path = os.path.join(root, name)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        versions = data.get("versions", data)
        return {name: versions.get(name) for name in SHARED_PROGRAMS}
    return {name: None for name in SHARED_PROGRAMS}


def preflight(root=None, expected_fingerprint=None, mountinfo_text=None,
              run_dir=None):
    """Pre-flight record for the run lock (3D.3/3D.9): fingerprint + versions."""
    root = root or SHARED_ROOT
    record = {
        "root": os.path.abspath(root),
        "versions": bundle_versions(root),
        "read_only": mount_is_read_only(mountinfo_text, root)
        if mountinfo_text is not None else None,
        "tagged_temp_folders": tagged_temp_folders(root),
        "fingerprint": None,
        "fingerprint_ok": False,
    }
    try:
        record["fingerprint"] = fingerprint_tree(root)
        record["fingerprint_ok"] = bool(expected_fingerprint) and (
            record["fingerprint"] == expected_fingerprint)
    except SharedToolsError as exc:
        record["error"] = exc.code
    if run_dir:
        guard_no_client_data(run_dir, shared_root=root)
    return record
