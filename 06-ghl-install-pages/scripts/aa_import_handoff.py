#!/usr/bin/env python3
import argparse,hashlib,json,sys
from pathlib import Path
SN=6
REQ=["Landing_Page"]
SUP=[]
PAGE='landing_page'
def _s(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def _l(dd):
 hp=dd/"HANDOFF.json"
 if not hp.is_file():return None,['no handoff']
 try:ho=json.loads(hp.read_text('utf-8'))
 except Exception as e:return None,[f'parse:{e}']
 if ho.get('handoff')!='avatar-alchemist-downstream':return None,['not aa']
 return ho,[]
def _f(ho):
 for t in ho.get("targets",[]):
  if t.get("skill_number")==SN:return t,[]
 return None,[f"no target {SN}"]
def _v(dd,inp):
 es=[]
 for i in inp:
  fn=i.get('file','');xp=i.get('sha256','')
  if not fn:es.append('no file');continue
  if not (dd/fn).is_file():es.append(f'absent {fn}');continue
  a=_s(dd/fn)
  if xp and a!=xp:es.append(f'mismatch {fn}')
 return es
def import_handoff(dd):
 ho,es=_l(dd)
 if ho is None:return None,es
 target,es2=_f(ho)
 if target is None:return None,es2
 iv=list(target.get("inputs",[]))
 ev=_v(dd,iv)
 if ev:return None,ev
 ds=[]
 for i in target.get("inputs",[]):
  fn=i.get('file','')
  ds.append(dict(deliverable=i.get('deliverable',''),file=fn,sha256=i.get('sha256',''),content_path=str(dd/fn) if fn else '',page_mode=PAGE,page_surface='funnel'))
 present={d['deliverable'] for d in ds if d.get('content_path')}
 missing=[r for r in REQ if r not in present]
 if missing:return None,[f'missing:{missing}']
 landing=ds[0];cl=ho.get('client_label','Client').replace('_',' ')
 r=dict(adapter='aa_import_handoff',adapter_skill=SN,client_label=ho.get('client_label',''),purpose=target.get('purpose',''),skill_name=target.get('skill_name',''),verified=True,page_target=PAGE,source_docs=ds,source_handoff_sha256=ho.get('source_manifest_sha256',''),source_certificate_sha256=ho.get('source_certificate_sha256',''))
 r['build_plan']=dict(funnel_name=f'{cl} Landing Page',surface='funnel',pages=[dict(name='Landing Page',path='/landing',payload_path=landing['content_path'],mode='direct',source_deliverable=landing['deliverable'],source_sha256=landing['sha256'])])
 r['notes']=['AA handoff.']
 return r,[]
def _rep(rr,es,op):
 if rr and not es:
  p=json.dumps(rr,indent=2)+chr(10)
  if op:op.parent.mkdir(parents=True,exist_ok=True);op.write_text(p,'utf-8')
  else:sys.stdout.write(p)
  pc=len(rr.get('build_plan',{}).get('pages',[]))
  print(f'PASS:Skill 6 imported - {pc} pages.',file=sys.stderr);return 0
 print(f'FAIL:{len(es)} violations.',file=sys.stderr)
 for m in es:print(f'  VIOLATION [AF-HI-6] {m}',file=sys.stderr)
 return 2
def main(argv):
 ap=argparse.ArgumentParser()
 ap.add_argument('--deliver-dir');ap.add_argument('--out');ap.add_argument('--self-test',action='store_true')
 a=ap.parse_args(argv)
 if a.self_test:return _st()
 if not a.deliver_dir:print('USAGE',file=sys.stderr);return 3
 dd=Path(a.deliver_dir)
 if not dd.is_dir():print(f'IO:{dd}',file=sys.stderr);return 3
 try:rr,es=import_handoff(dd)
 except Exception as e:print(f'IO:{e}',file=sys.stderr);return 3
 return _rep(rr,es,Path(a.out) if a.out else None)
def _st():
 import tempfile;ok=True
 with tempfile.TemporaryDirectory() as td:
  d=Path(td);lab="T"
  fn=f"{REQ[0]}-{lab}.md";open(str(d/fn),"w").write("MOCK\n")
  bd=open(str(d/fn)).read();fsha=hashlib.sha256(bd.encode()).hexdigest()
  ho={"handoff":"avatar-alchemist-downstream","client_label":lab,"targets":[{"skill_number":SN,"inputs":[{"deliverable":REQ[0],"file":fn,"sha256":fsha}]}]}
  open(str(d/"HANDOFF.json"),"w").write(json.dumps(ho,indent=2))
  rr,es=import_handoff(d)
  if es or not rr or not rr.get('verified'):ok=False;print('FAIL:valid')
  elif rr.get('page_target')!=PAGE:ok=False;print('FAIL:page_target')
  else:
   bp=rr.get('build_plan',{});ps=bp.get('pages',[])
   if len(ps)!=1 or ps[0].get('payload_path')!=str(d/fn):ok=False;print('FAIL:plan')
   else:print('SELF-TEST 1/4 PASS')
  open(str(d/fn),'w').write('TAMPER');rr,es=import_handoff(d)
  if rr or not es:ok=False;print('FAIL:tamper')
  else:print('SELF-TEST 2/4 PASS')
  open(str(d/fn),'w').write('MOCK\n')
  (d/'HANDOFF.json').unlink();rr,es=import_handoff(d)
  if rr or not es:ok=False;print('FAIL:missing')
  else:print('SELF-TEST 3/4 PASS')
  ho2=dict(ho);ho2['targets']=[{'skill_number':99}]
  open(str(d/'HANDOFF.json'),'w').write(json.dumps(ho2,indent=2));rr,es=import_handoff(d)
  if rr or not es:ok=False;print('FAIL:notarget')
  else:print('SELF-TEST 4/4 PASS')
 print('SELF-TEST:','PASS' if ok else 'FAIL');return 0 if ok else 1
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
