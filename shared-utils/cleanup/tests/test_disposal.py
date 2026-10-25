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
from unittest import mock

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
        store = self.root / 'caller-store' / 'unit'
        store.parent.mkdir(parents=True)
        shutil.copytree(str(path), str(store))
        result = self.dispatch(
            [self.item(preservation_receipt_ids=['saved-artifact'],
                       preserved_path=str(store))],
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


class ReceiptStageTests(Base):
    """D2: a deletion is never committed without its receipt. The receipt
    target is proven writable before the first removal, and a write that still
    fails comes back typed, with the real deletions recorded inline."""

    def test_unwritable_receipt_target_refuses_before_any_deletion(self):
        path = self.scratch(files={'unique.txt': 'only copy'})
        target = self.receipts / 'disposal-receipt.json'
        target.mkdir()  # os.replace onto a directory cannot succeed
        try:
            result = self.dispatch([self.item()], receipt_path=target)
        except OSError as exc:
            self.fail(f'dispatch raised after deciding to delete: {exc!r}; '
                      f'resource survives={os.path.lexists(str(path))}')
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'])
        self.assertIn(disposal.BLOCKED_RECEIPT_DESTINATION, record['reasons'])
        self.assertFalse(record['disposed'])
        self.assertTrue(os.path.lexists(str(path)),
                        'no receipt possible, so nothing is deleted')
        self.assertEqual('only copy', (path / 'unique.txt').read_text())
        self.assertEqual([], result['deletions'])
        self.assertFalse(result['receipt_written'])
        self.assertFalse(result['success'])

    def test_receipt_write_failing_after_removal_is_typed_not_raised(self):
        path = self.scratch()
        failure = OSError(28, 'No space left on device')
        with mock.patch.object(disposal, '_write_receipt', side_effect=failure):
            try:
                result = self.dispatch([self.item()])
            except OSError as exc:
                self.fail(f'committed deletion stranded by a raise: {exc!r}')
        self.assertFalse(os.path.lexists(str(path)), 'the removal really happened')
        self.assertFalse(result['receipt_written'])
        self.assertFalse(result['receipt_read_back'])
        self.assertFalse(result['success'])
        self.assertEqual('INCOMPLETE', result['status'])
        self.assertTrue(result['reason'].startswith(
            disposal.BLOCKED_RECEIPT_DESTINATION))
        # the deletion is recorded inline with its exact path and absence proof
        self.assertEqual(['unit'], [d['id'] for d in result['deletions']])
        deletion = result['deletions'][0]
        self.assertEqual(os.path.realpath(str(path)), deletion['canonical_path'])
        self.assertEqual({'path': str(path), 'lexists': False, 'absent': True},
                         deletion['absence'])

    def test_writable_receipt_destination_still_disposes(self):
        path = self.scratch()
        result = self.dispatch([self.item()])
        self.assertEqual('DISPATCHED', result['status'])
        self.assertTrue(result['success'])
        self.assertTrue(result['receipt_read_back'])
        self.assertFalse(os.path.lexists(str(path)))
        self.assertEqual(['disposal-receipt.json'], os.listdir(str(self.receipts)),
                         'the pre-flight probe leaves nothing behind')


class MissingFactTests(Base):
    """D4: an absent clean_state or consumers key is an unobserved fact,
    UNKNOWN, and never authorises disposal."""

    def test_missing_clean_state_or_consumers_is_unknown_not_disposal(self):
        for key, code in (('clean_state', disposal.UNKNOWN_CLEAN_STATE),
                          ('consumers', disposal.UNKNOWN_CONSUMER_STATE)):
            with self.subTest(missing=key):
                path = self.scratch(name=f'no-{key}')
                item = self.item(id=f'no-{key}', path=str(path))
                del item[key]
                result = self.dispatch([item])
                record = result['items'][0]
                self.assertEqual(disposal.UNKNOWN, record['disposition'])
                self.assertIn(code, record['reasons'])
                self.assertFalse(record['disposed'])
                self.assertEqual('INCOMPLETE', result['status'])
                self.assertFalse(result['success'])
                self.assertTrue(os.path.lexists(str(path)),
                                'a missing fact deletes nothing')

    def test_explicit_clean_state_and_empty_consumers_still_dispose(self):
        path = self.scratch()
        result = self.dispatch([self.item(clean_state='NOT_APPLICABLE',
                                          consumers=[])])
        self.assertEqual('DISPATCHED', result['status'])
        self.assertTrue(result['success'])
        self.assertFalse(os.path.lexists(str(path)))


class ContainmentTests(Base):
    """M3: contained-or-equal is one semantics, used for the receipt parent and
    for a caller copy that must sit outside the resource."""

    def test_receipt_directly_in_approved_root_is_accepted(self):
        path = self.scratch()
        result = self.dispatch([self.item()],
                               receipt_path=self.approved / 'disposal-receipt.json')
        record = result['items'][0]
        self.assertEqual(disposal.ELIGIBLE, record['disposition'], record['reason'])
        self.assertTrue(record['disposed'])
        self.assertEqual('DISPATCHED', result['status'])
        self.assertTrue(result['success'])
        self.assertFalse(os.path.lexists(str(path)))
        on_disk = json.loads((self.approved / 'disposal-receipt.json').read_text())
        self.assertEqual(['unit'], [d['id'] for d in on_disk['deletions']])

    def test_receipt_in_a_prefix_sibling_of_approved_root_is_outside(self):
        path = self.scratch()
        sibling = self.root / (self.approved.name + '-sibling')
        sibling.mkdir()
        result = self.dispatch([self.item()], receipt_path=sibling / 'r.json')
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'])
        self.assertIn(disposal.BLOCKED_RECEIPT_DESTINATION, record['reasons'])
        self.assertTrue(os.path.lexists(str(path)))

    def test_caller_copy_equal_to_or_containing_the_resource_is_not_preservation(self):
        for label in ('equal', 'ancestor'):
            with self.subTest(preserved_root=label):
                path = self.scratch(name=label, files={'unique.txt': 'only copy'})
                claimed = path if label == 'equal' else path.parent
                result = self.dispatch([self.item(id=label, path=str(path))],
                                       preserve_content=False,
                                       preserved_root=claimed)
                record = result['items'][0]
                self.assertEqual(disposal.BLOCKED, record['disposition'])
                self.assertIn(disposal.BLOCKED_MISSING_PRESERVATION,
                              record['reasons'])
                self.assertTrue(os.path.lexists(str(path)), 'the only copy survives')
                self.assertEqual('only copy', (path / 'unique.txt').read_text())


class RepairProofTests(Base):
    """Before/after proofs for the PBB-257 verdict defects. Every test here
    fails on the reviewed commit bd832e5f0 and passes on this repair."""

    def test_an_identity_cannot_steer_the_preserved_copy_outside_the_root(self):
        # defect 1: preserve() used the id as a raw path segment
        path = self.scratch(files={'unique.txt': 'only copy'})
        outside = self.root / 'OUTSIDE-PRESERVED-ROOT'
        outside.mkdir()
        result = self.dispatch([self.item(id='../../OUTSIDE-PRESERVED-ROOT/escaped')],
                               preserved_root=self.preserved)
        record = result['items'][0]
        self.assertNotEqual(disposal.ELIGIBLE, record['disposition'])
        self.assertFalse(record['disposed'])
        self.assertFalse((outside / 'escaped').exists(),
                         'a preserved copy may never land outside the preserved root')
        self.assertTrue(os.path.lexists(str(path)), 'the resource survives')
        self.assertEqual('only copy', (path / 'unique.txt').read_text())

    def test_preserve_refuses_a_destination_outside_the_preserved_root(self):
        path = self.scratch()
        self.preserved.mkdir(parents=True)
        outside = self.root / 'escape'
        outside.mkdir()
        for identity in ('../../escape', '/etc/kept', 'sub/name', 'feature/one'):
            with self.subTest(identity=identity):
                proof = disposal.preserve(str(path), str(self.preserved), identity)
                destination = Path(proof['destination']).resolve()
                self.assertTrue(
                    str(destination).startswith(str(self.preserved.resolve()) + os.sep),
                    f'preserved copy escaped the preserved root: {destination}')
                self.assertFalse((outside / 'escape').exists())
        for unusable in ('', '.', '..', '   '):
            with self.subTest(identity=unusable):
                with self.assertRaises(disposal.Refused):
                    disposal.preserve(str(path), str(self.preserved), unusable)

    def test_a_folded_identity_still_preserves_inside_the_preserved_root(self):
        path = self.scratch(name='one')
        proof = disposal.preserve(str(path), str(self.preserved), 'feature/one')
        self.assertTrue(proof['verified'])
        self.assertTrue(str(Path(proof['destination']).resolve()).startswith(
            str(self.preserved.resolve()) + os.sep),
            f"copy escaped the preserved root: {proof['destination']}")
        self.assertTrue((Path(proof['destination']) / 'notes.txt').exists())

    def test_symlink_component_guard_fires_on_mixed_path_forms(self):
        # defect 2: the guard compared root and path lexically and went quiet
        other = self.approved / 'other-place' / 'unit'
        other.mkdir(parents=True)
        (other / 'keep.txt').write_text('keep')
        bridge = self.approved / 'bridge'
        os.symlink(str(self.approved / 'other-place'), str(bridge))
        cwd = os.getcwd()
        os.chdir(str(self.root))
        try:
            result = disposal.dispatch(
                [self.item(path=str(bridge / 'unit'))],
                approved_root='approved',
                expected_device=self.device,
                receipt_path='approved/receipts/disposal-receipt.json',
                preserved_root='approved/preserved',
                preserve_content=True)
        finally:
            os.chdir(cwd)
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'], record['reason'])
        self.assertIn(disposal.BLOCKED_SYMLINK_ESCAPE, record['reasons'])
        self.assertFalse(record['disposed'])
        self.assertTrue((other / 'keep.txt').exists(),
                        'a symlinked component deletes nothing')

    def test_worktree_remove_command_refuses_force_in_every_spelling(self):
        # defect 3: the guard knew only the long form
        def authority(command):
            class Stub:
                @staticmethod
                def worktree_remove_cmd(repo_path, target_path):
                    return list(command)
            return Stub

        for spelling in ('-f', '-af', '--force', '--force=1', '--force=x'):
            with self.subTest(flag=spelling):
                command = ['git', '-C', '/repo', 'worktree', 'remove',
                           spelling, '/tree']
                with mock.patch.object(disposal, 'deletion_authority',
                                       return_value=authority(command)):
                    with self.assertRaises(disposal.Refused):
                        disposal.worktree_remove_command('/repo', '/tree')

    def test_worktree_remove_command_still_accepts_a_plain_removal(self):
        command = ['git', '-C', '/repo', 'worktree', 'remove', '/tree']
        with mock.patch.object(disposal, 'deletion_authority',
                               return_value=authority_for(command)):
            self.assertEqual(command,
                             disposal.worktree_remove_command('/repo', '/tree'))

    def test_a_claimed_caller_copy_with_no_content_is_not_preservation_proof(self):
        # defect 4 (first half): a directory merely existing is never proof
        self.preserved.mkdir(parents=True)
        path = self.scratch(files={'unique.txt': 'only copy'})
        result = self.dispatch(
            [self.item(preservation_receipt_ids=['claimed'])],
            preserve_content=False)
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'], record['reason'])
        self.assertIn(disposal.BLOCKED_MISSING_PRESERVATION, record['reasons'])
        self.assertFalse(record['disposed'])
        self.assertEqual([], result['deletions'])
        self.assertTrue(os.path.lexists(str(path)))
        self.assertEqual('only copy', (path / 'unique.txt').read_text())

    def test_a_proven_caller_copy_records_its_exact_external_path(self):
        # defect 4 (second half): the receipt names the exact external path
        self.preserved.mkdir(parents=True)
        path = self.scratch(files={'unique.txt': 'only copy'})
        store = self.root / 'caller-store' / 'unit'
        store.parent.mkdir(parents=True)
        shutil.copytree(str(path), str(store))
        result = self.dispatch(
            [self.item(preservation_receipt_ids=['claimed'],
                       preserved_path=str(store))],
            preserve_content=False)
        record = result['items'][0]
        self.assertEqual(disposal.ELIGIBLE, record['disposition'], record['reason'])
        self.assertTrue(record['disposed'])
        self.assertEqual(str(store.resolve()),
                         record['preserved']['destination'])
        self.assertTrue(record['preserved'].get('digest'))
        on_disk = json.loads((self.receipts / 'disposal-receipt.json').read_text())
        deletion = on_disk['deletions'][0]
        self.assertEqual(str(store.resolve()), deletion['preserved_destination'])
        self.assertEqual(record['preserved']['digest'],
                         deletion['preserved_digest'])
        self.assertTrue('preserved_proof' in deletion)
        self.assertTrue(os.path.lexists(str(store)))

    def test_a_caller_copy_that_differs_from_the_resource_is_not_proof(self):
        self.preserved.mkdir(parents=True)
        path = self.scratch(files={'unique.txt': 'only copy'})
        store = self.root / 'caller-store' / 'unit'
        store.parent.mkdir(parents=True)
        shutil.copytree(str(path), str(store))
        (store / 'unique.txt').write_text('half copy')
        result = self.dispatch(
            [self.item(preservation_receipt_ids=['claimed'],
                       preserved_path=str(store))],
            preserve_content=False)
        record = result['items'][0]
        self.assertEqual(disposal.BLOCKED, record['disposition'], record['reason'])
        self.assertTrue(os.path.lexists(str(path)),
                        'a partial copy never authorises a deletion')

    def test_a_wrong_type_batch_container_types_unknown_instead_of_raising(self):
        # defect 5: 'for item in items' ran before any typing
        for bad in (None, 5, {'a': 1}, 'unit'):
            with self.subTest(container=type(bad).__name__):
                result = self.dispatch(bad)
                self.assertEqual('INCOMPLETE', result['status'])
                self.assertFalse(result['success'])
                self.assertEqual(disposal.UNKNOWN,
                                 result['items'][0]['disposition'])
                self.assertIn(disposal.UNKNOWN_MALFORMED_ITEM,
                              result['items'][0]['reasons'])

    def test_a_whitespace_only_id_is_not_an_identity(self):
        # defect 6: a blank id was accepted as an identity
        path = self.scratch()
        result = self.dispatch([self.item(id='   ')])
        record = result['items'][0]
        self.assertEqual(disposal.UNKNOWN, record['disposition'])
        self.assertIn(disposal.UNKNOWN_MISSING_IDENTITY, record['reasons'])
        self.assertFalse(record['disposed'])
        self.assertTrue(os.path.lexists(str(path)))


class ThirdRepairProofTests(Base):
    """PBB-455: the absence proof is a measurement, and dispatch follows it.

    PBB-434's mutation pass left M2 ("absence proof always absent") SURVIVING
    at rc 0, 59 tests OK: nothing could tell a real absence proof from one that
    claims absence for a path still on disk. Both directions are pinned here --
    a genuinely proven absence dispatches, and a claim of absence for something
    still present never does.
    """

    def test_a_genuine_absence_proof_dispatches(self):
        path = self.scratch()
        # the instrument reads both polarities: still here is NOT absent
        self.assertEqual({'path': str(path), 'lexists': True, 'absent': False},
                         disposal.prove_absence(str(path)))
        result = self.dispatch([self.item()])
        self.assertEqual('DISPATCHED', result['status'])
        record = result['items'][0]
        self.assertTrue(record['disposed'])
        # gone after removal IS absent, proven at the exact recorded path
        self.assertEqual({'path': str(path), 'lexists': False, 'absent': True},
                         record['absence'])

    def test_a_proof_claiming_absence_for_a_path_still_present_never_dispatches(self):
        path = self.scratch()
        # the removal is made to leave the tree on disk, so any claim of
        # absence here is a claim about something still present
        with mock.patch.object(disposal, '_remove_tree', lambda _p: None):
            result = self.dispatch([self.item()])
        self.assertTrue(os.path.lexists(str(path)), 'the tree is still present')
        record = result['items'][0]
        self.assertEqual({'path': str(path), 'lexists': True, 'absent': False},
                         record['absence'],
                         'the proof must report what is on disk, not what is wanted')
        self.assertNotEqual(disposal.ELIGIBLE, record['disposition'])
        self.assertIn(disposal.BLOCKED_REMOVAL_FAILED, record['reasons'])
        self.assertFalse(record['disposed'])
        self.assertEqual([], result['deletions'])
        self.assertEqual('INCOMPLETE', result['status'])
        self.assertFalse(result['success'])


class SecondRepairProofTests(Base):
    """Before/after proofs for the PBB-312 verdict defects. Defects 1 and 2 fail
    on bd832e5f0 and a96a25e5 alike; defect 3 is the regression a96a25e5
    introduced (it passes on bd832e5f0). All three pass on this repair."""

    def test_a_remote_merge_proof_that_is_no_receipt_is_not_proof(self):
        # defect 1: a non-empty list was taken as proof; [''], [5], [None] are
        # not receipt references at all.
        for label, proofs in (('blank', ['']), ('int', [5]), ('bool', [True]),
                              ('mixed', ['ok', 5]), ('none', [None])):
            with self.subTest(proofs=label):
                path = self.scratch(name='proof-' + label,
                                    files={'unique.txt': 'only copy'})
                result = self.dispatch([self.item(
                    id='proof-' + label, resource_type='merged_worktree',
                    path=str(path), clean_state='CLEAN',
                    remote_merge_proof_ids=proofs,
                    preservation_receipt_ids=None)],
                    preserve_content=False)
                record = result['items'][0]
                self.assertNotEqual(disposal.ELIGIBLE, record['disposition'])
                self.assertIn(disposal.BLOCKED_MISSING_REMOTE_MERGE_PROOF,
                              record['reasons'])
                self.assertFalse(record['disposed'])
                self.assertTrue(os.path.lexists(str(path)),
                                'a proof that is no receipt deletes nothing')
                self.assertEqual('only copy', (path / 'unique.txt').read_text())

    def test_a_real_remote_merge_proof_still_disposes(self):
        # CONTROL for defect 1: expected to pass before and after the repair.
        path = self.scratch(name='proof-real')
        result = self.dispatch([self.item(
            resource_type='merged_worktree', path=str(path),
            clean_state='CLEAN', remote_merge_proof_ids=['remote-proof-1'],
            preservation_receipt_ids=None)], preserve_content=False)
        record = result['items'][0]
        self.assertEqual(disposal.ELIGIBLE, record['disposition'], record['reason'])
        self.assertTrue(record['disposed'])
        self.assertFalse(os.path.lexists(str(path)))

    def test_a_malformed_disposal_receipt_id_does_not_prove_prior_disposal(self):
        # defect 2: plain truthiness accepted 5 / True / {'a': 1} as a receipt.
        for label, receipt in (('blank-list', ['']), ('int', 5), ('bool', True),
                               ('mixed', ['ok', 5]), ('dict', {'a': 1})):
            with self.subTest(receipt=label):
                result = self.dispatch([self.item(
                    path=str(self.approved / 'scratch' / ('gone-' + label)),
                    disposal_receipt_id=receipt)])
                record = result['items'][0]
                self.assertNotIn(disposal.OK_ALREADY_DISPOSED, record['reasons'])
                self.assertNotEqual(disposal.ELIGIBLE, record['disposition'])
                self.assertIn(disposal.UNKNOWN_ABSENT_WITHOUT_RECEIPT,
                              record['reasons'])
                self.assertFalse(record['disposed'])
                self.assertFalse(result['success'])

    def test_a_real_disposal_receipt_still_proves_prior_disposal(self):
        # CONTROL for defect 2: expected to pass before and after the repair.
        result = self.dispatch([self.item(
            path=str(self.approved / 'scratch' / 'gone'),
            disposal_receipt_id='dispose-unit-1')])
        record = result['items'][0]
        self.assertEqual(disposal.ELIGIBLE, record['disposition'])
        self.assertIn(disposal.OK_ALREADY_DISPOSED, record['reasons'])
        self.assertTrue(record['disposed'])

    def test_evaluate_types_unreadable_content_and_never_raises(self):
        # defect 3: _tree_digest raised PermissionError out of evaluate().
        path, store = self._locked_pair('locked-evaluate')
        try:
            record = disposal.evaluate(
                self.item(path=str(path), preserved_path=str(store)),
                approved_root=self.approved, expected_device=self.device,
                preserved_paths=[str(self.preserved)], preserve_content=False)
        finally:
            self._unlock(path, store)
        self.assertEqual(disposal.UNKNOWN, record['disposition'])
        self.assertIn(disposal.UNKNOWN_UNREADABLE_CONTENT, record['reasons'])
        self.assertNotIn(disposal.OK_ELIGIBLE, record['reasons'])

    def test_dispatch_types_unreadable_content_and_deletes_nothing(self):
        path, store = self._locked_pair('locked-dispatch')
        try:
            result = self.dispatch(
                [self.item(path=str(path), preserved_path=str(store))],
                preserve_content=False)
        finally:
            self._unlock(path, store)
        record = result['items'][0]
        self.assertEqual(disposal.UNKNOWN, record['disposition'])
        self.assertIn(disposal.UNKNOWN_UNREADABLE_CONTENT, record['reasons'])
        self.assertNotIn(disposal.UNKNOWN_MALFORMED_ITEM, record['reasons'],
                         'an I/O failure is not a malformed record')
        self.assertFalse(record['disposed'])
        self.assertTrue(os.path.lexists(str(path)),
                        'unreadable content deletes nothing')

    def _locked_pair(self, name):
        if not hasattr(os, 'geteuid') or os.geteuid() == 0:
            self.skipTest('root can read any file: the lock cannot be proven')
        path = self.scratch(name=name, files={'unique.txt': 'only copy',
                                             'locked.bin': 'x'})
        store = self.root / ('caller-store-' + name) / name
        store.parent.mkdir(parents=True)
        shutil.copytree(str(path), str(store))
        os.chmod(str(path / 'locked.bin'), 0o000)
        os.chmod(str(store / 'locked.bin'), 0o000)
        return path, store

    def _unlock(self, path, store):
        for locked in (path / 'locked.bin', store / 'locked.bin'):
            if locked.exists():
                os.chmod(str(locked), 0o600)


def authority_for(command):
    class Stub:
        @staticmethod
        def worktree_remove_cmd(repo_path, target_path):
            return list(command)
    return Stub


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
