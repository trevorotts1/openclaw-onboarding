#!/usr/bin/env python3
"""Offline security-floor tests; no real Node install, database or service calls."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared-utils'))
import cc_runtime_preflight as guard
from cc_compat import load_cc_compat, resolve_cc_tag, assert_min_version


class Compatibility(unittest.TestCase):
    def test_node_boundaries(self):
        for value in ['v20.19.0','20.20.1','v22.13.0','22.99.0','24.0.0','25.1.0']:
            with self.subTest(value=value): guard.assert_node_version(value)
        for value in ['18.20.0','20.18.9','21.9.0','22.12.9','23.99.0','v24.0.0-rc.1','garbage','','024.0.0']:
            with self.subTest(value=value), self.assertRaises(ValueError): guard.assert_node_version(value)

    def test_security_floor_and_resolver(self):
        compat=load_cc_compat(ROOT)
        self.assertEqual(compat['commandCenter']['minVersion'],'v7.1.0')
        self.assertEqual(resolve_cc_tag(compat),'v7.1.0')
        for version in ['6.1.0','7.0.0']:
            with self.assertRaises(ValueError): assert_min_version(version,compat)
            with self.assertRaises(ValueError): guard.assert_cc_package({'version':version})
        guard.assert_cc_package({'version':'7.1.0'})
        compat['commandCenter']['pinnedTag']=None
        self.assertEqual(resolve_cc_tag(compat,['v7.0.0','v7.1.0']),'v7.1.0')
        with self.assertRaises(ValueError): resolve_cc_tag(compat,['v7.0.0'])

    def test_cli_node_and_checkout_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td); node=directory/'node'; package=directory/'package.json'
            package.write_text('{"version":"7.1.0"}')
            env={**os.environ,'PATH':str(directory)}
            for node_version,cc_version,expected in [('v22.12.0','7.1.0',1),('v22.13.0','7.0.0',1),('v22.13.0','7.1.0',0)]:
                node.write_text('#!/bin/sh\nprintf "%s\\n" "'+node_version+'"\n');node.chmod(0o755)
                package.write_text(json.dumps({'version':cc_version}))
                result=subprocess.run([sys.executable,str(ROOT/'shared-utils/cc_runtime_preflight.py'),'--checkout',td],env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,expected,result.stderr)
            node.unlink()
            self.assertNotEqual(subprocess.run([sys.executable,str(ROOT/'shared-utils/cc_runtime_preflight.py')],env=env,capture_output=True).returncode,0)

    def test_install_gate_fails_in_both_modes_before_side_effect(self):
        source=(ROOT/'32-command-center-setup/scripts/run-full-install.sh').read_text()
        fn=source[source.index('cc_security_preflight() {'):source.index('# ---- preflight ----')]
        self.assertLess(source.index('cc_security_preflight\n'),source.index('for cmd in jq curl git npm python3;'))
        self.assertEqual(source.count('cc_security_preflight --checkout "$DASHBOARD_DIR"'),3)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'skill').mkdir();(root/'shared-utils').mkdir()
            (root/'shared-utils/cc_runtime_preflight.py').write_text('raise SystemExit(1)\n')
            for mode in ['true','false']:
                script='fail_install() { exit 17; }\n'+fn+'\ncc_security_preflight\nprintf bad > "$LOG_FILE.bad"\n'
                result=subprocess.run(['/bin/bash','-c',script],env={**os.environ,'UPDATE_ONLY':mode,'SKILL_DIR':str(root/'skill'),'LOG_FILE':str(root/'log')})
                self.assertEqual(result.returncode,17)
                self.assertFalse((root/'log.bad').exists())

    def test_locked_installs_in_both_modes_use_ci_and_stop_on_failure(self):
        source=(ROOT/'32-command-center-setup/scripts/run-full-install.sh').read_text()
        function=source[source.index('cc_install_locked_dependencies() {'):source.index('# ---- preflight ----')]
        # Exercise the actual shell helper used by both phase-6 branches with a
        # recording npm stub. No package downloads, scripts or real DB calls.
        self.assertEqual(source.count('  cc_install_locked_dependencies\n'),2)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);checkout=root/'checkout';checkout.mkdir();bin_dir=root/'bin';bin_dir.mkdir()
            npm=bin_dir/'npm'
            npm.write_text('#!/bin/sh\nprintf "%s|%s\\n" "$PWD" "$*" >> "$CALL_LOG"\nexit "$NPM_STATUS"\n')
            npm.chmod(0o755)
            lock=checkout/'package-lock.json';calls=root/'calls';sentinel=root/'migration'
            for mode in ['true','false']:
                for has_lock,status in [(False,'0'),(True,'9'),(True,'0')]:
                    if has_lock: lock.write_text('{"lockfileVersion":3}\n')
                    elif lock.exists(): lock.unlink()
                    for file in [calls,sentinel]:
                        if file.exists():file.unlink()
                    script='fail_install() { exit 17; }\nlog() { :; }\n'+function+'\ncc_install_locked_dependencies\nprintf reached > "$MIGRATION_SENTINEL"\n'
                    result=subprocess.run(['/bin/bash','-c',script],env={**os.environ,
                        'PATH':str(bin_dir)+':'+os.environ['PATH'],'UPDATE_ONLY':mode,
                        'DASHBOARD_DIR':str(checkout),'LOG_FILE':str(root/'log'),
                        'CALL_LOG':str(calls),'NPM_STATUS':status,'MIGRATION_SENTINEL':str(sentinel)})
                    expected_success=has_lock and status=='0'
                    self.assertEqual(result.returncode,0 if expected_success else 17)
                    self.assertEqual(sentinel.exists(),expected_success)
                    if has_lock:
                        self.assertEqual(calls.read_text(),str(checkout)+'|ci --engine-strict --no-audit --no-fund\n')
                        self.assertEqual(lock.read_text(),'{"lockfileVersion":3}\n')
                    else:self.assertFalse(calls.exists())

    def test_fleet_blocks_before_fetch_on_old_node_and_before_deploy_on_old_checkout(self):
        spec=importlib.util.spec_from_file_location('fleet_test',ROOT/'shared-utils/fleet_refresh_runner.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td);(directory/'package.json').write_text('{"version":"7.0.0"}')
            result=runner.BoxResult('fixture',dry_run=False)
            with patch.object(guard,'check_node',side_effect=ValueError('unsupported Node')), patch.object(runner.subprocess,'run') as run:
                runner.step_pull_cc({'cc_dir':directory},'v7.1.0',result,False)
                run.assert_not_called()
                self.assertNotEqual(result.steps.get('pull-cc'),'ok')
            result=runner.BoxResult('fixture',dry_run=False)
            with patch.object(guard,'check_node'),patch.object(runner.subprocess,'run',side_effect=[
                subprocess.CompletedProcess([],0,''),
                subprocess.CompletedProcess([],0,'{"version":"7.0.0"}')
            ]) as run:
                runner.step_pull_cc({'cc_dir':directory},'v7.1.0',result,False)
                self.assertEqual(run.call_count,2)  # fetch/read only; old updater never invoked
                self.assertNotEqual(result.steps.get('pull-cc'),'ok')
            for method,step in [(runner.step_build_cc,'build-cc'),(runner.step_restart_cc,'restart-cc')]:
                result=runner.BoxResult('fixture',dry_run=False)
                with patch.object(runner,'wave5_deploy_preflight'),patch.object(guard,'check_node'),patch.object(runner.subprocess,'run') as run:
                    method({'cc_dir':directory},result,False)
                    run.assert_not_called()
                    self.assertNotEqual(result.steps.get(step),'ok')

if __name__=='__main__':unittest.main(verbosity=2)
