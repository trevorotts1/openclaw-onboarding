#!/usr/bin/env python3
"""import_aa_handoff.py — U061: checksum-verified import adapter for Skill 48."""
import argparse, hashlib, json, shutil, sys
from pathlib import Path

SKILL_NUMBER=48; SKILL_NAME="facebook-ad-generator"
REQUIRED_BASES=["Top_39_Suggested_Ad_Angles","Facebook_Headline_and_Primary_Text_Ad_Copy_Writer","Facebook_Targeting_Intelligence"]

def _sha256_file(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def _find_target(handoff):
    for t in handoff.get("targets",[]):
        if t.get("skill_number")==SKILL_NUMBER or t.get("skill_name")==SKILL_NAME: return t
    return None

def _load_handoff(path):
    if not path.is_file(): return None,[("AF-IMPORT-NO-HANDOFF","HANDOFF.json not found")]
    try: h=json.loads(path.read_text(encoding="utf-8"))
    except Exception as e: return None,[("AF-IMPORT-BAD-JSON",str(e))]
    if h.get("handoff")!="avatar-alchemist-downstream": return None,[("AF-IMPORT-WRONG-HANDOFF","not an AA handoff")]
    return h,[]

def _verify_checksums(target, deliver_dir):
    v=[]
    for inp in target.get("inputs",[]):
        fn=inp.get("file",""); exp=inp.get("sha256",""); fp=deliver_dir/fn
        if not fp.is_file(): v.append(("AF-IMPORT-MISSING-FILE",repr(fn)+" absent")); continue
        act=_sha256_file(fp)
        if act!=exp: v.append(("AF-IMPORT-CHECKSUM-MISMATCH",repr(fn)+": checksum mismatch"))
    return v

def _map(target, deliver_dir):
    creative=[]; targeting=None
    for inp in target.get("inputs",[]):
        base=inp.get("deliverable",""); e={"name":base.replace("_"," "),"file":inp["file"],"sha256":inp["sha256"]}
        if base=="Facebook_Targeting_Intelligence": targeting=e
        else: creative.append(e)
    return {"source":"avatar-alchemist-handoff","skill":48,"skill_name":"facebook-ad-generator",
            "purpose":target.get("purpose",""),"creative_source_docs":creative,
            "targeting_intelligence_doc":targeting,
            "show_bio_source":"Top 39 Suggested Ad Angles (from AA brand intelligence)",
            "audience_profile_source":"Facebook Targeting Intelligence (from AA brand intelligence)","client_label":""}

def import_handoff(handoff_path, deliver_dir, out_dir):
    h,hv=_load_handoff(handoff_path)
    if h is None: return None,hv
    t=_find_target(h)
    if t is None: return None,[("AF-IMPORT-NO-TARGET","no target for skill 48")]
    v=_verify_checksums(t,deliver_dir)
    if v: return None,v
    r=_map(t,deliver_dir); r["client_label"]=h.get("client_label","")
    out_dir.mkdir(parents=True,exist_ok=True); cp=[]
    for inp in t.get("inputs",[]):
        src=deliver_dir/inp["file"]; dst=out_dir/inp["file"]
        if src.is_file(): shutil.copy2(src,dst); cp.append(inp["file"])
    r["files_copied"]=cp
    (out_dir/"aa-creative-brief.json").write_text(json.dumps(r,indent=2)+"\n",encoding="utf-8")
    return r,[]

_FIXT={"Top_39_Suggested_Ad_Angles":"# Top 39 Ad Angles\n\nAngle 1: problem-solution.",
       "Facebook_Headline_and_Primary_Text_Ad_Copy_Writer":"# FB Headline & Primary Text\n\nShape A: provocative question.",
       "Facebook_Targeting_Intelligence":"# FB Targeting\n\nLayer 1: core interests."}

def _mk_fixture(tmp, corrupt=False):
    d=tmp/"deliver"; d.mkdir(parents=True,exist_ok=True); label="Test_Client"; files={}
    for base,content in _FIXT.items():
        fn=base+"-"+label+".md"; (d/fn).write_text(content,encoding="utf-8")
        sha=hashlib.sha256(content.encode()).hexdigest()
        if corrupt and base=="Top_39_Suggested_Ad_Angles": sha="0"*64
        files[fn]={"sha256":sha,"words":len(content.split())}
    (d/"MANIFEST.json").write_text(json.dumps({"package":"avatar-alchemist-brand-intelligence",
        "client_label":label,"deliverable_count":len(files),"files":files},indent=2),encoding="utf-8")
    inputs=[{"deliverable":base,"file":base+"-"+label+".md","sha256":files[base+"-"+label+".md"]["sha256"]} for base in REQUIRED_BASES]
    handoff={"handoff":"avatar-alchemist-downstream","skill":"52-avatar-alchemist","client_label":label,
        "targets":[{"skill_number":48,"skill_dir":"48-facebook-ad-generator","skill_name":"facebook-ad-generator",
        "purpose":"Facebook ad generation.","inputs":inputs,"supporting":[]}],"notes":[]}
    hp=d/"HANDOFF.json"; hp.write_text(json.dumps(handoff,indent=2),encoding="utf-8")
    return hp,d

def run_self_test():
    import tempfile; ok=True
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)
        hp,dd=_mk_fixture(tmp); o=tmp/"out"; r,v=import_handoff(hp,dd,o)
        if v or r is None: ok=False; print("FAIL (valid): "+str(v))
        elif len(r.get("creative_source_docs",[]))!=2: ok=False; print("FAIL: creative docs != 2")
        elif r.get("targeting_intelligence_doc") is None: ok=False; print("FAIL: targeting missing")
        elif not (o/"aa-creative-brief.json").is_file(): ok=False; print("FAIL: output missing")
        else: print("48 OK valid: "+str(len(r["files_copied"]))+" files")
        hp2,dd2=_mk_fixture(tmp/"c",corrupt=True); _,v2=import_handoff(hp2,dd2,tmp/"o2")
        if "AF-IMPORT-CHECKSUM-MISMATCH" in {c for c,_ in v2}: print("48 OK corrupt")
        else: ok=False; print("48 FAIL: corrupt not caught")
        hp3=tmp/"nt"/"HANDOFF.json"; hp3.parent.mkdir(parents=True,exist_ok=True)
        hp3.write_text(json.dumps({"handoff":"avatar-alchemist-downstream","skill":"52","client_label":"X",
            "targets":[{"skill_number":999,"skill_name":"nope","inputs":[]}],"notes":[]}),encoding="utf-8")
        _,v3=import_handoff(hp3,hp3.parent,tmp/"o3")
        if "AF-IMPORT-NO-TARGET" in {c for c,_ in v3}: print("48 OK no target")
        else: ok=False; print("48 FAIL: missing target")
        hpa,dda=_mk_fixture(tmp/"da"); import_handoff(hpa,dda,tmp/"oa")
        hpb,ddb=_mk_fixture(tmp/"db"); import_handoff(hpb,ddb,tmp/"ob")
        oa=json.loads((tmp/"oa"/"aa-creative-brief.json").read_text())
        ob=json.loads((tmp/"ob"/"aa-creative-brief.json").read_text())
        for o in (oa,ob): o.pop("files_copied",None)
        if oa==ob: print("48 OK deterministic")
        else: ok=False; print("48 FAIL: non-deterministic")
    print("48 RESULT: "+("PASS" if ok else "FAIL")); return 0 if ok else 1

def main(argv):
    if "--self-test" in argv: return run_self_test()
    ap=argparse.ArgumentParser(description="Import AA handoff into Skill 48.")
    ap.add_argument("--handoff",required=True); ap.add_argument("--deliver-dir",required=True)
    ap.add_argument("--out",required=True); args=ap.parse_args(argv)
    hp=Path(args.handoff); dd=Path(args.deliver_dir); od=Path(args.out)
    if not hp.is_file() or not dd.is_dir(): print("USAGE/IO ERROR"); return 3
    try: _,v=import_handoff(hp,dd,od)
    except Exception as e: print("USAGE/IO ERROR: "+str(e)); return 3
    if v:
        print("FAIL: "+str(len(v))+" violation(s)")
        for c,m in v: print("  VIOLATION ["+c+"] "+m)
        return 2
    print("PASS: creative brief -> "+str(od/"aa-creative-brief.json")); return 0

if __name__=="__main__": sys.exit(main(sys.argv[1:]))
