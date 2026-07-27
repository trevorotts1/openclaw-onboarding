#!/usr/bin/env python3
"""
presentation_job.py — the process engine for the Presentation Department.

WHY THIS EXISTS
---------------
`run_signature_deck.py` dispatches real work for only 2 of 26 manifest phases. Its own comment
(run_signature_deck.py:1590-1593) states the other phases "are produced by their owning department
role/agent, and the runner records their attestation once their produces_artifact is present."
A bare invocation with no --phase is a hard error (:1831-1841) — there is NO loop mode. Nothing
connects a Kanban card to the pipeline: zero cron entries, zero launchd jobs.

So the documented process is an invitation an LLM must voluntarily accept ~26 times in the correct
order. Nothing forces the loop; nothing notices when it stops. THIS FILE IS THAT MISSING MACHINE.

WHAT IT IS NOT
--------------
This engine cannot make an LLM act. For the 16 agent-authored phases it emits a precise work order,
then polls for the artifact until a per-phase timeout and announces BLOCKED. That is a STALL
DETECTOR, not an executor. The honest gain: today an unproduced phase is silently skipped and the
deck ships anyway; here it blocks and announces.

DESIGN INVARIANTS (do not break these)
--------------------------------------
1. state.json is the ONLY source of truth. The Kanban board is a mirror. Board sync retries and
   escalates but can NEVER block a build, and can NEVER be why a job is considered done.
2. Every state write is atomic: temp file + os.replace on the same filesystem.
3. Checkpoint BEFORE the expensive call, never after. speech_build_harness.checkpoint_slide()
   (:305-331) checkpoints after and uses a non-atomic write_text — do not copy that shape.
4. The manifest is pinned per job by sha256. A job started under v25 finishes under v25.
5. Fail-closed. A gate that cannot be evaluated is a FAILED gate, not a passed one.
6. Announce BEFORE the first retry, not after the last one.

Author this file in the repo at:
  23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job.py
That directory's scripts are already byte-identical to the box, so the existing installer delivers it.

Python 3.9+. Standard library only — no third-party imports in this module.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Exit codes. Documented so callers, CI, and the watchdog can branch on them.
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_GATE_BLOCKED = 3        # fail-closed: a required gate did not pass
EXIT_EXECUTOR_FAILED = 4     # a script executor failed after the heal ladder
EXIT_STALLED = 5             # no checkpoint progress inside the phase budget
EXIT_LOCK_HELD = 6           # another job owns this run dir
EXIT_MANIFEST_MISMATCH = 7   # pinned manifest sha256 != manifest on disk
EXIT_STATE_CORRUPT = 8       # state.json unreadable or schema-invalid
EXIT_WAIVER_INVALID = 9      # a waiver was presented but failed validation

STATE_FILENAME = "state.json"
LOCK_FILENAME = ".job.lock"
STATE_SCHEMA_VERSION = 1

# The five gates from the ratified fail-closed decision. Order is report order.
GATE_KEYS = ("script", "teleprompter", "prompt_floor", "ghl_upload", "qc")
# ocr_readback is a sixth gate but is NOT waivable — a self-disabled check is not a pass.
NON_WAIVABLE_GATES = ("ocr_readback",)
ALL_GATE_KEYS = GATE_KEYS + NON_WAIVABLE_GATES

QC_PASS_THRESHOLD = 8.5

# Heal ladder caps, per phase attempt.
HEAL_CAP_TRANSIENT = 3
HEAL_CAP_REGENERATE = 2
HEAL_CAP_ALT_ROUTE = 1
HEAL_CAP_REGATE = 1

# Default per-phase budget when the manifest declares no heartbeat_minutes.
# The live v18 manifest declares client_report on 0/20 phases and heartbeat_minutes on 0/20;
# the canonical v25 declares client_report on 26/26 and heartbeat_minutes on only 3/26
# (the three long_running phases, at 10 minutes). So most phases need a default, and the
# table below supplies one per phase class rather than leaving 23 phases with no threshold.
DEFAULT_PHASE_BUDGET_MINUTES = 20
PHASE_BUDGET_MINUTES: Dict[str, int] = {
    # long_running in the canonical manifest
    "P-0.5-RESEARCH": 45,
    "P-3.5-RESEARCH-MAP": 30,
    "P4-RENDER": 240,          # 62 slides of image generation is genuinely slow
    # scripted, fast
    "P0A-INTAKE": 60,          # human-paced: one question per turn
    "P-SP-INTAKE": 60,
    "P-SP-INTAKE-TRACE": 60,
    "P-SP-CLAIM": 10,
    "P-STYLE-PREVIEW": 45,
    "P8-ASSEMBLE": 30,
    "P8.1-PDF-EXPORT": 15,
    "P8.2-GUIDE": 20,
    "P8.4-FISH-TAG": 15,
    "P9-SPEECH": 45,
    "P9.1-SPEECH-PDF": 15,
    "P9.2-GHL-UPLOAD": 30,
    "P9.5-NOTES-SYNC": 20,
    # These five phase ids do not exist in manifest v25 (26 phases). U012 creates them.
    # Budgets are pre-seeded here on purpose so U012 does not have to touch this table.
    "P7-TELEPROMPTER": 10,
    "P9-DELIVER": 30,
    # agent-authored authoring phases
    "P-CONVERTER": 40,
    "P0B-PRIORITY": 30,
    "P3-ARC": 30,
    "P4-COPY": 60,
    "P-SP-STRUCTURE": 45,
    "P-SP-P3-HYGIENE": 20,
    "PF-DESIGN": 30,
    "P4-PROMPT": 90,           # 9,000+ chars per slide, authored
    # QC phases
    "P1Q-COPY-QC": 20,
    "P-TYPO-QC": 20,
    "P-PROMPT-QC": 20,
    "P-IMAGE-QC": 30,
    "P-SHIFT-QC": 20,
    "P-SPEECH-QC": 20,
}


def utcnow() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Atomic state store. Invariant 2.
# ---------------------------------------------------------------------------
class StateStore:
    """Reads and writes state.json atomically. Never leaves a partial file behind."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.path = run_dir / STATE_FILENAME

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> Dict[str, Any]:
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                state = json.load(fh)
        except FileNotFoundError:
            die(EXIT_STATE_CORRUPT, f"no {STATE_FILENAME} in {self.run_dir} — run --new first")
        except (json.JSONDecodeError, OSError) as exc:
            die(EXIT_STATE_CORRUPT, f"{self.path} is unreadable: {exc}")
        if not isinstance(state, dict) or "job_id" not in state:
            die(EXIT_STATE_CORRUPT, f"{self.path} is not a valid job state document")
        if state.get("schema_version") != STATE_SCHEMA_VERSION:
            die(EXIT_STATE_CORRUPT,
                f"state schema {state.get('schema_version')} != expected {STATE_SCHEMA_VERSION}")
        return state

    def save(self, state: Dict[str, Any]) -> None:
        """Atomic: write to a temp file in the same directory, fsync, then os.replace."""
        state["updated_at"] = utcnow()
        payload = json.dumps(state, indent=2, ensure_ascii=False, sort_keys=False)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.run_dir), prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)          # atomic on the same filesystem
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


class RunLock:
    """Exclusive advisory lock per run dir. Two engines over one state.json corrupts it."""

    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / LOCK_FILENAME
        self._fh = None

    def __enter__(self) -> "RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a+")
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._fh.close()
            die(EXIT_LOCK_HELD,
                f"another presentation_job owns {self.path.parent} — refusing to start a second")
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(f"{os.getpid()} {utcnow()}\n")
        self._fh.flush()
        return self

    def __exit__(self, *exc) -> None:
        if self._fh:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()


def die(code: int, message: str) -> None:
    print(f"FATAL: {message}", file=sys.stderr, flush=True)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Manifest. Pinned per job (invariant 4).
# ---------------------------------------------------------------------------
@dataclass
class Phase:
    id: str
    order: float
    owning_role: str
    produces_artifact: List[str]
    executor_kind: str                  # "script" | "agent" | "none"
    executor_cmd: Optional[str]
    verifier: Optional[str]
    client_report: Dict[str, Any] = field(default_factory=dict)
    heartbeat_minutes: Optional[int] = None
    long_running: bool = False

    @property
    def budget_minutes(self) -> int:
        """
        TOTAL time this phase may take, in minutes. Feeds the subprocess timeout.

        DO NOT derive this from the manifest's `heartbeat_minutes`. They are different concepts and
        conflating them is a render-killing bug: the canonical manifest sets heartbeat_minutes=10 on
        P4-RENDER, so returning it here would kill a 62-slide render after 10 minutes. The budget is
        240. See `heartbeat_interval_minutes` below for the watchdog's separate value.
        """
        return PHASE_BUDGET_MINUTES.get(self.id, DEFAULT_PHASE_BUDGET_MINUTES)

    @property
    def heartbeat_interval_minutes(self) -> int:
        """
        How often this phase is expected to CHECKPOINT — the watchdog's comparison value, not a
        timeout. The watchdog compares last-checkpoint AGE against this, never total elapsed.
        Falls back to the full budget for phases that checkpoint only on completion.
        """
        if self.heartbeat_minutes:
            return int(self.heartbeat_minutes)
        return self.budget_minutes


class Manifest:
    """
    Loads PIPELINE-MANIFEST.json and REFUSES to fall back silently.

    The bug this replaces: run_signature_deck.load_manifest() (:239-252) walks up looking for a
    `universal-sops` directory; from the materialized department tree no ancestor has one, so it
    silently loads the stale local v18 copy. Four separate resolvers share that shape
    (gate_integrity_check.py:77, runner_gate_integrity_check.py:86, sync_check.py:98).
    Here: resolve, then verify against MANIFEST-SOURCE.txt, then hard-fail on mismatch.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.sha256 = sha256_file(path)
        try:
            self.raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            die(EXIT_MANIFEST_MISMATCH, f"cannot parse manifest {path}: {exc}")
        self.version = self.raw.get("manifest_version")
        self.phases = self._parse_phases()
        self.deliverables = self.raw.get("deliverables_required", [])
        self.client_package = self.raw.get("client_package_files", [])

    def _parse_phases(self) -> List[Phase]:
        out: List[Phase] = []
        for p in self.raw.get("phases", []):
            ex = p.get("executor") or {}
            out.append(Phase(
                id=p["id"],
                order=float(p.get("order", 0)),
                owning_role=p.get("owning_role") or "",
                produces_artifact=_as_list(p.get("produces_artifact")),
                # NOTE: no phase in either shipped manifest declares an executor, and `verifier`
                # is not a field at all. Until the phase contract lands (fix A3), everything
                # resolves to "agent" — which is exactly why A3 must ship in warn-mode first.
                executor_kind=(ex.get("kind") or "agent"),
                executor_cmd=ex.get("cmd"),
                verifier=p.get("verifier"),
                client_report=p.get("client_report") or {},
                heartbeat_minutes=p.get("heartbeat_minutes"),
                long_running=bool(p.get("long_running")),
            ))
        out.sort(key=lambda x: x.order)
        return out

    def verify_pin(self, pinned_sha: str) -> None:
        if pinned_sha and pinned_sha != self.sha256:
            die(EXIT_MANIFEST_MISMATCH,
                "manifest changed under a running job.\n"
                f"  pinned : {pinned_sha}\n  on disk: {self.sha256}\n"
                f"  file   : {self.path}\n"
                "A job started under one manifest must finish under it. Resume with the pinned "
                "copy, or start a new job.")

    def verify_source(self) -> None:
        """Assert the installed manifest matches its recorded upstream (fix A1 step 3)."""
        src = self.path.parent / "MANIFEST-SOURCE.txt"
        if not src.is_file():
            print(f"WARN: no MANIFEST-SOURCE.txt beside {self.path.name} — provenance unverifiable "
                  "(fix A1 installs it)", file=sys.stderr)
            return
        recorded = {}
        for line in src.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                recorded[k.strip()] = v.strip()
        if recorded.get("content_sha256") and recorded["content_sha256"] != self.sha256:
            die(EXIT_MANIFEST_MISMATCH,
                f"installed manifest does not match its recorded source.\n"
                f"  recorded: {recorded['content_sha256']}\n  actual  : {self.sha256}")

    def phase(self, phase_id: str) -> Phase:
        for p in self.phases:
            if p.id == phase_id:
                return p
        die(EXIT_USAGE, f"unknown phase id {phase_id!r} in manifest v{self.version} "
                        f"({len(self.phases)} phases). Known: {', '.join(p.id for p in self.phases)}")


def _as_list(v: Any) -> List[str]:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [str(v)]


# The canonical manifest as of this writing. A resolved manifest below this version is
# the stale fork and MUST NOT be run: it lacks the six signature phases and all sixteen
# AF-SP-* codes, so a job would pass every gate it knows about while skipping the gates
# it has never heard of.
MIN_MANIFEST_VERSION = 25
MIN_MANIFEST_PHASES = 26


def _assert_manifest_current(path: Path) -> None:
    """Refuse to run on a stale manifest. Exit 7, never a warning."""
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        die(EXIT_MANIFEST_MISMATCH, f"cannot parse manifest {path}: {exc}")
    version = obj.get("manifest_version")
    phases = len(obj.get("phases") or [])
    af_sp = [a for a in (obj.get("autofails") or [])
             if str(a.get("code", "")).startswith("AF-SP-")]
    if not isinstance(version, int) or version < MIN_MANIFEST_VERSION or phases < MIN_MANIFEST_PHASES:
        die(EXIT_MANIFEST_MISMATCH,
            f"STALE MANIFEST — refusing to run.\n"
            f"  file    : {path}\n"
            f"  found   : version {version}, {phases} phases, {len(af_sp)} AF-SP-* codes\n"
            f"  required: version >= {MIN_MANIFEST_VERSION}, >= {MIN_MANIFEST_PHASES} phases\n"
            "  The department copy is a stale fork that omits the signature-presentation\n"
            "  phases and every AF-SP-* gate. Running it would report completeness while\n"
            "  silently skipping those gates. Install the canonical manifest (fix A1), or\n"
            "  pass --manifest pointing at universal-sops/presentation-slide-craft/.")
    src = path.parent / "MANIFEST-SOURCE.txt"
    if src.is_file():
        want = ""
        for line in src.read_text(encoding="utf-8").splitlines():
            if line.startswith("content_sha256="):
                want = line.split("=", 1)[1].strip()
        if want and want != sha256_file(path):
            die(EXIT_MANIFEST_MISMATCH,
                f"manifest does not match its recorded source.\n"
                f"  recorded: {want}\n  actual  : {sha256_file(path)}\n  file    : {path}")


def resolve_manifest(explicit: Optional[str], run_dir: Path, scripts_dir: Path) -> Path:
    """
    Resolution order, and it NEVER guesses past this list:
      1. --manifest
      2. <scripts_dir>/../sops/PIPELINE-MANIFEST.json   (the materialized department)
      3. $PRESENTATION_MANIFEST
    No walk-up search. A missing manifest is a hard error, not a fallback.

    ⚠️ RESOLVING IS NOT ENOUGH — THE RESOLVED FILE MUST ALSO BE CURRENT.
    On a real box, candidate 2 is the STALE v18 fork: 20 phases, 126 autofails, and ZERO
    of the six signature phases or sixteen AF-SP-* codes. Simply returning it would make
    this engine silently run a 20-phase pipeline while reporting completeness — the exact
    failure it was written to prevent. So every resolved manifest is version-gated by
    _assert_manifest_current() below, and a stale one is a hard error (exit 7), not a
    warning. Fix A1 installs the canonical manifest; until then this refuses to run.
    """
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            die(EXIT_USAGE, f"--manifest {p} does not exist")
        _assert_manifest_current(p)
        return p
    cand = (scripts_dir.parent / "sops" / "PIPELINE-MANIFEST.json").resolve()
    if cand.is_file():
        _assert_manifest_current(cand)
        return cand
    env = os.environ.get("PRESENTATION_MANIFEST")
    if env and Path(env).is_file():
        p = Path(env).resolve()
        _assert_manifest_current(p)
        return p
    die(EXIT_USAGE,
        "cannot locate PIPELINE-MANIFEST.json. Pass --manifest explicitly.\n"
        f"  tried: {cand}\n"
        "  This engine refuses to search upward — a silent fallback to a stale manifest is the "
        "bug it exists to prevent.")


# ---------------------------------------------------------------------------
# Reporting. Announce BEFORE retrying (invariant 6).
# ---------------------------------------------------------------------------
class Reporter:
    """
    Emits to three places, in this order of reliability:
      1. state.json events   — always, durable, local
      2. stdout              — always
      3. the board + Telegram — best effort, retried, NEVER blocking

    The bug this avoids: trust-engine.ts:469-499 commits the *_sent_at stamp inside a transaction
    BEFORE dispatching (:512-519), and rolls back on neither a false return nor a throw. Result:
    permanently marked delivered, permanently never delivered. Here a send is only recorded as
    delivered when the transport confirms it; otherwise it is recorded as undeliverable and queued.
    """

    def __init__(self, state: Dict[str, Any], store: StateStore) -> None:
        self.state = state
        self.store = store

    def event(self, kind: str, message: str, **extra: Any) -> None:
        ev = {"at": utcnow(), "kind": kind, "message": message}
        ev.update(extra)
        self.state.setdefault("events", []).append(ev)
        self.store.save(self.state)
        print(f"[{ev['at']}] {kind}: {message}", flush=True)

    def to_requester(self, kind: str, message: str) -> None:
        """
        kind ∈ {ack, progress, blocked, done}.
        BLOCKED and DONE ignore quiet hours. trust-engine.ts:219-223 currently holds EVERYTHING
        during 22:00-07:00 including completion — "your deck is ready" and "your deck is stuck"
        must never wait nine hours.
        """
        req = self.state.get("requester") or {}
        chat_id = req.get("chat_id")
        self.event(f"report.{kind}", message, requester=bool(chat_id))
        if not chat_id:
            # Fix F1 makes this a hard intake error. Until then, record and continue.
            self.event("report.undeliverable",
                       f"no requester chat_id on this job — {kind} message not sent")
            return
        ok = self._dispatch(chat_id, kind, message)
        if ok:
            self.state.setdefault("sent", {})[kind] = utcnow()
        else:
            self.state.setdefault("undeliverable", []).append(
                {"at": utcnow(), "kind": kind, "message": message, "chat_id_present": True})
        self.store.save(self.state)

    def _dispatch(self, chat_id: str, kind: str, message: str) -> bool:
        """Transport boundary. Returns True only on CONFIRMED delivery."""
        cmd = os.environ.get("PRESENTATION_NOTIFY_CMD")
        if not cmd:
            return False
        try:
            r = subprocess.run(cmd, shell=True, input=json.dumps(
                {"chat_id": chat_id, "kind": kind, "message": message}),
                text=True, capture_output=True, timeout=30)
            return r.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False


# ---------------------------------------------------------------------------
# Gates. Fail-closed (invariant 5).
# ---------------------------------------------------------------------------
class Gates:
    """
    close_job() is permitted only if every gate is pass or a VALID waiver exists,
    qc.score >= 8.5, and ocr_readback.checked is true (ocr is not waivable).
    """

    def __init__(self, run_dir: Path, state: Dict[str, Any]) -> None:
        self.run_dir = run_dir
        self.state = state

    def evaluate_all(self) -> Dict[str, Dict[str, Any]]:
        g = self.state.setdefault("gates", {})
        g["script"] = self._artifact_gate("working/deliverables/PRESENTERS-SPEECH.md", 2048)
        g["teleprompter"] = self._artifact_gate(
            "working/deliverables/presenter-teleprompter.html", 10240)
        g["prompt_floor"] = self._prompt_floor_gate()
        g["ghl_upload"] = self._ghl_gate()
        g["qc"] = self._qc_gate()
        g["ocr_readback"] = self._ocr_gate()
        return g

    def _artifact_gate(self, rel: str, min_bytes: int) -> Dict[str, Any]:
        p = self.run_dir / rel
        if not p.is_file():
            return {"state": "fail", "evidence": rel, "reason": f"{rel} does not exist"}
        size = p.stat().st_size
        if size < min_bytes:
            return {"state": "fail", "evidence": rel,
                    "reason": f"{rel} is {size} bytes, below the {min_bytes}-byte floor"}
        return {"state": "pass", "evidence": rel, "bytes": size, "reason": None}

    def _prompt_floor_gate(self) -> Dict[str, Any]:
        """PROMPT_CHAR_FLOOR = 9000 (prompt_gate.py:89, build_deck.py:325)."""
        floor = 9000
        d = self.run_dir / "working" / "prompts"
        if not d.is_dir():
            return {"state": "fail", "evidence": "working/prompts",
                    "reason": "no prompts directory — nothing to measure"}
        files = sorted(d.glob("slide-*.txt"))
        if not files:
            return {"state": "fail", "evidence": "working/prompts",
                    "reason": "prompts directory is empty"}
        lengths = [(f.name, len(f.read_text(encoding="utf-8", errors="replace"))) for f in files]
        short = [(n, L) for n, L in lengths if L < floor]
        base = {"evidence": "working/prompts", "slides_checked": len(lengths),
                "min_chars_seen": min(L for _, L in lengths)}
        if short:
            return {**base, "state": "fail",
                    "reason": f"{len(short)} prompt(s) below the {floor}-char floor: " +
                              ", ".join(f"{n}={L}" for n, L in short[:5])}
        return {**base, "state": "pass", "reason": None}

    def _ghl_gate(self) -> Dict[str, Any]:
        """
        Unconditional. delivery_gate.py:256-259 only demands the media id when an LLM-authored
        delivery_plan.json declares a `ghl` destination — the agent deletes its own obligation by
        staying silent (fix C2). Here the gate reads the engine's own record.
        """
        p = self.run_dir / "working" / "checkpoints" / "media_library.json"
        if not p.is_file():
            return {"state": "fail", "evidence": str(p.relative_to(self.run_dir)),
                    "reason": "no GHL media-library record — the upload phase did not run"}
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {"state": "fail", "reason": f"media_library.json unreadable: {exc}"}
        ids = obj.get("media_ids") or []
        if not ids:
            return {"state": "fail", "reason": "media_library.json records zero uploaded assets"}
        return {"state": "pass", "media_ids": ids, "folder_id": obj.get("folder_id"),
                "reason": None}

    def _qc_gate(self) -> Dict[str, Any]:
        p = self.run_dir / "working" / "qc" / "final_qc_report.json"
        if not p.is_file():
            return {"state": "fail", "reason": "no final QC report"}
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {"state": "fail", "reason": f"QC report unreadable: {exc}"}
        score = obj.get("average") or obj.get("score")
        if not isinstance(score, (int, float)):
            return {"state": "fail", "reason": "QC report carries no numeric score"}
        if score < QC_PASS_THRESHOLD:
            return {"state": "fail", "score": score,
                    "reason": f"QC score {score} is below the {QC_PASS_THRESHOLD} threshold"}
        return {"state": "pass", "score": score,
                "per_dimension": obj.get("per_dimension"), "reason": None}

    def _ocr_gate(self) -> Dict[str, Any]:
        """
        NOT WAIVABLE. prompt_gate.ocr_readback (:551) is the ONLY check in the whole pipeline that
        reads a finished slide's own content — and _ocr_engine_available (:514-526) returns
        (None, None) without tesseract, after which the guard at build_deck.py:1321 cannot fire.
        A self-disabled check is not a pass (fix D7).
        """
        d = self.run_dir / "renders"
        sidecars = sorted(d.glob("slide-*.ocr.json")) if d.is_dir() else []
        if not sidecars:
            return {"state": "fail", "checked": False,
                    "reason": "no OCR readback records. Either no slides were rendered, or the OCR "
                              "engine is not installed on this box. Install tesseract + "
                              "pytesseract; a self-disabled check does not count as a pass."}
        unchecked, mismatched = [], []
        for s in sidecars:
            try:
                o = json.loads(s.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                unchecked.append(s.name)
                continue
            if not o.get("checked"):
                unchecked.append(s.name)
            elif o.get("matched") is False:
                mismatched.append(s.name)
        if unchecked:
            return {"state": "fail", "checked": False,
                    "reason": f"{len(unchecked)} slide(s) have no completed OCR check "
                              f"(engine missing or skipped): {', '.join(unchecked[:5])}"}
        if mismatched:
            return {"state": "fail", "checked": True,
                    "reason": f"{len(mismatched)} slide(s) failed OCR readback — the words on the "
                              f"slide do not match approved copy: {', '.join(mismatched[:5])}"}
        return {"state": "pass", "checked": True, "slides": len(sidecars), "reason": None}


# ---------------------------------------------------------------------------
# Waivers. The only bypass, and it must not be self-issuable.
# ---------------------------------------------------------------------------
class WaiverError(Exception):
    pass


def load_waivers(run_dir: Path) -> List[Dict[str, Any]]:
    p = run_dir / "waivers.json"
    if not p.is_file():
        return []
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise WaiverError(f"waivers.json is unreadable: {exc}")
    return obj if isinstance(obj, list) else [obj]


def validate_waiver(w: Dict[str, Any], run_dir: Path) -> None:
    """
    A waiver must be traceable to the CLIENT, not to the agent that wants the skip.

    v1 of the plan required matching the quote against "the recorded conversation", which is not
    implementable for a Telegram-routed request (route-presentation.sh:101-107 sends five keys and
    no requester identity). So the accepted evidence is, in order of strength:
      1. intake_field  — a form field the client set (strongest; the form is the consent record)
      2. transcript    — a verbatim quote found in working/interview/intake_transcript.json,
                         which is written turn-by-turn by deck-intake-driver.py:1273-1298, a
                         DIFFERENT producer than the build being certified
    An empty, unquoted, or unsourced waiver is invalid. See the plan's D3 for the eight hardening
    changes still needed before a transcript quote is consent-grade.
    """
    rule = w.get("rule")
    if rule not in GATE_KEYS:
        raise WaiverError(f"waiver names {rule!r}, which is not a waivable gate. "
                          f"Waivable: {', '.join(GATE_KEYS)}. "
                          f"Never waivable: {', '.join(NON_WAIVABLE_GATES)}")
    if rule in NON_WAIVABLE_GATES:
        raise WaiverError(f"gate {rule!r} cannot be waived")
    src = w.get("source")
    if src not in ("intake_field", "transcript"):
        raise WaiverError(f"waiver for {rule!r} has source={src!r}; must be "
                          "'intake_field' or 'transcript'")
    quote = (w.get("client_request_quote") or "").strip()
    if len(quote) < 3:
        raise WaiverError(f"waiver for {rule!r} carries no client_request_quote — "
                          "a waiver the agent wrote for itself is not a waiver")
    if not w.get("captured_at"):
        raise WaiverError(f"waiver for {rule!r} has no captured_at timestamp")

    if src == "intake_field":
        intake = _read_json(run_dir / "working" / "copy" / "intake.json") or {}
        field_name = w.get("intake_field")
        if not field_name or field_name not in intake:
            raise WaiverError(f"waiver for {rule!r} cites intake field {field_name!r}, "
                              "which is not present in intake.json")
        return

    tp = run_dir / "working" / "interview" / "intake_transcript.json"
    if not tp.is_file():
        raise WaiverError(f"waiver for {rule!r} cites the transcript, but "
                          "working/interview/intake_transcript.json does not exist. "
                          "An absent transcript is not proof of client consent.")
    try:
        turns = json.loads(tp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise WaiverError(f"transcript unreadable: {exc}")
    owner_text = " ".join(
        (t.get("text") or "") for t in turns
        if isinstance(t, dict) and (t.get("role") or "").lower() in ("owner", "user", "client"))
    if _norm(quote) not in _norm(owner_text):
        raise WaiverError(
            f"waiver for {rule!r} quotes text that does not appear in any client turn of the "
            "recorded transcript. The quote must be the client's own words.")


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _read_json(p: Path) -> Optional[Dict[str, Any]]:
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


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

    # -- state helpers ----------------------------------------------------
    def _phase_state(self, pid: str) -> Dict[str, Any]:
        for ps in self.state.setdefault("phases", []):
            if ps["id"] == pid:
                return ps
        ps = {"id": pid, "status": "pending", "artifacts": [], "sha256": {},
              "attempts": 0, "heal_events": [], "attested_at": None}
        self.state["phases"].append(ps)
        return ps

    def _checkpoint(self, pid: str, **fields: Any) -> None:
        """Invariant 3: called BEFORE an expensive call, and again after success."""
        ps = self._phase_state(pid)
        ps.update(fields)
        hb = self.state.setdefault("heartbeat", {})
        hb["last_checkpoint_at"] = utcnow()
        hb["current_phase"] = pid
        self.store.save(self.state)

    # -- verification -----------------------------------------------------
    def _artifacts_present(self, phase: Phase) -> Tuple[bool, List[str]]:
        missing = []
        for rel in phase.produces_artifact:
            matches = list(self.run_dir.glob(rel)) if any(c in rel for c in "*?[") \
                else ([self.run_dir / rel] if (self.run_dir / rel).exists() else [])
            if not matches:
                missing.append(rel)
        return (not missing), missing

    # -- executors --------------------------------------------------------
    def run_phase(self, phase: Phase) -> int:
        ps = self._phase_state(phase.id)
        if ps.get("status") == "done":
            print(f"SKIP {phase.id}: already done (resuming reuses banked work)", flush=True)
            return EXIT_OK

        self.state["current_phase"] = phase.id
        self.state.setdefault("heartbeat", {})["phase_started_at"] = utcnow()
        self._checkpoint(phase.id, status="running", attempts=ps.get("attempts", 0) + 1)

        start_msg = (phase.client_report.get("start_template") or
                     f"Starting {phase.id} ({phase.owning_role})")
        self.report.to_requester("progress", start_msg)

        if phase.executor_kind == "script":
            rc = self._run_script_phase(phase)
        elif phase.executor_kind == "agent":
            rc = self._run_agent_phase(phase)
        else:
            self.report.event("phase.no_executor",
                              f"{phase.id} declares no executor. This is an install-time error "
                              "once fix A3 is enforced; blocking rather than skipping.")
            return self._block(phase, "no executor is defined for this phase")

        if rc == EXIT_OK:
            ok, missing = self._artifacts_present(phase)
            if not ok:
                return self._block(phase, f"produced no artifact: missing {', '.join(missing)}")
            shas = {}
            for rel in phase.produces_artifact:
                for m in self.run_dir.glob(rel) if any(c in rel for c in "*?[") else [self.run_dir / rel]:
                    if m.is_file():
                        shas[str(m.relative_to(self.run_dir))] = sha256_file(m)
            self._checkpoint(phase.id, status="done", attested_at=utcnow(), sha256=shas,
                             artifacts=sorted(shas.keys()))
            done_msg = (phase.client_report.get("done_template") or f"{phase.id} complete")
            self.report.to_requester("progress", done_msg)
        return rc

    def _run_script_phase(self, phase: Phase) -> int:
        cmd = (phase.executor_cmd or "").replace("{run_dir}", str(self.run_dir))
        if not cmd:
            return self._block(phase, "executor kind is 'script' but no cmd is declared")
        if self.dry_run:
            print(f"DRY-RUN {phase.id}: {cmd}", flush=True)
            return EXIT_OK

        # Checkpoint BEFORE the expensive call (invariant 3), so a resume never re-burns it.
        self._checkpoint(phase.id, pending_cmd=cmd, pending_started_at=utcnow())
        budget = phase.budget_minutes * 60
        for attempt in range(1, HEAL_CAP_TRANSIENT + 1):
            try:
                r = subprocess.run(cmd, shell=True, cwd=str(self.run_dir),
                                   timeout=budget, capture_output=False)
                if r.returncode == 0:
                    return EXIT_OK
                reason = f"exit {r.returncode}"
            except subprocess.TimeoutExpired:
                reason = f"exceeded its {phase.budget_minutes}-minute budget"
            except OSError as exc:
                reason = f"could not start: {exc}"

            self._heal_event(phase, rung=1, attempt=attempt, reason=reason)
            # ANNOUNCE BEFORE RETRYING (invariant 6).
            self.report.to_requester(
                "blocked",
                f"{phase.id} failed ({reason}). Retrying — attempt {attempt} of "
                f"{HEAL_CAP_TRANSIENT}. Nothing you need to do yet.")
            if attempt < HEAL_CAP_TRANSIENT:
                time.sleep(min(60, 5 * (2 ** (attempt - 1))))
        return self._block(phase, f"script executor failed after {HEAL_CAP_TRANSIENT} attempts")

    def _run_agent_phase(self, phase: Phase) -> int:
        """
        Emit a work order, then poll for the artifact until the phase budget expires.
        This is a stall detector, not an executor — see the module docstring. The gain over today
        is that a missing artifact BLOCKS AND ANNOUNCES instead of being silently skipped.
        """
        order = {
            "phase": phase.id, "owning_role": phase.owning_role,
            "produces_artifact": phase.produces_artifact,
            "verifier": phase.verifier,
            "budget_minutes": phase.budget_minutes,
            "issued_at": utcnow(),
        }
        wo = self.run_dir / "working" / "work-orders"
        wo.mkdir(parents=True, exist_ok=True)
        (wo / f"{phase.id}.json").write_text(json.dumps(order, indent=2), encoding="utf-8")
        self.report.event("phase.work_order",
                          f"{phase.id} is agent-authored. Work order written to "
                          f"working/work-orders/{phase.id}.json. Waiting for "
                          f"{', '.join(phase.produces_artifact)}.")
        if self.dry_run:
            return EXIT_OK

        deadline = time.time() + phase.budget_minutes * 60
        announced_half = False
        while time.time() < deadline:
            ok, _ = self._artifacts_present(phase)
            if ok:
                return EXIT_OK
            remaining = deadline - time.time()
            if not announced_half and remaining < (phase.budget_minutes * 60) / 2:
                announced_half = True
                self.report.to_requester(
                    "progress",
                    f"Still waiting on {phase.id} ({phase.owning_role}). "
                    f"About {int(remaining/60)} minutes before I flag it.")
            time.sleep(15)
        return self._block(
            phase,
            f"agent-authored phase produced nothing within {phase.budget_minutes} minutes. "
            f"Expected: {', '.join(phase.produces_artifact)}")

    def _heal_event(self, phase: Phase, rung: int, attempt: int, reason: str) -> None:
        self._phase_state(phase.id).setdefault("heal_events", []).append(
            {"at": utcnow(), "rung": rung, "attempt": attempt, "reason": reason})
        self.store.save(self.state)

    def _block(self, phase: Phase, reason: str) -> int:
        """Park resumable. Never die, never restart from scratch (decision #5)."""
        self._checkpoint(phase.id, status="blocked", blocked_reason=reason)
        self.state["terminal"] = "BLOCKED"
        self.state["blocked"] = {"phase": phase.id, "reason": reason, "at": utcnow()}
        banked = [a for ps in self.state.get("phases", []) if ps.get("status") == "done"
                  for a in ps.get("artifacts", [])]
        self.store.save(self.state)
        self.report.to_requester(
            "blocked",
            f"Your presentation is paused at {phase.id}. {reason} "
            f"{len(banked)} file(s) already produced are saved — nothing is lost. "
            "We have been told and are looking at it.")
        print("\n" + "=" * 72, file=sys.stderr)
        print(f"BLOCKED at {phase.id}", file=sys.stderr)
        print(f"  reason   : {reason}", file=sys.stderr)
        print(f"  owner    : {phase.owning_role}", file=sys.stderr)
        print(f"  expected : {', '.join(phase.produces_artifact) or '(none declared)'}",
              file=sys.stderr)
        print(f"  banked   : {len(banked)} artifact(s) — reused on resume, not regenerated",
              file=sys.stderr)
        print("\n  continue with:", file=sys.stderr)
        print(f"    python3 {Path(__file__).name} --resume --run-dir {self.run_dir}",
              file=sys.stderr)
        print("=" * 72 + "\n", file=sys.stderr)
        return EXIT_GATE_BLOCKED

    # -- the loop ---------------------------------------------------------
    def run(self, only: Optional[str] = None, until: Optional[str] = None) -> int:
        phases = self.manifest.phases
        if only:
            phases = [self.manifest.phase(only)]
        elif until:
            stop = self.manifest.phase(until)
            phases = [p for p in phases if p.order <= stop.order]

        if not self.state.get("sent", {}).get("ack"):
            n = len(phases)
            self.report.to_requester(
                "ack",
                f"Got it. Building your presentation in {n} steps. "
                "I will tell you as each step finishes, and immediately if anything stops.")

        for p in phases:
            rc = self.run_phase(p)
            if rc != EXIT_OK:
                return rc

        if only:
            return EXIT_OK
        return self.close()

    def close(self) -> int:
        """Fail-closed. Every gate must pass or carry a valid waiver."""
        gates = Gates(self.run_dir, self.state).evaluate_all()
        try:
            waivers = load_waivers(self.run_dir)
            for w in waivers:
                validate_waiver(w, self.run_dir)
        except WaiverError as exc:
            self.report.event("waiver.invalid", str(exc))
            print(f"FATAL: {exc}", file=sys.stderr)
            return EXIT_WAIVER_INVALID
        waived = {w["rule"] for w in waivers}
        self.state["waivers"] = waivers

        failures = []
        for k in ALL_GATE_KEYS:
            g = gates.get(k, {"state": "fail", "reason": "not evaluated"})
            if g.get("state") == "pass":
                continue
            if k in waived and k not in NON_WAIVABLE_GATES:
                g["state"] = "waived"
                continue
            failures.append((k, g.get("reason") or "failed"))

        self.store.save(self.state)
        if failures:
            self.state["terminal"] = "BLOCKED"
            self.store.save(self.state)
            lines = "\n".join(f"    - {k}: {r}" for k, r in failures)
            self.report.to_requester(
                "blocked",
                "Your presentation is finished building but cannot be delivered yet — "
                f"{len(failures)} quality check(s) did not pass. We are on it.")
            print("\nCANNOT CLOSE — fail-closed gates did not pass:\n" + lines, file=sys.stderr)
            print("\n  A gate can only be skipped with a recorded client waiver. See waivers.json.",
                  file=sys.stderr)
            return EXIT_GATE_BLOCKED

        self.state["terminal"] = "DONE"
        self.state["completed_at"] = utcnow()
        self.store.save(self.state)
        self.report.to_requester(
            "done", "Your presentation is ready. All quality checks passed.")
        print("DONE — all gates passed.", flush=True)
        return EXIT_OK


# ---------------------------------------------------------------------------
# Watchdog. Stall detection is SEPARATE from error detection: a hung tool call
# throws nothing, so error handling never fires (decision #5e).
# ---------------------------------------------------------------------------
def watchdog(scan_root: Path, grace_multiplier: float = 1.5) -> int:
    stalled = []
    for state_path in scan_root.glob("*/state.json"):
        st = _read_json(state_path)
        if not st or st.get("terminal") in ("DONE", "BLOCKED"):
            continue
        hb = st.get("heartbeat") or {}
        last = hb.get("last_checkpoint_at")
        pid = hb.get("current_phase") or st.get("current_phase") or "?"
        if not last:
            continue
        try:
            age_min = (datetime.now(timezone.utc) -
                       datetime.fromisoformat(last).astimezone(timezone.utc)).total_seconds() / 60
        except ValueError:
            continue
        budget = PHASE_BUDGET_MINUTES.get(pid, DEFAULT_PHASE_BUDGET_MINUTES)
        if age_min > budget * grace_multiplier:
            stalled.append((state_path.parent, pid, round(age_min, 1), budget))
    for run_dir, pid, age, budget in stalled:
        print(f"STALLED {run_dir}: phase {pid} last checkpointed {age} min ago "
              f"(budget {budget} min)", flush=True)
    return EXIT_STALLED if stalled else EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="presentation_job.py",
        description="The process engine for the Presentation Department. "
                    "Walks the manifest, refuses to skip a step, announces where it is.")
    m = p.add_mutually_exclusive_group(required=True)
    m.add_argument("--new", action="store_true", help="create a job in --run-dir from --intake")
    m.add_argument("--run", action="store_true", help="run the phase loop")
    m.add_argument("--resume", action="store_true", help="resume a parked job from checkpoint")
    m.add_argument("--status", action="store_true", help="print job status")
    m.add_argument("--close", action="store_true", help="evaluate gates and close")
    m.add_argument("--watchdog", action="store_true", help="scan for stalled jobs")
    p.add_argument("--run-dir", type=Path, help="the job's run directory")
    p.add_argument("--intake", type=Path, help="intake JSON for --new")
    p.add_argument("--manifest", help="explicit PIPELINE-MANIFEST.json path")
    p.add_argument("--phase", help="run exactly one phase")
    p.add_argument("--until", help="run through this phase then stop")
    p.add_argument("--scan-root", type=Path, help="root to scan for --watchdog")
    p.add_argument("--dry-run", action="store_true", help="print what would run, execute nothing")
    p.add_argument("--json", action="store_true", help="machine-readable --status")
    return p


def cmd_new(args, scripts_dir: Path) -> int:
    run_dir = args.run_dir.expanduser().resolve()
    store = StateStore(run_dir)
    if store.exists():
        die(EXIT_USAGE, f"{store.path} already exists — refusing to overwrite a live job")
    intake = _read_json(args.intake) if args.intake else None
    if args.intake and intake is None:
        die(EXIT_USAGE, f"cannot read intake JSON at {args.intake}")
    intake = intake or {}

    ptype = intake.get("presentation_type")
    legal = ("from_scratch", "content_personal", "content_general", "signature")
    if ptype not in legal:
        die(EXIT_USAGE,
            f"intake.presentation_type is {ptype!r}; must be one of {legal}.\n"
            "  This is the ONE question that derives both creation_mode and deck_type "
            "(deck-intake-driver.py:380-401). An unset value is AF-MODE-UNSET at preflight.")
    if ptype == "signature" and intake.get("signature_source") not in \
            ("from_scratch", "existing_content"):
        die(EXIT_USAGE,
            "presentation_type='signature' requires signature_source ∈ "
            "{from_scratch, existing_content} — it is the only thing that resolves creation_mode "
            "for a signature deck.")

    manifest_path = resolve_manifest(args.manifest, run_dir, scripts_dir)
    manifest = Manifest(manifest_path)
    manifest.verify_source()

    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "job_id": "pj_" + sha256_text(f"{run_dir}{utcnow()}")[:26],
        "run_dir": str(run_dir),
        "created_at": utcnow(),
        "manifest_path": str(manifest_path),
        "manifest_version": manifest.version,
        "manifest_sha256": manifest.sha256,
        "presentation_type": ptype,
        "requester": intake.get("requester") or {},
        "intake": intake,
        "current_phase": None,
        "phases": [],
        "gates": {},
        "waivers": [],
        "events": [],
        "sent": {},
        "undeliverable": [],
        "heartbeat": {},
        "terminal": None,
    }
    if not (state["requester"] or {}).get("chat_id"):
        die(EXIT_USAGE,
            "no requester.chat_id in intake. A presentations job with no requester cannot report "
            "progress or completion to anyone, and must not start (fix F1).")
    store.save(state)
    print(f"created {state['job_id']} in {run_dir}")
    print(f"  manifest v{manifest.version} ({len(manifest.phases)} phases) "
          f"pinned at {manifest.sha256[:12]}")
    return EXIT_OK


def cmd_status(args) -> int:
    store = StateStore(args.run_dir.expanduser().resolve())
    st = store.load()
    if args.json:
        print(json.dumps(st, indent=2))
        return EXIT_OK
    print(f"job      : {st['job_id']}")
    print(f"run dir  : {st['run_dir']}")
    print(f"manifest : v{st.get('manifest_version')} @ {str(st.get('manifest_sha256'))[:12]}")
    print(f"terminal : {st.get('terminal') or 'in progress'}")
    done = [p for p in st.get("phases", []) if p.get("status") == "done"]
    print(f"phases   : {len(done)} done")
    for p in st.get("phases", []):
        mark = {"done": "x", "running": ">", "blocked": "!", "pending": " "}.get(
            p.get("status", "pending"), "?")
        print(f"   [{mark}] {p['id']:<24} {p.get('status')}"
              + (f"  — {p.get('blocked_reason')}" if p.get("blocked_reason") else ""))
    for k, g in (st.get("gates") or {}).items():
        print(f"gate {k:<14} {g.get('state')}"
              + (f"  — {g.get('reason')}" if g.get("reason") else ""))
    if st.get("undeliverable"):
        print(f"UNDELIVERABLE messages: {len(st['undeliverable'])} "
              "(the requester was NOT told — see F2)")
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    scripts_dir = Path(__file__).resolve().parent

    if args.watchdog:
        root = (args.scan_root or args.run_dir)
        if not root:
            die(EXIT_USAGE, "--watchdog needs --scan-root")
        return watchdog(root.expanduser().resolve())

    if not args.run_dir:
        die(EXIT_USAGE, "--run-dir is required")
    run_dir = args.run_dir.expanduser().resolve()

    if args.new:
        return cmd_new(args, scripts_dir)
    if args.status:
        return cmd_status(args)

    with RunLock(run_dir):
        store = StateStore(run_dir)
        state = store.load()
        manifest_path = Path(state.get("manifest_path") or
                             resolve_manifest(args.manifest, run_dir, scripts_dir))
        if not manifest_path.is_file():
            die(EXIT_MANIFEST_MISMATCH, f"pinned manifest {manifest_path} is gone")
        manifest = Manifest(manifest_path)
        manifest.verify_pin(state.get("manifest_sha256", ""))

        engine = Engine(run_dir, manifest, store, state, dry_run=args.dry_run)
        if args.close:
            return engine.close()
        if args.resume:
            state["terminal"] = None
            state.pop("blocked", None)
            store.save(state)
            engine.report.event("job.resume", "resuming from checkpoint; banked artifacts reused")
        return engine.run(only=args.phase, until=args.until)


if __name__ == "__main__":
    sys.exit(main())
