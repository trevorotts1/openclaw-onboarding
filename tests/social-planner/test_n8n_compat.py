"""Portable compatibility compiler and actual n8n graph regression coverage.

No credentials or network are needed. Install the pinned expression parser with
npm ci in fixtures/n8n-expression-parser before running these tests.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPAT = ROOT / '35-social-media-planner/config/n8n/compat'
FIXTURES = Path(__file__).parent / 'fixtures'
PARSER = FIXTURES / 'n8n-expression-parser/node_modules/@n8n/tournament'
REFS = {kind: {'id': 'fixture_' + label, 'name': 'Fixture ' + label}
        for kind, label in [('googleDriveOAuth2Api', 'drive'), ('googleSheetsOAuth2Api', 'sheets')]}
spec = importlib.util.spec_from_file_location('compat_import', COMPAT / 'prepare-compat-import.py')
compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)


def run_node(fixture, *args):
    result = subprocess.run(['node', str(FIXTURES / fixture), str(PARSER), *map(str, args)],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise AssertionError(result.stdout + '\n' + result.stderr)
    return json.loads(result.stdout.strip().splitlines()[-1])


class CompatibilityTests(unittest.TestCase):
    def test_actual_append_graph_public_capability_and_header_regressions(self):
        outputs = compiler.build_all(REFS, 'https://fixture-n8n.example.invalid/webhook', 'fixture_template_123')
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / 'bound.json'
            payload.write_text(json.dumps(outputs['legacy-row-append.json']))
            result = run_node('legacy_append_graph.cjs', COMPAT / 'legacy-row-append.json', payload)
        self.assertEqual(result['tests'], 18)
        self.assertEqual(result['expressions'], 9)
        self.assertEqual(result['liveCalls'], 0)

    def test_actual_router_and_creator_graphs(self):
        result = run_node('compatibility_graph.cjs', COMPAT)
        self.assertGreaterEqual(result['tests'], 16)
        self.assertGreater(result['expressions'], 20)
        self.assertEqual(result['liveCalls'], 0)

    def test_compiler_binds_all_five_with_distinct_routes(self):
        outputs = compiler.build_all(REFS, 'https://fixture-n8n.example.invalid/webhook', 'fixture_template_123')
        self.assertEqual(len(outputs), 5)
        paths = []
        for filename, workflow in outputs.items():
            self.assertEqual(set(workflow), {'name', 'nodes', 'connections', 'settings'})
            for node in workflow['nodes']:
                if node['type'].endswith('.webhook'):
                    paths.append(node['parameters']['path'])
                kind = node['parameters'].get('nodeCredentialType')
                if node['type'] == 'n8n-nodes-base.googleDrive':
                    kind = 'googleDriveOAuth2Api'
                if kind:
                    self.assertEqual(node['credentials'], {kind: REFS[kind]})
            if filename == 'compatibility-router.json':
                for node in workflow['nodes']:
                    if node['type'].endswith('.httpRequest'):
                        self.assertTrue(node['parameters']['url'].startswith('https://fixture-n8n.example.invalid/webhook/'))
            if filename == 'legacy-sheet-create.json':
                copy = next(n for n in workflow['nodes'] if n['name'] == 'Copy Legacy Template')
                self.assertIn('/fixture_template_123/copy', copy['parameters']['url'])
        self.assertEqual(set(paths), {
            'social-planner-sheet-create', 'social-planner-row-append',
            'social-planner/v1.1.0/social-planner-sheet-create',
            'social-planner/v1.1.0/social-planner-row-append',
            'social-planner-compat-20260909/legacy-sheet-create',
            'social-planner-compat-20260909/legacy-row-append'})

    def test_untrusted_or_missing_operator_configuration_refused(self):
        for base in ['http://n8n.example/webhook', 'https://user:pass@n8n.example/webhook',
                     'https://n8n.example/webhook?url=evil', 'https://n8n.example/webhook#fragment',
                     'https://n8n.example/other', 'https://n8n.example/webhook\n',
                     'https://n8n.example:99999/webhook', '//n8n.example/webhook']:
            with self.subTest(base=base), self.assertRaises(ValueError):
                compiler.build_all(REFS, base, 'fixture_template_123')
        for template in ['', 'https://docs.google.com/spreadsheets/d/fixture', '../fixture_template', 'fixture?other=1']:
            with self.subTest(template=template), self.assertRaises(ValueError):
                compiler.build_all(REFS, 'https://n8n.example/webhook', template)
        with self.assertRaises(ValueError):
            compiler.build_all({}, 'https://n8n.example/webhook', 'fixture_template_123')

    def test_canonical_exports_have_no_credential_refs_or_live_template_id(self):
        for filename in compiler.COMPAT_FILES:
            data = json.loads((COMPAT / filename).read_text())
            self.assertEqual(set(data), {'name', 'nodes', 'connections', 'settings'})
            self.assertTrue(all('credentials' not in node for node in data['nodes']))
            self.assertEqual(data['settings']['saveDataSuccessExecution'], 'all')
            self.assertEqual(data['settings']['saveDataErrorExecution'], 'all')
        creator = json.loads((COMPAT / 'legacy-sheet-create.json').read_text())
        copy = next(n for n in creator['nodes'] if n['name'] == 'Copy Legacy Template')
        self.assertEqual(copy['parameters']['url'], 'https://www.googleapis.com/drive/v3/files/__LEGACY_TEMPLATE_ID__/copy?fields=id,name,mimeType')

    def test_cli_uses_private_new_snapshots_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            refs = tmp / 'fixture-refs.json'
            refs.write_text(json.dumps(REFS))
            command = ['python3', str(COMPAT / 'prepare-compat-import.py'), '--credentials-map', str(refs),
                       '--output-dir', str(tmp / 'output'), '--webhook-base', 'https://fixture.example.invalid/webhook',
                       '--legacy-template-id', 'fixture_template_123']
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            files = list((tmp / 'output').glob('*.json'))
            self.assertEqual(len(files), 5)
            for file in files:
                self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            before = {file.name: file.read_bytes() for file in files}
            again = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(before, {file.name: file.read_bytes() for file in files})


if __name__ == '__main__':
    unittest.main()
