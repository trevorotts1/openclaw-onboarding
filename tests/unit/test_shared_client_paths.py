#!/usr/bin/env python3
"""Hermetic shared-library, canonical-state and legacy-shim path regressions."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[2]


class SharedClientPaths(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.home=self.root/'home';self.home.mkdir()
        self.bundle=self.root/'bundle';self.bundle.mkdir();(self.bundle/'scripts').mkdir();(self.bundle/'platform').mkdir()
        for name in ('lib-shared.sh','lib-onboarding-state.sh','scripts/onboarding-state.sh','platform/common.sh'):
            shutil.copyfile(REPO/name,self.bundle/name)
        # Override only host container inventory. Exercise the actual resolver.
        with (self.bundle/'platform/common.sh').open('a') as handle:
            handle.write('\noc_container_marked() { [[ "${FIXTURE_CONTAINER:-0}" == 1 ]]; }\n')
        self.bin=self.root/'bin';self.bin.mkdir()
        self.stub('uname','printf "%s\\n" "$FIXTURE_OS"')
        for cmd in ('curl','openclaw','npm','pm2'):
            self.stub(cmd,'echo "Unexpected live runtime call" >&2; exit 97')
        self.env={'HOME':str(self.home),'PATH':str(self.bin)+':/usr/bin:/bin','FIXTURE_OS':'Linux','FIXTURE_CONTAINER':'0'}

    def stub(self,name,body):
        target=self.bin/name;target.write_text('#!/bin/bash\n'+body+'\n');target.chmod(0o755)

    def run_shell(self,body,**env):
        return subprocess.run(['/bin/bash','-c',body],env=dict(self.env,**env),capture_output=True,text=True,timeout=15)

    def source(self,relative):return 'source '+shlex.quote(str(self.bundle/relative))

    def test_actual_shared_resolver_preserves_pins_for_all_three_runtimes(self):
        own=self.root/"Owner's client";workspace=self.root/'selected workspace'
        for system,container,expected in [('Darwin','0','mac|native'),('Linux','0','vps|native'),('Linux','1','vps|container')]:
            with self.subTest(system=system,container=container):
                body=self.source('lib-shared.sh')+'\nresolve_platform_paths || exit $?\nprintf "%s|%s|%s|%s|%s" "$OPENCLAW_PLATFORM" "$OPENCLAW_RUNTIME_TOPOLOGY" "$WORKSPACE" "$CONFIG_JSON" "$SECRETS_ENV"'
                result=self.run_shell(body,FIXTURE_OS=system,FIXTURE_CONTAINER=container,OPENCLAW_ROOT=str(own),OPENCLAW_WORKSPACE_PATH=str(workspace))
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout,expected+'|'+str(workspace)+'|'+str(own/'openclaw.json')+'|'+str(own/'secrets/.env'))

    def test_canonical_library_first_does_not_redirect_shim_to_data(self):
        for system in ('Darwin','Linux'):
            body=self.source('lib-onboarding-state.sh')+' || exit $?\n'+self.source('scripts/onboarding-state.sh')+' || exit $?\nprintf "%s|%s|%s" "$OC_CONFIG" "$OBS_OC_ROOT" "$OBS_WORKSPACE"'
            result=self.run_shell(body,FIXTURE_OS=system)
            expected=self.home/'.openclaw'
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,str(expected)+'|'+str(expected)+'|'+str(expected/'workspace'))

    def test_canonical_first_preserves_explicit_root_and_workspace(self):
        own=self.root/'own';workspace=self.root/'work'
        body=self.source('lib-onboarding-state.sh')+' || exit $?\n'+self.source('scripts/onboarding-state.sh')+' || exit $?\nprintf "%s|%s|%s" "$ONBOARDING_STATE_FILE" "$OBS_STATE_FILE" "$OBS_SKILLS_DIR"'
        result=self.run_shell(body,OPENCLAW_ROOT=str(own),OPENCLAW_WORKSPACE_ROOT=str(workspace))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,str(own/'.onboarding-state.json')+'|'+str(workspace/'.onboarding-state.json')+'|'+str(own/'skills'))

    def test_main_agent_workspace_still_precedes_config_defaults(self):
        own=self.home/'.openclaw';own.mkdir()
        workspace=self.root/'main workspace'
        (own/'openclaw.json').write_text(json.dumps({'agents':{'defaults':{'workspace':str(self.root/'default workspace')},'list':[{'id':'main','workspace':str(workspace)}]}}))
        body=self.source('lib-onboarding-state.sh')+' || exit $?\n'+self.source('scripts/onboarding-state.sh')+' || exit $?\nprintf "%s" "$OBS_WORKSPACE"'
        result=self.run_shell(body)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout,str(workspace))

    def test_conflicting_pins_fail_twice_and_corrected_retry_can_load(self):
        body=self.source('scripts/onboarding-state.sh')+'; first=$?\n'+self.source('scripts/onboarding-state.sh')+'; second=$?\nOPENCLAW_WORKSPACE_ROOT="$OPENCLAW_WORKSPACE_PATH"\n'+self.source('scripts/onboarding-state.sh')+'; third=$?\nprintf "%s|%s|%s" "$first" "$second" "$third"'
        result=self.run_shell(body,OPENCLAW_WORKSPACE_PATH=str(self.root/'one'),OPENCLAW_WORKSPACE_ROOT=str(self.root/'two'))
        self.assertEqual(result.stdout,'1|1|0',result.stderr)

    def test_equivalent_trailing_slash_pins_are_accepted(self):
        own=self.root/'workspace'
        result=self.run_shell(self.source('scripts/onboarding-state.sh'),OPENCLAW_WORKSPACE_PATH=str(own)+'/',OPENCLAW_WORKSPACE_ROOT=str(own))
        self.assertEqual(result.returncode,0,result.stderr)

    def test_invalid_config_or_relative_workspace_never_falls_back(self):
        own=self.root/'own';own.mkdir()
        (own/'openclaw.json').write_text('{bad-json')
        result=self.run_shell(self.source('scripts/onboarding-state.sh'),OPENCLAW_ROOT=str(own))
        self.assertNotEqual(result.returncode,0)
        (own/'openclaw.json').unlink()
        result=self.run_shell(self.source('scripts/onboarding-state.sh'),OPENCLAW_ROOT=str(own),OPENCLAW_WORKSPACE_PATH='relative/workspace')
        self.assertNotEqual(result.returncode,0)

    def test_failed_canonical_library_is_propagated(self):
        (self.bundle/'lib-onboarding-state.sh').write_text('return 19\n')
        result=self.run_shell(self.source('scripts/onboarding-state.sh'))
        self.assertNotEqual(result.returncode,0)

    def test_resolution_failure_prevents_reads_and_directory_creation(self):
        for function in ('read_ghl_pit','read_ghl_location_id','get_or_create_master_files'):
            body=self.source('lib-shared.sh')+'\n'+function
            result=self.run_shell(body,OPENCLAW_WORKSPACE_PATH=str(self.root/'one'),OPENCLAW_WORKSPACE_ROOT=str(self.root/'two'))
            self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,'')
        self.assertFalse((self.home/'Downloads').exists())

    def test_selected_root_never_borrows_other_installation_credentials(self):
        other=self.home/'.openclaw/secrets';other.mkdir(parents=True)
        (other/'.env').write_text('GOHIGHLEVEL_API_KEY=pit-foreign-fixture\nGOHIGHLEVEL_LOCATION_ID=foreign-location\n')
        body=self.source('lib-shared.sh')+'\nread_ghl_pit\nread_ghl_location_id'
        result=self.run_shell(body,OPENCLAW_ROOT=str(self.root/'selected-root'))
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'')

    def test_json_credential_readers_support_apostrophe_root(self):
        own=self.root/"Owner's root";own.mkdir()
        (own/'openclaw.json').write_text(json.dumps({'env':{'vars':{'GOHIGHLEVEL_API_KEY':'pit-selected-fixture','GOHIGHLEVEL_LOCATION_ID':'selected-location'}}}))
        body=self.source('lib-shared.sh')+'\nread_ghl_pit\nread_ghl_location_id'
        result=self.run_shell(body,OPENCLAW_ROOT=str(own))
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.splitlines(),['pit-selected-fixture','selected-location'])

    def test_all_eleven_location_aliases_resolve_from_both_selected_stores(self):
        aliases=('GOHIGHLEVEL_API_KEY','GHL_API_KEY','GHL_PIT','GHL_TOKEN','GHL_PRIVATE_INTEGRATION_TOKEN',
                 'PRIVATE_INTEGRATION_TOKEN','GHL_PRIVATE_TOKEN','PIT_TOKEN','GHL_PIT_TOKEN',
                 'GOHIGHLEVEL_LOCATION_PIT','GHL_LOCATION_PIT')
        own=self.root/"Owner's selected root";(own/'secrets').mkdir(parents=True)
        secret=own/'secrets/.env';config=own/'openclaw.json'
        body=self.source('lib-shared.sh')+'\nread_ghl_pit'
        for store in ('secret','config'):
            for alias in aliases:
                with self.subTest(store=store,alias=alias):
                    secret.unlink(missing_ok=True);config.unlink(missing_ok=True)
                    value='pit-fixture-'+alias.lower()
                    if store=='secret':secret.write_text(alias+'='+value+'\n')
                    else:config.write_text(json.dumps({'env':{'vars':{alias:value}}}))
                    result=self.run_shell(body,OPENCLAW_ROOT=str(own))
                    self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),value)

    def test_canonical_name_beats_alias_across_stores_and_agency_is_excluded(self):
        own=self.root/'selected';(own/'secrets').mkdir(parents=True)
        secret=own/'secrets/.env';config=own/'openclaw.json'
        body=self.source('lib-shared.sh')+'\nread_ghl_pit'
        secret.write_text('GHL_PIT=pit-alias\n')
        config.write_text(json.dumps({'env':{'vars':{'GOHIGHLEVEL_API_KEY':'pit-canonical-json'}}}))
        result=self.run_shell(body,OPENCLAW_ROOT=str(own))
        self.assertEqual(result.stdout.strip(),'pit-canonical-json')
        secret.write_text('GOHIGHLEVEL_API_KEY=pit-canonical-secret\n')
        result=self.run_shell(body,OPENCLAW_ROOT=str(own))
        self.assertEqual(result.stdout.strip(),'pit-canonical-secret')
        secret.write_text('GOHIGHLEVEL_AGENCY_PIT=pit-agency-secret\nGOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=browser-fixture\n')
        config.write_text(json.dumps({'env':{'vars':{'GHL_AGENCY_PIT':'pit-agency-json'}}}))
        result=self.run_shell(body,OPENCLAW_ROOT=str(own))
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'')

    def test_missing_platform_library_fails_instead_of_inventing_paths(self):
        (self.bundle/'platform/common.sh').unlink()
        result=self.run_shell(self.source('lib-shared.sh')+'\nresolve_platform_paths')
        self.assertNotEqual(result.returncode,0)


if __name__=='__main__':unittest.main()
