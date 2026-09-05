#!/usr/bin/env python3
"""Verify the client-owned Command Center identity; never enroll or invent IDs."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'23-ai-workforce-blueprint/scripts'))
from workforce_state import read,update
from datetime import datetime,timezone

def verify(state,env,fetch=None):
    expected={'tenantId':env.get('MC_TENANT_ID'),'companyId':state.get('companyId') or env.get('MC_COMPANY_ID'),
              'installationId':env.get('MC_INSTALLATION_ID')}
    url=env.get('MC_TENANT_PUBLIC_URL') or state.get('commandCenterUrl') or ''
    parsed=urlsplit(url)
    missing=[k for k,v in expected.items() if not isinstance(v,str) or not v.strip()]
    if not env.get('MC_API_TOKEN'):missing.append('MC_API_TOKEN')
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:missing.append('client HTTPS origin')
    if state.get('companyId') and env.get('MC_COMPANY_ID') and state['companyId']!=env['MC_COMPANY_ID']:missing.append('company identity conflict')
    if missing:return {'ready':False,'missing':missing}
    host=parsed.hostname.lower();endpoint='https://'+parsed.netloc+'/api/auth/tenant-ready'
    if env.get('MC_REQUIRE_REMOTE_RECEIVER')=='1':endpoint+='?requireRemoteReceiver=1'
    def network():
        # Do not follow redirects carrying bearer credentials to another origin.
        import urllib.request
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        request=Request(endpoint,headers={'Authorization':'Bearer '+env['MC_API_TOKEN']})
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=15) as response:
            if response.status!=200:raise ValueError('readiness status is not 200')
            return json.loads(response.read(65537))
    try:receipt=fetch() if fetch else network()
    except Exception as exc:return {'ready':False,'missing':['authenticated readiness probe failed: '+type(exc).__name__]}
    for key,value in dict(expected,host=host,kind='self',protocol='interview.v1').items():
        if receipt.get(key)!=value:missing.append(key+' mismatch')
    if receipt.get('ready') is not True or receipt.get('missing')!=[]:missing.append('receiver readiness')
    return dict(expected,host=host,ready=not missing,missing=missing,protocol='interview.v1')

def main():
    path=sys.argv[1];before=read(path);receipt=verify(before,os.environ)
    def record(state):
        if state.get('companyId')!=before.get('companyId') or state.get('buildId')!=before.get('buildId'):
            receipt.update(ready=False,missing=['build identity changed during probe'])
        state['commandCenterTenantReady']=receipt['ready']
        state['commandCenterTenantVerification']=dict(receipt,buildId=state.get('buildId'),checkedAt=datetime.now(timezone.utc).isoformat())
    update(path,record)
    print(json.dumps(receipt))
    return 0 if receipt['ready'] else 1
if __name__=='__main__':raise SystemExit(main())
