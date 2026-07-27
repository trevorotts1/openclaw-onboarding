from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .state import (
    StateStore, utcnow, sha256_file, EXIT_OK, EXIT_GATE_BLOCKED,
)
from .manifest import Manifest, Phase
from .report import Reporter
from .gates import Gates, ALL_GATE_KEYS, NON_WAIVABLE_GATES
from .waivers import WaiverError, load_waivers, validate_waiver
from . import heal

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

            heal.record_heal_event(self.state, phase.id, self.store, ps, rung=1, attempt=attempt, reason=reason)
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

    def _block(self, phase: Phase, reason: str) -> int:
        """Park resumable. Never die, never restart from scratch (decision #5)."""
        self._checkpoint(phase.id, status="blocked", blocked_reason=reason)
        self.state["terminal"] = "BLOCKED"
        self.state["blocked"] = {"phase": phase.id, "reason": reason, "at": utcnow()}
        banked = [a for ps in self.state.get("phases", []) if ps.get("status") == "done"
                  for a in ps.get("artifacts", [])]
        self.store.save(self.state)
        if self.board:
            self.board.mark_blocked(phase.id, reason)
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

        if self.board:
            self.board.mark_review()
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

