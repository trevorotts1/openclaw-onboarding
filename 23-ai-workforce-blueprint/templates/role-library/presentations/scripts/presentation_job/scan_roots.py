"""Scan-root resolution shared by the watchdog, the board-reconcile sweep, and
run_discovery.

WHY THIS MODULE EXISTS (2026-08-27 incident)
--------------------------------------------
Every pass driven by presentation-watchdog.sh took exactly ONE scan root -- the
department tree, `<workspace>/departments/Presentations/runs`. A real client deck
run built outside that tree was therefore invisible to all three passes at once:
the watchdog scanned, found the two runs that happened to live in the department
tree, reported them, and exited 0. Nothing in the log said which forest had been
searched, so three hours of "watchdog is running fine" was indistinguishable from
three hours of watching the wrong directory.

The fix is two rules, both enforced here:

  1. A root list, never a root. The department tree stays the default; additional
     roots come from configuration (an env var or a config file), never from a
     path hardcoded for one operator's box.

  2. A root that cannot be read is UNDETERMINED, never empty. "I looked and found
     no runs" and "I could not look" are different claims and must never collapse
     into the same output. This mirrors EXIT_SWEEP_NO_RUNS / EXIT_WATCHDOG_NO_RUNS
     in state.py: a scanner that checked nothing must never read as a clean pass.

Nothing here blocks, heals, or fails a deck. Absence of a run inside a scanned
root is not evidence the run does not exist -- it may simply live in a root this
box was never told about, which is precisely the defect above. Callers get the
roots and their statuses; the reporting rule is that an UNDETERMINED root
disqualifies any claim of completeness.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

# Environment variable holding additional roots, os.pathsep-separated (":" on
# POSIX) in the same shape as PATH.
SCAN_ROOTS_ENV = "PRESENTATION_SCAN_ROOTS"
# Environment variable pointing at the config file, when it is not in the
# default location.
SCAN_ROOTS_CONFIG_ENV = "SCAN_ROOTS_CONFIG"
# Default config file, relative to the department root (the parent of scripts/).
DEFAULT_CONFIG_RELPATH = Path("config") / "scan-roots.conf"

ROOT_OK = "ok"
ROOT_UNDETERMINED = "undetermined"

# Identity markers that prove "this directory is a deck run", independent of what
# it is named. The 2026-08-27 incident run was named "2026-08-27" -- a date, not a
# "pres-*" slug -- so any discovery keyed on a naming convention would have missed
# it even pointed at the right root.
#
#   state.json  -- the engine's own state document (StateStore.STATE_FILENAME)
#   working/checkpoints/process_manifest.json -- a pre-engine legacy run
#   .job.lock   -- RunLock's lock file; present from the moment a job starts,
#                  including on a run that died before its first state write
MARKER_STATE = "state.json"
MARKER_LEGACY_MANIFEST = str(Path("working") / "checkpoints" / "process_manifest.json")
MARKER_LOCK = ".job.lock"
RUN_DIR_MARKERS: Tuple[str, ...] = (MARKER_STATE, MARKER_LEGACY_MANIFEST, MARKER_LOCK)


@dataclass(frozen=True)
class ScanRoot:
    """One resolved root plus how it got here and whether it can be read."""

    path: Path
    origin: str          # "primary" | "cli" | "env:<VAR>" | "config:<file>"
    status: str          # ROOT_OK | ROOT_UNDETERMINED
    detail: str = ""     # why it is UNDETERMINED; empty when ok

    @property
    def ok(self) -> bool:
        return self.status == ROOT_OK


def default_config_path(scripts_dir: Path) -> Path:
    """Where scan-roots.conf lives when SCAN_ROOTS_CONFIG is unset.

    scripts_dir is the presentations scripts/ directory; the config sits beside
    it under the department root, so a box can add roots without editing any
    file this repo ships."""
    return Path(scripts_dir).resolve().parent / DEFAULT_CONFIG_RELPATH


def parse_roots_config(path: Path) -> Tuple[List[Path], Optional[str]]:
    """Read a scan-roots config file.

    Format: one absolute path per line; blank lines and #-comments ignored;
    a leading ~ is expanded.

    Returns (paths, error). A config file that does not exist is NOT an error --
    it is an optional file and its absence means "no additional roots configured".
    A config file that exists but cannot be read IS an error, reported so the
    caller can mark the situation UNDETERMINED rather than silently proceeding
    with a short root list."""
    p = Path(path).expanduser()
    if not p.exists():
        return [], None
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        return [], f"unreadable: {exc}"
    paths: List[Path] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            paths.append(Path(line).expanduser())
    return paths, None


def _probe(path: Path) -> Tuple[str, str]:
    """Classify one root as readable or UNDETERMINED. Never raises."""
    try:
        if not path.exists():
            return ROOT_UNDETERMINED, "does not exist"
        if not path.is_dir():
            return ROOT_UNDETERMINED, "not a directory"
        # Existence is not readability -- a directory with no +x/+r for this user
        # raises only when actually walked, which is exactly when the scan would
        # otherwise report a silent zero.
        next(iter(os.scandir(path)), None)
        return ROOT_OK, ""
    except OSError as exc:
        return ROOT_UNDETERMINED, f"unreadable: {exc}"


def resolve_scan_roots(
    primary: Optional[Path] = None,
    extra: Sequence[Path] = (),
    env: Optional[dict] = None,
    config_path: Optional[Path] = None,
) -> List[ScanRoot]:
    """Build the ordered, de-duplicated root list with a status for each.

    Precedence (first occurrence of a path wins, so its origin is the one
    reported): primary root, --scan-root-extra flags, the env var, the config
    file. Order matters only for reporting and for which root owns the findings
    file; every root is scanned either way.

    A root is included in the returned list even when it is UNDETERMINED --
    dropping it would recreate the original defect, where a root nobody could
    read looked exactly like a root nobody configured."""
    env = os.environ if env is None else env
    candidates: List[Tuple[Path, str]] = []

    if primary is not None:
        candidates.append((Path(primary).expanduser(), "primary"))
    for p in extra:
        candidates.append((Path(p).expanduser(), "cli"))

    raw_env = env.get(SCAN_ROOTS_ENV, "")
    for chunk in raw_env.split(os.pathsep):
        chunk = chunk.strip()
        if chunk:
            candidates.append((Path(chunk).expanduser(), f"env:{SCAN_ROOTS_ENV}"))

    cfg = config_path if config_path is not None else env.get(SCAN_ROOTS_CONFIG_ENV)
    config_error: Optional[Tuple[Path, str]] = None
    if cfg:
        cfg = Path(cfg).expanduser()
        cfg_paths, err = parse_roots_config(cfg)
        if err:
            config_error = (cfg, err)
        for p in cfg_paths:
            candidates.append((p, f"config:{cfg}"))

    roots: List[ScanRoot] = []
    seen = set()
    for path, origin in candidates:
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        status, detail = _probe(key)
        roots.append(ScanRoot(path=key, origin=origin, status=status, detail=detail))

    # An unreadable config file is itself an UNDETERMINED input: the roots it
    # named are unknown, so the root list cannot be called complete.
    if config_error is not None:
        cfg_path, err = config_error
        roots.append(ScanRoot(path=cfg_path, origin="config-file",
                              status=ROOT_UNDETERMINED, detail=err))
    return roots


def undetermined_roots(roots: Iterable[ScanRoot]) -> List[ScanRoot]:
    return [r for r in roots if r.status == ROOT_UNDETERMINED]


def ok_roots(roots: Iterable[ScanRoot]) -> List[ScanRoot]:
    return [r for r in roots if r.status == ROOT_OK]


def format_roots_report(roots: Sequence[ScanRoot], label: str) -> str:
    """The per-pass audit line: which forests were actually searched.

    Written to the log on EVERY pass, including clean ones. The 2026-08-27
    blind spot was invisible precisely because a healthy-looking pass never said
    where it had looked -- so a missing root could only be found by reading the
    plist, not the log."""
    n_ok = len(ok_roots(roots))
    n_bad = len(undetermined_roots(roots))
    lines = [f"{label}: scan roots: {n_ok} readable, {n_bad} UNDETERMINED"]
    for r in roots:
        tag = "ok          " if r.ok else "UNDETERMINED"
        suffix = f" -- {r.detail}" if r.detail else ""
        lines.append(f"{label}:   [{tag}] {r.path} ({r.origin}){suffix}")
    if n_bad:
        lines.append(
            f"{label}: {n_bad} root(s) could not be read -- results below are "
            f"INCOMPLETE. A run absent from this scan is UNDETERMINED, not missing."
        )
    return "\n".join(lines)


def matched_markers(path: Path) -> List[str]:
    """Which identity markers this directory carries. Empty means not a run dir."""
    found: List[str] = []
    for marker in RUN_DIR_MARKERS:
        try:
            if (path / marker).is_file():
                found.append(marker)
        except OSError:
            continue
    return found


def is_run_dir(path: Path) -> bool:
    """True when the directory proves itself a deck run by content, not by name."""
    return bool(matched_markers(path))
