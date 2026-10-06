#!/usr/bin/env python3
"""Build API-ready payloads from verified exports without modifying the sources.
Credentials map contains n8n credential REFERENCES (id/name), never secret values.
Output is deliberately local-only; do not commit it.
"""
import argparse,copy,importlib.util,json,os,subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent
ALLOWED={'name','nodes','connections','settings'}
def build(source,credentials,webhook_prefix=None):
    if set(credentials)-{'googleDriveOAuth2Api','googleSheetsOAuth2Api'}:
        raise ValueError('Only Drive/Sheets credential references are accepted')
    result={key:copy.deepcopy(source[key]) for key in ALLOWED}
    for node in result['nodes']:
        typ=node['parameters'].get('nodeCredentialType')
        if node['type']=='n8n-nodes-base.googleDrive':typ='googleDriveOAuth2Api'
        if typ:
            ref=credentials.get(typ)
            if not isinstance(ref,dict) or set(ref)!={'id','name'} or not all(isinstance(v,str) and v.strip() for v in ref.values()):
                raise ValueError('Missing valid credential reference: '+typ)
            node['credentials']={typ:ref}
        if webhook_prefix and node['type']=='n8n-nodes-base.webhook':
            node['parameters']['path']=webhook_prefix.strip('/')+'/'+node['parameters']['path']
    return result
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--credentials-map',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--webhook-prefix');a=p.parse_args()
    subprocess.run(['python3',str(BASE/'verify-exports.py')],check=True)
    subprocess.run(['python3',str(BASE/'sync-create-code.py'),'--check'],check=True)
    creds=json.loads(a.credentials_map.read_text())
    outputs=[]
    for filename in ['social-planner-sheet-create.json','social-planner-row-append.json']:
        data=build(json.loads((BASE/filename).read_text()),creds,a.webhook_prefix)
        outputs.append((filename,json.dumps(data,indent=2)+'\n'))
    a.output_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
    for filename,data in outputs:
        dest=a.output_dir/filename
        # O_EXCL prevents silently overwriting an earlier deployment snapshot.
        fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(data)
        print(dest)
if __name__=='__main__':main()
