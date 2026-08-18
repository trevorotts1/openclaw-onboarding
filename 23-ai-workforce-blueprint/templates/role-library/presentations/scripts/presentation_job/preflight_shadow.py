#!/usr/bin/env python3
"""
preflight_shadow.py — TRUST BOUNDARY, SURFACE A: the admission validator
(report-only, Phase 1). Companion to presentation_job/runfacts.py, which this
module reuses without modification — see CONTROL/TRUST-BOUNDARY-BUILD-SPEC.md
§7.2 for the design this file implements.

OWNERSHIP (three-way split of the trust-boundary build): this file, and its
test (test_preflight_shadow.py), are the "core" builder's surface — the
RunFacts admission and the generic seal-vs-read validator. This file does
NOT edit build_deck.py, phase_verifiers.py, or verifier_registry.py, and
imports build_deck.py only lazily/defensively (see _import_build_deck below,
copied in spirit from presentation_job.runfacts._import_build_deck) purely to
read PREFLIGHT_REQUIRED's shape for the CLI helper at the bottom of this
file — never to call or edit a gate body. Wiring this module's two public
functions into build_deck.py's run_preflight() loop (build_deck.py:9795,
PREFLIGHT_REQUIRED at :9095-9623) is a SEPARATE builder's change (one import
line + one changed line inside the loop, per the spec's minimum-diff plan);
that wiring is out of scope here by design, not by oversight.

THE PROBLEM THIS ADDS TO WHAT RunFacts ALREADY COVERS: RunFacts (seal()) is a
one-time, front-door snapshot of a SMALL number of NAMED facts
(process_manifest.json, the six QC reports, the deliverables bundle, ...).
Surface A (PREFLIGHT_REQUIRED / run_preflight()) reads roughly 30 OTHER
artifact types RunFacts does not model (intake.json, arc_allocation.json,
research_map.json, the typography brief, ...) — see the spec's §4 gap list.
Modeling every one of those as a domain-specific RunFacts Fact is real,
valuable, future work (Phase 2, one gate at a time, per §8's Stage 1), but it
is not required to close the SPECIFIC gap this module closes: a run-dir file
that changes CONTENT between the moment a run is admitted and the moment a
specific gate actually reads it never gets checked by anything today — each
of the 60 PREFLIGHT_REQUIRED gates reads its own artifact fresh, with zero
memory of what that artifact looked like earlier in the SAME run_preflight()
call, and zero memory of what it looked like when the run started. This
module gives every one of those 60 gates that memory, generically (no gate
body touched, no per-gate semantic knowledge required):

    admit(run_dir)               — call ONCE, before the loop. Seals
                                    RunFacts (reused as-is) AND snapshots the
                                    admission-time sha256/size/mtime of every
                                    regular file currently under run_dir
                                    (bounded — see DEFAULT_MAX_FILE_BYTES /
                                    DEFAULT_MAX_FILES).

    shadow_check(check_fn, *call_args, rel, label, run_dir, manifest)
                                  — drop-in replacement for
                                    `reason = check(found)` / `reason =
                                    check(run_dir, slides_path)` inside the
                                    PREFLIGHT_REQUIRED loop. ALWAYS calls
                                    check_fn(*call_args) and returns EXACTLY
                                    that value — see "REPORT-ONLY GUARANTEE"
                                    below. In a try/except that can never
                                    propagate, compares the resolved path's
                                    current content against the admission-time
                                    snapshot and records ONE line to the
                                    shadow ledger (working/checkpoints/
                                    preflight-shadow.jsonl) naming the gate,
                                    the resolved path, the legacy result, and
                                    whether admission integrity held.

REPORT-ONLY GUARANTEE (stronger than the other three shadow wrappers already
in this repo, deliberately): _shadow_qc_verifier / _registry_gate_verifier /
_shadow_composite_verifier (phase_verifiers.py) all read
presentation_job.runfacts.enforcing() and CAN return a stricter result when
PRES_TRUST_BOUNDARY_ENFORCE=1. This module reads that flag NOWHERE. There is
no code path in shadow_check() that can return anything other than
check_fn(*call_args)'s own value, under any environment variable, in this
pass — matching the spec's own §7.2/§7.4 recommendation for this specific,
newly-touched surface ("Never blocks. No enforcing() branch at all in Phase
1 for this surface"). Promoting surface A to an enforcing branch is
explicitly named in the spec as later, separate, per-gate work (§8 Stage 1)
gated on first fixing the sealed-mode gap in runfacts.enforcing() (§7.4) —
neither of those preconditions exists yet, so this module does not pretend
to have them.

HONEST LIMIT (same one runfacts.py names, inherited unchanged): this is
tamper-EVIDENCE, not a tamper-proof boundary. admit() and shadow_check() run
as the same UID as whatever wrote the files they read. A same-UID adversary
that tampers BEFORE admit() ever runs is sealed as fact, faithfully, exactly
like RunFacts' own seal(). What this closes is narrower and real: tampering
that happens INSIDE a single run_preflight() call, between admission and a
specific gate's read — a window every existing gate is blind to today
because none of them remember what they saw a moment ago.

ZERO third-party deps (stdlib only), matching the rest of this package.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from presentation_job import runfacts as _rf

RUNFACTS_SCHEMA_VERSION = 1  # mirrors runfacts.py; bump together if the shape changes
SHADOW_LEDGER_REL = Path("working") / "checkpoints" / "preflight-shadow.jsonl"
ADMISSION_PREFIX = "TRUST-BOUNDARY-ADMISSION"
ERROR_PREFIX = "TRUST-BOUNDARY-ADMISSION-SHADOW-ERROR"

# Admission-time file walk is bounded so a pathological run_dir (huge media
# already present, e.g. a re-entrant preflight on a run that got as far as
# rendering before being re-checked) can never make admit() slow or
# unbounded-memory. A file over the cap, or a walk that hits the file-count
# cap, degrades to "no baseline available" for the paths it couldn't reach —
# reported honestly (divergence_kind="no_baseline_available"), never presented
# as "unchanged".
DEFAULT_MAX_FILE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_FILES = 5000

# divergence_kind values that represent a real, actionable admission-integrity
# finding — i.e. what shadow_check() would have refused, had this pass been
# enforcing (it never is — see module docstring). Every other divergence_kind
# is either "nothing to compare" (run_dir_scoped) or "my own tooling
# degraded, not a fact about the run" (no_baseline_available,
# check_time_hash_unavailable) and must NEVER be reported as a would-have-
# blocked finding — that distinction is the whole point of naming this
# explicitly instead of treating "not unchanged" as "suspicious".
_WOULD_HAVE_BLOCKED_KINDS = frozenset({
    "content_changed_since_admission",
    "path_vanished_since_admission",
    "path_appeared_since_admission",
})


def _trunc(s: str, n: int = 300) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 3] + "..."


# ---------------------------------------------------------------------------
# Admission-time snapshot primitives.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PathSnapshot:
    rel: str                        # posix-relative to run_dir, the lookup key
    sha256: Optional[str]           # None iff skipped_reason is set
    size: Optional[int]
    mtime_ns: Optional[int]
    skipped_reason: str = ""        # "" iff sha256 is KNOWN

    def to_json(self) -> dict:
        d: Dict[str, Any] = {"rel": self.rel}
        if self.skipped_reason:
            d["skipped_reason"] = self.skipped_reason
        else:
            d["sha256"] = self.sha256
            d["size"] = self.size
            d["mtime_ns"] = self.mtime_ns
        return d


@dataclass(frozen=True)
class AdmissionManifest:
    run_dir: str
    admitted_at: str
    epoch: float                    # time.monotonic(), for ledger correlation only
    facts: Optional["_rf.RunFacts"]  # None iff runfacts.get_or_seal() itself raised
    paths: Dict[str, PathSnapshot]
    truncated: bool                 # True iff the walk hit DEFAULT_MAX_FILES
    file_count: int
    max_file_bytes: int


def _relkey(run_dir: Path, p: Path) -> str:
    """Normalize p to a posix path relative to run_dir. Falls back to str(p) if
    p is not actually under run_dir (should not happen for paths this module
    resolves itself, but a caller-supplied `found` could in principle point
    anywhere — never raise over it).

    Deliberately resolves p's PARENT directory only, then reattaches p.name
    literally — NOT Path.resolve() on the full path. Path.resolve() follows
    a symlink all the way to its target, which would silently alias a
    symlink's key onto the key of the real file it points at (two different
    filesystem objects reported as the same admission-time fact — exactly
    the kind of collision this module exists to catch, not commit). Resolving
    only the parent still normalizes an ancestor symlink (e.g. macOS
    /var -> /private/var for tempfile.mkdtemp() output), which is required
    for run_dir and a caller's `found` to key-match consistently."""
    try:
        leaf_abs = p.parent.resolve() / p.name
        return leaf_abs.relative_to(run_dir.resolve()).as_posix()
    except Exception:  # noqa: BLE001
        return str(p)


def _hash_file(p: Path, max_bytes: int) -> Tuple[Optional[str], Optional[int], Optional[int], str]:
    """Returns (sha256_hex_or_None, size_or_None, mtime_ns_or_None, skipped_reason).
    Never raises — every failure mode degrades to a skipped_reason string."""
    try:
        st = p.stat()
    except OSError as exc:
        return None, None, None, f"stat failed: {exc!r}"
    if st.st_size > max_bytes:
        return None, st.st_size, st.st_mtime_ns, (
            f"skipped: {st.st_size}b exceeds the {max_bytes}b admission-hash cap"
        )
    try:
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError as exc:
        return None, st.st_size, st.st_mtime_ns, f"read failed: {exc!r}"
    return h.hexdigest(), st.st_size, st.st_mtime_ns, ""


def _snapshot_tree(run_dir: Path, max_file_bytes: int, max_files: int) -> Tuple[Dict[str, PathSnapshot], bool]:
    """Walk run_dir once, hashing every regular file (bounded). Symlinks are
    recorded but never followed (TOCTOU/escape risk — matches the symlink
    rejection convention build_deck.run_postflight_gate's DELIVERABLES_REQUIRED
    loop already applies, per the spec's §7.3 cross-reference) and are never
    treated as a usable admission baseline (skipped_reason set, sha256 None).
    Never raises: any per-entry failure degrades that one entry, never aborts
    the walk."""
    paths: Dict[str, PathSnapshot] = {}
    truncated = False
    count = 0
    try:
        for dirpath, dirnames, filenames in os.walk(run_dir, followlinks=False):
            dirnames[:] = sorted(
                d for d in dirnames if not (Path(dirpath, d).is_symlink())
            )
            for fname in sorted(filenames):
                fp = Path(dirpath) / fname
                if fp.is_symlink():
                    relkey = _relkey(run_dir, fp)
                    paths[relkey] = PathSnapshot(
                        relkey, None, None, None,
                        "skipped: symlink (not followed at admission time)"
                    )
                    continue
                if count >= max_files:
                    truncated = True
                    break
                relkey = _relkey(run_dir, fp)
                sha, size, mtime_ns, skip = _hash_file(fp, max_file_bytes)
                paths[relkey] = PathSnapshot(relkey, sha, size, mtime_ns, skip)
                count += 1
            if truncated:
                break
    except OSError as exc:  # noqa: BLE001 — e.g. run_dir vanished mid-walk
        try:
            print(f"{ERROR_PREFIX} snapshot walk of {run_dir} aborted: {exc!r}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
        truncated = True
    return paths, truncated


_ADMIT_LOCK = threading.Lock()
_ADMIT_CACHE: Dict[str, AdmissionManifest] = {}


def admit(run_dir, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
          max_files: int = DEFAULT_MAX_FILES, force: bool = False) -> AdmissionManifest:
    """Build (or return the cached) AdmissionManifest for run_dir. Call ONCE per
    run_preflight() invocation, before PREFLIGHT_REQUIRED's loop starts —
    caching by resolved run_dir path means a second call in the same process
    (e.g. a test re-entering the same run_dir) is free unless force=True.
    NEVER raises: get_or_seal() failure and snapshot-walk failure both degrade
    to a partial/empty manifest, logged loudly, never an exception — sealing
    can never itself block a run (this module is report-only end to end)."""
    run_dir = Path(run_dir).resolve()
    key = str(run_dir)
    with _ADMIT_LOCK:
        if not force and key in _ADMIT_CACHE:
            return _ADMIT_CACHE[key]

    facts = None
    try:
        facts = _rf.get_or_seal(run_dir)
    except Exception as exc:  # noqa: BLE001
        try:
            print(f"{ERROR_PREFIX} get_or_seal({run_dir}) raised: {exc!r} — "
                  f"admission manifest will carry facts=None", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass

    paths, truncated = _snapshot_tree(run_dir, max_file_bytes, max_files)

    manifest = AdmissionManifest(
        run_dir=key,
        admitted_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        epoch=time.monotonic(),
        facts=facts,
        paths=paths,
        truncated=truncated,
        file_count=len(paths),
        max_file_bytes=max_file_bytes,
    )
    with _ADMIT_LOCK:
        _ADMIT_CACHE[key] = manifest
    return manifest


def reset_cache_for_tests() -> None:
    """Test-only: clear the per-process admission cache so a test can admit the
    same run_dir path twice with different fixture content. Not called by any
    production code path (mirrors runfacts.reset_cache_for_tests)."""
    with _ADMIT_LOCK:
        _ADMIT_CACHE.clear()


# ---------------------------------------------------------------------------
# Shadow ledger.
# ---------------------------------------------------------------------------
def _append_ledger(run_dir: Path, record: dict) -> None:
    out_path = Path(run_dir) / SHADOW_LEDGER_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(str(out_path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def _glob_baseline_match(manifest: AdmissionManifest, pattern: str) -> Optional[PathSnapshot]:
    """For a glob-style `rel` (contains '*') resolved to found=None at check
    time: did ANY file matching this pattern exist (with a known hash) at
    admission time? Pure fnmatch against the admission snapshot's keys — no
    knowledge of what the gate means, matching the rest of this module."""
    for key, snap in manifest.paths.items():
        if snap.skipped_reason:
            continue
        if fnmatch.fnmatch(key, pattern):
            return snap
    return None


def _classify(run_dir: Path, rel: Optional[str], found: Optional[Path],
              manifest: Optional[AdmissionManifest]) -> Tuple[str, str, dict]:
    """Return (divergence_kind, detail, extra_ledger_fields). Never raises —
    any internal failure is caught by the caller (shadow_check) and reported
    as ERROR_PREFIX, never allowed to affect the legacy return value."""
    if rel is None:
        return ("run_dir_scoped", "run-dir-scoped check — no single admitted "
                "path to compare against", {})

    if manifest is None:
        return ("no_baseline_available",
                "admit() was never called for this run_dir before this gate "
                "ran — the admission validator has no baseline to compare "
                "against (this is a wiring gap, not a fact about the run)", {})

    if found is not None:
        relkey = _relkey(run_dir, found)
        baseline = manifest.paths.get(relkey)
        if baseline is None:
            if manifest.truncated:
                return ("no_baseline_available",
                        f"{relkey}: the admission-time snapshot of run_dir was "
                        f"truncated (>{DEFAULT_MAX_FILES} files) before reaching "
                        f"this path — admission state for it is unknown, not "
                        f"asserted clean", {"resolved_relkey": relkey})
            return ("path_appeared_since_admission",
                    f"{relkey}: ABSENT from the admission-time snapshot of "
                    f"run_dir, but present now — this file materialized "
                    f"during run_preflight(), after admission", {"resolved_relkey": relkey})
        if baseline.skipped_reason:
            return ("no_baseline_available",
                    f"{relkey}: admission-time hash unavailable "
                    f"({baseline.skipped_reason}) — admission state for it is "
                    f"unknown, not asserted clean", {"resolved_relkey": relkey})
        cur_sha, cur_size, cur_mtime, cur_skip = _hash_file(found, manifest.max_file_bytes)
        extra = {
            "resolved_relkey": relkey,
            "admission_sha256": baseline.sha256,
            "admission_size": baseline.size,
            "admission_mtime_ns": baseline.mtime_ns,
        }
        if cur_skip:
            extra.update(check_sha256=None, check_size=cur_size, check_mtime_ns=cur_mtime)
            return ("check_time_hash_unavailable",
                    f"{relkey}: check-time hash unavailable ({cur_skip}) — "
                    f"cannot assert admission integrity either way", extra)
        extra.update(check_sha256=cur_sha, check_size=cur_size, check_mtime_ns=cur_mtime)
        if cur_sha != baseline.sha256:
            return ("content_changed_since_admission",
                    f"{relkey}: sha256 at admission={baseline.sha256[:16]}... "
                    f"(size={baseline.size}b, mtime_ns={baseline.mtime_ns}) vs "
                    f"sha256 at check={cur_sha[:16]}... (size={cur_size}b, "
                    f"mtime_ns={cur_mtime}) — content changed inside this "
                    f"run_preflight() call, between admission (admit()) and "
                    f"this gate's read", extra)
        return ("unchanged", f"{relkey}: sha256 matches the admission-time "
                f"snapshot — no change detected between admission and this "
                f"gate's read", extra)

    # found is None: the artifact does not exist right now, at check time.
    if "*" in rel:
        matched = _glob_baseline_match(manifest, rel)
        if matched is not None:
            return ("path_vanished_since_admission",
                    f"pattern {rel!r} matched {matched.rel!r} at admission time "
                    f"(sha256={matched.sha256[:16]}..., size={matched.size}b) "
                    f"but no file matching it exists now", {
                        "resolved_relkey": matched.rel,
                        "admission_sha256": matched.sha256,
                        "admission_size": matched.size,
                        "admission_mtime_ns": matched.mtime_ns,
                    })
        return ("no_baseline_available",
                f"pattern {rel!r}: no match at admission time or now — "
                f"ordinary absence, not a finding", {})

    norm = rel.lstrip("./")
    baseline = manifest.paths.get(norm)
    if baseline is not None and not baseline.skipped_reason:
        return ("path_vanished_since_admission",
                f"{norm}: present at admission (sha256={baseline.sha256[:16]}..., "
                f"size={baseline.size}b) but absent now", {
                    "resolved_relkey": norm,
                    "admission_sha256": baseline.sha256,
                    "admission_size": baseline.size,
                    "admission_mtime_ns": baseline.mtime_ns,
                })
    return ("no_baseline_available",
            f"{norm}: no usable admission-time record — ordinary absence, "
            f"not a finding", {})


def _record_admission_check(check_fn, call_args: tuple, rel: Optional[str],
                             label: str, run_dir: Path,
                             manifest: Optional[AdmissionManifest],
                             legacy_reason: Optional[str]) -> dict:
    """Build the ledger record, append it, and loudly print a stderr line for
    any would-have-blocked or degraded finding. Returns the record (mainly so
    callers/tests can inspect it without re-reading the ledger file)."""
    run_dir = Path(run_dir)
    found = call_args[0] if call_args else None
    found = found if isinstance(found, Path) else None
    legacy_ok = not legacy_reason

    divergence_kind, detail, extra = _classify(run_dir, rel, found, manifest)
    would_have_blocked = divergence_kind in _WOULD_HAVE_BLOCKED_KINDS

    record: Dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_dir": str(run_dir),
        "label": label,
        "rel": rel,
        "check_fn": getattr(check_fn, "__name__", repr(check_fn)),
        "resolved": str(found) if found is not None else None,
        "legacy_result": "PASS" if legacy_ok else "FAIL",
        "legacy_reason": _trunc(legacy_reason or ""),
        "divergence_kind": divergence_kind,
        "would_have_blocked": would_have_blocked,
        "detail": _trunc(detail),
        "admission_epoch": manifest.epoch if manifest is not None else None,
    }
    record.update(extra)

    _append_ledger(run_dir, record)

    if would_have_blocked or divergence_kind == "check_time_hash_unavailable":
        try:
            print(
                f"{ADMISSION_PREFIX} label={label!r} rel={rel!r} "
                f"run_dir={run_dir} kind={divergence_kind} "
                f"would_have_blocked={would_have_blocked} "
                f"legacy={record['legacy_result']}({_trunc(legacy_reason or '', 120)!r}) "
                f"detail={_trunc(detail, 200)!r}",
                file=sys.stderr,
            )
        except Exception:  # noqa: BLE001
            pass

    return record


def shadow_check(check_fn, *call_args, rel: Optional[str], label: str,
                  run_dir, manifest: Optional[AdmissionManifest]) -> Optional[str]:
    """Drop-in replacement for the two call shapes PREFLIGHT_REQUIRED's loop
    already uses:

        reason = check(found)                       ->
        reason = shadow_check(check, found, rel=rel, label=label,
                               run_dir=run_dir, manifest=manifest)

        reason = check(run_dir, slides_path)         ->
        reason = shadow_check(check, run_dir, slides_path, rel=None,
                               label=label, run_dir=run_dir, manifest=manifest)

    ALWAYS calls check_fn(*call_args) and returns EXACTLY that value — see the
    module docstring's REPORT-ONLY GUARANTEE. Never raises into the caller:
    any failure in the admission-comparison path is caught, logged via
    ERROR_PREFIX, and does not affect the return value."""
    legacy_reason = check_fn(*call_args)
    try:
        _record_admission_check(check_fn, call_args, rel, label, Path(run_dir),
                                 manifest, legacy_reason)
    except Exception as exc:  # noqa: BLE001 — shadow must never break a gate
        try:
            print(f"{ERROR_PREFIX} label={label!r} rel={rel!r}: {exc!r}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
    return legacy_reason


# ---------------------------------------------------------------------------
# Standalone CLI: `python3 -m presentation_job.preflight_shadow --admit <run_dir>`.
# Inspection only — admits a run_dir and prints the manifest summary. Does not
# call any gate, does not touch build_deck.py's CLI or exit codes (separate
# EXIT_* space, matching runfacts.py's own convention of not colliding with
# either build_deck's or presentation_job/__main__.py's exit codes).
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_USAGE = 1


def _main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2 or argv[0] != "--admit":
        print("usage: python3 -m presentation_job.preflight_shadow --admit <run_dir>",
              file=sys.stderr)
        return EXIT_USAGE
    run_dir = Path(argv[1])
    manifest = admit(run_dir, force=True)
    summary = {
        "run_dir": manifest.run_dir,
        "admitted_at": manifest.admitted_at,
        "file_count": manifest.file_count,
        "truncated": manifest.truncated,
        "runfacts_findings": manifest.facts.findings() if manifest.facts is not None else None,
    }
    print(json.dumps(summary, indent=2))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
