#!/usr/bin/env python3
"""Compile all five Social Planner workflows; never deploy or activate anything.

Required inputs are trusted operator configuration, never webhook payload fields.
Credential maps contain only Google Drive/Sheets reference IDs and names. Output
contains these references and must remain local; output files are created 0600.
Install the four target workflows before switching the two canonical routes to
the compatibility router. Never import the bare canonical router beside existing
workflows that still own those routes. Reconcile ambiguous POST results instead
of retrying append/copy/router requests blindly.
"""
import argparse
import importlib.util
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parent
CORE = BASE.parent
ORIGINAL_BASE = 'https://main.blackceoautomations.com/webhook/'
CORE_PREFIX = 'social-planner/v1.1.0'
CORE_FILES = ('social-planner-sheet-create.json', 'social-planner-row-append.json')
COMPAT_FILES = ('legacy-sheet-create.json', 'legacy-row-append.json', 'compatibility-router.json')


def validate_base(value):
    if not isinstance(value, str) or re.search(r'[\s\\\x00-\x1f\x7f]', value):
        raise ValueError('Provide one explicit HTTPS webhook base without whitespace')
    p = urlsplit(value)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.query or p.fragment or p.path.rstrip('/') != '/webhook'
            or not re.fullmatch(r'[A-Za-z0-9.-]+', p.hostname)):
        raise ValueError('Webhook base must be https://operator-selected-host[:port]/webhook')
    if p.port is not None and not 1 <= p.port <= 65535:
        raise ValueError('Invalid webhook port')
    return value.rstrip('/') + '/'


def build_all(credentials, webhook_base, legacy_template_id):
    base = validate_base(webhook_base)
    if not isinstance(legacy_template_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,160}', legacy_template_id):
        raise ValueError('Provide the operator-verified legacy template spreadsheet ID')
    spec = importlib.util.spec_from_file_location('prepare_social_import', CORE / 'prepare-import.py')
    compiler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compiler)
    outputs = {}
    for filename in CORE_FILES:
        source = json.loads((CORE / filename).read_text())
        outputs[filename] = compiler.build(source, credentials, CORE_PREFIX)
    for filename in COMPAT_FILES:
        source = json.loads((BASE / filename).read_text())
        for node in source['nodes']:
            if filename == 'legacy-sheet-create.json' and node['name'] == 'Copy Legacy Template':
                expected = 'https://www.googleapis.com/drive/v3/files/__LEGACY_TEMPLATE_ID__/copy?fields=id,name,mimeType'
                if node['parameters']['url'] != expected:
                    raise ValueError('Unexpected legacy template URL contract')
                node['parameters']['url'] = expected.replace('__LEGACY_TEMPLATE_ID__', legacy_template_id)
            if filename == 'compatibility-router.json' and node['type'] == 'n8n-nodes-base.httpRequest':
                url = node['parameters']['url']
                if not isinstance(url, str) or not url.startswith(ORIGINAL_BASE):
                    raise ValueError('Router target must be a fixed trusted deployment route')
                suffix = url[len(ORIGINAL_BASE):]
                allowed = {CORE_PREFIX + '/' + x.removesuffix('.json') for x in CORE_FILES}
                allowed |= {'social-planner-compat-20260909/legacy-sheet-create', 'social-planner-compat-20260909/legacy-row-append'}
                if suffix not in allowed:
                    raise ValueError('Unexpected router target path')
                node['parameters']['url'] = base + suffix
        outputs[filename] = compiler.build(source, credentials)
    paths = [n['parameters']['path'] for d in outputs.values() for n in d['nodes'] if n['type'] == 'n8n-nodes-base.webhook']
    if len(paths) != 6 or len(set(paths)) != 6:
        raise ValueError('Deployment must contain six distinct webhook routes')
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials-map', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--webhook-base', required=True)
    parser.add_argument('--legacy-template-id', required=True)
    args = parser.parse_args()
    outputs = build_all(json.loads(args.credentials_map.read_text()), args.webhook_base, args.legacy_template_id)
    args.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any((args.output_dir / f).exists() for f in outputs):
        raise FileExistsError('Output already exists; use a new directory to preserve deployment snapshots')
    for filename, payload in outputs.items():
        fd = os.open(args.output_dir / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(payload, handle, indent=2)
            handle.write('\n')
        print(args.output_dir / filename)


if __name__ == '__main__':
    main()
