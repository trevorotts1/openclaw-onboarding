#!/usr/bin/env python3
"""speech_spec_build.py - Converts PRESENTERS-SPEECH.md to speech_spec.json for presenters_speech_pdf.py."""
import argparse, json, sys
from pathlib import Path
try:
    import build_teleprompter as _bt
except ImportError:
    _bt = None
STAGE_LABELS = {"WELCOME":"Welcome & Housekeeping","WHO_FOR":"Who This Is For","CREDIBILITY":"Who I Am","HOOK":"The Hook","BIG_PROMISE":"The One Thing","TEACH":"Teach the Framework","PROOF":"Proof & Case Studies","OFFER":"The Offer & Value Stack","PRICE_DROP":"Price Drop & Anchoring","SCARCITY":"Scarcity & Urgency","RECAP":"Recap","CLOSE":"The Close","QA":"Q&A","UNKNOWN":"Main Content"}
def _load(p, d=None):
    try: return json.loads(Path(p).read_text(encoding="utf-8",errors="replace"))
    except: return d
def build_spec(speech_path, intake_path=None, arc_path=None):
    md = Path(speech_path).read_text(encoding="utf-8",errors="replace")
    if _bt is None: return {}, "build_teleprompter not importable"
    data = _bt.parse_speech(md)
    if not data.get("slides"): return {}, "no slides could be parsed"
    intake = _load(intake_path,{})
    arc = _load(arc_path,{})
    ov={}
    if isinstance(arc,dict):
        for e in arc.get("stages",[]) or arc.get("sections",[]) or []:
            if isinstance(e,dict):
                k=e.get("key")or e.get("stage")or e.get("id",""); l=e.get("label")or e.get("name","")
                if k and l: ov[k.upper()]=l
        fl=arc.get("stage_labels",{})
        if isinstance(fl,dict): ov.update({k.upper():v for k,v in fl.items()})
    def sl(sk):
        k=(sk or "UNKNOWN").upper()
        return ov.get(k) or STAGE_LABELS.get(k,"Main Content")
    dt=data.get("deck_title","Presenter's Speech")
    w=data.get("wpm",130)
    spec={"deck_title":dt,"owner_name":intake.get("owner_name")or intake.get("client_name")or"the presenter","company_name":intake.get("company_name")or intake.get("owner_name")or"the company","duration_min":intake.get("DURATION_MIN")or intake.get("duration_min")or 60,"tone":intake.get("TONE")or intake.get("tone")or"Credible, warm, direct","hook":intake.get("HOOK")or intake.get("hook")or"","spoken_rate_wpm":int(intake.get("SPOKEN_RATE_WPM")or intake.get("spoken_rate_wpm")or w),"brand":intake.get("brand")or{}}
    slides=data["slides"]
    if not slides: return {},"no slides parsed"
    so=[]; ss=set()
    for s in slides:
        sk=(s.get("stage")or"UNKNOWN").upper()
        if sk not in ss: ss.add(sk); so.append(sk)
    sm={sk:{"stage":sk,"label":sl(sk),"slides":[]} for sk in so}
    for idx,s in enumerate(slides):
        sk=(s.get("stage")or"UNKNOWN").upper()
        k=s.get("kind","normal")or"normal"
        if k=="normal":
            if idx==0: k="hook"
            elif idx==len(slides)-1: k="cta"
        sp=[]
        for b in s.get("blocks",[]):
            t=(b.get("text")or"").strip()
            if not t: continue
            if b.get("type")=="cue": sp.append(f"[{t.upper().strip('[]')}]")
            else: sp.append(t)
        spoken = "\n\n".join(sp) if sp else ""
        sm[sk]["slides"].append({"slide_no":s.get("no",idx+1),"headline":s.get("headline",""),"kind":k,"spoken":spoken})
    spec["stages"]=[sm[sk] for sk in so]
    return spec,None
def main():
    ap=argparse.ArgumentParser(description="Build speech_spec.json")
    ap.add_argument("--speech",required=True)
    ap.add_argument("--intake",default=None)
    ap.add_argument("--arc",default=None)
    ap.add_argument("--out",required=True)
    ap.add_argument("--sample",action="store_true")
    args=ap.parse_args()
    if args.sample:
        if _bt is None or not hasattr(_bt,"SAMPLE_SPEECH_MD"): sys.exit("--sample requires build_teleprompter")
        import tempfile; tmp=Path(tempfile.mktemp(suffix=".md")); tmp.write_text(_bt.SAMPLE_SPEECH_MD,encoding="utf-8"); args.speech=str(tmp)
    spec,err=build_spec(args.speech,args.intake,args.arc)
    if err:
        print(f"FATAL: {err}",file=sys.stderr)
        if "no slides" in err:
            print("\nAccepted slide header formats:",file=sys.stderr)
            print("  ## Slide N -- Headline  (STAGE)   canonical",file=sys.stderr)
            print("  [Slide N] Headline                bracket form",file=sys.stderr)
            print("  Slide N: Headline                 bare with colon",file=sys.stderr)
            print("  Slide N -- Headline               bare with dash",file=sys.stderr)
            print("  Slide N                           bare number only",file=sys.stderr)
        sys.exit(2)
    if not spec.get("stages") or sum(len(s.get("slides",[])) for s in spec["stages"])==0:
        print("FATAL: spec has zero slides",file=sys.stderr); sys.exit(2)
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(spec,indent=2),encoding="utf-8")
    print(f"Wrote {len(spec['stages'])} stages, {sum(len(s.get('slides',[])) for s in spec['stages'])} slides to {args.out}")
if __name__=="__main__": main()
