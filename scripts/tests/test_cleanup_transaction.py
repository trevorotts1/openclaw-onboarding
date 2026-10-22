"""Skill 06 cleanup-transaction fault tests (Master Plan v3.0 C3).

Run sequentially, one heavy job at a time:
  python3 -m pytest scripts/tests/test_cleanup_transaction.py -q
Covers: the 8-condition eligibility contract (plan 8.2), dirty work never
deleted (CLEANUP_BLOCKED_UNPRESERVED_WORK), no --force (S15 refusal set),
interrupted cleanup restart is idempotent (S14), volume disconnect stops
writes with no metadata pruning (S16), and the receipt's logical bytes +
actual free-space change on BOTH drives.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import cleanup_transaction as ct


class Fixture:
    """Disposable run root: one real worktree, one scratch subtree."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.run_root = self.base / 'run'
        self.run_root.mkdir()
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'f.txt').write_text('x')
        subprocess.run(['git', '-C', str(self.repo), 'add', 'f.txt'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c',
                        'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'i'],
                       check=True)
        self.worktree = self.run_root / 'lane-1'
        subprocess.run(['git', '-C', str(self.repo), 'worktree', 'add',
                        '-q', '--detach', str(self.worktree), 'HEAD'],
                       check=True, capture_output=True)
        self.outputs = self.run_root / 'lane-1-scratch'
        (self.outputs / 'nested').mkdir(parents=True)
        (self.outputs / 'nested' / 'big.bin').write_bytes(b'0' * 4096)
        self.state = self.run_root / 'control'
        self.state.mkdir()
        self.volume = ct.volume_identity(self.run_root)
        self.ledger = [self.worktree, self.outputs]

    def manifest(self):
        return [{'path': str(self.outputs), 'kind': 'scratch',
                 'bytes': 4096}]

    def proof(self):
        return {'in_target': True, 'recovery_ref': None,
                'merge_method': 'merge', 'merge_commit': 'a' * 40,
                'base_sha': 'b' * 40, 'candidate_sha': 'c' * 40}

    def run(self, **kw):
        args = dict(target_path=str(self.worktree),
                    run_root=str(self.run_root),
                    state_dir=str(self.state),
                    internal_root='/',
                    external_root=str(self.base),
                    ownership_ledger=[str(p) for p in self.ledger],
                    expected_volume_identity=self.volume,
                    current_volume_identity=self.volume,
                    deletion_manifest=self.manifest(),
                    batch_id='b1', repo_path=str(self.repo),
                    worktree_status={'uncommitted': [], 'untracked': [],
                                     'submodules': [],
                                     'ignored_regenerable': []},
                    patch_proof=self.proof(),
                    evidence_read_back=True,
                    preserved_evidence_paths=['control/state.json'])
        args.update(kw)
        return ct.run_cleanup(**args)

    def cleanup(self):
        self.tmp.cleanup()


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.cleanup()

    def test_eligible_when_all_8_hold(self):
        result, checks = ct.check_eligibility(
            target_path=str(self.fx.worktree), run_root=str(self.fx.run_root),
            ownership_ledger=[str(p) for p in self.fx.ledger],
            expected_volume_identity=self.fx.volume,
            current_volume_identity=self.fx.volume,
            worktree_status={'uncommitted': [], 'untracked': [],
                             'submodules': [], 'ignored_regenerable': []},
            patch_proof=self.fx.proof(), evidence_read_back=True,
            deletion_manifest=self.fx.manifest())
        self.assertEqual(result, 'ELIGIBLE', checks)
        self.assertEqual({c['name'] for c in checks}, set(ct.CONDITIONS))
        self.assertTrue(all(c['ok'] for c in checks), checks)

    def test_dirty_untracked_work_never_deleted(self):
        for dirty in ({'uncommitted': ['f.py'], 'untracked': [],
                       'submodules': [], 'ignored_regenerable': []},
                      {'uncommitted': [], 'untracked': ['new.py'],
                       'submodules': [], 'ignored_regenerable': []},
                      {'uncommitted': [], 'untracked': [],
                       'submodules': ['sm'], 'ignored_regenerable': []}):
            with self.assertRaises(ct.EligibilityFailure) as cm:
                self.fx.run(worktree_status=dirty)
            self.assertEqual(cm.exception.result,
                             ct.CLEANUP_BLOCKED_UNPRESERVED_WORK)
        self.assertTrue(self.fx.worktree.exists())   # nothing removed

    def test_s15_symlink_escape_and_unowned_refused(self):
        evil = self.fx.base / 'elsewhere'
        evil.mkdir()
        link = self.fx.run_root / 'lane-link'
        os.symlink(evil, link)
        self.fx.ledger.append(link)
        with self.assertRaises(ct.EligibilityFailure):
            self.fx.run(target_path=str(link))
        self.assertTrue(evil.exists())               # escape target intact
        # unowned folder (not in the ledger)
        rogue = self.fx.run_root / 'unowned'
        rogue.mkdir()
        with self.assertRaises(ct.EligibilityFailure) as cm:
            self.fx.run(target_path=str(rogue))
        self.assertEqual(cm.exception.result, ct.CLEANUP_BLOCKED)
        self.assertTrue(rogue.exists())
        # the run root itself is never deletable
        with self.assertRaises(ct.EligibilityFailure):
            self.fx.run(target_path=str(self.fx.run_root))

    def test_s15_no_force_in_removal_command(self):
        cmd = ct.worktree_remove_cmd(self.fx.repo, self.fx.worktree)
        self.assertNotIn('--force', cmd)
        self.assertNotIn('-f', cmd)

    def test_s16_volume_disconnect_stops_writes_no_metadata_pruning(self):
        listing_before = subprocess.run(
            ['git', '-C', str(self.fx.repo), 'worktree', 'list'],
            capture_output=True, text=True, check=True).stdout
        with self.assertRaises(ct.VolumeUnavailable):
            self.fx.run(current_volume_identity='999-other-volume')
        listing_after = subprocess.run(
            ['git', '-C', str(self.fx.repo), 'worktree', 'list'],
            capture_output=True, text=True, check=True).stdout
        self.assertEqual(listing_before, listing_after)   # no prune
        self.assertTrue(self.fx.outputs.exists())          # no writes

    def test_manifest_forbidden_kind_or_escape_refused(self):
        with self.assertRaises(ct.EligibilityFailure):
            self.fx.run(deletion_manifest=[
                {'path': str(self.fx.outputs), 'kind': 'secret_store',
                 'bytes': 4096}])
        with self.assertRaises(ct.EligibilityFailure):
            self.fx.run(deletion_manifest=[
                {'path': str(self.fx.base / 'outside'), 'kind': 'scratch',
                 'bytes': 1}])
        self.assertTrue(self.fx.outputs.exists())


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.cleanup()

    def test_receipt_records_logical_bytes_and_df_both_drives(self):
        receipt = self.fx.run()
        self.assertEqual(receipt['result'], ct.CLEANUP_DONE)
        self.assertEqual(receipt['logical_bytes_deleted'], 4096)
        self.assertGreater(receipt['logical_kib_du'], 0)
        for drive in ('internal_ssd_root', 'external_mac_mini_m4'):
            free = receipt['free_space'][drive]
            self.assertIn('before_avail_kib', free)
            self.assertIn('after_avail_kib', free)
            self.assertEqual(free['delta_kib'],
                             free['after_avail_kib'] - free['before_avail_kib'])
        self.assertFalse(self.fx.outputs.exists())
        self.assertFalse(self.fx.worktree.exists())
        self.assertEqual(receipt['removed']['method'],
                         'git worktree remove (NO --force)')

    def test_s14_interrupted_cleanup_restart_is_idempotent(self):
        with self.assertRaises(ct.CleanupInterrupted):
            self.fx.run(fault_after='outputs_deleted')
        # outputs already gone, worktree + journal still present
        self.assertFalse(self.fx.outputs.exists())
        self.assertTrue(self.fx.worktree.exists())
        receipt = self.fx.run()                       # restart
        self.assertEqual(receipt['result'], ct.CLEANUP_DONE)
        self.assertEqual(receipt['logical_bytes_deleted'], 4096)  # once
        self.assertFalse(self.fx.worktree.exists())
        # third run returns the same receipt, no double count
        again = self.fx.run()
        self.assertEqual(again['logical_bytes_deleted'], 4096)
        self.assertEqual(again['free_space'], receipt['free_space'])

    def test_failed_worktree_remove_preserves_tree(self):
        # repo_path pointing at a non-repo makes git worktree remove fail:
        # the tree must be preserved with the reason recorded, never forced.
        receipt = self.fx.run(repo_path=str(self.fx.base))
        self.assertEqual(receipt['result'], ct.CLEANUP_BLOCKED)
        self.assertNotEqual(receipt['removed']['remove_rc'], 0)
        self.assertTrue(self.fx.worktree.exists())


if __name__ == '__main__':
    unittest.main()
