"""Skill 06 post-merge cleanup transaction (Master Plan v3.0 section 8,
checklist C3). Stdlib-only, deterministic.

Implements the cleanup eligibility contract (plan 8.2) as code — all 8
conditions — plus the cleanup sequence of plan 8.3:
  - dirty/untracked/uncommitted work is NEVER deleted
    (CLEANUP_BLOCKED_UNPRESERVED_WORK);
  - no --force anywhere: `git worktree remove` without force, and a failed
    removal preserves the tree with the reason recorded;
  - symlink escapes, path escapes, the run root itself and unowned folders
    are refused (S15);
  - a missing/mismatched/unwritable volume stops ALL writes, with no
    metadata pruning (S16);
  - an interrupted cleanup resumes idempotently: no double-counted bytes,
    no different path deleted on the second run (S14);
  - the receipt records logical bytes deleted AND the actual free-space
    change on BOTH drives (df before/after).
"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

CLEANUP_BLOCKED_UNPRESERVED_WORK = 'CLEANUP_BLOCKED_UNPRESERVED_WORK'
CLEANUP_BLOCKED = 'CLEANUP_BLOCKED'
CLEANUP_DONE = 'CLEANUP_DONE'

REGENERABLE_KINDS = frozenset({'generated_output', 'scratch', 'cache',
                               'temp_build', 'log_segment', 'trace'})
FORBIDDEN_KINDS = frozenset({'secret_store', 'source_asset',
                             'approved_deliverable', 'active_fixture',
                             'graphify_dataset'})

CONDITIONS = (
    'path_canonicalized_beneath_run_root',
    'in_ownership_ledger',
    'volume_identity_ok',
    'workers_stopped_no_dependent_consumers',
    'worktree_status_checked',
    'patch_proven_in_target_or_recovery_ref',
    'evidence_compacted_and_read_back',
    'deletion_manifest_regenerable_only',
)


class EligibilityFailure(Exception):
    def __init__(self, result, checks):
        self.result = result
        self.checks = checks
        failed = [c for c in checks if not c['ok']]
        super().__init__(f'{result}: ' + '; '.join(
            f"{c['name']} ({c['detail']})" for c in failed))


class VolumeUnavailable(Exception):
    """Volume identity mismatch or unwritable: stop writes, prune nothing."""


class CleanupInterrupted(Exception):
    """Test seam / crash marker: the journal keeps progress for resume."""


def volume_identity(path):
    """Cheap stable identity of the volume holding `path` (device number).
    Production callers may pass their recorded volume UUID instead — the
    contract is an exact string match either way."""
    return str(Path(path).resolve().stat().st_dev)


def worktree_remove_cmd(repo_path, target_path):
    """The EXACT removal command. Never contains --force (plan 8.3)."""
    return ['git', '-C', str(repo_path), 'worktree', 'remove', str(target_path)]


def _real(p):
    return Path(p).resolve()


def _beneath(child, root):
    try:
        return _real(child) != _real(root) and str(_real(child)).startswith(
            str(_real(root)) + os.sep)
    except OSError:
        return False


def _logical_bytes(path):
    """(sum of file sizes, du-style KiB) of a file or tree."""
    p = Path(path)
    if p.is_file():
        st = p.stat()
        return st.st_size, (st.st_blocks * 512) // 1024
    total = 0
    kib = 0
    for dirpath, _dirs, files in os.walk(p, followlinks=False):
        for name in files:
            fp = Path(dirpath) / name
            try:
                st = fp.lstat()
            except OSError:
                continue
            if not fp.is_symlink():
                total += st.st_size
                kib += (st.st_blocks * 512) // 1024
    return total, kib


def _free_kib(path):
    return shutil.disk_usage(path).free // 1024


def check_eligibility(*, target_path, run_root, ownership_ledger,
                      expected_volume_identity, current_volume_identity,
                      volume_writable=True, consumers=(), worktree_status=None,
                      patch_proof=None, evidence_read_back=False,
                      deletion_manifest=()):
    """Plan 8.2 eligibility contract as the 8 named checks. Returns
    (result, checks). Result is CLEANUP_DONE-ready ('ELIGIBLE'),
    CLEANUP_BLOCKED_UNPRESERVED_WORK when uncommitted work exists, or
    CLEANUP_BLOCKED otherwise."""
    checks = []

    def add(name, ok, detail):
        checks.append({'name': name, 'ok': bool(ok), 'detail': detail})

    target = Path(target_path)
    root = Path(run_root)
    # 1. exact path canonicalized, beneath run root, not root/parent/symlink
    try:
        target_real = _real(target)
        root_real = _real(root)
        is_link = target.is_symlink()
        beneath = (target_real != root_real
                   and str(target_real).startswith(str(root_real) + os.sep))
        not_parent = not str(root_real).startswith(str(target_real) + os.sep)
        add(CONDITIONS[0], beneath and not_parent and not (
            is_link and not _beneath(target, root)),
            f'path={target_real} root={root_real} symlink={is_link}')
    except OSError as e:
        add(CONDITIONS[0], False, f'canonicalization failed: {e}')
    # 2. present in the ownership ledger, never unowned
    ledger = {str(_real(p)) for p in ownership_ledger}
    add(CONDITIONS[1], str(_real(target)) in ledger,
        'owned' if str(_real(target)) in ledger else 'unowned folder')
    # 3. expected volume identity still matches and is writable
    vol_ok = (current_volume_identity == expected_volume_identity
              and volume_writable)
    add(CONDITIONS[2], vol_ok,
        f'expected={expected_volume_identity} '
        f'current={current_volume_identity} writable={volume_writable}')
    # 4. workers stopped, no dependent consumer
    add(CONDITIONS[3], not consumers,
        'none' if not consumers else f'consumers={list(consumers)}')
    # 5. worktree status checked incl. untracked/ignored/submodules
    st = worktree_status or {}
    uncommitted = st.get('uncommitted', [])
    untracked = st.get('untracked', [])
    submodules = st.get('submodules', [])
    ignored_regenerable = st.get('ignored_regenerable', [])
    dirty = bool(uncommitted or untracked or submodules)
    manifest_paths = [str(_real(e['path'])) for e in deletion_manifest]
    ignored_covered = all(str(_real(p)) in manifest_paths
                          for p in ignored_regenerable)
    add(CONDITIONS[4], not dirty and ignored_covered,
        f'uncommitted={uncommitted} untracked={untracked} '
        f'submodules={submodules} ignored_regenerable={ignored_regenerable}')
    # 6. patch proven in verified target or retained recovery ref
    proof = patch_proof or {}
    proven = bool(proof.get('in_target') or proof.get('recovery_ref'))
    add(CONDITIONS[5], proven,
        f"in_target={proof.get('in_target')} "
        f"recovery_ref={proof.get('recovery_ref')}")
    # 7. evidence compacted and read back
    add(CONDITIONS[6], bool(evidence_read_back),
        f'read_back={bool(evidence_read_back)}')
    # 8. deletion manifest lists regenerable data only, inside run root
    bad = []
    for e in deletion_manifest:
        kind = e.get('kind')
        if kind in FORBIDDEN_KINDS or kind not in REGENERABLE_KINDS:
            bad.append(f"{e.get('path')} kind={kind}")
            continue
        if not _beneath(e['path'], root) or Path(e['path']).is_symlink():
            bad.append(f"{e.get('path')} escapes run root")
    add(CONDITIONS[7], not bad and all(
        'bytes' in e for e in deletion_manifest),
        'ok' if not bad else '; '.join(bad))

    if dirty:
        return CLEANUP_BLOCKED_UNPRESERVED_WORK, checks
    if all(c['ok'] for c in checks):
        return 'ELIGIBLE', checks
    return CLEANUP_BLOCKED, checks


def run_cleanup(*, target_path, run_root, state_dir, internal_root,
                external_root, ownership_ledger, expected_volume_identity,
                current_volume_identity, deletion_manifest,
                batch_id, repo_path=None, volume_writable=True,
                consumers=(), worktree_status=None, patch_proof=None,
                evidence_read_back=False, preserved_evidence_paths=(),
                now=time.time, fault_after=None):
    """Execute the plan 8.3 sequence as resumable, idempotent phases.

    fault_after: test seam — raise CleanupInterrupted right after the named
    phase completes, to prove a restart neither double-counts bytes nor
    deletes a different path (S14).
    """
    state_dir = Path(state_dir)
    tag = Path(target_path).name.replace(os.sep, '_')
    journal_path = state_dir / f'cleanup-journal-{tag}.json'
    receipt_path = state_dir / f'cleanup-receipt-{tag}.json'

    # S16: volume check comes FIRST — mismatch stops all writes, including
    # the journal, and nothing (especially git metadata) is pruned.
    if current_volume_identity != expected_volume_identity or not volume_writable:
        raise VolumeUnavailable(
            f'volume identity {current_volume_identity!r} != '
            f'{expected_volume_identity!r} or not writable: writes stopped, '
            'no metadata pruning')

    result, checks = check_eligibility(
        target_path=target_path, run_root=run_root,
        ownership_ledger=ownership_ledger,
        expected_volume_identity=expected_volume_identity,
        current_volume_identity=current_volume_identity,
        volume_writable=volume_writable, consumers=consumers,
        worktree_status=worktree_status, patch_proof=patch_proof,
        evidence_read_back=evidence_read_back,
        deletion_manifest=deletion_manifest)
    if result != 'ELIGIBLE':
        raise EligibilityFailure(result, checks)

    journal = {'batch_id': batch_id, 'target': str(target_path),
               'phases': [], 'deleted': {}, 'logical_bytes_deleted': 0,
               'logical_kib_du': 0}
    if journal_path.exists():
        journal = json.loads(journal_path.read_text())

    def phase_done(name):
        return name in journal['phases']

    def mark(name):
        if name not in journal['phases']:
            journal['phases'].append(name)
        journal_path.write_text(json.dumps(journal, indent=1, sort_keys=True))
        if fault_after == name:
            raise CleanupInterrupted(f'fault after {name}')

    if receipt_path.exists() and phase_done('receipt_written'):
        return json.loads(receipt_path.read_text())

    if not phase_done('df_before'):
        journal['df_before'] = {
            'internal_kib': _free_kib(internal_root),
            'external_kib': _free_kib(external_root)}
        mark('df_before')

    if not phase_done('outputs_deleted'):
        for entry in deletion_manifest:
            p = Path(entry['path'])
            key = str(_real(p))
            if key in journal['deleted']:
                continue                      # S14: never count twice
            # containment/symlink/ownership rechecked immediately before
            if p.is_symlink() or not _beneath(p, run_root):
                raise EligibilityFailure(CLEANUP_BLOCKED, [{
                    'name': CONDITIONS[7], 'ok': False,
                    'detail': f'{p} escapes run root at deletion time'}])
            if p.exists():
                logical, kib = _logical_bytes(p)
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                journal['deleted'][key] = {'bytes': logical, 'kib': kib}
                journal['logical_bytes_deleted'] += logical
                journal['logical_kib_du'] += kib
        mark('outputs_deleted')

    removed = {'path': str(target_path),
               'method': 'git worktree remove (NO --force)',
               'remove_rc': None, 'verified': ''}
    if not phase_done('worktree_removed'):
        if repo_path:
            cmd = worktree_remove_cmd(repo_path, target_path)
            assert '--force' not in cmd
            rc = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=120).returncode
            removed['remove_rc'] = rc
            if rc != 0:
                # plan 8.3: safe removal failed -> preserve, record, never force
                removed['verified'] = 'removal failed: tree preserved'
                journal['removed'] = removed
                mark('worktree_failed')
                return {'result': CLEANUP_BLOCKED, 'removed': removed,
                        'eligibility_contract': {c['name']: c['ok']
                                                 for c in checks}}
        else:
            if Path(target_path).is_dir():
                shutil.rmtree(target_path)
            removed['remove_rc'] = 0
            removed['method'] = 'path removal (NO --force)'
        mark('worktree_removed')
    if journal.get('removed'):
        removed = journal['removed']

    if not phase_done('verified'):
        gone = not Path(target_path).exists()
        registered = True
        if repo_path:
            out = subprocess.run(
                ['git', '-C', str(repo_path), 'worktree', 'list'],
                capture_output=True, text=True, timeout=60).stdout
            registered = str(target_path) in out
        removed['verified'] = ('path gone' if gone else 'path still present')
        if not gone or registered:
            journal['removed'] = removed
            mark('verified_failed')
            return {'result': CLEANUP_BLOCKED, 'removed': removed,
                    'eligibility_contract': {c['name']: c['ok']
                                             for c in checks}}
        journal['removed'] = removed
        mark('verified')

    if not phase_done('df_after'):
        journal['df_after'] = {
            'internal_kib': _free_kib(internal_root),
            'external_kib': _free_kib(external_root)}
        mark('df_after')

    before, after = journal['df_before'], journal['df_after']
    receipt = {
        'batch_id': batch_id,
        'ts': now(),
        'eligibility_contract': {c['name']: c['ok'] for c in checks},
        'removed': journal['removed'],
        'logical_bytes_deleted': journal['logical_bytes_deleted'],
        'logical_kib_du': journal['logical_kib_du'],
        'free_space': {
            'internal_ssd_root': {
                'before_avail_kib': before['internal_kib'],
                'after_avail_kib': after['internal_kib'],
                'delta_kib': after['internal_kib'] - before['internal_kib']},
            'external_mac_mini_m4': {
                'before_avail_kib': before['external_kib'],
                'after_avail_kib': after['external_kib'],
                'delta_kib': after['external_kib'] - before['external_kib']}},
        'merged_target': dict(patch_proof or {}),
        'preserved_evidence_paths': list(preserved_evidence_paths),
        'result': CLEANUP_DONE,
    }
    receipt_path.write_text(json.dumps(receipt, indent=1, sort_keys=True))
    mark('receipt_written')
    return receipt
