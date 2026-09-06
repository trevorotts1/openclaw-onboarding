#!/usr/bin/env python3
"""Execute actual native PM2 boot helper with isolated files and fake commands."""
import importlib.util
import os
from pathlib import Path
import subprocess
import shlex
import tempfile
import types
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pm2_boot', REPO / '32-command-center-setup/scripts/ensure-pm2-boot.py')
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)


class BootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.units = self.root / 'units'
        self.units.mkdir()
        self.calls = []
        self.environment = {'HOME': str(self.root / "Owner's home"),
                            'PM2_HOME': str(self.root / "custom PM2 % $ path"),
                            'PATH': '/fixture/bin:/usr/bin:/bin',
                            'CLIENT_SECRET': "raw $(never-run) 'secret'"}
        self.enabled = 'enabled'
        self.fields = {}
        self.init = 'systemd'
        self.uid = 0
        self.refuse_sudo = False
        self.start_patch(patch.dict(os.environ, self.environment, clear=True))
        self.start_patch(patch.object(boot.platform, 'system', return_value='Linux'))
        self.container = self.start_patch(patch.object(boot, 'container', return_value=False))
        self.start_patch(patch.object(boot.os, 'geteuid', side_effect=lambda: self.uid))
        self.start_patch(patch.object(boot.pwd, 'getpwnam', return_value=types.SimpleNamespace(pw_dir=self.environment['HOME'])))
        self.start_patch(patch.object(boot.pwd, 'getpwuid', return_value=types.SimpleNamespace(pw_name='client')))
        self.start_patch(patch.object(boot.shutil, 'which', side_effect=lambda cmd: '/fixture/bin/' + cmd))
        self.start_patch(patch.object(boot.subprocess, 'run', side_effect=self.fake_run))

    def start_patch(self, item):
        value = item.start()
        self.addCleanup(item.stop)
        return value

    def fake_run(self, args, **kwargs):
        self.calls.append((args, kwargs))
        argv = args[2:] if Path(args[0]).name == 'sudo' else args
        stdout = ''
        rc = 0
        if Path(args[0]).name == 'sudo' and self.refuse_sudo:
            rc = 1
        elif argv[0] == 'ps':
            stdout = self.init
        elif Path(argv[0]).name == 'install':
            Path(argv[-1]).write_text(Path(argv[-2]).read_text())
        elif 'is-enabled' in argv:
            stdout = self.enabled
        elif any(arg.startswith('--property=') and arg.split('=', 1)[1] in self.fields for arg in argv):
            stdout = self.fields[next(arg.split('=', 1)[1] for arg in argv if arg.startswith('--property='))]
        elif '--property=PIDFile' in argv:
            stdout = str(Path(os.environ['PM2_HOME']) / 'pm2.pid')
        elif '--property=User' in argv:
            stdout = 'client'
        elif '--property=Environment' in argv:
            stdout = ' '.join(shlex.quote(key + '=' + os.environ[key]) for key in ('HOME', 'PM2_HOME', 'PATH'))
        elif '--property=ExecStart' in argv:
            stdout = '{ path=/fixture/bin/pm2 ; argv[]=/fixture/bin/pm2 resurrect ; ignore_errors=no ; }'
        return subprocess.CompletedProcess(args, rc, stdout=stdout, stderr='')

    def test_root_registers_verified_unit_without_restart_and_preserves_raw_env(self):
        result = boot.ensure(self.units)
        self.assertEqual(result['status'], 'enabled')
        unit = (self.units / 'pm2-client.service').read_text()
        self.assertIn('User=client', unit)
        self.assertIn('Environment=' + boot.quoted('PM2_HOME=' + self.environment['PM2_HOME']), unit)
        self.assertIn('ExecStart="/fixture/bin/pm2" resurrect', unit)
        self.assertIn('PIDFile=' + str(Path(self.environment['PM2_HOME']) / 'pm2.pid').replace('%', '%%') + '\n', unit)
        self.assertNotIn('CLIENT_SECRET', unit)
        commands = [args for args, _ in self.calls]
        self.assertIn(['/fixture/bin/systemctl', 'enable', 'pm2-client.service'], commands)
        self.assertFalse(any('start' in args or 'restart' in args for args in commands))
        saved = next(kwargs for args, kwargs in self.calls if args[-1] == 'save')
        self.assertEqual(saved['env']['CLIENT_SECRET'], self.environment['CLIENT_SECRET'])
        self.assertEqual(saved['env']['PM2_HOME'], self.environment['PM2_HOME'])
        self.assertTrue(saved['env']['PATH'].startswith('/fixture/bin:'))

    def test_nonroot_uses_passwordless_privilege_only_for_unit_operations(self):
        self.uid = 1001
        self.assertEqual(boot.ensure(self.units)['status'], 'enabled')
        commands = [args for args, _ in self.calls]
        self.assertIn(['/fixture/bin/sudo', '-n', 'true'], commands)
        self.assertIn(['/fixture/bin/sudo', '-n', '/fixture/bin/systemctl', 'enable', 'pm2-client.service'], commands)
        self.assertIn(['/fixture/bin/pm2', 'save'], commands)

    def test_missing_privilege_leaves_no_unit(self):
        self.uid = 1001
        self.refuse_sudo = True
        with self.assertRaises(boot.Pending):
            boot.ensure(self.units)
        self.assertEqual(list(self.units.iterdir()), [])
        self.assertFalse(any(args[-1] == 'save' for args, _ in self.calls))

    def test_unsupported_init_is_pending_without_unit_writes(self):
        self.init = 'init'
        with self.assertRaises(boot.Pending):
            boot.ensure(self.units)
        self.assertEqual(list(self.units.iterdir()), [])

    def test_disabled_unit_never_claims_success(self):
        self.enabled = 'disabled'
        with self.assertRaises(boot.Pending):
            boot.ensure(self.units)

    def test_container_never_touches_host_service_or_saves_daemon(self):
        self.container.return_value = True
        self.assertEqual(boot.ensure(self.units), {'status': 'external-policy', 'runtime': 'container'})
        self.assertEqual(self.calls, [])

    def test_mac_keeps_existing_platform_policy(self):
        with patch.object(boot.platform, 'system', return_value='Darwin'):
            self.assertEqual(boot.ensure(self.units)['status'], 'external-policy')
        self.assertEqual(self.calls, [])

    def test_existing_operator_unit_is_not_overwritten(self):
        unit = self.units / 'pm2-client.service'
        unit.write_text('operator unit\n')
        self.fields['User'] = 'another-user'
        with self.assertRaises(boot.Pending):
            boot.ensure(self.units)
        self.assertEqual(unit.read_text(), 'operator unit\n')

    def test_compatible_official_unit_is_preserved_and_enabled(self):
        unit = self.units / 'pm2-client.service'
        unit.write_text('official PM2 unit\n')
        self.fields['FragmentPath'] = str(unit)
        result = boot.ensure(self.units)
        self.assertTrue(result['preservedExisting'])
        self.assertEqual(unit.read_text(), 'official PM2 unit\n')
        self.assertFalse(any(Path(args[0]).name == 'install' for args, _ in self.calls))

    def test_loaded_pid_mismatch_prevents_enable(self):
        self.fields['PIDFile'] = '/other-client/pm2.pid'
        with self.assertRaises(boot.Pending):
            boot.ensure(self.units)
        self.assertFalse(any('enable' in args for args, _ in self.calls))

    def test_loaded_dropin_user_mismatch_prevents_enable(self):
        self.fields['User'] = 'another-user'
        with self.assertRaises(boot.Pending):
            boot.ensure(self.units)
        self.assertFalse(any('enable' in args for args, _ in self.calls))

    def test_environment_file_override_cannot_claim_daemon_context(self):
        self.fields['EnvironmentFiles'] = '/operator/another-client.env (ignore_errors=no)'
        with self.assertRaises(boot.Pending):
            boot.ensure(self.units)
        self.assertFalse(any('enable' in args for args, _ in self.calls))

    def test_own_unit_is_idempotent_but_foreign_pm2_home_refused(self):
        boot.ensure(self.units)
        boot.ensure(self.units)
        original = (self.units / 'pm2-client.service').read_text()
        with patch.dict(os.environ, PM2_HOME=str(self.root / 'other-client')):
            self.fields['PIDFile'] = str(Path(self.environment['PM2_HOME']) / 'pm2.pid')
            with self.assertRaises(boot.Pending):
                boot.ensure(self.units)
        self.assertEqual((self.units / 'pm2-client.service').read_text(), original)

    def test_unsupported_control_character_fails_before_mutation(self):
        with patch.dict(os.environ, HOME='/tmp/name\nmalicious'):
            with self.assertRaises(boot.Pending):
                boot.ensure(self.units)
        self.assertEqual(list(self.units.iterdir()), [])

    def test_installer_runs_boot_gate_after_tunnel_before_interview_exit(self):
        source = (REPO / '32-command-center-setup/scripts/run-full-install.sh').read_text()
        gate = source.index('if python3 "$SKILL_DIR/scripts/ensure-pm2-boot.py"')
        self.assertLess(source.index('phase=6h tunnel: starting'), gate)
        self.assertLess(gate, source.index('# INTERVIEW-COMPLETE GATE'))
        self.assertIn('.commandCenterBootPersistence = "pending"', source[gate:gate + 800])


if __name__ == '__main__':
    unittest.main()
