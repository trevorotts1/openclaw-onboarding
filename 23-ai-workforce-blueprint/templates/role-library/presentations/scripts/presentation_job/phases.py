from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from .artifacts import validate_artifact
from .heal import HEAL_CAP_TRANSIENT, HEAL_CAP_REGENERATE, HEAL_CAP_ALT_ROUTE, HEAL_CAP_REGATE, record_heal_event
from . import heal
from . import persona
from . import curate as _curate
# FIX-21 (D21): run_with_cleanup spawns the phase exec in a NEW PROCESS GROUP and, on
# budget expiry, kills the WHOLE group (SIGTERM -> SIGKILL) so a timed-out phase leaves
# no orphaned grandchildren (the D21 zombie path). Direct-child-only `subprocess.run`
# timeout is what let a `find` zombie run 18+ minutes beside the real build.
try:
    from process_reaper import run_with_cleanup
except ImportError:  # pragma: no cover — module ships beside presentation_job
    run_with_cleanup = None


def _wave_execution_enabled() -> bool:
    """FIX 1: default ON. The only value that disables is exactly "0" (also
    strip quotes/whitespace so `PRESENTATION_WAVE_EXECUTION=""` counts as
    unset, not OFF — an EMPTY value must never silently select the rollback
    path). =0 restores the exact pre-fix serial engine loop."""
    raw = os.environ.get("PRESENTATION_WAVE_EXECUTION")
    if raw is None:
        return True
    return raw.strip().strip("'\"") != "0"


# FIX 1 (Phase A stub capacity probe): fixed deepseek-direct profile with
# measured capacity 8, mirroring dispatcher._prompt_routing_stamp() and
# /Users/blackceomacmini/presentation-fix-tests/phase-a-routing.json.
# FIX 7/8/11 will replace this with real resource profiles through the same
# dict schema (status/provider/plan/available); until then the engine stamps
# these constants so the plan is built from a measured width, never an
# unmeasured one (CapacityUnmeasured must stay loud, not papered over).
_PHASE_A_CAPACITY_PROBE = {
    "status": "MEASURED",
    "provider": "deepseek-direct",
    "plan": "phase-a-stub",
    "available": 8,
    "dispatchable": 8,
    "probe_mode": "stub",
    "model": "deepseek-v4-flash",
}

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
            ps = {"id": pid, "status": "pending", "artifacts": [], "sha256": {},
                  "attempts": 0, "heal_events": [], "attested_at": None}
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
            try:
                from . import workingset
                workingset.checkpoint_phase(self.run_dir, pid, self.state, self.store)
            except Exception:  # noqa: BLE001
                pass

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
        self._checkpoint(phase.id, status="done", attested_at=utcnow(),
                         artifacts=[], sha256={}, verifier_ok=None,
                         verifier_notes=[f"NOTE: {reason}"],
                         owner_skip_approval=None, routed_around=True,
                         routed_around_reason=reason)

    # -- verification -----------------------------------------------------
    def _artifacts_present(self, phase: Phase) -> Tuple[bool, List[str]]:
        missing = []
        # U01-R2 (QC FAIL 6.46): the phase's raw produces_artifact may carry
        # {deck_slug}/{run_dir} tokens (P8.25-WORKBOOK declares
        # 'working/deliverables/{deck_slug}-WORKBOOK.pdf + {deck_slug}-WORKBOOK-FILLABLE.pdf').
        # Resolve EVERY pattern through phase.resolve_artifact_patterns(run_dir) BEFORE
        # globbing/existence checks -- the literal token path never exists on disk and
        # previously hard-blocked the phase despite real workbook PDFs being present.
        for rel in phase.resolve_artifact_patterns(self.run_dir):
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
        """
        try:
            tdir = self._telemetry_dir()
            tdir.mkdir(parents=True, exist_ok=True)
            with (tdir / "stage-timings.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, sort_keys=True) + "\n")
        except OSError as exc:
            print(f"WARN telemetry: could not write stage timing: {exc}", flush=True)

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
        with self._state_lock:
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

            start_msg = self._render_client_report_msg(phase, "start")
            self.report.to_requester("progress", start_msg)

        try:
            persona.resolve_for_phase(self.run_dir, phase.id)
        except (RuntimeError, TimeoutError) as exc:
            return self._block(phase, f"persona governance: {exc}")

        with self._state_lock:
            if phase.id == "P4-RENDER" and self.board:
                self.board.mark_in_progress()

        if phase.executor_kind == "script":
            rc = self._run_script_phase(phase)
        elif phase.executor_kind == "agent":
            rc = self._run_agent_phase(phase)
        else:
            with self._state_lock:
                self.report.event("phase.no_executor",
                                  f"{phase.id} declares no executor. This is an install-time error "
                                  "once fix A3 is enforced; blocking rather than skipping.")
            return self._block(phase, "no executor is defined for this phase")

        if rc == EXIT_OK:
            ok, missing = self._artifacts_present(phase)
            if not ok:
                with self._state_lock:
                    # heal internals record events + checkpoints — held under
                    # the engine lock; a rare regeneration serializes its wave
                    # rather than risk a torn state save.
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
                        return self._block(
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
            self._checkpoint(phase.id, status="done", attested_at=utcnow(), sha256=shas,
                             artifacts=sorted(shas.keys()),
                             verifier_ok=verifier_ok, verifier_notes=verifier_notes,
                             owner_skip_approval=verifier_skipped)
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
                             # U01-R2: resolve {deck_slug}/{run_dir} tokens before the scan
                             # so pre_run_artifacts reflects the real files, not the literal
                             # token path (QC FAIL 6.46).
                             for rel in phase.resolve_artifact_patterns(self.run_dir)
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

        # Rung 3: alternate route -- MECHANISM ONLY, NO CLIENT POLICY
        with self._state_lock:
            rc3 = heal.rung3_alt_route(self, phase)
        if rc3 == EXIT_OK:
            _r3 = 3
            with self._state_lock:
                heal.record_heal_event(self.state, phase.id, self.store, ps,
                                       rung=_r3, attempt=1, reason="alternate route")
            return EXIT_OK

        return self._block(phase, f"script executor failed after {heal.HEAL_CAP_TRANSIENT} attempts")

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
        with self._state_lock:
            if claim_live or wo_live:
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
            if ok and glob_patterns:
                # FAULT-16: bare presence is not completion for a multi-file
                # glob -- something NEWER than this dispatch's own baseline
                # (a new file, or an existing one rewritten) is still the
                # cheap fast path that trusts presence outright.
                if not (self._glob_progress_marker(glob_patterns) > baseline_progress):
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
                    ok = v_ok
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
                self._checkpoint(phase.id, status="running",
                                 waiting_for=list(phase.produces_artifact),
                                 waited_seconds=int(now - started_at))
            time.sleep(15)
        if last_present:
            return self._block(
                phase,
                f"artifact matching {', '.join(phase.produces_artifact)} exists but failed "
                f"substance verification for {phase.budget_minutes} minutes: "
                f"{'; '.join(last_verify_notes) or 'no verifier notes captured'}")
        return self._block(
            phase,
            f"agent-authored phase produced nothing within {phase.budget_minutes} minutes. "
            f"Expected: {', '.join(phase.produces_artifact)}")

    def _block(self, phase: Phase, reason: str) -> int:
        """Park resumable. Never die, never restart from scratch (decision #5)."""
        # Count banked artifacts BEFORE checkpointing, so the current
        # phase is still "done" when we look for done phases.
        with self._state_lock:
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
        # probe dict is the Phase A stub (see _PHASE_A_CAPACITY_PROBE). Only
        # phases the DAG marks independent share a wave — independence is never
        # invented here. A wave runs bounded by the measured capacity; every
        # future of a wave joins before a failure rc is returned, so a blocking
        # phase never abandons its wave-mates mid-flight.
        if _wave_execution_enabled():
            try:
                plan = build_execution_plan(self.manifest.path, _PHASE_A_CAPACITY_PROBE)
            except CapacityUnmeasured as exc:
                # Same loud refusal as execution_plan's own CLI: refuse, never
                # substitute an unmeasured width (Master-Spec file 9 AUTOFAIL).
                print(f"CAPACITY AUTOFAIL: {exc}", file=sys.stderr)
                print(json.dumps(autofail_payload(_PHASE_A_CAPACITY_PROBE), indent=2),
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

            def _run_wave(wave_no: int, members: List[Phase]) -> int:
                available = plan["available"]
                if not isinstance(available, int) or isinstance(available, bool):
                    # UNBOUNDED (a real measurement): no ceiling to enforce —
                    # the width is the wave size, never the sentinel literal.
                    available = len(members)
                width = max(1, min(len(members), available))
                with ThreadPoolExecutor(max_workers=width) as pool:
                    # list() joins EVERY future before returning, so all wave
                    # members finish (telemetry included) before we fail on rc.
                    rcs = list(pool.map(lambda m: self.run_phase_timed(m, wave=wave_no),
                                        members))
                return next((rc for rc in rcs if rc != EXIT_OK), EXIT_OK)

            for wave_no, members in enumerate(wave_phases, 1):
                if not members:
                    continue
                rc = _run_wave(wave_no, members)
                if rc != EXIT_OK:
                    return rc
            for p in extra:
                rc = self.run_phase_timed(p, wave=len(plan["waves"]) + 1)
                if rc != EXIT_OK:
                    return rc
        else:
            # PRESENTATION_WAVE_EXECUTION=0 rollback path: the pre-fix serial
            # loop, byte-for-byte (every phase wave=0).
            for p in phases:
                rc = self.run_phase_timed(p, wave=0)
                if rc != EXIT_OK:
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
        attested = [p for p in phases if p.get('status') == 'done']
        all_phase_ids = [p.get('id') for p in phases]

        # 2. Verify no gaps
        manifest_phase_ids = [p.id for p in self.manifest.phases]
        unentered = [pid for pid in manifest_phase_ids if pid not in all_phase_ids]
        incomplete = [p.get('id') for p in phases if p.get('status') not in ('done', 'blocked')]

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

        # 5. Monotonic timestamp check
        timestamps = []
        for p in attested:
            at = p.get('attested_at')
            if at:
                timestamps.append((p.get('id'), at))
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

