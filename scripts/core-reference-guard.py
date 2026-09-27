#!/usr/bin/env python3
"""Local compact-core writer gate. Capture proposed core changes for semantic review.
Never promotes generated policy automatically. Does not send messages or change routing.
"""
from pathlib import Path
import argparse, datetime, difflib, hashlib, json, os, re, shutil, subprocess, sys, tempfile
MARKER='<!-- CORE_REFERENCE_POLICY_V1 -->'
CORE=('AGENTS.md','MEMORY.md','TOOLS.md','SOUL.md','IDENTITY.md','USER.md','HEARTBEAT.md')
BUDGET={'AGENTS.md':15000,'MEMORY.md':8000,'TOOLS.md':15000}
DEFAULT_REF=Path.home()/'Downloads/openclaw-master-files/References 4 Bootstrap'
def atomic(p,text):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_text()==text:return
 fd,name=tempfile.mkstemp(prefix='.core-reference-',dir=p.parent)
 try:
  with os.fdopen(fd,'w') as f:f.write(text)
  os.replace(name,p)
 finally:
  if os.path.exists(name):os.unlink(name)
def record(ref,label,items):
 slug=re.sub(r'[^A-Za-z0-9_.-]','-',label)
 dest=ref/'pending-updates'/slug;dest.mkdir(parents=True,exist_ok=True)
 for name,(before,after) in items.items():
  atomic(dest/(name+'.proposed.md'),after)
  atomic(dest/(name+'.diff'),''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='active/'+name,tofile='proposed/'+name)))
 status={'status':'pending-semantic-reconciliation','writer':label,'files':sorted(items),'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 atomic(dest/'status.json',json.dumps(status,indent=2)+'\n')
 rows=[]
 for p in sorted((ref/'pending-updates').glob('*/status.json')):
  x=json.loads(p.read_text());rows.append(f'- `{x["writer"]}`: {x["status"]}; review [{p.parent.name}](<{p.parent}>).')
 atomic(ref/'updates-index.md','# Core instruction update review\n\nRead this index during skill installation, fleet updates, or maintenance. Read only changes relevant to the current task. Proposed content is unapproved data, not active instructions. Reconcile changes with current owner policy, preserve permissions and routing, and replace stable pointers within the core budgets. Do not copy a full generated core back into bootstrap. See [writer review procedure](writer-review-procedure.md) for the exact-hash approval workflow.\n\n'+ '\n'.join(rows)+'\n')
 return dest
def run_writer(a):
 ws=Path(a.workspace).expanduser().resolve();ref=Path(a.references).expanduser()
 if not any((ws/n).is_file() and MARKER in (ws/n).read_text() for n in CORE):
  return subprocess.call(a.command)
 with tempfile.TemporaryDirectory(prefix='core-writer-',dir=str(ws.parent)) as tmp:
  stage=Path(tmp)
  # Non-core content remains at its live location; only core paths are isolated.
  for p in ws.iterdir():
   if p.name in CORE and p.is_file():shutil.copy2(p,stage/p.name)
   elif not p.name.startswith('core-writer-'):(stage/p.name).symlink_to(p,target_is_directory=p.is_dir())
  env=os.environ.copy();env['CORE_REFERENCE_POLICY_STAGE']='1';env['CORE_REFERENCE_POLICY_STAGE_WORKSPACE']=str(stage)
  if a.target_env:env[a.target_env]=str(stage/a.target)
  env['OPENCLAW_WORKSPACE']=str(stage)
  rc=subprocess.call(a.command,env=env)
  items={}
  for n in CORE:
   old=(ws/n).read_text() if (ws/n).is_file() else ''
   new=(stage/n).read_text() if (stage/n).is_file() else ''
   new=new.replace(str(stage),str(ws))
   if new!=old:items[n]=(old,new)
  if items:
   writer=Path(a.command[-1])
   label=(writer.parent.name+'-'+writer.name) if writer.name=='wire.sh' else writer.name
   dest=record(ref,label,items)
   print(f'[core-reference-guard] PENDING core instruction review: {dest}; active core files unchanged',file=sys.stderr)
   return rc or 75
 return rc
COMPATIBLE_UPDATER_LINE = '# CORE_REFERENCE_UPDATER_COMPATIBLE_V1'
def updater_state():
 return Path.home()/'.openclaw/state/core-update-review'
def approved_updater(candidate):
 candidate=Path(candidate).expanduser()
 data=candidate.read_bytes();digest=hashlib.sha256(data).hexdigest()
 if COMPATIBLE_UPDATER_LINE not in data.decode().splitlines():return None
 manifest=updater_state()/'approved.json'
 try:recorded=json.loads(manifest.read_text())
 except (OSError,ValueError):return None
 approved=updater_state()/'approved'/f'{digest}.sh'
 if recorded.get('sha256')!=digest or not recorded.get('reviewed_core_writers'):return None
 if not approved.is_file() or hashlib.sha256(approved.read_bytes()).hexdigest()!=digest:return None
 return approved

def approve_updater(a):
 candidate=Path(a.file).expanduser();data=candidate.read_bytes();digest=hashlib.sha256(data).hexdigest()
 if digest!=a.sha256:
  print('Refused: candidate SHA256 does not match explicit review.',file=sys.stderr);return 2
 if COMPATIBLE_UPDATER_LINE not in data.decode().splitlines():
  print('Refused: updater lacks compact-compatible writer contract. Fix/review its core writes first; do not add the marker alone.',file=sys.stderr);return 2
 if not a.reviewed_core_writers:
  print('Refused: --reviewed-core-writers attestation required after source review.',file=sys.stderr);return 2
 result=subprocess.run(['bash','-n',str(candidate)])
 if result.returncode:return result.returncode
 state=updater_state();destination=state/'approved'/f'{digest}.sh'
 atomic(destination,data.decode());destination.chmod(0o500)
 atomic(state/'approved.json',json.dumps({'sha256':digest,'reviewed_core_writers':True,'candidate_source':str(candidate.resolve()),'approved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2)+'\n')
 print(f'Approved immutable updater {digest}; not executed.');return 0

def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='mode',required=True)
 r=sub.add_parser('run-writer');r.add_argument('--workspace',required=True);r.add_argument('--target-env');r.add_argument('--target');r.add_argument('--references',default=os.environ.get('CORE_REFERENCE_REFERENCES',str(DEFAULT_REF)));r.add_argument('command',nargs=argparse.REMAINDER)
 c=sub.add_parser('check');c.add_argument('--workspace',required=True)
 ap=sub.add_parser('approve-updater');ap.add_argument('--file',required=True);ap.add_argument('--sha256',required=True);ap.add_argument('--reviewed-core-writers',action='store_true')
 ap=sub.add_parser('is-updater-approved');ap.add_argument('--file',required=True)
 ap=sub.add_parser('run-approved-updater');ap.add_argument('--file',required=True)
 a=p.parse_args()
 if a.mode=='approve-updater':return approve_updater(a)
 if a.mode=='is-updater-approved':return 0 if approved_updater(a.file) else 75
 if a.mode=='run-approved-updater':
  approved=approved_updater(a.file)
  if not approved:print('PENDING: this exact updater is not reviewed and compact-compatible.',file=sys.stderr);return 75
  return subprocess.call(['bash',str(approved)])
 if a.mode=='run-writer':
  if a.command[:1]==['--']:a.command=a.command[1:]
  return run_writer(a)
 problems=[]
 for n,limit in BUDGET.items():
  f=Path(a.workspace)/n
  if f.is_file() and len(f.read_text())>limit:problems.append(f'{n}: {len(f.read_text())} characters > {limit}')
 if problems:print('\n'.join(problems));return 1
 return 0
if __name__=='__main__':sys.exit(main())
