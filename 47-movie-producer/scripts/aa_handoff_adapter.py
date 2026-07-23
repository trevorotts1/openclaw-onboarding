#!/usr/bin/env python3
"""aa_handoff_adapter.py - Skill 47 import adapter for Skill 52 handoff."""
import argparse, hashlib, json, sys
from pathlib import Path
REQUIRED = ["Top_39_Suggested_Image_Prompts", "Landing_Page_Image_Prompts"]
VERSION = "1.0.0"
def _sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def _load_handoff(hd):
    p = hd / "HANDOFF.json"
    if not p.is_file(): return None, [("AF-VID-ADAPTER-NO-HANDOFF", f"no handoff in {hd}")]
    try: ho = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e: return None, [("AF-VID-ADAPTER-PARSE", f"parse error: {e}")]
    if ho.get("handoff") != "avatar-alchemist-downstream": return None, [("AF-VID-ADAPTER-NOT-HANDOFF", "not a handoff")]
    if ho.get("skill") != "52-avatar-alchemist": return None, [("AF-VID-ADAPTER-WRONG-SKILL", "wrong source")]
    return ho, []
def _find_target(ho):
    for t in (ho.get("targets", []) or []):
        if isinstance(t, dict) and t.get("skill_number") == 47: return t, []
    return None, [("AF-VID-ADAPTER-NO-TARGET", "no target for skill 47")]
def _verify_checksums(hd, tgt):
    vs = []
    for inp in (tgt.get("inputs", []) or []) + (tgt.get("supporting", []) or []):
        if not isinstance(inp, dict): continue
        fn, es = inp.get("file", ""), inp.get("sha256", "")
        fp = hd / fn
        if not fp.is_file(): vs.append(("AF-VID-ADAPTER-MISSING", f"file {fn!r} missing"))
        elif _sha(fp) != es: vs.append(("AF-VID-ADAPTER-CHECKSUM", f"checksum mismatch {fn!r}"))
    return vs
def _parse_prompts(fp, name):
    raw = fp.read_text(encoding="utf-8")
    prompts, cur_lines, idx = [], [], 0
    for ln in raw.splitlines():
        s = ln.strip()
        if s.startswith("## ") or s.startswith("# ") or s == "---":
            if cur_lines:
                body = "\n".join(cur_lines).strip()
                if body: idx += 1; prompts.append({"index": idx, "text": body})
                cur_lines = []
            continue
        if s: cur_lines.append(s)
    if cur_lines:
        body = "\n".join(cur_lines).strip()
        if body: idx += 1; prompts.append({"index": idx, "text": body})
    if not prompts:
        content = [l.strip() for l in raw.splitlines() if l.strip() and not l.strip().startswith("#")]
        if content: prompts = [{"index": 1, "text": "\n".join(content)}]
    return {"source": "aa-handoff", "version": VERSION, "deliverable": name,
            "total_prompts": len(prompts), "prompts": prompts}
def import_handoff(hd, out):
    ho, hv = _load_handoff(hd)
    if ho is None: return hv, None
    tgt, tv = _find_target(ho)
    if tgt is None: return tv, None
    cv = _verify_checksums(hd, tgt)
    if cv: return cv, None
    imap = {}
    for inp in (tgt.get("inputs", []) or []):
        if isinstance(inp, dict): imap[inp.get("deliverable", "")] = inp.get("file", "")
    errors, ip, lp = [], {}, {}
    for key, store in [("Top_39_Suggested_Image_Prompts", "ip"), ("Landing_Page_Image_Prompts", "lp")]:
        fn = imap.get(key, "")
        if fn:
            try:
                parsed = _parse_prompts(hd / fn, key)
                if store == "ip": ip = parsed
                else: lp = parsed
            except Exception as e: errors.append(("AF-VID-ADAPTER-PARSE", f"{key}: {e}"))
    if errors: return errors, None
    for b in REQUIRED:
        if b not in imap: return [("AF-VID-ADAPTER-MISSING", f"Required {b!r} missing")], None
    cl = ho.get("client_label", "unknown")
    topic = (lp.get("prompts", [{}])[0].get("text", "AA prod") or "AA prod")[:80]
    jm = {"job_id": f"aa-handoff-{cl.replace('_', '-').lower()}", "title": topic, "topic": topic,
          "brief_gist": topic, "target_duration_sec": 60, "aspect_ratio": "16:9",
          "budget_ceiling_usd": 5.0, "estimated_cost_usd": 0.0, "tone": "brand-commercial",
          "pipeline_selected": "documentary-montage", "pipeline_slug": "documentary-montage.yaml",
          "kie_in_scope": False, "department": "video", "owner": cl.replace("_", " "),
          "source": "aa-handoff", "adapter_version": VERSION}
    out.mkdir(parents=True, exist_ok=True)
    (out / "job-manifest.json").write_text(json.dumps(jm, indent=2) + "\n", encoding="utf-8")
    (out / "image-prompts.json").write_text(json.dumps(ip, indent=2) + "\n", encoding="utf-8")
    (out / "landing-image-prompts.json").write_text(json.dumps(lp, indent=2) + "\n", encoding="utf-8")
    return [], {"job-manifest": jm, "image-prompts": ip, "landing-image-prompts": lp}
def _report(vs, mapped, out):
    if not vs and mapped is not None: print(f"PASS: 3 files -> {out}")
    else:
        print(f"FAIL: {len(vs)} violations")
        for c, m in vs: print(f"  [{c}] {m}")
def main(argv):
    ap = argparse.ArgumentParser(description="Import AA handoff into Skill 47")
    ap.add_argument("--handoff-dir", required=True); ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    hd, od = Path(args.handoff_dir), Path(args.out_dir)
    if not hd.is_dir(): print(f"ERROR: not dir {hd}"); return 3
    try: vs, mapped = import_handoff(hd, od)
    except Exception as e: print(f"ERROR: {e}"); return 3
    _report(vs, mapped, od)
    return 0 if not vs else 2
if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
