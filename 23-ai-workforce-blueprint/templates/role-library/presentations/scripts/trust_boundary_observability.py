#!/usr/bin/env python3
"""
trust_boundary_observability.py — TRUST BOUNDARY, OBSERVABILITY SURFACE ("obs").

SCOPE (read this before touching anything else): this module owns exactly two
things — WHERE a would-have-blocked verdict is RECORDED, and the raw parsing
that recording depends on. Its sibling, trust_boundary_report.py, owns HOW an
operator READS what got recorded. Neither file defines what a gate is, how a
gate decides, or when a gate is allowed to actually block a run — that is
presentation_job/runfacts.py (the sealed record + shadow_compare()/enforcing()
+ verdict functions) and phase_verifiers.py / build_deck.py (the dispatch
points that call them). This module imports NOTHING from those three files
and edits NONE of them. It is a pure, additive consumer of an already-public,
already-documented, already-stable contract: the single greppable stderr line
each of them prints today —

    TRUST-BOUNDARY-DIVERGENCE gate=<label> run_dir=<path> legacy=<V>(<reason!r>)
        runfacts=<V>(<reason!r>) enforcing=<bool>
                                            (presentation_job/runfacts.py: shadow_compare)
    TRUST-BOUNDARY-SEAL-FINDING run_dir=<path> <finding line>
                                            (presentation_job/runfacts.py: seal)
    TRUST-BOUNDARY-SHADOW-ERROR <gate>: <exc!r>
                                            (phase_verifiers.py / verifier_registry.py:
                                             the shadow wrapper's own except clause)

Those three prefixes and that shape are not something this module invented —
they are already-merged, already-executing code (grep DIVERGENCE_PREFIX /
FINDING_PREFIX / ERROR_PREFIX in runfacts.py, and the two `print(...,
file=sys.stderr)` call sites in phase_verifiers.py / verifier_registry.py).
Today every one of those lines is printed once and lost: nothing captures
them, nothing persists them, nothing aggregates them, and the ONE existing
test that exercises the divergence path (test_runfacts.py::
test_proven_gap_pass_false_report_still_returns_legacy_true_in_report_only)
asserts on the return value only — it never looks at stderr at all. That gap
is what this module closes.

WHY A LOG-CAPTURE DESIGN INSTEAD OF EDITING shadow_compare()/seal() DIRECTLY:
three builders are splitting this trust-boundary work in parallel
(feat/trust-core, feat/trust-wrap, feat/trust-obs — this branch). Editing
runfacts.py or phase_verifiers.py to call into a recorder directly would put
this file's writes on a collision course with whichever of the other two owns
those files this pass. Capturing the stable, already-public stderr contract
instead means this module needs ZERO coordination and ZERO shared edits: it
works today, against the code already on origin/main, with no dependency on
what --core or --wrap change or add this pass. If a future increment wants a
tighter, in-process hook instead of a stderr tee, THIS module is the
interface to extend — record_observation() below takes a fully-formed
ShadowObservation and does not care how the caller obtained one.

REPORT-ONLY, STRUCTURALLY (not by convention — by construction):
  * capture_stderr() is a pass-through tee: every byte written to sys.stderr
    by the wrapped code is still written to the real sys.stderr, unchanged,
    before or after this module's parser looks at it. Nothing this module
    does can suppress, delay-block, or alter what the wrapped code prints or
    returns.
  * run_and_record() is a subprocess wrapper: the child's returncode,
    stdout, and stderr are returned to the caller EXACTLY as
    subprocess.run() would have returned them. This module never inspects
    or rewrites the returncode.
  * record_observation() is best-effort / non-fatal (mirrors
    runfacts._best_effort_save's own contract): a disk-write failure here is
    caught and swallowed, never raised into the caller. An observability
    write failing must never be the reason a real build fails.
  * Nothing in this file calls os._exit, sys.exit, or raises out of a
    capture/record path on the happy OR the parse-failure path. A line that
    doesn't match any known TRUST-BOUNDARY-* shape is simply not an
    observation — it passes through the tee untouched and is not recorded
    (this module does not attempt to parse arbitrary build output).

ZERO third-party deps (stdlib only), matching the rest of this package.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import IO, Any, Dict, List, Optional, Sequence

# Persisted alongside (never overwriting) runfacts.py's own sealed-record file
# (presentation_job/runfacts.py: SEALED_REL = working/checkpoints/
# .runfacts.sealed.json) -- same directory, a DIFFERENT filename, append-only
# JSONL rather than a single sealed JSON object, because this is a log of
# EVENTS across a run (potentially many gates, each checked once) rather than
# a single point-in-time fact record.
SHADOW_LOG_REL = Path("working") / "checkpoints" / ".trust-boundary-shadow.jsonl"

OBS_SCHEMA_VERSION = 1

# The exact prefixes already live in runfacts.py / phase_verifiers.py /
# verifier_registry.py today. Duplicated here as plain strings (not imported)
# so this module has zero import dependency on the files it observes -- it
# must keep working even if --core/--wrap rename, move, or temporarily break
# import of those modules mid-pass.
DIVERGENCE_PREFIX = "TRUST-BOUNDARY-DIVERGENCE"
FINDING_PREFIX = "TRUST-BOUNDARY-SEAL-FINDING"
ERROR_PREFIX = "TRUST-BOUNDARY-SHADOW-ERROR"

KNOWN_KINDS = (DIVERGENCE_PREFIX, FINDING_PREFIX, ERROR_PREFIX)

# Matches shadow_compare()'s exact f-string (runfacts.py ~line 1450):
#   TRUST-BOUNDARY-DIVERGENCE gate={label} run_dir={run_dir} legacy={V}({reason!r})
#       runfacts={V}({reason!r}) enforcing={bool}
_DIVERGENCE_RE = re.compile(
    r"^" + re.escape(DIVERGENCE_PREFIX) + r" gate=(?P<gate>\S+) run_dir=(?P<run_dir>\S+) "
    r"legacy=(?P<legacy_verdict>PASS|FAIL|UNDETERMINED)\((?P<legacy_reason>.*?)\) "
    r"runfacts=(?P<new_verdict>PASS|FAIL|UNDETERMINED)\((?P<new_reason>.*?)\) "
    r"enforcing=(?P<enforcing>True|False)\s*$"
)

# Matches seal()'s finding line (runfacts.py ~line 538):
#   TRUST-BOUNDARY-SEAL-FINDING run_dir={run_dir} {line}
_FINDING_RE = re.compile(
    r"^" + re.escape(FINDING_PREFIX) + r" run_dir=(?P<run_dir>\S+) (?P<detail>.*)$"
)

# Matches both shadow-wrapper error prints (phase_verifiers.py /
# verifier_registry.py):
#   TRUST-BOUNDARY-SHADOW-ERROR {gate}: {exc!r}
#   TRUST-BOUNDARY-SHADOW-ERROR qc:{qc_key}: {exc!r}
#   TRUST-BOUNDARY-SHADOW-ERROR verifier={gate} seal raised {exc!r}
_ERROR_RE = re.compile(r"^" + re.escape(ERROR_PREFIX) + r" (?P<detail>.*)$")


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclasses.dataclass(frozen=True)
class ShadowObservation:
    """One would-have-blocked (or would-have-confirmed) observation, captured
    from a single TRUST-BOUNDARY-* stderr line. `gate` and the specific fact
    named in `new_reason` / `legacy_reason` / `detail` are what answer "the
    record names the specific fact that failed and where it came from" --
    `source` answers "where it came from" at the code level (which existing,
    unmodified function emitted this line)."""

    captured_at: str
    kind: str                       # one of KNOWN_KINDS
    source: str                     # e.g. "presentation_job.runfacts.shadow_compare"
    gate: Optional[str]             # None only for a SEAL-FINDING (run-wide, not per-gate)
    run_dir: Optional[str]
    legacy_verdict: Optional[str]   # PASS / FAIL / UNDETERMINED, DIVERGENCE only
    legacy_reason: Optional[str]
    new_verdict: Optional[str]      # PASS / FAIL / UNDETERMINED, DIVERGENCE only
    new_reason: Optional[str]
    enforcing: Optional[bool]       # DIVERGENCE only -- was PRES_TRUST_BOUNDARY_ENFORCE=1
    detail: Optional[str]           # SEAL-FINDING / SHADOW-ERROR body
    raw_line: str

    @property
    def would_have_blocked(self) -> bool:
        """True iff this observation represents a run that a stricter gate
        WOULD have failed while the legacy/actual result let it through --
        the exact fact the acceptance criteria calls "detected but still
        proceeds". A DIVERGENCE where the RunFacts verdict is not PASS is
        would-have-blocked (the legacy side won, by construction of
        report-only mode, whenever enforcing=False). A SEAL-FINDING or
        SHADOW-ERROR is a signal worth surfacing to an operator but is not
        itself a pass/fail divergence, so it does not count here."""
        return self.kind == DIVERGENCE_PREFIX and self.new_verdict != "PASS"

    def to_json(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["schema_version"] = OBS_SCHEMA_VERSION
        d["would_have_blocked"] = self.would_have_blocked
        return d


def parse_line(line: str) -> Optional[ShadowObservation]:
    """Parse ONE line of text. Returns None (never raises) for anything that
    is not a recognised TRUST-BOUNDARY-* line -- this module only records
    what it can unambiguously attribute to a known, existing emitter; it does
    not guess at the shape of build output it wasn't given a contract for."""
    line = line.rstrip("\n")
    if not line or not any(line.startswith(p) for p in KNOWN_KINDS):
        return None

    m = _DIVERGENCE_RE.match(line)
    if m is not None:
        g = m.groupdict()
        return ShadowObservation(
            captured_at=_utcnow(),
            kind=DIVERGENCE_PREFIX,
            source="presentation_job.runfacts.shadow_compare",
            gate=g["gate"],
            run_dir=g["run_dir"],
            legacy_verdict=g["legacy_verdict"],
            legacy_reason=_unrepr(g["legacy_reason"]),
            new_verdict=g["new_verdict"],
            new_reason=_unrepr(g["new_reason"]),
            enforcing=(g["enforcing"] == "True"),
            detail=None,
            raw_line=line,
        )

    m = _FINDING_RE.match(line)
    if m is not None:
        g = m.groupdict()
        return ShadowObservation(
            captured_at=_utcnow(),
            kind=FINDING_PREFIX,
            source="presentation_job.runfacts.seal",
            gate=None,
            run_dir=g["run_dir"],
            legacy_verdict=None,
            legacy_reason=None,
            new_verdict=None,
            new_reason=None,
            enforcing=None,
            detail=g["detail"],
            raw_line=line,
        )

    m = _ERROR_RE.match(line)
    if m is not None:
        g = m.groupdict()
        return ShadowObservation(
            captured_at=_utcnow(),
            kind=ERROR_PREFIX,
            source="phase_verifiers/verifier_registry shadow wrapper",
            gate=None,
            run_dir=None,
            legacy_verdict=None,
            legacy_reason=None,
            new_verdict=None,
            new_reason=None,
            enforcing=None,
            detail=g["detail"],
            raw_line=line,
        )

    # Starts with a known prefix but didn't match its expected shape -- an
    # emitter changed its format. Record it anyway, degraded, rather than
    # silently dropping a real signal (same "degrade, never discard" rule
    # runfacts.py itself follows for UNPARSEABLE facts).
    return ShadowObservation(
        captured_at=_utcnow(),
        kind="UNRECOGNISED-SHAPE",
        source="trust_boundary_observability.parse_line",
        gate=None,
        run_dir=None,
        legacy_verdict=None,
        legacy_reason=None,
        new_verdict=None,
        new_reason=None,
        enforcing=None,
        detail="line began with a known TRUST-BOUNDARY-* prefix but did not "
               "match the expected shape -- recorded raw, not decoded",
        raw_line=line,
    )


def _unrepr(s: str) -> str:
    """shadow_compare() prints reasons through !r (Python repr). Best-effort
    decode back to the plain string for a friendlier operator report; falls
    back to the raw repr text on anything that doesn't literal_eval cleanly
    (never raises)."""
    import ast
    try:
        val = ast.literal_eval(s)
        return val if isinstance(val, str) else s
    except Exception:  # noqa: BLE001
        return s


def _log_path_for(run_dir: Path, log_path: Optional[Path]) -> Path:
    if log_path is not None:
        return Path(log_path)
    return Path(run_dir) / SHADOW_LOG_REL


def record_observation(obs: ShadowObservation, run_dir: Path,
                        log_path: Optional[Path] = None) -> None:
    """Append one observation as one JSON line. Best-effort / non-fatal: an
    exception here is caught and swallowed, mirroring runfacts.py's own
    _best_effort_save contract -- see the module docstring's REPORT-ONLY
    section. Never truncates or rewrites prior entries (append-only), 0600,
    parent dirs created on demand."""
    try:
        out_path = _log_path_for(run_dir, log_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(obs.to_json(), sort_keys=True)
        # Create with 0600 from the first write; append thereafter.
        existed = out_path.exists()
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        if not existed:
            os.chmod(out_path, 0o600)
    except Exception:  # noqa: BLE001 -- observability must never break a caller
        pass


def load_observations(run_dir: Path, log_path: Optional[Path] = None) -> List[ShadowObservation]:
    """Read back the persisted JSONL for a run. Returns [] if absent/unreadable
    (never raises) -- a read-only audit view, same posture as
    runfacts.load_sealed()."""
    p = _log_path_for(run_dir, log_path)
    out: List[ShadowObservation] = []
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return out
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        d.pop("schema_version", None)
        d.pop("would_have_blocked", None)
        try:
            out.append(ShadowObservation(**d))
        except TypeError:  # noqa: BLE001 -- schema drift; skip the one bad row
            continue
    return out


class _TeeTextIO(io.TextIOBase):
    """Wraps an existing text stream. Every write() goes to the real stream
    FIRST (unchanged, full pass-through -- this is what makes capture_stderr
    structurally unable to suppress or alter what wrapped code prints), then
    is split into lines and handed to `on_line` for parsing. Partial writes
    (no trailing newline) are buffered until a newline arrives, so a
    print(..., end="") sequence is still parsed correctly."""

    def __init__(self, real: IO[str], on_line):
        super().__init__()
        self._real = real
        self._on_line = on_line
        self._buf = ""

    def write(self, s: str) -> int:
        n = self._real.write(s)
        self._real.flush()
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            try:
                self._on_line(line)
            except Exception:  # noqa: BLE001 -- a parse callback must never
                pass          # break the stream it's observing
        return n if n is not None else len(s)

    def flush(self) -> None:
        self._real.flush()

    def isatty(self) -> bool:
        return False


@contextlib.contextmanager
def capture_stderr(run_dir: Path, log_path: Optional[Path] = None,
                    observations: Optional[List[ShadowObservation]] = None):
    """In-process capture: while this context is open, every line written to
    sys.stderr is (a) still written to the REAL sys.stderr unchanged, in
    full, and (b) parsed; recognised TRUST-BOUNDARY-* lines are persisted via
    record_observation() and, if `observations` was passed, also appended to
    it in memory for the caller's own immediate use (e.g. a demo/proof
    script, or a future in-process caller that wants observations without a
    subprocess boundary). This function cannot raise out of the wrapped
    block's own exceptions -- it only ever adds a pass-through layer around
    sys.stderr and restores the original stream in a `finally`, exception or
    not."""
    real_stderr = sys.stderr

    def _handle(line: str) -> None:
        obs = parse_line(line)
        if obs is None:
            return
        record_observation(obs, run_dir, log_path)
        if observations is not None:
            observations.append(obs)

    tee = _TeeTextIO(real_stderr, _handle)
    sys.stderr = tee
    try:
        yield observations if observations is not None else []
    finally:
        sys.stderr = real_stderr


def run_and_record(argv: Sequence[str], run_dir: Path, log_path: Optional[Path] = None,
                    **subprocess_kwargs: Any) -> subprocess.CompletedProcess:
    """Process-level capture: run `argv` as a child process, tee its stderr
    live (parsed line-by-line as it arrives, recorded as each observation is
    seen -- not batch-parsed after exit, so a process that hangs after
    emitting a divergence still has that divergence on disk). Returns the
    subprocess.CompletedProcess EXACTLY as subprocess.run() would -- same
    returncode, same captured stdout/stderr text -- this function never
    inspects or changes the child's exit status. This is the wrapper an
    operator (or a CI step) can put around ANY existing entry point --
    build_deck.py's CLI, run_signature_deck.py, or the standalone
    `python3 -m presentation_job.runfacts --verify <run_dir>` CLI -- without
    that entry point needing to know this module exists."""
    proc = subprocess.Popen(
        list(argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, **subprocess_kwargs,
    )
    stderr_lines: List[str] = []

    assert proc.stderr is not None
    for raw_line in proc.stderr:
        stderr_lines.append(raw_line)
        sys.stderr.write(raw_line)
        line = raw_line.rstrip("\n")
        obs = parse_line(line)
        if obs is not None:
            record_observation(obs, run_dir, log_path)
    stdout_text = proc.stdout.read() if proc.stdout is not None else ""
    returncode = proc.wait()
    return subprocess.CompletedProcess(
        args=list(argv), returncode=returncode,
        stdout=stdout_text, stderr="".join(stderr_lines),
    )


def ingest_log_file(text_log_path: Path, run_dir: Path,
                     log_path: Optional[Path] = None) -> int:
    """Batch variant of run_and_record's parsing: read an EXISTING plain-text
    build log (e.g. a saved CI job log, or a log an operator already has on
    disk from a run that wasn't launched through run_and_record) and record
    every TRUST-BOUNDARY-* line found in it. Returns the count of
    observations recorded. Never raises -- an unreadable log yields 0."""
    count = 0
    try:
        with open(text_log_path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                obs = parse_line(raw.rstrip("\n"))
                if obs is not None:
                    record_observation(obs, run_dir, log_path)
                    count += 1
    except Exception:  # noqa: BLE001
        return count
    return count
