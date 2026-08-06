from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .state import (
    StateStore, utcnow, sha256_file, EXIT_OK, EXIT_GATE_BLOCKED, EXIT_WAIVER_INVALID,
    ENTRY_COMMAND,
)
from .manifest import Manifest, Phase
from .report import Reporter
from .gates import Gates, ALL_GATE_KEYS, NON_WAIVABLE_GATES, WARN_ONLY_GATES
from .waivers import WaiverError, load_waivers, validate_waiver
from .artifacts import validate_artifact
from .heal import HEAL_CAP_TRANSIENT, HEAL_CAP_REGENERATE, HEAL_CAP_ALT_ROUTE, HEAL_CAP_REGATE, record_heal_event
from . import heal
from . import persona
# FIX-21 (D21): run_with_cleanup spawns the phase exec in a NEW PROCESS GROUP and, on
# budget expiry, kills the WHOLE group (SIGTERM -> SIGKILL) so a timed-out phase leaves
# no orphaned grandchildren (the D21 zombie path). Direct-child-only `subprocess.run`
# timeout is what let a `find` zombie run 18+ minutes beside the real build.
try:
    from process_reaper import run_with_cleanup
except ImportError:  # pragma: no cover — module ships beside presentation_job
    run_with_cleanup = None

# ---------------------------------------------------------------------------
# U069: named error for unparseable executor.cmd.
# ---------------------------------------------------------------------------
class PhaseExecutorContractError(RuntimeError):
    """U069: a phase's executor.cmd is not a parseable argument vector."""

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
        try:
            from . import workingset
            workingset.checkpoint_phase(self.run_dir, pid, self.state, self.store)
        except Exception:  # noqa: BLE001
            pass

    # -- verification -----------------------------------------------------
    def _artifacts_present(self, phase: Phase) -> Tuple[bool, List[str]]:
        missing = []
        for rel in phase.produces_artifact:
            matches = list(self.run_dir.glob(rel)) if any(c in rel for c in "*?[") \
                else ([self.run_dir / rel] if (self.run_dir / rel).exists() else [])
            if not matches:
                missing.append(rel)
        return (not missing), missing

    def _revalidate_banked(self, phase: Phase, ps: Dict[str, Any]) -> List[str]:
        """Return a list of human-readable reasons, empty when every banked artifact is still good."""
        bad = []
        shas = ps.get("sha256") or {}
        for rel in (ps.get("artifacts") or []):
            ok, why = validate_artifact(self.run_dir, rel, self.manifest,
                                        recorded_sha=shas.get(rel))
            if not ok:
                bad.append(f"{rel}: {why}")
        if not (ps.get("artifacts") or []) and phase.produces_artifact:
            bad.append("phase recorded status=done with an empty artifact list")
        return bad

    # -- executors --------------------------------------------------------
    def run_phase(self, phase: Phase) -> int:
        ps = self._phase_state(phase.id)
        if ps.get("status") == "done":
            bad = self._revalidate_banked(phase, ps)
            if not bad:
                print(f"SKIP {phase.id}: already done, {len(ps.get('artifacts', []))} artifact(s) "
                      f"re-validated (resuming reuses banked work)", flush=True)
                return EXIT_OK
            self.report.event(
                "phase.banked_invalid",
                f"{phase.id} was marked done but {len(bad)} banked artifact(s) no longer validate: "
                + "; ".join(bad) + " -- re-running this phase.")
            self._checkpoint(phase.id, status="pending", banked_invalid=bad)

        self.state["current_phase"] = phase.id
        self.state.setdefault("heartbeat", {})["phase_started_at"] = utcnow()
        self._checkpoint(phase.id, status="running", attempts=ps.get("attempts", 0) + 1)

        start_msg = (phase.client_report.get("start_template") or
                     f"Starting {phase.id} ({phase.owning_role})")
        self.report.to_requester("progress", start_msg)

        try:
            persona.resolve_for_phase(self.run_dir, phase.id)
        except (RuntimeError, TimeoutError) as exc:
            return self._block(phase, f"persona governance: {exc}")

        if phase.id == "P4-RENDER" and self.board:
            self.board.mark_in_progress()

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
                rc2 = heal.rung2_regenerate(self, phase, f"missing {', '.join(missing)}")
                if rc2 != EXIT_OK:
                    return self._block(phase, f"produced no artifact after "
                                              f"{heal.HEAL_CAP_REGENERATE} regeneration attempt(s): "
                                              f"missing {', '.join(missing)}")
                ok, missing = self._artifacts_present(phase)
                if not ok:
                    return self._block(phase, f"regeneration reported success but produced "
                                              f"nothing: missing {', '.join(missing)}")
            shas = {}
            for rel in phase.produces_artifact:
                for m in self.run_dir.glob(rel) if any(c in rel for c in "*?[") else [self.run_dir / rel]:
                    if m.is_file():
                        shas[str(m.relative_to(self.run_dir))] = sha256_file(m)
            # F4 (warn-mode): substance verifier runs after artifact presence, before done checkpoint.
            verifier_ok = None
            verifier_notes = None
            try:
                import phase_verifiers
                verifier_ok, verifier_notes = phase_verifiers.verify(phase.id, self.run_dir)
                if not verifier_ok:
                    self.report.event("phase.verifier_warn",
                                      f"{phase.id}: {'; '.join(verifier_notes)}")
            except ImportError:
                self.report.event("warn", f"{phase.id}: phase_verifiers not importable, "
                                          "substance check skipped")
            self._checkpoint(phase.id, status="done", attested_at=utcnow(), sha256=shas,
                             artifacts=sorted(shas.keys()),
                             verifier_ok=verifier_ok, verifier_notes=verifier_notes)
            done_msg = (phase.client_report.get("done_template") or f"{phase.id} complete")
            self.report.to_requester("progress", done_msg)
            if self.board:
                self.board.phase_progress(phase.id, done_msg)
        return rc

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
        return [run_dir_str if tok == "{run_dir}" else tok.replace("{run_dir}", run_dir_str)
                for tok in argv]

    def _run_script_phase(self, phase: Phase) -> int:
        # U069: tokenise FIRST, substitute SECOND -- via the single shared helper.
        argv = self._build_executor_argv(phase.executor_cmd, phase.id)
        if not argv:
            return self._block(phase, "executor kind is 'script' but no cmd is declared")
        if self.dry_run:
            print(f"DRY-RUN {phase.id}: {' '.join(argv)}", flush=True)
            return EXIT_OK

        ps = self._phase_state(phase.id)

        # Checkpoint BEFORE the expensive call (invariant 3), so a resume never re-burns it.
        self._checkpoint(phase.id, pending_cmd=' '.join(argv), pending_started_at=utcnow(),
                         pre_run_artifacts=sorted(
                             str(m.relative_to(self.run_dir))
                             for rel in phase.produces_artifact
                             for m in (self.run_dir.glob(rel) if any(c in rel for c in "*?[")
                                       else ([self.run_dir / rel] if (self.run_dir / rel).exists() else []))
                             if m.is_file()))
        budget = phase.budget_minutes * 60
        for attempt in range(1, heal.HEAL_CAP_TRANSIENT + 1):
            try:
                # FIX-21 (D21): process-group exec with cleanup — on budget expiry the
                # whole group dies, so a timed-out phase never leaves a stray orphan.
                # Falls back to the old direct-child subprocess.run only if the reaper
                # module is absent (it ships beside this package).
                if run_with_cleanup is not None:
                    r = run_with_cleanup(argv, cwd=str(self.run_dir),
                                         timeout=budget, capture=False)
                else:
                    r = subprocess.run(argv, shell=False, cwd=str(self.run_dir),
                                       timeout=budget, capture_output=False)
                if r.returncode == 0:
                    return EXIT_OK
                reason = f"exit {r.returncode}"
            except subprocess.TimeoutExpired:
                reason = f"exceeded its {phase.budget_minutes}-minute budget"
            except OSError as exc:
                reason = f"could not start: {exc}"

            record_heal_event(self.state, phase.id, self.store, ps, rung=1, attempt=attempt, reason=reason)
            # ANNOUNCE BEFORE RETRYING (invariant 6).
            self.report.to_requester(
                "blocked",
                f"{phase.id} failed ({reason}). Retrying — attempt {attempt} of "
                f"{heal.HEAL_CAP_TRANSIENT}. Nothing you need to do yet.",
                phase_id=phase.id, reason=reason)
            if attempt < heal.HEAL_CAP_TRANSIENT:
                time.sleep(min(60, 5 * (2 ** (attempt - 1))))

        # Rung 3: alternate route -- MECHANISM ONLY, NO CLIENT POLICY
        rc3 = heal.rung3_alt_route(self, phase)
        if rc3 == EXIT_OK:
            _r3 = 3
            heal.record_heal_event(self.state, phase.id, self.store, ps,
                                   rung=_r3, attempt=1, reason="alternate route")
            return EXIT_OK

        return self._block(phase, f"script executor failed after {heal.HEAL_CAP_TRANSIENT} attempts")

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
        checkpoint_every = max(60, phase.heartbeat_interval_minutes * 60 // 4)
        last_cp = time.time()
        started_at = time.time()
        while time.time() < deadline:
            ok, _ = self._artifacts_present(phase)
            if ok:
                return EXIT_OK
            now = time.time()
            remaining = deadline - now
            if not announced_half and remaining < (phase.budget_minutes * 60) / 2:
                announced_half = True
                self.report.to_requester(
                    "progress",
                    f"Still waiting on {phase.id} ({phase.owning_role}). "
                    f"About {int(remaining/60)} minutes before I flag it.")
            if now - last_cp >= checkpoint_every:
                last_cp = now
                self._checkpoint(phase.id, status="running",
                                 waiting_for=list(phase.produces_artifact),
                                 waited_seconds=int(now - started_at))
            time.sleep(15)
        return self._block(
            phase,
            f"agent-authored phase produced nothing within {phase.budget_minutes} minutes. "
            f"Expected: {', '.join(phase.produces_artifact)}")

    def _block(self, phase: Phase, reason: str) -> int:
        """Park resumable. Never die, never restart from scratch (decision #5)."""
        # Count banked artifacts BEFORE checkpointing, so the current
        # phase is still "done" when we look for done phases.
        banked, lost = [], []
        for ps_ in self.state.get("phases", []):
            if ps_.get("status") != "done":
                continue
            for a in (ps_.get("artifacts") or []):
                ok, _why = validate_artifact(self.run_dir, a, self.manifest,
                                             recorded_sha=(ps_.get("sha256") or {}).get(a))
                (banked if ok else lost).append(a)
        self._checkpoint(phase.id, status="blocked", blocked_reason=reason)
        self.state["terminal"] = "BLOCKED"
        self.state["blocked"] = {"phase": phase.id, "reason": reason, "at": utcnow()}
        self.store.save(self.state)
        if self.board:
            self.board.mark_blocked(phase.id, reason)
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

        if not self.state.get("sent", {}).get("ack"):
            n = len(phases)
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

        for p in phases:
            rc = self.run_phase(p)
            if rc != EXIT_OK:
                return rc

        if only:
            return EXIT_OK
        return self.close()

    def close(self) -> int:
        gates = Gates(self.run_dir, self.state).evaluate_all()
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

