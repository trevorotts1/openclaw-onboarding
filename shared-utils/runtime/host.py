#!/usr/bin/env python3
"""host.py - supported Mac, VPS and Docker runtime adapters.

Contract basis: Purple Billboard TODO T-38 and R-26/R-32/R-33; STORAGE.md
("a remote host/container needs its own explicit approved mount/bind identity;
the Mac path is not assumed to exist there"). Python 3 stdlib only.

Doctrine, enforced in code:

  * The host is detected from observed facts (platform, container markers,
    mount info). An unsupported host is refused by name; it is never silently
    treated as one of the supported three.
  * An adapter verifies its own bind. Mac requires a real external mount that
    is not the root disk. VPS requires an explicit approved bind source and
    refuses the root filesystem unless the operator declared a dedicated
    volume. Docker requires a host bind proven by mount info and refuses an
    overlay/tmpfs layer or a Docker-managed volume: an anonymous volume is not
    storage this project may write to.
  * A browser is NEVER assumed and NEVER required. `browser_capability()`
    reports "not_assumed" unless a real probe was supplied, and no adapter
    exposes a capability that depends on one.
  * Restart persistence is declared per adapter and stays UNVERIFIED until a
    real registration read-back is supplied. A documented launchd/systemd/
    Docker primitive is not evidence that a job is registered.
  * Nothing here launches, stops or registers a process: adapters return the
    plan and the exact read-back command; the caller supplies the observation.

Import::

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from runtime.host import detect_host, adapter_for

Assert-based self-check:  python3 -I host.py
"""

from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass, replace
from collections.abc import Mapping as MappingABC
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

try:  # package import; the fallback exists so `python3 host.py` self-checks
    from .external import (
        ChildProbe,
        Destination,
        MountIdentity,
        PathRejected,
        assert_external,
        open_destination,
        probe_child,
        resolve_destinations,
        temp_env,
        tool_output_options,
        verify_mount,
    )
except ImportError:  # pragma: no cover - direct execution
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from external import (  # type: ignore
        ChildProbe,
        Destination,
        MountIdentity,
        PathRejected,
        assert_external,
        open_destination,
        probe_child,
        resolve_destinations,
        temp_env,
        tool_output_options,
        verify_mount,
    )

RUNTIME_MAC = "mac"
RUNTIME_VPS = "vps"
RUNTIME_DOCKER = "docker"
SUPPORTED_RUNTIMES: Tuple[str, ...] = (RUNTIME_MAC, RUNTIME_VPS, RUNTIME_DOCKER)

BROWSER_NOT_ASSUMED = "not_assumed"
BROWSER_AVAILABLE = "available"
BROWSER_ABSENT = "absent"
BROWSER_PROBE_FAILED = "probe_failed"

# Filesystems that are the image layer or an ephemeral tmpfs, never a bind.
MANAGED_FSTYPES = frozenset({
    "overlay", "overlayfs", "tmpfs", "devtmpfs", "proc", "sysfs", "cgroup",
    "cgroup2", "ramfs",
})
DOCKER_MANAGED_PREFIXES = ("/var/lib/docker/", "/var/lib/containerd/")

def _is_managed_volume(source: str) -> bool:
    """True for a Docker/containerd-managed volume path, including the
    /private/var alias macOS uses for /var."""
    real = os.path.realpath(source)
    for prefix in DOCKER_MANAGED_PREFIXES:
        if real.startswith(prefix) or real.startswith(
                os.path.realpath(prefix.rstrip("/")) + "/"):
            return True
    return False

TERMINAL_STATES = {
    "launchd": ("state = running", "state = waiting"),
    "systemd": ("activestate=active", "active"),
    "container_restart_policy": ("always", "unless-stopped"),
}


# ── refusals ────────────────────────────────────────────────────────────────

class UnsupportedHost(RuntimeError):
    """Observed host facts match no supported runtime. No fallback adapter."""

class BindingRefused(RuntimeError):
    """The declared external bind is absent, internal, managed or mismatched."""


# ── facts ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HostFacts:
    system: str
    arch: str
    container_markers: Tuple[str, ...] = ()
    evidence: Tuple[str, ...] = ()

    @property
    def is_container(self) -> bool:
        return bool(self.container_markers)

def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""

def detect_host(*, platform_name: Optional[str] = None,
                machine: Optional[str] = None,
                docker_env: Optional[bool] = None,
                cgroup_text: Optional[str] = None,
                evidence: Sequence[str] = ()) -> HostFacts:
    """Observe host facts. Every default is a real read, never a constant."""
    system = (platform_name if platform_name is not None else platform.system())
    system = system.strip().lower()
    arch = (machine if machine is not None else platform.machine()).strip().lower()

    has_env = os.path.exists("/.dockerenv") if docker_env is None else docker_env
    cgroup = _read_text("/proc/1/cgroup") if cgroup_text is None else cgroup_text

    markers = []
    if has_env:
        markers.append("dockerenv")
    for token in ("docker", "kubepods", "containerd", "lxc", "podman"):
        if token in cgroup:
            markers.append("cgroup:" + token)
            break

    observed = ("platform:" + (system or "unknown"), "arch:" + (arch or "unknown"))
    observed += tuple(evidence)
    if has_env:
        observed += ("dockerenv:present",)
    if markers:
        observed += ("container:" + markers[-1],)
    return HostFacts(system=system, arch=arch,
                     container_markers=tuple(markers), evidence=observed)

def classify_runtime(facts: HostFacts) -> str:
    """Map observed facts to one supported runtime or refuse by name."""
    if facts.system == "darwin":
        return RUNTIME_MAC
    if facts.system == "linux":
        return RUNTIME_DOCKER if facts.is_container else RUNTIME_VPS
    raise UnsupportedHost(
        "unsupported_host: system=%r arch=%r evidence=%s; supported runtimes "
        "are %s; this adapter does not fall back to one of them"
        % (facts.system, facts.arch, ",".join(facts.evidence),
           ", ".join(SUPPORTED_RUNTIMES)))


# ── mount info (Docker) ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class MountEntry:
    mount_point: str
    fstype: str
    source: str

_ESCAPE = re.compile(r"\\([0-7]{3})")

def _unescape(value: str) -> str:
    return _ESCAPE.sub(lambda m: chr(int(m.group(1), 8)), value)

def parse_mountinfo(text: str) -> Tuple[MountEntry, ...]:
    """Parse /proc/self/mountinfo. Unknown-shaped lines are skipped, not guessed."""
    entries = []
    for line in text.splitlines():
        if " - " not in line:
            continue
        left, right = line.split(" - ", 1)
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 5 or len(right_fields) < 2:
            continue
        entries.append(MountEntry(mount_point=_unescape(left_fields[4]),
                                  fstype=right_fields[0],
                                  source=_unescape(right_fields[1])))
    return tuple(entries)

def _longest_mount_for(root: str, entries: Sequence[MountEntry]) -> Optional[MountEntry]:
    target = os.path.realpath(root)
    best: Optional[MountEntry] = None
    for entry in entries:
        point = os.path.realpath(entry.mount_point)
        if target == point or target.startswith(point.rstrip(os.sep) + os.sep):
            if best is None or len(point) > len(os.path.realpath(best.mount_point)):
                best = entry
    return best


# ── capabilities and persistence ────────────────────────────────────────────

@dataclass(frozen=True)
class Capabilities:
    browser: str
    browser_evidence: str
    requires_browser: bool = False

def browser_capability(probe: Optional[Any] = None) -> Capabilities:
    """Report browser availability honestly; never require one.

    With no probe the status is `not_assumed`, because presence is not observed.
    A probe returning truthy reports `available`, falsy `absent`, and a raising
    probe `probe_failed` with the exception type recorded.
    """
    if probe is None:
        return Capabilities(BROWSER_NOT_ASSUMED,
                            "no browser probe supplied; automation never "
                            "assumes or requires a browser", False)
    try:
        result = probe()
    except Exception as exc:
        return Capabilities(BROWSER_PROBE_FAILED,
                            "probe raised %s: %s" % (type(exc).__name__, exc),
                            False)
    if result and isinstance(result, Mapping) and "path" in result:
        return Capabilities(BROWSER_AVAILABLE,
                            "probe observed %r" % (result.get("path"),), False)
    if result:
        return Capabilities(BROWSER_AVAILABLE, "probe returned %r" % (result,), False)
    return Capabilities(BROWSER_ABSENT, "probe returned a falsy result", False)


@dataclass(frozen=True)
class PersistencePlan:
    """A declared restart-persistence mechanism plus its exact read-back."""

    kind: str
    identity: str
    declared: str
    readback_command: Tuple[str, ...]
    verified: bool = False
    reason: str = "not_read_back"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "identity": self.identity,
            "declared": self.declared,
            "readback_command": list(self.readback_command),
            "verified": self.verified,
            "reason": self.reason,
        }

def verify_persistence(plan: PersistencePlan, readback: Optional[Any]) -> PersistencePlan:
    """Promote the plan to verified ONLY from a real registration read-back.

    A documented primitive is not evidence. No read-back, a read-back that does
    not name this identity, or a non-persistent state all leave it unverified.
    """
    if readback is None:
        return replace(plan, verified=False, reason="no_readback")
    if isinstance(readback, MappingABC):
        identity = readback.get("identity")
        observed = readback.get("observed")
        if identity != plan.identity:
            return replace(plan, verified=False, reason="identity_mismatch")
        text = "" if observed is None else str(observed)
    else:
        text = str(readback)
        if plan.identity.lower() not in text.lower():
            return replace(plan, verified=False, reason="identity_mismatch")
    lowered = text.lower()
    tokens = TERMINAL_STATES.get(plan.kind, ())
    if tokens and not any(token in lowered for token in tokens):
        return replace(plan, verified=False, reason="state_not_persistent")
    if not text.strip():
        return replace(plan, verified=False, reason="empty_readback")
    return replace(plan, verified=True, reason="read_back")


# ── adapters ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BindIdentity:
    """What the operator declared as the approved external destination root."""

    root: str
    source: Optional[str] = None      # explicit host bind source (VPS/Docker)
    media_uuid: Optional[str] = None
    dedicated: bool = False            # operator-declared dedicated volume (VPS)

class _BaseAdapter:
    runtime = ""

    def __init__(self, facts: HostFacts, bind: BindIdentity, *,
                 mount_entries: Optional[Sequence[MountEntry]] = None,
                 uuid_probe: Optional[Any] = None,
                 browser_probe: Optional[Any] = None) -> None:
        self.facts = facts
        self.bind = bind
        self._mount_entries = mount_entries
        self._uuid_probe = uuid_probe
        self._browser_probe = browser_probe

    # -- bind ---------------------------------------------------------------
    def verify_bind(self) -> MountIdentity:
        raise NotImplementedError

    def _mount(self, *, require_mount: bool) -> MountIdentity:
        return verify_mount(self.bind.root,
                            expected_uuid=self.bind.media_uuid,
                            uuid_probe=self._uuid_probe,
                            require_mount=require_mount)

    def _reject_internal_root(self, identity: MountIdentity) -> None:
        try:
            assert_external(os.path.join(identity.path, "probe"),
                            identity.path)
        except PathRejected as exc:
            raise BindingRefused(str(exc)) from None

    # -- runtime surface ----------------------------------------------------
    def destinations(self, run_id: str, *, create: bool = False,
                     required_bytes: int = 0) -> Dict[str, Destination]:
        self.verify_bind()
        return resolve_destinations(self.bind.root, run_id, create=create,
                                    required_bytes=required_bytes,
                                    expected_uuid=self.bind.media_uuid,
                                    uuid_probe=self._uuid_probe)

    def process_env(self, run_id: str, *, create: bool = False) -> Dict[str, str]:
        destinations = self.destinations(run_id, create=create)
        return temp_env(destinations["temp"].path)

    def child_probe(self, run_id: str, **kwargs: Any) -> ChildProbe:
        destinations = self.destinations(run_id)
        return probe_child(destinations["temp"].path, **kwargs)

    def open_ledger(self, run_id: str,
                    *, create: bool = False):
        """Open the retained ledger destination with the no-follow handle."""
        destinations = self.destinations(run_id, create=create)
        return open_destination(destinations["ledger"].path,
                                expected=destinations["ledger"])

    def tool_options(self, tool: str, run_id: str) -> Dict[str, Any]:
        destinations = self.destinations(run_id)
        return tool_output_options(tool, destinations, root=self.bind.root)

    def capabilities(self) -> Capabilities:
        return browser_capability(self._browser_probe)

    def persistence_plan(self) -> PersistencePlan:
        raise NotImplementedError

    def receipt(self, run_id: str) -> Dict[str, Any]:
        identity = self.verify_bind()
        return {
            "runtime": self.runtime,
            "host": {
                "system": self.facts.system,
                "arch": self.facts.arch,
                "container_markers": list(self.facts.container_markers),
                "evidence": list(self.facts.evidence),
            },
            "bind": {
                "root": identity.path,
                "device": identity.device,
                "media_uuid": identity.media_uuid,
                "source": self.bind.source,
                "limitations": list(identity.limitations),
            },
            "capabilities": {
                "browser": self.capabilities().browser,
                "browser_evidence": self.capabilities().browser_evidence,
                "requires_browser": self.capabilities().requires_browser,
            },
            "persistence": self.persistence_plan().as_dict(),
            "run_id": run_id,
        }

class MacAdapter(_BaseAdapter):
    """macOS client/operator host: an external mounted volume, launchd restart."""

    runtime = RUNTIME_MAC

    def verify_bind(self) -> MountIdentity:
        identity = self._mount(require_mount=True)
        root_device = os.stat(os.sep).st_dev
        if identity.device == root_device:
            raise BindingRefused(
                "internal_disk_binding: %s is on the root disk (device %d); "
                "the project root must be an external mounted volume"
                % (identity.path, identity.device))
        self._reject_internal_root(identity)
        return identity

    def persistence_plan(self, unit: str = "runtime") -> PersistencePlan:
        label = "com.blackceo.purple-billboard." + unit
        return PersistencePlan(
            kind="launchd",
            identity=label,
            declared="a launchd job registered by the approved host installer; "
                     "this adapter does not register it",
            readback_command=("launchctl", "print",
                              "gui/%d/%s" % (os.getuid(), label)),
        )

class VpsAdapter(_BaseAdapter):
    """Linux VPS: an explicitly approved bind, systemd restart."""

    runtime = RUNTIME_VPS

    def verify_bind(self) -> MountIdentity:
        if not self.bind.source:
            raise BindingRefused(
                "vps_bind_identity_required: the Mac path is not assumed to "
                "exist on a remote host; declare the approved mount or volume")
        identity = self._mount(require_mount=True)
        if os.path.realpath(self.bind.source) != os.path.realpath(identity.path):
            raise BindingRefused(
                "vps_bind_identity_mismatch: declared %r, root resolves to %r"
                % (self.bind.source, identity.path))
        if identity.device == os.stat(os.sep).st_dev and not self.bind.dedicated:
            raise BindingRefused(
                "vps_rootfs_binding: %s is on the root filesystem (device %d); "
                "declare dedicated=True for an approved dedicated volume"
                % (identity.path, identity.device))
        self._reject_internal_root(identity)
        return identity

    def persistence_plan(self, unit: str = "runtime") -> PersistencePlan:
        name = "purple-billboard-%s.service" % unit
        return PersistencePlan(
            kind="systemd",
            identity=name,
            declared="a systemd unit registered by the approved host installer; "
                     "this adapter does not register it",
            readback_command=("systemctl", "show",
                              "--property=ActiveState,UnitFileState", name),
        )

class DockerAdapter(_BaseAdapter):
    """Container: a host bind proven by mount info, host-set restart policy."""

    runtime = RUNTIME_DOCKER

    def _entries(self) -> Tuple[MountEntry, ...]:
        if self._mount_entries is not None:
            return tuple(self._mount_entries)
        return parse_mountinfo(_read_text("/proc/self/mountinfo"))

    def verify_bind(self) -> MountIdentity:
        if not self.bind.source:
            raise BindingRefused(
                "docker_bind_identity_required: the Mac path is not assumed "
                "inside a container; declare the approved host bind source")
        entries = self._entries()
        if not entries:
            raise BindingRefused(
                "docker_mountinfo_unavailable: no mount info was readable; "
                "the bind cannot be proven and is not assumed")
        entry = _longest_mount_for(self.bind.root, entries)
        if entry is None:
            raise BindingRefused(
                "docker_bind_not_mounted: %s is not covered by any mount entry"
                % self.bind.root)
        if entry.fstype.lower() in MANAGED_FSTYPES:
            raise BindingRefused(
                "docker_managed_filesystem: %s is on %s, an image layer or "
                "ephemeral filesystem, not a verified bind"
                % (self.bind.root, entry.fstype))
        source_real = os.path.realpath(entry.source)
        if _is_managed_volume(entry.source):
            raise BindingRefused(
                "docker_managed_volume_not_supported: %s is a Docker-managed "
                "volume; only a host bind is admissible"
                % entry.source)
        if source_real != os.path.realpath(self.bind.source):
            raise BindingRefused(
                "docker_bind_identity_mismatch: mount source %r, declared %r"
                % (entry.source, self.bind.source))
        identity = self._mount(require_mount=False)
        self._reject_internal_root(identity)
        return identity

    def persistence_plan(self, unit: str = "runtime") -> PersistencePlan:
        return PersistencePlan(
            kind="container_restart_policy",
            identity=unit,
            declared="a container restart policy set by the host operator; a "
                     "process inside the container cannot set or prove it",
            readback_command=("docker", "inspect", "--format",
                              "{{.HostConfig.RestartPolicy.Name}}", unit),
        )


def adapter_for(facts: HostFacts, bind: BindIdentity, *,
                mount_entries: Optional[Sequence[MountEntry]] = None,
                uuid_probe: Optional[Any] = None,
                browser_probe: Optional[Any] = None) -> _BaseAdapter:
    """Return the adapter for observed facts. Never guesses across runtimes."""
    runtime = classify_runtime(facts)
    cls = {RUNTIME_MAC: MacAdapter, RUNTIME_VPS: VpsAdapter,
           RUNTIME_DOCKER: DockerAdapter}[runtime]
    return cls(facts, bind, mount_entries=mount_entries, uuid_probe=uuid_probe,
               browser_probe=browser_probe)


# ── assert-based self-check (stdlib only) ───────────────────────────────────

def _selfcheck() -> None:
    facts = detect_host()
    assert facts.system, "no system fact observed"
    runtime = classify_runtime(facts)
    assert runtime in SUPPORTED_RUNTIMES, runtime
    caps = browser_capability()
    assert caps.browser == BROWSER_NOT_ASSUMED and not caps.requires_browser
    plan = MacAdapter(facts, BindIdentity(root=os.sep)).persistence_plan()
    assert verify_persistence(plan, None).verified is False
    assert verify_persistence(plan, "state = running " + plan.identity).verified
    assert verify_persistence(plan, "state = running other.label").verified is False
    entries = parse_mountinfo(
        "36 35 98:0 /host/data /host/data rw,relatime - ext4 /dev/sdb1 rw")
    assert entries and entries[0].fstype == "ext4", entries
    print("host.py self-check OK: %s/%s" % (facts.system, runtime))


if __name__ == "__main__":
    _selfcheck()
