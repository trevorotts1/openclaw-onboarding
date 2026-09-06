#!/usr/bin/env python3
"""Collect first-onboarding names before resources; never infer a business from an owner."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
import uuid
from datetime import datetime, timezone

QUESTIONS = {'ownerName': 'What is the name of the client or owner of this ZHC?',
             'companyName': 'What is the name of the company?'}


def read_object(path):
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Expected an identity object: ' + str(path))
    return value


def name(value):
    if not isinstance(value, str) or not value.strip():
        return ''
    value = value.strip()
    if len(value) > 200 or any(ord(c) < 32 for c in value):
        raise ValueError('Names must be a single line of at most 200 characters')
    return value


def ensure(root, workspace, owner='', company='', interactive=False, slug=''):
    root = Path(root).resolve()
    workspace = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'onboarding-identity.json'
    with open(root / '.onboarding-identity.lock', 'a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        saved = read_object(path)
        state = read_object(workspace / '.workforce-build-state.json')
        established = bool(state.get('companyId') and (state.get('companySlug') or state.get('clientSlug')))
        if saved and saved.get('workspace') != str(workspace):
            raise ValueError('Saved intake belongs to another workspace; refusing adoption')
        if saved and established and saved.get('companySlug') != (state.get('companySlug') or state.get('clientSlug')):
            raise ValueError('Saved intake conflicts with the existing company; refusing replacement')
        for key in ('companyId', 'tenantId', 'installationId'):
            if saved.get(key) and saved[key] != state.get(key):
                raise ValueError(key + ' conflicts with saved intake; refusing identity adoption')
        values = dict(saved)
        # Established workforce identity wins. Updates never create a replacement company.
        if established:
            for key in ('ownerName', 'companyName', 'companyId', 'tenantId', 'installationId'):
                if state.get(key):
                    values[key] = state[key]
            values['companySlug'] = state.get('companySlug') or state['clientSlug']
        if slug:
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
                raise ValueError('Invalid company slug')
            if values.get('companySlug') and values['companySlug'] != slug:
                raise ValueError('Company slug conflicts with saved identity')
            values['companySlug'] = slug
        supplied = {'ownerName': name(owner), 'companyName': name(company)}
        for key, value in supplied.items():
            if value and values.get(key) and value != values[key]:
                raise ValueError(key + ' conflicts with saved identity; use an explicit profile correction instead of replacing it')
            if value:
                values[key] = value
        missing = [key for key in QUESTIONS if not name(values.get(key))]
        # Existing installations keep their identity and are not forced into fresh intake.
        if missing and not established and interactive:
            try:
                terminal = open('/dev/tty', 'r')
            except OSError:
                terminal = None
            if terminal:
                with terminal, open('/dev/tty', 'w') as prompt:
                    for key in missing:
                        while not name(values.get(key)):
                            prompt.write(QUESTIONS[key] + ' ')
                            prompt.flush()
                            answer = terminal.readline()
                            if not answer:
                                raise ValueError('Identity questions were interrupted; onboarding has not started')
                            values[key] = name(answer)
        missing = [key for key in QUESTIONS if not name(values.get(key))]
        if missing and not established:
            return {'status': 'needs-input', 'questions': [QUESTIONS[key] for key in missing]}
        if established and not saved:
            return dict(values, status='existing', workspace=str(workspace))
        if not values.get('companySlug'):
            ascii_name = unicodedata.normalize('NFKD', values['companyName']).encode('ascii', 'ignore').decode().lower()
            generated = re.sub(r'[^a-z0-9]+', '-', ascii_name).strip('-') or 'company-' + uuid.uuid4().hex[:12]
            if len(generated) > 63:
                generated = generated[:50].rstrip('-') + '-' + hashlib.sha256(values['companyName'].encode()).hexdigest()[:12]
            values['companySlug'] = generated
        values.update(schemaVersion=1, workspace=str(workspace))
        values.setdefault('collectedAt', datetime.now(timezone.utc).isoformat())
        if values != saved:
            fd, temporary = tempfile.mkstemp(prefix='.identity-', dir=root)
            try:
                with os.fdopen(fd, 'w') as handle:
                    json.dump(values, handle, ensure_ascii=False, indent=2)
                    handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)
        return dict(values, status='ready' if not established else 'existing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--owner-name', default=os.environ.get('OPENCLAW_OWNER_NAME', ''))
    parser.add_argument('--company-name', default=os.environ.get('OPENCLAW_COMPANY_NAME', ''))
    parser.add_argument('--company-slug', default='')
    parser.add_argument('--interactive', action='store_true')
    args = parser.parse_args()
    try:
        result = ensure(args.root, args.workspace or args.root / 'workspace', args.owner_name, args.company_name, args.interactive, args.company_slug)
        print(json.dumps(result, ensure_ascii=False))
        return 8 if result['status'] == 'needs-input' else 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'pending', 'reason': str(exc)}), file=sys.stderr)
        return 8


if __name__ == '__main__':
    sys.exit(main())
