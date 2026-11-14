"""BU-62: one uncertain send no longer locks the link sender for good.

The builder writes this file; QC runs it. No network, no real OpenClaw CLI.
"""
import importlib.util
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

STUB = '''#!{python}
import json, os, sys, time
if os.environ.get('INTERVIEW_STUB_MODE') == 'timeout':
    time.sleep(5)
    sys.exit(0)
target = sys.argv[sys.argv.index('--target') + 1]
print(json.dumps({'ok': True, 'channel': 'telegram', 'payload': {'messageId': 'fixture-message-1', 'chatId': target}}))
'''


class UncertainRecoveryTests(unittest.TestCase):
    MESSAGE = 'Hi - your AI Workforce Interview is ready: https://client.example.com/interview'
    TARGET = '123456789'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.cli = self.bin / 'openclaw'
        self.cli.write_text(STUB.replace('{python}', sys.executable))
        self.cli.chmod(0o755)
        self.ledger = self.root / 'discovery' / 'sends.log'
        self.context = {'origin': 'https://client.example.com', 'companyId': 'client-a',
                        'tenantId': 'tenant-a', 'installationId': 'install-a',
                        'mode': 'start', 'lane': 'legacy'}
        env = {key: value for key, value in os.environ.items()
               if not key.startswith('INTERVIEW_INVITATION_') and key != 'FORCE'}
        env.update(HOME=str(self.root), PATH=str(self.bin) + os.pathsep + os.environ.get('PATH', ''),
                   OPENCLAW_BIN=str(self.cli), OPENCLAW_ROOT=str(self.root / '.openclaw'),
                   INTERVIEW_STUB_MODE='ack')
        self.process_env = patch.dict(os.environ, env, clear=True)
        self.process_env.start()
        self.addCleanup(self.process_env.stop)

    def send(self, **kwargs):
        return m.send_gateway(self.MESSAGE, self.TARGET, self.ledger, self.context,
                              force=os.environ.get('FORCE') == '1', **kwargs)

    def receipt_path(self):
        return self.ledger.with_suffix(self.ledger.suffix + '.receipt.json')

    def test_uncertain_send_recovers_only_after_the_window_and_only_for_the_owner(self):
        with patch.dict(os.environ, {'INTERVIEW_STUB_MODE': 'timeout'}):
            code, receipt = self.send(timeout=0.3)
        self.assertEqual(code, 9)
        self.assertEqual(receipt['status'], 'uncertain')
        receipt_file = self.receipt_path()
        uncertain = json.loads(receipt_file.read_text())

        # Inside the window an explicit FORCE still refuses and says how to recover.
        with patch.dict(os.environ, {'FORCE': '1'}):
            with self.assertRaises(m.Pending) as caught:
                self.send()
        self.assertIn('retry after 30 minutes with FORCE=1', str(caught.exception))

        # Past the window, an automatic retry still refuses and nothing is written.
        stale = dict(uncertain, epoch=int(m.time.time()) - 1860)
        receipt_file.write_text(json.dumps(stale))
        with patch.dict(os.environ, {'INTERVIEW_INVITATION_AUTOMATIC': '1'}):
            with self.assertRaises(m.Pending):
                self.send()
        self.assertEqual(json.loads(receipt_file.read_text()), stale)

        # The owner asking to resume is the one path that proceeds, and the old
        # receipt is kept before the new send.
        with patch.dict(os.environ, {'INTERVIEW_INVITATION_OWNER_REQUEST': '1'}):
            code, receipt = self.send()
        self.assertEqual(code, 0)
        self.assertEqual(receipt['status'], 'accepted')
        superseded = receipt_file.with_name(receipt_file.name + '.superseded-' + str(stale['epoch']) + '.json')
        self.assertEqual(json.loads(superseded.read_text()), stale)


if __name__ == '__main__':
    unittest.main()
