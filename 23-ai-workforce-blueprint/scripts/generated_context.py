"""Refresh generated context without replacing owner-authored content."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from workforce_state import atomic_write, lock

START='<!-- WORKFORCE_INTERVIEW_CONTEXT_V1 -->'
END='<!-- /WORKFORCE_INTERVIEW_CONTEXT_V1 -->'

def refresh_context(path, company_id, answers):
    path=Path(path)
    content = '# Current company and department context\n\n' + '\n'.join(
        '- **' + k.replace('_', ' ') + ':** ' + str(v) for k,v in sorted(answers.items()) if v is not None and v != '')
    rendered=f'{START}\nCompany ID: {company_id}\n{content}\n{END}'
    sidecar=path.with_name(path.name+'.generated-context.json')
    with lock(path):
        old=path.read_text() if path.exists() else ''
        previous=json.loads(sidecar.read_text()) if sidecar.exists() else {}
        match=re.search(re.escape(START)+r'.*?'+re.escape(END),old,re.S)
        if match and hashlib.sha256(match.group().encode()).hexdigest() != previous.get('sha256'):
            raise ValueError('owner-edited generated context needs review: '+str(path))
        new=old[:match.start()]+rendered+old[match.end():] if match else old.rstrip()+'\n\n'+rendered+'\n'
        if new != old:
            # Atomic text replacement with unique same-directory temporary file.
            import os,tempfile
            path.parent.mkdir(parents=True,exist_ok=True)
            fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.'+path.name)
            try:
                with os.fdopen(fd,'w') as f:
                    f.write(new);f.flush();os.fsync(f.fileno())
                os.replace(tmp,path)
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
        atomic_write(sidecar,{'companyId':company_id,'sha256':hashlib.sha256(rendered.encode()).hexdigest(),
                              'answersRevision':hashlib.sha256(json.dumps(answers,sort_keys=True).encode()).hexdigest()})

def write_new(path, text, encoding='utf-8'):
    """Role re-materialization fills missing files; existing owner memory is sacred."""
    path=Path(path)
    if path.exists():
        return False
    path.write_text(text,encoding=encoding)
    return True
