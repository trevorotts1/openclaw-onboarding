#!/usr/bin/env python3
"""Skill 72 technical QC (MG-034): the fail-closed replacement for the
legacy qc.sh sweeps.

Why this exists: the legacy qc.sh printed PASS unconditionally for its
contact sheet (the Python heredoc's failure was never checked), counted
grep matches of ffmpeg output for its black/freeze sweeps (so an
ffmpeg failure, which prints nothing matchable, read as zero defects),
and compared the output's audio stream against the output's video
stream instead of against the plan. Defect register D-QC-FALSE-GREEN.
This module is built so that none of those failure shapes can recur:

- Every check emits an explicit result: PASS, FAIL,
  SKIPPED_WITH_REASON, or NOT_RUN, each carrying the command run, its
  exit status, the observed values, and an evidence pointer.
- A tool that cannot start, times out, or exits nonzero makes its
  check FAIL (or NOT_RUN with the reason when a prerequisite failed
  first). A tool error can never become a PASS, and a crash anywhere
  surfaces as a named check result, never a traceback-only exit.
- The gate fails when any check FAILs, and when any MANDATORY check
  is missing or NOT_RUN.
- Checks validate the artifact against the PLANNED truth: the MG-021
  compiled timeline and sidecar, the package manifest's canvas and
  delivery profile, and the MG-023 resolved audio plan. Two output
  streams are never compared against each other as a substitute for
  the plan.
- Black and freeze sweeps are intent-aware: intervals the plan
  approves (timeline hold_start events, scene-spec readable holds,
  planner-declared intentional stillness, and the job's
  qc-approved-intervals.json declaration) are not defects;
  unapproved intervals are, by name.
- Loudness is verified only where MG-023 says it applies: a job with
  an independent final mix (mode own) that carries a loudness target.
  Modes none and inherited are SKIPPED_WITH_REASON for loudness and
  are instead checked for what their mode promises.
- The review receipt is the MG-031 coverage record for THIS artifact:
  it must exist, name this job, carry verdict complete, and bind the
  artifact's own sha256. A bundle build failure, an incomplete
  verdict, or a receipt for different bytes fails the gate by name,
  and dependent scoring has no passing record to stand on.
- The MG-029 process registry is consumed at the end of the run:
  the records the isolation layer filed for this job must show no
  live render processes when QC judges the artifact final. A
  still-running (or leaked) render process fails by name, and a
  registry record too malformed to read fails by name rather than
  being silently ignored.

The report is the job's final-QC record: it carries the top-level
artifact_path / artifact_sha256 / verdict fields the MG-025 delivery
gate consumes, and it validates against references/qc-schema.json
(schema_version 1.0).

Usage:
    python3 scripts/qc.py check --job-dir DIR [--final PATH]
                                [--out REPORT.json]
    python3 scripts/qc.py check --plan PLAN.json --sidecar S.json
                                --media MEDIA.json --final FINAL.mp4
                                [--manifest M.json] [--coverage C.json]
    python3 scripts/qc.py check --legacy-manifest M.json
                                --workdir DIR --final FINAL.mp4
    (the last form is what the scripts/qc.sh compatibility lane runs)

Exit codes follow directive Section 16.9 through the same category
map the MG-025 gate uses: 0 pass; 9 foreign job / hash mismatch;
2 schema / mode / timeline invalid; 3 input missing / capability;
5 encode failed; 6 QC failed / coverage incomplete; 1 internal;
2 usage (argparse).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

SCHEMA_VERSION = "1.0"
ITEM = "MG-034"
TOOL_VERSION = "1.0.0"
SAMPLE_RATE = 48000

# Section 16.9 exit classes, mirrored from scripts/check_approvals.py
# so a QC verdict and the delivery gate agree on what a failure costs.
EXIT_BY_CATEGORY = {
    "MG_FOREIGN_JOB": 9,
    "MG_HASH_MISMATCH": 9,
    "MG_SECURITY_VIOLATION": 9,
    "MG_SCHEMA_INVALID": 2,
    "MG_UNKNOWN_COMPONENT": 2,
    "MG_MODE_MISMATCH": 2,
    "MG_TIMELINE_INVALID": 2,
    "MG_INPUT_MISSING": 3,
    "MG_CAPABILITY_UNSUPPORTED": 3,
    "MG_ENCODE_FAILED": 5,
    "MG_QC_FAILED": 6,
    "MG_COVERAGE_INCOMPLETE": 6,
}
CATEGORY_ORDER = [
    "MG_FOREIGN_JOB", "MG_HASH_MISMATCH", "MG_SECURITY_VIOLATION",
    "MG_SCHEMA_INVALID", "MG_UNKNOWN_COMPONENT", "MG_MODE_MISMATCH",
    "MG_TIMELINE_INVALID", "MG_INPUT_MISSING",
    "MG_CAPABILITY_UNSUPPORTED", "MG_ENCODE_FAILED", "MG_QC_FAILED",
    "MG_COVERAGE_INCOMPLETE",
]

PASS = "PASS"
FAIL = "FAIL"
SKIPPED = "SKIPPED_WITH_REASON"
NOT_RUN = "NOT_RUN"

# Tolerances. The duration tolerance is MG-022's own (assemble.py
# verify_output): the encoded duration may differ from the compiled
# duration by container padding, never by a missing piece of program.
DURATION_TOLERANCE_S = 0.12
FPS_TOLERANCE = 0.01
# Legacy V1 runs pad audio to whole encoder frames through a chain
# that predates the sample-exact assembler; the legacy lane keeps a
# documented quarter second, the V2 lane derives its tolerance from
# DURATION_TOLERANCE_S like everything else.
LEGACY_AUDIO_TOLERANCE_S = 0.25
# Black/freeze sweep thresholds, carried from the legacy script's
# declared values (black runs over 0.5 s, frozen runs over 1.0 s) so
# the replacement judges the same events the old gate claimed to.
BLACK_MIN_SECONDS = 0.5
BLACK_PIXEL_THRESHOLD = 0.10
FREEZE_NOISE = 0.003
FREEZE_MIN_SECONDS = 1.0
# Detection boundaries wobble by a frame or two at interval edges
# (codec delay, filter rounding). Approval coverage allows this much
# slack at both ends; it cannot hide a real defect, which by the
# thresholds above is at least 15 frames long.
INTERVAL_EDGE_TOLERANCE_FRAMES = 2

ALPHA_PIXEL_FORMATS = (
    "yuva", "rgba", "bgra", "argb", "abgr", "ya8", "ya16", "pal8",
)
ALPHA_PROFILES = ("prores_4444_alpha", "vp9_alpha")


def _load_audio_policy():
    """MG-023's policy layer lives beside this module. Load it by
    path so qc.py works as a script and when a test loads this file
    by path (the assemble.py pattern)."""
    try:
        import audio_policy
        return audio_policy
    except ImportError:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "audio_policy.py")
        spec = importlib.util.spec_from_file_location("audio_policy", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


audio_policy = _load_audio_policy()


# --------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def round_half_up(x):
    return int(math.floor(x + 0.5))


class ToolResult:
    """One subprocess invocation, recorded whether it ran or not."""

    def __init__(self, argv):
        self.argv = [str(a) for a in argv]
        self.returncode = None
        self.stdout = ""
        self.stderr = ""
        self.error = None  # spawn failure or timeout description

    @property
    def command(self):
        return shlex.join(self.argv)

    def evidence(self):
        out = {"command": self.command, "exit_status": self.returncode}
        if self.error:
            out["error"] = self.error
        return out


def run_tool(argv, timeout=600):
    """Run a tool, never raising. A missing binary, a timeout, and a
    nonzero exit are all data the calling check must judge."""
    res = ToolResult(argv)
    try:
        proc = subprocess.run(res.argv, capture_output=True, text=True,
                              timeout=timeout)
        res.returncode = proc.returncode
        res.stdout = proc.stdout or ""
        res.stderr = proc.stderr or ""
    except FileNotFoundError:
        res.error = "tool not found: %s" % res.argv[0]
    except subprocess.TimeoutExpired:
        res.error = "timed out after %ds" % timeout
    except OSError as exc:
        res.error = "could not start: %s" % exc
    return res


def make_check(check_id, title, mandatory, status, message, code=None,
               category=None, tool=None, observed=None, evidence=None):
    """One explicit check result. `tool` is a ToolResult (or a list of
    them) whose command and exit status the result must carry."""
    out = {
        "id": check_id,
        "title": title,
        "mandatory": bool(mandatory),
        "status": status,
        "code": code,
        "category": category,
        "message": message,
        "command": None,
        "exit_status": None,
        "observed": observed or {},
        "evidence": evidence,
    }
    if tool is not None:
        tools = tool if isinstance(tool, list) else [tool]
        out["command"] = "; ".join(t.command for t in tools)
        exits = [t.returncode for t in tools]
        out["exit_status"] = exits[0] if len(exits) == 1 else exits
        errs = [t.error for t in tools if t.error]
        if errs:
            out["observed"] = dict(out["observed"], tool_errors=errs)
    return out


def not_run(check_id, title, mandatory, reason, evidence=None):
    return make_check(check_id, title, mandatory, NOT_RUN, reason,
                      evidence=evidence)


def skipped(check_id, title, mandatory, reason, observed=None,
            evidence=None):
    return make_check(check_id, title, mandatory, SKIPPED, reason,
                      observed=observed, evidence=evidence)


# --------------------------------------------------------------------
# Interval arithmetic for the intent-aware sweeps
# --------------------------------------------------------------------

def subtract_approvals(detected, approvals):
    """Remove approved coverage from detected [start, end) frame
    intervals, with INTERVAL_EDGE_TOLERANCE_FRAMES of slack at the
    approval edges. Returns the uncovered remainder intervals."""
    remaining = []
    for start, end in detected:
        pieces = [(start, end)]
        for a_start, a_end in approvals:
            lo = a_start - INTERVAL_EDGE_TOLERANCE_FRAMES
            hi = a_end + INTERVAL_EDGE_TOLERANCE_FRAMES
            nxt = []
            for p_start, p_end in pieces:
                if hi <= p_start or lo >= p_end:
                    nxt.append((p_start, p_end))
                    continue
                if lo > p_start:
                    nxt.append((p_start, lo))
                if hi < p_end:
                    nxt.append((hi, p_end))
            pieces = nxt
            if not pieces:
                break
        remaining.extend(pieces)
    return sorted(remaining)


def seconds_to_frames(seconds, fps):
    return round_half_up(seconds * fps)


# --------------------------------------------------------------------
# MG-029 process registry consumption
# --------------------------------------------------------------------
# The isolation layer records every render process it launches in
# one JSON file per job under the process registry directory
# (runtime/src/isolation/processes.ts): {jobId, token, processes},
# each process entry carrying its pid and the kernel start-time
# ticks recorded at launch. The helpers below replicate that
# module's directory rule, file naming, and identity semantics
# exactly, so QC judges liveness the same way the layer that wrote
# the records does.

def process_registry_dir():
    """The MG-029 registry directory: MOTION_PROCESS_REGISTRY_DIR
    when set, else $XDG_STATE_HOME or ~/.local/state, under
    motion-render/processes (processes.ts defaultRegistryDir)."""
    override = os.environ.get("MOTION_PROCESS_REGISTRY_DIR")
    if override:
        return Path(override)
    state_base = os.environ.get("XDG_STATE_HOME") or str(
        Path.home() / ".local" / "state")
    return Path(state_base) / "motion-render" / "processes"


def sanitize_job_segment(job_id):
    """paths.ts sanitizeJobSegment, replicated: characters outside
    [A-Za-z0-9._:-] become underscores, leading dots collapse to one
    underscore, an empty result becomes "job", and the segment is
    truncated to 96 characters."""
    cleaned = re.sub(r"[^A-Za-z0-9._:-]", "_", str(job_id))
    cleaned = re.sub(r"^\.+", "_", cleaned)
    if cleaned == "":
        cleaned = "job"
    return cleaned[:96]


def _proc_stat(pid):
    """(state, start_time_ticks) from /proc/<pid>/stat, or None on
    any doubt. Mirrors processes.ts readProcStat: the comm field
    may contain spaces and parens, so fields are counted from the
    last close paren; state is field 3, starttime is field 22."""
    try:
        raw = Path("/proc/%d/stat" % pid).read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return None
    close = raw.rfind(")")
    if close < 0:
        return None
    fields = raw[close + 2:].split(" ")
    try:
        return fields[0], int(fields[19])
    except (IndexError, ValueError):
        return None


def read_start_time_ticks(pid):
    stat = _proc_stat(pid)
    return stat[1] if stat else None


def _pid_alive(pid):
    """MG-029 pidAlive: /proc shows the pid in a non-zombie state.
    A zombie is already dead; only its parent has not reaped it."""
    stat = _proc_stat(pid)
    return bool(stat) and stat[0] not in ("Z", "X")


def _environ_token(pid):
    try:
        raw = Path("/proc/%d/environ" % pid).read_bytes()
    except OSError:
        return None
    for entry in raw.split(b"\0"):
        key, eq, value = entry.partition(b"=")
        if eq and key == b"MOTION_JOB_TOKEN":
            return value.decode("utf-8", errors="replace")
    return None


def registry_identity_live(pid, start_ticks, token):
    """MG-029 identityMatches: the pid is alive and its identity
    is proven, by the recorded kernel start-time when one was
    recorded, else by the job ownership token in its environment.
    A pid with neither proof does not match: it may have been
    recycled and belong to someone else."""
    if not _pid_alive(pid):
        return False
    if start_ticks is not None:
        stat = _proc_stat(pid)
        return bool(stat) and stat[1] == start_ticks
    return token is not None and _environ_token(pid) == token


def _registry_shape_problem(doc):
    """Validate one parsed registry file against the documented
    format {jobId: string, token: string, processes: [...]}.
    Returns a problem description, or None when the shape holds."""
    if not isinstance(doc, dict):
        return "the record is not a JSON object"
    if not isinstance(doc.get("jobId"), str):
        return "jobId is missing or not a string"
    if not isinstance(doc.get("token"), str):
        return "token is missing or not a string"
    processes = doc.get("processes")
    if not isinstance(processes, list):
        return "processes is missing or not a list"
    for entry in processes:
        if not isinstance(entry, dict):
            return "a process entry is not an object"
        pid = entry.get("pid")
        if not isinstance(pid, int) or isinstance(pid, bool):
            return "a process entry's pid is missing or not an integer"
        ticks = entry.get("startTimeTicks")
        if ticks is not None and (not isinstance(ticks, int)
                                  or isinstance(ticks, bool)):
            return ("process %d's startTimeTicks is neither an "
                    "integer nor null" % pid)
        state = entry.get("state")
        if state is not None and state not in (
                "running", "exited", "terminated"):
            return ("process %d's state %r is not a registry state"
                    % (pid, state))
    return None


# --------------------------------------------------------------------
# Runtime font alias registry consumption
# --------------------------------------------------------------------
# The canonical contracts require a job package to declare font
# requirements by alias token (family_alias, source
# runtime_registry): the alias is the intake-layer name, and the
# runtime resolves it to a real family through its own registry
# (runtime/src/remotion/fonts.ts, ALIAS_REGISTRY) and refuses to
# render otherwise. The registry is shipped data, so the alias to
# family map is parsed out of that file at check time; a copy of
# the map kept here would drift from the runtime's truth. When
# the file cannot be read or its registry literal cannot be
# parsed, alias resolution cannot be proven and the fonts check
# fails by name (QC_FONT_REGISTRY_UNREADABLE): it never falls
# back to comparing the raw alias token against fontconfig
# families, which is the comparison that false-failed every
# canonically declared package (the layer-7 defect the MG-035
# and MG-037 evidence records both carry).

def font_registry_path():
    """The shipped runtime font registry: MOTION_FONT_REGISTRY_PATH
    when set (a test seam mirroring MOTION_PROCESS_REGISTRY_DIR),
    else runtime/src/remotion/fonts.ts under this module's skill
    root."""
    override = os.environ.get("MOTION_FONT_REGISTRY_PATH")
    if override:
        return Path(override)
    return (Path(__file__).resolve().parent.parent / "runtime"
            / "src" / "remotion" / "fonts.ts")


def _registry_literal(text):
    """The inner text of the ALIAS_REGISTRY object literal, or
    None when it cannot be located or brace-matched. String
    state is tracked so braces inside strings cannot end the
    match early."""
    marker = text.find("ALIAS_REGISTRY")
    if marker < 0:
        return None
    start = text.find("{", marker)
    if start < 0:
        return None
    depth = 0
    quote = None
    i = start
    while i < len(text):
        ch = text[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
        i += 1
    return None


def _registry_entries(body):
    """Top-level entries of the registry literal, as a list of
    (key, entry_body) pairs, or None when the literal is too
    malformed to scan. Entry keys are double-quoted strings;
    each entry's object is brace-matched whole, so nested
    objects (fileByWeight) stay inside their entry and are
    never mistaken for entries."""
    entries = []
    i = 0
    n = len(body)
    while i < n:
        if body[i] != '"':
            i += 1
            continue
        j = i + 1
        chars = []
        while j < n and body[j] != '"':
            if body[j] == "\\" and j + 1 < n:
                j += 1
            chars.append(body[j])
            j += 1
        if j >= n:
            return None
        key = "".join(chars)
        k = j + 1
        while k < n and body[k] in " \t\r\n:":
            k += 1
        if k >= n or body[k] != "{":
            # A quoted string in a value position, not an entry
            # key: skip it and keep scanning.
            i = j + 1
            continue
        depth = 0
        quote = None
        m = k
        end = None
        while m < n:
            ch = body[m]
            if quote is not None:
                if ch == "\\":
                    m += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "\"'`":
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = m
                    break
            m += 1
        if end is None:
            return None
        entries.append((key, body[k + 1:end]))
        i = end + 1
    return entries


def load_font_alias_registry(path):
    """Parse the alias to family map out of the shipped runtime
    registry at `path`. Returns (mapping, None) on success or
    (None, problem) when the file cannot be read or its
    registry literal yields no usable entries. The mapping is
    the runtime's own data, read at check time; nothing here
    duplicates it. Only the family is consumed: per-weight
    file registration is the runtime's render-time concern,
    and it refuses unregistered weights itself."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return None, "cannot be read: %s" % exc
    body = _registry_literal(text)
    if body is None:
        return None, ("no ALIAS_REGISTRY object literal could "
                      "be located in the file")
    entries = _registry_entries(body)
    if not entries:
        return None, ("the ALIAS_REGISTRY literal yielded no "
                      "entries")
    mapping = {}
    for alias, entry_body in entries:
        m = re.search(r'family\s*:\s*"([^"\\]+)"', entry_body)
        if not m:
            return None, ("registry entry %r carries no family "
                          "string" % alias)
        mapping[alias] = m.group(1)
    return mapping, None


# --------------------------------------------------------------------
# The QC run
# --------------------------------------------------------------------

class QcRun:
    def __init__(self, args):
        self.args = args
        self.ffmpeg = args.ffmpeg
        self.ffprobe = args.ffprobe
        self.checks = []
        self.job_dir = Path(args.job_dir).resolve() if args.job_dir else None
        self.final_path = self._resolve_final()
        # Plan-side state, filled by inputs.plan.
        self.manifest = None
        self.manifest_path = None
        self.timeline = None
        self.sidecar = None
        self.plan_path = None
        self.sidecar_path = None
        self.media = None
        self.media_path = None
        self.audio_plan = None
        self.plan_error = None
        self.plan_standalone = False
        # Artifact-side state.
        self.artifact_sha256 = None
        self.artifact_bytes = None
        self.probe = None  # parsed ffprobe JSON for the final
        self.probe_tool = None
        self.output_samples = None  # decoded PCM of the final's audio
        self.inputs_record = {}

    # -- path resolution -------------------------------------------

    def _resolve_final(self):
        if self.args.final:
            return Path(self.args.final)
        if self.job_dir:
            return self.job_dir / "renders" / "final.mp4"
        return None

    def _job_file(self, explicit, *candidates):
        if explicit:
            return Path(explicit)
        if self.job_dir:
            for rel in candidates:
                p = self.job_dir / rel
                if p.exists():
                    return p
        return None

    def _plan_input_path(self):
        """The plan document this run consumes, when one exists on
        disk: the legacy manifest, the explicit --plan, or the job
        package's timeline. Checks whose own product is not a file
        (tools.available) point their evidence here rather than
        fabricating a pointer."""
        legacy = getattr(self.args, "legacy_manifest", None)
        if legacy and Path(legacy).exists():
            return Path(legacy)
        plan = getattr(self.args, "plan", None)
        if plan and Path(plan).exists():
            return Path(plan)
        if self.job_dir:
            for rel in ("timeline.json", "plan.json"):
                p = self.job_dir / rel
                if p.exists():
                    return p
        return None

    def add(self, check):
        self.checks.append(check)
        return check

    def check_by_id(self, check_id):
        for c in self.checks:
            if c["id"] == check_id:
                return c
        return None

    def failed(self, check_id):
        c = self.check_by_id(check_id)
        return c is not None and c["status"] in (FAIL, NOT_RUN)

    # -- setup checks ------------------------------------------------

    def check_tools(self):
        tools = [run_tool([self.ffmpeg, "-version"], timeout=30),
                 run_tool([self.ffprobe, "-version"], timeout=30)]
        bad = [t for t in tools
               if t.error or t.returncode != 0]
        observed = {
            "ffmpeg": (tools[0].stdout.splitlines() or [""])[0],
            "ffprobe": (tools[1].stdout.splitlines() or [""])[0],
            "tool_paths": {"ffmpeg": shutil.which(self.ffmpeg),
                           "ffprobe": shutil.which(self.ffprobe)},
        }
        if bad:
            names = [t.argv[0] for t in bad]
            return self.add(make_check(
                "tools.available", "ffmpeg and ffprobe are runnable",
                True, FAIL,
                "required tool(s) unavailable or failing: %s; every "
                "measurement below is impossible, so nothing can pass"
                % ", ".join(names),
                code="QC_TOOL_MISSING", category="MG_INPUT_MISSING",
                tool=tools, observed=observed))
        plan_input = self._plan_input_path()
        return self.add(make_check(
            "tools.available", "ffmpeg and ffprobe are runnable",
            True, PASS, "ffmpeg and ffprobe both answered -version "
            "with exit 0", tool=tools, observed=observed,
            evidence=str(plan_input) if plan_input else None))

    def _record_input(self, key, path):
        if path and Path(path).exists():
            self.inputs_record[key] = {
                "path": str(path), "sha256": sha256_file(path)}

    def check_inputs_plan(self):
        """Load the planned truth: manifest (package mode), compiled
        timeline + sidecar, media registry; resolve the MG-023 audio
        plan once, here, exactly as the assembler does."""
        args = self.args
        problems = []
        observed = {}
        # Manifest: required in job-dir mode; optional otherwise.
        self.manifest_path = self._job_file(args.manifest, "manifest.json")
        if self.manifest_path and self.manifest_path.exists():
            try:
                self.manifest = load_json(self.manifest_path)
                self._record_input("manifest", self.manifest_path)
            except (OSError, ValueError) as exc:
                problems.append("manifest %s does not parse: %s"
                                  % (self.manifest_path, exc))
        elif self.job_dir:
            problems.append("job package has no manifest.json at %s"
                            % (self.job_dir / "manifest.json"))
        # Plan: combined document or separate timeline + sidecar.
        self.plan_path = self._job_file(
            args.plan, "timeline.json", "plan.json")
        plan_doc = None
        if self.plan_path and self.plan_path.exists():
            try:
                plan_doc = load_json(self.plan_path)
                self._record_input("plan", self.plan_path)
            except (OSError, ValueError) as exc:
                problems.append("plan %s does not parse: %s"
                                % (self.plan_path, exc))
        else:
            problems.append("no compiled timeline found (looked for "
                            "timeline.json in the job package or an "
                            "explicit --plan)")
        if plan_doc is not None:
            if "timeline" in plan_doc:
                self.timeline = plan_doc["timeline"]
                if plan_doc.get("sidecar") is not None:
                    self.sidecar = plan_doc["sidecar"]
            else:
                self.timeline = plan_doc
                # The plan file IS the standalone timeline document,
                # so a coverage record's timeline hash can be held
                # against its exact bytes. A combined plan file
                # hashes differently from the timeline the bundle
                # consumed even when the content is identical, so
                # the binding is only enforced in this case.
                self.plan_standalone = True
        self.sidecar_path = self._job_file(
            args.sidecar, "timeline-sidecar.json", "sidecar.json")
        if self.sidecar is None and self.sidecar_path \
                and self.sidecar_path.exists():
            try:
                self.sidecar = load_json(self.sidecar_path)
                self._record_input("sidecar", self.sidecar_path)
            except (OSError, ValueError) as exc:
                problems.append("sidecar %s does not parse: %s"
                                % (self.sidecar_path, exc))
        # Media registry: explicit, or media.json in the job package.
        self.media_path = self._job_file(args.media, "media.json")
        if self.media_path and self.media_path.exists():
            try:
                self.media = load_json(self.media_path)
                self._record_input("media", self.media_path)
            except (OSError, ValueError) as exc:
                problems.append("media registry %s does not parse: %s"
                                % (self.media_path, exc))
        if problems:
            self.plan_error = "; ".join(problems)
            return self.add(make_check(
                "inputs.plan", "planned truth loads and agrees",
                True, FAIL, self.plan_error,
                code="QC_INPUT_MISSING", category="MG_INPUT_MISSING",
                observed=observed))
        if self.timeline is None or self.sidecar is None:
            missing = "timeline" if self.timeline is None else "sidecar"
            self.plan_error = ("the compiled %s is missing; QC "
                               "validates against the MG-021 compiled "
                               "plan, and without it there is nothing "
                               "to validate against" % missing)
            return self.add(make_check(
                "inputs.plan", "planned truth loads and agrees",
                True, FAIL, self.plan_error,
                code="QC_PLAN_MISSING", category="MG_INPUT_MISSING",
                observed=observed))
        tl, sc = self.timeline, self.sidecar
        try:
            fps = tl["fps"]
            total_frames = tl["total_frames"]
            total_samples = sc["total_samples"]
            job_id = tl["job_id"]
        except (KeyError, TypeError) as exc:
            self.plan_error = ("compiled plan lacks a required field: "
                               "%s" % exc)
            return self.add(make_check(
                "inputs.plan", "planned truth loads and agrees",
                True, FAIL, self.plan_error,
                code="QC_PLAN_INVALID", category="MG_TIMELINE_INVALID",
                observed=observed))
        if sc.get("fps") != fps or sc.get("total_frames") != total_frames:
            self.plan_error = ("timeline and sidecar disagree on fps "
                               "or total_frames")
            return self.add(make_check(
                "inputs.plan", "planned truth loads and agrees",
                True, FAIL, self.plan_error,
                code="QC_PLAN_INVALID", category="MG_TIMELINE_INVALID",
                observed=observed))
        if total_samples != total_frames * SAMPLE_RATE // fps:
            self.plan_error = ("sidecar total_samples %d does not "
                               "equal total_frames at %d Hz (%d)"
                               % (total_samples, SAMPLE_RATE,
                                  total_frames * SAMPLE_RATE // fps))
            return self.add(make_check(
                "inputs.plan", "planned truth loads and agrees",
                True, FAIL, self.plan_error,
                code="QC_PLAN_INVALID", category="MG_TIMELINE_INVALID",
                observed=observed))
        ids = {"timeline": job_id, "sidecar": sc.get("job_id")}
        if self.manifest:
            ids["manifest"] = self.manifest.get("job_id")
        if self.media:
            ids["media"] = self.media.get("job_id")
        disagree = {k: v for k, v in ids.items()
                    if v is not None and v != job_id}
        if disagree:
            self.plan_error = ("job id disagreement: timeline says "
                               "%r but %s" % (job_id, disagree))
            return self.add(make_check(
                "inputs.plan", "planned truth loads and agrees",
                True, FAIL, self.plan_error,
                code="QC_FOREIGN_JOB", category="MG_FOREIGN_JOB",
                observed=dict(observed, job_ids=ids)))
        # Resolve the audio plan once, through MG-023, from the
        # compiled ownership plus the sidecar's placed content. When
        # no media registry was supplied the registry is empty: mode
        # resolution still works, and the checks that need source
        # files will say so by name.
        media = self.media or {}
        narration_ids = [n["id"] for n in sc.get("narration", [])]
        sfx_ids = [x["id"] for x in sc.get("sfx", [])]
        try:
            self.audio_plan = audio_policy.resolve_audio_plan(
                tl.get("audio_owner"), narration_ids, sfx_ids, media)
        except audio_policy.AudioPolicyError as exc:
            self.plan_error = exc.message
            return self.add(make_check(
                "inputs.plan", "planned truth loads and agrees",
                True, FAIL, self.plan_error,
                code=exc.code, category=exc.mg_category,
                observed=dict(observed, policy_finding=exc.finding())))
        observed.update({
            "job_id": job_id, "fps": fps,
            "total_frames": total_frames,
            "total_samples": total_samples,
            "duration_seconds": round(total_frames / fps, 3),
            "audio_mode": self.audio_plan["mode"],
            "audio_owner": tl.get("audio_owner"),
            "loudness_target": self.audio_plan.get("loudnessTarget"),
            "job_ids": ids,
        })
        return self.add(make_check(
            "inputs.plan", "planned truth loads and agrees",
            True, PASS,
            "compiled timeline and sidecar agree on fps, totals, and "
            "job id; MG-023 resolved audio mode %s"
            % self.audio_plan["mode"],
            observed=observed,
            evidence=str(self.plan_path)))

    # -- artifact checks ---------------------------------------------

    def check_artifact_exists(self):
        if self.final_path is None:
            return self.add(make_check(
                "artifact.exists", "final artifact exists", True, FAIL,
                "no final artifact was named (pass --final or "
                "--job-dir)", code="QC_ARTIFACT_MISSING",
                category="MG_INPUT_MISSING"))
        p = self.final_path
        if not p.exists():
            return self.add(make_check(
                "artifact.exists", "final artifact exists", True, FAIL,
                "final artifact not found: %s" % p,
                code="QC_ARTIFACT_MISSING", category="MG_INPUT_MISSING",
                observed={"path": str(p)}))
        size = p.stat().st_size
        self.artifact_bytes = size
        if size == 0:
            return self.add(make_check(
                "artifact.exists", "final artifact exists", True, FAIL,
                "final artifact is zero bytes: %s" % p,
                code="QC_ARTIFACT_MISSING", category="MG_INPUT_MISSING",
                observed={"path": str(p), "bytes": 0},
                evidence=str(p)))
        return self.add(make_check(
            "artifact.exists", "final artifact exists", True, PASS,
            "final artifact present at %d bytes" % size,
            observed={"path": str(p), "bytes": size}, evidence=str(p)))

    def check_artifact_hash(self):
        if self.failed("artifact.exists"):
            return self.add(not_run(
                "artifact.hash", "artifact sha256 recorded", True,
                "artifact.exists did not pass, so there are no bytes "
                "to hash"))
        self.artifact_sha256 = sha256_file(self.final_path)
        return self.add(make_check(
            "artifact.hash", "artifact sha256 recorded", True, PASS,
            "sha256 of the exact bytes under review is recorded in "
            "the report header and binds every other record",
            observed={"sha256": self.artifact_sha256,
                      "bytes": self.artifact_bytes},
            evidence=str(self.final_path)))

    def _probe_argv(self, path, count_frames=False):
        argv = [self.ffprobe, "-v", "error", "-show_streams",
                "-show_format", "-of", "json"]
        if count_frames:
            argv.append("-count_frames")
        argv.append(str(path))
        return argv

    def check_artifact_probe(self):
        if self.failed("tools.available"):
            return self.add(not_run(
                "artifact.probe", "artifact probes cleanly", True,
                "tools.available failed; ffprobe cannot run"))
        if self.failed("artifact.exists"):
            return self.add(not_run(
                "artifact.probe", "artifact probes cleanly", True,
                "artifact.exists did not pass; nothing to probe"))
        tool = run_tool(self._probe_argv(self.final_path), timeout=300)
        self.probe_tool = tool
        if tool.error or tool.returncode != 0:
            return self.add(make_check(
                "artifact.probe", "artifact probes cleanly", True, FAIL,
                "ffprobe failed on the final artifact (exit %s): %s"
                % (tool.returncode,
                   (tool.error or tool.stderr.strip())[-400:]),
                code="QC_MEDIA_CORRUPT", category="MG_QC_FAILED",
                tool=tool, observed={"path": str(self.final_path)},
                evidence=str(self.final_path)))
        try:
            info = json.loads(tool.stdout)
        except ValueError:
            return self.add(make_check(
                "artifact.probe", "artifact probes cleanly", True, FAIL,
                "ffprobe output is not JSON; the artifact's container "
                "is not readable", code="QC_MEDIA_CORRUPT",
                category="MG_QC_FAILED", tool=tool,
                observed={"path": str(self.final_path)},
                evidence=str(self.final_path)))
        streams = info.get("streams") or []
        video = next((s for s in streams
                      if s.get("codec_type") == "video"), None)
        if not streams or video is None:
            return self.add(make_check(
                "artifact.probe", "artifact probes cleanly", True, FAIL,
                "ffprobe found %s; a final artifact must carry a "
                "video stream" % (
                    "no streams at all" if not streams
                    else "no video stream"),
                code="QC_MEDIA_CORRUPT", category="MG_QC_FAILED",
                tool=tool,
                observed={"streams": [
                    {"index": s.get("index"),
                     "codec_type": s.get("codec_type"),
                     "codec_name": s.get("codec_name")}
                    for s in streams]},
                evidence=str(self.final_path)))
        self.probe = info
        return self.add(make_check(
            "artifact.probe", "artifact probes cleanly", True, PASS,
            "ffprobe parsed the container and found a video stream",
            tool=tool,
            observed={"streams": [
                {"index": s.get("index"),
                 "codec_type": s.get("codec_type"),
                 "codec_name": s.get("codec_name")}
                for s in streams],
                "format": (info.get("format") or {}).get("format_name")},
            evidence=str(self.final_path)))

    def check_artifact_decode(self):
        if self.failed("artifact.probe"):
            return self.add(not_run(
                "artifact.decode", "artifact decodes end to end", True,
                "artifact.probe did not pass; a full decode would "
                "only repeat its failure"))
        argv = [self.ffmpeg, "-v", "error", "-i", str(self.final_path),
                "-f", "null", "-"]
        tool = run_tool(argv, timeout=1800)
        errors = [ln for ln in tool.stderr.splitlines() if ln.strip()]
        if tool.error or tool.returncode != 0 or errors:
            return self.add(make_check(
                "artifact.decode", "artifact decodes end to end", True,
                FAIL,
                "full decode of the final artifact reported errors "
                "(exit %s): %s" % (tool.returncode,
                                   "; ".join(errors[:3])[-400:]),
                code="QC_MEDIA_CORRUPT", category="MG_QC_FAILED",
                tool=tool,
                observed={"error_lines": errors[:5]},
                evidence=str(self.final_path)))
        return self.add(make_check(
            "artifact.decode", "artifact decodes end to end", True,
            PASS, "every stream decoded to the end with no error",
            tool=tool, observed={"error_lines": []},
            evidence=str(self.final_path)))

    # -- plan conformance --------------------------------------------

    def _video_stream(self):
        if not self.probe:
            return None
        return next((s for s in self.probe.get("streams", [])
                     if s.get("codec_type") == "video"), None)

    def _audio_stream(self):
        if not self.probe:
            return None
        return next((s for s in self.probe.get("streams", [])
                     if s.get("codec_type") == "audio"), None)

    def _expected_canvas(self):
        if self.manifest and isinstance(self.manifest.get("canvas"), dict):
            c = self.manifest["canvas"]
            if c.get("width") and c.get("height"):
                return int(c["width"]), int(c["height"]), "manifest.canvas"
        if self.media and isinstance(self.media.get("canvas"), dict):
            c = self.media["canvas"]
            if c.get("width") and c.get("height"):
                return int(c["width"]), int(c["height"]), "media.canvas"
        return None

    def _plan_gate(self, check_id, title):
        """Shared prerequisite handling for plan-conformance checks."""
        if self.failed("inputs.plan"):
            return self.add(not_run(
                check_id, title, True,
                "inputs.plan failed (%s); there is no planned truth "
                "to validate against" % self.plan_error))
        if self.failed("artifact.probe"):
            return self.add(not_run(
                check_id, title, True,
                "artifact.probe did not pass; the artifact cannot be "
                "measured"))
        return None

    def check_dimensions(self):
        gate = self._plan_gate("plan.dimensions",
                               "final dimensions match the plan canvas")
        if gate:
            return gate
        expected = self._expected_canvas()
        if expected is None:
            return self.add(not_run(
                "plan.dimensions",
                "final dimensions match the plan canvas", True,
                "neither the manifest nor the media registry declares "
                "a canvas; the plan states no dimensions to check"))
        exp_w, exp_h, source = expected
        v = self._video_stream()
        got_w, got_h = int(v["width"]), int(v["height"])
        observed = {
            "expected": {"width": exp_w, "height": exp_h,
                         "aspect": round(exp_w / exp_h, 4),
                         "source": source},
            "observed": {"width": got_w, "height": got_h,
                         "aspect": round(got_w / got_h, 4)
                         if got_h else None},
        }
        if (got_w, got_h) != (exp_w, exp_h):
            return self.add(make_check(
                "plan.dimensions",
                "final dimensions match the plan canvas", True, FAIL,
                "artifact is %dx%d (aspect %.4f); the plan canvas is "
                "%dx%d (aspect %.4f) from %s"
                % (got_w, got_h, observed["observed"]["aspect"] or 0,
                   exp_w, exp_h, observed["expected"]["aspect"],
                   source),
                code="QC_DIMENSIONS_MISMATCH", category="MG_QC_FAILED",
                observed=observed, evidence=str(self.final_path)))
        return self.add(make_check(
            "plan.dimensions",
            "final dimensions match the plan canvas", True, PASS,
            "artifact dimensions equal the plan canvas %dx%d"
            % (exp_w, exp_h), observed=observed,
            evidence=str(self.final_path)))

    def check_fps(self):
        gate = self._plan_gate("plan.fps", "final fps matches the plan")
        if gate:
            return gate
        plan_fps = float(self.timeline["fps"])
        v = self._video_stream()
        raw = v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1"
        try:
            got = float(Fraction(raw))
        except (ValueError, ZeroDivisionError):
            got = 0.0
        observed = {"expected_fps": plan_fps, "observed_fps": got,
                    "avg_frame_rate": raw}
        if abs(got - plan_fps) > FPS_TOLERANCE:
            return self.add(make_check(
                "plan.fps", "final fps matches the plan", True, FAIL,
                "artifact runs at %s fps; the compiled plan is %s fps"
                % (raw, plan_fps), code="QC_FPS_MISMATCH",
                category="MG_QC_FAILED", observed=observed,
                evidence=str(self.final_path)))
        return self.add(make_check(
            "plan.fps", "final fps matches the plan", True, PASS,
            "artifact frame rate matches the compiled plan",
            observed=observed, evidence=str(self.final_path)))

    def check_frame_count(self):
        gate = self._plan_gate("plan.frame_count",
                               "decoded frame count matches the plan")
        if gate:
            return gate
        tool = run_tool(self._probe_argv(self.final_path,
                                         count_frames=True),
                        timeout=1800)
        if tool.error or tool.returncode != 0:
            return self.add(make_check(
                "plan.frame_count",
                "decoded frame count matches the plan", True, FAIL,
                "ffprobe -count_frames failed (exit %s): %s"
                % (tool.returncode,
                   (tool.error or tool.stderr.strip())[-400:]),
                code="QC_TOOL_ERROR", category="MG_QC_FAILED",
                tool=tool, evidence=str(self.final_path)))
        try:
            info = json.loads(tool.stdout)
            v = next(s for s in info["streams"]
                     if s.get("codec_type") == "video")
            got = int(v.get("nb_read_frames") or v.get("nb_frames") or 0)
        except (ValueError, KeyError, StopIteration, TypeError):
            return self.add(make_check(
                "plan.frame_count",
                "decoded frame count matches the plan", True, FAIL,
                "ffprobe counted no readable frames; the artifact "
                "cannot be the planned program",
                code="QC_MEDIA_CORRUPT", category="MG_QC_FAILED",
                tool=tool, evidence=str(self.final_path)))
        want = int(self.timeline["total_frames"])
        observed = {"expected_frames": want, "decoded_frames": got}
        if got != want:
            return self.add(make_check(
                "plan.frame_count",
                "decoded frame count matches the plan", True, FAIL,
                "decoded %d frames; the compiled timeline declares "
                "%d" % (got, want), code="QC_FRAME_COUNT_MISMATCH",
                category="MG_QC_FAILED", tool=tool,
                observed=observed, evidence=str(self.final_path)))
        return self.add(make_check(
            "plan.frame_count",
            "decoded frame count matches the plan", True, PASS,
            "decoded frame count equals the compiled total",
            tool=tool, observed=observed, evidence=str(self.final_path)))

    def check_duration(self):
        gate = self._plan_gate("plan.duration",
                               "final duration matches the compiled "
                               "duration")
        if gate:
            return gate
        want = int(self.timeline["total_frames"]) / float(
            self.timeline["fps"])
        raw = (self.probe.get("format") or {}).get("duration")
        try:
            got = float(raw)
        except (TypeError, ValueError):
            got = None
        observed = {"expected_seconds": round(want, 3),
                    "observed_seconds": got,
                    "tolerance_seconds": DURATION_TOLERANCE_S}
        if got is None or abs(got - want) > DURATION_TOLERANCE_S:
            return self.add(make_check(
                "plan.duration",
                "final duration matches the compiled duration", True,
                FAIL,
                "artifact duration %s differs from the compiled "
                "duration %.3fs by more than %.2fs"
                % (raw, want, DURATION_TOLERANCE_S),
                code="QC_DURATION_MISMATCH", category="MG_QC_FAILED",
                observed=observed, evidence=str(self.final_path)))
        return self.add(make_check(
            "plan.duration",
            "final duration matches the compiled duration", True, PASS,
            "artifact duration is within %.2fs of the compiled "
            "duration" % DURATION_TOLERANCE_S, observed=observed,
            evidence=str(self.final_path)))

    def _audio_expected(self):
        plan = self.audio_plan
        if plan is None:
            return None
        return bool(plan.get("narration") or plan.get("sfx")
                    or plan.get("music"))

    def check_streams(self):
        gate = self._plan_gate("plan.streams",
                               "stream inventory matches the plan")
        if gate:
            return gate
        expected_audio = self._audio_expected()
        a = self._audio_stream()
        streams = [{"index": s.get("index"),
                    "codec_type": s.get("codec_type"),
                    "codec_name": s.get("codec_name")}
                   for s in self.probe.get("streams", [])]
        observed = {"expected_audio": expected_audio,
                    "observed_audio": a is not None,
                    "audio_mode": self.audio_plan["mode"],
                    "streams": streams}
        if expected_audio and a is None:
            return self.add(make_check(
                "plan.streams", "stream inventory matches the plan",
                True, FAIL,
                "the resolved audio plan (mode %s) carries narration, "
                "sfx, or music, but the artifact has no audio stream"
                % self.audio_plan["mode"],
                code="QC_STREAM_INVENTORY_MISMATCH",
                category="MG_QC_FAILED", observed=observed,
                evidence=str(self.final_path)))
        if not expected_audio and a is not None:
            return self.add(make_check(
                "plan.streams", "stream inventory matches the plan",
                True, FAIL,
                "the resolved audio plan (mode %s) carries no audio, "
                "but the artifact has an audio stream (%s)"
                % (self.audio_plan["mode"], a.get("codec_name")),
                code="QC_STREAM_INVENTORY_MISMATCH",
                category="MG_QC_FAILED", observed=observed,
                evidence=str(self.final_path)))
        return self.add(make_check(
            "plan.streams", "stream inventory matches the plan", True,
            PASS, "stream inventory matches the resolved plan",
            observed=observed, evidence=str(self.final_path)))

    # -- audio checks --------------------------------------------------

    def _audio_gate(self, check_id, title):
        """Prerequisites shared by the decoded-audio checks."""
        if self.failed("inputs.plan"):
            return self.add(not_run(
                check_id, title, True,
                "inputs.plan failed (%s)" % self.plan_error))
        if self.failed("artifact.probe"):
            return self.add(not_run(
                check_id, title, True,
                "artifact.probe did not pass; the artifact cannot be "
                "measured"))
        return None

    def _output_pcm(self):
        """Decode the final's audio once and cache it; returns
        (samples, error_check_or_None)."""
        if self.output_samples is not None:
            return self.output_samples, None
        try:
            self.output_samples = audio_policy.decode_pcm(
                self.ffmpeg, str(self.final_path))
        except audio_policy.AudioPolicyError as exc:
            return None, exc
        return self.output_samples, None

    def check_audio_decode(self):
        title = "final audio decodes for measurement"
        if self._audio_stream() is None:
            if self.failed("artifact.probe"):
                return self.add(not_run(
                    "audio.decode", title, True,
                    "artifact.probe did not pass"))
            return self.add(skipped(
                "audio.decode", title, True,
                "the artifact has no audio stream; there is no audio "
                "to decode (plan.streams judges whether that absence "
                "is correct)",
                observed={"audio_stream": None},
                evidence=str(self.final_path)))
        gate = self._audio_gate("audio.decode", title)
        if gate:
            return gate
        samples, err = self._output_pcm()
        if err is not None:
            return self.add(make_check(
                "audio.decode", title, True, FAIL,
                "the artifact's audio could not be decoded for "
                "measurement: %s" % err.message,
                code="QC_AUDIO_MEASUREMENT_FAILED",
                category="MG_QC_FAILED",
                observed={"policy_code": err.code},
                evidence=str(self.final_path)))
        return self.add(make_check(
            "audio.decode", title, True, PASS,
            "decoded %d samples at %d Hz from the encoded artifact"
            % (len(samples), SAMPLE_RATE),
            observed={"samples": len(samples)},
            evidence=str(self.final_path)))

    def check_audio_duration(self):
        title = "audio length matches the compiled total samples"
        if self.failed("artifact.probe"):
            return self.add(not_run(
                "audio.duration", title, True,
                "artifact.probe did not pass; the artifact cannot "
                "be measured"))
        if self._audio_stream() is None:
            return self.add(skipped(
                "audio.duration", title, True,
                "no audio stream to measure; plan.streams judges "
                "whether the plan expected one",
                observed={"audio_stream": None},
                evidence=str(self.plan_path) if self.plan_path
                else None))
        gate = self._audio_gate("audio.duration", title)
        if gate:
            return gate
        if self.failed("audio.decode"):
            return self.add(not_run(
                "audio.duration", title, True,
                "audio.decode failed; the audio cannot be measured"))
        samples, _ = self._output_pcm()
        want = int(self.sidecar["total_samples"])
        tolerance = int(DURATION_TOLERANCE_S * SAMPLE_RATE)
        delta = len(samples) - want
        observed = {"expected_samples": want,
                    "decoded_samples": len(samples),
                    "delta_samples": delta,
                    "tolerance_samples": tolerance,
                    "expected_seconds": round(want / SAMPLE_RATE, 3),
                    "decoded_seconds": round(len(samples) / SAMPLE_RATE,
                                             3)}
        if abs(delta) > tolerance:
            verdict = "truncated" if delta < 0 else "overlong"
            return self.add(make_check(
                "audio.duration", title, True, FAIL,
                "the encoded audio is %s: decoded %d samples against "
                "the compiled total of %d (delta %d, tolerance %d). "
                "The comparison is against the plan, not against the "
                "video stream" % (verdict, len(samples), want, delta,
                                   tolerance),
                code="QC_AUDIO_TRUNCATED", category="MG_QC_FAILED",
                observed=observed, evidence=str(self.final_path)))
        return self.add(make_check(
            "audio.duration", title, True, PASS,
            "decoded audio length matches the compiled total samples "
            "within tolerance", observed=observed,
            evidence=str(self.final_path)))

    def check_audio_clipping(self):
        title = "encoded audio does not clip"
        if self.failed("artifact.probe"):
            return self.add(not_run(
                "audio.clipping", title, True,
                "artifact.probe did not pass; the artifact cannot "
                "be measured"))
        if self._audio_stream() is None:
            return self.add(skipped(
                "audio.clipping", title, True,
                "no audio stream; nothing can clip",
                observed={"audio_stream": None},
                evidence=str(self.plan_path) if self.plan_path
                else None))
        gate = self._audio_gate("audio.clipping", title)
        if gate:
            return gate
        if self.failed("audio.decode"):
            return self.add(not_run(
                "audio.clipping", title, True,
                "audio.decode failed; the audio cannot be measured"))
        samples, _ = self._output_pcm()
        report = audio_policy.clipping_report(samples)
        observed = {"clipping": report,
                    "ceiling_dbfs": audio_policy.OUTPUT_CLIP_CEILING_DBFS}
        if report["clipped"] or \
                report["peakDbfs"] > audio_policy.OUTPUT_CLIP_CEILING_DBFS:
            return self.add(make_check(
                "audio.clipping", title, True, FAIL,
                "encoded output peaks at %.2f dBFS (ceiling %.2f) "
                "with full-scale ratio %.6f; the same rule the "
                "assembler verifies by (MG-023)"
                % (report["peakDbfs"],
                   audio_policy.OUTPUT_CLIP_CEILING_DBFS,
                   report["fullScaleRatio"]),
                code="QC_AUDIO_CLIPPING", category="MG_QC_FAILED",
                observed=observed, evidence=str(self.final_path)))
        return self.add(make_check(
            "audio.clipping", title, True, PASS,
            "encoded output peak %.2f dBFS is under the ceiling and "
            "shows no flat-top clipping" % report["peakDbfs"],
            observed=observed, evidence=str(self.final_path)))

    def check_audio_loudness(self):
        title = "loudness verified where the mode applies"
        if self.failed("inputs.plan"):
            return self.add(not_run(
                "audio.loudness", title, True,
                "inputs.plan failed (%s); no resolved audio plan"
                % self.plan_error))
        plan = self.audio_plan
        mode = plan["mode"]
        target = plan.get("loudnessTarget")
        if mode != audio_policy.MODE_OWN:
            return self.add(skipped(
                "audio.loudness", title, True,
                "loudness is verified only for an independent final "
                "mix (MG-023 mode own); this job's mode is %s, so no "
                "loudness target exists to fail against. The mode's "
                "own promise is judged by audio.mode_promise" % mode,
                observed={"audio_mode": mode, "loudness_target": None},
                evidence=str(self.plan_path)))
        if not target:
            return self.add(skipped(
                "audio.loudness", title, True,
                "mode own but the resolved plan carries no loudness "
                "target (no narration, sfx, or music to mix)",
                observed={"audio_mode": mode, "loudness_target": None},
                evidence=str(self.plan_path)))
        if self.failed("artifact.probe"):
            return self.add(not_run(
                "audio.loudness", title, True,
                "artifact.probe did not pass; loudness cannot be "
                "measured"))
        if self._audio_stream() is None:
            return self.add(not_run(
                "audio.loudness", title, True,
                "the plan carries a loudness target but the artifact "
                "has no audio stream to measure (plan.streams judges "
                "the inventory failure)"))
        if self.failed("audio.decode"):
            return self.add(not_run(
                "audio.loudness", title, True,
                "audio.decode failed; loudness cannot be measured"))
        argv = [self.ffmpeg, "-v", "info", "-i", str(self.final_path),
                "-af", "loudnorm=I=%.2f:TP=%.2f:LRA=%.2f:"
                "print_format=json" % (target["integratedLufs"],
                                       target["truePeakDb"],
                                       audio_policy.LOUDNORM_LRA),
                "-f", "null", "-"]
        tool_holder = ToolResult(argv)
        try:
            measured = audio_policy.measure_loudness(
                self.ffmpeg, str(self.final_path), target)
        except audio_policy.AudioPolicyError as exc:
            return self.add(make_check(
                "audio.loudness", title, True, FAIL,
                "loudness measurement failed on the encoded output: "
                "%s" % exc.message, code="QC_AUDIO_MEASUREMENT_FAILED",
                category="MG_QC_FAILED", tool=tool_holder,
                observed={"policy_code": exc.code, "target": target},
                evidence=str(self.final_path)))
        verdict = audio_policy.loudness_verdict(measured, target)
        tool_holder.returncode = 0
        observed = {"measured": measured, "target": target,
                    "verdict": verdict,
                    "tolerance_lu": audio_policy.LOUDNESS_TOLERANCE_LU,
                    "tolerance_true_peak_db":
                        audio_policy.TRUE_PEAK_TOLERANCE_DB}
        if not verdict["ok"]:
            return self.add(make_check(
                "audio.loudness", title, True, FAIL,
                "encoded output measures %.2f LUFS integrated and "
                "%.2f dBTP true peak against the resolved target "
                "%.2f LUFS / %.2f dBTP (tolerance %.1f LU / %.1f dB)"
                % (measured["integratedLufs"], measured["truePeakDb"],
                   target["integratedLufs"], target["truePeakDb"],
                   audio_policy.LOUDNESS_TOLERANCE_LU,
                   audio_policy.TRUE_PEAK_TOLERANCE_DB),
                code="QC_AUDIO_LOUDNESS_OFF_TARGET",
                category="MG_QC_FAILED", tool=tool_holder,
                observed=observed, evidence=str(self.final_path)))
        return self.add(make_check(
            "audio.loudness", title, True, PASS,
            "measured loudness of the encoded output is within "
            "tolerance of the resolved target", tool=tool_holder,
            observed=observed, evidence=str(self.final_path)))

    def _media_entry_path(self, kind, ident):
        """Resolve a narration/sfx/music source path from the media
        registry, relative to the registry file (assemble.py's rule).
        Returns (path_or_None, problem_or_None)."""
        if not self.media:
            return None, ("no media registry was supplied; the "
                          "narration sources the plan places cannot "
                          "be located")
        entries = {e.get("id"): e for e in self.media.get(kind, [])
                   if isinstance(e, dict)}
        entry = entries.get(ident)
        if entry is None or not entry.get("path"):
            return None, ("media registry has no %s entry for %r"
                          % (kind, ident))
        base = Path(self.media_path).resolve().parent \
            if self.media_path else Path.cwd()
        p = Path(entry["path"])
        if not p.is_absolute():
            p = base / p
        if not p.exists():
            return None, ("narration source %s does not exist" % p)
        return p, None

    def check_audio_final_words(self):
        title = "final spoken content is present in the mix"
        if self.failed("inputs.plan"):
            return self.add(not_run(
                "audio.final_words", title, True,
                "inputs.plan failed (%s)" % self.plan_error))
        placed = self.sidecar.get("narration", [])
        if not placed:
            return self.add(skipped(
                "audio.final_words", title, True,
                "the compiled plan places no narration; there is no "
                "spoken content to verify",
                observed={"placed_narration": []},
                evidence=str(self.sidecar_path or self.plan_path)))
        if self._audio_stream() is None:
            return self.add(not_run(
                "audio.final_words", title, True,
                "the plan places narration but the artifact has no "
                "audio stream (plan.streams judges the inventory "
                "failure)"))
        if self.failed("audio.decode"):
            return self.add(not_run(
                "audio.final_words", title, True,
                "audio.decode failed; the mix cannot be measured"))
        samples, _ = self._output_pcm()
        spans = {}
        failures = []
        for seg in placed:
            src_path, problem = self._media_entry_path(
                "narration", seg["id"])
            if problem:
                return self.add(make_check(
                    "audio.final_words", title, True, FAIL,
                    "cannot verify the final spoken content: %s. "
                    "Missing evidence fails this check; it is never "
                    "assumed present" % problem,
                    code="QC_AUDIO_SOURCE_MISSING",
                    category="MG_INPUT_MISSING",
                    observed={"segment": seg["id"], "problem": problem},
                    evidence=str(self.media_path or "")))
            try:
                src = audio_policy.decode_pcm(self.ffmpeg, str(src_path))
            except audio_policy.AudioPolicyError as exc:
                return self.add(make_check(
                    "audio.final_words", title, True, FAIL,
                    "narration source %s could not be decoded for "
                    "comparison: %s" % (src_path, exc.message),
                    code="QC_AUDIO_MEASUREMENT_FAILED",
                    category="MG_QC_FAILED",
                    observed={"segment": seg["id"]},
                    evidence=str(src_path)))
            rep = audio_policy.segment_presence_report(
                samples, src, seg["startSample"],
                seg["endSampleExclusive"])
            spans[seg["id"]] = rep
            if not rep["present"]:
                failures.append(
                    "segment %s is not present in the encoded output "
                    "at its dominant bands (band ratio %.3f)"
                    % (seg["id"], rep["bandRatio"]))
        last = max(placed, key=lambda n: n["endSampleExclusive"])
        src_path, _ = self._media_entry_path("narration", last["id"])
        try:
            src = audio_policy.decode_pcm(self.ffmpeg, str(src_path))
        except audio_policy.AudioPolicyError as exc:
            return self.add(make_check(
                "audio.final_words", title, True, FAIL,
                "narration source %s could not be decoded for the "
                "final-words comparison: %s" % (src_path, exc.message),
                code="QC_AUDIO_MEASUREMENT_FAILED",
                category="MG_QC_FAILED",
                observed={"segment": last["id"], "spans": spans},
                evidence=str(src_path)))
        tail = audio_policy.narration_tail_report(
            samples, src, last["startSample"],
            last["endSampleExclusive"])
        observed = {"spans": spans, "final_segment": last["id"],
                    "final_tail": tail,
                    "method": "MG-023 band presence: Hann-windowed "
                              "band amplitudes, energy-weighted "
                              "aggregate over significant bands"}
        if failures:
            return self.add(make_check(
                "audio.final_words", title, True, FAIL,
                "; ".join(failures),
                code="QC_AUDIO_NARRATION_MISSING",
                category="MG_QC_FAILED", observed=observed,
                evidence=str(self.final_path)))
        if not tail["presentAtPlannedEnd"]:
            return self.add(make_check(
                "audio.final_words", title, True, FAIL,
                "the final narration segment %s is missing at its "
                "planned end in the encoded output (source tail "
                "%.2f dBFS, output tail %.2f dBFS, band ratio %.3f): "
                "the final words were cut or never mixed"
                % (last["id"], tail["sourceTailRmsDbfs"],
                   tail["outputTailRmsDbfs"], tail["bandRatio"]),
                code="QC_AUDIO_FINAL_WORDS_MISSING",
                category="MG_QC_FAILED", observed=observed,
                evidence=str(self.final_path)))
        return self.add(make_check(
            "audio.final_words", title, True, PASS,
            "every placed narration segment is present at its "
            "dominant bands, and the final segment is still present "
            "at its planned end", observed=observed,
            evidence=str(self.final_path)))

    def check_audio_score(self):
        title = "the chosen score is audible where nothing speaks"
        if self.failed("inputs.plan"):
            return self.add(not_run(
                "audio.score_audible", title, True,
                "inputs.plan failed (%s)" % self.plan_error))
        plan = self.audio_plan
        music = plan.get("music")
        if plan["mode"] != audio_policy.MODE_OWN or not music:
            return self.add(skipped(
                "audio.score_audible", title, True,
                "no own-mode score to verify (mode %s, music %s)"
                % (plan["mode"], bool(music)),
                observed={"audio_mode": plan["mode"],
                          "music": music},
                evidence=str(self.plan_path)))
        if self.failed("audio.decode"):
            return self.add(not_run(
                "audio.score_audible", title, True,
                "audio.decode failed; the mix cannot be measured"))
        if music.get("kind") == "supplied":
            base = Path(self.media_path).resolve().parent \
                if self.media_path else Path.cwd()
            music_path = Path(music["path"])
            if not music_path.is_absolute():
                music_path = base / music_path
            if not music_path.exists():
                return self.add(make_check(
                    "audio.score_audible", title, True, FAIL,
                    "the resolved score source %s does not exist; "
                    "its audibility cannot be verified"
                    % music_path, code="QC_AUDIO_SOURCE_MISSING",
                    category="MG_INPUT_MISSING",
                    observed={"music": music},
                    evidence=str(music_path)))
        else:
            return self.add(skipped(
                "audio.score_audible", title, True,
                "the score is synthesized at assembly time and no "
                "source file survives in the registry to compare "
                "against; the assembler's own record covers it",
                observed={"music": music}, evidence=str(self.plan_path)))
        samples, _ = self._output_pcm()
        src = audio_policy.decode_pcm(self.ffmpeg, str(music_path))
        ranges = [(n["startSample"], n["endSampleExclusive"])
                  for n in self.sidecar.get("narration", [])]
        rep = audio_policy.score_audibility_report(
            samples, ranges, int(self.sidecar["total_samples"]),
            audio_policy.rms_dbfs(src), plan["mix"]["musicVolume"])
        if rep["applicable"] and not rep["audible"]:
            return self.add(make_check(
                "audio.score_audible", title, True, FAIL,
                "the chosen score is not audible in the "
                "narration-free window %s (measured %.2f dBFS, "
                "expected about %.2f dBFS)"
                % (rep["windowSeconds"], rep["windowRmsDbfs"],
                   rep["expectedRmsDbfs"]),
                code="QC_AUDIO_SCORE_NOT_AUDIBLE",
                category="MG_QC_FAILED", observed={"report": rep},
                evidence=str(self.final_path)))
        return self.add(make_check(
            "audio.score_audible", title, True, PASS,
            "score audibility verified by MG-023's narration-free "
            "window measurement", observed={"report": rep},
            evidence=str(self.final_path)))

    def check_audio_mode_promise(self):
        title = "the artifact keeps its audio mode's promise"
        if self.failed("inputs.plan"):
            return self.add(not_run(
                "audio.mode_promise", title, True,
                "inputs.plan failed (%s)" % self.plan_error))
        if self.failed("artifact.probe"):
            return self.add(not_run(
                "audio.mode_promise", title, True,
                "artifact.probe did not pass"))
        mode = self.audio_plan["mode"]
        a = self._audio_stream()
        observed = {"audio_mode": mode, "audio_stream_present":
                    a is not None, "exclusions":
                    self.audio_plan.get("exclusions", [])}
        if mode == audio_policy.MODE_OWN:
            return self.add(skipped(
                "audio.mode_promise", title, True,
                "mode own makes its promises through the loudness, "
                "clipping, narration, and score checks; there is no "
                "separate silence or inheritance promise to judge",
                observed=observed, evidence=str(self.plan_path)))
        if mode == audio_policy.MODE_NONE:
            if a is not None:
                return self.add(make_check(
                    "audio.mode_promise", title, True, FAIL,
                    "mode none promises a silent deliverable, but "
                    "the artifact carries an audio stream (%s)"
                    % a.get("codec_name"),
                    code="QC_AUDIO_MODE_VIOLATION",
                    category="MG_MODE_MISMATCH", observed=observed,
                    evidence=str(self.final_path)))
            return self.add(make_check(
                "audio.mode_promise", title, True, PASS,
                "mode none: the deliverable is silent, as promised "
                "(no audio stream)", observed=observed,
                evidence=str(self.final_path)))
        # inherited: the parent owns the soundtrack; the insert must
        # not carry a bed of its own (a duplicated bed under the
        # parent's program is the failure this mode exists to avoid).
        if a is None:
            return self.add(make_check(
                "audio.mode_promise", title, True, PASS,
                "mode inherited: the insert carries no audio, so the "
                "parent soundtrack cannot be duplicated",
                observed=observed, evidence=str(self.final_path)))
        if self.failed("audio.decode"):
            return self.add(not_run(
                "audio.mode_promise", title, True,
                "audio.decode failed; the carried stream cannot be "
                "measured for silence"))
        samples, _ = self._output_pcm()
        rms = audio_policy.rms_dbfs(samples)
        observed["carried_stream_rms_dbfs"] = round(rms, 2)
        observed["silence_threshold_dbfs"] = audio_policy.SILENCE_DBFS
        if rms > audio_policy.SILENCE_DBFS:
            return self.add(make_check(
                "audio.mode_promise", title, True, FAIL,
                "mode inherited: the insert carries audible audio "
                "(%.2f dBFS RMS); the parent owns the soundtrack, so "
                "this bed would be duplicated under the parent's "
                "program" % rms,
                code="QC_AUDIO_PARENT_BED_DUPLICATED",
                category="MG_MODE_MISMATCH", observed=observed,
                evidence=str(self.final_path)))
        return self.add(make_check(
            "audio.mode_promise", title, True, PASS,
            "mode inherited: the carried stream measures silent "
            "(%.2f dBFS RMS), so nothing is duplicated" % rms,
            observed=observed, evidence=str(self.final_path)))

    # -- approved intervals --------------------------------------------

    def approved_intervals(self):
        """Derive the plan-approved dark and frozen intervals from
        plan data only. Returns (dark, freeze, sources) where dark
        and freeze are [start, end) frame interval lists and sources
        names every document consulted. Nothing here is a hardcoded
        exemption: no document, no approval."""
        dark, freeze, sources = [], [], []
        tl = self.timeline or {}
        scenes = {s["id"]: s for s in tl.get("scenes", [])}
        # Timeline hold_start events: a hold the compiler placed is
        # an approved freeze from the event frame to the scene end.
        for ev in tl.get("events", []):
            if ev.get("type") == "hold_start":
                scene = scenes.get(ev.get("scene_id"))
                if scene:
                    freeze.append((int(ev["frame"]),
                                   int(scene["end_frame_exclusive"])))
                    sources.append(
                        "timeline event %s (hold_start at frame %s, "
                        "scene %s)" % (ev.get("id"), ev["frame"],
                                       ev.get("scene_id")))
        # Scene-spec motion holds, mapped from source frames to
        # placed frames through the sidecar ranges.
        side_scenes = {}
        if self.sidecar:
            side_scenes = {s["id"]: s
                           for s in self.sidecar.get("scenes", [])}
        spec_docs = self._scene_specs()
        for spec in spec_docs:
            motion = spec.get("motion") or {}
            end = motion.get("end_frame_exclusive")
            hold_to = motion.get("hold_to_frame_exclusive")
            sid = spec.get("id")
            if end is None or hold_to is None or hold_to <= end:
                continue
            ss = side_scenes.get(sid)
            if not ss:
                continue
            placed0 = ss["placedRange"]["startFrame"]
            src0 = ss["sourceRange"]["startFrame"]
            freeze.append((placed0 + (int(end) - src0),
                           placed0 + (int(hold_to) - src0)))
            sources.append(
                "scene spec %s motion hold (source frames %s..%s)"
                % (sid, end, hold_to))
        # Planner-declared intentional stillness: a beat whose
        # planner entry says the stillness is intentional, with a
        # reason, approves a freeze over that beat's scene range.
        planner, storyboard = self._planner_and_storyboard()
        if planner and storyboard:
            beats = {b.get("id"): b
                     for b in storyboard.get("beats", [])}
            for pb in planner.get("beats", []):
                if pb.get("intentional_stillness") and \
                        pb.get("stillness_reason"):
                    beat = beats.get(pb.get("beat_id"))
                    scene = scenes.get((beat or {}).get("scene_id"))
                    if scene:
                        freeze.append(
                            (int(scene["start_frame"]),
                             int(scene["end_frame_exclusive"])))
                        sources.append(
                            "planner beat %s: intentional stillness "
                            "(%s)" % (pb.get("beat_id"),
                                      pb.get("stillness_reason")))
        # The job's explicit declaration file: dark beats, frozen
        # beats, and silent dark beats named by the plan package.
        decl_path = self._approved_intervals_path()
        if decl_path and decl_path.exists():
            try:
                decl = load_json(decl_path)
                entries = decl.get("intervals", decl) \
                    if isinstance(decl, dict) else decl
                for entry in entries:
                    kinds = entry.get("kinds") or [entry.get("kind")]
                    rng = (int(entry["start_frame"]),
                           int(entry["end_frame_exclusive"]))
                    label = ("approved-intervals %s (reason: %s; "
                             "source: %s)"
                             % (decl_path.name,
                                entry.get("reason"),
                                entry.get("source")))
                    if "dark" in kinds or "silent_dark" in kinds:
                        dark.append(rng)
                        sources.append(label + " [dark]")
                    if "freeze" in kinds or "silent_dark" in kinds:
                        freeze.append(rng)
                        sources.append(label + " [freeze]")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                sources.append(
                    "approved-intervals file %s could not be read "
                    "(%s); its approvals are NOT honored"
                    % (decl_path, exc))
        return sorted(dark), sorted(freeze), sources

    def _scene_specs(self):
        docs = []
        if self.job_dir:
            scenes_dir = self.job_dir / "scenes"
            if scenes_dir.is_dir():
                for p in sorted(scenes_dir.glob("*.json")):
                    try:
                        docs.append(load_json(p))
                    except (OSError, ValueError):
                        pass
        return docs

    def _planner_and_storyboard(self):
        planner = storyboard = None
        candidates = []
        if self.args.planner:
            candidates.append(Path(self.args.planner))
        if self.job_dir:
            candidates.append(self.job_dir / "planner.json")
        for cand in candidates:
            if cand and cand.exists():
                try:
                    planner = load_json(cand)
                except (OSError, ValueError):
                    planner = None
                break
        sb_path = self._job_file(self.args.storyboard, "storyboard.json")
        if sb_path and sb_path.exists():
            try:
                storyboard = load_json(sb_path)
            except (OSError, ValueError):
                storyboard = None
        if planner is not None and storyboard is None and self.job_dir:
            sibling = self.job_dir / "storyboard.json"
            if sibling.exists():
                try:
                    storyboard = load_json(sibling)
                except (OSError, ValueError):
                    storyboard = None
        return planner, storyboard

    def _approved_intervals_path(self):
        if self.args.approved_intervals:
            return Path(self.args.approved_intervals)
        if self.job_dir:
            p = self.job_dir / "qc-approved-intervals.json"
            if p.exists():
                return p
        legacy_manifest = getattr(self.args, "legacy_manifest", None)
        if legacy_manifest:
            for base in (Path(legacy_manifest).resolve().parent,
                         Path(self.args.workdir)
                         if self.args.workdir else None):
                if base:
                    p = base / "qc-approved-intervals.json"
                    if p.exists():
                        return p
        return None

    # -- video sweeps ----------------------------------------------------

    def _sweep_gate(self, check_id, title):
        if self.failed("tools.available"):
            return self.add(not_run(
                check_id, title, True,
                "tools.available failed; ffmpeg cannot run"))
        if self.failed("artifact.probe"):
            return self.add(not_run(
                check_id, title, True,
                "artifact.probe did not pass; the sweep has no "
                "readable artifact"))
        if self.failed("inputs.plan"):
            return self.add(not_run(
                check_id, title, True,
                "inputs.plan failed (%s); detected intervals could "
                "not be judged against plan approvals"
                % self.plan_error))
        return None

    def check_black(self):
        title = "no unapproved black intervals"
        gate = self._sweep_gate("video.black", title)
        if gate:
            return gate
        fps = float(self.timeline["fps"])
        argv = [self.ffmpeg, "-i", str(self.final_path), "-vf",
                "blackdetect=d=%.2f:pix_th=%.2f"
                % (BLACK_MIN_SECONDS, BLACK_PIXEL_THRESHOLD),
                "-an", "-f", "null", "-"]
        tool = run_tool(argv, timeout=1800)
        if tool.error or tool.returncode != 0:
            return self.add(make_check(
                "video.black", title, True, FAIL,
                "the blackdetect sweep itself failed (exit %s): %s. "
                "A failed sweep is a failed check, never a clean one"
                % (tool.returncode,
                   (tool.error or tool.stderr.strip())[-400:]),
                code="QC_TOOL_ERROR", category="MG_QC_FAILED",
                tool=tool, evidence=str(self.final_path)))
        detected = []
        for m in re.finditer(
                r"black_start:([\d.]+)\s+black_end:([\d.]+)",
                tool.stderr):
            detected.append((seconds_to_frames(float(m.group(1)), fps),
                             seconds_to_frames(float(m.group(2)), fps)))
        dark_approvals, _, sources = self.approved_intervals()
        uncovered = [(s, e) for s, e in
                     subtract_approvals(detected, dark_approvals)
                     if e - s >= seconds_to_frames(BLACK_MIN_SECONDS,
                                                   fps) - 1]
        observed = {
            "detected_intervals_frames": detected,
            "approved_dark_intervals_frames": dark_approvals,
            "approval_sources": sources,
            "uncovered_intervals_frames": uncovered,
            "threshold": {"min_seconds": BLACK_MIN_SECONDS,
                          "pixel_threshold": BLACK_PIXEL_THRESHOLD},
        }
        if uncovered:
            return self.add(make_check(
                "video.black", title, True, FAIL,
                "black interval(s) %s are not approved by any plan "
                "data (approvals consulted: %s)"
                % (uncovered, sources or "none"),
                code="QC_BLACK_UNAPPROVED", category="MG_QC_FAILED",
                tool=tool, observed=observed,
                evidence=str(self.final_path)))
        return self.add(make_check(
            "video.black", title, True, PASS,
            "no unapproved black intervals (%d detected, all covered "
            "by plan approvals)" % len(detected)
            if detected else "no black intervals detected",
            tool=tool, observed=observed, evidence=str(self.final_path)))

    def check_freeze(self):
        title = "no unapproved frozen intervals"
        gate = self._sweep_gate("video.freeze", title)
        if gate:
            return gate
        fps = float(self.timeline["fps"])
        argv = [self.ffmpeg, "-i", str(self.final_path), "-vf",
                "freezedetect=n=%s:d=%.2f"
                % (FREEZE_NOISE, FREEZE_MIN_SECONDS),
                "-an", "-f", "null", "-"]
        tool = run_tool(argv, timeout=1800)
        if tool.error or tool.returncode != 0:
            return self.add(make_check(
                "video.freeze", title, True, FAIL,
                "the freezedetect sweep itself failed (exit %s): %s. "
                "A failed sweep is a failed check, never a clean one"
                % (tool.returncode,
                   (tool.error or tool.stderr.strip())[-400:]),
                code="QC_TOOL_ERROR", category="MG_QC_FAILED",
                tool=tool, evidence=str(self.final_path)))
        starts = [float(x) for x in re.findall(
            r"freeze_start:\s*([\d.]+)", tool.stderr)]
        ends = [float(x) for x in re.findall(
            r"freeze_end:\s*([\d.]+)", tool.stderr)]
        detected = []
        for i, s in enumerate(starts):
            e = ends[i] if i < len(ends) else float(
                self.timeline["total_frames"]) / fps
            detected.append((seconds_to_frames(s, fps),
                             seconds_to_frames(e, fps)))
        _, freeze_approvals, sources = self.approved_intervals()
        uncovered = [(s, e) for s, e in
                     subtract_approvals(detected, freeze_approvals)
                     if e - s >= seconds_to_frames(FREEZE_MIN_SECONDS,
                                                   fps) - 1]
        observed = {
            "detected_intervals_frames": detected,
            "approved_freeze_intervals_frames": freeze_approvals,
            "approval_sources": sources,
            "uncovered_intervals_frames": uncovered,
            "threshold": {"min_seconds": FREEZE_MIN_SECONDS,
                          "noise": FREEZE_NOISE},
        }
        if uncovered:
            return self.add(make_check(
                "video.freeze", title, True, FAIL,
                "frozen interval(s) %s are not approved by any plan "
                "data (approvals consulted: %s)"
                % (uncovered, sources or "none"),
                code="QC_FREEZE_UNAPPROVED", category="MG_QC_FAILED",
                tool=tool, observed=observed,
                evidence=str(self.final_path)))
        return self.add(make_check(
            "video.freeze", title, True, PASS,
            "no unapproved frozen intervals (%d detected, all "
            "covered by plan approvals)" % len(detected)
            if detected else "no frozen intervals detected",
            tool=tool, observed=observed, evidence=str(self.final_path)))

    def _declared_profile(self):
        if self.manifest:
            delivery = self.manifest.get("delivery") or {}
            if delivery.get("video_profile"):
                return delivery["video_profile"], "manifest.delivery"
        if self.media:
            for key in ("delivery", "export"):
                rec = self.media.get(key)
                if isinstance(rec, dict) and rec.get("video_profile"):
                    return rec["video_profile"], "media.%s" % key
        if self.timeline:
            for key in ("video_profile", "export_profile"):
                if self.timeline.get(key):
                    return self.timeline[key], "timeline.%s" % key
        return None, None

    def check_alpha(self):
        title = "alpha matches the declared export profile"
        if self.failed("inputs.plan"):
            return self.add(not_run(
                "video.alpha", title, True,
                "inputs.plan failed (%s)" % self.plan_error))
        if self.failed("artifact.probe"):
            return self.add(not_run(
                "video.alpha", title, True,
                "artifact.probe did not pass"))
        profile, source = self._declared_profile()
        if not profile:
            return self.add(skipped(
                "video.alpha", title, True,
                "no export profile is declared in the manifest, "
                "media registry, or timeline, so no alpha claim "
                "exists to verify (MG-040 profile names are consumed "
                "when a profile is declared)",
                observed={"video_profile": None},
                evidence=str(self.plan_path)))
        v = self._video_stream()
        pix_fmt = v.get("pix_fmt") or ""
        has_alpha_fmt = any(pix_fmt.startswith(p) or pix_fmt == p
                            for p in ALPHA_PIXEL_FORMATS)
        observed = {"video_profile": profile, "profile_source": source,
                    "pix_fmt": pix_fmt, "alpha_pixel_format":
                    has_alpha_fmt}
        # Measure the alpha plane on three sampled frames when the
        # format carries one: a claimed-alpha artifact whose alpha
        # is a single constant value is opaque in fact.
        alpha_stats = None
        tool = None
        if has_alpha_fmt:
            total = int(self.timeline["total_frames"])
            frames = sorted({max(0, int(total * f) - 1)
                             for f in (0.1, 0.5, 0.9)})
            sel = "+".join("eq(n\\,%d)" % f for f in frames)
            argv = [self.ffmpeg, "-v", "error", "-i",
                    str(self.final_path), "-vf",
                    "select='%s',extractplanes=a,format=gray" % sel,
                    "-vsync", "0", "-f", "rawvideo", "-"]
            # Raw pixel bytes: this one invocation must run in
            # bytes mode, not through the text-mode run_tool.
            tool = ToolResult(argv)
            raw = b""
            try:
                proc = subprocess.run(argv, capture_output=True,
                                      timeout=600)
                tool.returncode = proc.returncode
                tool.stderr = proc.stderr.decode(errors="replace")
                raw = proc.stdout or b""
            except FileNotFoundError:
                tool.error = "tool not found: %s" % argv[0]
            except subprocess.TimeoutExpired:
                tool.error = "timed out after 600s"
            except OSError as exc:
                tool.error = "could not start: %s" % exc
            if tool.error or tool.returncode != 0 or not raw:
                return self.add(make_check(
                    "video.alpha", title, True, FAIL,
                    "the alpha plane could not be extracted for "
                    "measurement (exit %s): %s"
                    % (tool.returncode,
                       (tool.error or tool.stderr.strip())[-300:]),
                    code="QC_TOOL_ERROR", category="MG_QC_FAILED",
                    tool=tool, observed=observed,
                    evidence=str(self.final_path)))
            alpha_stats = {"min": min(raw), "max": max(raw),
                           "bytes": len(raw)}
            observed["alpha_plane_sample"] = alpha_stats
        varying = bool(alpha_stats and
                       alpha_stats["min"] < alpha_stats["max"])
        observed["alpha_varies"] = varying
        claims_alpha = profile in ALPHA_PROFILES
        if claims_alpha and not (has_alpha_fmt and varying):
            return self.add(make_check(
                "video.alpha", title, True, FAIL,
                "profile %s (from %s) claims alpha, but the artifact "
                "pix_fmt %s %s" % (
                    profile, source, pix_fmt,
                    "has no alpha plane" if not has_alpha_fmt else
                    "has an alpha plane that never varies "
                    "(min %s, max %s): the file is opaque in fact"
                    % (alpha_stats["min"], alpha_stats["max"])),
                code="QC_ALPHA_MISMATCH", category="MG_QC_FAILED",
                tool=tool, observed=observed,
                evidence=str(self.final_path)))
        if not claims_alpha and varying:
            return self.add(make_check(
                "video.alpha", title, True, FAIL,
                "profile %s (from %s) declares an opaque deliverable, "
                "but the artifact carries genuinely varying alpha "
                "(sampled min %s, max %s): the file is mislabeled "
                "for its profile" % (profile, source,
                                      alpha_stats["min"],
                                      alpha_stats["max"]),
                code="QC_ALPHA_MISMATCH", category="MG_QC_FAILED",
                tool=tool, observed=observed,
                evidence=str(self.final_path)))
        return self.add(make_check(
            "video.alpha", title, True, PASS,
            "artifact alpha agrees with profile %s" % profile,
            tool=tool, observed=observed, evidence=str(self.final_path)))

    # -- review receipt and package evidence -------------------------

    def _find_coverage_record(self):
        """Locate the MG-031 coverage record for this job. Returns
        (path_or_None, bundle_dirs_seen)."""
        args = self.args
        if args.coverage:
            p = Path(args.coverage)
            if p.is_dir():
                named = sorted(p.glob("*__coverage.json"))
                if named:
                    return named[0], [p]
                plain = p / "coverage.json"
                return (plain if plain.exists() else None), [p]
            return (p if p.exists() else None), []
        seen_dirs = []
        roots = []
        if self.job_dir:
            roots += [self.job_dir / "review", self.job_dir]
        job_id = (self.timeline or {}).get("job_id")
        for root in roots:
            if not root.is_dir():
                continue
            named = sorted(root.rglob("*__coverage.json"))
            for cand in named:
                if job_id and job_id in cand.name:
                    return cand, seen_dirs
            if named:
                return named[0], seen_dirs
            plain = root / "coverage.json"
            if plain.exists():
                return plain, seen_dirs
            if root.name == "review":
                seen_dirs.append(root)
        return None, seen_dirs

    def check_review_receipt(self):
        title = "review receipt (MG-031 coverage) binds this artifact"
        if self.failed("inputs.plan"):
            return self.add(not_run(
                "review.receipt", title, True,
                "inputs.plan failed (%s); the receipt cannot be "
                "matched to a job" % self.plan_error))
        if self.failed("artifact.hash"):
            return self.add(not_run(
                "review.receipt", title, True,
                "artifact.hash did not run; there is no artifact hash "
                "for a receipt to bind"))
        path, bundle_dirs = self._find_coverage_record()
        job_id = self.timeline.get("job_id")
        if path is None:
            hint = ""
            if bundle_dirs:
                hint = (" A review bundle directory exists at %s "
                        "but holds no coverage record: the bundle "
                        "build failed or never completed, so no "
                        "review evidence exists."
                        % bundle_dirs[0])
            return self.add(make_check(
                "review.receipt", title, True, FAIL,
                "no MG-031 coverage record found for job %s.%s An "
                "absent review receipt fails the gate: a final "
                "artifact without complete review coverage must not "
                "be scored or delivered" % (job_id, hint),
                code="QC_REVIEW_RECEIPT_MISSING",
                category="MG_INPUT_MISSING",
                observed={"searched_job_dir":
                          str(self.job_dir) if self.job_dir else None,
                          "bundle_dirs_seen":
                          [str(d) for d in bundle_dirs]}))
        try:
            record = load_json(path)
        except (OSError, ValueError) as exc:
            return self.add(make_check(
                "review.receipt", title, True, FAIL,
                "coverage record %s does not parse: %s" % (path, exc),
                code="QC_REVIEW_RECORD_INVALID",
                category="MG_SCHEMA_INVALID",
                observed={"coverage_path": str(path)},
                evidence=str(path)))
        self._record_input("coverage", path)
        observed = {"coverage_path": str(path),
                    "record_job_id": record.get("job_id"),
                    "verdict": record.get("verdict"),
                    "record_video": record.get("video")}
        if record.get("job_id") != job_id:
            return self.add(make_check(
                "review.receipt", title, True, FAIL,
                "coverage record names job %r; this job is %r. A "
                "receipt for another job is not evidence about this "
                "artifact" % (record.get("job_id"), job_id),
                code="QC_REVIEW_FOREIGN_JOB",
                category="MG_FOREIGN_JOB", observed=observed,
                evidence=str(path)))
        verdict = record.get("verdict")
        if verdict != "complete":
            code = "QC_REVIEW_BUNDLE_FAILED" if verdict == "failed" \
                else "QC_REVIEW_INCOMPLETE"
            return self.add(make_check(
                "review.receipt", title, True, FAIL,
                "the MG-031 coverage verdict is %r, not complete: %s "
                "A bundle whose verdict is not complete must not be "
                "scored, and every check that would stand on the "
                "review has no passing record"
                % (verdict, record.get("findings") or
                   "no findings recorded"),
                code=code, category="MG_COVERAGE_INCOMPLETE",
                observed=observed, evidence=str(path)))
        video = record.get("video") or {}
        if video.get("sha256") != self.artifact_sha256:
            return self.add(make_check(
                "review.receipt", title, True, FAIL,
                "the coverage record binds video sha256 %s, but the "
                "artifact under review hashes to %s: the review "
                "covered different bytes"
                % (video.get("sha256"), self.artifact_sha256),
                code="QC_REVIEW_HASH_MISMATCH",
                category="MG_HASH_MISMATCH", observed=observed,
                evidence=str(path)))
        inputs = record.get("inputs") or {}
        timeline_ref = inputs.get("timeline") or {}
        if timeline_ref.get("sha256") and self.plan_standalone \
                and self.plan_path and Path(self.plan_path).exists():
            plan_sha = sha256_file(self.plan_path)
            if timeline_ref["sha256"] != plan_sha:
                return self.add(make_check(
                    "review.receipt", title, True, FAIL,
                    "the coverage record was built against timeline "
                    "sha256 %s, but the plan under review hashes to "
                    "%s" % (timeline_ref["sha256"], plan_sha),
                    code="QC_REVIEW_HASH_MISMATCH",
                    category="MG_HASH_MISMATCH", observed=observed,
                    evidence=str(path)))
        review_ref = inputs.get("review_record") or {}
        explicit_review = None
        if self.args.review_record:
            try:
                explicit_review = load_json(self.args.review_record)
            except (OSError, ValueError):
                explicit_review = None
        rough = review_ref.get("rough_layout_only")
        if rough is None and explicit_review is not None:
            rough = explicit_review.get(
                "rough_layout_only",
                explicit_review.get("roughLayoutOnly"))
        label = review_ref.get("label") or (
            explicit_review or {}).get("label")
        observed["review_record"] = {
            "label": label, "rough_layout_only": bool(rough),
            "engine": review_ref.get("engine")}
        if rough:
            return self.add(make_check(
                "review.receipt", title, True, FAIL,
                "the bound review record is labeled %r with "
                "rough_layout_only set: rough layout evidence cannot "
                "stand as the review receipt for a final artifact "
                "(MG-031 records it honestly; this gate refuses to "
                "upgrade it)" % label,
                code="QC_REVIEW_ROUGH_ONLY", category="MG_QC_FAILED",
                observed=observed, evidence=str(path)))
        return self.add(make_check(
            "review.receipt", title, True, PASS,
            "coverage record for job %s is complete and binds the "
            "artifact's exact sha256" % job_id, observed=observed,
            evidence=str(path)))

    def _assets_doc(self):
        """The package assets record: explicit --assets, else the
        manifest's assets reference inside the job package."""
        if self.args.assets:
            p = Path(self.args.assets)
            return (p, load_json(p)) if p.exists() else (p, None)
        if self.manifest and self.job_dir:
            ref = self.manifest.get("assets")
            if isinstance(ref, str):
                p = self.job_dir / ref
                if p.exists():
                    return p, load_json(p)
            p = self.job_dir / "assets.json"
            if p.exists():
                return p, load_json(p)
        return None, None

    def check_assets(self):
        title = "declared assets are present and hash-true"
        path, doc = (None, None)
        try:
            path, doc = self._assets_doc()
        except (OSError, ValueError) as exc:
            return self.add(make_check(
                "package.assets", title, True, FAIL,
                "assets record does not parse: %s" % exc,
                code="QC_SCHEMA_INVALID", category="MG_SCHEMA_INVALID"))
        if doc is None:
            if self.job_dir:
                return self.add(make_check(
                    "package.assets", title, True, FAIL,
                    "the job package declares no readable assets "
                    "record; asset completion cannot be proven",
                    code="QC_INPUT_MISSING",
                    category="MG_INPUT_MISSING",
                    observed={"looked_for": "manifest assets ref or "
                              "assets.json in the job package"}))
            return self.add(skipped(
                "package.assets", title, True,
                "no assets record in scope (plan mode without a job "
                "package); asset completion is a package-level "
                "promise and is checked in package mode"))
        self._record_input("assets", path)
        base = Path(path).resolve().parent
        per_asset = []
        failures = []
        for entry in doc.get("assets", []):
            rel = entry.get("path")
            ident = entry.get("id")
            target = base / rel if rel else None
            if target is None or not target.exists():
                per_asset.append({"id": ident, "path": rel,
                                  "status": "missing"})
                failures.append("asset %s (%s) is missing"
                                % (ident, rel))
                continue
            got_sha = sha256_file(target)
            want_sha = entry.get("sha256")
            ok = want_sha is None or got_sha == want_sha
            per_asset.append({"id": ident, "path": rel,
                              "status": "verified" if ok
                              else "hash_mismatch",
                              "sha256": got_sha})
            if not ok:
                failures.append(
                    "asset %s hashes to %s; the record declares %s"
                    % (ident, got_sha, want_sha))
        observed = {"assets": per_asset, "assets_path": str(path)}
        if failures:
            code = "QC_ASSET_HASH_MISMATCH" if any(
                a["status"] == "hash_mismatch" for a in per_asset) \
                else "QC_ASSET_MISSING"
            category = "MG_HASH_MISMATCH" if code.endswith(
                "HASH_MISMATCH") else "MG_INPUT_MISSING"
            return self.add(make_check(
                "package.assets", title, True, FAIL,
                "; ".join(failures), code=code, category=category,
                observed=observed, evidence=str(path)))
        return self.add(make_check(
            "package.assets", title, True, PASS,
            "all %d declared assets are present and hash-true"
            % len(per_asset), observed=observed, evidence=str(path)))

    def check_fonts(self):
        title = "declared fonts resolve without substitution"
        try:
            path, doc = self._assets_doc()
        except (OSError, ValueError):
            path, doc = None, None
        requirements = (doc or {}).get("font_requirements") or []
        if not requirements:
            return self.add(skipped(
                "package.fonts", title, True,
                "the assets record declares no font requirements; "
                "there is no font promise to verify",
                observed={"font_requirements": []},
                evidence=str(path) if path else None))
        base = Path(path).resolve().parent if path else Path.cwd()
        assets_by_id = {a.get("id"): a
                        for a in (doc or {}).get("assets", [])}
        # The installed family set, from fontconfig. A declared
        # name that is not in this set is an alias token and
        # resolves through the shipped runtime registry (see
        # load_font_alias_registry), never by comparing the raw
        # token here.
        fc = run_tool(["fc-list", ":", "family"], timeout=60)
        families = None
        if not fc.error and fc.returncode == 0:
            families = set()
            for line in fc.stdout.splitlines():
                for fam in line.split(","):
                    families.add(fam.strip().lower())
        per_font = []
        failures = []
        registry_failures = []
        not_run_reason = None
        # The runtime alias registry, loaded lazily the first
        # time a requirement declares a name fontconfig does not
        # know: an alias token resolves the way the runtime
        # resolves it, or the check fails by name.
        registry_path = font_registry_path()
        registry = {"loaded": False, "mapping": None,
                    "problem": None}

        def alias_registry():
            if not registry["loaded"]:
                registry["loaded"] = True
                mapping, problem = load_font_alias_registry(
                    registry_path)
                registry["mapping"] = mapping
                registry["problem"] = problem
            return registry

        for req in requirements:
            ident = req.get("id")
            alias = req.get("family_alias")
            source = req.get("source")
            if source == "package":
                entry = assets_by_id.get(ident)
                target = base / entry["path"] \
                    if entry and entry.get("path") else None
                ok = bool(target and target.exists())
                per_font.append({"id": ident, "family_alias": alias,
                                 "source": source,
                                 "status": "resolved_package_file"
                                 if ok else "missing_package_file"})
                if not ok:
                    failures.append(
                        "font requirement %s is package-sourced but "
                        "no font asset with that id exists" % ident)
                continue
            if families is None:
                not_run_reason = ("fontconfig (fc-list) is "
                                  "unavailable: %s; runtime-registry "
                                  "font resolution cannot be proven"
                                  % (fc.error or "exit %s"
                                     % fc.returncode))
                per_font.append({"id": ident, "family_alias": alias,
                                 "source": source,
                                 "status": "not_checked"})
                continue
            if isinstance(alias, str) and alias.strip() \
                    and alias.strip().lower() in families:
                # The declared name is itself an installed
                # family (a package may declare the resolved
                # family directly): no alias resolution needed.
                per_font.append({
                    "id": ident, "family_alias": alias,
                    "source": source, "status": "resolved",
                    "resolution": "installed_family",
                    "declared_family": alias,
                    "resolved_family": alias})
                continue
            # The declared name is not an installed family, so
            # it is an alias token: resolve it through the
            # shipped runtime registry, by exact name, the way
            # the runtime's own lookup does.
            reg = alias_registry()
            if reg["problem"] is not None:
                per_font.append({
                    "id": ident, "family_alias": alias,
                    "source": source,
                    "status": "registry_unreadable",
                    "declared_family": alias,
                    "registry_source": str(registry_path),
                    "registry_problem": reg["problem"]})
                registry_failures.append(
                    "font requirement %s declares %r, which is "
                    "not an installed family, so it must resolve "
                    "as an alias through the runtime font "
                    "registry at %s; that registry %s, so alias "
                    "resolution cannot be proven"
                    % (ident, alias, registry_path,
                       reg["problem"]))
                continue
            mapping = reg["mapping"]
            if not isinstance(alias, str) \
                    or alias not in mapping:
                per_font.append({
                    "id": ident, "family_alias": alias,
                    "source": source, "status": "unresolved",
                    "resolution": "unknown_alias",
                    "declared_family": alias,
                    "registry_source": str(registry_path)})
                failures.append(
                    "font requirement %s (family %r, substitution "
                    "%s) is not an installed family and the "
                    "runtime font registry at %s has no alias "
                    "registered under that name; the runtime "
                    "would refuse to render it rather than "
                    "substitute a different face"
                    % (ident, alias, req.get("substitution"),
                       registry_path))
                continue
            resolved_family = mapping[alias]
            entry = {
                "id": ident, "family_alias": alias,
                "source": source,
                "resolution": "runtime_registry_alias",
                "declared_family": alias,
                "resolved_family": resolved_family,
                "registry_source": str(registry_path)}
            if resolved_family.strip().lower() in families:
                entry["status"] = "resolved"
            else:
                entry["status"] = "resolved_family_not_installed"
                failures.append(
                    "font requirement %s declares alias %r, "
                    "which the runtime font registry resolves "
                    "to family %r, but that family is not "
                    "installed; fontconfig would substitute a "
                    "different face"
                    % (ident, alias, resolved_family))
            per_font.append(entry)
        observed = {"fonts": per_font,
                    "installed_family_count":
                    len(families) if families is not None else None,
                    "font_registry": {
                        "source": str(registry_path),
                        "consulted": registry["loaded"],
                        "aliases_registered":
                            sorted(registry["mapping"])
                            if registry["mapping"] is not None
                            else None,
                        "problem": registry["problem"]}}
        if registry_failures:
            return self.add(make_check(
                "package.fonts", title, True, FAIL,
                "; ".join(registry_failures),
                code="QC_FONT_REGISTRY_UNREADABLE",
                category="MG_QC_FAILED", tool=fc,
                observed=observed,
                evidence=str(path) if path else None))
        if failures:
            return self.add(make_check(
                "package.fonts", title, True, FAIL,
                "; ".join(failures), code="QC_FONT_UNRESOLVED",
                category="MG_QC_FAILED", tool=fc,
                observed=observed,
                evidence=str(path) if path else None))
        if not_run_reason:
            return self.add(make_check(
                "package.fonts", title, True, NOT_RUN,
                not_run_reason, tool=fc, observed=observed,
                evidence=str(path) if path else None))
        return self.add(make_check(
            "package.fonts", title, True, PASS,
            "every declared font requirement resolves to an "
            "installed family or a package font file", tool=fc,
            observed=observed, evidence=str(path) if path else None))

    def check_lint(self):
        title = "static lint record consumed (MG-030)"
        path = Path(self.args.lint_report) \
            if self.args.lint_report else None
        if path is None or not path.exists():
            return self.add(skipped(
                "package.lint", title, False,
                "no MG-030 lint report was supplied (--lint-report); "
                "lint is produced by the runtime lint layer, and QC "
                "consumes its record when one exists"))
        try:
            report = load_json(path)
        except (OSError, ValueError) as exc:
            return self.add(make_check(
                "package.lint", title, False, FAIL,
                "lint report %s does not parse: %s" % (path, exc),
                code="QC_LINT_RECORD_INVALID",
                category="MG_SCHEMA_INVALID",
                observed={"lint_path": str(path)}, evidence=str(path)))
        audit = report.get("visualAudit") or {}
        observed = {"lint_path": str(path), "pass": report.get("pass"),
                    "counts": report.get("counts"),
                    "visual_audit_status": audit.get("status"),
                    "visual_audit_evidence": audit.get("evidence")}
        if report.get("pass") is not True:
            return self.add(make_check(
                "package.lint", title, False, FAIL,
                "the MG-030 lint report does not pass: %s"
                % (report.get("findings") or "pass flag is not true"),
                code="QC_LINT_FAILED", category="MG_QC_FAILED",
                observed=observed, evidence=str(path)))
        return self.add(make_check(
            "package.lint", title, False, PASS,
            "lint report passes. Its visualAudit status is recorded "
            "verbatim (%s); QC never upgrades a pending visual audit "
            "into evidence" % audit.get("status"),
            observed=observed, evidence=str(path)))

    def check_motion_proof(self):
        title = "motion-proof record consumed (MG-032)"
        path = Path(self.args.motion_proof) \
            if self.args.motion_proof else None
        if path is None and self.job_dir:
            cand = self.job_dir / "motion-proof.json"
            path = cand if cand.exists() else None
        if path is None or not path.exists():
            return self.add(skipped(
                "package.motion_proof", title, False,
                "no MG-032 motion-proof record was supplied or "
                "found in the job package; when a record exists QC "
                "consumes its verdict here"))
        try:
            record = load_json(path)
        except (OSError, ValueError) as exc:
            return self.add(make_check(
                "package.motion_proof", title, False, FAIL,
                "motion-proof record %s does not parse: %s"
                % (path, exc), code="QC_MOTION_PROOF_INVALID",
                category="MG_SCHEMA_INVALID",
                observed={"motion_proof_path": str(path)},
                evidence=str(path)))
        verdict = record.get("verdict") or record.get("status")
        passed = record.get("pass")
        ok = passed is True or verdict in ("pass", "passed", "PASS")
        observed = {"motion_proof_path": str(path),
                    "verdict": verdict, "pass": passed,
                    "label": record.get("label"),
                    "rough_layout_only": record.get(
                        "roughLayoutOnly",
                        record.get("rough_layout_only"))}
        if not ok:
            return self.add(make_check(
                "package.motion_proof", title, False, FAIL,
                "the motion-proof record does not record a pass "
                "(verdict %r, pass %r)" % (verdict, passed),
                code="QC_MOTION_PROOF_FAILED",
                category="MG_QC_FAILED", observed=observed,
                evidence=str(path)))
        return self.add(make_check(
            "package.motion_proof", title, False, PASS,
            "motion-proof record records a pass", observed=observed,
            evidence=str(path)))

    def check_process_registry(self):
        title = ("no live render processes remain registered to "
                 "this job (MG-029)")
        if self.failed("inputs.plan"):
            return self.add(not_run(
                "process.registry", title, True,
                "inputs.plan failed (%s); the job under QC cannot "
                "be identified, so its registry records cannot be "
                "matched to it" % self.plan_error))
        job_id = (self.timeline or {}).get("job_id")
        if not job_id:
            return self.add(not_run(
                "process.registry", title, True,
                "the compiled plan names no job id; the MG-029 "
                "registry keeps one file per job, so there is no "
                "identity to match records against"))
        reg_dir = process_registry_dir()
        reg_path = reg_dir / (sanitize_job_segment(job_id) + ".json")
        observed = {"registry_dir": str(reg_dir),
                    "registry_file": str(reg_path),
                    "job_id": job_id}
        if not reg_path.exists():
            return self.add(skipped(
                "process.registry", title, True,
                "the MG-029 process registry holds no records for "
                "job %s (no %s): the isolation layer recorded no "
                "render processes for this job, so there are no "
                "registered processes to account for"
                % (job_id, reg_path.name),
                observed=dict(observed, records_found=0,
                              registry_file_present=False)))
        try:
            doc = load_json(reg_path)
        except (OSError, ValueError) as exc:
            return self.add(make_check(
                "process.registry", title, True, FAIL,
                "the process-registry record for job %s cannot be "
                "read (%s). A registry record QC cannot read "
                "cannot prove the job's render processes are done, "
                "so it fails by name rather than being ignored"
                % (job_id, exc),
                code="QC_PROCESS_REGISTRY_INVALID",
                category="MG_SCHEMA_INVALID",
                observed=observed, evidence=str(reg_path)))
        problem = _registry_shape_problem(doc)
        if problem:
            return self.add(make_check(
                "process.registry", title, True, FAIL,
                "the process-registry record for job %s is "
                "malformed: %s. A malformed record cannot prove "
                "the job's render processes are done, so it fails "
                "by name rather than being ignored"
                % (job_id, problem),
                code="QC_PROCESS_REGISTRY_INVALID",
                category="MG_SCHEMA_INVALID",
                observed=observed, evidence=str(reg_path)))
        observed["registry_job_id"] = doc["jobId"]
        if doc["jobId"] != job_id:
            # The registry files one record per job under the
            # sanitized job segment, and two job ids can sanitize
            # to the same segment. A file whose jobId names
            # another job holds that job's records, never this
            # one's, and another job's processes are never judged
            # here.
            return self.add(skipped(
                "process.registry", title, True,
                "the registry file at %s belongs to job %s, not "
                "job %s (their ids sanitize to the same registry "
                "segment); it holds no records for this job"
                % (reg_path, doc["jobId"], job_id),
                observed=dict(observed, records_found=0,
                              registry_file_present=True)))
        token = doc["token"]
        live, stale, finished = [], [], []
        for entry in doc["processes"]:
            pid = entry["pid"]
            state = entry.get("state", "running")
            if state != "running":
                finished.append({"pid": pid, "state": state})
                continue
            if registry_identity_live(
                    pid, entry.get("startTimeTicks"), token):
                live.append({"pid": pid,
                             "role": entry.get("role"),
                             "started_at": entry.get("startedAt")})
            else:
                stale.append(pid)
        observed.update({
            "records_found": len(doc["processes"]),
            "registry_file_present": True,
            "live_processes": live,
            "stale_pids": stale,
            "finished_processes": finished,
            "identity_rule": "MG-029: a running record is live "
                             "only when the pid is alive and its "
                             "kernel start-time still equals the "
                             "recorded ticks (or, when no ticks "
                             "were recorded, its environment "
                             "carries the job token)"})
        if live:
            return self.add(make_check(
                "process.registry", title, True, FAIL,
                "%d process(es) registered to job %s are still "
                "live at QC time (pids %s): the artifact is still "
                "being produced, or its render leaked processes, "
                "so QC over it cannot be final"
                % (len(live), job_id,
                   ", ".join(str(p["pid"]) for p in live)),
                code="QC_PROCESS_STILL_RUNNING",
                category="MG_QC_FAILED",
                observed=observed, evidence=str(reg_path)))
        return self.add(make_check(
            "process.registry", title, True, PASS,
            "no live processes remain registered to job %s "
            "(%d record(s): %d finished, %d stale)"
            % (job_id, len(doc["processes"]), len(finished),
               len(stale)),
            observed=observed, evidence=str(reg_path)))

    # -- the V2 run ------------------------------------------------------

    def run_v2(self):
        self.check_tools()
        self.check_inputs_plan()
        self.check_artifact_exists()
        self.check_artifact_hash()
        self.check_artifact_probe()
        self.check_artifact_decode()
        self.check_dimensions()
        self.check_fps()
        self.check_frame_count()
        self.check_duration()
        self.check_streams()
        self.check_audio_decode()
        self.check_audio_duration()
        self.check_audio_clipping()
        self.check_audio_loudness()
        self.check_audio_final_words()
        self.check_audio_score()
        self.check_audio_mode_promise()
        self.check_black()
        self.check_freeze()
        self.check_alpha()
        self.check_review_receipt()
        self.check_assets()
        self.check_fonts()
        self.check_lint()
        self.check_motion_proof()
        self.check_process_registry()
        return self.report(mode="package" if self.job_dir else "plan")

    # -- report assembly -------------------------------------------------

    def _artifact_relpath(self):
        if self.final_path is None:
            return None
        if self.job_dir:
            try:
                return str(self.final_path.resolve().relative_to(
                    self.job_dir))
            except ValueError:
                pass
        return str(self.final_path)

    def report(self, mode):
        failed = [c for c in self.checks if c["status"] == FAIL]
        not_run_mandatory = [c for c in self.checks
                             if c["status"] == NOT_RUN
                             and c["mandatory"]]
        verdict = "pass" if not failed and not not_run_mandatory \
            else "fail"
        first_category = None
        exit_code = 0
        if verdict == "fail":
            cats = [c["category"] for c in failed + not_run_mandatory
                    if c.get("category")]
            for cat in CATEGORY_ORDER:
                if cat in cats:
                    first_category = cat
                    break
            if first_category is None and (failed or not_run_mandatory):
                first_category = "MG_QC_FAILED"
            exit_code = EXIT_BY_CATEGORY.get(first_category, 6)
        plan_summary = None
        if self.timeline:
            plan_summary = {
                "job_id": self.timeline.get("job_id"),
                "fps": self.timeline.get("fps"),
                "total_frames": self.timeline.get("total_frames"),
                "total_samples": (self.sidecar or {}).get(
                    "total_samples"),
                "canvas": self._expected_canvas()[:2]
                if self._expected_canvas() else None,
                "audio_mode": (self.audio_plan or {}).get("mode"),
                "video_profile": self._declared_profile()[0],
            }
        report = {
            "schema_version": SCHEMA_VERSION,
            "item": ITEM,
            "tool": "qc.py",
            "tool_version": TOOL_VERSION,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "job_id": (self.timeline or {}).get("job_id"),
            "artifact_path": self._artifact_relpath(),
            "artifact_sha256": self.artifact_sha256,
            "artifact_bytes": self.artifact_bytes,
            "verdict": verdict,
            "exit_code": exit_code,
            "first_error_category": first_category,
            "plan": plan_summary,
            "inputs": self.inputs_record,
            "checks": self.checks,
            "summary": {
                "total": len(self.checks),
                "pass": sum(1 for c in self.checks
                            if c["status"] == PASS),
                "fail": len(failed),
                "skipped_with_reason": sum(
                    1 for c in self.checks if c["status"] == SKIPPED),
                "not_run": sum(1 for c in self.checks
                               if c["status"] == NOT_RUN),
                "failed_checks": [c["id"] for c in failed],
                "mandatory_not_run": [c["id"]
                                      for c in not_run_mandatory],
            },
        }
        return report

    # -- legacy V1 lane ------------------------------------------------
    # The scripts/qc.sh invocation path predates the compiled plan:
    # a V1 manifest, a work tree of scene segments, and a final. The
    # lane keeps that path working with the same fail-closed rules:
    # expectations derive from the manifest (the only plan a V1 run
    # has), tool failures fail by name, and the contact sheet step's
    # failure fails the gate, which is the exact hole
    # D-QC-FALSE-GREEN recorded against the old script.

    def _legacy_setup(self):
        args = self.args
        self.legacy_manifest_path = Path(args.legacy_manifest)
        self.workdir = Path(args.workdir) if args.workdir else None
        try:
            doc = load_json(self.legacy_manifest_path)
        except (OSError, ValueError) as exc:
            self.plan_error = "legacy manifest does not parse: %s" % exc
            return self.add(make_check(
                "inputs.plan", "planned truth loads and agrees", True,
                FAIL, self.plan_error, code="QC_INPUT_MISSING",
                category="MG_INPUT_MISSING"))
        fps = doc.get("fps")
        scenes = doc.get("scenes") or []
        if not fps or not scenes:
            self.plan_error = ("legacy manifest lacks fps or scenes; "
                               "there is no plan to validate against")
            return self.add(make_check(
                "inputs.plan", "planned truth loads and agrees", True,
                FAIL, self.plan_error, code="QC_PLAN_INVALID",
                category="MG_TIMELINE_INVALID"))
        total = sum(round_half_up(float(s["duration_seconds"]) * fps)
                    for s in scenes)
        self.legacy_manifest = doc
        # Present the derived plan in the same shapes the shared
        # checks consume.
        self.manifest = {"canvas": {"width": doc.get("width"),
                                    "height": doc.get("height")}}
        self.timeline = {"job_id": doc.get("video_name") or "legacy",
                         "fps": fps, "total_frames": total,
                         "scenes": [], "events": []}
        self.sidecar = {"total_samples": total * SAMPLE_RATE // fps}
        self.audio_plan = {"mode": "legacy", "narration": [],
                           "sfx": [], "music": None,
                           "loudnessTarget": None, "exclusions": []}
        self._record_input("manifest", self.legacy_manifest_path)
        return self.add(make_check(
            "inputs.plan", "planned truth loads and agrees", True,
            PASS, "legacy manifest parsed; expected totals derived "
            "from its scene durations (the V1 plan of record)",
            observed={"fps": fps, "total_frames": total,
                      "scenes": [s.get("id") for s in scenes],
                      "derivation": "sum(round(duration_seconds * "
                                    "fps)) over manifest scenes"},
            evidence=str(self.legacy_manifest_path)))

    def _legacy_audio_expected(self):
        doc = self.legacy_manifest
        if doc.get("music_bed"):
            return True
        return any((s.get("voiceover_text") or "").strip()
                   for s in doc.get("scenes", []))

    def check_legacy_segments(self):
        title = "scene segments match the manifest frame counts"
        if self.failed("inputs.plan"):
            return self.add(not_run(
                "legacy.segments", title, True,
                "inputs.plan failed (%s)" % self.plan_error))
        per_scene = []
        failures = []
        category = "MG_QC_FAILED"
        for s in self.legacy_manifest.get("scenes", []):
            sid = s.get("id")
            seg = self.workdir / "scenes" / sid / ("%s.mp4" % sid)
            want = round_half_up(float(s["duration_seconds"])
                                 * float(self.timeline["fps"]))
            if not seg.exists():
                per_scene.append({"scene": sid, "path": str(seg),
                                  "status": "missing"})
                failures.append("segment %s is missing" % seg)
                category = "MG_INPUT_MISSING"
                continue
            tool = run_tool(self._probe_argv(seg, count_frames=True),
                            timeout=600)
            if tool.error or tool.returncode != 0:
                per_scene.append({"scene": sid, "path": str(seg),
                                  "status": "probe_failed",
                                  "exit_status": tool.returncode,
                                  "error": tool.error})
                failures.append(
                    "segment %s could not be probed (exit %s): a "
                    "failed probe is a failed segment, not a "
                    "matching one" % (sid, tool.returncode))
                continue
            try:
                info = json.loads(tool.stdout)
                v = next(x for x in info["streams"]
                         if x.get("codec_type") == "video")
                got = int(v.get("nb_read_frames")
                          or v.get("nb_frames") or 0)
            except (ValueError, KeyError, StopIteration, TypeError):
                got = 0
            status = "match" if got == want else "mismatch"
            per_scene.append({"scene": sid, "path": str(seg),
                              "status": status,
                              "expected_frames": want,
                              "decoded_frames": got})
            if got != want:
                failures.append("segment %s: manifest %d frames, "
                                "file holds %d" % (sid, want, got))
        observed = {"segments": per_scene}
        if failures:
            code = "QC_SEGMENT_MISSING" if category == \
                "MG_INPUT_MISSING" else "QC_SEGMENT_FRAME_MISMATCH"
            return self.add(make_check(
                "legacy.segments", title, True, FAIL,
                "; ".join(failures), code=code, category=category,
                observed=observed))
        return self.add(make_check(
            "legacy.segments", title, True, PASS,
            "every segment exists and decodes to the manifest's "
            "frame count", observed=observed))

    def check_legacy_worktree(self):
        title = "no zero-byte files in the work tree"
        zero = []
        if self.workdir and self.workdir.is_dir():
            for root, _dirs, files in os.walk(self.workdir):
                for name in files:
                    p = Path(root) / name
                    try:
                        if p.stat().st_size == 0:
                            zero.append(str(p))
                    except OSError:
                        pass
        else:
            return self.add(make_check(
                "legacy.worktree", title, True, FAIL,
                "work tree %s does not exist" % self.workdir,
                code="QC_INPUT_MISSING", category="MG_INPUT_MISSING"))
        if zero:
            return self.add(make_check(
                "legacy.worktree", title, True, FAIL,
                "zero-byte files in the work tree: %s"
                % ", ".join(zero[:10]),
                code="QC_ZERO_BYTE_FILE", category="MG_QC_FAILED",
                observed={"zero_byte_files": zero[:25],
                          "count": len(zero)}))
        return self.add(make_check(
            "legacy.worktree", title, True, PASS,
            "no zero-byte files in the work tree",
            observed={"zero_byte_files": []}))

    def check_legacy_streams(self):
        title = "stream inventory matches the manifest"
        if self.failed("inputs.plan") or self.failed("artifact.probe"):
            return self.add(not_run(
                "plan.streams", title, True,
                "a prerequisite check failed"))
        expected = self._legacy_audio_expected()
        a = self._audio_stream()
        observed = {"expected_audio": expected,
                    "observed_audio": a is not None,
                    "derivation": "manifest music_bed or any scene "
                                  "voiceover_text"}
        if expected and a is None:
            return self.add(make_check(
                "plan.streams", title, True, FAIL,
                "the manifest declares a music bed or voiceover, "
                "but the final has no audio stream",
                code="QC_STREAM_INVENTORY_MISMATCH",
                category="MG_QC_FAILED", observed=observed,
                evidence=str(self.final_path)))
        if not expected and a is not None:
            return self.add(make_check(
                "plan.streams", title, True, FAIL,
                "the manifest declares no audio, but the final "
                "carries an audio stream",
                code="QC_STREAM_INVENTORY_MISMATCH",
                category="MG_QC_FAILED", observed=observed,
                evidence=str(self.final_path)))
        return self.add(make_check(
            "plan.streams", title, True, PASS,
            "stream inventory matches the manifest", observed=observed,
            evidence=str(self.final_path)))

    def check_legacy_audio_duration(self):
        title = "audio length matches the manifest duration"
        a = self._audio_stream()
        if a is None:
            return self.add(skipped(
                "audio.duration", title, True,
                "no audio stream to measure; plan.streams judges "
                "whether the manifest expected one",
                observed={"audio_stream": None}))
        if self.failed("inputs.plan"):
            return self.add(not_run(
                "audio.duration", title, True,
                "inputs.plan failed (%s)" % self.plan_error))
        want = int(self.timeline["total_frames"]) / float(
            self.timeline["fps"])
        raw = a.get("duration") or (
            self.probe.get("format") or {}).get("duration")
        try:
            got = float(raw)
        except (TypeError, ValueError):
            got = None
        observed = {"expected_seconds": round(want, 3),
                    "observed_seconds": got,
                    "tolerance_seconds": LEGACY_AUDIO_TOLERANCE_S,
                    "compared_against": "the manifest's total "
                                        "duration, never the video "
                                        "stream"}
        if got is None or abs(got - want) > LEGACY_AUDIO_TOLERANCE_S:
            return self.add(make_check(
                "audio.duration", title, True, FAIL,
                "audio stream runs %ss against the manifest's "
                "%.3fs program (tolerance %.2fs)"
                % (raw, want, LEGACY_AUDIO_TOLERANCE_S),
                code="QC_AUDIO_TRUNCATED", category="MG_QC_FAILED",
                observed=observed, evidence=str(self.final_path)))
        return self.add(make_check(
            "audio.duration", title, True, PASS,
            "audio length matches the manifest duration within the "
            "legacy tolerance", observed=observed,
            evidence=str(self.final_path)))

    def check_legacy_contact_sheet(self):
        title = "contact sheet builds and is written"
        if self.failed("inputs.plan"):
            return self.add(not_run(
                "legacy.contact_sheet", title, True,
                "inputs.plan failed (%s)" % self.plan_error))
        sheet = self.workdir / "contact-sheet.jpg"
        tiles = []
        tools = []
        tmp = Path(tempfile.mkdtemp(prefix="mg034-sheet-"))
        try:
            for s in self.legacy_manifest.get("scenes", []):
                sid = s.get("id")
                seg = self.workdir / "scenes" / sid / ("%s.mp4" % sid)
                probe = run_tool(
                    [self.ffprobe, "-v", "error", "-show_entries",
                     "format=duration", "-of", "csv=p=0", str(seg)],
                    timeout=120)
                tools.append(probe)
                if probe.error or probe.returncode != 0:
                    return self.add(make_check(
                        "legacy.contact_sheet", title, True, FAIL,
                        "contact sheet build failed while probing "
                        "segment %s (exit %s). The legacy script "
                        "printed PASS here regardless; this gate "
                        "fails by name" % (sid, probe.returncode),
                        code="QC_CONTACT_SHEET_FAILED",
                        category="MG_ENCODE_FAILED", tool=tools,
                        observed={"failed_segment": sid},
                        evidence=str(sheet)))
                try:
                    dur = float(probe.stdout.strip())
                except ValueError:
                    dur = 0.0
                for frac, tag in ((0.15, "a"), (0.5, "b"), (0.85, "c")):
                    out = tmp / ("tile_%s_%s.jpg" % (sid, tag))
                    tool = run_tool(
                        [self.ffmpeg, "-y", "-ss",
                         "%.3f" % (dur * frac), "-i", str(seg),
                         "-frames:v", "1", "-q:v", "4", str(out)],
                        timeout=120)
                    tools.append(tool)
                    if tool.error or tool.returncode != 0 \
                            or not out.exists():
                        return self.add(make_check(
                            "legacy.contact_sheet", title, True, FAIL,
                            "contact sheet build failed extracting "
                            "a frame from segment %s (exit %s)"
                            % (sid, tool.returncode),
                            code="QC_CONTACT_SHEET_FAILED",
                            category="MG_ENCODE_FAILED", tool=tools,
                            observed={"failed_segment": sid},
                            evidence=str(sheet)))
                    tiles.append(out)
            cols = 3
            rows = max(1, (len(tiles) + cols - 1) // cols)
            argv = [self.ffmpeg, "-y"]
            for t in tiles:
                argv += ["-i", str(t)]
            argv += ["-filter_complex", "tile=%dx%d" % (cols, rows),
                     "-q:v", "4", str(sheet)]
            tool = run_tool(argv, timeout=300)
            tools.append(tool)
            if tool.error or tool.returncode != 0 \
                    or not sheet.exists() or sheet.stat().st_size == 0:
                return self.add(make_check(
                    "legacy.contact_sheet", title, True, FAIL,
                    "contact sheet tiling failed (exit %s); no sheet "
                    "was written" % tool.returncode,
                    code="QC_CONTACT_SHEET_FAILED",
                    category="MG_ENCODE_FAILED", tool=tools,
                    evidence=str(sheet)))
            return self.add(make_check(
                "legacy.contact_sheet", title, True, PASS,
                "contact sheet written from %d tiles with every "
                "extraction step checked" % len(tiles), tool=tools,
                observed={"sheet": str(sheet), "tiles": len(tiles),
                          "bytes": sheet.stat().st_size},
                evidence=str(sheet)))
        finally:
            for t in tiles:
                try:
                    t.unlink()
                except OSError:
                    pass
            try:
                tmp.rmdir()
            except OSError:
                pass

    def check_legacy_determinism(self):
        title = "per-scene determinism backstop"
        scripts_dir = Path(__file__).resolve().parent
        verifier = scripts_dir / "verify-determinism.js"
        # The backstop re-renders each scene from its source file;
        # when the run tree does not carry the scene sources it
        # cannot run at all, and the pre-render determinism gate
        # remains the authority. That is an applicability skip,
        # named as one, never a pass.
        missing_sources = []
        base = self.legacy_manifest_path.resolve().parent
        for s in self.legacy_manifest.get("scenes", []):
            ref = s.get("file")
            if ref and not (base / ref).exists():
                missing_sources.append(ref)
        if missing_sources:
            return self.add(skipped(
                "legacy.determinism", title, False,
                "scene source file(s) %s are not in the run tree, "
                "so the determinism backstop has nothing to "
                "re-render; the pre-render determinism gate remains "
                "the authority for this run"
                % ", ".join(missing_sources),
                observed={"missing_scene_sources": missing_sources}))
        node = run_tool(["node", "--version"], timeout=30)
        if node.error or node.returncode != 0:
            return self.add(skipped(
                "legacy.determinism", title, False,
                "node is unavailable, so the determinism backstop "
                "cannot run; the pre-render determinism gate remains "
                "the authority for V1 runs",
                observed={"node_error": node.error}))
        per_scene = []
        failures = []
        for s in self.legacy_manifest.get("scenes", []):
            sid = s.get("id")
            tool = run_tool(
                ["node", str(verifier), "--manifest",
                 str(self.legacy_manifest_path), "--scene", sid,
                 "--probes", "6"], timeout=900)
            ok = tool.returncode == 0 and "determinism OK" in (
                tool.stdout + tool.stderr)
            per_scene.append({"scene": sid,
                              "exit_status": tool.returncode,
                              "status": "pass" if ok else "fail"})
            if not ok:
                failures.append(sid)
        observed = {"scenes": per_scene}
        if failures:
            return self.add(make_check(
                "legacy.determinism", title, False, FAIL,
                "determinism drift in scene(s): %s"
                % ", ".join(failures), code="QC_DETERMINISM_FAILED",
                category="MG_QC_FAILED", observed=observed))
        return self.add(make_check(
            "legacy.determinism", title, False, PASS,
            "every scene's animation is still a pure function of t",
            observed=observed))

    def check_legacy_beat_sheet(self):
        title = "per-beat contact sheet"
        beats = self.workdir / "audio" / "beats.json"
        if not beats.exists():
            return self.add(skipped(
                "legacy.beat_sheet", title, False,
                "no beat grid at %s; there are no beats to sheet. "
                "The legacy script recorded this skip as a PASS; "
                "it is a skip, named as one" % beats,
                observed={"beats": str(beats)}))
        scripts_dir = Path(__file__).resolve().parent
        out = self.workdir / "beats-sheet.jpg"
        tool = run_tool(
            ["node", str(scripts_dir / "render.js"), "--beatsheet",
             "--beats", str(beats), "--video", str(self.final_path),
             "--out", str(out)], timeout=900)
        if tool.error or tool.returncode != 0 or not out.exists():
            return self.add(make_check(
                "legacy.beat_sheet", title, False, FAIL,
                "per-beat sheet failed (exit %s): %s"
                % (tool.returncode,
                   (tool.error or tool.stderr.strip())[-300:]),
                code="QC_BEAT_SHEET_FAILED",
                category="MG_ENCODE_FAILED", tool=tool,
                evidence=str(out)))
        return self.add(make_check(
            "legacy.beat_sheet", title, False, PASS,
            "per-beat sheet written", tool=tool,
            observed={"sheet": str(out)}, evidence=str(out)))

    def check_legacy_receipt_note(self):
        return self.add(skipped(
            "review.receipt",
            "review receipt (MG-031 coverage) binds this artifact",
            False,
            "legacy V1 run: the MG-031 coverage contract applies to "
            "V2 job packages. The legacy lane's review evidence is "
            "the contact sheet, judged by legacy.contact_sheet",
            observed={"mode": "legacy"}))

    def run_legacy(self):
        self.check_tools()
        self._legacy_setup()
        self.check_legacy_segments()
        self.check_legacy_worktree()
        self.check_artifact_exists()
        self.check_artifact_hash()
        self.check_artifact_probe()
        self.check_artifact_decode()
        self.check_dimensions()
        self.check_fps()
        self.check_frame_count()
        self.check_duration()
        self.check_legacy_streams()
        self.check_legacy_audio_duration()
        self.check_black()
        self.check_freeze()
        self.check_legacy_receipt_note()
        self.check_legacy_contact_sheet()
        self.check_legacy_determinism()
        self.check_legacy_beat_sheet()
        return self.report(mode="legacy")


# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="qc.py",
        description="Skill 72 technical QC (MG-034): fail-closed, "
                    "plan-referenced final checks.")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check", help="run technical QC")
    c.add_argument("--job-dir",
                   help="V2 job package directory (manifest.json, "
                        "timeline.json, timeline-sidecar.json, "
                        "renders/final.mp4, review/ bundle)")
    c.add_argument("--final", help="final artifact (default: "
                                   "<job-dir>/renders/final.mp4)")
    c.add_argument("--manifest")
    c.add_argument("--plan", help="compiled plan document (combined "
                                  "or timeline-only)")
    c.add_argument("--sidecar")
    c.add_argument("--media", help="plan-mode media registry")
    c.add_argument("--assets")
    c.add_argument("--storyboard")
    c.add_argument("--planner")
    c.add_argument("--coverage",
                   help="MG-031 coverage record file or bundle dir")
    c.add_argument("--review-record",
                   help="MG-024 preview.review.json bound to the "
                        "coverage record")
    c.add_argument("--approved-intervals",
                   help="plan declaration of approved dark/frozen "
                        "intervals (default: "
                        "<job-dir>/qc-approved-intervals.json)")
    c.add_argument("--lint-report", help="MG-030 LintReport JSON")
    c.add_argument("--motion-proof", help="MG-032 record JSON")
    c.add_argument("--out", help="also write the report here "
                                 "(default in job-dir mode: "
                                 "<job-dir>/qc/final-qc.json)")
    c.add_argument("--ffmpeg", default="ffmpeg")
    c.add_argument("--ffprobe", default="ffprobe")
    c.add_argument("--legacy-manifest",
                   help="V1 manifest: selects the legacy lane")
    c.add_argument("--workdir",
                   help="V1 work tree (legacy lane)")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "check":
        parser.error("unknown command")
    try:
        run = QcRun(args)
        if args.legacy_manifest:
            if not args.workdir or not args.final:
                parser.error("the legacy lane requires --workdir "
                             "and --final")
            report = run.run_legacy()
            out_path = Path(args.out) if args.out else None
        else:
            if run.final_path is None:
                parser.error("name the final artifact with --final "
                             "or --job-dir")
            report = run.run_v2()
            if args.out:
                out_path = Path(args.out)
            elif run.job_dir:
                out_path = run.job_dir / "qc" / "final-qc.json"
            else:
                out_path = None
    except Exception as exc:  # never a traceback-only exit
        report = {
            "schema_version": SCHEMA_VERSION,
            "item": ITEM,
            "tool": "qc.py",
            "tool_version": TOOL_VERSION,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "mode": "error",
            "job_id": None,
            "artifact_path": None,
            "artifact_sha256": None,
            "artifact_bytes": None,
            "verdict": "fail",
            "exit_code": 1,
            "first_error_category": "MG_QC_FAILED",
            "plan": None,
            "inputs": {},
            "checks": [make_check(
                "qc.internal", "QC ran to completion", True, FAIL,
                "QC itself raised %s: %s; the gate fails closed "
                "rather than guessing" % (type(exc).__name__, exc),
                code="QC_INTERNAL_ERROR", category="MG_QC_FAILED")],
            "summary": {"total": 1, "pass": 0, "fail": 1,
                        "skipped_with_reason": 0, "not_run": 0,
                        "failed_checks": ["qc.internal"],
                        "mandatory_not_run": []},
        }
        print(json.dumps(report, indent=1))
        print("qc.py: internal error: %s" % exc, file=sys.stderr)
        return 1
    text = json.dumps(report, indent=1)
    print(text)
    if out_path:
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print("qc.py: could not write report to %s: %s"
                  % (out_path, exc), file=sys.stderr)
            return 1
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
