from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import signal
import shlex
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# FIX 11: the engine consults the real capacity probe (module + its refusal
# helpers) instead of a hand-stamped stub dict.
from . import capacity as _capacity
from .capacity import CapacityUnmeasured, autofail_payload, refusal_message
from .execution_plan import build_execution_plan
from .state import (
    StateStore, utcnow, sha256_file, EXIT_OK, EXIT_GATE_BLOCKED, EXIT_WAIVER_INVALID,
    ENTRY_COMMAND,
)
from .manifest import Manifest, Phase
from .report import Reporter
from .gates import Gates, ALL_GATE_KEYS, NON_WAIVABLE_GATES, WARN_ONLY_GATES
from .waivers import WaiverError, load_waivers, validate_waiver
from .defers import load_intake, phase_is_deferred
from .artifacts import validate_artifact
from .heal import HEAL_CAP_TRANSIENT, HEAL_CAP_REGENERATE, HEAL_CAP_ALT_ROUTE, HEAL_CAP_REGATE, record_heal_event
from . import heal
from . import persona
from . import curate as _curate


_ENGINE_ATTESTED_BY_PREFIX = "engine:"

def _process_manifest_path(run_dir) -> Path:
    return run_dir / "working" / "checkpoints" / "process_manifest.json"

def _load_process_manifest(run_dir) -> dict:
    p = _process_manifest_path(run_dir)
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text())
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}

def _atomic_write_json(path: Path, obj) -> None:
    """F18-style atomic replace: the process manifest is the attestation chain,
    so a torn write must never truncate it (readers see either the old complete
    file or the new complete one)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        tmp.write_text(json.dumps(obj, indent=2))
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass

def _combined_artifact_sha(shas) -> str:
    """FIX 30 — one deterministic sha256 over the banked artifact set, so
    artifact_sha256 means 'hash of exactly what this phase produced'. Mirrors
    the runner's _compute_artifact_sha discipline: sorted (path, sha) pairs fed
    into a fresh sha256. Empty set => 'no-artifact-spec' (same marker the
    runner's attest_phase accepts for system phases with no concrete
    artifact)."""
    import hashlib as _hl
    if not shas:
        return "no-artifact-spec"
    h = _hl.sha256()
    for rel in sorted(shas):
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(str(shas[rel]).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()

def _intake_sha_now(run_dir):
    """FIX 109: the intake sha to stamp alongside a DONE checkpoint.

    phases.py records, on every phase it parks at status=done, WHICH intake
    the phase's work was built from — runfacts.invalidate_intake_consumers()
    compares that stamp against the provenance row's sha_before to decide
    freshness by CONTENT, never by a 1-second-resolution wall clock (a
    sanctioned intake write and a phase completion landing in the same
    second would otherwise skip the consumer invalidation silently).
    Best-effort by contract: an import or read failure yields None and the
    invalidation falls back to the attested_at rule — never blocks the
    checkpoint."""
    try:
        from .runfacts import current_intake_sha
        return current_intake_sha(run_dir)
    except Exception:  # noqa: BLE001 — stamping must never block a completion
        return None


def _deliverable_specs():
    """FIX 7 (W06b-B4): the ten-deliverable whitelist from deliverables.py
    (the single source of truth). Returns [] when the module cannot be
    imported -- board registration is fail-soft by contract and can never
    block a run."""
    try:
        from .deliverables import DELIVERABLE_AUDIT_SPEC
        return DELIVERABLE_AUDIT_SPEC
    except Exception:  # noqa: BLE001 -- registration never blocks a run
        return []


# F54b (SMOKE-1, 2026-09-01): serializes each script phase's nonce
# mint -> child -> unlink critical section (see _run_script_phase). Module-level so
# ALL Job instances in this process — one engine process dispatches every wave
# sibling — share the same mutual exclusion.
# FIX 25 (MASTER Part 8): the lock stays for the umask-protected mint, but the
# FILE is now PER PHASE (.nonce-<sanitized phase id>) instead of one shared
# run-scoped path, so sibling script phases in one wave no longer overwrite
# each other's nonce and the exec critical section need not serialize the
# whole wave.
_NONCE_LOCK = threading.Lock()

# FIX 25 (MASTER Part 8): sanitize a manifest phase id into a safe nonce-file
# basename segment. Mirrors build_deck._entry_nonce_phase_file's own sanitizer
# byte-for-byte so the engine's minted name and the guard's derived name can
# never diverge. Falls back to the empty string on a malformed id, which the
# caller treats as "no per-phase file" (legacy run-scoped handshake).
def _nonce_phase_token(phase_id: str) -> str:
    try:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(phase_id or ""))
    except Exception:  # noqa: BLE001 — never let a malformed id break dispatch
        safe = ""
    return safe


def _entry_nonce_phase_file(run_dir: Path, phase_id: str) -> Path:
    """FIX 25: run-scoped PER-PHASE nonce file
    <run_dir>/working/checkpoints/.nonce-<sanitized phase id>."""
    return (Path(run_dir) / "working" / "checkpoints"
            / f".nonce-{_nonce_phase_token(phase_id)}")
# FIX-21 (D21): run_with_cleanup spawns the phase exec in a NEW PROCESS GROUP and, on
# budget expiry, kills the WHOLE group (SIGTERM -> SIGKILL) so a timed-out phase leaves
# no orphaned grandchildren (the D21 zombie path). Direct-child-only `subprocess.run`
# timeout is what let a `find` zombie run 18+ minutes beside the real build.
try:
    from process_reaper import run_with_cleanup
except ImportError:  # pragma: no cover — module ships beside presentation_job
    run_with_cleanup = None


# ---------------------------------------------------------------------------
# FIX 105 (Master Part 8): ENGINE SHUTDOWN REAPS IN-FLIGHT EXEC HANDLES.
# A render batch is spawned by _run_script_phase_locked through
# run_with_cleanup, which puts the exec in its OWN session
# (start_new_session=True). That own session is what makes a budget-timeout
# group-kill work — but it also means the launcher's stop_engine killpg of the
# ENGINE'S group does NOT reach the render child: a SIGTERM (or SIGKILL) that
# kills the engine mid-render leaves the own-session render batch alive,
# writing stale renders into a dead run (the FIX 105 orphan the QC probe
# catches). The engine's FIX 19 SIGTERM handler only set a flag nothing read.
#
# The engine therefore REGISTERS every in-flight exec handle at spawn time and
# (a) the SIGTERM/SIGINT handler flips _ENGINE_SHUTDOWN_EVENT AND kills every
#     registered handle's whole process group (TERM, engine's own 10s-grace
#     escalation is the launcher's SIGKILL; the handler KILLs after its own
#     short grace inside communicate()'s wake-up path);
# (b) each blocking communicate() waits on the handle in small slices and
#     returns as soon as the shutdown event fires, so the wave's finally path
#     runs immediately instead of blocking for the remaining phase budget.
# Handles are unregistered the moment their wait returns — the registry only
# ever names LIVE execs.
# ---------------------------------------------------------------------------
_ENGINE_SHUTDOWN_EVENT = threading.Event()
_EXEC_REGISTRY_LOCK = threading.Lock()
_EXEC_REGISTRY: Dict[int, subprocess.Popen] = {}

def _register_exec(proc: subprocess.Popen) -> None:
    with _EXEC_REGISTRY_LOCK:
        _EXEC_REGISTRY[proc.pid] = proc

def _unregister_exec(proc: subprocess.Popen) -> None:
    with _EXEC_REGISTRY_LOCK:
        _EXEC_REGISTRY.pop(proc.pid, None)

def _kill_registered_execs(sig: int) -> None:
    """os.killpg every registered exec's own process group, best-effort. The
    execs ARE group leaders (run_with_cleanup spawns start_new_session=True);
    a non-leader fallback covers a plain subprocess.run child."""
    with _EXEC_REGISTRY_LOCK:
        procs = list(_EXEC_REGISTRY.values())
    for proc in procs:
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except OSError:
            try:
                proc.kill()
            except OSError:
                pass

def _shutdown_requested() -> bool:
    return _ENGINE_SHUTDOWN_EVENT.is_set()

#: FIX 105: slice width for the shutdown-aware exec wait (seconds). Small
#: enough that a SIGTERM's kill-and-unwind lands well inside the launcher's
#: 10 s grace; large enough that the poll loop costs nothing.
_EXEC_JOIN_SLICE_S = 0.5

def _run_exec_joined(spawn_and_wait, timeout_s: Optional[float]):
    """FIX 105: run `spawn_and_wait()` (a run_with_cleanup / subprocess.run
    call that BLOCKS until the exec exits or hits `timeout_s`) while staying
    responsive to engine shutdown. The spawned exec's Popen handle is
    REGISTERED in the engine's exec registry for its whole life (via
    run_with_cleanup's on_spawn hook), so the shutdown path can killpg the
    render batch's own session; the wait is sliced so the moment the shutdown
    event fires the call returns what it has (the killed exec's
    CompletedProcess, or None when the kill races the very first slice).
    Normal runs behave EXACTLY like the bare call: the whole timeout is
    honoured and the return value passes through unchanged."""
    deadline = (time.monotonic() + timeout_s) if timeout_s else None
    handle: Dict[str, Any] = {"proc": None, "result": None, "exc": None, "done": False}

    def _on_spawn(proc) -> None:  # noqa: ANN001 — Popen from run_with_cleanup
        handle["proc"] = proc
        _register_exec(proc)

    def _runner() -> None:
        try:
            handle["result"] = spawn_and_wait(on_spawn=_on_spawn)
        except BaseException as exc:  # noqa: BLE001 — forwarded to the caller verbatim
            handle["exc"] = exc
        finally:
            if handle["proc"] is not None:
                _unregister_exec(handle["proc"])
            handle["done"] = True

    th = threading.Thread(target=_runner, daemon=True)
    th.start()
    while not handle["done"]:
        if _shutdown_requested():
            # Kill every own-session exec this engine knows about, then join.
            _kill_registered_execs(signal.SIGTERM)
            time.sleep(0.5)
            _kill_registered_execs(signal.SIGKILL)
            th.join(timeout=10)
            return handle["result"]
        if deadline is not None and time.monotonic() >= deadline:
            th.join(timeout=5)  # the inner call enforces its own cap
            return handle["result"] if handle["done"] else None
        time.sleep(_EXEC_JOIN_SLICE_S)
    if handle["exc"] is not None:
        raise handle["exc"]
    return handle["result"]

def _fallback_run(argv, budget: float, child_env, on_spawn, run_dir: Optional[Path] = None):
    """FIX 105: the process_reaper-absent fallback for
    _run_script_phase_locked — the same bare subprocess.run contract the
    pre-FIX 105 code ran (CompletedProcess / TimeoutExpired, no env mutation),
    with an on_spawn hook so the exec is still registered for engine-shutdown
    reaping. NOT its own group leader here — _kill_registered_execs falls back
    to a direct pid kill for it. `run_dir` carries the caller's cwd explicitly:
    wave members run on pool threads, so any module-global handoff would race."""
    proc = subprocess.Popen(argv, shell=False, cwd=str(run_dir or Path.cwd()),
                            stdout=None, stderr=None,
                            env=child_env)
    if on_spawn is not None:
        try:
            on_spawn(proc)
        except Exception:  # noqa: BLE001 — hook never breaks the exec
            pass
    try:
        out, err = proc.communicate(timeout=budget)
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=5)
        except (subprocess.TimeoutExpired, Exception):  # noqa: BLE001
            pass
        raise


# ---------------------------------------------------------------------------
# FIX 9a (MASTER Part 8 Fix 9): the per-unit status enum -- the ONLY values a
# phase record in state.json's "phases" list may carry. QC FIX 9 proof binds
# one of them by name: a unit the stub provider fails must end with
# state.phases['<id>'].status == 'quarantined' while every other phase
# reaches done and state.terminal stays None until the end-of-run park.
#
#   pending -> running -> done | deferred | quarantined | blocked
#                       (| failed  -- normalized by run() for a unit that
#                                    died without parking its own status;
#                        | obsolete -- repin FIX 20, set in __main__.py)
#
# quarantined: unit-level failure (substance FAIL, budget or regeneration
#   exhausted). The wave-mates and every downstream wave still run; run()
#   parks the RUN exactly once at the end, with the failed_units ledger row
#   naming the unit.
# blocked: operator/gate park (intake gate, executor wiring) -- resumable.
# ---------------------------------------------------------------------------
PHASE_STATUS_PENDING = "pending"
PHASE_STATUS_RUNNING = "running"
PHASE_STATUS_DONE = "done"
PHASE_STATUS_DEFERRED = "deferred"
PHASE_STATUS_QUARANTINED = "quarantined"
PHASE_STATUS_BLOCKED = "blocked"
PHASE_STATUS_FAILED = "failed"
PHASE_STATUS_OBSOLETE = "obsolete"

PHASE_STATUSES = (
    PHASE_STATUS_PENDING,
    PHASE_STATUS_RUNNING,
    PHASE_STATUS_DONE,
    PHASE_STATUS_DEFERRED,
    PHASE_STATUS_QUARANTINED,
    PHASE_STATUS_BLOCKED,
    PHASE_STATUS_FAILED,
    PHASE_STATUS_OBSOLETE,
)
assert len(PHASE_STATUSES) == len(set(PHASE_STATUSES)), \
    "duplicate value in the per-unit status enum"


def _wave_execution_enabled() -> bool:
    """FIX 1: default ON. The only value that disables is exactly "0" (also
    strip quotes/whitespace so `PRESENTATION_WAVE_EXECUTION=""` counts as
    unset, not OFF — an EMPTY value must never silently select the rollback
    path). =0 restores the exact pre-fix serial engine loop."""
    raw = os.environ.get("PRESENTATION_WAVE_EXECUTION")
    if raw is None:
        return True
    return raw.strip().strip("'\"") != "0"

# ---------------------------------------------------------------------------
# FIX 5 (emitter): mirror stage-timing rows to the Command Center ingest route.
#
# PRESENTATION_TELEMETRY_CC: default ON (=1). =0 disables the CC mirror POST
# entirely (the durable working/telemetry/stage-timings.jsonl file is still
# written — the file is the source of truth, the POST is only a mirror).
# Value semantics match _wave_execution_enabled: strips quotes/whitespace, so
# "" counts as unset (ON), and only exactly "0" selects OFF.
#
# Env used (all optional; resolver mirrors cc_board.board_config):
#   COMMAND_CENTER_URL | MISSION_CONTROL_URL   CC base URL (unset -> mirror off)
#   CC_API_TOKEN | MC_API_TOKEN                CC bearer token (required by CC
#                                              middleware Gate B for /api/*)
#   WEBHOOK_SECRET | CC_WEBHOOK_SECRET         HMAC-SHA256 signing secret for
#                                              x-webhook-signature. If unset the
#                                              POST is SKIPPED with one warning
#                                              line — never sent unsigned, and
#                                              never allowed to break a run.
#
# Endpoint: POST {base}/api/presentations/stage-timings (route in the CC repo,
# src/app/api/presentations/stage-timings/route.ts). Envelope and signing
# mirror that route's validator byte-for-byte:
#   body    = {"rows":[...]}  (StageTimingBatchSchema: 1..1000 rows)
#   auth    = x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, raw_body) hex
#   limits  = 64KB body cap (the route 413s bigger; we chunk at 100 rows so a
#             batch can never approach it)
# The route is in WEBHOOK_SECRET_ROUTES: middleware Gate A 503s the box when
# WEBHOOK_SECRET is unset, and Gate B requires the Bearer token — both are
# satisfied by the envs above.
# ---------------------------------------------------------------------------
_CC_TELEMETRY_MAX_ROWS = 100          # chunk size: stays far under the 64KB cap
_CC_TELEMETRY_CONNECT_TIMEOUT_S = 5   # socket timeout: fail fast, never hang a run

def _telemetry_mirror_enabled() -> bool:
    """FIX 5 emitter flag — default ON; exactly "0" disables the CC mirror POST."""
    raw = os.environ.get("PRESENTATION_TELEMETRY_CC")
    if raw is None:
        return True
    return raw.strip().strip("'\"") != "0"

# One-time latch: when CC is configured (base set) but WEBHOOK_SECRET is unset,
# the mirror is disabled with exactly ONE warning line per process — never a
# per-row spam, never an unsigned POST, never an exception.
_CC_TELEMETRY_SECRET_WARNED = [False]

def _telemetry_mirror_config() -> Optional[Dict[str, str]]:
    """Resolve base URL / bearer / secret the same way cc_board.board_config()
    does. Returns None (mirror disabled) when the base URL is unset (a box with
    no CC configured — clean silent no-op) OR when the HMAC secret is unset
    (fail-soft: one warning line, then skip — an unsigned write to an
    authenticated route is never attempted). Never raises."""
    base = (os.environ.get("COMMAND_CENTER_URL") or
            os.environ.get("MISSION_CONTROL_URL") or "").strip().rstrip("/")
    token = (os.environ.get("CC_API_TOKEN") or
             os.environ.get("MC_API_TOKEN") or "").strip()
    secret = (os.environ.get("WEBHOOK_SECRET") or
              os.environ.get("CC_WEBHOOK_SECRET") or "").strip()
    if not base:
        return None
    if not secret:
        if not _CC_TELEMETRY_SECRET_WARNED[0]:
            _CC_TELEMETRY_SECRET_WARNED[0] = True
            print("WARN telemetry: CC stage-timings mirror disabled — "
                  "WEBHOOK_SECRET/CC_WEBHOOK_SECRET unset (unsupported "
                  "unsigned write never attempted)", flush=True)
        return None
    return {"base_url": base, "token": token, "secret": secret}

def _post_stage_timings_cc(rows: List[Dict[str, Any]]) -> None:
    """FIX 5 (emitter): POST stage-timing rows to the CC ingest route.

    Called after each batch append to working/telemetry/stage-timings.jsonl —
    the jsonl file stays the durable source of truth; this POST is a mirror
    for CC-side history. BEST-EFFORT by contract (same invariant as the jsonl
    writer): a telemetry POST can never abort a presentation run. Every exit
    path degrades to at most ONE printed warning line; nothing is raised.

    Failure modes covered: flag off, config unset (base or secret), URL
    construction errors, urllib/OS/ValueError on the request itself.
    """
    if not _telemetry_mirror_enabled():
        return
    if not rows:
        return
    cfg = _telemetry_mirror_config()
    if cfg is None:
        return
    url = f"{cfg['base_url']}/api/presentations/stage-timings"
    try:
        for i in range(0, len(rows), _CC_TELEMETRY_MAX_ROWS):
            chunk = rows[i:i + _CC_TELEMETRY_MAX_ROWS]
            raw_body = json.dumps({"rows": chunk}, separators=(",", ":")).encode("utf-8")
            headers = {"Content-Type": "application/json",
                       "Accept": "application/json"}
            if cfg["token"]:
                headers["Authorization"] = f"Bearer {cfg['token']}"
            headers["x-webhook-signature"] = hmac.new(
                cfg["secret"].encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
            req = urllib.request.Request(url, data=raw_body, headers=headers,
                                         method="POST")
            try:
                with urllib.request.urlopen(req,
                                            timeout=_CC_TELEMETRY_CONNECT_TIMEOUT_S) as resp:
                    status = resp.getcode()
                if status >= 300:
                    print(f"WARN telemetry: CC stage-timings POST failed "
                          f"(status {status})", flush=True)
            except urllib.error.HTTPError as exc:  # 4xx/5xx — read body for context
                print(f"WARN telemetry: CC stage-timings POST failed "
                      f"(status {exc.code})", flush=True)
    except Exception as exc:  # noqa: BLE001 — telemetry must NEVER break a run
        print(f"WARN telemetry: CC stage-timings POST failed: {exc}", flush=True)


# FIX 11 (real capacity width, stub deleted): the engine no longer carries a
# hand-stamped capacity probe. The old `_PHASE_A_CAPACITY_PROBE` constant --
# a fabricated deepseek-direct/available=8 dict -- was the exact defect this
# fix removes: whatever capacity_override.json declared (say 100) or whatever
# the box actually measured, the engine's wave plan was pinned to 8, so a
# 12-independent-phase manifest could never run wider than 8 and telemetry
# never showed more than 8 overlapping phase_exit intervals. The probe the
# engine passes to build_execution_plan is now the REAL capacity.probe()
# result (capacity.py), which reads capacity_override.json first, then
# 9Router/OpenClaw detection, then the cap table / PARK / conservative
# fallback. Unmeasured stays loud: a probe that produces no dispatchable
# number raises CapacityUnmeasured and the run refuses with
# AF-CAPACITY-UNMEASURED (same refusal execution_plan's CLI serves) -- it is
# never papered over with a constant.

# ---------------------------------------------------------------------------
# U069: named error for unparseable executor.cmd.
# ---------------------------------------------------------------------------
class PhaseExecutorContractError(RuntimeError):
    """U069: a phase's executor.cmd is not a parseable argument vector."""

# FIX 17: named error for a substance-verifier IMPORT failure. The engine must
# fail CLOSED: a phase that can never be substance-verified may never reach its
# done attestation, so the run aborts (raised out of run_phase) instead of the
# old warn-and-skip that advanced every phase unverified.
class VerifierImportError(RuntimeError):
    """FIX 17: phase_verifiers could not be imported -- the run aborts, unverified."""


# ---------------------------------------------------------------------------
# B2b (fix/engine-client-report-unformatted -- MASTER-WORK-ORDER-20260818 Wave
# B, unit B2b). This engine (presentation_job.py) is the path
# presentation-canonical-entry.sh actually dispatches to production -- it
# prefers ENGINE_ENTRY (this package) over the legacy run_signature_deck.py
# runner and only falls back to the runner when the engine component is
# absent from the box, which it is not on the live box. B2 fixed
# run_signature_deck.py's client-facing step count/messages, but that runner
# is not the code path production dispatches through, so B2's fix never
# reached a client.
#
# The defect here was worse than the one B2 fixed: run_phase() (below) read
# phase.client_report["start_template"] / ["done_template"] straight off the
# manifest -- "Step {k} of {N} -- {name} -- starting{eta}" -- and handed that
# STRING, UNFORMATTED, to self.report.to_requester(). A client received the
# literal text "Step {k} of {N} -- ... -- starting{eta}", braces and all,
# never a real step number. Verified: PIPELINE-MANIFEST.json v50 declares
# this exact template on all 36 phases, and no call to .format()/format_map()
# existed anywhere in this file before this fix.
#
# _client_deck_shape / _client_visible_phases / _client_phase_index below
# mirror run_signature_deck.py's B2 fix of the SAME name 1:1: SAME phase-id
# sets (_SP_ONLY_PHASE_IDS, _CONVERTER_ONLY_PHASE_IDS -- P-SP-CLAIM is the
# router and is NEVER filtered), SAME fail-safe direction (an unknown
# deck-shape signal WIDENS the visible/N count to the full 36-phase
# superset, never narrows it to a guessed smaller number). Unlike B2 (which
# discards the manifest's own client_report templates and hardcodes its own
# message string in emit_client_report()), _render_client_report_msg below
# ACTUALLY formats the manifest-declared template -- client_report is a real
# per-phase manifest field this engine is supposed to honor, not dead
# configuration to route around, and Phase.name (manifest.py) now parses the
# {name} token's source so it can be substituted too, not just {k}/{N}.
#
# None of this touches self.manifest.phases, the phase walk/dispatch loop,
# the DAG, declared_plan.json, or the 36-phase attestation/certificate chain
# -- display-only, exactly like B2's constraint on the runner side.
_SP_ONLY_PHASE_IDS = frozenset({
    "P-SP-INTAKE", "P-SP-INTAKE-TRACE", "P-SP-STRUCTURE", "P-SP-P3-HYGIENE",
})
_CONVERTER_ONLY_PHASE_IDS = frozenset({"P-CONVERTER"})
# Wave C unit C1 (manifest_version 51) -- the upsell branch. Same fail-safe shape as the
# two sets above: filtered out ONLY when the electing intake flag is POSITIVELY known to be
# something other than "yes"; an absent/unknown flag WIDENS the visible count, never narrows
# it. P-U-FORM-CHECKOUT rides the same WANT_SALES_CHECKOUT flag as P-U-SALES-BUILD /
# P-U-CHECKOUT-BUILD -- intake/upsell-questions.json has one combined yes/no for the pair.
_SALES_CHECKOUT_ONLY_PHASE_IDS = frozenset({
    "P-U-SALES-BUILD", "P-U-CHECKOUT-BUILD", "P-U-FORM-CHECKOUT",
})
_VSL_ONLY_PHASE_IDS = frozenset({"P-U-VSL-BUILD"})
# AF-INTAKE-GATE (Ticket 6, presentation department fix campaign, 2026-08-27):
# the artifact every content-authoring phase downstream ultimately depends on.
# See Engine._intake_gate_applies / Engine._check_intake_gate below -- a run
# that reaches a content phase before this file exists on disk was building
# on no client data at all, which is the defect this gate closes.
_INTAKE_ARTIFACT = "working/copy/intake.json"


class _SafeFormatDict(dict):
    """str.format_map() helper: a {token} in a manifest-authored client_report
    template that this dict does not recognize resolves to "" instead of
    raising KeyError (which would abort phase reporting entirely) or leaving
    the literal '{token}' in the client-facing message (the exact defect this
    fix exists to close). Only {k}/{N}/{name}/{eta} are ever populated today;
    this is forward defense for a future manifest edit that adds a new token
    to the template without a matching code change."""

    def __missing__(self, key: str) -> str:
        return ""

# ---------------------------------------------------------------------------
# The engine.
# ---------------------------------------------------------------------------
class Engine:
    def __init__(self, run_dir: Path, manifest: Manifest, store: StateStore,
                 state: Dict[str, Any], dry_run: bool = False) -> None:
        self.run_dir = run_dir
        self.manifest = manifest
        self.store = store
        self.state = state
        self.dry_run = dry_run
        self.report = Reporter(state, store)
        from .board import BoardMirror
        try:
            self.board = BoardMirror(run_dir, state, store, self.report)
        except Exception:
            self.report.event("warn", "board init failed — running without board mirror")
            self.board = None
        # FIX 1: wave execution runs independent phases concurrently, so every
        # mutation of the shared run state (self.state, store.save, report,
        # board mirror) is guarded by this engine-level lock. RLock, because
        # the guarded call sites re-enter each other (run_phase -> _checkpoint
        # -> _phase_state; run_phase -> report -> store.save).
        self._state_lock = threading.RLock()
        # FIX 5 (emitter): rows accepted into the durable jsonl that are still
        # waiting to be mirrored to the CC ingest route. Flushed (under the
        # state lock) by _emit_stage_timing at 100-row boundaries and on the
        # run_summary row; also flushed on every early run() exit and on a
        # phase crash so completed-phase telemetry is never stranded.
        self._telemetry_cc_pending: List[Dict[str, Any]] = []
        # FIX 25 (MASTER Part 8): the per-phase nonce file minted by the most
        # recent _script_nonce_env call; None once consumed/cleared.
        self._script_nonce_file: Optional[Path] = None

    # -- Option B child cards -----------------------------------------------
    def _child_card_meta(self, phase: Phase) -> Tuple[str, str]:
        """(title, description) for phase.id's Command Center child card."""
        return (
            f"{phase.id} — {phase.owning_role}",
            f"Phase {phase.id} of presentation build {self.run_dir.name}, "
            f"owned by {phase.owning_role}.",
        )

    # -- state helpers ----------------------------------------------------
    def _phase_state(self, pid: str) -> Dict[str, Any]:
        with self._state_lock:
            for ps in self.state.setdefault("phases", []):
                if ps["id"] == pid:
                    return ps
            ps = {"id": pid, "status": PHASE_STATUS_PENDING, "artifacts": [],
                  "sha256": {}, "attempts": 0, "heal_events": [],
                  "attested_at": None}
            self.state["phases"].append(ps)
            return ps

    def _checkpoint(self, pid: str, **fields: Any) -> None:
        """Invariant 3: called BEFORE an expensive call, and again after success."""
        with self._state_lock:
            ps = self._phase_state(pid)
            ps.update(fields)
            hb = self.state.setdefault("heartbeat", {})
            hb["last_checkpoint_at"] = utcnow()
            hb["current_phase"] = pid
            # The watchdog is read-only and must not resolve a manifest (Super Spec 8.3). The engine,
            # which already has the pinned Phase, writes the two numbers the watchdog needs.
            try:
                ph = self.manifest.phase_or_none(pid)
            except AttributeError:
                ph = None
            if ph is not None:
                hb["interval_minutes"] = ph.heartbeat_interval_minutes
                hb["budget_minutes"] = ph.budget_minutes
                hb["interval_source"] = ("manifest_heartbeat_minutes" if ph.heartbeat_minutes
                                         else "phase_budget_fallback")
            self.store.save(self.state)
            # FIX-20 (D19): checkpoint phase state to disk so a compaction that
            # drops in-memory history cannot lose it. Best-effort — a working-set
            # checkpoint failure must never block the phase loop (mirrors the
            # invariant-1 fail-soft discipline of the board mirror).
            # FIX 26 (MASTER Part 8): stat-only by default. A checkpoint that
            # reads every PNG's bytes on a 40-slide dir blew the 100 ms bar
            # inside P4-RENDER; the measurement is now stat-based (size +
            # mtime), and the real byte read happens ONLY on a phase-completion
            # checkpoint (fields["status"] == "done") where attestation needs
            # it. This keeps the hot loop under budget by construction.
            try:
                from . import workingset
                workingset.checkpoint_phase(
                    self.run_dir, pid, self.state, self.store,
                    hash_on_completion=bool(fields.get("status") == "done"))
            except Exception:  # noqa: BLE001
                pass

    # -- FIX 30: engine-written attestations --------------------------------
    def _engine_attest(self, phase: Phase, substance_verified: bool,
                       shas: Dict[str, str], method: str,
                       notes: Optional[List[str]] = None) -> None:
        """FIX 30 — attestations WRITTEN BY THE ENGINE.

        Every phase this engine marks done appends ONE row to
        working/checkpoints/process_manifest.json["phase_attestations"]:

          {phase_id, owning_role, status: "done", method,
           substance_verified, artifact_sha256, artifact_sha,
           attested_at (tz-aware ISO from the engine's own clock — never a
           placeholder T00:00:00),
           attested_by: "engine:<pid>"}

        attested_by is the WRITER IDENTITY the shared phase chain gate
        (build_deck.check_phase_preconditions) now requires: a row without an
        "engine:"-prefixed attested_by is a hand-edited / self-minted shape and
        satisfies nothing, even when it carries a completed status and
        substance_verified True. Both engine writers sign the same way — the
        engine above and run_signature_deck.attest_phase — so the ledger rows
        are indistinguishable-by-shape from hand rows only in the sense that a
        hand editor must forge the attested_by to launder one, and the
        artifact_sha256 (deterministic over the banked artifact set) plus the
        tz-aware timestamp make the row auditable.

        The read-modify-write runs under the engine lock, so concurrent wave
        siblings append without losing each other's rows (every checkpoint in
        this module is lock-guarded; the ledger write keeps the same
        discipline). Best-effort by contract at the END of a completed phase:
        a ledger write failure is loud on stderr and must never block a
        finished phase from reporting or the run from advancing — the row is
        skipped, remaining on stderr for the operator."""
        sha = _combined_artifact_sha(shas)
        row = {
            "phase_id": phase.id,
            "owning_role": phase.owning_role,
            "status": PHASE_STATUS_DONE,
            "method": method,
            "substance_verified": bool(substance_verified),
            "artifact_sha256": sha,
            "artifact_sha": sha,
            "attested_at": utcnow(),
            "attested_by": _ENGINE_ATTESTED_BY_PREFIX + str(os.getpid()),
        }
        if notes:
            row["notes"] = list(notes)
        try:
            with self._state_lock:
                mpath = _process_manifest_path(self.run_dir)
                obj = _load_process_manifest(self.run_dir)
                obj.setdefault("phase_attestations", [])
                obj["phase_attestations"].append(row)
                _atomic_write_json(mpath, obj)
        except Exception as exc:  # noqa: BLE001 — stamping must never block completion
            print(
                f"WARN: engine attestation for {phase.id} not written to "
                f"process_manifest.json: {exc!r}",
                file=sys.stderr)

    # -- fix/run-slides: converter routing ---------------------------------
    # ROOT CAUSE (live run pj_34a56a26caca04532ec6e9cba6, 2026-08-18): P-CONVERTER
    # (manifest order -1) declares "converter_path": true and a routing_note of
    # "Content-first path only" -- but nothing in this package ever read either
    # field, so every deck, including a from_scratch deck with no source to
    # convert, walked straight into P-CONVERTER's substance verifier, which
    # then demanded a "slides" key inside working/copy/intake.json that NO
    # writer in this codebase (production or otherwise) ever produces -- the
    # owning role's own SOP (content-to-presentation-architect/how-to.md line
    # 25: "You never build slides yourself... Your single deliverable is the
    # source-derived presentation brief") confirms this phase's real output is
    # a source brief, not a "slides" key, and that it only applies when a
    # content source exists at all (creation_mode content_personal /
    # content_general -- build_deck.py:8212 CREATION_MODES). This is a
    # dispatch/routing defect, not a substance-check defect: the fix routes
    # converter-only phases around a from_scratch deck instead of touching
    # what the substance check demands of a deck the phase actually applies to.
    _CONTENT_FIRST_CREATION_MODES = ("content_personal", "content_general")

    def _deck_creation_mode(self) -> Optional[str]:
        """Best-effort read of working/copy/intake.json's creation_mode.

        Returns None on ANY absence/parse failure -- a routing decision that
        depends on this must NEVER skip a phase on missing information, only
        on a positively-read, confirmed creation_mode. This mirrors the
        fail-open-to-full-enforcement posture the rest of this module already
        uses (e.g. _artifacts_present, the substance verifier's FAIL-HARD
        rule): when in doubt, the phase still runs and still has to earn its
        pass the normal way.
        """
        p = self.run_dir / "working" / "copy" / "intake.json"
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(obj, dict):
            return None
        val = obj.get("creation_mode")
        return val if isinstance(val, str) and val else None

    # -- B2b: CLIENT-FACING deck-shape + step-count/message rendering -------
    def _client_deck_shape(self) -> Dict[str, Any]:
        """Best-effort read of intake.json's deck-shape signals for
        CLIENT-FACING messages/counts ONLY (mirrors
        run_signature_deck._client_deck_shape 1:1). `*_known` is False
        whenever this run's intake.json does not yet declare that signal;
        callers MUST treat known=False as "do not filter on this signal" --
        never guess (same fail-safe rule as _deck_creation_mode above)."""
        p = self.run_dir / "working" / "copy" / "intake.json"
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            obj = {}
        if not isinstance(obj, dict):
            obj = {}
        deck_type = str(obj.get("deck_type") or "").strip()
        creation_mode = str(obj.get("creation_mode") or "").strip()
        pre_capture = obj.get("pre_presentation_capture")
        if not isinstance(pre_capture, dict):
            pre_capture = {}
        sales_checkout = str(pre_capture.get("WANT_SALES_CHECKOUT") or "").strip().lower()
        vsl_page = str(pre_capture.get("WANT_VSL_PAGE") or "").strip().lower()
        return {
            "deck_type_known": bool(deck_type),
            "is_signature": deck_type == "signature_presentation",
            "creation_mode_known": bool(creation_mode),
            "is_content_first": creation_mode in self._CONTENT_FIRST_CREATION_MODES,
            "sales_checkout_known": bool(sales_checkout),
            "wants_sales_checkout": sales_checkout == "yes",
            "vsl_known": bool(vsl_page),
            "wants_vsl": vsl_page == "yes",
        }

    def _client_visible_phases(self, phases: List[Phase]) -> List[Phase]:
        """The subset of `phases` (kept in manifest `order`) a CLIENT should
        be told about for THIS run's deck shape -- filters out only the
        phases that do no real work on this deck (defer-unless-applicable,
        per FABLE-TRUTH SS1 / MASTER-WORK-ORDER B2/B2b). Returns the full
        input unchanged whenever a signal is not yet knowable (fail-safe).

        Does NOT change `phases` itself, the attestation chain, the DAG, or
        anything the phase walk/dispatch loop iterates -- this is
        display-only, consumed solely by the ack message and
        _render_client_report_msg's per-phase {k}/{N}."""
        shape = self._client_deck_shape()
        ordered = sorted(phases, key=lambda p: p.order)
        visible = []
        for ph in ordered:
            if ph.id in _CONVERTER_ONLY_PHASE_IDS:
                if shape["creation_mode_known"] and not shape["is_content_first"]:
                    continue  # positively known non-content-first deck: no-ops
            elif ph.id in _SP_ONLY_PHASE_IDS:
                if shape["deck_type_known"] and not shape["is_signature"]:
                    continue  # positively known non-signature deck: no-ops
            elif ph.id in _SALES_CHECKOUT_ONLY_PHASE_IDS:
                if shape["sales_checkout_known"] and not shape["wants_sales_checkout"]:
                    continue  # positively known decline: no-ops
            elif ph.id in _VSL_ONLY_PHASE_IDS:
                if shape["vsl_known"] and not shape["wants_vsl"]:
                    continue  # positively known decline: no-ops
            else:
                # defers_unless-gated optional phase (DESIGN-OPUS §4, merged
                # 2026-09-01): visible ONLY when this run's intake proves the
                # gate open. Fail-safe: no intake record or unevaluable gate
                # keeps the phase visible (unknown widens).
                gate = getattr(ph, "defers_unless", None)
                if gate:
                    intake = self.state.get("intake") if isinstance(self.state, dict) else None
                    if not isinstance(intake, dict) or not intake:
                        intake = load_intake(self.run_dir)
                    if intake:
                        from .defers import evaluate_defers_unless
                        try:
                            if not evaluate_defers_unless(gate, intake):
                                continue  # provably deferred by intake
                        except Exception:
                            pass  # cannot prove closed -> keep visible
            visible.append(ph)
        return visible

    def _client_phase_index(self, phase_id: str,
                            phases: List[Phase]) -> Tuple[Optional[int], int]:
        """CLIENT-FACING (k, N) for phase_id against THIS deck's filtered
        client-visible phase list. k is None when phase_id is being
        walked/attested (the 36-phase enforcement never skips it) but is NOT
        one of the N steps this deck's client was told to expect -- e.g.
        P-CONVERTER dispatched on a non-content-conversion deck, or an
        SP-only phase on a non-signature deck. N is always the filtered
        count (len(_client_visible_phases(...)))."""
        visible = self._client_visible_phases(phases)
        for i, ph in enumerate(visible):
            if ph.id == phase_id:
                return i + 1, len(visible)
        return None, len(visible)

    def _render_client_report_msg(self, phase: Phase, kind: str) -> str:
        """Render phase.client_report's start/done template for the client,
        substituting {k}/{N}/{name}/{eta} for real -- NEVER hands a manifest
        template to the client with its braces unformatted (see the B2b
        block above PhaseExecutorContractError). kind in {"start", "done"}.

        Fails safe in three independent ways:
          1. deck shape unknown  -> _client_visible_phases widens N to the
             full 36-phase superset instead of asserting a smaller number.
          2. phase_id not one of this deck's visible steps (k is None) ->
             honest "not part of the N-step plan" wording, never a
             fabricated step number (same branch run_signature_deck.py's
             emit_client_report uses for the identical case).
          3. a malformed manifest template (stray brace) -> caught and
             replaced with the plain default message, never raised, never
             leaked partially-formatted.
        """
        tmpl_key = "start_template" if kind == "start" else "done_template"
        default = (f"Starting {phase.id} ({phase.owning_role})" if kind == "start"
                   else f"{phase.id} complete")
        tmpl = phase.client_report.get(tmpl_key) or default
        if "{" not in tmpl:
            return tmpl  # nothing to substitute (default string, or a static template)
        k, n = self._client_phase_index(phase.id, self.manifest.phases)
        if k is None:
            return (f"{phase.id} — not part of the {n}-step plan for this deck type "
                    f"(internal housekeeping phase, no client-visible step number) — "
                    f"{'starting' if kind == 'start' else 'complete'}")
        eta_val = phase.client_report.get("eta_minutes") or phase.client_report.get("eta")
        eta_str = f" (ETA ~{eta_val} min)" if (kind == "start" and eta_val) else ""
        fields = _SafeFormatDict(k=k, N=n, name=(phase.name or phase.id), eta=eta_str)
        try:
            return tmpl.format_map(fields)
        except (ValueError, IndexError):
            # Malformed template syntax (e.g. a stray unmatched '{' or '}') --
            # never let a bad template string reach the client verbatim, and
            # never crash phase reporting over it.
            return default

    def _route_around_converter_phase(self, phase: Phase, creation_mode: str) -> None:
        """Record a converter_path phase as not applicable to this deck, WITHOUT
        running its executor or its substance verifier, and WITHOUT disguising
        the routing decision as a genuine execution.

        This is not an owner_skip_approval bypass (that mechanism silences a
        gate that fired; this phase's gate never fires at all, because the
        phase itself does not apply). status="done" so certificate/gap/
        all_done accounting stays consistent with a deck that never had this
        phase's precondition to begin with -- but `routed_around` +
        `routed_around_reason` make the distinction from a real, verified
        execution fully auditable, permanently, in state.json and the event
        log. verifier_ok stays None (never checked, not "checked and passed")
        and artifacts stays empty (nothing was produced), so
        _mint_process_certificate's substance_unverified scan
        (verifier_ok is None and artifacts) does not misflag it either.
        """
        reason = (f"creation_mode={creation_mode!r} — {phase.id} declares "
                  "converter_path:true (\"Content-first path only\"); not "
                  "applicable to this deck, so it was never dispatched")
        self.report.event("phase.routed_around", f"{phase.id}: {reason}")
        self._checkpoint(phase.id, status=PHASE_STATUS_DONE, attested_at=utcnow(),
                         artifacts=[], sha256={}, verifier_ok=None,
                         verifier_notes=[f"NOTE: {reason}"],
                         owner_skip_approval=None, routed_around=True,
                         routed_around_reason=reason,
                         intake_sha_at_done=_intake_sha_now(self.run_dir))
        # FIX 30 — a routed-around phase is also 'completed': it gets an engine
        # row too, honestly marked (never verified, no artifact). Its
        # substance_verified=False means the shared chain gate does NOT count it
        # as attested — the routing distinction stays auditable in the row and
        # in state.json, exactly as the method docstring promises.
        self._engine_attest(
            phase,
            substance_verified=False,
            shas={},
            method="engine_routed_around",
            notes=[f"NOTE: {reason}"])

    # -- verification -----------------------------------------------------
    def _artifacts_present(self, phase: Phase) -> Tuple[bool, List[str]]:
        # U01-R2 (QC FAIL 6.46): the phase's raw produces_artifact may carry
        # {deck_slug}/{run_dir} tokens (P8.25-WORKBOOK declares
        # 'working/deliverables/{deck_slug}-WORKBOOK.pdf + {deck_slug}-WORKBOOK-FILLABLE.pdf').
        # Resolve EVERY pattern through phase.resolve_artifact_patterns(run_dir) BEFORE
        # globbing/existence checks -- the literal token path never exists on disk and
        # previously hard-blocked the phase despite real workbook PDFs being present.
        #
        # FIX 107 — ONE artifact resolver for engine and verifiers. This engine-side
        # check used to hand-mirror the verifier's resolver (the F60 working/upsell
        # retry was a copy of _pu_artifact_paths logic) and the two copies DRIFTED:
        # the mirror handled files only, so the P-U-COLLATERAL dir-glob pattern
        # ('delivery/upsell/*') sat "missing" engine-side while the very same
        # pattern resolved and PASSED in the verifier — the final phase waiting
        # forever on its own PASS, again. phase_verifiers.artifact_path() is now
        # the single resolution rule (same ordering: literal run-dir path first,
        # then the working/upsell/ convention; '/*' resolves to the non-empty
        # upsell dir), and both sides go through it. The engine keeps ONLY the
        # token substitution and 'a + b' splitting, which belong to the manifest
        # spelling, not to path resolution.
        try:
            import phase_verifiers
        except ImportError:  # degraded CI context: no verifier module beside the runner
            phase_verifiers = None  # type: ignore[assignment]
        missing: List[str] = []
        for rel in phase.resolve_artifact_patterns(self.run_dir):
            # Manifest 'a + b' multi-artifact spelling (same expansion the
            # verifier's _pu_artifact_paths applies).
            parts = [p.strip() for p in rel.split(" + ")] if " + " in rel else [rel]
            for part in parts:
                if phase_verifiers is not None:
                    if phase_verifiers.artifact_path(self.run_dir, part) is not None:
                        continue
                    missing.append(part)
                    continue
                # Degraded fallback (verifier module absent): literal path, then
                # the working/upsell/ convention — never a silent pass.
                if (self.run_dir / part).exists() \
                        or (self.run_dir / "working" / "upsell" / part).is_file():
                    continue
                missing.append(part)
        return (not missing), missing

    def _phase_is_gate_declined(self, phase: Phase) -> bool:
        """True when the phase's own substance verifier returns a PASS whose
        reason names a gate decline (defer/waived) — the phase legitimately
        made no artifact because the client declined the upsell, and must be
        checkpointed deferred, never regenerated or blocked (F59)."""
        try:
            import phase_verifiers
            ok, notes = phase_verifiers.verify(phase.id, self.run_dir)
        except Exception:  # noqa: BLE001 — verifier unusable: not a decline
            return False
        if not ok:
            return False
        joined = "; ".join(notes or []).lower()
        return ("defer" in joined or "waived" in joined) and ("gate" in joined
                or "declined" in joined)

    def _revalidate_banked(self, phase: Phase, ps: Dict[str, Any]) -> List[str]:
        """Return a list of human-readable reasons, empty when every banked artifact is still good."""
        bad = []
        shas = ps.get("sha256") or {}
        for rel in (ps.get("artifacts") or []):
            ok, why = validate_artifact(self.run_dir, rel, self.manifest,
                                        recorded_sha=shas.get(rel))
            if not ok:
                bad.append(f"{rel}: {why}")
        if not (ps.get("artifacts") or []) and phase.resolve_artifact_patterns(self.run_dir):
            bad.append("phase recorded status=done with an empty artifact list")
        return bad

    # -- executors --------------------------------------------------------
    def _telemetry_dir(self) -> Path:
        """FIX 5: durable per-stage timing telemetry location."""
        return self.run_dir / "working" / "telemetry"

    def _emit_stage_timing(self, record: Dict[str, Any]) -> None:
        """FIX 5: append one stage-timing row to working/telemetry/stage-timings.jsonl.

        Best-effort: telemetry must NEVER break a run. On write failure the row is
        dropped with a printed warning (visible in engine output, not silent).
        A row successfully appended to the jsonl is ALSO queued for the CC mirror
        POST (_post_stage_timings_cc) — the file remains the durable source of
        truth, the POST is only a mirror; queue flush failures never raise.
        """
        try:
            tdir = self._telemetry_dir()
            tdir.mkdir(parents=True, exist_ok=True)
            with (tdir / "stage-timings.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, sort_keys=True) + "\n")
        except OSError as exc:
            print(f"WARN telemetry: could not write stage timing: {exc}", flush=True)
            return
        with self._state_lock:
            self._telemetry_cc_pending.append(record)
            if len(self._telemetry_cc_pending) >= 100:
                self._flush_telemetry_cc()

    def _flush_telemetry_cc(self) -> None:
        """FIX 5 (emitter): drain the pending CC mirror queue as one batched POST
        (or several 100-row chunks). Expected to be called holding the state lock;
        the POST itself is fire-and-forget so a slow/unreachable CC never blocks
        the phase loop past the socket timeout. Never raises."""
        rows = list(self._telemetry_cc_pending)
        self._telemetry_cc_pending = []
        if rows:
            _post_stage_timings_cc(rows)

    def run_phase_timed(self, phase: Phase, wave: int = 0) -> int:
        """FIX 5: telemetry wrapper around run_phase.

        Emits ONE phase_exit row per run_phase call covering every exit path
        (done, blocked, gate-blocked, crash escape) with duration measured on
        time.monotonic(). Telemetry never alters the return code, and never
        raises: a telemetry failure must not be able to break a run.
        """
        started_t = time.monotonic()
        started_iso = utcnow()
        try:
            rc = self.run_phase(phase)
        except BaseException as exc:
            self._emit_stage_timing({
                "run_id": self.run_dir.name,
                "phase_id": phase.id,
                "wave": wave,
                "model_used": None,
                "event": "phase_exit",
                "started_at": started_iso,
                "ended_at": utcnow(),
                "duration_s": round(time.monotonic() - started_t, 3),
                "status": "crashed",
                "error_class": type(exc).__name__,
            })
            with self._state_lock:
                # FIX 5 (emitter): a crashing phase is THIS process's last
                # chance to flush completed-phase telemetry — drain the mirror
                # queue on the way out (best-effort, cannot mask the crash).
                self._flush_telemetry_cc()
            raise
        self._emit_stage_timing({
            "run_id": self.run_dir.name,
            "phase_id": phase.id,
            "wave": wave,
            "model_used": None,
            "event": "phase_exit",
            "started_at": started_iso,
            "ended_at": utcnow(),
            "duration_s": round(time.monotonic() - started_t, 3),
            "status": {EXIT_OK: "done"}.get(rc, f"nonzero_rc_{rc}"),
            "return_code": rc,
        })
        return rc

    def run_phase(self, phase: Phase) -> int:
        ps = self._phase_state(phase.id)
        # FIX 109 (wave-B3, judge defect a): the intake provenance check runs
        # BEFORE the done-skip. A DONE consumer whose banked artifacts are
        # still byte-valid was previously skipped here (EXIT_OK) before any
        # gate ran — so an approval-path intake rewrite never re-ran it on the
        # new intake unless some LATER pending phase happened to fire the
        # gate. The gate's _check_intake_provenance is where consumer
        # invalidation lands in self.state; running it first makes the
        # done-skip below see the post-invalidation record and re-run the
        # phase. A refusal (out-of-band edit) blocks every phase exactly as
        # the gate would have — fail-closed, naming the sha.
        with self._state_lock:
            prov_rc = self._check_intake_provenance(phase)
        if prov_rc is not None:
            return prov_rc
        with self._state_lock:
            if ps.get("status") == PHASE_STATUS_DONE:
                bad = self._revalidate_banked(phase, ps)
                if not bad:
                    print(f"SKIP {phase.id}: already done, {len(ps.get('artifacts', []))} artifact(s) "
                          f"re-validated (resuming reuses banked work)", flush=True)
                    return EXIT_OK
                self.report.event(
                    "phase.banked_invalid",
                    f"{phase.id} was marked done but {len(bad)} banked artifact(s) no longer validate: "
                    + "; ".join(bad) + " -- re-running this phase.")
                self._checkpoint(phase.id, status=PHASE_STATUS_PENDING, banked_invalid=bad)

            gate_rc = self._check_intake_gate(phase)
            if gate_rc is not None:
                return gate_rc

            self.state["current_phase"] = phase.id
            self.state.setdefault("heartbeat", {})["phase_started_at"] = utcnow()
            self._checkpoint(phase.id, status=PHASE_STATUS_RUNNING,
                             attempts=ps.get("attempts", 0) + 1)

            start_msg = self._render_client_report_msg(phase, "start")
            self.report.to_requester("progress", start_msg)

        try:
            persona.resolve_for_phase(self.run_dir, phase.id)
        except (RuntimeError, TimeoutError) as exc:
            return self._fail_unit(phase, f"persona governance: {exc}")

        with self._state_lock:
            if phase.id == "P4-RENDER" and self.board:
                self.board.mark_in_progress()

        if phase.executor_kind == "script":
            rc = self._run_script_phase(phase)
        elif phase.executor_kind == "agent":
            rc = self._run_agent_phase(phase)
        elif phase.executor_kind == "human":
            # FIX 29 (MASTER Part 8, W05+W07): a declared human executor is a
            # REAL executor kind now, never the install-time error the old
            # fall-through called it. P-STYLE-PICK (order 4.86, kind human) is
            # the owner gateway stage: deliver the pick request, wait for the
            # owner's choice file with a verified owner_msg_id, and auto-pick
            # variant 1 only when the client's own intake opted in
            # (intake.style_pick_auto: true) and the wait times out. See
            # _run_human_phase for the full contract.
            rc = self._run_human_phase(phase)
        else:
            with self._state_lock:
                self.report.event("phase.no_executor",
                                  f"{phase.id} declares no executor. This is an install-time error "
                                  "once fix A3 is enforced; blocking rather than skipping.")
            return self._block(phase, "no executor is defined for this phase")

        if rc == EXIT_OK:
            ok, missing = self._artifacts_present(phase)
            if not ok:
                # F59 (SMOKE-1, 2026-09-01): a gate-decline script phase (the
                # upsell-BUILD phases P-U-VSL-BUILD / P-U-SALES-BUILD /
                # P-U-CHECKOUT-BUILD / P-U-FORM-CHECKOUT) runs a CONDITIONAL
                # executor: when the client declined the option (e.g.
                # want_vsl_page == "no") the executor resolves its gate to
                # WAIVED/DEFER and exits 0 WITHOUT writing produces_artifact.
                # The artifact-presence pre-check used to fire REGENERATION on
                # that (run64: "regeneration reported success but produced
                # nothing: missing working/vsl/html/vsl.html") -- an infinite
                # block on a phase that is legitimately declined. The phase's
                # OWN substance verifier is the authority on the gate: it
                # already returns PASS for defer/waived (see
                # _verify_upsell_vsl_build etc. -- "NOTE: ... {defer,waived} --
                # gated OUT (not a failure)"). So BEFORE regenerating, consult
                # the verifier: a PASS whose NOTE names a gate decline means
                # this phase is deferred-by-design, not missing a product.
                if self._phase_is_gate_declined(phase):
                    with self._state_lock:
                        self._checkpoint(phase.id, status=PHASE_STATUS_DEFERRED,
                                         deferred_reason=(
                                             "decline-gated (WANT_VSL_PAGE / "
                                             "WANT_SALES_CHECKOUT = no) — conditional "
                                             "executor resolved WAIVED/DEFER, no artifact "
                                             "by design"))
                        self.report.event(
                            "phase.deferred",
                            f"{phase.id} deferred — client declined this upsell; "
                            "the conditional executor produced no artifact by design.")
                        print(f"DEFER {phase.id}: gate resolved to decline "
                              "(WAIVED/DEFER) — no artifact produced, deferred by "
                              "design.", flush=True)
                    return EXIT_OK
                with self._state_lock:
                    # heal internals record events + checkpoints — held under
                    # the engine lock; a rare regeneration serializes its wave
                    # rather than risk a torn state save.
                    # FIX 10: classify first. A PROVIDER error at the
                    # artifact-presence stage (the executor died on a provider
                    # refusal) takes the alternate-provider rung; everything
                    # else (missing input / transient) takes the regenerate
                    # rung as before.
                    miss_reason = f"missing {', '.join(missing)}"
                    if heal.classify_failure(miss_reason) == heal.FAILURE_PROVIDER_ERROR:
                        rc2 = heal.rung2_provider_failover(
                            self, phase, miss_reason,
                            child_env=self._script_nonce_env(phase))
                    else:
                        heal._ledger(self, phase=phase.id, rung=2, attempt=0,
                                     failure_class=heal.classify_failure(miss_reason),
                                     reason=miss_reason, route_change=False,
                                     outcome="rung2_regenerate")
                        rc2 = heal.rung2_regenerate(self, phase, miss_reason,
                                                    child_env=self._script_nonce_env(phase))
                if rc2 != EXIT_OK:
                    return self._fail_unit(phase, f"produced no artifact after "
                                                  f"{heal.HEAL_CAP_REGENERATE} regeneration attempt(s): "
                                                  f"missing {', '.join(missing)}")
                ok, missing = self._artifacts_present(phase)
                if not ok:
                    return self._fail_unit(phase, f"regeneration reported success but produced "
                                                  f"nothing: missing {', '.join(missing)}")
            shas = {}
            # U01-R2: resolve tokens before globbing -- same rule as _artifacts_present,
            # so the banked sha256 list covers the RESOLVED files, never the literal
            # {deck_slug} path.
            for rel in phase.resolve_artifact_patterns(self.run_dir):
                for m in self.run_dir.glob(rel) if any(c in rel for c in "*?[") else [self.run_dir / rel]:
                    if m.is_file():
                        shas[str(m.relative_to(self.run_dir))] = sha256_file(m)
            # F4 (warn-mode): substance verifier runs after artifact presence, before done checkpoint.
            # WORK-ITEM-14 (R3 U03): a FAILING substance verifier no longer records a warning
            # and advances. It BLOCKS the phase (parked resumable) unless an AUTHENTIC
            # owner_skip_approval token covers this exact phase.
            # R3 U03-R2 (QC FAIL 8.00): the ONLY authentic source is the operator-signed
            # waivers.json ledger (validated against the client's own recorded words by
            # waivers.validate_waiver — client_request_quote + captured_at + issuer).
            # A token found in this run's own process_manifest.json is a self-mint and
            # authorizes nothing; owner_skip_approval_authorizes returns None and appends
            # an AF-FORGED-APPROVAL reason (naming the missing authenticity field) to the
            # live verifier_notes list, so the block message carries it.
            # The credential-dependent allowed_simulated exception stays — it degrades the
            # verifier to a NOTE pass inside phase_verifiers.verify(), so it never reaches
            # this branch.
            verifier_ok = None
            verifier_notes = None
            verifier_skipped = None
            try:
                import phase_verifiers
                verifier_ok, verifier_notes = phase_verifiers.verify(phase.id, self.run_dir)
                if not verifier_ok:
                    # Mechanical gate: a substance FAIL parks the phase unless the owner has
                    # recorded an authentic skip-approval waiver for this exact phase
                    # (waivers.json, rule mapped to the phase id).  Rejection reasons are
                    # appended to verifier_notes in place by the authorizer.
                    token = phase_verifiers.owner_skip_approval_authorizes(
                        phase.id, verifier_notes, self.run_dir)
                    if token is not None:
                        verifier_skipped = token
                        with self._state_lock:
                            self.report.event(
                                "phase.verifier_skipped",
                                f"{phase.id}: substance check failed ({'; '.join(verifier_notes)}) "
                                f"but an owner_skip_approval token ({token.get('gate') or token.get('phase_id')}) "
                                f"recorded by {token.get('approved_by')} authorizes the skip")
                    else:
                        with self._state_lock:
                            self.report.event("phase.verifier_block",
                                              f"{phase.id}: {'; '.join(verifier_notes)}")
                        # FIX 10: the verifier's message IS the heal reason.
                        # Record it on the phase record (last_verifier_notes)
                        # so the regeneration and any human reading state.json
                        # see exactly what substance failed, ledger the class,
                        # then take the regenerate rung ONCE with the notes
                        # appended; a second substance failure quarantines.
                        sub_reason = (f"substance check failed: "
                                      f"{'; '.join(verifier_notes)}.")
                        with self._state_lock:
                            ps = self._phase_state(phase.id)
                            ps["last_verifier_notes"] = list(verifier_notes or [])
                            heal._ledger(self, phase=phase.id, rung=2, attempt=0,
                                         failure_class=heal.classify_failure(sub_reason),
                                         reason=sub_reason, route_change=False,
                                         outcome="rung2_regenerate")
                        if not ps.get("verifier_regen_done"):
                            with self._state_lock:
                                self._checkpoint(phase.id,
                                                 verifier_regen_done=True)
                            rc2 = heal.rung2_regenerate(
                                self, phase, sub_reason,
                                child_env=(self._script_nonce_env(phase)
                                           if phase.executor_kind == "script"
                                           else None))
                            if rc2 == EXIT_OK:
                                return self.run_phase(phase)
                        return self._fail_unit(
                            phase,
                            f"substance check failed: {'; '.join(verifier_notes)}. "
                            "An owner_skip_approval token for this phase is required to "
                            "advance it to done.")
            except ImportError as exc:
                # FIX 17 (fail-closed): the OLD behaviour here warned and SKIPPED the
                # substance check, then fell through to the status="done" checkpoint
                # below -- attesting a phase whose substance was never verified. An
                # unavailable verifier aborts the run instead: the raise propagates
                # through run_phase_timed (telemetry records the crash) and run(),
                # and the done checkpoint below is never reached, so no attestation
                # is minted.
                self.report.event(
                    "phase.verifier_unavailable",
                    f"{phase.id}: phase_verifiers not importable -- aborting before "
                    f"any attestation is minted ({exc})")
                raise VerifierImportError(
                    f"substance verifier import failed for {phase.id}: {exc} "
                    "(FIX 17: the run aborts instead of advancing unverified)") from exc
            self._checkpoint(phase.id, status=PHASE_STATUS_DONE, attested_at=utcnow(),
                             sha256=shas, artifacts=sorted(shas.keys()),
                             verifier_ok=verifier_ok, verifier_notes=verifier_notes,
                             owner_skip_approval=verifier_skipped,
                             intake_sha_at_done=_intake_sha_now(self.run_dir))
            # FIX 30 — the engine itself writes the attestation row on done.
            # Runs BEFORE the (heavier) board/report work so a crash between
            # this checkpoint and the report can never leave a checked-out
            # phase with no ledger row.
            self._engine_attest(
                phase,
                substance_verified=bool(verifier_ok),
                shas=shas,
                method="engine_done")
            done_msg = self._render_client_report_msg(phase, "done")
            with self._state_lock:
                self.report.to_requester("progress", done_msg)
                if self.board:
                    self.board.phase_progress(phase.id, done_msg)
                    # Option B: the phase's verifier has already passed by this point
                    # (a failing verifier returns via _block() above, never reaching
                    # here) -- so this phase's FIRST progress report both mints its
                    # child card (idempotent, see BoardMirror.child_report) and closes
                    # it 'done' in the same call.
                    title, description = self._child_card_meta(phase)
                    self.board.child_report(phase.id, title, description, "done", done_msg)
        return rc

    def _intake_gate_applies(self, phase: Phase) -> bool:
        """AF-INTAKE-GATE (Ticket 6): does `phase` need working/copy/intake.json
        to already exist before it is allowed to start?

        A manifest that declares no phase producing intake.json at all does not
        model the intake concept -- most existing tests build narrow, single- or
        few-phase synthetic manifests to exercise unrelated behavior (checkpoint
        persistence, working-set measurement, ...) and never write intake.json;
        the gate is a deliberate no-op there, never a false block.

        Within a manifest that DOES declare an intake producer, a phase is
        exempt only if it IS a declared producer itself (P0A-INTAKE / P-CONVERTER
        / P-SP-CLAIM all (re)write this same file -- gating them would deadlock
        the pipeline against its own intake step) or if its own order sits at or
        before the LATEST declared producer's order (P-0.5-RESEARCH, order -0.5,
        runs before P0A-INTAKE, order 0.1, in the standard from-scratch walk --
        every routing variant this manifest declares puts every producer at or
        below order 0.14, so <= that ceiling is the whole "Phase 0" cluster).
        Every phase past that ceiling reads intake.json's content directly or
        depends on a downstream artifact that does, so it is gated for real.
        """
        producer_orders = [p.order for p in self.manifest.phases
                            if _INTAKE_ARTIFACT in p.produces_artifact]
        if not producer_orders:
            return False
        if _INTAKE_ARTIFACT in phase.produces_artifact:
            return False
        return phase.order > max(producer_orders)

    def _check_intake_provenance(self, phase: Phase) -> Optional[int]:
        """FIX 109 — the engine-side intake provenance pre-phase check.

        intake.json is the trust root: only the intake phase and the owner's
        approval path may write it, and every sanctioned write appends a row
        {writer_phase, writer_pid, ts, sha_before, sha_after} to
        working/checkpoints/intake.provenance.jsonl (via runfacts).
        Before ANY phase runs, the engine checks the CURRENT intake sha:

          1. no provenance row ends at the current sha -> the file was edited
             out-of-band (a leftover worker / a shell edit) and EVERY phase
             refuses, naming the sha (AF-INTAKE-PROVENANCE). This is
             fail-closed: the sanctioned rewrite through the approval path
             (resolve_intake.py / deck-intake-driver.py) appends the missing
             row and unblocks the run.
          2. provenance OK but the intake was re-written after some phase
             banked -> every DONE phase whose manifest consumes[] includes
             intake.json is invalidated (reset to pending) HERE, so the
             engine re-runs exactly those consumers on the new intake
             instead of failing later on artifacts built from the old one.

        Runs for every phase (including intake producers and phases the
        AF-INTAKE-GATE does not apply to): an out-of-band edit must block
        the whole run, not only the content-authoring phases. No provenance
        log at all (a pre-FIX-109 run) stays allowed — the regime activates
        the moment the first sanctioned write lands its row. Import failure
        of runfacts is fail-closed loud, never a silent pass."""
        try:
            from . import runfacts as _rf
        except ImportError:
            try:
                import runfacts as _rf  # type: ignore[no-redef]
            except ImportError:
                print(
                    "AF-INTAKE-PROVENANCE: presentation_job.runfacts could not be "
                    "imported — the intake provenance check cannot run and every "
                    "phase is refused (fail-closed). Fix the engine install.",
                    file=sys.stderr)
                return self._block(
                    phase,
                    "AF-INTAKE-PROVENANCE: runfacts unavailable — refusing to "
                    "run without the intake provenance check (fail-closed).")
        try:
            ok, why, invalidated = _rf.check_intake_provenance(
                self.run_dir, manifest_path=self.manifest.path)
        except Exception as exc:  # noqa: BLE001 — fail closed, never crash the loop
            return self._block(
                phase,
                f"AF-INTAKE-PROVENANCE: the intake provenance check itself failed "
                f"({exc!r}) — refusing to run against an unverifiable intake.")
        if not ok:
            return self._block(phase, why)
        if invalidated:
            print(f"FIX 109: intake re-written — invalidated {len(invalidated)} "
                  f"consuming phase(s), they re-run on the new intake: "
                  f"{', '.join(invalidated)}", flush=True)
            # FIX 109 (wave-B3, judge defect b): runfacts.invalidate_intake_
            # consumers() reset those phases to pending ON DISK, but this
            # engine's authoritative copy is self.state — and the report.event
            # loop below saves self.state right back over state.json, silently
            # resurrecting every consumer the disk rewrite just invalidated.
            # The next SKIP in run_phase then serves stale banked artifacts
            # built from the OLD intake. So apply the invalidation to the
            # in-memory phase records FIRST, under the state lock, and only
            # then report — the event saves the already-invalidated state.
            with self._state_lock:
                by_id = {ps.get("id"): ps
                         for ps in self.state.get("phases", []) if isinstance(ps, dict)}
                for pid in invalidated:
                    ps = by_id.get(pid)
                    if ps is None or ps.get("status") != PHASE_STATUS_DONE:
                        continue
                    ps["status"] = PHASE_STATUS_PENDING
                    ps["intake_invalidated"] = {
                        "reason": "intake.json re-written through the approval "
                                  "path after this phase banked; banked artifacts "
                                  "invalidated — the phase re-runs on the new intake",
                    }
                    ps["artifacts"] = []
                    ps["sha256"] = {}
                self.store.save(self.state)
            for pid in invalidated:
                self.report.event(
                    "phase.intake_invalidated",
                    f"{pid}: banked artifacts invalidated — intake.json was "
                    "re-written through the approval path after this phase "
                    "banked; the phase re-runs on the new intake.")
        return None

    def _check_intake_gate(self, phase: Phase) -> Optional[int]:
        """AF-INTAKE-GATE (Ticket 6): fail-closed pre-check run before any phase
        this manifest doesn't exempt (see _intake_gate_applies) is allowed to
        start. Refuses to author content -- priority-shift spec, arc allocation,
        slide copy, renders, deliverables, all of it -- without a completed
        client intake on disk. Returns a block exit code on failure, None when
        the gate passes (or does not apply) and the caller should proceed."""
        # FIX 109: the provenance gate runs FIRST, for every phase — an
        # out-of-band intake edit blocks the whole run before any other check.
        prov_rc = self._check_intake_provenance(phase)
        if prov_rc is not None:
            return prov_rc
        if not self._intake_gate_applies(phase):
            return None
        intake_path = self.run_dir / "working" / "copy" / "intake.json"
        if not intake_path.is_file():
            return self._block(
                phase,
                "AF-INTAKE-GATE: working/copy/intake.json missing — client "
                "intake (Phase 0) has not completed; refusing to author "
                "content without client data.")
        try:
            intake = json.loads(intake_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return self._block(
                phase,
                f"AF-INTAKE-GATE: working/copy/intake.json is unreadable or "
                f"not valid JSON ({exc}) — client intake (Phase 0) has not "
                "completed; refusing to author content without client data.")
        if not intake:
            return self._block(
                phase,
                "AF-INTAKE-GATE: working/copy/intake.json is empty — client "
                "intake (Phase 0) has not completed; refusing to author "
                "content without client data.")
        return None


    def _build_executor_argv(self, raw_cmd: Optional[str], phase_id: str) -> List[str]:
        """U069: tokenise FIRST, substitute SECOND.

        This is the ONLY sanctioned way to turn a manifest executor.cmd (or
        alt_cmd) into an argv anywhere in this package. `run_dir` can contain
        arbitrary characters (it is derived from client-controlled intake
        text upstream) -- if it were substituted into a raw command string
        before that string is split, a run_dir crafted with shell metacharacters
        would be re-interpreted as shell syntax. Splitting first means
        substitution only ever lands inside an already-tokenised argument,
        so it can never introduce a new token or an operator.

        heal.py's retry rungs (rung2_regenerate, rung3_alt_route) MUST call
        this too instead of re-deriving a command themselves -- that
        duplication is exactly how U069's original fix in this method left a
        live bypass in the retry path.
        """
        raw = raw_cmd or ""
        try:
            argv = shlex.split(raw)
        except ValueError as exc:
            raise PhaseExecutorContractError(
                f"phase {phase_id}: executor.cmd is not a valid argument vector "
                f"({exc}). Fix the manifest; this is not sanitised for you."
            ) from exc
        run_dir_str = str(self.run_dir)
        tokens = [run_dir_str if tok == "{run_dir}" else tok.replace("{run_dir}", run_dir_str)
                  for tok in argv]
        # D2 (canary DEFECT D2): resolve relative scripts/xxxx.py paths against
        # the actual scripts directory (parent of the presentation_job package).
        # Without this, subprocess.run(cwd=run_dir) interprets "scripts/pdf_export.py"
        # relative to /tmp/canary-spaulding-.../ where no scripts/ subdirectory exists,
        # causing "can't open file" and a hard BLOCKED after 3 retries.
        scripts_dir = Path(__file__).resolve().parent.parent
        return [str(scripts_dir / tok[len('scripts/'):])
                if tok.startswith('scripts/') and not tok.startswith('/')
                else tok
                for tok in tokens]

    # -- FIX 10: captured-exec output helpers --------------------------------
    @staticmethod
    def _last_exec_stderr(captured) -> str:
        """The stderr of a CAPTURED rung-1 attempt (the final one), as a short
        single-line tail. FIX 10: classify_failure can only see the failure
        CLASS the executor printed -- HTTP 402/429/5xx, quota, connection
        refused -- if that text rides the reason string. None/empty when the
        attempt was not captured or printed nothing. Never raises."""
        try:
            err = (getattr(captured, "stderr", "") or "")
            if isinstance(err, bytes):
                err = err.decode("utf-8", errors="replace")
            tail = " ".join(err.strip().split())
            return tail[-400:] if tail else ""
        except Exception:  # noqa: BLE001 -- best-effort classification aid
            return ""

    @staticmethod
    def _flush_captured_output(captured) -> None:
        """Print a captured attempt's stdout/stderr to the operator console
        (FIX 10: only the FINAL attempt is captured, and only on success does
        anything remain to show -- failure output rides the reason). Best
        effort, never raises."""
        try:
            if captured is None:
                return
            out = getattr(captured, "stdout", "") or ""
            if isinstance(out, bytes):
                out = out.decode("utf-8", errors="replace")
            if out.strip():
                print(out, end="" if out.endswith("\n") else "\n", flush=True)
        except Exception:  # noqa: BLE001
            pass

    # -- FIX 25: per-phase front-door nonce minting -------------------------
    def _script_nonce_env(self, phase: Phase) -> Optional[Dict[str, str]]:
        """Mint (or return the live) per-phase front-door nonce env.

        FIX 25 (MASTER Part 8): returns the env dict a script-phase child needs
        to pass build_deck's front door — OC_DECK_ENTRY_NONCE plus, for a
        non-empty sanitized phase token, OC_DECK_ENTRY_NONCE_FILE naming THIS
        phase's own .nonce-<id> file (which this helper also writes, 0600). A
        phase whose id sanitizes to empty stays on the legacy run-scoped
        handshake (OC_DECK_ENTRY_NONCE_FILE unset) so `_verify_entry_nonce`
        falls back to .canonical-entry-nonce untouched.

        Each call mints a FRESH nonce over the previous file: attempt 1's file
        is unlinked by _run_script_phase's finally, but a rung2 regenerate
        re-executes the same guarded script and must mint its own rather than
        reuse a consumed (deleted) one.
        """
        phase_token = _nonce_phase_token(phase.id)
        nonce = secrets.token_hex(32)
        nonce_file = _entry_nonce_phase_file(self.run_dir, phase.id)
        with _NONCE_LOCK:
            umask = os.umask(0o077)
            try:
                nonce_file.write_text(nonce)
            finally:
                os.umask(umask)
            os.chmod(nonce_file, 0o600)
        child_env = dict(os.environ)
        child_env["OC_DECK_ENTRY_NONCE"] = nonce
        if phase_token:
            child_env["OC_DECK_ENTRY_NONCE_FILE"] = phase_token
        self._script_nonce_file = nonce_file
        return child_env

    def _clear_script_nonce(self) -> None:
        """Remove the engine's remembered per-phase nonce file if one is live."""
        try:
            self._script_nonce_file.unlink(missing_ok=True)
        except OSError:
            pass
        except AttributeError:
            pass
        self._script_nonce_file = None

    def _run_script_phase(self, phase: Phase) -> int:
        # U069: tokenise FIRST, substitute SECOND -- via the single shared helper.
        argv = self._build_executor_argv(phase.executor_cmd, phase.id)
        if not argv:
            return self._fail_unit(phase, "executor kind is 'script' but no cmd is declared")
        if self.dry_run:
            print(f"DRY-RUN {phase.id}: {' '.join(argv)}", flush=True)
            return EXIT_OK

        ps = self._phase_state(phase.id)

        # FIX 4 (presentation rev2 phase A): canonical front-door nonce provisioning.
        # executors whose kind is "script" run build_deck.py, whose front-door guard
        # (AF-CANONICAL-RENDER-BYPASS) demands BOTH the nonce file
        # ({run_dir}/working/checkpoints/.canonical-entry-nonce) AND the matching
        # OC_DECK_ENTRY_NONCE environment value. The standalone canonical entry
        # (presentation-canonical-entry.sh) mints these; the engine dispatch never
        # did, so every engine-spawned script phase exited 2 at the front door.
        # The run_dir may not have a checkpoints dir yet on a fresh run; create it.
        checkpoints_dir = self.run_dir / "working" / "checkpoints"
        checkpoints_dir.mkdir(parents=True, exist_ok=True)

        # FIX 25 (MASTER Part 8): the nonce FILE is PER PHASE —
        # working/checkpoints/.nonce-<sanitized phase id> — not one shared
        # run-scoped path. F54b's single shared file forced every script phase in
        # a wave through the serialized mint -> child -> unlink critical section
        # because sibling B minted its nonce OVER A's file (run61 P9.6 attempt 3).
        # With a per-phase file there is no cross-sibling overwrite, so phases run
        # concurrently and the _NONCE_LOCK critical section shrinks to the 0600
        # mint itself. build_deck._verify_entry_nonce prefers
        # OC_DECK_ENTRY_NONCE_FILE and confines the value to THIS run's
        # checkpoints dir with a .nonce-* basename (phase-id form or confined
        # path form) — the consumer side of this contract is already merged.
        child_env = self._script_nonce_env(phase)
        nonce_file = (None if child_env is None
                      else _entry_nonce_phase_file(self.run_dir, phase.id))

        try:
            return self._run_script_phase_locked(phase, argv, checkpoints_dir,
                                                 nonce_file, child_env)
        finally:
            # FIX 4 cleanup: the nonce is per-invocation. Remove the file on EVERY
            # exit path (success return, heal exhaustion, rung 3, block, exception),
            # so a later run can never reuse (or leak) this front-door nonce.
            # FIX 25: this file is THIS phase's own — a concurrent sibling's
            # per-phase file is a different path, so unlinking here can no longer
            # destroy a sibling's in-flight handshake. If run_phase then fires a
            # rung2 regeneration, _script_nonce_env mints a FRESH file for it.
            if nonce_file is not None:
                try:
                    nonce_file.unlink(missing_ok=True)
                except OSError:
                    pass
            self._clear_script_nonce()

    def _run_script_phase_locked(self, phase: Phase, argv, checkpoints_dir, nonce_file,
                                 child_env: Optional[dict] = None) -> int:
        ps = self._phase_state(phase.id)

        # Checkpoint BEFORE the expensive call (invariant 3), so a resume never re-burns it.
        self._checkpoint(phase.id, pending_cmd=' '.join(argv), pending_started_at=utcnow(),
                         pre_run_artifacts=sorted(
                             str(m.relative_to(self.run_dir))
                             # U01-R2: resolve {deck_slug}/{run_dir} tokens before the scan
                             # so pre_run_artifacts reflects the real files, not the literal
                             # token path (QC FAIL 6.46).
                             for rel in phase.resolve_artifact_patterns(self.run_dir)
                             for m in (self.run_dir.glob(rel) if any(c in rel for c in "*?[")
                                       else ([self.run_dir / rel] if (self.run_dir / rel).exists() else []))
                             if m.is_file()))
        budget = phase.budget_minutes * 60
        # FIX 10: the FINAL rung-1 attempt runs captured (stdout+stderr piped) so
        # the failure CLASS the executor printed is available to the class
        # dispatch below. Earlier attempts keep the live passthrough the operator
        # watches; the final attempt's output is dead weight -- the phase already
        # failed twice with visible output -- and its stderr is exactly what
        # classify_failure needs (a bare "exit 146" names no class; the 402 the
        # executor printed does).
        _final_attempt = heal.HEAL_CAP_TRANSIENT
        _captured = None
        for attempt in range(1, heal.HEAL_CAP_TRANSIENT + 1):
            try:
                # FIX-21 (D21): process-group exec with cleanup — on budget expiry the
                # whole group dies, so a timed-out phase never leaves a stray orphan.
                # Falls back to the old direct-child subprocess.run only if the reaper
                # module is absent (it ships beside this package).
                if run_with_cleanup is not None:
                    r = _run_exec_joined(
                        lambda on_spawn=None: run_with_cleanup(
                            argv, cwd=str(self.run_dir),
                            timeout=budget,
                            capture=(attempt == _final_attempt),
                            env=child_env, on_spawn=on_spawn),
                        budget)
                    if attempt == _final_attempt:
                        _captured = r
                else:
                    # F54: even the fallback path must not mutate os.environ —
                    # pass the per-invocation env dict instead.
                    # FIX 105: the bare-subprocess fallback still registers its
                    # handle so the shutdown path can kill it (it is NOT its own
                    # group leader here — _kill_registered_execs falls back to a
                    # direct kill on the pid).
                    r = _run_exec_joined(
                        lambda on_spawn=None: _fallback_run(
                            argv, budget, child_env, on_spawn,
                            run_dir=self.run_dir),
                        budget)
                if _shutdown_requested() and r is not None:
                    # FIX 105: the engine was signalled to stop while THIS exec
                    # ran; the shutdown path killed the exec's whole process
                    # group. Surface the shutdown rc instead of a heal retry —
                    # the engine is going down regardless of the exit code.
                    reason = f"engine shutdown requested -- exec {argv[0]} reaped"
                    with self._state_lock:
                        self.state.setdefault("shutdown_events", []).append(
                            {"at": utcnow(), "phase": phase.id, "attempt": attempt})
                        self.store.save(self.state)
                    print(f"[engine shutdown] {phase.id}: in-flight exec reaped "
                          f"({reason}); no restart attempt", file=sys.stderr, flush=True)
                    return EXIT_GATE_BLOCKED
                if r.returncode == 0:
                    # FIX 10: a captured success still has to SHOW its output.
                    self._flush_captured_output(_captured)
                    return EXIT_OK
                reason = f"exit {r.returncode}"
                # FIX 10: a bare exit code names no failure CLASS -- the provider
                # refusal (HTTP 402/429/5xx, quota, connection refused...) is only
                # visible in the executor's stderr, and 402's masked exit code
                # (402 & 255 == 146) is opaque. The final attempt's captured
                # stderr (the SAME invocation -- no re-run, no side-effect replay)
                # rides the reason string so classify_failure sees the class and
                # the alternate-provider rung can fire.
                tail = self._last_exec_stderr(_captured)
                if tail:
                    reason = f"exit {r.returncode}: {tail}"
            except subprocess.TimeoutExpired:
                reason = f"exceeded its {phase.budget_minutes}-minute budget"
            except OSError as exc:
                reason = f"could not start: {exc}"

            with self._state_lock:
                record_heal_event(self.state, phase.id, self.store, ps, rung=1, attempt=attempt, reason=reason)
                # ANNOUNCE BEFORE RETRYING (invariant 6).
                self.report.to_requester(
                    "blocked",
                    f"{phase.id} failed ({reason}). Retrying — attempt {attempt} of "
                    f"{heal.HEAL_CAP_TRANSIENT}. Nothing you need to do yet.",
                    phase_id=phase.id, reason=reason)
            if attempt < heal.HEAL_CAP_TRANSIENT:
                time.sleep(min(60, 5 * (2 ** (attempt - 1))))

        # FIX 10: class-dispatch the exhaustion. The reason from the LAST
        # rung-1 attempt is classified: a PROVIDER error takes the
        # alternate-provider rung (cap x1, ledger records route_change with
        # both providers -- the QC FIX 10 proof row), any other class falls
        # through to the alternate-route rung (cap x1) exactly as before.
        last_reason = reason  # always bound: HEAL_CAP_TRANSIENT >= 1 attempt ran
        if heal.classify_failure(last_reason) == heal.FAILURE_PROVIDER_ERROR:
            with self._state_lock:
                rc_pf = heal.rung2_provider_failover(self, phase, last_reason,
                                                     child_env=child_env)
            if rc_pf == EXIT_OK:
                return EXIT_OK
            return self._fail_unit(
                phase, f"script executor failed after {heal.HEAL_CAP_TRANSIENT} "
                       f"transient attempt(s) and {heal.HEAL_CAP_PROVIDER} "
                       f"alternate-provider failover(s): {last_reason}")

        # Rung 3: alternate route -- MECHANISM ONLY, NO CLIENT POLICY
        with self._state_lock:
            rc3 = heal.rung3_alt_route(self, phase, child_env=child_env)
        if rc3 == EXIT_OK:
            _r3 = 3
            with self._state_lock:
                heal.record_heal_event(self.state, phase.id, self.store, ps,
                                       rung=_r3, attempt=1, reason="alternate route")
            return EXIT_OK

        return self._fail_unit(phase, f"script executor failed after {heal.HEAL_CAP_TRANSIENT} attempts")

    # -- FAULT-16 / FAULT-09 helpers -----------------------------------------
    def _phase_glob_patterns(self, phase: Phase) -> List[str]:
        """The subset of phase.resolve_artifact_patterns() that are GLOBS
        (contain *, ?, or [) -- i.e. a pattern that can match MORE THAN ONE
        file (P4-PROMPT's working/prompts/slide-*.txt: 25 independently-
        graded files for a 25-slide deck). An exact/single-file pattern's
        presence already IS its completeness (there is no "partial" way for
        one named file to exist) -- this list is empty for those, which is
        exactly what keeps this fix a no-op for the vast majority of phases."""
        return [rel for rel in phase.resolve_artifact_patterns(self.run_dir)
                if any(c in rel for c in "*?[")]

    def _glob_progress_marker(self, patterns: List[str]) -> float:
        """Latest mtime across every file currently matching any pattern in
        `patterns` (0.0 when none match yet). A cheap, mechanism-only proxy
        for "has anything changed here since I looked" -- a brand-new file
        raises it (one more slide written), and so does dispatcher.py's own
        in-place rewrite of an existing failing file (_dispatch_prompt_phase:
        `os.replace(tmp_path, target)`, same name, later mtime) -- both count
        as real forward progress. This never inspects content; deciding
        whether the content is actually GOOD stays phase_verifiers.verify()'s
        job, unchanged."""
        latest = 0.0
        for rel in patterns:
            for m in self.run_dir.glob(rel):
                try:
                    latest = max(latest, m.stat().st_mtime)
                except OSError:
                    continue
        return latest

    def _sidecar_pending(self, phase_id: str) -> bool:
        """FIX 21: for an EXACT-path agent phase, bare on-disk presence is not
        completion while the dispatcher is still mid-flight on that order --
        the dispatcher writes the artifact, runs its own substance verifier,
        and RETRIES when it fails (attempt 1 failed, attempt 2 can pass). The
        engine's old path trusted presence alone and could exit the poll loop
        the same second attempt 1 landed, kill the dispatcher mid-retry, and
        park the phase BLOCKED on artifact the dispatcher itself was about to
        fix. The dispatcher's own sidecar log
        (working/work-orders/<phase_id>.dispatcher-log.jsonl, appended by
        dispatcher._append_sidecar -- the engine never writes it) is the
        coordination point: it carries one row per dispatch attempt with a
        `status` field (`verified` = attempt passed its verifier;
        `exhausted`/`declined`/`already_satisfied`/`already_done_in_state`/
        `phase_exhausted`/`blocked_retry_ceiling` = the dispatcher has finished
        with this order either way; everything else -- call_failed,
        empty_completion, failed, error,
        routing_unavailable, parked, ... -- means the order is still LIVE and
        a later attempt may land). Returns True while a sidecar exists whose
        LATEST status row is not yet settled, so the
        poll loop keeps its identical wait cadence within the phase budget
        instead of trusting presence. Read-only and best-effort: a missing,
        unreadable, or empty sidecar returns False -- an engine-restart
        re-entry (or a pre-sidecar run) keeps the FALSE-BLOCK tiebreaker
        path (verifier PASS accepts a complete inherited artifact), so no
        phase that is genuinely done can ever hang on this.

        DEADLOCK-1 (live run 2026-09-04/05, phase P-SP-INTAKE): `blocked_retry_
        ceiling` was MISSING from the settled list above, and it is the one park
        the dispatcher writes for itself. Its own marker file says re-dispatch
        "resumes automatically if the Engine reissues the work order"
        (dispatcher.py:4374-4376) -- so after that row lands NO later attempt can
        ever come without the Engine acting first. Reading it as "still mid-flight"
        made this method permanently True, which forced ok=False in the poll loop
        below (phases.py:2037) on every single tick: the Engine waited its whole
        budget for a dispatcher that was waiting for the Engine. Observed at
        23:22:54 (ceiling park) against a valid artifact, with the 00:02:29
        --resume then sitting silent for 22 minutes. A ceiling park is the
        dispatcher DONE with this order, so it settles."""
        log = self.run_dir / "working" / "work-orders" / f"{phase_id}.dispatcher-log.jsonl"
        try:
            if not log.is_file():
                return False
            last: Optional[Dict[str, Any]] = None
            with log.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict) and "status" in row:
                        last = row
            if last is None:
                return False
            # Terminal settle states: the dispatcher is done either way.
            if last.get("status") in ("verified", "exhausted", "declined",
                                      "already_satisfied", "already_done_in_state",
                                      "phase_exhausted", "blocked_retry_ceiling"):
                return False
            return True
        except OSError:
            return False

    def _phase_artifact_satisfied(self, phase: Phase) -> bool:
        """True when this phase's declared artifact is BOTH on disk AND passes
        its own substance verifier -- the engine-side twin of the dispatcher's
        already_satisfied pre-check (dispatcher.py:3557-3561).

        Presence alone is deliberately NOT enough. _artifacts_present()
        (phases.py:921) gates on LITERAL FILE EXISTENCE and never consults
        substance -- the hazard documented at dispatcher.py:3541-3544 for
        P1Q-COPY-QC, and the same hole through which one phase writing another
        phase's declared path can suppress that phase. Both halves must hold, so
        this can never complete a phase on a file it did not earn.

        Cheap and model-free: phase_verifiers.verify() only reads the run dir --
        it dispatches nothing and spends nothing, and the poll loop already calls
        it on every tick a few lines below. Fail-closed: an unimportable module
        or a raising verifier returns False, i.e. keep waiting, exactly as
        before."""
        ok, _missing = self._artifacts_present(phase)
        if not ok:
            return False
        try:
            import phase_verifiers
            v_ok, _notes = phase_verifiers.verify(phase.id, self.run_dir)
        except Exception:  # noqa: BLE001 -- unusable verifier: never claim satisfied
            return False
        return bool(v_ok)

    def _run_agent_phase(self, phase: Phase) -> int:
        """
        Emit a work order, then poll for the artifact until the phase budget expires.
        This is a stall detector, not an executor — see the module docstring. The gain over today
        is that a missing artifact BLOCKS AND ANNOUNCES instead of being silently skipped.

        FAULT-16 / FAULT-09 (2026-08-20, orchestrator-verified from the live event
        log): two related coordination defects lived here.

        (a) The poll loop's ONLY completion signal was _artifacts_present() -- bare
        glob-match existence. For a phase whose produces_artifact is a glob covering
        MANY independently-graded files, "the pattern matches >=1 file" is true the
        instant a SINGLE stale file from an earlier, blocked attempt is still sitting
        on disk -- which it always is on re-entry. That let the FIRST poll (before
        any sleep, in the SAME SECOND the work order below was written) declare the
        phase done and fall straight into run_phase()'s substance verifier, which of
        course failed against admittedly partial output. terminal then flipped to
        BLOCKED, and the dispatcher process that would have written the rest refused
        to run at all once it saw that ("run terminal is set -- exiting") -- a real
        deck sat blocked 9.5 hours with 14 of 25 slide prompts never written,
        re-verifying the SAME partial artifact on every --resume instead of waiting
        for the rest of it (FAULT-09: a ~2-second re-block, state.json.resume_history
        growing past 180 entries with zero forward progress between any of them).
        Other agent phases (P1Q-COPY-QC, "Still waiting ... About 9 minutes before I
        flag it") never hit this because their produces_artifact is a single exact
        path, where presence really does equal completeness -- only a multi-file glob
        can be PARTIALLY, misleadingly "present."

        (b) This method also unconditionally overwrote the work order file on every
        call, including on --resume -- even when a dispatcher process still held a
        live claim on this exact phase (working/work-orders/<phase>.claim). One
        component silently reissuing work another was already mid-flight on is the
        "two components, no coordination" half of FAULT-09.

        FIX: (a) for a GLOB pattern only, the loop requires genuine forward progress
        (a matching file with a newer mtime than THIS dispatch's own entry baseline)
        before trusting presence -- so a stale re-entry snapshot can never satisfy it
        by itself. The loop then runs its IDENTICAL pre-existing wait/announce/
        checkpoint cadence (same budget, same "About N minutes before I flag it"
        mechanism P1Q-COPY-QC already uses correctly) until real progress appears or
        the budget genuinely expires -- re-entry with partial output takes the exact
        same waiting path as a fresh dispatch, never an invented new one. An exact/
        single-file pattern is untouched: presence alone still exits immediately,
        byte-for-byte the pre-fix behaviour. (b) a live claim, or a work order that
        is simply still outstanding and not yet stale, is reused rather than
        clobbered -- the engine stops racing the dispatcher for the same phase.

        Neither change touches WHETHER phase_verifiers.verify() can fail -- only
        WHEN it is ever reached.

        FALSE-BLOCK (2026-08-20, Fable-diagnosed from the live run
        pres-wave-e-v3-1787240658, phase PF-DESIGN): the FAULT-16 mtime-growth
        guard above is itself an overcorrection. baseline_progress is captured
        fresh at every ENTRY of this method (line ~697) -- so on an engine
        restart that re-enters a phase AFTER a dispatcher has already finished
        and verify-passed the artifact, the finished file's own mtime becomes
        the baseline, the strict `>` can never become true again, and the loop
        burns its entire budget declaring a COMPLETE phase to have "produced
        nothing." The dispatcher, watching the same filesystem with
        phase_verifiers.verify(), correctly logged already_satisfied the whole
        time -- the two components never agreed because the poll loop had no
        path to consult substance, only a filesystem proxy. FIX: when presence
        is true but the mtime-growth check fails, that state is ambiguous (a
        stale partial from an earlier blocked attempt, or a complete artifact
        inherited across a restart) -- ask phase_verifiers.verify() itself as
        the tiebreaker. PASS means genuinely done: accept it. FAIL changes
        nothing: falls through to the identical wait/announce/checkpoint
        cadence, so a stale or bad artifact still cannot block early and a
        phase that truly produced nothing still times out honestly. See the
        inline comment at the tiebreaker call below for the full mechanics.
        """
        wo = self.run_dir / "working" / "work-orders"
        wo.mkdir(parents=True, exist_ok=True)
        wo_path = wo / f"{phase.id}.json"
        claim_path = wo / f"{phase.id}.claim"  # dispatcher.py's own claim-file convention

        glob_patterns = self._phase_glob_patterns(phase)
        # FAULT-16: snapshot what already exists BEFORE (re)issuing this work
        # order -- the re-entry baseline. Computed only for glob patterns;
        # see _phase_glob_patterns' docstring for why an exact path skips this.
        baseline_progress = self._glob_progress_marker(glob_patterns) if glob_patterns else 0.0

        # FAULT-09b: never clobber a work order a dispatcher is actively
        # holding, or one that is simply still outstanding and not obviously
        # abandoned. "Stale" mirrors a fresh dispatch's own patience: no sign
        # of life for more than 2x this phase's OWN budget is presumed
        # abandoned (crashed worker), not slow, and is still safe to reissue.
        stale_after = max(120.0, phase.budget_minutes * 60 * 2)
        now_ts = time.time()
        claim_live = claim_path.is_file() and (now_ts - claim_path.stat().st_mtime) < stale_after
        wo_live = wo_path.is_file() and (now_ts - wo_path.stat().st_mtime) < stale_after
        # DEADLOCK-1 (live run 2026-09-04/05, phase P-SP-INTAKE). "Live" above is
        # decided PURELY by file mtime; it never asked whether the artifact the
        # order exists to produce is ALREADY THERE. Observed: order written
        # 23:19:18, dispatcher parked it at its retry ceiling 23:22:54, the real
        # driver-signed artifact landed afterwards, and the 00:02:29 --resume
        # still logged "a work order is already outstanding ... waiting on it
        # instead of reissuing" -- then waited. Nothing was ever coming: the
        # dispatcher's own park marker says re-dispatch resumes only "if the
        # Engine reissues the work order" (dispatcher.py:4374-4376), and the
        # Engine was waiting on the dispatcher. A circular wait, silent, for up
        # to the whole phase budget on any interrupted run.
        #
        # An outstanding work order for an ALREADY-SATISFIED artifact is not a
        # reason to wait. "Satisfied" is not bare presence (see
        # _phase_artifact_satisfied) -- it is presence AND the phase's own
        # substance verifier, the same authority the poll loop tiebreaker below
        # and the dispatcher's already_satisfied pre-check use, so all three
        # components agree by construction.
        #
        # FAULT-09 IS NOT WEAKENED. A LIVE CLAIM -- a dispatcher process actually
        # holding this phase right now -- still wins unconditionally, satisfied
        # artifact or not: that IS the "two components must never act on one
        # phase simultaneously" guarantee, and the claim holder may be mid-rewrite
        # of the very file just measured. Only the claim-less "an order file is
        # merely still outstanding" case is short-circuited.
        wo_satisfied = bool(wo_live and not claim_live) and self._phase_artifact_satisfied(phase)
        # DEADLOCK-2 (same run). state.json carried terminal="BLOCKED" from
        # 00:25:20 (_block() parks the run mid-plan, phases.py:2446) and from that
        # instant every dispatcher watching this run exits on its next tick
        # ("run terminal is set -- exiting", dispatcher.py:4679 / :4738). The
        # Engine never noticed: it kept walking the plan and queueing work orders
        # (00:55:20 -- P-STYLE-SPEC and P-3.5-RESEARCH-MAP) for a run nothing
        # would ever dispatch, and each such phase then burns its FULL budget
        # before failing "produced nothing" -- exactly what P3-ARC did between
        # 00:25:20 and 00:55:20. To an operator that is indistinguishable from
        # slow progress.
        #
        # This is FIX 22's bug recurring MID-RUN. FIX 22 (__main__.py:866-876)
        # diagnosed the identical mechanism -- "the dispatcher's watch loop saw
        # the set terminal and exited immediately, and every agent phase then
        # blocked after its full budget with nothing servicing its work order" --
        # and fixed it only at ENTRY, by clearing a stale terminal on --run /
        # --resume. Nothing stopped a fresh one being set half way through.
        #
        # The Engine now honours its own park: no NEW work order is queued for a
        # parked run, and it says so loudly rather than accumulating silent work.
        # Visibility at the top of status already exists (diagnose.py:16 prints
        # "terminal : BLOCKED"); the missing half was the Engine ignoring it.
        # The terminal check itself is untouched everywhere it lives -- BLOCKED
        # stays load-bearing for supervisor.py:406, watchdog.py:131, sweep.py:120,
        # cc_board.py:188 and process_reaper.py:351.
        run_parked = None if wo_satisfied else (self.state.get("terminal") or None)
        with self._state_lock:
            if wo_satisfied:
                self.report.event(
                    "phase.work_order_satisfied",
                    f"{phase.id}: a work order was still outstanding at "
                    f"working/work-orders/{phase.id}.json, but "
                    f"{', '.join(phase.produces_artifact)} already exists and PASSES its "
                    "substance verifier, and no dispatcher holds a live claim - completing "
                    "the phase instead of waiting on an order nothing is servicing "
                    "(DEADLOCK-1).")
            elif run_parked:
                self.report.event(
                    "phase.no_dispatch_run_parked",
                    f"{phase.id}: NOT queueing a work order - this run is PARKED "
                    f"(state.terminal={run_parked!r}). Every dispatcher exits while a "
                    "terminal is set, so the order could never be serviced and this phase "
                    "would burn its whole budget producing nothing (DEADLOCK-2). Re-enter "
                    "with --resume (or --run): both clear terminal/blocked (FIX 22).")
            elif claim_live or wo_live:
                self.report.event(
                    "phase.work_order_reused",
                    f"{phase.id}: {'a dispatcher holds a live claim on' if claim_live else 'a work order is already outstanding for'} "
                    f"working/work-orders/{phase.id}.json — waiting on it instead of "
                    "reissuing a new one (FAULT-09: two components must not act on one "
                    "phase with no coordination).")
            else:
                order = {
                    "phase": phase.id, "owning_role": phase.owning_role,
                    "produces_artifact": phase.produces_artifact,
                    "verifier": phase.verifier,
                    "budget_minutes": phase.budget_minutes,
                    "issued_at": utcnow(),
                }
                wo_path.write_text(json.dumps(order, indent=2), encoding="utf-8")
                self.report.event("phase.work_order",
                                  f"{phase.id} is agent-authored. Work order written to "
                                  f"working/work-orders/{phase.id}.json. Waiting for "
                                  f"{', '.join(phase.produces_artifact)}.")
        if wo_satisfied:
            return EXIT_OK
        if run_parked:
            print("\n" + "=" * 72, file=sys.stderr)
            print(f"NO DISPATCH - run is PARKED (state.terminal={run_parked})", file=sys.stderr)
            print(f"  phase    : {phase.id} ({phase.owning_role})", file=sys.stderr)
            print(f"  expected : {', '.join(phase.produces_artifact) or '(none declared)'}",
                  file=sys.stderr)
            print("  why      : every dispatcher exits while state.terminal is set, so a "
                  "work order", file=sys.stderr)
            print("             queued now could never be serviced - the phase would just "
                  "burn its budget.", file=sys.stderr)
            print("  fix      : re-enter with --resume (or --run) - both clear "
                  "terminal/blocked (FIX 22).", file=sys.stderr)
            print("=" * 72 + "\n", file=sys.stderr)
            return EXIT_GATE_BLOCKED
        if self.dry_run:
            return EXIT_OK

        deadline = time.time() + phase.budget_minutes * 60
        announced_half = False
        checkpoint_every = max(60, phase.heartbeat_interval_minutes * 60 // 4)
        last_cp = time.time()
        started_at = time.time()
        last_present = False
        last_verify_notes: List[str] = []
        import phase_verifiers  # local-import idiom, same as run_phase (phases.py:461)
        while time.time() < deadline:
            ok, _ = self._artifacts_present(phase)
            last_present = last_present or ok
            if ok and (glob_patterns or self._sidecar_pending(phase.id)):
                # FAULT-16: bare presence is not completion for a multi-file
                # glob -- something NEWER than this dispatch's own baseline
                # (a new file, or an existing one rewritten) is still the
                # cheap fast path that trusts presence outright.
                # FIX 21: for an EXACT path (no glob), _sidecar_pending() says
                # the dispatcher is still mid-retry on this order (its sidecar's
                # latest attempt row is not yet `verified`) -- presence alone
                # must not complete the phase while attempt 2 may still fix
                # attempt 1's failure. And a pending sidecar also OVERRIDES the
                # verifier tiebreaker below: a stale artifact left by attempt 1
                # can pass the verifier, yet attempt 2 is about to REPLACE that
                # file -- accepting it would re-create exactly the race this
                # fix removes. The verifier is only ever a TIEBREAKER when NO
                # sidecar row is pending (engine-restart re-entry, which
                # _sidecar_pending() itself excludes); while a row IS pending
                # the loop keeps its identical wait cadence within the phase
                # budget instead of completing and killing the dispatcher
                # mid-retry.
                if not glob_patterns or not (
                        self._glob_progress_marker(glob_patterns) > baseline_progress):
                    # FALSE-BLOCK fix (PF-DESIGN, run pres-wave-e-v3-1787240658,
                    # 2026-08-20): presence with NO new mtime is ambiguous -- a
                    # stale partial from an earlier blocked attempt (FAULT-16:
                    # keep waiting) or a COMPLETE artifact inherited across an
                    # engine restart (accept). Only the substance verifier can
                    # tell them apart -- the same authority run_phase() applies
                    # after this loop and the same check dispatcher.py's
                    # already_satisfied pre-check uses (dispatcher.py:1953,1980),
                    # so the two components now agree by construction. A FAIL
                    # here NEVER blocks -- it keeps waiting exactly as before;
                    # a phase that truly produced nothing still times out below.
                    try:
                        v_ok, v_notes = phase_verifiers.verify(phase.id, self.run_dir)
                    except Exception as exc:  # fail closed: treat as not-yet-complete
                        v_ok, v_notes = False, [f"verifier error: {exc}"]
                    last_verify_notes = list(v_notes or [])
                    # FIX 21: a pending dispatcher sidecar wins over the
                    # verifier tiebreaker -- the phase may not complete while
                    # the dispatcher is mid-flight on this order. Keep waiting
                    # (notes captured for the timeout message) until the
                    # sidecar settles (verified/exhausted => _sidecar_pending
                    # goes False and presence completes) or the budget expires.
                    if self._sidecar_pending(phase.id):
                        ok = False
            if ok:
                return EXIT_OK
            now = time.time()
            remaining = deadline - now
            if not announced_half and remaining < (phase.budget_minutes * 60) / 2:
                announced_half = True
                with self._state_lock:
                    self.report.to_requester(
                        "progress",
                        f"Still waiting on {phase.id} ({phase.owning_role}). "
                        f"About {int(remaining/60)} minutes before I flag it.")
            if now - last_cp >= checkpoint_every:
                last_cp = now
                self._checkpoint(phase.id, status=PHASE_STATUS_RUNNING,
                                 waiting_for=list(phase.produces_artifact),
                                 waited_seconds=int(now - started_at))
            time.sleep(15)
        if last_present:
            return self._fail_unit(
                phase,
                f"artifact matching {', '.join(phase.produces_artifact)} exists but failed "
                f"substance verification for {phase.budget_minutes} minutes: "
                f"{'; '.join(last_verify_notes) or 'no verifier notes captured'}")
        return self._fail_unit(
            phase,
            f"agent-authored phase produced nothing within {phase.budget_minutes} minutes. "
            f"Expected: {', '.join(phase.produces_artifact)}")

    # -- FIX 29 (W05 + W07): the human executor kind -------------------------
    #
    # A declared human executor is a REAL executor kind now. Before this fix the
    # engine dispatched every unknown executor kind to _run_agent_phase's
    # work-order loop, which for a human phase meant the engine "assigned" the
    # owner decision to the LLM dispatcher — the exact forged-approval vector
    # Fix 32 closed for skip records. P-STYLE-PICK (order 4.86, kind human) is
    # the owner gateway stage: the engine itself delivers the pick request, then
    # waits for the owner's choice file, then proves the choice authentic.
    #
    # Contract (the full _run_human_phase):
    #
    #   1. DELIVER: on first entry (no pick-request record on the phase yet) the
    #      engine sends the owner a pick request through the SAME reporter
    #      transport every client message already uses (Reporter.to_requester —
    #      the request text carries the three variants from the samples
    #      manifest). The delivered record is stamped on the phase checkpoint
    #      (pick_request_sent_at) so a --resume NEVER re-spams the owner's chat.
    #      If the phase is re-entered with the request already stamped and not
    #      yet timed out, delivery is skipped and the wait continues.
    #   2. WAIT: poll working/copy/style_preview_choice.json on the standard
    #      15 s engine cadence until the phase budget expires (budget 45 via
    #      PHASE_BUDGET_MINUTES — the owner-response polling cadence the
    #      manifest declares as heartbeat_minutes 45).
    #   3. PROVE: a choice file alone is never proof (the live E2E forged
    #      "e2e-test-002"). The choice must carry owner_approved:true, a
    #      chosen_variant that exists in the samples manifest, AND an
    #      owner_msg_id that approvals.verify() — the single Fix 32 oracle —
    #      resolves to a REAL owner-authored message. Any failure shape
    #      (missing id, unresolvable id, UNDETERMINED oracle) is DENIED and the
    #      wait continues; the run never advances on an unproven pick.
    #   4. TIMEOUT: the configurable default (style-pick-timeout-minutes,
    #      env PRESENTATION_STYLE_PICK_TIMEOUT_MINUTES) is the phase's own
    #      budget. When the wait times out the engine auto-picks variant 1
    #      (manifest order) ONLY when the client's own intake opted in
    #      (intake.style_pick_auto: true) — a recorded opt-in, never inferred.
    #      Without the opt-in the phase BLOCKS (park and notify — an owner
    #      decision, never auto-healed).
    #
    # Return codes: EXIT_OK advances to run_phase's substance verifier (the
    # P-STYLE-PICK verifier re-measures the choice file itself); _block parks
    # the run resumably.

    _STYLE_PICK_CHOICE_REL = "working/copy/style_preview_choice.json"

    def _style_pick_timeout_minutes(self) -> float:
        """Configurable owner-response window (FIX 29). Precedence: the env
        override PRESENTATION_STYLE_PICK_TIMEOUT_MINUTES (a real number,
        refusing garbage), then the phase's own budget. Never raises."""
        raw = (os.environ.get("PRESENTATION_STYLE_PICK_TIMEOUT_MINUTES") or "").strip()
        if raw:
            try:
                v = float(raw)
                if v > 0:
                    return v
            except ValueError:
                pass
        return float(self.manifest.phase_or_none("P-STYLE-PICK").budget_minutes
                     if self.manifest.phase_or_none("P-STYLE-PICK") is not None
                     else 45)

    def _read_style_choice(self) -> Optional[Dict[str, Any]]:
        """Read + parse working/copy/style_preview_choice.json. Returns the
        parsed dict, or None when absent/unparseable (parse failure is NOT a
        valid choice — never trusted, never raised)."""
        p = self.run_dir / self._STYLE_PICK_CHOICE_REL
        if not p.is_file():
            return None
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return obj if isinstance(obj, dict) else None

    def _style_choice_authentic(self, choice: Dict[str, Any],
                                offered_variants: List[str]) -> Tuple[bool, str]:
        """The pick-proof gate. owner_approved:true + a chosen_variant that
        exists in the offered set + an owner_msg_id the Fix 32 oracle resolves
        to a real owner-authored message. Undetermined DENIES (fail-closed,
        same contract as every consumer of presentation_job.approvals).
        Returns (ok, denial_reason)."""
        if choice.get("owner_approved") is not True:
            return False, ("style choice carries owner_approved != true — "
                           "presence of a file is never an owner decision")
        picked = str(choice.get("chosen_variant") or "").strip()
        if not picked:
            return False, "style choice records no chosen_variant"
        if offered_variants and picked not in offered_variants:
            return False, (f"chosen_variant {picked!r} is not one of the "
                           f"offered variants {offered_variants}")
        owner_msg_id = str(choice.get("owner_msg_id") or "").strip()
        if not owner_msg_id:
            return False, ("style choice has NO owner_msg_id — a pick without a "
                           "resolvable owner message id is a forged approval "
                           "(AF-FORGED-APPROVAL)")
        approval = {
            "gate": "P-STYLE-PICK",
            "approved_by": str(choice.get("approved_by") or "owner"),
            "owner_msg_id": owner_msg_id,
            "reason": str(choice.get("reason") or
                          f"owner style pick: variant {picked}"),
            "granted_at": str(choice.get("granted_at") or choice.get("picked_at")
                              or utcnow()),
        }
        try:
            from . import approvals as _approvals
            _approvals.verify(approval, self.run_dir)
        except Exception as exc:  # ApprovalError or oracle transport — DENIED either way
            return False, (f"style choice owner_msg_id {owner_msg_id!r} failed "
                           f"authenticity verification: {exc}")
        return True, ""

    def _style_pick_offered_variants(self) -> List[str]:
        """The variant ids the owner was offered, in manifest order, from the
        samples manifest P-STYLE-PREVIEW produced. Empty list when the samples
        manifest is absent/unreadable (the chosen_variant check then skips the
        membership test — the substance verifier still enforces the file's
        own shape)."""
        p = self.run_dir / "working" / "style-preview" / "style_samples_manifest.json"
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        variants = obj.get("variants") if isinstance(obj, dict) else None
        if not isinstance(variants, list):
            return []
        return [str(v).strip() for v in variants if str(v).strip()]

    def _style_pick_intake_auto(self) -> bool:
        """True ONLY when the client's own intake record opted in
        (intake.style_pick_auto: true). A missing or falsy field is NEVER an
        opt-in — auto-picking for a silent client is the forgery this fix
        exists to prevent."""
        try:
            from .defers import load_intake
            intake = load_intake(self.run_dir)
        except Exception:
            return False
        auto = intake.get("style_pick_auto",
                          (intake.get("pre_presentation_capture") or {})
                          .get("STYLE_PICK_AUTO")
                          if isinstance(intake.get("pre_presentation_capture"), dict)
                          else None)
        return auto is True

    def _style_pick_write_auto_choice(self, variants: List[str]) -> str:
        """The timeout auto-pick: write the choice file on the owner's behalf
        with auto_pick provenance (intake.style_pick_auto:true recorded the
        standing consent) and a reason that says so — never an owner_msg_id,
        which would forge one."""
        picked = variants[0] if variants else "A"
        choice = {
            "owner_approved": True,
            "chosen_variant": picked,
            "auto_pick": True,
            "auto_pick_basis": "intake.style_pick_auto:true (recorded client "
                               "opt-in; the owner-response wait timed out)",
            "picked_at": utcnow(),
            "reason": "variant 1 auto-picked after the owner-response timeout "
                      "under a recorded intake.style_pick_auto opt-in",
        }
        p = self.run_dir / self._STYLE_PICK_CHOICE_REL
        try:
            import tempfile
            dest_dir = p.parent
            dest_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(dest_dir))
            os.write(fd, json.dumps(choice, indent=2).encode("utf-8"))
            os.close(fd)
            os.replace(tmp, str(p))
        except OSError as exc:
            return f"auto-pick could not write {self._STYLE_PICK_CHOICE_REL}: {exc}"
        self.report.event(
            "phase.style_pick.auto_pick",
            f"{self.state.get('current_phase') or 'P-STYLE-PICK'}: "
            "intake.style_pick_auto opt-in honored — variant "
            f"{picked} auto-picked after the owner-response timeout.")
        return ""


    def _run_human_phase(self, phase: Phase) -> int:
        """FIX 29: the human executor contract (see the block comment above
        _STYLE_PICK_CHOICE_REL for the full design). Deliver the pick request
        once, wait for an AUTHENTIC choice file (owner_msg_id proven through
        the Fix 32 oracle), and on timeout auto-pick variant 1 only under a
        recorded intake.style_pick_auto opt-in — otherwise park resumable
        (an owner decision is never auto-healed)."""
        ps = self._phase_state(phase.id)
        variants = self._style_pick_offered_variants()
        choice = self._read_style_choice()

        # Re-entry fast path: a choice already on disk from an earlier attempt.
        # Prove it before trusting it (presence is never proof).
        if choice is not None:
            ok, denial = self._style_choice_authentic(choice, variants)
            if ok:
                # FIX 29: stamp the proven pick on the phase record here too —
                # the re-entry path (the choice landed while the run was parked,
                # and --resume re-enters this phase) must attest the SAME
                # owner_pick record the live-wait path stamps below, or a
                # resumed attestation carries no record of WHICH variant the
                # owner picked and under which message id.
                with self._state_lock:
                    self._checkpoint(
                        phase.id,
                        owner_pick={k: choice.get(k) for k in
                                    ("chosen_variant", "owner_msg_id")},
                        picked_at=utcnow())
                self.report.event(
                    "phase.style_pick.choice_received",
                    f"{phase.id}: owner choice verified — variant "
                    f"{choice.get('chosen_variant')} (owner_msg_id verified).")
                return EXIT_OK
            self.report.event(
                "phase.style_pick.choice_rejected",
                f"{phase.id}: choice file present but DENIED — {denial}. "
                "Waiting for a verifiable owner pick.")
            choice = None

        if self.dry_run:
            print(f"DRY-RUN {phase.id}: human executor — pick request would be "
                  f"delivered to the requester; waiting on "
                  f"{self._STYLE_PICK_CHOICE_REL}", flush=True)
            return EXIT_OK

        # 1. DELIVER (once per run: stamped on the phase record so --resume
        #    never re-spams the owner's chat for the same outstanding request).
        with self._state_lock:
            already_sent = bool(ps.get("pick_request_sent_at"))
        if not already_sent:
            variant_lines = "\n".join(
                f"  {i + 1}. Variant {v}" for i, v in enumerate(variants)
            ) or "  (variant list unavailable — see style_samples_manifest.json)"
            msg = (
                f"Your presentation has 3 style directions ready. "
                f"Please pick ONE by replying A, B or C:\n{variant_lines}\n"
                f"(Phase {phase.id} — the deck renders only after your pick.)"
            )
            # Delivered as kind="ack", deliberately: "progress" is the one kind
            # _throttle_decision may suppress (PROGRESS_MIN_INTERVAL_MINUTES), and
            # a pick request that the throttle eats is an owner never asked — the
            # run then times out and parks with no request EVER delivered. "ack"
            # (the "Got it, building your presentation" class) bypasses the
            # throttle unconditionally, so the ask is always on the wire exactly
            # once per run (the pick_request_sent_at stamp guards re-entry).
            self.report.to_requester("ack", msg)
            self._checkpoint(phase.id, pick_request_sent_at=utcnow())
            self.report.event(
                "phase.style_pick.request_delivered",
                f"{phase.id}: pick request delivered to the requester "
                f"({len(variants) or 3} variants; waiting on "
                f"{self._STYLE_PICK_CHOICE_REL} with a verified owner_msg_id).")

        # 2. WAIT + PROVE on the standard 15 s cadence.
        timeout_minutes = self._style_pick_timeout_minutes()
        deadline = time.time() + timeout_minutes * 60
        checkpoint_every = max(60, phase.heartbeat_interval_minutes * 60 // 4)
        last_cp = time.time()
        started_at = time.time()
        while time.time() < deadline:
            choice = self._read_style_choice()
            if choice is not None:
                ok, denial = self._style_choice_authentic(choice, variants)
                if ok:
                    with self._state_lock:
                        self._checkpoint(
                            phase.id,
                            owner_pick={k: choice.get(k) for k in
                                        ("chosen_variant", "owner_msg_id")},
                            picked_at=utcnow())
                    self.report.event(
                        "phase.style_pick.choice_received",
                        f"{phase.id}: owner choice verified — variant "
                        f"{choice.get('chosen_variant')} (owner_msg_id verified "
                        f"through the approvals oracle).")
                    return EXIT_OK
                # DENIED — keep waiting (the owner may rewrite the file with a
                # real id); the denial is loud, never silent.
                self.report.event(
                    "phase.style_pick.choice_rejected",
                    f"{phase.id}: choice file DENIED — {denial}. "
                    "Continuing to wait for a verifiable owner pick.")
            now = time.time()
            if now - last_cp >= checkpoint_every:
                last_cp = now
                self._checkpoint(phase.id, status=PHASE_STATUS_RUNNING,
                                 waiting_for=[self._STYLE_PICK_CHOICE_REL],
                                 waited_seconds=int(now - started_at))
            time.sleep(15)

        # 3. TIMEOUT: auto-pick ONLY under the recorded opt-in.
        if self._style_pick_intake_auto():
            err = self._style_pick_write_auto_choice(variants)
            if not err:
                self.report.event(
                    "phase.style_pick.auto_pick",
                    f"{phase.id}: intake.style_pick_auto opt-in honored — "
                    f"variant {variants[0] if variants else 'A'} auto-picked "
                    "after the owner-response timeout.")
                return EXIT_OK
            return self._block(phase, err)
        reason = (
            f"{phase.id}: the owner style pick timed out after "
            f"{timeout_minutes:.0f} minutes with no verifiable owner choice. "
            "The full deck must NOT render until the owner picks A/B/C via "
            "their OWN gateway — this is an owner decision "
            f"(record intake.style_pick_auto:true to allow a timeout auto-pick "
            "of variant 1)."
        )
        self.report.event("phase.style_pick.timeout", reason)
        return self._block(phase, reason)

    def _fail_unit(self, phase: Phase, reason: str) -> int:
        """FIX 9a (MASTER Part 8 Fix 9): quarantine ONE unit, park nothing.

        Replaces the old unit-level _block() park for execution failures.
        The failing phase's record becomes status='quarantined' (the QC FIX 9
        enum value) with its failure reason; terminal is NEVER set here and
        state["blocked"] is never written here, so the dispatcher keeps
        running every still-runnable wave and run() parks the run exactly
        ONCE at the end with the failed_units ledger row naming this unit.
        Resume treats a quarantined unit exactly like a blocked one: it is
        not 'done', so the next run re-enters it.

        FIX 10: OWNER-DECISION failures are the exception — they classify to
        FAILURE_OWNER_DECISION (waiver / owner-skip-approval / gate decline
        vocabulary) and route to _block() instead: park and notify, never
        auto-heal, never quarantine a decision only the client can make."""
        if heal.classify_failure(reason) == heal.FAILURE_OWNER_DECISION:
            with self._state_lock:
                heal._ledger(self, phase=phase.id, rung=None, attempt=0,
                             failure_class=heal.FAILURE_OWNER_DECISION,
                             reason=reason, route_change=False,
                             outcome="park_and_notify")
            return self._block(phase, reason)
        with self._state_lock:
            self._checkpoint(phase.id, status=PHASE_STATUS_QUARANTINED,
                             quarantined_reason=reason, quarantined_at=utcnow())
            self.report.event(
                "phase.quarantined",
                f"{phase.id}: unit quarantined (run continues past it): {reason}")
            if self.board:
                # Option B, same mint-on-demand contract as the old _block
                # path: a unit that never reached its own progress report
                # still gets its child card, closed 'blocked' with the reason
                # (the CC board's own status vocabulary has no quarantine).
                title, description = self._child_card_meta(phase)
                self.board.child_report(phase.id, title, description,
                                        "blocked", reason)
        print("\n" + "=" * 72, file=sys.stderr)
        print(f"QUARANTINED UNIT {phase.id}", file=sys.stderr)
        print(f"  reason   : {reason}", file=sys.stderr)
        print(f"  owner    : {phase.owning_role}", file=sys.stderr)
        print(f"  expected : {', '.join(phase.produces_artifact) or '(none declared)'}",
              file=sys.stderr)
        print("  note     : the run continues — this unit is recorded in the "
              "failed-units ledger at the end", file=sys.stderr)
        print("=" * 72 + "\n", file=sys.stderr)
        return EXIT_GATE_BLOCKED

    def _block(self, phase: Phase, reason: str) -> int:
        """Park resumable. Never die, never restart from scratch (decision #5).

        FIX 9a: this is now the OPERATOR/GATE park only (intake gate, missing
        executor wiring). Unit-level execution failures go through _fail_unit
        (status='quarantined', run continues) instead of parking the whole
        run mid-flight."""
        # Count banked artifacts BEFORE checkpointing, so the current
        # phase is still "done" when we look for done phases.
        with self._state_lock:
            banked, lost = [], []
            for ps_ in self.state.get("phases", []):
                if ps_.get("status") != PHASE_STATUS_DONE:
                    continue
                for a in (ps_.get("artifacts") or []):
                    ok, _why = validate_artifact(self.run_dir, a, self.manifest,
                                                 recorded_sha=(ps_.get("sha256") or {}).get(a))
                    (banked if ok else lost).append(a)
            self._checkpoint(phase.id, status=PHASE_STATUS_BLOCKED, blocked_reason=reason)
            self.state["terminal"] = "BLOCKED"
            self.state["blocked"] = {"phase": phase.id, "reason": reason, "at": utcnow()}
            self.store.save(self.state)
            if self.board:
                self.board.mark_blocked(phase.id, reason)
                # Option B: a gate failure on a phase that never reached its own
                # progress report (the success-path child_report call above) still
                # needs a child card -- child_report mints one on demand (idempotent,
                # same as the success path) and closes it 'blocked' with the reason.
                title, description = self._child_card_meta(phase)
                self.board.child_report(phase.id, title, description, "blocked", reason)
            safe_msg = f"{len(banked)} file(s) are saved and {len(lost)} will be rebuilt on resume " \
                       "-- nothing you sent us is lost."
            if not lost:
                safe_msg = f"{len(banked)} file(s) already produced are saved -- nothing is lost."
            self.report.to_requester(
                "blocked",
                f"Your presentation is paused at {phase.id}. {reason} "
                f"{safe_msg} "
                "We have been told and are looking at it.",
                phase_id=phase.id, reason=reason)
        print("\n" + "=" * 72, file=sys.stderr)
        print(f"BLOCKED at {phase.id}", file=sys.stderr)
        print(f"  reason   : {reason}", file=sys.stderr)
        print(f"  owner    : {phase.owning_role}", file=sys.stderr)
        print(f"  expected : {', '.join(phase.produces_artifact) or '(none declared)'}",
              file=sys.stderr)
        print(f"  banked   : {len(banked)} artifact(s) — reused on resume, not regenerated",
              file=sys.stderr)
        if lost:
            print(f"  lost     : {len(lost)} artifact(s) — will be rebuilt on resume",
                  file=sys.stderr)
        print("\n  continue with:", file=sys.stderr)
        print(f"    python3 {ENTRY_COMMAND} --resume --run-dir {self.run_dir}",
              file=sys.stderr)
        print("=" * 72 + "\n", file=sys.stderr)
        return EXIT_GATE_BLOCKED

    # -- the loop ---------------------------------------------------------
    def run(self, only: Optional[str] = None, until: Optional[str] = None) -> int:
        # U024 — sacred-structure warn check, once at engine start-up.
        # DELIBERATELY NON-BLOCKING: a structure drift is a signal to a human,
        # not grounds to refuse a client's job. A missing pin file is likewise
        # reported and stepped over, never treated as a failure.
        # NOTE: persona.resolve_for_phase() is already wired in _run_phase();
        # this adds ONLY the start-up check, so there is exactly one resolution
        # call per phase.
        try:
            warn = persona.structure_warn_check()
        except Exception as exc:  # never let a warn-only check break a run
            self.report.event("warn", f"sacred-structure check failed to run: {exc}")
        else:
            if warn.get("mismatched"):
                self.report.event(
                    "warn", f"sacred-structure mismatch: {warn['mismatched']}")
            elif not warn.get("pin_file_found"):
                self.report.event(
                    "warn", "sacred-structure pin file not found — skipping structure check")

        phases = self.manifest.phases
        if only:
            phases = [self.manifest.phase(only)]
        elif until:
            stop = self.manifest.phase(until)
            phases = [p for p in phases if p.order <= stop.order]

        # fix/run-slides: route converter_path phases (P-CONVERTER) around any
        # deck whose confirmed creation_mode is not a content-conversion mode.
        # `only` means the operator explicitly asked to dispatch this ONE phase
        # by id -- that direct request is always honored as-is, never silently
        # rerouted. `until` still gets the filter: it walks the same automatic
        # phase list this routing decision governs.
        if not only:
            creation_mode = self._deck_creation_mode()
            if creation_mode is not None and creation_mode not in self._CONTENT_FIRST_CREATION_MODES:
                keep, routed = [], []
                for p in phases:
                    (routed if p.converter_path else keep).append(p)
                for p in routed:
                    self._route_around_converter_phase(p, creation_mode)
                phases = keep
        # DESIGN-OPUS.md §4.2 — defers_unless gating. A phase whose gate evaluates
        # false is DEFERRED for this run: never surfaced, never attested, but
        # recorded with a skip_attestation so the attestation chain stays complete
        # and downstream phases never fail on a missing optional phase.
        # Intake answers come from state["intake"] (the record passed to --new);
        # falls back to working/copy/intake.json written by deck-intake-driver.py.
        intake = self.state.get("intake")
        if not isinstance(intake, dict):
            intake = load_intake(self.run_dir)
        deferred_ids = {p.id for p in phases if phase_is_deferred(p, intake)}
        if deferred_ids:
            for p in phases:
                if p.id not in deferred_ids:
                    continue
                ps = self._phase_state(p.id)
                if ps.get("status") in (PHASE_STATUS_DONE, PHASE_STATUS_DEFERRED):
                    continue
                self._checkpoint(
                    p.id, status=PHASE_STATUS_DEFERRED,
                    deferred_reason=f"defers_unless: {p.defers_unless or ''}")
                self.report.event(
                    "phase.deferred",
                    f"{p.id} deferred — defers_unless ({p.defers_unless or ''}) "
                    "not satisfied by intake answers.")
                print(f"DEFER {p.id}: defers_unless ({p.defers_unless or ''}) "
                      "not satisfied — skipped for this run.", flush=True)
            phases = [p for p in phases if p.id not in deferred_ids]

        if not self.state.get("sent", {}).get("ack"):
            # B2b: use the SAME client-visible filtering the per-phase
            # {k}/{N} messages use (_client_visible_phases), so the ack's
            # step count is never a different number than what the
            # individual "Step k of N" messages report later in this same
            # run. `phases` here already excludes any P-CONVERTER routed
            # around above; _client_visible_phases additionally excludes the
            # four SP-only phases when deck_type is positively known
            # non-signature -- fails safe to the full count otherwise.
            n = len(self._client_visible_phases(phases))
            self.report.to_requester(
                "ack",
                f"Got it. Building your presentation in {n} steps. "
                "I will tell you as each step finishes, and immediately if anything stops.")

        if self.board:
            deck_slug = self.run_dir.name
            intake = self.state.get("intake") or {}
            title = intake.get("title") or f"Presentation {self.state.get('job_id', '?')[:8]}"
            description = intake.get("description") or ""
            self.board.open_card(deck_slug, title, description)

        run_started_t = time.monotonic()
        # FIX 1: wave execution behind PRESENTATION_WAVE_EXECUTION (default ON).
        # =0 selects the exact pre-fix serial loop (documented rollback). Flag ON:
        # the plan is built through the SAME build_execution_plan the department
        # CLI serves (reuse-as-is boundary) from the pinned manifest path; the
        # probe is the REAL capacity.probe() result — capacity_override.json is
        # honoured first (FIX 11: a declared max_concurrent drives the width),
        # then 9Router/OpenClaw detection, then the cap table. Only
        # phases the DAG marks independent share a wave — independence is never
        # invented here. A wave runs bounded by the measured capacity; every
        # future of a wave joins before a failure rc is returned, so a blocking
        # phase never abandons its wave-mates mid-flight.
        if _wave_execution_enabled():
            capacity_probe = _capacity.probe()
            try:
                plan = build_execution_plan(self.manifest.path, capacity_probe)
            except CapacityUnmeasured as exc:
                # Same loud refusal as execution_plan's own CLI: refuse, never
                # substitute an unmeasured width (Master-Spec file 9 AUTOFAIL).
                print(f"CAPACITY AUTOFAIL: {exc}", file=sys.stderr)
                print(json.dumps(autofail_payload(capacity_probe), indent=2),
                      file=sys.stderr)
                return EXIT_GATE_BLOCKED
            by_id = {p.id: p for p in phases}
            planned_ids = [pid for wave in plan["waves"] for pid in wave]
            wave_phases = [[by_id[pid] for pid in wave if pid in by_id]
                           for wave in plan["waves"]]
            # Phases the operator selected (`only`/`until`/converter routing)
            # that the plan's waves never named still run — serially, appended
            # after the waves, in manifest order. A selected phase is never
            # dropped just because a subset selection didn't intersect a wave.
            extra = [p for p in phases if p.id not in planned_ids]

            # FIX 9b (MASTER Part 8 Fix 9): one failing unit no longer stops the
            # run. _run_wave COLLECTS every result — all wave members are joined
            # (list(pool.map) already guarantees that) and ALL their exit codes
            # are returned, not just the first non-OK. run() records the failed
            # rcs, keeps going while anything is runnable, and parks once at the
            # end if any unit failed. Proof contract (QC.md FIX 9): a forced
            # failure in one leaf phase leaves every other phase done.
            def _run_wave(wave_no: int, members: List[Phase]) -> List[int]:
                available = plan["available"]
                if not isinstance(available, int) or isinstance(available, bool):
                    # UNBOUNDED (a real measurement): no ceiling to enforce —
                    # the width is the wave size, never the sentinel literal.
                    available = len(members)
                width = max(1, min(len(members), available))
                with ThreadPoolExecutor(max_workers=width) as pool:
                    # list() joins EVERY future before returning, so all wave
                    # members finish (telemetry included) before we look at rcs.
                    # FIX 9b containment: run_phase_timed re-raises on a member
                    # crash, and pool.map propagates the FIRST exception,
                    # discarding every wave-mate's result and ending run() while
                    # downstream waves are still runnable. Each member therefore
                    # runs inside its own try/except: a crash is contained to
                    # that unit and surfaces as its failed rc; every wave-mate's
                    # rc is still collected and every downstream wave still runs.
                    def _member_rc(m: Phase) -> int:
                        try:
                            return self.run_phase_timed(m, wave=wave_no)
                        except BaseException as exc:  # noqa: BLE001 — collect, never abandon
                            return getattr(exc, "exit_code", EXIT_GATE_BLOCKED)
                    return list(pool.map(_member_rc, members))

            failed_rcs: List[Tuple[str, int]] = []
            for wave_no, members in enumerate(wave_phases, 1):
                if not members:
                    continue
                # Per-unit results, in wave-member order. A non-OK rc from one
                # unit (the phase quarantined itself via _fail_unit or parked
                # via _block) is recorded — the rest of the wave already ran
                # to completion and every DOWNSTREAM wave still runs while it
                # is runnable.
                for m, rc in zip(members, _run_wave(wave_no, members)):
                    if rc != EXIT_OK:
                        failed_rcs.append((m.id, rc))
            for p in extra:
                # FIX 9b containment: same per-unit crash guard as _run_wave so
                # an extra (selected-but-unplanned) phase that crashes records
                # its rc instead of aborting the run with waves still runnable.
                try:
                    rc = self.run_phase_timed(p, wave=len(plan["waves"]) + 1)
                except BaseException as exc:  # noqa: BLE001 — collect, never abandon
                    rc = getattr(exc, "exit_code", EXIT_GATE_BLOCKED)
                if rc != EXIT_OK:
                    failed_rcs.append((p.id, rc))
            if failed_rcs:
                # FIX 9b: park ONCE for the whole run, after every runnable
                # phase has been given its chance. No mid-run early exits.
                with self._state_lock:
                    # FIX 5 (emitter): a parked run skips the run summary,
                    # so drain the mirror queue before leaving.
                    self._flush_telemetry_cc()
                    self.state.setdefault("failed_units", []).extend(
                        {"phase": pid, "rc": rc} for pid, rc in failed_rcs)
                    if self.state.get("terminal") is None:
                        self.state["terminal"] = "BLOCKED"
                        self.state["blocked"] = {
                            "phase": failed_rcs[0][0],
                            "reason": (
                                f"{len(failed_rcs)} unit(s) failed after all runnable "
                                f"phases ran: " + ", ".join(
                                    f"{pid} (rc {rc})" for pid, rc in failed_rcs)),
                            "at": utcnow(),
                            "units": [pid for pid, _ in failed_rcs],
                        }
                    self.store.save(self.state)
                for pid, rc in failed_rcs:
                    ps = self._phase_state(pid)
                    if ps.get("status") in (PHASE_STATUS_RUNNING,
                                            PHASE_STATUS_PENDING):
                        # The unit parked itself below (blocked/quarantined/failed
                        # status from _fail_unit); only normalize a unit that died
                        # without recording its own terminal state.
                        with self._state_lock:
                            self._checkpoint(
                                pid, status=PHASE_STATUS_FAILED, failed_rc=rc,
                                failed_reason=f"phase exited rc={rc} without parking")
                first_pid, first_rc = failed_rcs[0]
                print("\n" + "=" * 72, file=sys.stderr)
                print(f"PARKED at {first_pid} (+{len(failed_rcs) - 1} other failed unit(s))",
                      file=sys.stderr)
                for pid, rc in failed_rcs:
                    print(f"  failed unit: {pid} rc={rc}", file=sys.stderr)
                print("\n  continue with:", file=sys.stderr)
                print(f"    python3 {ENTRY_COMMAND} --resume --run-dir {self.run_dir}",
                      file=sys.stderr)
                print("=" * 72 + "\n", file=sys.stderr)
                return failed_rcs[0][1]
        else:
            # PRESENTATION_WAVE_EXECUTION=0 rollback path: the pre-fix serial
            # loop, byte-for-byte (every phase wave=0).
            for p in phases:
                rc = self.run_phase_timed(p, wave=0)
                if rc != EXIT_OK:
                    with self._state_lock:
                        # FIX 5 (emitter): same early-exit drain as the wave fail.
                        self._flush_telemetry_cc()
                    return rc

        # FIX 5: one-line run summary (total wall-clock, slowest phases).
        self._emit_run_summary(run_started_t)

        if only:
            return EXIT_OK
        return self.close()

    def _emit_run_summary(self, run_started_t: float) -> None:
        """FIX 5: emit a run-level summary -- total wall clock + slowest 3 phases.

        Reads back the run's own stage-timings rows (event=phase_exit only) so
        blocks/crashes are visible too. Best-effort, never raises.
        """
        try:
            rows = []
            tf = self._telemetry_dir() / "stage-timings.jsonl"
            if tf.exists():
                with tf.open("r", encoding="utf-8") as fh:
                    rows = [json.loads(line) for line in fh if line.strip()]
            exits = [r for r in rows if r.get("event") == "phase_exit"]
            by_phase: Dict[str, float] = {}
            for r in exits:
                pid = r.get("phase_id")
                if pid:
                    by_phase[pid] = by_phase.get(pid, 0.0) + float(r.get("duration_s") or 0.0)
            slowest = sorted(by_phase.items(), key=lambda kv: kv[1], reverse=True)[:3]
            total = time.monotonic() - run_started_t
            summary = {
                "run_id": self.run_dir.name,
                "event": "run_summary",
                "total_wall_s": round(total, 3),
                "phase_count": len(exits),
                "slowest_3": [{"phase_id": pid, "duration_s": round(d, 3)} for pid, d in slowest],
                "generated_at": utcnow(),
            }
            self._emit_stage_timing(summary)
            with self._state_lock:
                # FIX 5 (emitter): the summary is the LAST row of a run, so any
                # pending mirror rows are drained with it (best-effort).
                self._flush_telemetry_cc()
            slow_str = ", ".join(f"{pid} {d:.0f}s" for pid, d in slowest)
            print(f"RUN SUMMARY: total {total:.0f}s | phases executed: {len(exits)} | "
                  f"slowest: {slow_str}", flush=True)
        except Exception as exc:  # noqa: BLE001 telemetry must never break a run
            print(f"WARN telemetry: run summary failed: {exc}", flush=True)

    def _mint_process_certificate(self) -> dict:
        """U067 -- WORK-ITEM-05: Mint PROCESS-CERTIFICATE inside engine close().

        Imports prove-deck's cert minting logic. Checks every declared step:
        attestation record, substance_verified, client_reports start+done,
        monotonic timestamps, no gaps. Writes PROCESS-CERTIFICATE.json to
        working/checkpoints/. Records sha256 in state. Returns the cert dict.
        """
        now = utcnow()
        phases = self.state.get('phases', [])
        manifest_version = self.state.get('manifest_version', 'unknown')
        manifest_sha = self.state.get('manifest_sha256', '')[:12]

        # 1. Collect attestation records -- every phase that reached status 'done'
        attested = [p for p in phases if p.get('status') == PHASE_STATUS_DONE]
        all_phase_ids = [p.get('id') for p in phases]

        # 2. Verify no gaps
        manifest_phase_ids = [p.id for p in self.manifest.phases]
        unentered = [pid for pid in manifest_phase_ids if pid not in all_phase_ids]
        # FIX 20: an obsolete row is a phase REMOVED from the manifest at
        # repin, not a gap in this run — it must not read as incomplete and
        # brick the close gate for a job whose manifest legitimately changed.
        incomplete = [p.get('id') for p in phases
                      if p.get('status') not in (PHASE_STATUS_DONE,
                                                 PHASE_STATUS_BLOCKED,
                                                 PHASE_STATUS_OBSOLETE)]

        # 3. Check substance verification
        substance_unverified = [
            p.get('id') for p in attested
            if p.get('verifier_ok') is False
            or (p.get('verifier_ok') is None and p.get('artifacts'))
        ]
        substance_verified_count = len([
            p for p in attested if p.get('verifier_ok') is True
        ])

        # 4. Check client reports
        sent = self.state.get('sent') or {}
        has_ack = bool(sent.get('ack'))
        has_done = bool(sent.get('done'))
        progress_sent = (sent.get('progress', {}).get('count', 0)
                         if isinstance(sent.get('progress'), dict) else 0)
        blocked_sent = (sent.get('blocked', {}).get('count', 0)
                        if isinstance(sent.get('blocked'), dict) else 0)

        # 5. Monotonic timestamp check — CHRONOLOGICAL order, not manifest order.
        # F48 (SMOKE-1, 2026-09-01): the previous loop compared attested_at in
        # manifest sequence, so a phase that re-ran later in wall clock but sits
        # EARLIER in the manifest (banked revalidation, driver-authored heals)
        # counted as a "violation" purely from ordering. The integrity property
        # that matters is that attestation timestamps never go backwards in TIME.
        timestamps = []
        for p in attested:
            at = p.get('attested_at')
            if at:
                timestamps.append((p.get('id'), at))
        timestamps.sort(key=lambda t: t[1] or "")
        monotonic_violations = []
        for i in range(1, len(timestamps)):
            if timestamps[i][1] < timestamps[i-1][1]:
                monotonic_violations.append(
                    f"{timestamps[i][0]} @ {timestamps[i][1]} < "
                    f"{timestamps[i-1][0]} @ {timestamps[i-1][1]}"
                )

        # 6. Gate results
        gates_state = self.state.get('gates', {})
        gate_pass_count = sum(
            1 for g in gates_state.values()
            if isinstance(g, dict) and g.get('state') in ('pass', 'waived')
        )
        gate_total = len(ALL_GATE_KEYS)
        gate_failures = [
            k for k, v in gates_state.items()
            if isinstance(v, dict) and v.get('state') not in ('pass', 'waived')
        ]

        # 7. Build the certificate
        cert = {
            'certificate_version': 1,
            'job_id': self.state.get('job_id'),
            'run_dir': str(self.run_dir),
            'minted_at': now,
            'manifest': {
                'version': manifest_version,
                'sha256': manifest_sha,
            },
            'phase_integrity': {
                'manifest_phase_count': len(manifest_phase_ids),
                'phases_attested': len(attested),
                'phases_incomplete': len(incomplete),
                'phases_unentered': len(unentered),
                'unentered_phase_ids': unentered,
                'incomplete_phase_ids': incomplete,
                'no_gaps': len(unentered) == 0,
                'all_done': len(attested) == len(manifest_phase_ids),
            },
            'substance_verification': {
                'verified_count': substance_verified_count,
                'unverified_phase_ids': substance_unverified,
                'all_verified': len(substance_unverified) == 0,
            },
            'client_reports': {
                'ack_sent': has_ack,
                'done_sent': has_done,
                'progress_messages': progress_sent,
                'blocked_messages': blocked_sent,
            },
            'timestamp_integrity': {
                'attestation_count': len(timestamps),
                'monotonic': len(monotonic_violations) == 0,
                'violations': monotonic_violations,
            },
            'gate_results': {
                'passed': gate_pass_count,
                'total': gate_total,
                'failed_gate_keys': gate_failures,
                'all_passed': len(gate_failures) == 0,
            },
            'integrity_pass': (
                len(unentered) == 0 and
                len(substance_unverified) == 0 and
                len(monotonic_violations) == 0 and
                len(gate_failures) == 0
            ),
            'integrity_fail_reasons': [],
        }

        if not cert['integrity_pass']:
            if unentered:
                cert['integrity_fail_reasons'].append(
                    f'AF-PROCESS-INTEGRITY: {len(unentered)} manifest phase(s) '
                    'never entered: ' + ', '.join(unentered))
            if substance_unverified:
                cert['integrity_fail_reasons'].append(
                    f'AF-PROCESS-INTEGRITY: {len(substance_unverified)} phase(s) '
                    'without substance verification: ' + ', '.join(substance_unverified))
            if monotonic_violations:
                cert['integrity_fail_reasons'].append(
                    f'AF-PROCESS-INTEGRITY: {len(monotonic_violations)} timestamp '
                    'monotonicity violation(s)')

        # 8. Write to checkpoints (atomic, same pattern as state.save())
        import tempfile as _tempfile
        import os as _os
        checkpoints_dir = self.run_dir / 'working' / 'checkpoints'
        checkpoints_dir.mkdir(parents=True, exist_ok=True)
        cert_path = checkpoints_dir / 'PROCESS-CERTIFICATE.json'
        cert_json = json.dumps(cert, indent=2, ensure_ascii=False, sort_keys=True)
        fd, tmp = _tempfile.mkstemp(dir=str(checkpoints_dir),
                                    prefix='.cert-', suffix='.tmp')
        try:
            with _os.fdopen(fd, 'w', encoding='utf-8') as fh:
                fh.write(cert_json)
                fh.flush()
                _os.fsync(fh.fileno())
            _os.replace(tmp, str(cert_path))
        except Exception:
            try:
                _os.unlink(tmp)
            except OSError:
                pass
            raise

        # 9. Compute sha256 and record in state
        cert_sha = sha256_file(cert_path)
        self.state['process_certificate'] = {
            'path': str(cert_path.relative_to(self.run_dir)),
            'sha256': cert_sha,
            'minted_at': now,
            'integrity_pass': cert['integrity_pass'],
        }

        self.report.event(
            'certificate.minted',
            f'PROCESS-CERTIFICATE minted: sha256={cert_sha[:12]}, '
            f'integrity={"PASS" if cert["integrity_pass"] else "FAIL"}, '
            f'{len(attested)}/{len(manifest_phase_ids)} phases attested'
        )
        print(f'CERT: {cert_path.relative_to(self.run_dir)} '
              f'sha256={cert_sha[:12]} '
              f'integrity={"PASS" if cert["integrity_pass"] else "FAIL"}', flush=True)

        return cert

    def _run_self_audit(self) -> Tuple[bool, str, str]:
        """WORK-ITEM-16 (ANTI-DRIFT CORE): mechanical self-audit of the run
        directory, run as the FINAL step before handoff. Invokes
        self_audit.py as a subprocess against this run's deliverables; a
        non-zero exit means one or more deliverables failed verification
        (missing, undersized, or wrong file type) and handoff must be
        rejected.

        Returns (ok, reason, output) -- output is captured stdout+stderr,
        truncated to a sane length for state.json.
        """
        scripts_dir = Path(__file__).resolve().parent.parent
        self_audit_path = scripts_dir / "self_audit.py"
        argv = ["python3", str(self_audit_path), "--run-dir", str(self.run_dir)]
        try:
            r = subprocess.run(argv, cwd=str(self.run_dir), capture_output=True,
                               text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"self-audit could not run: {exc}", str(exc)[-4000:]
        output = ((r.stdout or "") + (r.stderr or ""))[-4000:]
        if r.returncode != 0:
            return False, f"self-audit exited {r.returncode}", output
        return True, "", output

    # FIX 7 (W06b-B4) -- make done reachable from the engine: close() itself
    # registers the run's deliverables and the PROCESS-CERTIFICATE on the
    # parent card, then PATCHes it to review with process_certificate_sha so
    # the board-side QC scorer has everything it needs to promote
    # review->done with NO human PATCH.
    #
    # WHY THIS LIVES HERE (not in board.py): board.py's mark_review() goes
    # through cc_board.patch_phase, which reads the certificate sha ONLY from
    # delivery/*-FINAL/PROCESS-CERTIFICATE.json (the prove-deck/runner path).
    # The ENGINE mints its own certificate at
    # working/checkpoints/PROCESS-CERTIFICATE.json (_mint_process_certificate),
    # so on engine runs the review PATCH went out with NO
    # process_certificate_sha and the CC-side registration gate (F14) held
    # every engine-owned card in review forever -- zero done, ever.
    #
    # Everything below is FAIL-SOFT by the same contract as every other board
    # advance: the board is a VIEW; a board outage, a missing token, or a
    # rejected row can never block the build (Invariant 1). Any failure falls
    # back to the pre-existing mark_review() path so the movement receipt
    # still records the attempt.
    def _board_register_close(self) -> bool:
        """Register the ten deliverables + the engine certificate on the
        parent card and PATCH it to review with process_certificate_sha.

        Returns True ONLY when the explicit review PATCH landed (HTTP 200);
        every other outcome returns False and the caller falls back to
        board.mark_review(). Never raises.
        """
        try:
            import cc_board as _cc_board
        except ImportError:
            return False
        cfg = _cc_board.board_config(os.environ)
        if cfg is None:
            return False

        # task_id: the same dual source BoardMirror uses.
        task_id = (self.state.get("board") or {}).get("task_id")
        if not task_id:
            manifest = _cc_board._read_manifest(self.run_dir)
            cc_task_id = manifest.get("cc_task_id")
            task_id = str(cc_task_id) if cc_task_id else None
        if not task_id:
            return False

        # Certificate sha: the ENGINE-minted certificate first (this is the
        # engine path), the delivery/*-FINAL runner certificate second.
        cert_sha = ((self.state.get("process_certificate") or {})
                    .get("sha256"))
        if not cert_sha:
            cert_sha = _cc_board._read_certificate_sha(self.run_dir)
        if not cert_sha:
            self.report.event(
                "board.cert_sha_missing",
                "close(): no PROCESS-CERTIFICATE sha in state or delivery/; "
                "registering deliverables but skipping the cert-bearing PATCH")
            return False

        registered = 0
        for spec in _deliverable_specs():
            dest = spec.get("standardized_dest") or ""
            if not dest:
                continue
            fpath = self.run_dir / "deliverables" / dest
            if not fpath.is_file():
                # Deliverable gated separately (workbook, webinar audio) or
                # not produced this run: registration is per-file, skip
                # silently -- the flat folder was already gate-verified by
                # curate() and the self-audit before this point.
                continue
            payload = {
                "deliverable_type": "file",
                "title": dest,
                "path": str(fpath.resolve()),
                "description": json.dumps({
                    "key": spec.get("key"),
                    "label": spec.get("label"),
                    "run_dir": str(self.run_dir),
                }, separators=(",", ":")),
            }
            url = f"{cfg['base_url']}/api/tasks/{task_id}/deliverables"
            try:
                st, body = _cc_board._request("POST", url, payload, cfg)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                self.report.event(
                    "board.error",
                    f"register_deliverable {dest}: {type(exc).__name__}: {exc}")
                continue
            if 200 <= st < 300:
                registered += 1
            else:
                self.report.event(
                    "board.error",
                    f"register_deliverable {dest} non-2xx (HTTP {st}); "
                    "build continues.")

        # The cert-bearing terminal PATCH: status review + the sha the
        # no-skip done gate reads. Same endpoint cc_board.patch_phase uses
        # for cert-bearing transitions (review/done).
        patch_payload = {
            "phase_id": "TERMINAL",
            "status": "review",
            "process_certificate_sha": cert_sha,
            "note": "Engine close: deliverables registered, "
                    f"{registered} on the card; process certificate attached.",
        }
        patch_url = f"{cfg['base_url']}/api/tasks/{task_id}"
        try:
            st, body = _cc_board._request("PATCH", patch_url, patch_payload, cfg)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self.report.event(
                "board.error",
                f"close review PATCH failed: {type(exc).__name__}: {exc}")
            return False
        _cc_board._record_movement(self.run_dir, {
            "phase_id": "TERMINAL", "kind": "status", "target": "review",
            "endpoint": "PATCH /api/tasks/{id}", "http_status": st,
            "ok": st == 200,
            "detail": ("OK (engine-registered, "
                       f"{registered} deliverables)" if st == 200
                       else str(body)[:300]),
        })
        if st == 200:
            self.report.event(
                "board.review_registered",
                f"parent card {task_id} -> review with "
                f"process_certificate_sha={cert_sha[:12]}... and "
                f"{registered} deliverable(s) registered")
            return True
        return False

    def close(self) -> int:
        gates = Gates(self.run_dir, self.state).evaluate_all()

        # F15 — fail closed on certificate integrity. _mint_process_certificate
        # computes integrity_pass (no unentered phases, substance verified,
        # monotonic timestamps, gates passed) but nothing read it before this
        # fix: a cert minted with FAIL integrity still reached terminal DONE.
        # The gate check runs AFTER evaluate_all() so the same gate failures
        # that would fail here anyway are handled by the normal path; this
        # guard catches integrity gaps the gate list alone does not cover
        # (unentered phases, unverified substance, non-monotonic timestamps).
        def _integrity_block(cert: dict) -> int:
            reasons = cert.get('integrity_fail_reasons') or [
                'AF-PROCESS-INTEGRITY: integrity_pass=False (no specific reasons recorded)']
            lines = "\n".join(f"    - {r}" for r in reasons)
            self.state["terminal"] = "BLOCKED"
            self.state["blocked"] = {
                "phase": "CERT-INTEGRITY",
                "reason": "PROCESS-CERTIFICATE integrity_pass=False",
                "at": utcnow(),
                "gates": [r.split(':', 1)[0] for r in reasons],
            }
            self.store.save(self.state)
            self.report.to_requester(
                "blocked",
                f"Process integrity failed — deck cannot ship: {len(reasons)} integrity violation(s)")
            print("\nCANNOT CLOSE -- process certificate integrity FAILED:", file=sys.stderr)
            print(lines, file=sys.stderr)
            print("\n  Every manifest phase must have run and been substance-verified.", file=sys.stderr)
            print("\n  continue with:", file=sys.stderr)
            print(f"    python3 {ENTRY_COMMAND} --resume --run-dir {self.run_dir}", file=sys.stderr)
            return EXIT_GATE_BLOCKED

        try:
            waivers = load_waivers(self.run_dir)
            for w in waivers:
                validate_waiver(w, self.run_dir)
        except WaiverError as exc:
            self.report.event("waiver.invalid", str(exc))
            print("\nFATAL: " + str(exc), file=sys.stderr)
            print("  Valid waiver: {rule, source, client_request_quote, intake_field?, captured_at, captured_from}", file=sys.stderr)
            print("\n  Resume: python3 presentation_job.py --resume --run-dir " + str(self.run_dir), file=sys.stderr)
            return EXIT_WAIVER_INVALID
        waived = {w.get("rule") for w in waivers if w.get("rule")}
        self.state["waivers"] = waivers
        failures = []
        gate_warnings = []
        for k in ALL_GATE_KEYS:
            g = gates.get(k, {"state": "fail", "reason": "not evaluated"})
            if g.get("state") == "pass":
                continue
            if k in waived and k not in NON_WAIVABLE_GATES:
                g["state"] = "waived"
                continue
            if g.get("warn_only", False):
                gate_warnings.append({"gate": k, "reason": g.get("reason") or "failed"})
                continue
            failures.append((k, g.get("reason") or "failed"))
        if gate_warnings:
            self.state["gate_warnings"] = gate_warnings
            print(f"{len(gate_warnings)} gate(s) in warn-mode did not pass -- see state.json gate_warnings", file=sys.stderr)
        self.store.save(self.state)
        if failures:
            failed_keys = [k for k, _ in failures]
            regated = heal.rung4_regate(self, failed_keys)
            failures = [(k, r.get("reason") or "failed") for k, r in regated.items()
                        if r.get("state") != "pass"]
            if not failures:
                # All failed gates passed on re-evaluation.
                # WORK-ITEM-05: Mint certificate BEFORE terminal transition.
                cert = self._mint_process_certificate()
                if not cert.get('integrity_pass', False):
                    return _integrity_block(cert)
                # WORK-ITEM-13: assemble flat deliverables/ folder.
                try:
                    _curate.curate(self.run_dir)
                except _curate.CurateAlreadyRan:
                    # F50/FIX 106 (SMOKE-1): the regate path re-enters the same
                    # curation the main close path already ran — curate refuses a
                    # second pass by design (duplicate-file safety), and a prior
                    # curation with the full deliverable set present IS the
                    # close-time end state. Treat it as success (mirrors the main
                    # path's catch below) so close() stays idempotent: close
                    # called twice returns success both times instead of crashing
                    # the re-gate branch on CurateAlreadyRan.
                    pass
                except _curate.AFBundleIncomplete as exc:
                    self.state["terminal"] = "BLOCKED"
                    self.state["blocked"] = {
                        "phase": "CURATION",
                        "reason": str(exc),
                        "at": utcnow(),
                        "missing_keys": exc.missing_keys,
                    }
                    self.store.save(self.state)
                    self.report.to_requester(
                        "blocked",
                        f"Curation failed — {len(exc.missing_keys)} deliverable(s) missing: {exc}")
                    print(f"\nCANNOT CLOSE — curation failed:\n{exc}", file=sys.stderr)
                    return EXIT_GATE_BLOCKED
                # WORK-ITEM-16: self-audit runs as the FINAL step before
                # handoff -- after curation succeeds, before terminal=DONE.
                # A non-zero exit REJECTS the handoff.
                audit_ok, audit_reason, audit_output = self._run_self_audit()
                if not audit_ok:
                    self.state["terminal"] = "BLOCKED"
                    self.state["blocked"] = {
                        "phase": "SELF-AUDIT",
                        "reason": audit_reason,
                        "at": utcnow(),
                        "output": audit_output,
                    }
                    self.store.save(self.state)
                    self.report.to_requester(
                        "blocked",
                        f"Self-audit failed before handoff — {audit_reason}")
                    print(f"\nCANNOT CLOSE — self-audit failed:\n{audit_output}", file=sys.stderr)
                    return EXIT_GATE_BLOCKED
                if not self._board_register_close():
                    if self.board:
                        self.board.mark_review()
                self.state["terminal"] = "DONE"
                self.state["completed_at"] = utcnow()
                self.store.save(self.state)
                self.report.to_requester(
                    "done", "Your presentation is ready. All quality checks passed.")
                print("DONE — all gates passed after re-evaluation.", flush=True)
                return EXIT_OK
            self.state["terminal"] = "BLOCKED"
            # Symmetric with _block: write state["blocked"] here too, so a gate-failure
            # park is recorded exactly like a phase-failure park and diagnose.py has one
            # primary source to read (U017). "phase" is the sentinel "CLOSE" because no
            # single manifest phase owns a gate.
            self.state["blocked"] = {
                "phase": "CLOSE",
                "reason": f"{len(failures)} gate(s) did not pass: " +
                          ", ".join(k for k, _ in failures),
                "at": utcnow(),
                "gates": [k for k, _ in failures],
            }
            self.store.save(self.state)
            lines = "\n".join(f"    - {k}: {r}" for k, r in failures)
            print("\nCANNOT CLOSE -- fail-closed gates did not pass:\n" + lines, file=sys.stderr)
            print("\n  A gate can only be skipped with a recorded client waiver. See waivers.json.", file=sys.stderr)
            print("\n  continue with:", file=sys.stderr)
            print(f"    python3 {ENTRY_COMMAND} --resume --run-dir {self.run_dir}", file=sys.stderr)
            return EXIT_GATE_BLOCKED
        # WORK-ITEM-05: Mint certificate BEFORE terminal DONE transition.
        cert = self._mint_process_certificate()
        if not cert.get('integrity_pass', False):
            return _integrity_block(cert)
        # WORK-ITEM-13: assemble flat deliverables/ folder.
        try:
            _curate.curate(self.run_dir)
        except _curate.CurateAlreadyRan:
            # F50 (SMOKE-1, 2026-09-01): close() re-runs curate on EVERY invocation,
            # and curate refuses a second pass by design (duplicate-file safety). A
            # prior curation with the full deliverable set present IS the close-time
            # end state — the fix is to treat it as success, not crash close().
            # Re-verified below by the self-audit (flat folder audit) either way.
            pass
        except _curate.AFBundleIncomplete as exc:
            self.state["terminal"] = "BLOCKED"
            self.state["blocked"] = {
                "phase": "CURATION",
                "reason": str(exc),
                "at": utcnow(),
                "missing_keys": exc.missing_keys,
            }
            self.store.save(self.state)
            self.report.to_requester(
                "blocked",
                f"Curation failed — {len(exc.missing_keys)} deliverable(s) missing: {exc}")
            print(f"\nCANNOT CLOSE — curation failed:\n{exc}", file=sys.stderr)
            return EXIT_GATE_BLOCKED
        # WORK-ITEM-16: self-audit runs as the FINAL step before handoff --
        # after curation succeeds, before terminal=DONE. A non-zero exit
        # REJECTS the handoff.
        audit_ok, audit_reason, audit_output = self._run_self_audit()
        if not audit_ok:
            self.state["terminal"] = "BLOCKED"
            self.state["blocked"] = {
                "phase": "SELF-AUDIT",
                "reason": audit_reason,
                "at": utcnow(),
                "output": audit_output,
            }
            self.store.save(self.state)
            self.report.to_requester(
                "blocked",
                f"Self-audit failed before handoff — {audit_reason}")
            print(f"\nCANNOT CLOSE — self-audit failed:\n{audit_output}", file=sys.stderr)
            return EXIT_GATE_BLOCKED
        if not self._board_register_close():
            if self.board:
                self.board.mark_review()
        self.state["terminal"] = "DONE"
        self.state["completed_at"] = utcnow()
        self.store.save(self.state)
        print("DONE -- all gates passed.", flush=True)
        return EXIT_OK


# ---------------------------------------------------------------------------
# Watchdog. Stall detection is SEPARATE from error detection: a hung tool call
# throws nothing, so error handling never fires (decision #5e).
# ---------------------------------------------------------------------------

