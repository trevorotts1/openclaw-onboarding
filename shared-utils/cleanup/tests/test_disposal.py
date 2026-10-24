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


class _HostileItem(dict):
    """A mapping that raises while it is being typed."""

    def get(self, *args, **kwargs):
        raise RuntimeError('record reads its own fields unreliably')


class MalformedRecordTests(Base):
    """MISSING and MALFORMED input is typed UNKNOWN. Never a crash, never a
    silent ELIGIBLE, never a guessed default."""

    def test_non_mapping_records_are_typed_unknown_not_exceptions(self):
        live = self.scratch(name='live')
        for bad in (None, 'unit', ['unit'], 7):
            with self.subTest(bad=bad):
                result = self.dispatch([bad])
                record = result['items'][0]
                self.assertEqual(disposal.UNKNOWN, record['disposition'])
                self.assertIn(disposal.UNKNOWN_MALFORMED_ITEM, record['reasons'])
                self.assertFalse(record['disposed'])
                self.assertFalse(result['success'])
                self.assertEqual('INCOMPLETE', result['status'])
        self.assertTrue(os.path.lexists(str(live)),
                        'an untypeable record deletes nothing')

    def test_evaluate_types_a_malformed_record_without_raising(self):
        for bad in (None, 'unit', ['unit'], 7, {'id': 5, 'consumers': 7}):
            with self.subTest(bad=bad):
                record = disposal.evaluate(
                    bad, approved_root=self.approved,
                    expected_device=self.device, preserve_content=True)
                self.assertEqual(disposal.UNKNOWN, record['disposition'])
                self.assertIn(disposal.UNKNOWN_MALFORMED_ITEM, record['reasons'])

    def test_wrong_shaped_list_fields_are_malformed_unknown(self):
        path = self.scratch()
        for field in ('consumers', 'lease_ids', 'remote_merge_proof_ids',
                      'preservation_receipt_ids'):
            with self.subTest(field=field):
                result = self.dispatch([self.item(**{field: 7})])
                record = result['items'][0]
                self.assertEqual(disposal.UNKNOWN, record['disposition'])
                self.assertIn(disposal.UNKNOWN_MALFORMED_ITEM, record['reasons'])
                self.assertTrue(os.path.lexists(str(path)),
                                'a malformed record is never deleted')

    def test_a_record_that_raises_while_typed_is_unknown_not_a_crash(self):
        live = self.scratch(name='live')
        result = self.dispatch([self.item(id='live', path=str(live)),
                                _HostileItem()])
        self.assertEqual(2, len(result['items']))
        self.assertEqual(disposal.UNKNOWN, result['items'][1]['disposition'])
        self.assertIn(disposal.UNKNOWN_MALFORMED_ITEM,
                      result['items'][1]['reasons'])
        self.assertTrue(result['items'][0]['disposed'])
        self.assertTrue(result['receipt_written'],
                        'a bad record never strands a committed deletion')

    def test_one_bad_record_never_aborts_the_batch_or_strands_a_deletion(self):
        first = self.scratch(name='first')
        second = self.scratch(name='second')
        third = self.scratch(name='third')
        result = self.dispatch([
            self.item(id='first', path=str(first)), None,
            self.item(id='second', path=str(second)), 'unit', ['unit'], 7,
            _HostileItem(), self.item(id='third', path=str(third))])
        self.assertTrue(result['receipt_written'])
        self.assertTrue(result['receipt_read_back'])
        self.assertEqual({'ELIGIBLE': 3, 'DEFERRED': 0, 'BLOCKED': 0,
                          'UNKNOWN': 5}, result['counts'])
        self.assertEqual('INCOMPLETE', result['status'])
        self.assertFalse(result['success'])
        deleted = {entry['id']: entry for entry in result['deletions']}
        self.assertEqual({'first', 'second', 'third'}, set(deleted))
        for name in ('first', 'second', 'third'):
            self.assertTrue(deleted[name]['absence']['absent'])
            self.assertEqual(os.path.realpath(deleted[name]['path']),
                             deleted[name]['canonical_path'])
        # no stranded removal: every deletion is on disk with actual absence
        on_disk = json.loads((self.receipts / 'disposal-receipt.json').read_text())
        self.assertEqual({'first', 'second', 'third'},
                         {entry['id'] for entry in on_disk['deletions']})
        for record in on_disk['items']:
            if record.get('disposed'):
                self.assertIn('absence', record)
                self.assertTrue(record['absence']['absent'])
                self.assertIn('disposal_receipt_id', record)
                self.assertTrue(record['preserved'].get('verified'))


class ApprovedRootTests(Base):
    def test_missing_approved_root_is_unknown_volume_identity(self):
        missing_root = self.root / 'no-such-root'
        path = self.approved / 'scratch' / 'unit'
        path.mkdir(parents=True)
        (path / 'notes.txt').write_text('keep')
        record = disposal.evaluate(
            self.item(), approved_root=missing_root,
            expected_device=self.device, preserve_content=True)
        self.assertEqual(disposal.UNKNOWN, record['disposition'])
        self.assertIn(disposal.UNKNOWN_VOLUME_IDENTITY, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)))
        result = disposal.dispatch(
            [self.item()], approved_root=missing_root,
            expected_device=self.device,
            receipt_path=self.receipts / 'disposal-receipt.json',
            preserve_content=True, preserved_root=self.preserved)
        self.assertFalse(result['success'])
        self.assertEqual(disposal.UNKNOWN, result['items'][0]['disposition'])
        self.assertTrue(os.path.lexists(str(path)),
                        'an unstatable volume identity deletes nothing')


class PreservationProofTests(Base):
    def test_preserve_content_wins_over_an_existing_preserved_root(self):
        self.preserved.mkdir(parents=True)
        path = self.scratch(files={'unique.txt': 'only copy'})
        result = self.dispatch([self.item()])
        record = result['items'][0]
        self.assertEqual(disposal.ELIGIBLE, record['disposition'], record['reason'])
        self.assertTrue(record['disposed'])
        self.assertEqual('immediate_copy', record['checks']['preservation'])
        preserved = record['preserved']
        self.assertTrue(preserved.get('verified'),
                        'the module copies content before it deletes')
        self.assertEqual('only copy',
                         (Path(preserved['destination']) / 'unique.txt').read_text())
        self.assertFalse(os.path.lexists(str(path)))

    def test_a_second_batch_is_still_preserved_content(self):
        self.preserved.mkdir(parents=True)
        first = self.scratch(name='one', files={'unique.txt': 'first only'})
        self.dispatch([self.item(id='one', path=str(first))])
        second = self.scratch(name='two', files={'unique.txt': 'second only'})
        result = self.dispatch([self.item(id='two', path=str(second))])
        record = result['items'][0]
        self.assertEqual(disposal.ELIGIBLE, record['disposition'], record['reason'])
        self.assertTrue(record['preserved'].get('verified'),
                        'a preserved root left by an earlier batch is not proof')
        self.assertEqual('second only',
                         (Path(record['preserved']['destination'])
                          / 'unique.txt').read_text())
        self.assertFalse(os.path.lexists(str(second)))

    def test_existing_preserved_root_alone_is_not_preservation_proof(self):
        self.preserved.mkdir(parents=True)
        path = self.scratch(files={'unique.txt': 'only copy'})
        result = self.dispatch([self.item(preservation_receipt_ids=[])],
                               preserve_content=False)
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'])
        self.assertIn(disposal.BLOCKED_MISSING_PRESERVATION, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)),
                        'unproven content must survive')
        self.assertEqual('only copy', (path / 'unique.txt').read_text())

    def test_caller_preserved_needs_per_resource_receipts(self):
        self.preserved.mkdir(parents=True)
        path = self.scratch()
        result = self.dispatch(
            [self.item(preservation_receipt_ids=['saved-artifact'])],
            preserve_content=False)
        record = result['items'][0]
        self.assertEqual(disposal.ELIGIBLE, record['disposition'], record['reason'])
        self.assertEqual('caller_preserved', record['checks']['preservation'])
        self.assertEqual(['saved-artifact'],
                         record['preserved'].get('receipt_ids'))
        self.assertTrue(record['disposed'])
        self.assertEqual([], os.listdir(str(self.preserved)),
                         'caller_preserved makes no copy of its own')


class OwnershipProofTests(Base):
    def test_a_malformed_ownership_receipt_is_not_ownership(self):
        path = self.scratch()
        for bad in (5, {'id': 'x'}, [''], '', [None], ['ok', 5]):
            with self.subTest(bad=bad):
                result = self.dispatch([self.item(ownership_receipt_id=bad)])
                record = result['items'][0]
                self.assertEqual(disposal.BLOCKED, record['disposition'])
                self.assertIn(disposal.BLOCKED_UNOWNED, record['reasons'])
                self.assertTrue(os.path.lexists(str(path)),
                                'unverified ownership deletes nothing')


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
