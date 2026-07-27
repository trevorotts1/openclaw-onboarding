from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

GATE_KEYS = ("script", "teleprompter", "prompt_floor", "ghl_upload", "qc")
NON_WAIVABLE_GATES = ("ocr_readback",)
ALL_GATE_KEYS = GATE_KEYS + NON_WAIVABLE_GATES

QC_PASS_THRESHOLD = 8.5

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
        U020 — delegate to the existing per-asset gate_ghl_media_complete (ghl_media_push.py
        :316-388). It checks folder + per-slide PNGs + final PPTX, and honors the owner token
        and client waiver paths — a much stronger check than the local read of phantom keys.

        The import chain is ghl_media_push -> ghl_media -> _find_canonical_ghl_media (which
        does a filesystem walk and module exec at import time, but no network call), and
        ghl_media_push -> delivery_gate (already imported by the time this runs). Verified
        safe for gate evaluation: no credential resolution or network call at import time.

        Falls back to the local read (U013's key-reading implementation) when the producer
        module is unimportable, so the engine still works on a box without it installed.
        """
        try:
            sys.path.insert(0, str((Path(__file__).resolve().parent.parent)))
            import ghl_media_push
            ok, reasons = ghl_media_push.gate_ghl_media_complete(self.run_dir)
        except Exception as exc:
            p = self.run_dir / "working" / "checkpoints" / "media_library.json"
            if not p.is_file():
                return {"state": "fail",
                        "evidence": str(p.relative_to(self.run_dir)),
                        "reason": f"upload gate unevaluable: {exc!r} (fail-closed) — "
                                  "no media_library.json"}
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc2:
                return {"state": "fail",
                        "reason": f"upload gate unevaluable: {exc!r} (fail-closed) — "
                                  f"media_library.json unreadable: {exc2}"}
            # Document the keys the producer actually writes: ghl_folder_id, slides[],
            # pptx_ghl_media_id. Never media_ids or folder_id (C2's phantom keys — U013).
            folder = str(obj.get("ghl_folder_id") or "").strip()
            slides = obj.get("slides") or []
            pptx_id = str(obj.get("pptx_ghl_media_id") or "").strip()
            if not folder and not slides and not pptx_id:
                return {"state": "fail",
                        "reason": f"upload gate unevaluable: {exc!r} (fail-closed) — "
                                  "gate_ghl_media_complete unavailable and "
                                  "media_library.json records zero uploaded assets. "
                                  "A client who declined the upload needs a waiver in "
                                  "waivers.json naming rule 'ghl_upload' with their own "
                                  "quoted words. An operator skipping the gate needs an "
                                  "owner_skip_approval token in process_manifest.json. "
                                  "These are different things: the first is client "
                                  "consent, the second is an operator decision."}
            return {"state": "pass", "ghl_folder_id": folder,
                    "reason": f"gate_ghl_media_complete unavailable ({exc!r}); "
                              "falling back to local ledger read — records present"}
        if ok:
            return {"state": "pass", "reason": None}
        # Add the dual-route guidance to the failure reason so an operator reading a
        # rejection knows which bypass path applies.
        return {"state": "fail",
                "reason": "; ".join(reasons) + ". A client who declined the upload needs "
                          "a waiver in waivers.json naming rule 'ghl_upload' with their own "
                          "quoted words. An operator skipping the gate needs an "
                          "owner_skip_approval token in process_manifest.json. These are "
                          "different things: the first is client consent, the second is an "
                          "operator decision."}

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

