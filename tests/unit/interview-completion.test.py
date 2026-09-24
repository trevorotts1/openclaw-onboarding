#!/usr/bin/env python3
"""INT-001: canonical declarations suppress repeat prompts without faking builds."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared-utils'))
from interview_completion import prompt_status
from interview_invitation import resolve_public_origin, Pending
spec = importlib.util.spec_from_file_location('nudge', ROOT / 'shared-utils/nudge-incomplete-interviews.py')
nudge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nudge)


class Completion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / 'canonical.db'
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute('''CREATE TABLE interview_prior_completion_declarations (
                tenant_id TEXT,company_id TEXT,installation_id TEXT,declared_by TEXT,
                declared_at TEXT,source TEXT,PRIMARY KEY(tenant_id,company_id,installation_id))''')
        self.state = dict(tenantId='tenant', companyId='company', installationId='installation',
                          companySlug='company', interviewComplete=False,
                          interviewProgress={'lastQuestionAt': '2020-01-01T00:00:00Z'})
        self.env = dict(os.environ, DATABASE_PATH=str(self.db), DASHBOARD_DB_PATH=str(self.db),
                        MC_TENANT_ID='tenant', MC_COMPANY_ID='company', MC_INSTALLATION_ID='installation')
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.statefile = self.workspace / '.workforce-build-state.json'
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        self.statefile.write_text(json.dumps(self.state))

    def declare(self, scope=('tenant', 'company', 'installation')):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute('INSERT INTO interview_prior_completion_declarations VALUES(?,?,?,?,?,?)',
                         (*scope, 'owner', '2026-09-24', 'owner-self-attestation'))

    def test_scoped_read_only_persistence_and_foreign_isolation(self):
        self.assertEqual(prompt_status(self.state, self.env), 'INCOMPLETE')
        self.declare()
        before = self.db.read_bytes()
        self.assertEqual(prompt_status(self.state, self.env), 'DECLARED')
        self.assertEqual(self.db.read_bytes(), before)
        self.assertFalse(self.state['interviewComplete'])
        for key, variable in [('tenantId','MC_TENANT_ID'), ('companyId','MC_COMPANY_ID'), ('installationId','MC_INSTALLATION_ID')]:
            with self.subTest(key=key):
                self.assertEqual(prompt_status(dict(self.state, **{key:'foreign'}), self.env), 'UNKNOWN')
                self.assertEqual(prompt_status(dict(self.state, **{key:'foreign'}), dict(self.env, **{variable:'foreign'})), 'INCOMPLETE')

    def test_legacy_trusted_self_registry_resolves_without_tenant_pin(self):
        registration = dict(kind='self', tenantId='tenant', companyId='company', installationId='installation')
        legacy = dict(MC_COMPANY_ID='company', MC_INSTALLATION_ID='installation',
                      MC_TENANT_REGISTRY_JSON=json.dumps({'client.example.com':registration}),
                      DATABASE_PATH=str(self.db), MC_API_TOKEN='fixture-token')
        self.assertNotIn('MC_TENANT_ID', legacy)
        self.assertNotIn('launchBootstrap', self.state)
        self.assertEqual(prompt_status(self.state, legacy), 'INCOMPLETE')
        state = dict(self.state, commandCenterUrl='https://client.example.com')
        receipt = dict(tenantId='tenant', companyId='company', installationId='installation',
                       host='client.example.com', protocol='interview-launch.v1', stage='interview',
                       ready=True, missing=[], interviewComplete=False,
                       capabilities=dict(state=True, localInterviewPrerequisites=True, enrollment=True))
        resolved = resolve_public_origin(state, legacy, fetch=lambda *_: receipt)
        self.assertEqual(resolved['tenantId'], 'tenant')
        self.declare()
        before = self.db.read_bytes()
        self.assertEqual(prompt_status(self.state, legacy), 'DECLARED')
        with self.assertRaises(Pending):
            resolve_public_origin(state, legacy, fetch=lambda *_: self.fail('declared owner must not be invited'))
        self.assertEqual(self.db.read_bytes(), before)
        self.assertFalse(self.state['interviewComplete'])
        # Multiple host aliases are safe only when they identify the same tenant.
        aliases = {'client.example.com':registration, 'alias.example.com':registration}
        self.assertEqual(prompt_status(self.state, dict(legacy, MC_TENANT_REGISTRY_JSON=json.dumps(aliases))), 'DECLARED')
        bad_registries = ['{', '[]', '{}', json.dumps({'host':None}),
                          json.dumps({'host':dict(registration, kind='client')}),
                          json.dumps({'host':dict(registration, companyId='foreign')}),
                          json.dumps({'host':dict(registration, installationId='foreign')}),
                          json.dumps({'host':dict(registration, tenantId='foreign')}),
                          json.dumps({'host':dict(registration, tenantId='')}),
                          json.dumps({'one':registration, 'two':dict(registration, tenantId='another')})]
        for registry in bad_registries:
            with self.subTest(registry=registry):
                self.assertEqual(prompt_status(self.state, dict(legacy, MC_TENANT_REGISTRY_JSON=registry)), 'UNKNOWN')
        for pin in ['', 'foreign']:
            self.assertEqual(prompt_status(self.state, dict(legacy, MC_TENANT_ID=pin)), 'UNKNOWN')
        for key in ['tenantId', 'companyId', 'installationId']:
            self.assertEqual(prompt_status(dict(self.state, **{key:'foreign'}), legacy), 'UNKNOWN')

    def test_unpinned_decoys_and_unreadable_explicit_pin_never_select_another_database(self):
        home = self.root / 'home'
        decoy = home / 'data/mission-control.db'
        canonical = home / 'projects/command-center/mission-control.db'
        for database in [decoy, canonical]:
            database.parent.mkdir(parents=True, exist_ok=True)
            database.write_bytes(self.db.read_bytes())
        unpinned = {key: value for key, value in self.env.items() if key not in ('DATABASE_PATH', 'DASHBOARD_DB_PATH')}
        unpinned['HOME'] = str(home)
        for declared_database in [decoy, canonical]:
            for database in [decoy, canonical]:
                with closing(sqlite3.connect(database)) as connection, connection:
                    connection.execute('DELETE FROM interview_prior_completion_declarations')
                    if database == declared_database:
                        connection.execute('INSERT INTO interview_prior_completion_declarations VALUES(?,?,?,?,?,?)',
                                           ('tenant','company','installation','owner','2026-09-24','owner-self-attestation'))
            with patch.dict(os.environ, unpinned, clear=True):
                self.assertEqual(prompt_status(self.state), 'UNKNOWN')
            self.assertEqual(prompt_status(self.state, dict(unpinned, DATABASE_PATH=str(canonical))),
                             'DECLARED' if declared_database == canonical else 'INCOMPLETE')
        missing = home / 'missing.db'
        self.assertEqual(prompt_status(self.state, dict(unpinned, DATABASE_PATH=str(missing))), 'UNKNOWN')
        self.assertFalse(missing.exists())
        with patch('interview_completion.sqlite3.connect', side_effect=sqlite3.OperationalError('read denied')):
            self.assertEqual(prompt_status(self.state, dict(unpinned, DATABASE_PATH=str(canonical))), 'UNKNOWN')
        self.assertEqual(prompt_status(self.state, dict(unpinned, DATABASE_PATH=str(canonical), DASHBOARD_DB_PATH=str(decoy))), 'UNKNOWN')

    def test_installed_service_default_database_ignores_decoys_and_rejects_conflicts(self):
        home = self.root / 'service-home'
        app = home / 'projects/command-center'
        app.mkdir(parents=True)
        (app / 'package.json').write_text(json.dumps({'name':'mission-control'}))
        registry = {'client.example.com': dict(kind='self',tenantId='tenant',companyId='company',installationId='installation')}
        config = {'MC_COMPANY_ID':'company','MC_INSTALLATION_ID':'installation','MC_TENANT_REGISTRY_JSON':json.dumps(registry)}
        service = app / '.env.local'
        service.write_text('\n'.join(k+'='+json.dumps(v) for k,v in config.items()))
        manager = home / '.pm2'
        manager.mkdir()
        dump = manager / 'dump.pm2'
        process = {'name':'blackceo-command-center','pm_cwd':str(app),'env':{}}
        dump.write_text(json.dumps([process]))
        canonical = app / 'mission-control.db'
        decoy = home / 'data/mission-control.db'
        decoy.parent.mkdir()
        for database in (canonical, decoy):
            database.write_bytes(self.db.read_bytes())
        env = {'HOME':str(home), **config}
        for declared_database in (decoy, canonical):
            for database in (canonical, decoy):
                with closing(sqlite3.connect(database)) as connection, connection:
                    connection.execute('DELETE FROM interview_prior_completion_declarations')
                    if database == declared_database:
                        connection.execute('INSERT INTO interview_prior_completion_declarations VALUES(?,?,?,?,?,?)',
                                           ('tenant','company','installation','owner','2026-09-24','owner-self-attestation'))
            expected = 'DECLARED' if declared_database == canonical else 'INCOMPLETE'
            self.assertEqual(prompt_status(self.state, env), expected)
            self.assertEqual(prompt_status(self.state, dict(env, CC_APP_DIR=str(app))), expected)
            state = dict(self.state, commandCenterUrl='https://client.example.com')
            invitation_env = dict(env, MC_API_TOKEN='fixture-token')
            receipt = dict(tenantId='tenant', companyId='company', installationId='installation',
                           host='client.example.com', protocol='interview-launch.v1', stage='interview',
                           ready=True, missing=[], interviewComplete=False,
                           capabilities=dict(state=True, localInterviewPrerequisites=True, enrollment=True))
            if expected == 'INCOMPLETE':
                self.assertEqual(resolve_public_origin(state, invitation_env, fetch=lambda *_: receipt)['tenantId'], 'tenant')
            else:
                with self.assertRaises(Pending):
                    resolve_public_origin(state, invitation_env, fetch=lambda *_: self.fail('must not invite'))
        dump.write_text(json.dumps([process, dict(process, name='mission-control')]))
        self.assertEqual(prompt_status(self.state, env), 'UNKNOWN')
        dump.write_text(json.dumps([dict(process, env={'MC_COMPANY_ID':'foreign'})]))
        self.assertEqual(prompt_status(self.state, env), 'UNKNOWN')
        dump.write_text(json.dumps([dict(process, env={'DATABASE_PATH':str(decoy)})]))
        service.write_text(service.read_text()+'\nDATABASE_PATH='+json.dumps(str(canonical)))
        self.assertEqual(prompt_status(self.state, env), 'UNKNOWN')
        dump.write_text(json.dumps([process]))
        self.assertEqual(prompt_status(self.state, env), 'DECLARED')
        canonical.unlink()
        self.assertEqual(prompt_status(self.state, env), 'UNKNOWN')
        self.assertFalse(canonical.exists())
        dump.write_text('{')
        self.assertEqual(prompt_status(self.state, env), 'UNKNOWN')
        dump.unlink()
        self.assertEqual(prompt_status(self.state, env), 'UNKNOWN')
        self.assertEqual(prompt_status(self.state, dict(env, CC_APP_DIR=str(home/'absent'))), 'UNKNOWN')
        with patch.object(Path, 'read_text', side_effect=PermissionError('service unreadable')):
            self.assertEqual(prompt_status(self.state, dict(env, CC_APP_DIR=str(app))), 'UNKNOWN')

    def test_missing_corrupt_unreadable_and_unmigrated_stores_are_unknown(self):
        missing = self.root / 'missing.db'
        env = dict(self.env, DATABASE_PATH=str(missing), DASHBOARD_DB_PATH=str(missing))
        self.assertEqual(prompt_status(self.state, env), 'UNKNOWN')
        self.assertFalse(missing.exists())
        with patch('interview_completion.sqlite3.connect', side_effect=sqlite3.OperationalError('read denied')):
            self.assertEqual(prompt_status(self.state, self.env), 'UNKNOWN')
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute('DROP TABLE interview_prior_completion_declarations')
        self.assertEqual(prompt_status(self.state, self.env), 'UNKNOWN')
        self.db.write_bytes(b'not sqlite')
        self.assertEqual(prompt_status(self.state, self.env), 'UNKNOWN')

    def test_pinned_service_identity_and_terminal_legacy_preserved(self):
        self.declare()
        service = self.root / '.env.local'
        service.write_text('\n'.join(k+'='+json.dumps(v) for k,v in self.env.items() if k in ['DATABASE_PATH','DASHBOARD_DB_PATH','MC_TENANT_ID','MC_COMPANY_ID','MC_INSTALLATION_ID']))
        self.state['launchBootstrap'] = {'serviceEnvPath': str(service)}
        self.assertEqual(prompt_status(self.state, {}), 'DECLARED')
        self.assertEqual(prompt_status(self.state, {'MC_COMPANY_ID':'foreign'}), 'UNKNOWN')
        with patch.object(Path, 'read_text', side_effect=PermissionError('read denied')):
            self.assertEqual(prompt_status(self.state, {}), 'UNKNOWN')
        for flags in [{'interviewComplete':True}, {'interview_complete':True}, {'buildCompletedAt':'2026-06-20T12:00:44Z'}]:
            self.assertEqual(prompt_status(dict(self.state, **flags), {}), 'COMPLETE')
        self.assertTrue(nudge.merge_meta_from_state({'complete':True}, {'interviewComplete':False})['complete'])
        self.assertFalse(nudge.merge_meta_from_state({}, {'interviewComplete':'false'})['complete'])

    def test_worker_and_invitation_never_send_for_declared_or_unknown(self):
        company_root = self.root / 'companies'
        (company_root / 'company').mkdir(parents=True)
        paths = {'workspace':self.workspace, 'company_root':company_root}
        for declared in [True, False]:
            if declared:
                self.declare()
            else:
                self.db.unlink()
            with self.subTest(declared=declared), patch.dict(os.environ, self.env, clear=True), patch.object(nudge, 'get_openclaw_paths', return_value=paths), patch.object(nudge, 'send_telegram_nudge', side_effect=AssertionError('must not send')):
                self.assertEqual(nudge.scan_and_nudge()['nudged'], 0)
                with self.assertRaises(Pending):
                    resolve_public_origin(self.state, self.env, fetch=lambda *_: self.fail('must not fetch invitation'))

    def test_shell_selectors_stop_before_owner_resolution_or_worker(self):
        self.declare()
        home = self.root / 'home'
        home.mkdir()
        env = dict(self.env, HOME=str(home), OC_ROOT=str(self.root), OPENCLAW_ROOT=str(self.root),
                   OPENCLAW_WORKSPACE_ROOT=str(self.workspace), OPENCLAW_WORKSPACE_PATH=str(self.workspace))
        scripts = ROOT / '23-ai-workforce-blueprint/scripts'
        for declared in [True, False]:
            if not declared:
                self.db.unlink()
            sent = subprocess.run(['bash',str(scripts/'send-interview-link.sh'),'--dry-run'],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(sent.returncode, 3 if declared else 8, sent.stderr)
            cron = subprocess.run(['bash',str(scripts/'interview-nudge-cron.sh')],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(cron.returncode,0,cron.stderr)
            self.assertIn('status='+('DECLARED' if declared else 'UNKNOWN'), (self.workspace/'.interview-nudge.log').read_text())
        self.assertFalse(json.loads(self.statefile.read_text())['interviewComplete'])


if __name__ == '__main__':
    unittest.main()
