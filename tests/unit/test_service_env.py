#!/usr/bin/env python3
"""Literal service-env regression; all values and process environments are fixtures."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('service_env', ROOT / 'shared-utils/service_env.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
CC = Path(os.environ.get('SERVICE_ENV_TEST_CC_ROOT', '/private/tmp/codex-cc-portable-20260906'))
NEXT_ENV = CC / 'node_modules/@next/env'


class LiteralServiceEnvironment(unittest.TestCase):
    def test_scalar_roundtrip_and_read_comments(self):
        values = ['', 'ordinary', ' spaced ', 'cash$HOME#tag', r'back\$HOME',
                  r'two\\$HOME', '${EXPAND_ME:-oops}', 'quote"here', "apostrophe's",
                  "apostrophe' and backtick`", r'literal\n\t', 'ending\\', 'unicode Ω']
        for value in values:
            with self.subTest(case=values.index(value)):
                self.assertEqual(m.decode_value(m.encode_value(value)), value)
        self.assertEqual(m.decode_value("' value # hash ' # comment"), ' value # hash ')
        self.assertEqual(m.decode_value('plain # comment'), 'plain')
        self.assertEqual(m.decode_value('$(touch /tmp/fixture-never-execute)'), '$(touch /tmp/fixture-never-execute)')
        self.assertEqual(m.decode_value(r'"literal\t"'), r'literal\t')

    def test_structured_roundtrip_and_legacy_repair(self):
        record = {'client.example': {'companyRoot': "/tmp/owner's $HOME/#work`/\"quoted\"",
                                    'companyId': 'fixture-Ω', 'lines': 'one\ntwo\u2028three'}}
        original = json.dumps(record)
        legacy = json.dumps(original)
        self.assertEqual(json.loads(m.decode_value(legacy, structured=True)), record)
        assignment = m.encode_assignment('MC_PERSONA_COMPANY_CONTEXTS_JSON', original)
        self.assertEqual(json.loads(m.decode_value(assignment.split('=', 1)[1])), record)
        self.assertNotIn('$', assignment)
        self.assertNotIn('#', assignment)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env.local'
            path.write_text('MC_PERSONA_COMPANY_CONTEXTS_JSON=' + legacy + '\n')
            repaired = m.read_env(path)
            path.write_text(m.encode_assignment('MC_PERSONA_COMPANY_CONTEXTS_JSON', repaired['MC_PERSONA_COMPANY_CONTEXTS_JSON']))
            self.assertEqual(json.loads(m.read_env(path)['MC_PERSONA_COMPANY_CONTEXTS_JSON']), record)

    def test_refuses_ambiguous_or_multiline_input_without_echoing_values(self):
        secret = 'synthetic-private-marker'
        bad = [secret + '#trailing\\', secret + "'\"`#", secret + '\nNEW=value', secret + '\0',
               secret + '\u2028NEW=value', secret + '\x85NEW=value']
        for value in bad:
            with self.subTest(case=bad.index(value)):
                with self.assertRaises(ValueError) as error:
                    m.encode_value(value)
                self.assertNotIn(secret, str(error.exception))
        for raw in ['$HOME', '${HOME}', '"unterminated', '"valid" trailing']:
            with self.assertRaises(ValueError):
                m.decode_value(raw)
        for key in ['BAD-KEY', 'export KEY', '9KEY', 'UNICODE_Ω', 'A\nB']:
            with self.assertRaises(ValueError):
                m.encode_assignment(key, 'value')
        for raw in ['null', '"json scalar"', '{"x":NaN}', 'not json']:
            with self.assertRaises(ValueError):
                m.encode_value(raw, structured=True)

    def test_duplicate_conflicts_and_unicode_lines_are_not_silently_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env.local'
            path.write_text("MC_COMPANY_ID='own'\nMC_COMPANY_ID='foreign'\n")
            with self.assertRaises(ValueError):
                m.read_env(path)
            path.write_text("ROOT='safe\u2028INJECTED=value'\n")
            with self.assertRaises(ValueError):
                m.read_env(path)
            path.write_text("# comment\nMC_COMPANY_ID='own'\r\nMC_COMPANY_ID='own'\n")
            self.assertEqual(m.read_env(path), {'MC_COMPANY_ID': 'own'})


@unittest.skipUnless(shutil.which('node') and NEXT_ENV.is_dir(),
                     'Actual Next loader requires SERVICE_ENV_TEST_CC_ROOT with installed @next/env')
class ActualNextAndProcessManager(unittest.TestCase):
    def test_next_loader_and_pm2_config_preserve_literals_and_json(self):
        scalar = {'MC_API_TOKEN': "fixture$EXPAND_ME#token's\"quote", 'MC_TENANT_SESSION_SECRET': r'fixture\${EXPAND_ME}',
                  'DATABASE_PATH': "/tmp/fixture's $EXPAND_ME/#data/mission-control.db",
                  'OPENCLAW_ROOT': 'backtick`with\"quote', 'UNICODE_VALUE': 'fixture Ω',
                  'DOUBLE_DELIMITER': "apostrophe' and backtick` and $EXPAND_ME", 'LITERAL_SLASHES': r'\n\t\$EXPAND_ME', 'ENDING_SLASH': 'fixture\\', 'NEXT_NEIGHBOR': '#preserved'}
        objects = {'MC_TENANT_REGISTRY_JSON': {'client.example': {'kind': 'self', 'companyId': 'company-Ω',
                   'tenantId': "tenant'$EXPAND_ME#`", 'installationId': 'installation"one'}},
                   'MC_PERSONA_COMPANY_CONTEXTS_JSON': {'company-Ω': {'companyRoot': scalar['DATABASE_PATH'],
                   'companyConfig': '/tmp/"quoted"/config.json', 'personaCatalog': '/tmp/catalog\nwith\u2028separator'}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            values = {**scalar, **{key: json.dumps(value) for key, value in objects.items()}}
            (path / '.env.local').write_text('\n'.join(m.encode_assignment(key, value) for key, value in values.items()))
            decoded = m.read_env(path / '.env.local')
            clean_env = {'PATH': os.environ.get('PATH', ''), 'EXPAND_ME': 'MUST_NOT_REPLACE', 'NODE_ENV': 'production'}
            program = r'''
const { loadEnvConfig } = require(process.argv[1]);
const result = loadEnvConfig(process.argv[2], false, { info() {}, error() { throw new Error('fixture env load failed'); } });
const keys = JSON.parse(process.argv[3]);
process.stdout.write(JSON.stringify(Object.fromEntries(keys.map(k => [k, result.combinedEnv[k]]))));
'''
            keys = list(values)
            actual = json.loads(subprocess.check_output(['node', '-e', program, str(NEXT_ENV), directory, json.dumps(keys)], env=clean_env, text=True))
            for key, value in scalar.items():
                self.assertEqual(actual[key], value, key)
                self.assertEqual(decoded[key], value, key)
            for key, value in objects.items():
                self.assertEqual(json.loads(actual[key]), value, key)
                self.assertEqual(json.loads(decoded[key]), value, key)
            # Exercise the real PM2 ecosystem configuration without starting PM2
            # or touching a database. Inherited values plus its env object are
            # exactly the child environment presented to Next at startup.
            pm2_program = r'''
const config = require(process.argv[1]);
Object.assign(process.env, config.apps[0].env);
require(process.argv[5]).prepareNextEnvironment(process.argv[3]);
require(process.argv[5]).prepareNextEnvironment(process.argv[3]); // Idempotent within this process.
const { loadEnvConfig } = require(process.argv[2]);
loadEnvConfig(process.argv[3], false);
const keys = JSON.parse(process.argv[4]);
process.stdout.write(JSON.stringify(Object.fromEntries(keys.map(k => [k, process.env[k]]))));
'''
            pm2_env = {**clean_env, **decoded, 'CC_INSTALL_DIR': directory}
            actual_pm2 = json.loads(subprocess.check_output(['node', '-e', pm2_program, str(CC / 'ecosystem.config.cjs'),
                str(NEXT_ENV), directory, json.dumps(keys), str(CC / 'scripts/next-service-env.cjs')], env=pm2_env, text=True))
            for key in keys:
                self.assertEqual(actual_pm2[key], decoded[key], key)


if __name__ == '__main__':
    unittest.main()
