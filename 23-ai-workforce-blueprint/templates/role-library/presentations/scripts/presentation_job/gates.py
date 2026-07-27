from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

GATE_KEYS = ("script", "teleprompter", "prompt_floor", "ghl_upload", "qc")
NON_WAIVABLE_GATES = ("ocr_readback",)
ALL_GATE_KEYS = GATE_KEYS + NON_WAIVABLE_GATES
# Warn-mode: these gates have no producer yet. They are printed, counted, and
# recorded into state["gate_warnings"], and do not enter failures. Remove from
# this set when the warn count reaches zero across the golden corpus (U013 step 3).
WARN_ONLY_GATES = ("qc", "ocr_readback")

QC_PASS_THRESHOLD = 8.5

# Import-time assertion: GATE_KEYS and NON_WAIVABLE_GATES must not overlap.
# A future edit that adds ocr_readback to GATE_KEYS silently makes it waivable;
# this assertion prevents that.
assert not (set(GATE_KEYS) & set(NON_WAIVABLE_GATES)), (
    "GATE_KEYS and NON_WAIVABLE_GATES overlap: "
    + str(set(GATE_KEYS) & set(NON_WAIVABLE_GATES))
)

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
        g["script"] = self._artifact_gate_any(
            ["working/deliverables/PRESENTERS-SPEECH.md",
             "working/presenter-speech/PRESENTERS-SPEECH.md"], 2048)
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

    def _artifact_gate_any(self, rels, min_bytes):
        """Try each path in order; return pass on the first one that meets the floor."""
        for rel in rels:
            p = self.run_dir / rel
            if not p.is_file():
                continue
            size = p.stat().st_size
            if size >= min_bytes:
                return {"state": "pass", "evidence": rel, "bytes": size,
                        "reason": None}
        tried = ", ".join(rels)
        return {"state": "fail", "evidence": tried,
                "reason": f"none of [{tried}] exists and meets the {min_bytes}-byte floor"}

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
        Key names are the PRODUCER's, verified against ghl_media_push.push_deck_media (:229-246),
        its own gate contract (:30-33), delivery_gate._check_destinations (:257), and the
        media-librarian role doc. There is no `media_ids` key anywhere in this system.
        """
        p = self.run_dir / "working" / "checkpoints" / "media_library.json"
        if not p.is_file():
            return {"state": "fail", "evidence": str(p.relative_to(self.run_dir)),
                    "reason": "no GHL media-library record -- the upload phase did not run"}
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {"state": "fail", "reason": f"media_library.json unreadable: {exc}"}
        # Key names are the PRODUCER's. See docstring.
        folder_id = str(obj.get("ghl_folder_id") or "").strip()
        slides = [e for e in (obj.get("slides") or []) if isinstance(e, dict)]
        complete = [e for e in slides
                    if (e.get("ghl_media_id") or e.get("file_id"))
                    and str(e.get("ghl_upload_status") or "").lower() == "complete"]
        pptx_id = str(obj.get("pptx_ghl_media_id") or "").strip()
        missing = []
        if not folder_id:
            missing.append("ghl_folder_id is null or empty -- the per-deck media folder was never resolved")
        if not complete:
            missing.append("no per-slide upload carries a real ghl_media_id with status 'complete'")
        elif len(complete) != len(slides):
            missing.append(f"{len(slides) - len(complete)} of {len(slides)} slide uploads are incomplete")
        if not pptx_id:
            missing.append("pptx_ghl_media_id is absent -- the assembled deck is not in the media library")
        base = {"evidence": str(p.relative_to(self.run_dir)),
                "ghl_folder_id": folder_id or None,
                "slide_uploads_complete": len(complete),
                "slide_uploads_total": len(slides),
                "pptx_ghl_media_id": pptx_id or None}
        if missing:
            return {**base, "state": "fail", "reason": "; ".join(missing)}
        return {**base, "state": "pass", "reason": None}

    def _qc_gate(self) -> Dict[str, Any]:
        p = self.run_dir / "working" / "qc" / "final_qc_report.json"
        warn_only = "qc" in WARN_ONLY_GATES
        if not p.is_file():
            return {"state": "fail", "reason": "no final QC report",
                    "warn_only": warn_only}
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {"state": "fail", "reason": f"QC report unreadable: {exc}",
                    "warn_only": warn_only}
        score = obj.get("average") or obj.get("score")
        if not isinstance(score, (int, float)):
            return {"state": "fail", "reason": "QC report carries no numeric score",
                    "warn_only": warn_only}
        if score < QC_PASS_THRESHOLD:
            return {"state": "fail", "score": score,
                    "reason": f"QC score {score} is below the {QC_PASS_THRESHOLD} threshold",
                    "warn_only": warn_only}
        return {"state": "pass", "score": score,
                "per_dimension": obj.get("per_dimension"), "reason": None}

    def _ocr_gate(self) -> Dict[str, Any]:
        """
        NOT WAIVABLE. prompt_gate.ocr_readback (:551) is the ONLY check in the whole pipeline that
        reads a finished slide's own content — and _ocr_engine_available (:514-526) returns
        (None, None) without tesseract, after which the guard at build_deck.py:1321 cannot fire.
        A self-disabled check is not a pass (fix D7).
        """
        warn_only = "ocr_readback" in WARN_ONLY_GATES
        d = self.run_dir / "renders"
        sidecars = sorted(d.glob("slide-*.ocr.json")) if d.is_dir() else []
        if not sidecars:
            return {"state": "fail", "checked": False,
                    "reason": "no OCR readback records. Either no slides were rendered, or the OCR "
                              "engine is not installed on this box. Install tesseract + "
                              "pytesseract; a self-disabled check does not count as a pass.",
                    "warn_only": warn_only}
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
                              f"(engine missing or skipped): {', '.join(unchecked[:5])}",
                    "warn_only": warn_only}
        if mismatched:
            return {"state": "fail", "checked": True,
                    "reason": f"{len(mismatched)} slide(s) failed OCR readback — the words on the "
                              f"slide do not match approved copy: {', '.join(mismatched[:5])}",
                    "warn_only": warn_only}
        return {"state": "pass", "checked": True, "slides": len(sidecars), "reason": None}


# ---------------------------------------------------------------------------
# Waivers. The only bypass, and it must not be self-issuable.
# ---------------------------------------------------------------------------

