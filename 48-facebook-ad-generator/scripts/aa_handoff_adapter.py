#!/usr/bin/env python3
"""aa_handoff_adapter.py - Skill 48 import adapter for Skill 52 handoff."""
import argparse, hashlib, json, sys
from pathlib import Path

REQUIRED = ["Top_39_Suggested_Ad_Angles","Facebook_Headline_and_Primary_Text_Ad_Copy_Writer","Facebook_Targeting_Intelligence"]
VERSION = "1.0.0"

def _sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def _load_handoff(hd):
    p = hd / "HANDOFF.json"
    if not p.is_file(): return None, [("AF-FBAD-ADAPTER-NO-HANDOFF", f"no handoff in {hd}")]
    try: ho = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e: return None, [("AF-FBAD-ADAPTER-PARSE", f"parse error: {e}")]
    if ho.get("handoff") != "avatar-alchemist-downstream": return None, [("AF-FBAD-ADAPTER-NOT-HANDOFF", "not a handoff")]
    if ho.get("skill") != "52-avatar-alchemist": return None, [("AF-FBAD-ADAPTER-WRONG-SKILL", "wrong source")]
    return ho, []
def _find_target(ho):
    for t in (ho.get("targets", []) or []):
        if isinstance(t, dict) and t.get("skill_number") == 48: return t, []
    return None, [("AF-FBAD-ADAPTER-NO-TARGET", "no target for skill 48")]
def _verify_checksums(hd, tgt):
    vs = []
    for inp in (tgt.get("inputs", []) or []) + (tgt.get("supporting", []) or []):
        if not isinstance(inp, dict): continue
        fn, es = inp.get("file", ""), inp.get("sha256", "")
        fp = hd / fn
        if not fp.is_file(): vs.append(("AF-FBAD-ADAPTER-MISSING", f"file {fn!r} missing"))
        elif _sha(fp) != es: vs.append(("AF-FBAD-ADAPTER-CHECKSUM", f"checksum mismatch {fn!r}"))
    return vs
def _parse_angles(fp):
    raw = fp.read_text(encoding="utf-8")
    lines = [l.strip() for l in raw.splitlines() if l.strip() and not l.strip().startswith("#")]
    return {"source": "aa-handoff", "version": VERSION, "deliverable": "Top_39_Suggested_Ad_Angles",
            "total": len(lines), "angles": [{"i": i + 1, "text": t} for i, t in enumerate(lines)]}
def _parse_copy(fp):
    raw = fp.read_text(encoding="utf-8")
    lines = raw.splitlines()
    hls, pts, cur = [], [], ""
    for ln in lines:
        s = ln.strip()
        if not s: continue
        low = s.lower()
        if "headline" in low and len(s) < 20: cur = "hl"; continue
        if "primary text" in low or "primary_text" in low or "ad copy" in low: cur = "pt"; continue
        if s.startswith("#"): continue
        if cur == "hl": hls.append(s)
        elif cur == "pt": pts.append(s)
    if not hls and not pts:
        pts = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    return {"source": "aa-handoff", "version": VERSION,
            "deliverable": "Facebook_Headline_and_Primary_Text_Ad_Copy_Writer",
            "headlines": hls, "primary_text": pts}
def _parse_targeting(fp):
    raw = fp.read_text(encoding="utf-8")
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    groups, cur = [], None
    for ln in lines:
        if ln.startswith("#"):
            if cur: groups.append(cur)
            cur = {"name": ln.lstrip("#").strip(), "explanation": f"Targeting: {ln.lstrip('#').strip()}",
                   "layer1": [], "layer2": [], "layer3": []}
        elif cur is not None:
            s = ln.lstrip("-*").strip()
            if s: cur["layer1"].append(s)
    if cur: groups.append(cur)
    if not groups:
        interests = [l.lstrip("-*").strip() for l in lines if not l.startswith("#")]
        groups = [{"name": "AA Targeting", "explanation": "From AA package",
                    "layer1": interests, "layer2": [], "layer3": []}]
    return {"source": "aa-handoff", "version": VERSION, "deliverable": "Facebook_Targeting_Intelligence",
            "groups": groups}
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
    errors, mapped = [], {}
    for key, parser in [
        ("Top_39_Suggested_Ad_Angles", _parse_angles),
        ("Facebook_Headline_and_Primary_Text_Ad_Copy_Writer", _parse_copy),
        ("Facebook_Targeting_Intelligence", _parse_targeting),
    ]:
        fn = imap.get(key, "")
        if fn:
            try: mapped[key] = parser(hd / fn)
            except Exception as e: errors.append(("AF-FBAD-ADAPTER-PARSE", f"{key}: {e}"))
    if errors: return errors, None
    for b in REQUIRED:
        if b not in imap: return [("AF-FBAD-ADAPTER-MISSING", f"Required {b!r} missing")], None
    out.mkdir(parents=True, exist_ok=True)
    for k, data in mapped.items():
        fname = k.replace(" ", "_").replace("/", "_")
        (out / f"{fname}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return [], mapped
def _report(vs, mapped, out):
    if not vs and mapped is not None: print(f"PASS: {len(mapped)} inputs -> {out}")
    else:
        print(f"FAIL: {len(vs)} violations")
        for c, m in vs: print(f"  [{c}] {m}")
def main(argv):
    ap = argparse.ArgumentParser(description="Import AA handoff into Skill 48")
    ap.add_argument("--handoff-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    hd, od = Path(args.handoff_dir), Path(args.out_dir)
    if not hd.is_dir(): print(f"ERROR: not dir {hd}"); return 3
    try: vs, mapped = import_handoff(hd, od)
    except Exception as e: print(f"ERROR: {e}"); return 3
    _report(vs, mapped, od)
    return 0 if not vs else 2
if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
