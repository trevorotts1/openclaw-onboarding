from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .deliverables import DELIVERABLE_AUDIT_SPEC as _DELIVERABLE_AUDIT_SPEC
from .result import CheckResult
GATE_KEYS = ("script", "teleprompter", "prompt_floor", "ghl_upload", "qc")
# DERIVED from presentation_job/deliverables.py (the single source of truth,
# U05) rather than hardcoded -- this used to be a THIRD independent copy of the
# teleprompter_html floor (10_240, stale) alongside deliverables.py and
# build_deck.py's DELIVERABLES_REQUIRED (split-brain fix, 2026-08-18).
_MIN_BYTES = {s["key"]: s["min_bytes"] for s in _DELIVERABLE_AUDIT_SPEC}
NON_WAIVABLE_GATES = ("ocr_readback",)
ALL_GATE_KEYS = GATE_KEYS + NON_WAIVABLE_GATES
QC_PASS_THRESHOLD = 8.5
# The phase that OWES working/qc/final_qc_report.json. Mirrors the PIPELINE-MANIFEST.json
# entry (id / order / produces_artifact) so the operator-facing reason in _qc_gate names a
# real, schedulable phase instead of asserting no producer exists. These constants are
# pinned to the manifest by tests/test_f21_text_truth.py: change the manifest and the test
# fails until they are updated together. Deliberately NOT read from the manifest at import
# time -- gates.py is imported by close() paths that must not depend on a resolvable manifest
# on disk, and a wrong-but-tested constant beats a silent fallback to a stale string.
#
# QC_AGGREGATE_EVIDENCE_REL is state.json, NOT the dispatcher sidecar. P-QC-AGGREGATE declares
# executor kind "script", and a script phase runs through Engine._run_script_phase ->
# _run_script_phase_locked, which records via Engine._checkpoint into state.json's phases[]
# entry (status / attempts / heal_events, plus quarantined_reason + quarantined_at when
# _fail_unit quarantines it). working/work-orders/<phase>.dispatcher-log.jsonl is written by
# dispatcher._append_sidecar for AGENT phases only -- phases.py's own _sidecar_pending
# docstring says so outright ("the engine never writes it"). Pointing a stuck operator at a
# file this phase never creates would be the same class of lie F21 exists to remove.
QC_AGGREGATE_PHASE_ID = "P-QC-AGGREGATE"
QC_AGGREGATE_PHASE_ORDER = 8.65
QC_AGGREGATE_EVIDENCE_REL = "state.json"
# ocr_readback was removed from this tuple deliberately (see _ocr_gate below): MASTER-SPEC
# section 7.4 and decision D10 require an unchecked slide-content readback to BLOCK the job,
# and D10 names it as the one gate no waiver can pass either. U013 originally staged it here
# in warn-mode because no phase declared a producer for renders/slide-*.ocr.json; that
# producer question is orthogonal to whether a missing/unchecked record should ever be
# allowed to reach DONE, and the spec's answer for "unchecked" is unconditional: no.
#
# `qc` was removed from this tuple for the identical reason, in a follow-up fix. When that fix
# was written there was genuinely no producer for working/qc/final_qc_report.json: the manifest's
# six QC phases each wrote only their OWN domain report (copy_qc_report.json,
# typography_qc_report.json, prompt_qc_report.json, image_qc_report.json,
# priority_shift_report.json, speech_qc_report.json) and nothing aggregated them. This gate's
# input was therefore permanently absent, and being warn-only meant a job could reach DONE with
# NO QC score at all. D10's own doctrine names that shape directly: "a check that defers because
# its input is missing is a fail-open wearing a fail-closed label." The fix mirrors ocr_readback
# exactly: _qc_gate below sets warn_only=False on every branch, so close() always routes a
# missing/unreadable/sub-threshold QC report into the blocking `failures` list, never the
# non-blocking `gate_warnings` list. Unlike ocr_readback, `qc` stays a member of GATE_KEYS (not
# NON_WAIVABLE_GATES) -- the department's ratified strictness decision is fail-closed by default,
# with the client's own quoted request (via waivers.json, validated by waivers.py) as the ONLY
# bypass.
#
# TEXT-TRUTH (F21, 2026-09): the "no producer exists" half of the paragraph above WAS true when
# it was written and is NOT true any more, and it stayed in the operator-facing failure reason
# long after it went stale -- an outside reviewer read it and filed a P0 for a defect that does
# not exist. The producer landed with manifest_version 34 -> 35 (see manifest.py's version log:
# "merging fix/qc-gate-fail-closed adds P-QC-AGGREGATE"). As of manifest_version 67 the phase
# P-QC-AGGREGATE is scheduled at order 8.65, owned by qc-specialist-presentations, executor
# `python3 scripts/qc_aggregate.py --run-dir {run_dir} --phase-mode`, declares
# produces_artifact = "working/qc/final_qc_report.json", and consumes exactly the six domain
# reports listed above. A missing final_qc_report.json today means THAT PHASE did not produce
# it -- not that nothing can. Blocking is still the only honest behaviour, but the reason an
# operator reads must point them at the phase and at the evidence that phase actually leaves
# behind (its state.json phases[] record -- see QC_AGGREGATE_EVIDENCE_REL above for why that
# is state.json and not the dispatcher sidecar), not at a producer gap that closed.
# See CHANGELOG [Unreleased] qc-gate-fail-closed for the original account. Guarded by
# tests/test_f21_text_truth.py -- do not reintroduce a "no phase produces this" claim here.
WARN_ONLY_GATES = ()
class Gates:
    def __init__(self, run_dir: Path, state: Dict[str, Any]) -> None:
        self.run_dir = run_dir
        self.state = state
    def _prompt_gate(self):
        """Lazily import the shared prompt_gate module (ships beside this package's
        parent scripts dir). Returns the module or None so callers degrade gracefully
        to their built-in checks — mirrors build_deck._import_prompt_gate."""
        try:
            import importlib
            import sys as _sys
            here = Path(__file__).resolve().parent.parent  # scripts/
            if str(here) not in _sys.path:
                _sys.path.insert(0, str(here))
            return importlib.import_module("prompt_gate")
        except Exception:  # noqa: BLE001
            return None
    def _canonical_prompt_dir_problems(self) -> Tuple[CheckResult, List[str]]:
        """Directory-level prompt problems (duplicates / non-canonical names) as this
        gate's strictness requires them. Runs the shared prompt_gate detector (FIX-22 /
        D16), then applies build_deck's R3 3-digit-canonical OVERLAY on its verdict —
        _canonical_prompt_dir_problems in build_deck.py is the SINGLE source of that
        re-judgement: signature decks have a 100-slide floor, so a name whose ordinal
        field is exactly 2 OR 3 digits is canonical (slide-01..slide-99, slide-100..
        slide-999, plus the -prompt variants). AF-PROMPT-NAME is relaxed accordingly;
        AF-PROMPT-DUP-FILE passes through unchanged (a same-ordinal collision stays
        fatal at any digit width, R3). The shared prompt_gate module itself is
        deliberately left %02d-only (other consumers depend on that contract).
        build_deck imports cleanly with no side effects (verified: stdlib + its own
        package's checkpoint only), so this route is preferred whenever it is
        importable; on any failure it degrades to the raw shared-detector verdict
        (the pre-R3 behaviour).

        Returns (CheckResult, problems). CheckResult.UNDETERMINED means the detector
        itself could not run at all -- both the build_deck route AND the shared
        prompt_gate fallback failed -- and `problems` is `[]` in that case for the
        same reason `[]` means "checked, clean" in the other two outcomes: an empty
        list alone can't tell those two apart. This used to just `return []` on a
        double-fallback failure, which read as "no duplicate-prompt-file problems"
        to every caller -- a genuine slide-1.txt/slide-01.txt collision (D16) would
        have gone completely undetected and this gate would have reported PASS.
        This is a security/completeness gate: UNDETERMINED refuses (see result.py)."""
        try:
            import importlib
            import sys as _sys
            here = Path(__file__).resolve().parent.parent  # scripts/
            if str(here) not in _sys.path:
                _sys.path.insert(0, str(here))
            bd = importlib.import_module("build_deck")
            problems = bd._canonical_prompt_dir_problems(self.run_dir)
            problems = list(problems) if problems else []
            return (CheckResult.FAIL if problems else CheckResult.PASS), problems
        except Exception:  # noqa: BLE001 — degrade to the raw shared verdict
            _pg = self._prompt_gate()
            if _pg is None:
                return CheckResult.UNDETERMINED, []
            try:
                problems = list(_pg.prompt_dir_problems(self.run_dir / "working" / "prompts"))
            except Exception:  # noqa: BLE001 — the fallback detector itself failed too
                return CheckResult.UNDETERMINED, []
            return (CheckResult.FAIL if problems else CheckResult.PASS), problems
    def evaluate_all(self) -> Dict[str, Dict[str, Any]]:
        g = self.state.setdefault("gates", {})
        g["script"] = self._artifact_gate_any(["working/deliverables/PRESENTERS-SPEECH.md","working/presenter-speech/PRESENTERS-SPEECH.md"], 2048)
        # RECONCILED (split-brain fix, 2026-08-18): the doctrine-ratified floor is
        # sops/presenters-speech-writer-sops.md's AF-BUNDLE-COMPLETE gate-tie-in line,
        # verbatim "HTML >= 20,000 bytes", also enforced at production time by
        # build_teleprompter.py's own TELEPROMPTER_MIN_BYTES. This gate previously
        # hardcoded 10_240 (a never-cited number this codebase's own git history shows
        # was copied from PIPELINE-MANIFEST.json's own orphaned pre-doctrine value,
        # dated 2026-06-17 -- before the 2026-07-12 reconciliation, commit eaae2e33).
        g["teleprompter"] = self._artifact_gate(
            "working/deliverables/presenter-teleprompter.html", _MIN_BYTES["teleprompter_html"])
        g["prompt_floor"] = self._prompt_floor_gate()
        g["ghl_upload"] = self._ghl_gate()
        g["qc"] = self._qc_gate()
        g["ocr_readback"] = self._ocr_gate()
        return g
    def _artifact_gate(self, rel: str, min_bytes: int) -> Dict[str, Any]:
        p = self.run_dir / rel
        if not p.is_file(): return {"state":"fail","evidence":rel,"reason":f"{rel} does not exist"}
        size = p.stat().st_size
        if size < min_bytes: return {"state":"fail","evidence":rel,"reason":f"{rel} is {size} bytes, below the {min_bytes}-byte floor"}
        return {"state":"pass","evidence":rel,"bytes":size,"reason":None}
    def _artifact_gate_any(self, paths: List[str], min_bytes: int) -> Dict[str, Any]:
        for rel in paths:
            p = self.run_dir / rel
            if p.is_file():
                size = p.stat().st_size
                if size >= min_bytes: return {"state":"pass","evidence":rel,"bytes":size,"reason":None}
                return {"state":"fail","evidence":rel,"reason":f"{rel} is {size} bytes, below the {min_bytes}-byte floor"}
        return {"state":"fail","evidence":paths[0],"reason":f"none of {paths} exist"}
    def _prompt_floor_gate(self) -> Dict[str, Any]:
        floor = 9000
        d = self.run_dir / "working" / "prompts"
        if not d.is_dir(): return {"state":"fail","evidence":"working/prompts","reason":"no prompts directory -- nothing to measure"}
        # FIX-22 / D16: a zero-padding naming collision (slide-1.txt vs slide-01.txt)
        # or any non-canonical prompt filename fails the gate BEFORE the floor measure —
        # two files for one slide would silently ship a wrong/duplicate render.
        # R3 / D10: the verdict runs through build_deck's canonical overlay
        # (2-OR-3-digit ordinals are canonical, since signature decks have a 100-slide
        # floor) — see _canonical_prompt_dir_problems above, whose build_deck route is
        # the single source of the overlay.
        dir_result, dir_problems = self._canonical_prompt_dir_problems()
        if dir_result is CheckResult.UNDETERMINED:
            # Both the build_deck and shared prompt_gate detectors failed to run --
            # this gate cannot tell you there ISN'T a slide-1.txt/slide-01.txt
            # collision, so it refuses rather than silently passing. Fix the
            # import path (build_deck / prompt_gate both unreachable from here)
            # and re-run; do not waive this away as if it were a normal fail.
            return {"state":"fail","evidence":"working/prompts",
                    "reason":"prompt duplicate/canonical-name detector could not run "
                             "(both the build_deck route and the shared prompt_gate "
                             "fallback raised) -- UNDETERMINED, not checked. Refusing: "
                             "a security/completeness gate never treats 'could not "
                             "check' as a pass. See FIX-22 / D16."}
        if dir_problems:
            return {"state":"fail","evidence":"working/prompts",
                    "reason":"; ".join(dir_problems[:5])}
        files = sorted(d.glob("slide-*.txt"))
        if not files: return {"state":"fail","evidence":"working/prompts","reason":"prompts directory is empty"}
        lengths = [(f.name, len(f.read_text(encoding="utf-8", errors="replace"))) for f in files]
        short = [(n, L) for n, L in lengths if L < floor]
        base = {"evidence":"working/prompts","slides_checked":len(lengths),"min_chars_seen":min(L for _, L in lengths)}
        if short: return {**base,"state":"fail","reason":f"{len(short)} prompt(s) below the {floor}-char floor: "+", ".join(f"{n}={L}" for n, L in short[:5])}
        return {**base,"state":"pass","reason":None}
    def _ghl_gate(self) -> Dict[str, Any]:
        p = self.run_dir / "working" / "checkpoints" / "media_library.json"
        if not p.is_file(): return {"state":"fail","evidence":str(p.relative_to(self.run_dir)),"reason":"no GHL media-library record -- the upload phase did not run"}
        try: obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc: return {"state":"fail","reason":f"media_library.json unreadable: {exc}"}
        folder_id = str(obj.get("ghl_folder_id") or "").strip()
        slides = [e for e in (obj.get("slides") or []) if isinstance(e, dict)]
        complete = [e for e in slides if (e.get("ghl_media_id") or e.get("file_id")) and str(e.get("ghl_upload_status") or "").lower() == "complete"]
        pptx_id = str(obj.get("pptx_ghl_media_id") or "").strip()
        missing = []
        if not folder_id: missing.append("ghl_folder_id is null or empty -- the per-deck media folder was never resolved")
        if not complete: missing.append("no per-slide upload carries a real ghl_media_id with status 'complete'")
        elif len(complete) != len(slides): missing.append(f"{len(slides) - len(complete)} of {len(slides)} slide uploads are incomplete")
        if not pptx_id: missing.append("pptx_ghl_media_id is absent -- the assembled deck is not in the media library")
        base = {"evidence":str(p.relative_to(self.run_dir)),"ghl_folder_id":folder_id or None,"slide_uploads_complete":len(complete),"slide_uploads_total":len(slides),"pptx_ghl_media_id":pptx_id or None}
        if missing: return {**base,"state":"fail","reason":"; ".join(missing)}
        return {**base,"state":"pass","reason":None}
    def _qc_gate(self) -> Dict[str, Any]:
        # MASTER-SPEC / D10, same fail-closed contract as _ocr_gate: warn_only is always False
        # here, on every branch, so a missing, unreadable, unscored, or sub-threshold QC report
        # lands in close()'s blocking `failures` list, never the non-blocking `gate_warnings`
        # list. See the WARN_ONLY_GATES comment above for the full account of why this gate
        # used to defer (at the time, nothing produced final_qc_report.json) and why deferring
        # is exactly the fail-open shape the doctrine forbids: a missing input BLOCKS, it does
        # not pass. The producer EXISTS now -- P-QC-AGGREGATE, order 8.65 -- so the reason below
        # names the phase that owes the file, never "no phase produces it" (F21).
        p = self.run_dir / "working" / "qc" / "final_qc_report.json"
        if not p.is_file():
            return {"state":"fail","warn_only":False,
                    "reason":f"no final QC report at {p.relative_to(self.run_dir)} -- "
                             f"{QC_AGGREGATE_PHASE_ID} (order {QC_AGGREGATE_PHASE_ORDER}) did not "
                             "produce it -- see that phase's record in "
                             f"{QC_AGGREGATE_EVIDENCE_REL} (phases[] entry "
                             f"id={QC_AGGREGATE_PHASE_ID}: status, attempts, heal_events, "
                             "quarantined_reason) for why. "
                             f"Without the report the deck's overall QC score "
                             f"(>= {QC_PASS_THRESHOLD} required) cannot be verified. "
                             "This cannot close silently: either "
                             f"{QC_AGGREGATE_PHASE_ID} must run to completion (executor: "
                             "scripts/qc_aggregate.py, which aggregates the six domain QC "
                             "reports), or the client must be asked to waive this gate "
                             "(waivers.json, rule=qc, quoting the client's own words)."}
        try: obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {"state":"fail","warn_only":False,"reason":f"QC report unreadable: {exc}"}
        score = obj.get("average") or obj.get("score")
        # qc_aggregate.py (the final_qc_report.json producer, P-QC-AGGREGATE) records
        # WHY the score is missing/absent in "blocking_reasons" -- e.g. which of the six
        # domain reports is missing, which AF-QC-* provenance code fired, which domain
        # scored below threshold. When present, fold it into the reason so "no numeric
        # score" is never the whole story a human sees. Purely additive: a report with no
        # blocking_reasons key (every existing test fixture) is unaffected.
        reasons = obj.get("blocking_reasons")
        detail = "; ".join(str(r) for r in reasons) if isinstance(reasons, list) and reasons else ""
        if not isinstance(score, (int, float)):
            base = "QC report carries no numeric score"
            return {"state":"fail","warn_only":False,
                    "reason": f"{base} -- {detail}" if detail else base}
        if score < QC_PASS_THRESHOLD:
            base = f"QC score {score} is below the {QC_PASS_THRESHOLD} threshold"
            return {"state":"fail","score":score,"warn_only":False,
                    "reason": f"{base} -- {detail}" if detail else base}
        return {"state":"pass","score":score,"per_dimension":obj.get("per_dimension"),"reason":None,"warn_only":False}
    def _ocr_gate(self) -> Dict[str, Any]:
        # MASTER-SPEC 7.4 / D10: the slide-content readback is the one gate that fail-closes
        # unconditionally -- "a check that disabled itself is not a pass, and no waiver can
        # make it one." warn_only is always False here, on every branch, on purpose: an
        # unchecked or mismatched readback must land in close()'s `failures`, never in the
        # non-blocking `gate_warnings` list. See NON_WAIVABLE_GATES above for the companion
        # half of the contract (no waiver can mark this gate "waived" either).
        d = self.run_dir / "renders"
        sidecars = sorted(d.glob("slide-*.ocr.json")) if d.is_dir() else []
        if not sidecars: return {"state":"fail","checked":False,"warn_only":False,"reason":"no OCR readback records -- no slide was ever read back against its approved copy"}
        unchecked, mismatched = [], []
        for s in sidecars:
            try: o = json.loads(s.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError): unchecked.append(s.name); continue
            if not o.get("checked"): unchecked.append(s.name)
            elif o.get("matched") is False: mismatched.append(s.name)
        if unchecked: return {"state":"fail","checked":False,"warn_only":False,"reason":f"{len(unchecked)} slide(s) unchecked: {', '.join(unchecked[:5])} -- the OCR engine did not run against these renders"}
        if mismatched: return {"state":"fail","checked":True,"warn_only":False,"reason":f"{len(mismatched)} slide(s) mismatched: {', '.join(mismatched[:5])} -- rendered text does not match the approved copy"}
        return {"state":"pass","checked":True,"slides":len(sidecars),"reason":None,"warn_only":False}
