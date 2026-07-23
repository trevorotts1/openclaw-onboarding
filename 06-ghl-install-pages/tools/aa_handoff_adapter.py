#!/usr/bin/env python3
"""aa_handoff_adapter.py - Skill 06 import adapter for Skill 52 handoff."""
import argparse, hashlib, json, sys
from pathlib import Path
REQUIRED = ["Landing_Page"]
VERSION = "1.0.0"
def _sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def _load_handoff(hd):
    p = hd / "HANDOFF.json"
    if not p.is_file(): return None, [("AF-GHL-ADAPTER-NO-HANDOFF", f"no handoff in {hd}")]
    try: ho = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e: return None, [("AF-GHL-ADAPTER-PARSE", f"parse error: {e}")]
    if ho.get("handoff") != "avatar-alchemist-downstream": return None, [("AF-GHL-ADAPTER-NOT-HANDOFF", "not a handoff")]
    if ho.get("skill") != "52-avatar-alchemist": return None, [("AF-GHL-ADAPTER-WRONG-SKILL", "wrong source")]
    return ho, []
def _find_target(ho):
    for t in (ho.get("targets", []) or []):
        if isinstance(t, dict) and t.get("skill_number") == 6: return t, []
    return None, [("AF-GHL-ADAPTER-NO-TARGET", "no target for skill 06")]
def _verify_checksums(hd, tgt):
    vs = []
    for inp in (tgt.get("inputs", []) or []):
        if not isinstance(inp, dict): continue
        fn, es = inp.get("file", ""), inp.get("sha256", "")
        fp = hd / fn
        if not fp.is_file(): vs.append(("AF-GHL-ADAPTER-MISSING", f"file {fn!r} missing"))
        elif _sha(fp) != es: vs.append(("AF-GHL-ADAPTER-CHECKSUM", f"checksum mismatch {fn!r}"))
    return vs
def _parse_lp(fp):
    raw = fp.read_text(encoding="utf-8")
    lines = raw.splitlines()
    s0 = raw.strip()
    is_html = s0.lower().startswith("<!doctype") or s0.lower().startswith("<html") or s0.startswith("<")
    title = "Avatar-Alchemist Landing Page"
    for ln in lines:
        s = ln.strip()
        if s.startswith("# ") and not s.startswith("## "): title = s[2:].strip()[:120]; break
    return {"source": "aa-handoff", "version": VERSION, "deliverable": "Landing_Page",
            "page_type_hint": "html" if is_html else "markdown", "title": title[:120],
            "line_count": len(lines), "char_count": len(raw), "word_count": len(raw.split())}
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
    fn = imap.get("Landing_Page", "")
    if not fn: return [("AF-GHL-ADAPTER-MISSING", "Landing_Page missing")], None
    try: meta = _parse_lp(hd / fn); raw = (hd / fn).read_text(encoding="utf-8")
    except Exception as e: return [("AF-GHL-ADAPTER-PARSE", f"LP parse fail: {e}")], None
    cl = ho.get("client_label", "unknown")
    sa = cl.replace("_", " ").strip()
    pm = {"source": "aa-handoff", "adapter_version": VERSION, "skill": "06-ghl-install-pages",
          "client_label": cl, "display_name": f"ZHC {sa} - {meta['title']}", "page_type": "funnel",
          "steps": [{"order": 1, "name": "ZHC part 1", "page_type_hint": meta["page_type_hint"],
                      "title": meta["title"], "content_file": "landing-page-content.md"}]}
    out.mkdir(parents=True, exist_ok=True)
    (out / "page-manifest.json").write_text(json.dumps(pm, indent=2) + "\n", encoding="utf-8")
    (out / "landing-page-content.md").write_text(raw, encoding="utf-8")
    return [], {"page-manifest": pm, "landing-page-content": raw}
def _report(vs, mapped, out):
    if not vs and mapped is not None: print(f"PASS: 2 files -> {out}")
    else:
        print(f"FAIL: {len(vs)} violations")
        for c, m in vs: print(f"  [{c}] {m}")
def main(argv):
    ap = argparse.ArgumentParser(description="Import AA handoff into Skill 06")
    ap.add_argument("--handoff-dir", required=True); ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    hd, od = Path(args.handoff_dir), Path(args.out_dir)
    if not hd.is_dir(): print(f"ERROR: not dir {hd}"); return 3
    try: vs, mapped = import_handoff(hd, od)
    except Exception as e: print(f"ERROR: {e}"); return 3
    _report(vs, mapped, od)
    return 0 if not vs else 2
if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
