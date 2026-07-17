#!/usr/bin/env python3
"""ghl_run_state.py — the shared PHASE-CHECKPOINT store + uniform RUN REPORT
emitter for every Skill-06 builder.

Covers SKILL-6-BROWSER-CONTROL-BULLETPROOF units:

  * **U8 — phase-granular resume.** Every builder persists a per-phase
    checkpoint keyed by ``run_id``. A run that is killed mid-walk (SIGKILL,
    lost box, expired token, browser crash) restarts at its LAST COMPLETED
    PHASE, not at phase 0. Before this module the only ``--resume`` in the whole
    skill was ``ghl_course_builder``'s per-lesson receipt skip; the survey and
    form builders had none, so a 40-minute build that died at the T&C slide
    started over from the folder.

  * **U10 — the honest cockpit.** Every builder emits an IDENTICALLY SHAPED
    ``RUN REPORT`` block at exit that prints, among other things, the EXACT
    resume command — a string you can paste into a shell and have it run.

DESIGN NOTES (read before changing anything here)

1. **The RUN REPORT goes to STDERR, never stdout.** Every Skill-6 builder
   prints ``json.dumps(result)`` to stdout as its machine-readable contract
   (the v2_dispatcher and the CC board hooks parse it). A human-shaped report
   on stdout would corrupt that JSON for every existing consumer. ``_log()`` in
   the builders is already stderr; the report joins it there.

2. **Not every phase is resumable, and pretending otherwise would be a gate
   that fails open.** A phase is declared with ``resumable=False`` when
   re-running it is either REQUIRED FOR CORRECTNESS or free:

     - **gates** (``preflight``) — a safety gate that is skipped on resume is
       not a gate. It re-runs, every time, on every resume.
     - **pure/deterministic THINK output** (``plan``, ``field_map``,
       ``dep_plan``, ``click_list``) — cheap, no side effects, and the
       in-memory objects are needed by the phases that follow.
     - **navigation / entry** (``p2a_create``, form ``F1``/``F2``) — you cannot
       skip walking back INTO the object you are resuming. These are idempotent
       (reuse-by-name / route straight to the captured id), so re-running them
       creates nothing new.

   Everything expensive and MUTATING (slides, fields, conditional logic,
   required toggles, capture slide, save) is ``resumable=True`` and is genuinely
   skipped on resume. ``phases_skipped`` in the RUN REPORT names exactly which.

3. **State is committed AFTER each phase, atomically** (write-temp → fsync →
   rename). A process killed at any instant therefore leaves a state file that
   is either "phase N done" or "phase N not done" — never a torn half-phase. A
   killed run's on-disk state is byte-identical to the state a clean
   ``--stop-after-phase N`` leaves behind, which is what makes resume trustworthy.

Self-test: ``python3 ghl_run_state.py --selftest`` (no network, no browser).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import sys
import time
from typing import Any, Callable, Dict, Iterable, List, Optional

RUN_STATE_VERSION = 1

# Terminal statuses a run can end in (the RUN REPORT's `status` row).
STATUS_OK = "OK"
STATUS_FAILED = "FAILED"
STATUS_STOPPED = "STOPPED"      # honest STOP-and-report (capture-pending selector, gate)
STATUS_RUNNING = "RUNNING"      # only ever seen in a state file whose process died

# Per-phase statuses inside the ledger.
PHASE_PENDING = "pending"
PHASE_RUNNING = "running"
PHASE_DONE = "done"
PHASE_FAILED = "failed"
PHASE_SKIPPED = "skipped"       # resumed: already done in an earlier attempt

# ── U28 (B-U14): D6 headless-guard refusal -> exit 75, not a generic exit-1 ──
# fail. ``ghl_builder.headless_guard`` / ``browser_manager.headless_guard`` both
# raise RuntimeError with this exact prefix (see 06-ghl-install-pages/tools/
# ghl_builder.py::headless_guard and browser_manager.py::headless_guard — the
# two independent implementations were kept string-identical on purpose so a
# single prefix check here covers both). The D6 CLI contract (ENV-MATRIX.md,
# ghl_builder.py's own `headless-guard` subcommand) promises "headed = forbidden
# (D6, exit 75)" — but every builder's main()/cli_run() previously caught this
# RuntimeError with the SAME generic `except Exception` that catches every other
# build failure and returned 1, silently breaking the exit-75 promise for the
# community/course/pipeline/form/survey live-build entry points (the U28
# headless-guard coverage audit's finding). Duplicating just the prefix string
# here (rather than importing browser_manager) keeps this module import-light,
# the same rationale browser_manager.py's own docstring gives for
# re-implementing headless_guard instead of importing ghl_builder.
D6_HEADLESS_REFUSAL_PREFIX = "REFUSE (D6 headless guard)"


def is_d6_headless_refusal(error_text: Optional[str]) -> bool:
    """True iff a builder's terminal error string IS the D6 headless-guard
    refusal (AGENT_BROWSER_HEADED would open a visible window). Callers use
    this to map the exit code to 75 (the D6 CLI contract) instead of the
    generic 1 an ordinary build failure gets."""
    return D6_HEADLESS_REFUSAL_PREFIX in (error_text or "")


class RunStateNotFound(FileNotFoundError):
    """``--resume <run_id>`` named a run with no state file under the state root."""


class RunStateCorrupt(ValueError):
    """The state file exists but is not a readable v1 run-state document."""


def default_state_root() -> str:
    """Where run state lives. Env-overridable so a box, a test, and a CI job can
    each point at their own store without touching argv.

    Deliberately NOT under ``evidence_root``: ``--resume <run_id>`` must be able
    to find a run knowing ONLY the run id, and the evidence root is itself one of
    the things the state file restores.
    """
    env = os.environ.get("GHL_RUN_STATE_ROOT", "").strip()
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".openclaw", "skill6-runs")


def new_run_id(builder: str = "") -> str:
    """A sortable, collision-resistant run id: ``<utc>-<6 hex>``.

    Time-prefixed so ``ls`` sorts chronologically; random-suffixed so two runs
    started in the same second on the same box never collide.
    """
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{stamp}-{secrets.token_hex(3)}"


class PhaseSpec:
    """One declared phase of a builder's walk.

    ``resumable=False`` means: ALWAYS re-execute on resume (a gate, a pure THINK
    step, or a navigation/entry step). See design note 2 in the module docstring
    — this is the difference between a resume that is honest and a resume that
    silently skips a safety check.
    """

    __slots__ = ("name", "title", "resumable")

    def __init__(self, name: str, title: str = "", resumable: bool = True) -> None:
        self.name = name
        self.title = title or name
        self.resumable = resumable

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"PhaseSpec({self.name!r}, resumable={self.resumable})"


def phase_names(specs: Iterable[PhaseSpec]) -> List[str]:
    return [p.name for p in specs]


class RunState:
    """The per-run phase ledger. One JSON file per run id.

    The file is the ONLY source of truth for what a previous attempt completed —
    an in-memory claim that a phase ran is worth nothing to a process that has
    already been killed.
    """

    def __init__(
        self,
        run_id: str,
        builder: str,
        *,
        state_root: str = "",
        evidence_root: str = "",
        argv: Optional[List[str]] = None,
        specs: Optional[List[PhaseSpec]] = None,
        doc: Optional[dict] = None,
    ) -> None:
        self.run_id = run_id
        self.builder = builder
        self.state_root = state_root or default_state_root()
        self.specs: List[PhaseSpec] = list(specs or [])
        self._spec_by_name = {p.name: p for p in self.specs}
        # Phases this PROCESS executed (vs. inherited from an earlier attempt).
        # The RUN REPORT's `phases_skipped` row is the difference between the two,
        # and it can only be told from process-local memory — the on-disk ledger
        # cannot distinguish "done just now" from "done an hour ago".
        self._touched: set = set()
        self._skipped: set = set()
        if doc is not None:
            self.doc = doc
        else:
            self.doc = {
                "run_state_version": RUN_STATE_VERSION,
                "run_id": run_id,
                "builder": builder,
                "evidence_root": evidence_root,
                "argv": list(argv or []),
                "status": STATUS_RUNNING,
                "started_at": _ts(),
                "updated_at": _ts(),
                "attempts": 1,
                "phase_order": phase_names(self.specs),
                "phases": {},
                "carry": {},          # cross-phase values a resume must restore (survey_id…)
            }
        # Keep the declared order authoritative for THIS process even when the
        # stored doc came from an older attempt with a different phase list.
        if self.specs:
            self.doc["phase_order"] = phase_names(self.specs)

    # ── paths / io ──────────────────────────────────────────────────────────
    @property
    def path(self) -> str:
        safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in self.run_id)[:80]
        return os.path.join(self.state_root, f"{safe}.json")

    @property
    def evidence_root(self) -> str:
        return self.doc.get("evidence_root", "")

    @property
    def argv(self) -> List[str]:
        return list(self.doc.get("argv", []))

    def save(self) -> str:
        """Atomic commit: temp → fsync → rename. A kill mid-save can never leave a
        torn state file, which is the whole premise of trusting it on resume."""
        self.doc["updated_at"] = _ts()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.tmp-{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.doc, fh, indent=2, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)
        return self.path

    # ── construction ────────────────────────────────────────────────────────
    @classmethod
    def start(
        cls,
        builder: str,
        specs: List[PhaseSpec],
        *,
        run_id: str = "",
        state_root: str = "",
        evidence_root: str = "",
        argv: Optional[List[str]] = None,
    ) -> "RunState":
        st = cls(
            run_id or new_run_id(builder), builder,
            state_root=state_root, evidence_root=evidence_root,
            argv=argv, specs=specs,
        )
        st.save()
        return st

    @classmethod
    def load(
        cls,
        run_id: str,
        builder: str = "",
        *,
        state_root: str = "",
        specs: Optional[List[PhaseSpec]] = None,
    ) -> "RunState":
        root = state_root or default_state_root()
        probe = cls(run_id, builder, state_root=root, specs=specs)
        if not os.path.isfile(probe.path):
            raise RunStateNotFound(
                f"no run state for run_id {run_id!r} under {root!r} — "
                f"nothing to resume (looked for {probe.path})"
            )
        try:
            with open(probe.path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            raise RunStateCorrupt(f"{probe.path}: {type(exc).__name__}: {exc}") from exc
        if not isinstance(doc, dict) or "phases" not in doc:
            raise RunStateCorrupt(f"{probe.path}: not a run-state document")
        st = cls(
            run_id, builder or doc.get("builder", ""),
            state_root=root, specs=specs, doc=doc,
        )
        if builder and doc.get("builder") and doc["builder"] != builder:
            raise RunStateCorrupt(
                f"run {run_id!r} belongs to builder {doc['builder']!r}, "
                f"not {builder!r} — refusing to resume it with the wrong builder"
            )
        st.doc["attempts"] = int(doc.get("attempts", 1)) + 1
        st.doc["status"] = STATUS_RUNNING
        st.save()
        return st

    # ── phase ledger ────────────────────────────────────────────────────────
    def is_done(self, phase: str) -> bool:
        return self.doc["phases"].get(phase, {}).get("status") == PHASE_DONE

    def should_skip(self, phase: str) -> bool:
        """True only when the phase is BOTH already done AND declared resumable.
        A non-resumable phase (gate / pure THINK / navigation) always re-runs."""
        spec = self._spec_by_name.get(phase)
        if spec is not None and not spec.resumable:
            return False
        return self.is_done(phase)

    def mark_running(self, phase: str) -> None:
        self.doc["phases"][phase] = {"status": PHASE_RUNNING, "started_at": _ts()}
        self.doc["last_phase"] = phase
        self._touched.add(phase)
        self.save()

    def mark_skipped(self, phase: str) -> None:
        """Record (process-locally) that a resume SKIPPED this phase. The on-disk
        entry stays ``done`` — it IS done; only this attempt did not redo it."""
        self._skipped.add(phase)

    def mark_done(self, phase: str, data: Any = None) -> None:
        rec = self.doc["phases"].get(phase, {})
        rec.update({"status": PHASE_DONE, "done_at": _ts()})
        if data is not None:
            rec["data"] = _jsonable(data)
        self.doc["phases"][phase] = rec
        self.doc["last_phase"] = phase
        self.save()

    def mark_failed(self, phase: str, error: str) -> None:
        rec = self.doc["phases"].get(phase, {})
        rec.update({"status": PHASE_FAILED, "failed_at": _ts(), "error": str(error)[:800]})
        self.doc["phases"][phase] = rec
        self.doc["last_phase"] = phase
        self.doc["status"] = STATUS_FAILED
        self.save()

    def phase_data(self, phase: str) -> Any:
        return self.doc["phases"].get(phase, {}).get("data")

    def completed_phases(self) -> List[str]:
        """Completed phases, in the DECLARED order (never dict insertion order —
        a resumed run's insertion order interleaves attempts and would lie)."""
        order = self.doc.get("phase_order") or list(self.doc["phases"])
        return [p for p in order if self.is_done(p)]

    def last_completed_phase(self) -> str:
        done = self.completed_phases()
        return done[-1] if done else ""

    def skippable_completed(self) -> List[str]:
        return [p for p in self.completed_phases() if self.should_skip(p)]

    def resume_phase(self) -> str:
        """The phase a ``--resume`` will restart the MUTATING walk at: the first
        declared phase that is not both done and resumable. '' when the run has
        no work left."""
        for spec in self.specs:
            if not self.should_skip(spec.name):
                if spec.resumable or not self.is_done(spec.name):
                    return spec.name
        return ""

    def first_incomplete_mutating_phase(self) -> str:
        """The first RESUMABLE phase that is not done — i.e. the first real piece
        of work a resume will actually redo. This is the number the acceptance
        test means by 'restarts at phase N'."""
        for spec in self.specs:
            if spec.resumable and not self.is_done(spec.name):
                return spec.name
        return ""

    # ── cross-phase carry (survey_id, form_id, urls…) ────────────────────────
    def carry_set(self, key: str, value: Any) -> None:
        self.doc.setdefault("carry", {})[key] = _jsonable(value)
        self.save()

    def carry_get(self, key: str, default: Any = None) -> Any:
        return self.doc.get("carry", {}).get(key, default)

    # ── terminal status ─────────────────────────────────────────────────────
    def finish(self, status: str, error: str = "") -> None:
        self.doc["status"] = status
        self.doc["finished_at"] = _ts()
        if error:
            self.doc["error"] = str(error)[:800]
        self.save()


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _jsonable(v: Any) -> Any:
    """Keep the ledger a plain JSON document — a phase that hands back a browser
    handle or a subprocess must not poison the state file."""
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return str(v)


# ---------------------------------------------------------------------------
# The phase runner — the ONE code path every builder's walk goes through
# ---------------------------------------------------------------------------
def run_phase(
    state: Optional[RunState],
    phase: str,
    fn: Callable[[], Any],
    *,
    log: Optional[Callable[[str], None]] = None,
    carry: str = "",
) -> Any:
    """Execute (or resume-skip) ONE checkpointed phase.

    * ``state is None`` → no checkpointing at all (library callers / dispatcher).
    * already done + resumable → SKIP, returning the value the earlier attempt
      recorded (so ``survey_id`` etc. survive across a kill).
    * otherwise → run it, then COMMIT the phase to disk before returning.

    A raised exception is recorded as a phase failure and re-raised — the ledger
    must show where the run actually died, and a swallowed error would be exactly
    the "gate that fails open" the QC bar forbids.
    """
    if state is None:
        return fn()

    if state.should_skip(phase):
        if log:
            log(f"PHASE {phase}: SKIP — already completed in run {state.run_id}")
        state.mark_skipped(phase)
        data = state.phase_data(phase)
        if carry and data is None:
            data = state.carry_get(carry)
        return data

    if log:
        log(f"PHASE {phase}: RUN")
    state.mark_running(phase)
    try:
        result = fn()
    except BaseException as exc:  # noqa: BLE001 - includes KeyboardInterrupt: the ledger must record a kill
        state.mark_failed(phase, f"{type(exc).__name__}: {exc}")
        raise
    state.mark_done(phase, result)
    if carry and result is not None:
        state.carry_set(carry, result)
    return result


# ---------------------------------------------------------------------------
# U106 — smoke_first(): the shared one-proof-create-before-a-bulk-run gate.
#
# The community/course builders each drive a potentially LONG bulk walk after
# a single object is created — community: create ONE group, then add N
# channels; course: create ONE course, then add N modules/lessons. Nothing
# proved the FIRST bulk item actually landed before the walk committed to the
# rest of a long (and, on a live account, expensive) run. This is the shared
# gate: run ONE proof-create, verify it with a STORE-DELTA assertion (never a
# CLI "✓ Done" — that is a FALSE PASS if it created nothing; the snapshot/
# store delta is the only honest arbiter), and ONLY on a PASS let the caller
# proceed into the rest of the bulk walk. A FAILING smoke raises
# ``SmokeFirstFailed`` before a single additional bulk item is attempted.
#
# Generalized here (U106) for the community/course/channel builders; the same
# shape (create_fn + verify_fn, no I/O of its own) is what U30 lifts from the
# survey builder for the iframe/page-code drag surfaces — whichever unit lands
# first, the other's call sites are meant to converge on this ONE helper
# rather than each builder growing its own ad hoc "create the first one, then
# loop" gate.
# ---------------------------------------------------------------------------
class SmokeFirstFailed(RuntimeError):
    """Raised when the ONE proof-create step's store-delta verification fails.
    The caller MUST NOT enter the bulk run — carries the create_fn() result and
    the verify_fn() verdict for diagnostics (never swallowed, never retried
    silently)."""

    def __init__(self, step: str, reason: str, *, result: Any = None, verdict: Any = None):
        self.step = step
        self.reason = reason
        self.result = result
        self.verdict = verdict
        super().__init__(f"SMOKE-FIRST FAILED @ {step}: {reason} — STOP before the bulk run.")

    def to_dict(self) -> Dict[str, Any]:
        return {"step": self.step, "reason": self.reason,
                "result": _jsonable(self.result), "verdict": _jsonable(self.verdict)}


def smoke_first(
    step: str,
    create_fn: Callable[[], Any],
    verify_fn: Callable[[Any], Any],
    *,
    log: Optional[Callable[[str], None]] = None,
) -> Any:
    """Run ONE proof-create, then gate the caller's bulk run on its verify.

    ``create_fn()`` performs the single real proof-create (e.g. add the FIRST
    channel / FIRST lesson) and returns whatever the caller needs to keep (a
    receipt, an identity dict, ...). ``verify_fn(result)`` performs the
    STORE-DELTA assertion — return a plain bool, or a dict carrying at least
    ``{"ok": bool}`` for a richer verdict recorded in the failure. This
    function does no browser/network I/O of its own: both callables are
    caller-injected, exactly like every other Skill-6 dependency-injected
    helper (``ghl_selector_drift_probe``'s ``finder``/``page_fetcher`` — module
    renamed from ``ghl_selector_canary`` by U30/B-U16).

    On a PASS, returns ``create_fn()``'s result unchanged so the caller can
    fold the smoke step's own object straight into its results/receipts.
    On a FAIL, raises ``SmokeFirstFailed`` — the caller's bulk loop (every
    item after the smoke) must never be reached; this function itself never
    loops or retries, it runs the ONE proof exactly once.
    """
    result = create_fn()
    verdict = verify_fn(result)
    ok = bool(verdict.get("ok")) if isinstance(verdict, dict) else bool(verdict)
    if log:
        log(f"smoke_first[{step}]: {'PASS' if ok else 'FAIL'}")
    if not ok:
        raise SmokeFirstFailed(
            step, "store-delta assertion failed on the proof-create — bulk run aborted",
            result=result, verdict=verdict)
    return result


# ---------------------------------------------------------------------------
# U10 — the uniform RUN REPORT
# ---------------------------------------------------------------------------
RUN_REPORT_WIDTH = 78


def resume_command(
    script_path: str,
    run_id: str,
    *,
    state_root: str = "",
    python: str = "python3",
    extra: Optional[List[str]] = None,
) -> str:
    """The EXACT, paste-able resume command.

    Absolute script path (a relative one only runs from one directory), and
    ``--state-root`` is emitted ONLY when it differs from the default — printing
    a flag whose value is already the default is noise, but omitting a
    NON-default one would print a command that cannot find the run.

    Everything else a resume needs (evidence root, dry-run posture, task args) is
    restored from the state file, which is why ``--resume <run_id>`` is sufficient
    on its own.
    """
    parts = [python, os.path.abspath(script_path), "--resume", run_id]
    if state_root and os.path.abspath(state_root) != os.path.abspath(default_state_root()):
        parts += ["--state-root", state_root]
    parts += list(extra or [])
    return " ".join(shlex.quote(p) for p in parts)


def format_run_report(
    *,
    builder: str,
    run_id: str,
    status: str,
    dry_run: bool,
    evidence_root: str,
    duration_s: float,
    script_path: str,
    state: Optional[RunState] = None,
    state_root: str = "",
    error: str = "",
    extra_rows: Optional[Dict[str, Any]] = None,
    resume_cmd: Optional[str] = None,
) -> str:
    """The identically-shaped RUN REPORT block emitted by EVERY Skill-6 builder.

    Same rows, same order, same widths, whichever builder you ran — that
    sameness is the point of U10: an operator reads one shape, not six.
    """
    rows: List[tuple] = [
        ("builder", builder),
        ("run_id", run_id or "(none)"),
        ("status", status),
        ("dry_run", "true" if dry_run else "false"),
        ("evidence_root", evidence_root or "(none)"),
        ("duration_s", f"{duration_s:.1f}"),
    ]

    if state is not None:
        order = phase_names(state.specs) or state.doc.get("phase_order", [])
        done = state.completed_phases()
        skipped = [p for p in order if p in state._skipped]
        rows += [
            ("phases_done", f"{len(done)}/{len(order)}" if order else str(len(done))),
            ("last_phase", state.doc.get("last_phase", "") or "(none)"),
        ]
        if int(state.doc.get("attempts", 1)) > 1:
            rows.append(("resumed_from", state.doc.get("resumed_from", "") or "(start)"))
            rows.append(("phases_skipped", ", ".join(skipped) if skipped else "(none)"))
        nxt = state.first_incomplete_mutating_phase()
        if nxt:
            rows.append(("next_phase", nxt))

    for k, v in (extra_rows or {}).items():
        rows.append((k, v))

    if error:
        rows.append(("error", str(error)[:200]))

    cmd = resume_cmd
    if cmd is None:
        cmd = (
            resume_command(script_path, run_id, state_root=state_root)
            if run_id else "(no run_id — nothing to resume)"
        )
    rows.append(("resume", cmd))

    title = " RUN REPORT "
    bar = title.center(RUN_REPORT_WIDTH, "=")
    lines = [bar]
    keyw = max(len(k) for k, _ in rows)
    for k, v in rows:
        lines.append(f"{k.ljust(keyw)} : {v}")
    lines.append("=" * RUN_REPORT_WIDTH)
    return "\n".join(lines)


def emit_run_report(stream=None, **kwargs: Any) -> str:
    """Print the RUN REPORT to **stderr** (design note 1: stdout is the builders'
    machine-readable JSON contract and must stay parseable). Returns the block."""
    block = format_run_report(**kwargs)
    print(block, file=stream or sys.stderr, flush=True)
    return block


# ---------------------------------------------------------------------------
# Uniform CLI surface — every builder gets the SAME flags, spelled the same way
# ---------------------------------------------------------------------------
def add_run_state_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """``--resume RUN_ID`` / ``--run-id RUN_ID`` / ``--state-root DIR`` /
    ``--stop-after-phase NAME``, identical on every builder."""
    parser.add_argument(
        "--resume", metavar="RUN_ID", default="",
        help=("Resume a previous run by its run id: re-runs the gates and the "
              "navigation/entry phases, SKIPS every mutating phase that run already "
              "completed, and continues from the first one it did not. The evidence "
              "root and task args are restored from the run's state file."),
    )
    parser.add_argument(
        "--run-id", metavar="RUN_ID", default="",
        help="Force this run's id (default: generated). Use it to pre-name a run you intend to resume.",
    )
    parser.add_argument(
        "--state-root", metavar="DIR", default=default_state_root(),
        help=f"Where per-run phase state is stored (default: {default_state_root()}; "
             "env GHL_RUN_STATE_ROOT overrides).",
    )
    parser.add_argument(
        "--stop-after-phase", metavar="PHASE", default="",
        help="Stop cleanly AFTER this phase completes (state is committed; resume with --resume). "
             "Operator control for a staged / inspectable build.",
    )
    return parser


class StopAfterPhase(RuntimeError):
    """Raised by the walk when ``--stop-after-phase`` fires. Not a failure — the
    run stopped exactly where the operator asked, with state committed."""

    def __init__(self, phase: str) -> None:
        super().__init__(f"stopped after phase {phase!r} as requested (--stop-after-phase)")
        self.phase = phase


def open_run_state(
    args: argparse.Namespace,
    builder: str,
    specs: List[PhaseSpec],
    *,
    argv: Optional[List[str]] = None,
) -> RunState:
    """Resolve ``--resume`` / ``--run-id`` into a live RunState (the same three
    lines in every builder's main, so the semantics cannot drift between them)."""
    state_root = getattr(args, "state_root", "") or default_state_root()
    resume_id = getattr(args, "resume", "") or ""
    if resume_id:
        st = RunState.load(resume_id, builder, state_root=state_root, specs=specs)
        st.doc["resumed_from"] = st.first_incomplete_mutating_phase() or "(complete)"
        st.save()
        return st
    return RunState.start(
        builder, specs,
        run_id=getattr(args, "run_id", "") or "",
        state_root=state_root,
        evidence_root=getattr(args, "evidence_root", "") or "",
        argv=list(argv if argv is not None else sys.argv[1:]),
    )


def cli_run(
    args: argparse.Namespace,
    *,
    builder: str,
    specs: List[PhaseSpec],
    script_path: str,
    task: dict,
    build: Callable[..., dict],
    ok_key: str = "location_gate_ok",
    url_key: str = "",
    argv: Optional[List[str]] = None,
) -> int:
    """The ONE main()-body every Skill-6 builder shares: open/restore the run
    ledger → build → commit the terminal status → print the JSON result on stdout
    → print the RUN REPORT on stderr → return the exit code.

    Having one implementation is what makes the RUN REPORT *identically shaped*
    across builders (U10) rather than six lookalikes that drift apart.
    """
    started = time.monotonic()

    try:
        state = open_run_state(args, builder, specs, argv=argv)
    except (RunStateNotFound, RunStateCorrupt) as exc:
        print(f"--resume: {exc}", file=sys.stderr)
        return 2

    resumed = bool(getattr(args, "resume", ""))
    evidence_root = getattr(args, "evidence_root", "") or ""
    if resumed and state.evidence_root:
        evidence_root = state.evidence_root

    dry_run = bool(getattr(args, "dry_run", True))
    if resumed:
        # A resume rebuilds the SAME object the dead run was building — not a fresh
        # one shaped by whatever flags happen to be on this command line.
        saved_task = state.carry_get("task")
        if isinstance(saved_task, dict):
            task = dict(saved_task)
        saved_dry = state.carry_get("dry_run")
        if saved_dry is not None:
            dry_run = bool(saved_dry)
    else:
        state.carry_set("task", task)
        state.carry_set("dry_run", dry_run)

    task["stop_after_phase"] = getattr(args, "stop_after_phase", "") or ""

    status = STATUS_OK
    error = ""
    result: dict = {}
    try:
        result = build(task, evidence_root, dry_run=dry_run, state=state)
    except StopAfterPhase as sap:
        status = STATUS_STOPPED
        result = {"stopped_after_phase": sap.phase, "run_id": state.run_id}
    except Exception as exc:  # noqa: BLE001
        status = STATUS_FAILED
        error = f"{type(exc).__name__}: {exc}"
        result = {"error": error}

    if status == STATUS_OK:
        if result.get("stopped_after_phase"):
            status = STATUS_STOPPED
        elif result.get("error"):
            status = STATUS_FAILED
            error = str(result["error"])
    state.finish(status, error)

    print(json.dumps(result, indent=2, default=str))

    extra = {}
    if url_key:
        extra[url_key] = result.get(url_key) or "(none)"
    emit_run_report(
        builder=builder, run_id=state.run_id, status=status, dry_run=dry_run,
        evidence_root=evidence_root, duration_s=time.monotonic() - started,
        script_path=script_path, state=state,
        state_root=getattr(args, "state_root", ""), error=error, extra_rows=extra,
    )

    if status == STATUS_FAILED:
        # U28 (B-U14): a D6 headless-guard refusal is NOT a generic build
        # failure — it must keep the promised exit 75 (ENV-MATRIX.md, the
        # ghl_builder.py `headless-guard` subcommand), whether it propagated
        # here as a raised RuntimeError (caught above, folded into `error`) or
        # was captured into `result["error"]` by the builder itself.
        if is_d6_headless_refusal(error):
            return 75
        return 1
    return 0 if result.get(ok_key, True) else 1


# ---------------------------------------------------------------------------
# Self-test — no network, no browser, no builder imports
# ---------------------------------------------------------------------------
def _selftest() -> int:  # pragma: no cover - exercised by tests/ too
    import tempfile

    errors: List[str] = []
    specs = [
        PhaseSpec("preflight", resumable=False),
        PhaseSpec("plan", resumable=False),
        PhaseSpec("build_a"),
        PhaseSpec("build_b"),
        PhaseSpec("build_c"),
    ]

    with tempfile.TemporaryDirectory() as root:
        ran: List[str] = []

        st = RunState.start("demo", specs, state_root=root, evidence_root="/tmp/x")
        for p in ("preflight", "plan", "build_a", "build_b"):
            run_phase(st, p, lambda p=p: (ran.append(p), f"{p}-out")[1])

        if st.last_completed_phase() != "build_b":
            errors.append(f"last_completed_phase = {st.last_completed_phase()!r}, want 'build_b'")
        if st.first_incomplete_mutating_phase() != "build_c":
            errors.append("first_incomplete_mutating_phase should be build_c")

        # Resume: the gates + THINK re-run, the done mutating phases are SKIPPED.
        ran.clear()
        st2 = RunState.load(st.run_id, "demo", state_root=root, specs=specs)
        for p in ("preflight", "plan", "build_a", "build_b", "build_c"):
            run_phase(st2, p, lambda p=p: (ran.append(p), f"{p}-out")[1])

        if ran != ["preflight", "plan", "build_c"]:
            errors.append(f"resume re-ran {ran} — want ['preflight','plan','build_c']")
        if st2.phase_data("build_a") != "build_a-out":
            errors.append("skipped phase did not return its recorded data")

        # Wrong builder must be refused, not silently resumed.
        try:
            RunState.load(st.run_id, "other_builder", state_root=root, specs=specs)
            errors.append("resuming with the WRONG builder was allowed")
        except RunStateCorrupt:
            pass

        # Unknown run id must fail loudly.
        try:
            RunState.load("nope", "demo", state_root=root, specs=specs)
            errors.append("unknown run_id did not raise")
        except RunStateNotFound:
            pass

        # A failing phase records the failure and re-raises.
        st3 = RunState.start("demo", specs, state_root=root)
        try:
            run_phase(st3, "build_a", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
            errors.append("a raising phase did not propagate")
        except RuntimeError:
            pass
        if st3.doc["phases"]["build_a"]["status"] != PHASE_FAILED:
            errors.append("a raising phase was not recorded as failed")

        block = format_run_report(
            builder="demo", run_id=st2.run_id, status=STATUS_OK, dry_run=True,
            evidence_root="/tmp/x", duration_s=1.0, script_path=__file__,
            state=st2, state_root=root,
        )
        if "RUN REPORT" not in block or "resume" not in block:
            errors.append("RUN REPORT block missing its header / resume row")
        if st2.run_id not in block:
            errors.append("RUN REPORT does not print the run id in the resume command")

    # U106 — smoke_first(): PASS returns the create_fn() result unchanged.
    calls: List[str] = []
    result = smoke_first(
        "demo:smoke", lambda: (calls.append("create"), "created-thing")[1],
        lambda r: {"ok": r == "created-thing"})
    if result != "created-thing" or calls != ["create"]:
        errors.append(f"smoke_first PASS path wrong: result={result!r} calls={calls!r}")

    # U106 — smoke_first(): FAIL raises SmokeFirstFailed BEFORE any bulk item,
    # and the exception carries the create result + verdict for diagnostics.
    try:
        smoke_first("demo:smoke-fail", lambda: "half-made", lambda r: False)
        errors.append("smoke_first with a failing verify_fn did not raise")
    except SmokeFirstFailed as sf:
        if sf.step != "demo:smoke-fail" or sf.result != "half-made":
            errors.append(f"SmokeFirstFailed carried wrong step/result: {sf.to_dict()}")

    # U106 — smoke_first(): a dict verdict with ok=False also fails, and its
    # richer verdict is preserved on the exception (not just a bare bool).
    try:
        smoke_first("demo:smoke-dict", lambda: "x",
                    lambda r: {"ok": False, "present_in_nav": False})
        errors.append("smoke_first with a dict verdict ok=False did not raise")
    except SmokeFirstFailed as sf:
        if sf.verdict.get("present_in_nav") is not False:
            errors.append(f"SmokeFirstFailed dropped the rich verdict: {sf.to_dict()}")

    for e in errors:
        print(f"FAIL: {e}", file=sys.stderr)
    print(f"ghl_run_state selftest: {'PASS' if not errors else 'FAIL'} "
          f"({len(errors)} error(s))", file=sys.stderr)
    return 1 if errors else 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_run_state",
        description="Skill-6 shared phase-checkpoint store + uniform RUN REPORT emitter.",
    )
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--list", action="store_true", help="List known runs under the state root.")
    p.add_argument("--show", metavar="RUN_ID", default="", help="Print one run's phase ledger.")
    p.add_argument("--state-root", default=default_state_root())
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.show:
        st = RunState.load(args.show, state_root=args.state_root)
        print(json.dumps(st.doc, indent=2, default=str))
        return 0
    if args.list:
        root = args.state_root
        if not os.path.isdir(root):
            print(f"(no runs — {root} does not exist)")
            return 0
        for fn in sorted(os.listdir(root)):
            if fn.endswith(".json"):
                print(fn[:-5])
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
