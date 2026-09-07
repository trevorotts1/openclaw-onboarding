#!/usr/bin/env python3
"""Extract the real installer function; launchctl is always a fixture stub."""
import json
import os
from pathlib import Path
import plistlib
import shlex
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / '23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-intake-poll.plist.template'
# F12 moved install_intake_poll_schedule() and _fix61_selected_workspace() out
# of install.sh and into lib-presentation-schedules.sh VERBATIM, so
# update-skills.sh can reach them and a fleet roll can repair the schedule.
# The function text is byte-identical -- only its address changed -- so this
# test still executes the real installer.
INSTALLER_SRC = (REPO / 'lib-presentation-schedules.sh').read_text()
SOURCE = INSTALLER_SRC.split('install_intake_poll_schedule() {', 1)[1].split('\n    return "$_rc"\n}', 1)[0] + '\n    return "$_rc"\n}'
FUNCTION = 'install_intake_poll_schedule() {' + SOURCE
FUNCTION += '\n_fix61_selected_workspace() {' + INSTALLER_SRC.split('_fix61_selected_workspace() {', 1)[1].split('\n}', 1)[0] + '\n}'

class IntakePollPlistTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "owner & company | O'Brien home"
        self.scripts = self.home / "departments & more | scripts's"
        self.scripts.mkdir(parents=True)
        for name in ['presentation-intake-poll.sh', 'presentation-notify.py']:
            (self.scripts / name).write_text('# fixture only\n')
        self.template = self.scripts / TEMPLATE.name
        self.template.write_text(TEMPLATE.read_text())
        self.destination = self.home / 'Library/LaunchAgents/com.blackceo.presentation-intake-poll.plist'
        self.destination.parent.mkdir(parents=True)
        self.previous = plistlib.dumps({'Label': 'prior-valid-working-job', 'KeepAlive': True})
        self.destination.write_bytes(self.previous)
        self.log = self.root / 'launchctl-calls.jsonl'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        stub = self.bin / 'launchctl'
        stub.write_text('#!/usr/bin/env python3\nimport json,os,sys\nwith open(os.environ["FIXTURE_LAUNCHCTL_LOG"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n')
        stub.chmod(0o755)

    def run_installer(self):
        base = {k: v for k, v in os.environ.items() if not k.startswith(('OPENCLAW_', 'OC_'))}
        env = dict(base, HOME=str(self.home), PRESENTATIONS_SCRIPTS_SRC=str(self.scripts), OPENCLAW_PLATFORM='mac', FIXTURE_LAUNCHCTL_LOG=str(self.log), PATH=str(self.bin) + ':' + os.environ['PATH'])
        script = 'set -euo pipefail\nwarn() { echo "$*" >&2; }\nsuccess() { :; }\n' + FUNCTION + '\ninstall_intake_poll_schedule\n'
        return subprocess.run(['bash', '-c', script], env=env, text=True, capture_output=True, timeout=20)

    def assert_preserved(self):
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.destination.read_bytes(), self.previous)
        self.assertFalse(self.log.exists(), 'validation failure must not unload or load a job')
        self.assertEqual(list(self.destination.parent.glob('.presentation-intake-poll-*')), [])

    def test_literal_special_paths_atomic_render_and_idempotent_reload(self):
        for _ in range(2):
            result = self.run_installer()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = plistlib.loads(self.destination.read_bytes())
            self.assertEqual(data['ProgramArguments'], ['/bin/bash', str(self.scripts / 'presentation-intake-poll.sh')])
            self.assertEqual(data['StandardOutPath'], str(self.home / 'Library/Logs/openclaw/presentation-intake-poll.log'))
            env = data['EnvironmentVariables']
            self.assertEqual(env['PRESENTATION_RUNS_DIR'], str(self.home / '.openclaw/workspace/departments/Presentations/runs'))
            self.assertEqual(shlex.split(env['PRESENTATION_NOTIFY_CMD']), [str(self.scripts / 'presentation-notify.py')])
            self.assertIn(str(self.home / '.npm-global/bin'), env['PATH'].split(':'))
            self.assertEqual(env['OPENCLAW_ROOT'], str(self.home / '.openclaw'))
            self.assertEqual(env['OPENCLAW_WORKSPACE_PATH'], str(self.home / '.openclaw/workspace'))
            self.assertEqual(env['OPENCLAW_WORKSPACE_ROOT'], env['OPENCLAW_WORKSPACE_PATH'])
            self.assertEqual(data['StartInterval'], 300)
            self.assertFalse(data['RunAtLoad'])
            self.assertEqual(list(self.destination.parent.glob('.presentation-intake-poll-*')), [])
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(calls, [['unload', str(self.destination)], ['load', str(self.destination)]] * 2)

    def test_invalid_xml_preserves_previous_job(self):
        self.template.write_text('<?xml version="1.0"?><plist>bad')
        self.assert_preserved()

    def test_missing_required_environment_preserves_previous_job(self):
        self.template.write_text(TEMPLATE.read_text().replace('&lt;PRESENTATION_NOTIFY_CMD&gt;', 'hardcoded-transport'))
        self.assert_preserved()

    def test_unknown_placeholder_preserves_previous_job(self):
        self.template.write_text(TEMPLATE.read_text().replace('&lt;POLL_PATH&gt;', '&lt;UNKNOWN_PATH&gt;'))
        self.assert_preserved()

    def test_wrong_program_contract_preserves_previous_job(self):
        self.template.write_text(TEMPLATE.read_text().replace('/bin/bash', '/bin/false'))
        self.assert_preserved()

    def test_missing_notify_transport_keeps_empty_env_store_fallback(self):
        (self.scripts / 'presentation-notify.py').unlink()
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(plistlib.loads(self.destination.read_bytes())['EnvironmentVariables']['PRESENTATION_NOTIFY_CMD'], '')

if __name__ == '__main__':
    unittest.main()
