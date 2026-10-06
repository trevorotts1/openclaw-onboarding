#!/usr/bin/env python3
"""Actual inspection/initialization and shell preflight/database-boundary recovery."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('launch',ROOT/'32-command-center-setup/scripts/interview-launch.py')
launch=importlib.util.module_from_spec(spec);spec.loader.exec_module(launch)


class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.state=self.root/'workspace/.workforce-build-state.json'
        self.state.parent.mkdir();self.app=self.root/'cc';self.app.mkdir()
        self.source=(ROOT/'32-command-center-setup/scripts/run-full-install.sh').read_text()

    def initialize(self):
        launch.initialize(self.state,'fixture-company','Fixture Company','owner@example.test',{})

    def test_failure_only_state_resumes_without_deletion(self):
        self.state.write_text(json.dumps(dict(commandCenterStatus='failed',commandCenterFailureReason='migration failed',stateRevision=2)))
        self.assertTrue(launch.inspect_installation(self.state,self.app)['requiresInitialization'])
        self.initialize();one=json.loads(self.state.read_text());self.initialize();two=json.loads(self.state.read_text())
        for k in ('companyId','tenantId','installationId','buildId'):self.assertEqual(one[k],two[k])
        self.assertEqual(two['commandCenterFailureReason'],'migration failed')
        self.assertEqual(two['buildType'],'standard-first')
        self.assertFalse(two['interviewComplete'])

    def test_unknown_or_answer_bearing_state_never_fresh(self):
        for extra in ({'answers':{}},{'companyId':'existing'},{'otherOwner':'foreign'},{'interviewComplete':True}):
            value=dict(commandCenterStatus='failed',stateRevision=1,**extra)
            self.assertFalse(launch.is_uninitialized(value))
            if 'companyId' not in extra:
                self.state.write_text(json.dumps(value));before=self.state.read_bytes()
                with self.assertRaises(ValueError):self.initialize()
                self.assertEqual(self.state.read_bytes(),before)

    def test_existing_database_cannot_be_adopted_by_fresh_state(self):
        with sqlite3.connect(self.app/'mission-control.db') as db:
            db.execute('CREATE TABLE companies(id TEXT)');db.execute("INSERT INTO companies VALUES('foreign')")
        with self.assertRaises(ValueError):launch.inspect_installation(self.state,self.app)
        self.assertFalse(self.state.exists())

    def test_existing_completed_identity_stays_update(self):
        self.initialize();state=json.loads(self.state.read_text());state['interviewComplete']=True;state['answers']={'1':'saved'};self.state.write_text(json.dumps(state));before=self.state.read_bytes()
        with sqlite3.connect(self.app/'mission-control.db') as db:
            for table in ('companies','workspaces','tasks'):db.execute('CREATE TABLE '+table+'(id TEXT)')
        result=launch.inspect_installation(self.state,self.app)
        self.assertEqual(result['status'],'update');self.assertFalse(result['requiresInitialization'])
        self.assertEqual(self.state.read_bytes(),before)

    def test_inspection_reads_literal_database_filename(self):
        target=self.app/'client #question?.db'
        with sqlite3.connect(target) as db:
            db.execute('CREATE TABLE companies(id TEXT)')
            db.execute("INSERT INTO companies VALUES('foreign')")
        (self.app/'.env.local').write_text("DATABASE_PATH='"+str(target)+"'\n")
        with self.assertRaises(ValueError):launch.inspect_installation(self.state,self.app)
        self.assertFalse(self.state.exists())

    def test_binding_uses_literal_database_filename(self):
        self.initialize();target=self.app/'client #question?.db'
        with sqlite3.connect(target) as db:
            db.execute('CREATE TABLE companies(id TEXT PRIMARY KEY,name TEXT,slug TEXT UNIQUE)')
        (self.app/'.env.local').write_text("DATABASE_PATH='"+str(target)+"'\n")
        launch.bind_database(self.state,self.app)
        with sqlite3.connect(target) as db:
            self.assertEqual(db.execute('SELECT id FROM companies').fetchone()[0],json.loads(self.state.read_text())['companyId'])

    def test_fresh_explicit_database_and_custom_workspace_are_preserved(self):
        self.state=self.root/'custom workspace'/'state.json';self.initialize()
        (self.app/'.env.local').write_text('MC_API_TOKEN=fixture-token\n')
        launch.provision(self.state,self.app,self.root,{'DATABASE_PATH':'custom data/a$b.db'})
        values=launch.env_read(self.app/'.env.local')
        self.assertEqual(values['DATABASE_PATH'],str((self.app/'custom data/a$b.db').resolve()))
        self.assertEqual(values['ZERO_HUMAN_COMPANY_DIR'],str((self.state.parent/'zero-human-company/fixture-company').resolve()))
        launch.provision(self.state,self.app,self.root,{'DATABASE_PATH':values['DATABASE_PATH']})
        before=(self.app/'.env.local').read_bytes()
        with self.assertRaises(ValueError):launch.provision(self.state,self.app,self.root,{'DATABASE_PATH':'foreign.db'})
        self.assertEqual((self.app/'.env.local').read_bytes(),before)

    def test_actual_installer_service_writer_preserves_literals_and_existing_value(self):
        value="fixture$EXPAND_ME#token's\"quote"
        funcs=self.function('cc_env_has_nonempty')+self.function('cc_env_set_if_absent')
        driver=self.setup()+funcs+'\ncc_env_set_if_absent "$DASHBOARD_DIR/.env.local" MC_API_TOKEN "$FIXTURE_VALUE"'
        result=subprocess.run(['bash','-c',driver],env=dict(os.environ,FIXTURE_VALUE=value),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(launch.env_read(self.app/'.env.local')['MC_API_TOKEN'],value)
        before=(self.app/'.env.local').read_bytes()
        result=subprocess.run(['bash','-c',driver],env=dict(os.environ,FIXTURE_VALUE='replacement'),capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertEqual((self.app/'.env.local').read_bytes(),before)
        self.assertEqual((self.app/'.env.local').stat().st_mode & 0o777,0o600)

    def test_service_writer_fills_quoted_empty_but_preserves_invalid_configuration(self):
        funcs=self.function('cc_env_has_nonempty')+self.function('cc_env_set_if_absent')
        driver=self.setup()+funcs+'\ncc_env_set_if_absent "$DASHBOARD_DIR/.env.local" MC_API_TOKEN fixture-value'
        target=self.app/'.env.local'
        for raw in ("''", '\"\"', ''):
            target.write_text('MC_API_TOKEN='+raw+'\n')
            result=subprocess.run(['bash','-c',driver],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(launch.env_read(target)['MC_API_TOKEN'],'fixture-value')
        target.write_text('MC_API_TOKEN=$FOREIGN_VALUE\n');before=target.read_bytes()
        result=subprocess.run(['bash','-c',driver],capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertEqual(target.read_bytes(),before)

    def test_invalid_service_env_stops_before_default_database(self):
        (self.app/'.env.local').write_text("DATABASE_PATH=$FOREIGN_DB\n")
        driver=self.setup()+self.function('cc_env_get')+self.function('cc_prepare_database_environment')+'\ncc_prepare_database_environment\nprintf should-not-run'
        result=subprocess.run(['bash','-c',driver],capture_output=True,text=True)
        self.assertEqual(result.returncode,71);self.assertNotIn('should-not-run',result.stdout)

    def function(self,name):
        start=self.source.index(name+'() {');return self.source[start:self.source.index('\n}\n',start)+3]

    def setup(self):
        fields={'UPDATE_ONLY':'true','RESUME_REQUESTED':'false','SKILL_DIR':str(ROOT/'32-command-center-setup'),'OC_ROOT':str(self.root),'STATE_FILE':str(self.state),'DASHBOARD_DIR':str(self.app),'DASHBOARD_DIR_SOURCE':'--app-dir flag','CLIENT_SLUG':'fixture-company','COMPANY_NAME':'Fixture Company','CONTACT_EMAIL':'owner@example.test','LOG_FILE':str(self.root/'log')}
        return '\n'.join(k+'='+shlex.quote(v) for k,v in fields.items())+'\nexport OPENCLAW_OWNER_NAME=FixtureOwner\nlog() { :; }\nstate_get() { echo ""; }\ncc_security_preflight() { :; }\nfail_install() { exit 71; }\n'

    def test_real_update_preflight_initializes_cloned_only_install(self):
        start=self.source.index('# ---- preflight ----');end=self.source.index('for cmd in jq curl git npm python3;',start)
        constants=self.source[self.source.index('CC_PKG_NAME='):self.source.index('# Normalize a git remote')]
        block=constants+'\nDASHBOARD_REPO=https://github.com/fixture/blackceo-command-center.git\n'+self.function('cc_repo_slug')+self.function('cc_validate_cc_checkout')+self.source[start:end]
        subprocess.run(['git','init','-q',str(self.app)],check=True)
        subprocess.run(['git','-C',str(self.app),'remote','add','origin','https://github.com/fixture/blackceo-command-center.git'],check=True)
        (self.app/'package.json').write_text('{"name":"mission-control"}')
        (self.app/'next.config.mjs').write_text('export default {}')
        (self.app/'src').mkdir()
        result=subprocess.run(['bash','-c','set -u\n'+self.setup()+block+'\ntest "$UPDATE_ONLY" = true\ntest "$LAUNCH_INIT_REQUIRED" = true'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        state=json.loads(self.state.read_text());self.assertEqual(state['ownerName'],'FixtureOwner');self.assertFalse(state['interviewComplete'])
        original=state['companyId']
        result=subprocess.run(['bash','-c','set -u\n'+self.setup()+block],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(self.state.read_text())['companyId'],original)

    def test_migration_gets_literal_pinned_db_and_failure_stops(self):
        target=self.root/'custom data'/'a$b.db';target.parent.mkdir()
        (self.app/'.env.local').write_text("DATABASE_PATH='"+str(target).replace('$','\\$')+"'\n")
        funcs=self.function('cc_env_get')+self.function('cc_prepare_database_environment')
        start=self.source.index('  cc_prepare_database_environment\n  if ! ( cd')
        end=self.source.index('  # DATA-08',start)
        block=self.source[start:end]
        driver=self.setup()+funcs+'''\nnpm() { test "$DATABASE_PATH" = "$EXPECTED_DB" || return 99; printf '%s' "$DATABASE_PATH" > "$DB_PROOF"; return "$MIGRATION_RC"; }\n'''+block+'\nprintf success\n'
        base={k:v for k,v in os.environ.items() if k!='DATABASE_PATH'}
        for code in (0,3):
            proof=self.root/('proof-'+str(code))
            result=subprocess.run(['bash','-c',driver],env=dict(base,EXPECTED_DB=str(target.resolve()),DB_PROOF=str(proof),MIGRATION_RC=str(code)),capture_output=True,text=True)
            self.assertTrue(proof.exists(),result.stdout+result.stderr+(self.root/'log').read_text());self.assertEqual(proof.read_text(),str(target.resolve()));self.assertEqual(result.returncode,0 if code==0 else 71,result.stderr)
            self.assertEqual('success' in result.stdout,code==0)

    def test_database_env_conflict_does_not_run_migrations(self):
        (self.app/'.env.local').write_text("DATABASE_PATH='/client/own.db'\n")
        driver=self.setup()+self.function('cc_env_get')+self.function('cc_prepare_database_environment')+'\ncc_prepare_database_environment\nprintf should-not-run'
        result=subprocess.run(['bash','-c',driver],env=dict(os.environ,DATABASE_PATH='/foreign/db'),capture_output=True,text=True)
        self.assertEqual(result.returncode,71);self.assertNotIn('should-not-run',result.stdout)


if __name__=='__main__':unittest.main()
