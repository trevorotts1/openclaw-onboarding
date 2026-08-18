#!/usr/bin/env python3
"""
gate_read_audit.py — closes the "83% blind spot" in build_deck.py's
PREFLIGHT_REQUIRED shadow snapshot.

THE PROBLEM THIS CLOSES: PREFLIGHT_REQUIRED (build_deck.py) is a list of
(rel, label, phase, check) tuples. `rel` is the ONE static file path a gate's
tuple declares it cares about. 50 of PREFLIGHT_REQUIRED's 60 entries carry
rel=None — a run-dir-scoped check that needs more than a single named file (or
whose exact file depends on run-time content, e.g. a glob) does not, and
cannot, declare a `rel`. Any snapshot/divergence mechanism keyed off `rel`
therefore has NO FILE to snapshot for those 50 gates and is mathematically
incapable of ever registering a divergence for them, no matter how the
underlying file is tampered with — an 83%-blind detector is not a detector.

THE FIX: stop trusting the DECLARED `rel` and instead OBSERVE what a gate
call ACTUALLY reads. `sys.addaudithook` fires a process-wide 'open' event for
every `open()` / `Path.open()` / `Path.read_text()` (io.open under the hood)
call in the process, CPython-guaranteed and unremovable once installed — which
is exactly the property this needs: a check() function cannot open a file
under run_dir without this module seeing it, regardless of whether its
PREFLIGHT_REQUIRED tuple named that file. trace_reads() scopes recording to a
single call via a contextvars.ContextVar (thread-safe, no global mutable
state), and every observed path is filtered to those under run_dir so imports
(build_deck.py's own bytecode, stdlib, site-packages) never pollute the
recorded read set.

REPORT-ONLY, matching the rest of the Trust Boundary work: seal_gate_reads()
is called ALONGSIDE the existing PREFLIGHT_REQUIRED loop in run_preflight(),
never in place of it — it cannot change what any gate returns and a failure
inside this module can never block or alter preflight. verify_gate_reads()
is a separate, later re-observation that diffs fresh hashes against the
sealed baseline and reports (never blocks) any content drift on a path a gate
is PROVEN — empirically, not declaratively — to read.

HONEST LIMIT: like runfacts.py's seal(), this seals per-process, per-run_dir,
same-UID. It converts "no snapshot exists for 50 gates" into "a snapshot of
what was empirically read exists for every gate that actually touched a
file" — it does not add a privilege boundary. A gate whose check() function
legitimately reads ZERO files under run_dir (e.g. one that only inspects
environment or in-memory state already passed in) still has nothing to seal;
that is a real, different, and much smaller set than "50 of 60, unconditionally".

ZERO third-party deps (stdlib only), matching the rest of this package.
"""

from __future__ import annotations

import contextvars
import hashlib
import inspect
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

SEALED_REL = Path("working") / "checkpoints" / ".gate-reads.sealed.json"
DIVERGENCE_PREFIX = "GATE-READS-DIVERGENCE"
SEAL_ERROR_PREFIX = "GATE-READ-AUDIT-SEAL-ERROR"

# ---------------------------------------------------------------------------
# The recording primitive. ONE audit hook, installed at most once per
# process (sys.addaudithook hooks cannot be removed — installing more than
# one would just mean more no-op calls on every 'open' in the process, so
# this guards against that rather than for correctness). A contextvars
# ContextVar (not a plain module global) makes recording scope safe under
# concurrent/nested use: only a call actively inside trace_reads() has a
# non-None target, so an 'open' fired by unrelated code in another thread —
# or a nested trace_reads() call is simply not possible here since gates run
# strictly sequentially in run_preflight(), but the primitive is correct
# regardless — never lands in the wrong bucket.
# ---------------------------------------------------------------------------
_RECORDING: "contextvars.ContextVar[Optional[set]]" = contextvars.ContextVar(
    "gate_read_audit_recording", default=None
)
_HOOK_INSTALLED = False


def _audit_hook(event: str, args: tuple) -> None:
    if event != "open":
        return
    target = _RECORDING.get()
    if target is None:
        return
    try:
        path = args[0]
        if path is None:
            return
        target.add(str(path))
    except Exception:  # noqa: BLE001 — an audit hook must never raise
        pass


def _ensure_hook_installed() -> None:
    global _HOOK_INSTALLED
    if _HOOK_INSTALLED:
        return
    sys.addaudithook(_audit_hook)
    _HOOK_INSTALLED = True


def trace_reads(fn: Callable[[], Any]) -> Tuple[Any, FrozenSet[str]]:
    """Call the zero-arg callable fn(), returning (result, frozenset of every
    path the 'open' audit event saw during the call — UNFILTERED, absolute or
    relative exactly as the opener passed it). Never raises due to tracing
    itself; an exception raised BY fn() propagates unchanged (callers that
    need fail-soft behavior wrap the whole trace_reads call, exactly like
    every other shadow call site in this package)."""
    _ensure_hook_installed()
    collected: set = set()
    token = _RECORDING.set(collected)
    try:
        result = fn()
    finally:
        _RECORDING.reset(token)
    return result, frozenset(collected)


def _paths_under(run_dir: Path, raw_paths: FrozenSet[str]) -> List[str]:
    """Filter raw observed paths to those that resolve under run_dir — this is
    what keeps module imports (build_deck.py itself, stdlib, site-packages)
    from polluting the recorded per-gate read set. Returns resolved, sorted,
    de-duplicated absolute path strings."""
    try:
        run_dir_resolved = run_dir.resolve()
    except OSError:
        run_dir_resolved = run_dir
    out = set()
    for raw in raw_paths:
        try:
            p = Path(raw)
            if not p.is_absolute():
                # A relative open() during a gate call is always relative to
                # the process cwd, not run_dir — resolve it the same way the
                # opener's own runtime would have.
                p = Path.cwd() / p
            resolved = p.resolve()
        except (OSError, ValueError):
            continue
        try:
            resolved.relative_to(run_dir_resolved)
        except ValueError:
            continue
        out.add(str(resolved))
    return sorted(out)


def hash_paths(paths: List[str]) -> Dict[str, Optional[str]]:
    """sha256 hex digest per path, or None when the path is no longer
    readable at hash time (deleted / permissions / became a directory) —
    absence of a hash is itself meaningful and is carried through, never
    silently dropped."""
    out: Dict[str, Optional[str]] = {}
    for p in paths:
        try:
            data = Path(p).read_bytes()
            out[p] = hashlib.sha256(data).hexdigest()
        except OSError:
            out[p] = None
    return out


# ---------------------------------------------------------------------------
# PREFLIGHT_REQUIRED dispatch — deliberately duplicated (not imported) from
# build_deck.run_preflight's own gate loop, in miniature: this module must
# never import build_deck (build_deck already imports THIS module from
# run_preflight; importing back would be a cycle) and the call convention is
# tiny and stable (two shapes: run-dir-scoped check(run_dir[, slides_path])
# and rel-scoped check(resolved_path_or_None)). Callers pass PREFLIGHT_REQUIRED
# itself as data, so this module never needs to know where that list lives.
# ---------------------------------------------------------------------------
def _resolve_rel(run_dir: Path, rel: Optional[str]) -> Optional[Path]:
    if rel is None:
        return None
    if "*" in rel:
        matches = sorted(run_dir.glob(rel))
        return matches[0] if matches else None
    p = run_dir / rel
    return p if p.exists() else None


def _call_gate(run_dir: Path, rel: Optional[str], check: Callable,
                slides_path: Optional[Path]) -> Any:
    if rel is None:
        try:
            accepts_slides = "slides_path" in inspect.signature(check).parameters
        except (TypeError, ValueError):
            accepts_slides = False
        return check(run_dir, slides_path) if accepts_slides else check(run_dir)
    found = _resolve_rel(run_dir, rel)
    return check(found)


def _gate_key(label: str) -> str:
    """Stable per-gate key for the sealed record. Deliberately NOT `rel` —
    two DIFFERENT gates can and do share the same declared rel (e.g.
    _chk_research_brief and _chk_research_cited both declare
    "working/research/brief-*.md"; keying on rel silently drops one gate's
    seal record to a dict collision, exactly the kind of blind spot this
    module exists to close). `label` is verified unique across every entry
    in PREFLIGHT_REQUIRED (build_deck.py) and is human-readable in the
    sealed JSON and in divergence lines, so it is the key."""
    return label


def observe_all_gates(run_dir: Path, preflight_required, slides_path: Optional[Path] = None
                       ) -> Dict[str, dict]:
    """Run every (rel, label, phase, check) tuple's check() call EXACTLY as
    run_preflight() does, under trace_reads(), and return {gate_key: record}
    where record carries the declared rel (may be None), the label, whether
    rel was None (i.e. this gate was previously blind to any snapshot), the
    empirically-observed paths under run_dir, and their sha256 hashes.

    A single gate's check() raising is caught and recorded as an 'error'
    field on that gate's record rather than aborting the whole observation —
    one broken/incompatible checker must never blind every other gate's
    audit, mirroring the fail-soft posture of every other shadow call site
    in this package."""
    out: Dict[str, dict] = {}
    for rel, label, phase, check in preflight_required:
        key = _gate_key(label)
        try:
            _result, raw_paths = trace_reads(lambda: _call_gate(run_dir, rel, check, slides_path))
            observed = _paths_under(run_dir, raw_paths)
            out[key] = {
                "declared_rel": rel,
                "label": label,
                "was_blind": rel is None,
                "observed_paths": observed,
                "hashes": hash_paths(observed),
            }
        except Exception as exc:  # noqa: BLE001 — one bad gate must not blind the rest
            out[key] = {
                "declared_rel": rel,
                "label": label,
                "was_blind": rel is None,
                "observed_paths": [],
                "hashes": {},
                "error": repr(exc),
            }
    return out


def seal_gate_reads(run_dir: Path, preflight_required, slides_path: Optional[Path] = None
                     ) -> Optional[Path]:
    """Observe every gate's real read set and write it to
    <run_dir>/working/checkpoints/.gate-reads.sealed.json (0600, atomic,
    best-effort). Returns the path written, or None on any failure — never
    raises (report-only: sealing must never be able to block a run)."""
    try:
        run_dir = Path(run_dir).resolve()
        gates = observe_all_gates(run_dir, preflight_required, slides_path)
        payload = {
            "run_dir": str(run_dir),
            "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "gate_count": len(gates),
            "blind_gate_count": sum(1 for g in gates.values() if g.get("was_blind")),
            "gates": gates,
        }
        out_path = run_dir / SEALED_REL
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_suffix(out_path.suffix + f".tmp{os.getpid()}")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, out_path)
        return out_path
    except Exception:  # noqa: BLE001 — sealing must never raise into a caller
        return None


def load_sealed(run_dir: Path) -> Optional[dict]:
    p = Path(run_dir) / SEALED_REL
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


def verify_gate_reads(run_dir: Path, preflight_required, slides_path: Optional[Path] = None
                       ) -> List[str]:
    """Re-observe every gate's read set NOW and diff it against the sealed
    baseline written by seal_gate_reads(). Returns a list of human-readable
    divergence lines (empty == clean). A path present in BOTH baseline and
    fresh observation whose sha256 differs is reported as tampering with
    exactly what that gate reads — the case that was mathematically
    impossible to catch for any rel=None gate before this module existed.
    Never raises; a missing baseline (never sealed) yields a single
    informational line rather than an exception."""
    baseline = load_sealed(run_dir)
    if baseline is None:
        return [f"{DIVERGENCE_PREFIX}: no sealed baseline at {Path(run_dir) / SEALED_REL} "
                f"— seal_gate_reads() was never called for this run_dir; nothing to verify"]

    fresh = observe_all_gates(Path(run_dir), preflight_required, slides_path)
    lines: List[str] = []
    for key, base_rec in baseline.get("gates", {}).items():
        fresh_rec = fresh.get(key)
        base_hashes = base_rec.get("hashes") or {}
        fresh_hashes = (fresh_rec or {}).get("hashes") or {}
        label = base_rec.get("label", key)
        for path, base_sha in base_hashes.items():
            fresh_sha = fresh_hashes.get(path)
            if path in fresh_hashes and fresh_sha != base_sha:
                lines.append(
                    f"{DIVERGENCE_PREFIX} gate={label!r} run_dir={run_dir} "
                    f"tampered_file={path} baseline_sha256={(base_sha or 'None')[:12]} "
                    f"now_sha256={(fresh_sha or 'None')[:12]} was_blind={base_rec.get('was_blind')}"
                )
    return lines


# ---------------------------------------------------------------------------
# Standalone CLI: `python3 -m presentation_job.gate_read_audit --verify <run_dir>`
# Imports build_deck lazily/defensively (same pattern runfacts.py uses) ONLY
# in the CLI entry point — the library functions above never import it, so
# this module stays importable (and testable) without build_deck present.
# ---------------------------------------------------------------------------
def _main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2 or argv[0] not in ("--verify", "--seal"):
        print("usage: python3 -m presentation_job.gate_read_audit --seal|--verify <run_dir>",
              file=sys.stderr)
        return 2
    mode, run_dir_arg = argv[0], argv[1]
    run_dir = Path(run_dir_arg)

    here = Path(__file__).resolve().parent.parent  # .../scripts
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    import build_deck as _bd  # noqa: PLC0415

    if mode == "--seal":
        out = seal_gate_reads(run_dir, _bd.PREFLIGHT_REQUIRED)
        print(json.dumps({"sealed": str(out) if out else None}, indent=2))
        return 0 if out else 1

    lines = verify_gate_reads(run_dir, _bd.PREFLIGHT_REQUIRED)
    for line in lines:
        print(line, file=sys.stderr)
    print(json.dumps({"divergences": len(lines), "clean": not lines}, indent=2))
    return 1 if lines else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
