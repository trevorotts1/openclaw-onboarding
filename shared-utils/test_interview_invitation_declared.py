"""BU-35p: the link sender may send past a DECLARED prior completion.

DECLARED is the owner's word, not a finished interview: the operator flag from
send-interview-link.sh (--allow-declared) lets the invitation through. Without
it the refusal is exactly what it was. COMPLETE is never overridable.

The builder writes this file; QC runs it. No network, no OpenClaw CLI.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('invitation', ROOT / 'shared-utils' / 'interview_invitation.py')
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

CLEAN = ('MC_TENANT_ID', 'MC_COMPANY_ID', 'MC_INSTALLATION_ID', 'MC_API_TOKEN',
         'CC_PUBLIC_URL', 'MC_TENANT_PUBLIC_URL', 'OPENCLAW_DASHBOARD_URL',
         'INTERVIEW_GATE_URL', 'ALLOW_DECLARED', 'FORCE')


class DeclaredGateTests(unittest.TestCase):
    def setUp(self):
        env = {key: value for key, value in os.environ.items() if key not in CLEAN}
        self.process_env = patch.dict(os.environ, env, clear=True)
        self.process_env.start()
        self.addCleanup(self.process_env.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / '.workforce-build-state.json'
        self.state.write_text(json.dumps({}))

    def run_main(self, *argv):
        err = io.StringIO()
        with patch.object(sys, 'argv', ['interview_invitation.py', *argv]), \
             patch.object(m, 'prompt_status', return_value='DECLARED'), \
             contextlib.redirect_stderr(err):
            code = m.main()
        return code, err.getvalue()

    def test_predicate(self):
        self.assertTrue(m.completion_permits_invitation('INCOMPLETE'))
        self.assertTrue(m.completion_permits_invitation('INCOMPLETE', True))
        self.assertFalse(m.completion_permits_invitation('DECLARED'))
        self.assertTrue(m.completion_permits_invitation('DECLARED', True))
        self.assertFalse(m.completion_permits_invitation('COMPLETE', True))
        self.assertFalse(m.completion_permits_invitation('UNKNOWN', True))

    def test_declared_refused_without_the_flag(self):
        code, err = self.run_main('resolve', '--state', str(self.state))
        self.assertEqual(code, 8)
        self.assertIn('PENDING: prior interview completion recorded', err)

    def test_declared_passes_the_completion_gate_with_the_flag(self):
        # Past the gate it stops on the next honest refusal (no identity), which
        # proves the completion refusal is the one that changed and only it.
        code, err = self.run_main('resolve', '--state', str(self.state), '--allow-declared')
        self.assertEqual(code, 8)
        self.assertIn('PENDING: tenantId missing', err)
        self.assertNotIn('prior interview completion recorded', err)

    def test_declared_passes_with_the_environment_flag(self):
        with patch.dict(os.environ, {'ALLOW_DECLARED': '1'}):
            code, err = self.run_main('resolve', '--state', str(self.state))
        self.assertEqual(code, 8)
        self.assertIn('PENDING: tenantId missing', err)

    def test_complete_is_not_overridable(self):
        err = io.StringIO()
        with patch.object(sys, 'argv', ['interview_invitation.py', 'resolve',
                                        '--state', str(self.state), '--allow-declared']), \
             patch.object(m, 'prompt_status', return_value='COMPLETE'), \
             contextlib.redirect_stderr(err):
            code = m.main()
        self.assertEqual(code, 8)
        self.assertIn('PENDING: prior interview completion recorded', err.getvalue())

    def test_resolve_public_origin_default_is_unchanged(self):
        with patch.object(m, 'prompt_status', return_value='DECLARED'), \
             self.assertRaises(m.Pending) as caught:
            m.resolve_public_origin({}, {})
        self.assertEqual(str(caught.exception), 'prior interview completion recorded')


if __name__ == '__main__':
    unittest.main()
