#!/usr/bin/env python3
"""Compile readable create-node sources into the credential-free n8n export."""
import argparse,json
from pathlib import Path
base=Path(__file__).resolve().parent
p=base/'social-planner-sheet-create.json'
d=json.loads(p.read_text())
schema=json.loads((base.parent/'sheet-template.schema.json').read_text())
schema={'tabs':{t:{k:v for k,v in d.items() if k in ('headings','frozen_columns','status_columns')} for t,d in schema['tabs'].items() if d.get('headings')},'status_colors':schema['status_colors']}
mapping={'Validate + Build Provisioning Key':'create-validate.js','Interpret Readback':'create-readback.js','Sheet Context':'create-context.js','Build Formatting Requests (F25)':'create-format.js','Provision This Week View (F25)':'create-this-week.js'}
for node in d['nodes']:
    if node['name'] in mapping:
        source=(base/'code'/mapping[node['name']]).read_text()
        if mapping[node['name']]=='create-format.js':
            source='const SCHEMA='+json.dumps(schema,separators=(',',':'))+';\n'+source
        node['parameters']['jsCode']=source
result=json.dumps(d,indent=2)+'\n'
a=argparse.ArgumentParser();a.add_argument('--check',action='store_true');args=a.parse_args()
if args.check:
    if p.read_text()!=result: raise SystemExit('Export Code nodes are stale; run sync-create-code.py')
else:p.write_text(result)
