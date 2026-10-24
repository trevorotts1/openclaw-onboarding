#!/usr/bin/env python3
"""Proofs for the T-46 typed cleanup module. No network, no database, no model.

Run: python3 shared-utils/cleanup/tests/test_disposal.py

Each test pins one clause of
"Typed cleanup eligibility for scratch/merged/dirty/shared-consumer resources;
immediate eligible dispatch with preserved content, exact external path and
actual absence proof; no force deletion", including the unknown/refusal cases.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))
import disposal  # noqa: E402


def _rmtree_force_permissions(path):
    def onerror(func, target, _exc_info):
        try:
            os.chmod(target, stat.S_IRWXU)
            func(target)
        except OSError:
            pass
    if os.path.lexists(str(path)):
        shutil.rmtree(str(path), onerror=onerror)


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='pbb-t46-')).resolve()
        self.approved = self.root / 'approved'
        self.approved.mkdir()
        self.receipts = self.approved / 'receipts'
        self.receipts.mkdir()
        self.device = os.stat(str(self.approved)).st_dev
        self.preserved = self.approved / 'preserved'

    def tearDown(self):
        _rmtree_force_permissions(self.root)

    def item(self, **overrides):
        record = {
            'id': 'unit',
            'resource_type': 'disposable_scratch',
            'path': str(self.approved / 'scratch' / 'unit'),
            'ownership_receipt_id': 'owner-receipt',
            'preservation_receipt_ids': ['saved-artifact'],
            'remote_merge_proof_ids': [],
            'consumers': [],
            'lease_ids': [],
            'clean_state': 'NOT_APPLICABLE',
            'has_unique_unmerged_work': False,
            'disposition': 'eligible',
        }
        record.update(overrides)
        return record

    def scratch(self, name='unit', files=None):
        path = self.approved / 'scratch' / name
        path.mkdir(parents=True)
        for filename, content in (files or {'notes.txt': 'keep me'}).items():
            target = path / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        return path

    def dispatch(self, items, **overrides):
        kwargs = {
            'approved_root': self.approved,
            'expected_device': self.device,
            'receipt_path': self.receipts / 'disposal-receipt.json',
            'preserved_root': self.preserved,
            'preserve_content': True,
        }
        kwargs.update(overrides)
        return disposal.dispatch(items, **kwargs)


class EligibleDispatchTests(Base):
    def test_scratch_is_eligible_preserved_and_actually_absent(self):
        path = self.scratch()
        expected = (path / 'notes.txt').read_text()

        result = self.dispatch([self.item()])

        self.assertEqual('DISPATCHED', result['status'])
        self.assertTrue(result['success'])
        record = result['items'][0]
        self.assertEqual(disposal.ELIGIBLE, record['disposition'])
        self.assertTrue(record['disposed'])
        # immediate: gone inside the call
        self.assertFalse(os.path.lexists(str(path)))
        # preserved content, byte for byte, outside the disposed path
        preserved = result['items'][0]['preserved']
        self.assertTrue(preserved['verified'])
        self.assertEqual(expected,
                         (Path(preserved['destination']) / 'notes.txt').read_text())
        self.assertFalse(str(preserved['destination']).startswith(str(path)))
        # exact external path recorded
        self.assertEqual(os.path.realpath(str(path)), record['canonical_path'])
        self.assertEqual(self.device, record['device'])
        self.assertEqual(str(path), record['path'])
        # actual absence proof
        self.assertEqual({'path': str(path), 'lexists': False, 'absent': True},
                         record['absence'])
        # receipt written atomically and read back
        self.assertTrue(result['receipt_read_back'])
        on_disk = json.loads((self.receipts / 'disposal-receipt.json').read_text())
        self.assertEqual('DISPATCHED', on_disk['status'])
        self.assertEqual(['unit'], [d['id'] for d in on_disk['deletions']])

    def test_released_consumers_do_not_defer_control(self):
        self.scratch()
        result = self.dispatch([self.item(consumers=[
            {'id': 'builder', 'state': 'released'},
            {'id': 'checker', 'state': 'released'}])])
        self.assertEqual('DISPATCHED', result['status'],
                         'control for the active-consumer test')

    def test_already_disposed_with_receipt_is_idempotent(self):
        result = self.dispatch([self.item(
            path=str(self.approved / 'scratch' / 'gone'),
            disposal_receipt_id='dispose-unit-1')])
        record = result['items'][0]
        self.assertEqual(disposal.ELIGIBLE, record['disposition'])
        self.assertIn(disposal.OK_ALREADY_DISPOSED, record['reasons'])
        self.assertTrue(record['disposed'])
        self.assertEqual('DISPATCHED', result['status'])

    def test_merged_clean_worktree_uses_shared_no_force_authority(self):
        repo = self.root / 'repo'
        repo.mkdir()
        self._git(['init', '-q'], repo)
        (repo / 'a.txt').write_text('base')
        self._git(['add', '-A'], repo)
        self._git(['-c', 'user.email=t@example.invalid',
                   '-c', 'user.name=T', 'commit', '-qm', 'base'], repo)
        worktree = self.approved / 'worktrees' / 'unit'
        self._git(['worktree', 'add', '-q', '-b', 'unit', str(worktree)], repo)

        result = self.dispatch([self.item(
            resource_type='merged_worktree',
            path=str(worktree),
            clean_state='CLEAN',
            remote_merge_proof_ids=['remote-proof-1'])],
            repo_path=str(repo))

        record = result['items'][0]
        self.assertEqual(disposal.ELIGIBLE, record['disposition'], record['reason'])
        self.assertTrue(record['disposed'])
        self.assertFalse(os.path.lexists(str(worktree)))
        command = record['removal']['command']
        self.assertEqual(['git', '-C', str(repo), 'worktree', 'remove',
                          str(worktree)], command)
        self.assertFalse([part for part in command if part.startswith('--force')])
        authority = disposal.deletion_authority()
        self.assertEqual(list(authority.worktree_remove_cmd(repo, worktree)),
                         command[:1] + command[1:])
        listed = self._git(['worktree', 'list'], repo)
        self.assertNotIn(str(worktree), listed)

    def _git(self, args, cwd):
        return subprocess.run(['git'] + args, cwd=str(cwd), check=True,
                              capture_output=True, text=True).stdout


class NonEligibleTests(Base):
    def test_dirty_unique_work_is_deferred_and_untouched(self):
        path = self.scratch()
        result = self.dispatch([self.item(
            clean_state='DIRTY_UNIQUE', has_unique_unmerged_work=True)])
        record = result['items'][0]
        self.assertEqual(disposal.DEFERRED, record['disposition'])
        self.assertIn(disposal.DEFERRED_UNIQUE_UNMERGED_WORK, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)), 'dirty work must be preserved')
        self.assertEqual('INCOMPLETE', result['status'])
        self.assertFalse(result['success'])

    def test_active_shared_consumer_defers(self):
        path = self.scratch()
        result = self.dispatch([self.item(consumers=[
            {'id': 'builder', 'state': 'released'},
            {'id': 'checker', 'state': 'active'}])])
        record = result['items'][0]
        self.assertEqual(disposal.DEFERRED, record['disposition'])
        self.assertIn(disposal.DEFERRED_ACTIVE_CONSUMER, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)))

    def test_lease_held_defers(self):
        path = self.scratch()
        result = self.dispatch([self.item(lease_ids=['lease-1'])])
        record = result['items'][0]
        self.assertEqual(disposal.DEFERRED, record['disposition'])
        self.assertIn(disposal.DEFERRED_LEASE_HELD, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)))

    def test_merged_worktree_without_remote_proof_is_blocked(self):
        path = self.scratch(name='wt')
        result = self.dispatch([self.item(
            resource_type='merged_worktree', path=str(path),
            clean_state='CLEAN', remote_merge_proof_ids=[])])
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'])
        self.assertIn(disposal.BLOCKED_MISSING_REMOTE_MERGE_PROOF, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)))


class UnknownNeverSuccessTests(Base):
    def test_unknown_clean_state_is_unknown_and_not_success(self):
        path = self.scratch()
        result = self.dispatch([self.item(clean_state='UNKNOWN')])
        record = result['items'][0]
        self.assertEqual(disposal.UNKNOWN, record['disposition'])
        self.assertIn(disposal.UNKNOWN_CLEAN_STATE, record['reasons'])
        self.assertNotEqual('DISPATCHED', result['status'])
        self.assertFalse(result['success'])
        self.assertTrue(os.path.lexists(str(path)), 'unknown must delete nothing')

    def test_unknown_consumer_state_is_unknown(self):
        path = self.scratch()
        result = self.dispatch([self.item(consumers=[{'id': 'ghost'}])])
        record = result['items'][0]
        self.assertEqual(disposal.UNKNOWN, record['disposition'])
        self.assertIn(disposal.UNKNOWN_CONSUMER_STATE, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)))

    def test_unknown_resource_type_is_unknown(self):
        path = self.scratch()
        result = self.dispatch([self.item(resource_type='mystery_kind')])
        record = result['items'][0]
        self.assertEqual(disposal.UNKNOWN, record['disposition'])
        self.assertIn(disposal.UNKNOWN_RESOURCE_TYPE, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)))

    def test_absent_without_disposal_receipt_is_unknown(self):
        missing = str(self.approved / 'scratch' / 'never-existed')
        result = self.dispatch([self.item(path=missing)])
        record = result['items'][0]
        self.assertEqual(disposal.UNKNOWN, record['disposition'])
        self.assertIn(disposal.UNKNOWN_ABSENT_WITHOUT_RECEIPT, record['reasons'])
        self.assertFalse(result['success'])

    def test_unknown_outranks_blocked_in_precedence(self):
        path = self.scratch()
        record = disposal.evaluate(
            self.item(clean_state='UNKNOWN', ownership_receipt_id=None),
            approved_root=self.approved, expected_device=self.device,
            preserve_content=True)
        self.assertEqual(disposal.UNKNOWN, record['disposition'])
        self.assertIn(disposal.BLOCKED_UNOWNED, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)))


    def test_unknown_does_not_hold_an_unrelated_eligible_resource(self):
        eligible = self.scratch(name='eligible')
        unknown = self.scratch(name='unknown')
        result = self.dispatch([
            self.item(id='eligible', path=str(eligible)),
            self.item(id='unknown', path=str(unknown), clean_state='UNKNOWN')])
        by_id = {record['id']: record for record in result['items']}
        self.assertEqual(disposal.ELIGIBLE, by_id['eligible']['disposition'])
        self.assertTrue(by_id['eligible']['disposed'])
        self.assertFalse(os.path.lexists(str(eligible)),
                         'an eligible resource is disposed immediately')
        self.assertEqual(disposal.UNKNOWN, by_id['unknown']['disposition'])
        self.assertTrue(os.path.lexists(str(unknown)))
        self.assertEqual({'ELIGIBLE': 1, 'DEFERRED': 0, 'BLOCKED': 0,
                          'UNKNOWN': 1}, result['counts'])
        self.assertEqual('INCOMPLETE', result['status'])
        self.assertFalse(result['success'], 'a mixed batch is never success')


class RefusalTests(Base):
    def test_unowned_resource_is_blocked(self):
        path = self.scratch()
        result = self.dispatch([self.item(ownership_receipt_id=None)])
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'])
        self.assertIn(disposal.BLOCKED_UNOWNED, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)))

    def test_path_outside_approved_root_is_blocked(self):
        outside = self.root / 'elsewhere' / 'unit'
        outside.mkdir(parents=True)
        result = self.dispatch([self.item(path=str(outside))])
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'])
        self.assertIn(disposal.BLOCKED_OUTSIDE_APPROVED_ROOT, record['reasons'])
        self.assertTrue(os.path.lexists(str(outside)), 'outside path must survive')

    def test_symlink_leaf_escape_is_blocked(self):
        outside = self.root / 'outside-target'
        outside.mkdir()
        (outside / 'secret.txt').write_text('do not delete')
        link = self.approved / 'scratch' / 'linked'
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(outside), str(link))
        result = self.dispatch([self.item(path=str(link))])
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'])
        self.assertIn(disposal.BLOCKED_SYMLINK_ESCAPE, record['reasons'])
        self.assertTrue((outside / 'secret.txt').exists())

    def test_symlink_component_escape_is_blocked(self):
        outside = self.root / 'outside-dir'
        (outside / 'unit').mkdir(parents=True)
        (outside / 'unit' / 'keep.txt').write_text('keep')
        bridge = self.approved / 'bridge'
        os.symlink(str(outside), str(bridge))
        result = self.dispatch([self.item(path=str(bridge / 'unit'))])
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'])
        self.assertIn(disposal.BLOCKED_SYMLINK_ESCAPE, record['reasons'])
        self.assertTrue((outside / 'unit' / 'keep.txt').exists())

    def test_volume_identity_mismatch_is_blocked(self):
        path = self.scratch()
        result = self.dispatch([self.item()], expected_device=self.device + 1)
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'])
        self.assertIn(disposal.BLOCKED_VOLUME_IDENTITY_MISMATCH, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)), 'wrong volume: nothing deleted')
        self.assertFalse(result.get('receipt_written', False),
                         'no receipt write on an unverified volume')

    def test_missing_preservation_proof_is_blocked(self):
        path = self.scratch()
        result = self.dispatch([self.item()], preserve_content=False,
                               preserved_root=None)
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'])
        self.assertIn(disposal.BLOCKED_MISSING_PRESERVATION, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)))

    def test_removal_failure_preserves_tree_and_never_forces(self):
        path = self.scratch(name='locked', files={'inner.txt': 'x'})
        locked = path / 'sub'
        locked.mkdir()
        (locked / 'inner.txt').write_text('x')
        os.chmod(str(locked), 0o500)
        try:
            result = self.dispatch([self.item(path=str(path))])
        finally:
            os.chmod(str(locked), 0o700)
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'])
        self.assertIn(disposal.BLOCKED_REMOVAL_FAILED, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)), 'failed removal must not force')
        self.assertFalse(result['success'])

    def test_receipt_outside_approved_root_blocks_deletion(self):
        path = self.scratch()
        result = self.dispatch(
            [self.item()], receipt_path=self.root / 'outside-receipts' / 'r.json')
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'])
        self.assertIn(disposal.BLOCKED_RECEIPT_DESTINATION, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)))
        self.assertFalse(result['receipt_written'])
        self.assertFalse(result['success'])


class SourceGuardTests(unittest.TestCase):
    def test_deletion_path_contains_no_force_and_no_ignore_errors(self):
        source = (PKG / 'disposal.py').read_text()
        self.assertNotIn('ignore_errors', source,
                         'ignore_errors would swallow a failed removal')
        command = disposal.worktree_remove_command('/repo', '/tree')
        self.assertFalse([p for p in command if p.startswith('--force')])
        self.assertEqual(['git', '-C', '/repo', 'worktree', 'remove', '/tree'],
                         command)


if __name__ == '__main__':
    unittest.main(verbosity=2)
