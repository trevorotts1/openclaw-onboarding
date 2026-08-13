from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
GATE_KEYS = ("script", "teleprompter", "prompt_floor", "ghl_upload", "qc")
NON_WAIVABLE_GATES = ("ocr_readback",)
ALL_GATE_KEYS = GATE_KEYS + NON_WAIVABLE_GATES
QC_PASS_THRESHOLD = 8.5
# ocr_readback was removed from this tuple deliberately (see _ocr_gate below): MASTER-SPEC
# section 7.4 and decision D10 require an unchecked slide-content readback to BLOCK the job,
# and D10 names it as the one gate no waiver can pass either. U013 originally staged it here
# in warn-mode because no phase declared a producer for renders/slide-*.ocr.json; that
# producer question is orthogonal to whether a missing/unchecked record should ever be
# allowed to reach DONE, and the spec's answer for "unchecked" is unconditional: no.
#
# `qc` was removed from this tuple for the identical reason, in a follow-up fix. It was left
# behind when ocr_readback was fixed with a "that reasoning still holds for qc" note (see
# CHANGELOG) -- but a QC review of that very fix flagged it as the same defect shape, still
# open: no phase anywhere writes working/qc/final_qc_report.json (verified by grep across the
# whole repo -- the manifest's six QC phases each write their OWN domain report --
# copy_qc_report.json, typography_qc_report.json, prompt_qc_report.json, image_qc_report.json,
# priority_shift_report.json, speech_qc_report.json -- and nothing aggregates them into
# final_qc_report.json), so this gate's input was permanently absent, and being warn-only meant
# a job could reach DONE with NO QC score at all. D10's own doctrine names this shape directly:
# "a check that defers because its input is missing is a fail-open wearing a fail-closed label."
# The correct fix mirrors ocr_readback exactly: _qc_gate below now sets warn_only=False on every
# branch, so close() always routes a missing/unreadable/sub-threshold QC report into the
# blocking `failures` list, never the non-blocking `gate_warnings` list. Unlike ocr_readback,
# `qc` stays a member of GATE_KEYS (not NON_WAIVABLE_GATES) -- the department's ratified
# strictness decision is fail-closed by default, with the client's own quoted request (via
# waivers.json, validated by waivers.py) as the ONLY bypass. A genuine producer for
# final_qc_report.json (an aggregation phase over the six domain reports) does not exist yet;
# until it does, every real job either produces one (out of band) or is blocked here, on
# purpose -- see CHANGELOG [Unreleased] qc-gate-fail-closed for the full account of why
# blocking, not a silent pass, is the only honest behaviour for a gate whose input is absent.
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
    def _canonical_prompt_dir_problems(self) -> List[str]:
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
        (the pre-R3 behaviour), never to a silent pass."""
        try:
            import importlib
            import sys as _sys
            here = Path(__file__).resolve().parent.parent  # scripts/
            if str(here) not in _sys.path:
                _sys.path.insert(0, str(here))
            bd = importlib.import_module("build_deck")
            problems = bd._canonical_prompt_dir_problems(self.run_dir)
            return list(problems) if problems else []
        except Exception:  # noqa: BLE001 — degrade to the raw shared verdict
            _pg = self._prompt_gate()
            if _pg is None:
                return []
            return list(_pg.prompt_dir_problems(self.run_dir / "working" / "prompts"))
    def evaluate_all(self) -> Dict[str, Dict[str, Any]]:
        g = self.state.setdefault("gates", {})
        g["script"] = self._artifact_gate_any(["working/deliverables/PRESENTERS-SPEECH.md","working/presenter-speech/PRESENTERS-SPEECH.md"], 2048)
        g["teleprompter"] = self._artifact_gate("working/deliverables/presenter-teleprompter.html", 10240)
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
        dir_problems = self._canonical_prompt_dir_problems()
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
        # used to defer (no phase produces final_qc_report.json) and why deferring is exactly
        # the fail-open shape the doctrine forbids: a missing input BLOCKS, it does not pass.
        p = self.run_dir / "working" / "qc" / "final_qc_report.json"
        if not p.is_file():
            return {"state":"fail","warn_only":False,
                    "reason":f"no final QC report at {p.relative_to(self.run_dir)} -- no phase "
                             "in the current manifest produces this file, so the deck's overall "
                             f"QC score (>= {QC_PASS_THRESHOLD} required) cannot be verified. "
                             "This cannot close silently: either a genuine final_qc_report.json "
                             "must be produced, or the client must be asked to waive this gate "
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
