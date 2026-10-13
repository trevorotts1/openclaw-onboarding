"""Startability gate (item 04): every prerequisite fails on its own.

"Installed" used to mean a pm2 command returned zero. This gate is what an
installer and the onboarding guide sign off on instead: canonical process
online, local health payload exact, authenticated public readiness with a
registered Access identity, and a REAL minted invitation whose ticket is
discarded — with --no-send asserted, so the gate can never deliver a message.
"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys_path_shared = ROOT / 'shared-utils'
if str(sys_path_shared) not in __import__('sys').path:
    __import__('sys').path.insert(0, str(sys_path_shared))
spec = importlib.util.spec_from_file_location('startability_verifier', ROOT / '32-command-center-setup/scripts/verify-tenant-readiness.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

READY_RECEIPT = {
    'protocol': 'interview-launch.v1', 'stage': 'interview', 'ready': True, 'missing': [],
    'interviewComplete': False, 'host': 'client.example.com',
    'companyId': 'client-a', 'tenantId': 'tenant-a', 'installationId': 'install-a',
    'capabilities': {'state': True, 'localInterviewPrerequisites': True, 'enrollment': True,
                     'providerLiveness': 'unverified', 'runtimeReady': True, 'invitationIssuable': True},
    'warnings': [],
}
RESOLVED = {'origin': 'https://client.example.com', 'host': 'client.example.com',
            'companyId': 'client-a', 'tenantId': 'tenant-a', 'installationId': 'install-a',
            'protocol': 'interview-launch.v1', 'receipt': READY_RECEIPT}
MINTED = {'status': 'minted', 'invitation': 'issued', 'delivery': 'not-attempted', 'ticket': 'discarded',
          'host': 'client.example.com', 'origin': 'https://client.example.com',
          'companyId': 'client-a', 'tenantId': 'tenant-a', 'installationId': 'install-a',
          'invitationExpiresAt': 2000000000, 'invitationReopenable': True, 'recipientHash': 'f' * 64}


class StartabilityGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state_path = self.root / '.workforce-build-state.json'
        self.state = {'companyId': 'client-a', 'tenantId': 'tenant-a', 'installationId': 'install-a',
                      'buildId': 'build-one', 'interviewComplete': False, 'ownerChat': '123456789',
                      'commandCenterUrl': 'https://client.example.com'}
        self.state_path.write_text(json.dumps(self.state))
        (self.root / 'app').mkdir()

    def args(self, **overrides):
        base = {'state': str(self.state_path), 'interview': False, 'env_file': None, 'startability': True,
                'no_send': True, 'app_dir': str(self.root / 'app'), 'pm2_app': 'blackceo-command-center', 'port': 4000}
        base.update(overrides)
        return type('Args', (), base)()

    def run_gate(self, env=None, pm2=(True, 'online'), health=(True, 'ok'), mint=(True, dict(MINTED)), receipt=None):
        receipt = READY_RECEIPT if receipt is None else receipt
        with patch.object(m, '_pm2_canonical_online', return_value=pm2), \
             patch.object(m, '_local_health', return_value=health), \
             patch.object(m, '_mint_only_proof', return_value=mint), \
             patch('interview_invitation.resolve_public_origin',
                   return_value=dict(RESOLVED, receipt=dict(receipt))):
            return m.startability(self.state, env or {}, self.args())

    def test_startability_without_no_send_is_refused(self):
        with patch.object(m, '_pm2_canonical_online', return_value=(True, 'online')):
            receipt = m.startability(self.state, {}, self.args(no_send=False))
        # The gate itself runs; the refusal lives in main(), asserted below.
        with patch.dict(os.environ, {}, clear=False):
            pass
        # main() is the enforcement point: --startability without --no-send exits 1.
        with patch('sys.argv', ['verify-tenant-readiness.py', str(self.state_path), '--startability', '--app-dir', str(self.root / 'app')]), \
             patch.object(m, '_pm2_canonical_online', return_value=(True, 'online')):
            self.assertEqual(m.main(), 1)

    def test_each_prerequisite_fails_independently(self):
        cases = {
            'canonical_process': dict(pm2=(False, 'blackceo-command-center is errored')),
            'local_health': dict(health=(False, 'local health status is None')),
            'public_readiness': dict(receipt=dict(READY_RECEIPT, warnings=['missing_registry_identity'])),
            'invitation_mint': dict(mint=(False, 'invitation did not mint: authenticated invitation HTTP 409: access_identity_unregistered')),
        }
        for expected, overrides in cases.items():
            with self.subTest(expected):
                receipt = self.run_gate(**overrides)
                self.assertFalse(receipt['ready'])
                self.assertEqual(receipt['missing'], [expected])
                self.assertFalse(receipt['checks'][expected]['ok'])
                if expected == 'public_readiness':
                    self.assertIsInstance(receipt['checks'][expected]['detail'], list)
                elif expected != 'invitation_mint':
                    self.assertIsInstance(receipt['checks'][expected]['detail'], str)

    def test_identity_only_registry_cannot_pass_the_gate(self):
        # The exact live failure: ready=true-shaped receipt whose issuer still
        # reports the registry triple missing.
        receipt = dict(READY_RECEIPT, warnings=['missing_registry_identity'],
                       capabilities={'state': True, 'localInterviewPrerequisites': True, 'enrollment': False,
                                     'providerLiveness': 'unverified', 'runtimeReady': True, 'invitationIssuable': False})
        result = self.run_gate(receipt=receipt)
        self.assertFalse(result['ready'])
        self.assertEqual(result['missing'], ['public_readiness'])

    def test_wrong_host_and_foreign_identity_fail_public_readiness(self):
        for resolved in (dict(RESOLVED, host='someone-else.example'),
                         dict(RESOLVED, installationId='foreign-install'),
                         dict(RESOLVED, receipt=dict(READY_RECEIPT, missing=['company_record'], ready=False))):
            with self.subTest(host=resolved.get('host'), installation=resolved.get('installationId')):
                with patch.object(m, '_pm2_canonical_online', return_value=(True, 'online')), \
                     patch.object(m, '_local_health', return_value=(True, 'ok')), \
                     patch.object(m, '_mint_only_proof', return_value=(True, dict(MINTED))), \
                     patch('interview_invitation.resolve_public_origin', return_value=resolved):
                    result = m.startability(self.state, {}, self.args())
                self.assertFalse(result['ready'])
                self.assertIn('public_readiness', result['missing'])

    def test_all_prerequisites_pass_and_the_proof_is_sanitized(self):
        result = self.run_gate()
        self.assertTrue(result['ready'], json.dumps(result))
        self.assertEqual(result['missing'], [])
        self.assertEqual(result['delivery'], 'not-attempted')
        self.assertEqual(result['ticket'], 'discarded')
        proof = Path(result['proofPath'])
        self.assertTrue(proof.is_file())
        text = proof.read_text()
        self.assertEqual(json.loads(text)['buildId'], 'build-one')
        self.assertEqual(len(json.loads(text)['ownerHash']), 64)
        for forbidden in ('fixture-secret', 'enroll=', '123456789'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(json.loads(text)['checks']['invitation_mint']['detail']['ticket'], 'discarded')

    def test_wrong_mint_summary_shape_fails_at_the_parser(self):
        # The real mint-only parser, fed a forged or mislabelled summary, must
        # refuse: ticket kept, delivery attempted, or a non-minted status.
        for bad in (dict(MINTED, ticket='kept'), dict(MINTED, delivery='sent'), dict(MINTED, status='pending'), {'status': 'minted', 'ticket': 'discarded'}):
            with self.subTest(bad=sorted(bad.items())):
                with patch.object(m, '_bounded_json', return_value=dict(READY_RECEIPT)), \
                     patch('subprocess.run', return_value=type('R', (), {'returncode': 0, 'stdout': json.dumps(bad) + '\n', 'stderr': ''})()):
                    ok, detail = m._mint_only_proof(Path(ROOT / '23-ai-workforce-blueprint/scripts/send-interview-link.sh'), str(self.state_path), '123456789')
                self.assertFalse(ok, json.dumps(bad))
                self.assertIsInstance(detail, str)


if __name__ == '__main__':
    unittest.main()
