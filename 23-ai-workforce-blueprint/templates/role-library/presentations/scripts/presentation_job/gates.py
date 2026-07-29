from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
GATE_KEYS = ("script", "teleprompter", "prompt_floor", "ghl_upload", "qc")
NON_WAIVABLE_GATES = ("ocr_readback",)
ALL_GATE_KEYS = GATE_KEYS + NON_WAIVABLE_GATES
QC_PASS_THRESHOLD = 8.5
WARN_ONLY_GATES = ("qc", "ocr_readback")
class Gates:
    def __init__(self, run_dir: Path, state: Dict[str, Any]) -> None:
        self.run_dir = run_dir
        self.state = state
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
        p = self.run_dir / "working" / "qc" / "final_qc_report.json"
        if not p.is_file(): return {"state":"fail","reason":"no final QC report","warn_only":True}
        try: obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc: return {"state":"fail","reason":f"QC report unreadable: {exc}","warn_only":True}
        score = obj.get("average") or obj.get("score")
        if not isinstance(score, (int, float)): return {"state":"fail","reason":"QC report carries no numeric score","warn_only":True}
        if score < QC_PASS_THRESHOLD: return {"state":"fail","score":score,"warn_only":True,"reason":f"QC score {score} is below the {QC_PASS_THRESHOLD} threshold"}
        return {"state":"pass","score":score,"per_dimension":obj.get("per_dimension"),"reason":None,"warn_only":False}
    def _ocr_gate(self) -> Dict[str, Any]:
        d = self.run_dir / "renders"
        sidecars = sorted(d.glob("slide-*.ocr.json")) if d.is_dir() else []
        if not sidecars: return {"state":"fail","checked":False,"warn_only":True,"reason":"no OCR readback records"}
        unchecked, mismatched = [], []
        for s in sidecars:
            try: o = json.loads(s.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError): unchecked.append(s.name); continue
            if not o.get("checked"): unchecked.append(s.name)
            elif o.get("matched") is False: mismatched.append(s.name)
        if unchecked: return {"state":"fail","checked":False,"warn_only":True,"reason":f"{len(unchecked)} slide(s) unchecked: {', '.join(unchecked[:5])}"}
        if mismatched: return {"state":"fail","checked":True,"warn_only":True,"reason":f"{len(mismatched)} slide(s) mismatched: {', '.join(mismatched[:5])}"}
        return {"state":"pass","checked":True,"slides":len(sidecars),"reason":None,"warn_only":False}
