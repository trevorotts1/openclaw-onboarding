#!/usr/bin/env python3
"""Actual shell gate plus synthetic CLI/QC processes: no live services."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which('bash')


class GateDeadline(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.skills = self.root / 'skills'
        self.skill = self.skills / 'fixture'
        self.skill.mkdir(parents=True)
        (self.skill / 'SKILL.md').write_text('---\nname: fixture\n---\n')
        self.write_executable(self.bin / 'openclaw', 'printf "Name: fixture\\nReady\\n"')
        self.env = dict(os.environ, HOME=str(self.root),
                        PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        OPENCLAW_ROOT=str(self.root / 'openclaw'),
                        OPENCLAW_WORKSPACE_ROOT=str(self.workspace),
                        OBS_SKILLS_INFO_TIMEOUT_SECONDS='1', OBS_QC_TIMEOUT_SECONDS='1')

    def write_executable(self, path, body):
        path.write_text('#!/usr/bin/env bash\n' + body + '\n')
        path.chmod(0o700)

    def gate(self):
        # Override fixture paths after sourcing: neither host config nor state is
        # read by the actual verification invocation.
        script = '''source "$1/scripts/onboarding-state.sh"
OBS_WORKSPACE="$2"
OBS_STATE_FILE="$2/.onboarding-state.json"
OBS_OC_JSON="$2/nonexistent.json"
obs_default_agent() { printf fixture-owner; }
if obs_verify_skill fixture "$3"; then rc=0; else rc=$?; fi
printf '\\nNEXT_SKILL_REACHED\\n'
exit "$rc"
'''
        result = subprocess.run([BASH, '-c', script, 'fixture', str(ROOT), str(self.workspace), str(self.skills)],
                                env=self.env, capture_output=True, text=True, timeout=8)
        self.assertIn('NEXT_SKILL_REACHED', result.stdout)
        status = json.loads((self.workspace / '.onboarding-state.json').read_text())['skills']['fixture']['status']
        self.assertEqual(status, 'qc-passed' if result.returncode == 0 else 'qc-failed')
        return result

    def receipts(self):
        return [json.loads(p.read_text()) for p in (self.workspace / '.onboarding-qc-diagnostics').glob('*/status.json')]

    def test_normal_cli_and_qc_pass_with_private_diagnostics(self):
        self.write_executable(self.skill / 'qc-fixture.sh', 'echo synthetic-private-value; exit 0')
        result = self.gate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('synthetic-private-value', result.stdout + result.stderr)
        self.assertEqual([r['status'] for r in self.receipts()], ['passed', 'passed'])
        logs = list((self.workspace / '.onboarding-qc-diagnostics').glob('*/*'))
        self.assertTrue(any('synthetic-private-value' in p.read_text() for p in logs))
        for path in logs:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_stalled_cli_reports_distinct_timeout_and_continues(self):
        self.write_executable(self.bin / 'openclaw', 'echo private-cli-diagnostic >&2; sleep 30')
        result = self.gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn('skills-info:timeout', result.stdout)
        self.assertNotIn('private-cli-diagnostic', result.stdout + result.stderr)
        self.assertEqual(self.receipts()[0]['status'], 'timeout')

    def test_stalled_qc_kills_child_process_group_and_records_timeout(self):
        marker = self.root / 'escaped-child'
        pidfile = self.root / 'child.pid'
        self.write_executable(self.skill / 'qc-fixture.sh',
            f"(trap '' TERM; sleep 3; touch '{marker}') &\necho $! > '{pidfile}'\nwait")
        result = self.gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn('qc-script:timeout', result.stdout)
        self.assertIn('timeout', [r['status'] for r in self.receipts()])
        time.sleep(2.2)
        self.assertFalse(marker.exists(), 'QC descendant survived the deadline')
        pid = int(pidfile.read_text())
        ps = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
        self.assertTrue(ps.returncode != 0 or ps.stdout.strip().startswith('Z'), ps.stdout)

    def test_cli_ready_text_with_nonzero_exit_is_not_verified(self):
        self.write_executable(self.bin / 'openclaw', 'echo Ready; exit 3')
        result = self.gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn('skills-info:nonzero-exit', result.stdout)

    def test_nonzero_qc_is_not_timeout(self):
        self.write_executable(self.skill / 'qc-fixture.sh', 'exit 3')
        result = self.gate()
        self.assertIn('qc-script:nonzero-exit', result.stdout)
        self.assertNotIn('qc-script:timeout', result.stdout)
        self.assertIn(3, [r['exitCode'] for r in self.receipts()])

    def test_unbounded_or_invalid_override_refused_before_cli(self):
        for value in ('0', '-1', '999999', 'not-a-number'):
            with self.subTest(value=value):
                self.env['OBS_SKILLS_INFO_TIMEOUT_SECONDS'] = value
                result = self.gate()
                self.assertIn('skills-info:deadline-runner-failed', result.stdout)


if __name__ == '__main__':
    unittest.main()
