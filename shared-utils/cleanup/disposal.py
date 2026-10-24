"""Typed cleanup eligibility for scratch / merged / dirty / shared-consumer
resources, with immediate eligible dispatch (PBB-131 T-46, requirements R-32
and R-37).

Contract, in this order:

1. Every resource carries a typed disposition, never a bare boolean:
   ELIGIBLE, DEFERRED, BLOCKED or UNKNOWN. Only ELIGIBLE is dispatchable.
2. UNKNOWN outranks BLOCKED, which outranks DEFERRED. An input this module
   cannot determine is UNKNOWN with a reason code -- never success, never a
   silent ELIGIBLE, never a guessed default.
3. Eligible resources are disposed inside the same call (immediate, no queue),
   content is preserved first, the receipt records the exact external path,
   and absence is proven by a real lstat after removal.
4. Deletion never forces. `git worktree remove` is taken from the repository's
   accepted cleanup transaction module (scripts/lib/cleanup_transaction.py) and
   must not carry --force; direct tree removal calls shutil.rmtree with default
   error handling, so a failure surfaces as BLOCKED_REMOVAL_FAILED with the tree
   left in place.

Deliberately not implemented here: global resource census (T-04), engineering
loop transport (T-05), merge integration (T-43..T-45).
"""
import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path

SCHEMA_VERSION = 1

ELIGIBLE = 'ELIGIBLE'
DEFERRED = 'DEFERRED'
BLOCKED = 'BLOCKED'
UNKNOWN = 'UNKNOWN'
DISPOSITIONS = (ELIGIBLE, DEFERRED, BLOCKED, UNKNOWN)

SCRATCH_TYPES = frozenset({'disposable_scratch', 'scratch', 'temp_build',
                           'cache', 'generated_output', 'log_segment', 'trace'})
WORKTREE_TYPES = frozenset({'merged_worktree', 'branch'})
RESOURCE_TYPES = SCRATCH_TYPES | WORKTREE_TYPES

CLEAN_STATES = frozenset({'CLEAN', 'DIRTY_UNIQUE', 'NOT_APPLICABLE'})
CONSUMER_STATES = frozenset({'released', 'active'})

# Machine-readable reason codes. Never free text.
OK_ELIGIBLE = 'OK_ELIGIBLE'
OK_ALREADY_DISPOSED = 'OK_ALREADY_DISPOSED'
DEFERRED_UNIQUE_UNMERGED_WORK = 'DEFERRED_UNIQUE_UNMERGED_WORK'
DEFERRED_ACTIVE_CONSUMER = 'DEFERRED_ACTIVE_CONSUMER'
DEFERRED_LEASE_HELD = 'DEFERRED_LEASE_HELD'
BLOCKED_UNOWNED = 'BLOCKED_UNOWNED'
BLOCKED_OUTSIDE_APPROVED_ROOT = 'BLOCKED_OUTSIDE_APPROVED_ROOT'
BLOCKED_SYMLINK_ESCAPE = 'BLOCKED_SYMLINK_ESCAPE'
BLOCKED_VOLUME_IDENTITY_MISMATCH = 'BLOCKED_VOLUME_IDENTITY_MISMATCH'
BLOCKED_MISSING_REMOTE_MERGE_PROOF = 'BLOCKED_MISSING_REMOTE_MERGE_PROOF'
BLOCKED_MISSING_PRESERVATION = 'BLOCKED_MISSING_PRESERVATION'
BLOCKED_PRESERVATION_FAILED = 'BLOCKED_PRESERVATION_FAILED'
BLOCKED_REMOVAL_FAILED = 'BLOCKED_REMOVAL_FAILED'
BLOCKED_RECEIPT_DESTINATION = 'BLOCKED_RECEIPT_DESTINATION'
BLOCKED_DELETION_AUTHORITY_UNAVAILABLE = 'BLOCKED_DELETION_AUTHORITY_UNAVAILABLE'
UNKNOWN_MISSING_IDENTITY = 'UNKNOWN_MISSING_IDENTITY'
UNKNOWN_RESOURCE_TYPE = 'UNKNOWN_RESOURCE_TYPE'
UNKNOWN_VOLUME_IDENTITY = 'UNKNOWN_VOLUME_IDENTITY'
UNKNOWN_CLEAN_STATE = 'UNKNOWN_CLEAN_STATE'
UNKNOWN_CONSUMER_STATE = 'UNKNOWN_CONSUMER_STATE'
UNKNOWN_ABSENT_WITHOUT_RECEIPT = 'UNKNOWN_ABSENT_WITHOUT_RECEIPT'

PRECEDENCE = (UNKNOWN, BLOCKED, DEFERRED, ELIGIBLE)


class Refused(Exception):
    """A deletion precondition failed. Nothing was removed."""


class CleanupAuthorityUnavailable(Exception):
    """The repository's accepted no-force deletion module could not be loaded.
    Deletion is refused rather than reimplemented here."""


def _module_path():
    return Path(__file__).resolve().parents[2] / 'scripts' / 'lib' / 'cleanup_transaction.py'


def deletion_authority():
    """The repository's accepted cleanup transaction module, loaded by path.

    Loading, not copying: the no-force removal command has one owner.
    """
    path = _module_path()
    if not path.is_file():
        raise CleanupAuthorityUnavailable(f'missing {path}')
    spec = importlib.util.spec_from_file_location(
        '_pbb_cleanup_transaction_authority', path)
    if spec is None or spec.loader is None:
        raise CleanupAuthorityUnavailable(f'unloadable {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worktree_remove_command(repo_path, target_path):
    """The exact removal command, owned by the accepted authority module."""
    module = deletion_authority()
    cmd = [str(part) for part in module.worktree_remove_cmd(repo_path, target_path)]
    if any(part == '--force' or part.startswith('--force=') for part in cmd):
        raise Refused('deletion authority produced a forcing command')
    return cmd


def prove_absence(path):
    """Actual absence: a real lstat of the exact recorded path."""
    p = Path(path)
    present = os.path.lexists(str(p))
    return {'path': str(p), 'lexists': present, 'absent': not present}


def _real(path):
    return Path(os.path.realpath(str(path)))


def _beneath(child, root):
    child_real, root_real = _real(child), _real(root)
    if child_real == root_real:
        return False
    return str(child_real).startswith(str(root_real) + os.sep)


def _symlink_component(path, root):
    """First symlinked component between root (exclusive) and path (inclusive)."""
    try:
        rel = Path(path).relative_to(Path(root))
    except ValueError:
        return None
    current = Path(root)
    for part in rel.parts:
        current = current / part
        if os.path.islink(str(current)):
            return str(current)
    return None


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_digest(path):
    """{relative path: (sha256, size)} for regular files; symlinks recorded as
    links so a preserved copy can be compared without following them out."""
    entries = {}
    root = Path(path)
    if root.is_symlink():
        targets = None
        try:
            targets = os.readlink(str(root))
        except OSError:
            targets = None
        return {'': ('symlink', targets)}
    if root.is_file():
        return {'': ('file', _sha256(str(root)), root.stat().st_size)}
    for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            full = Path(dirpath) / name
            rel = str(full.relative_to(root))
            if full.is_symlink():
                entries[rel] = ('symlink', os.readlink(str(full)))
            else:
                entries[rel] = ('file', _sha256(str(full)), full.stat().st_size)
    return entries


def preserve(resource_path, preserved_root, resource_id):
    """Copy resource content outside itself and prove the copy byte-for-byte."""
    source = Path(resource_path)
    root = Path(preserved_root)
    if _beneath(root, source):
        raise Refused('preserved root is inside the resource being disposed')
    root.mkdir(parents=True, exist_ok=True)
    destination = root / resource_id
    if os.path.lexists(str(destination)):
        raise Refused(f'preserved destination already exists: {destination}')
    before = _tree_digest(source)
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(str(source), str(destination), symlinks=True)
    else:
        shutil.copy2(str(source), str(destination), follow_symlinks=False)
    after = _tree_digest(destination)
    if before != after:
        raise Refused(f'preserved copy differs from source: {destination}')
    files = sum(1 for value in after.values() if value[0] == 'file')
    total = sum(value[2] for value in after.values() if value[0] == 'file')
    return {'destination': str(destination), 'verified': True,
            'entries': len(after), 'files': files, 'bytes': total,
            'digest': hashlib.sha256(
                json.dumps(sorted(after.items()), default=str).encode()).hexdigest()}


def _remove_tree(path):
    """No force: default rmtree error handling, no chmod, no metadata pruning."""
    p = Path(path)
    if p.is_symlink():
        raise Refused(f'refusing to remove symlink: {p}')
    if p.is_dir():
        shutil.rmtree(str(p))
    elif os.path.lexists(str(p)):
        os.unlink(str(p))


def evaluate(item, *, approved_root, expected_device, preserved_paths=(),
             preserve_content=False):
    """Type one resource. Returns a record with a disposition and reason codes.

    Frozen precedence: UNKNOWN > BLOCKED > DEFERRED > ELIGIBLE.
    """
    findings = []

    def note(disposition, code, detail):
        findings.append({'disposition': disposition, 'code': code,
                         'detail': detail})

    resource_id = item.get('id')
    resource_type = item.get('resource_type')
    raw_path = item.get('path')
    record = {
        'id': resource_id if isinstance(resource_id, str) else '',
        'resource_type': resource_type if isinstance(resource_type, str) else '',
        'path': str(raw_path) if raw_path else '',
        'canonical_path': None,
        'device': None,
        'present': None,
        'checks': {},
    }

    if not record['id'] or not record['path']:
        note(UNKNOWN, UNKNOWN_MISSING_IDENTITY,
             'id and path are both required to type a resource')
    if resource_type not in RESOURCE_TYPES:
        note(UNKNOWN, UNKNOWN_RESOURCE_TYPE,
             f'resource_type {resource_type!r} is not one of {sorted(RESOURCE_TYPES)}')

    # Ownership is a definite fact: no receipt means no right to delete.
    if not item.get('ownership_receipt_id'):
        note(BLOCKED, BLOCKED_UNOWNED, 'no ownership receipt for this resource')

    if record['path']:
        canonical = _real(record['path'])
        record['canonical_path'] = str(canonical)
        try:
            record['present'] = os.path.lexists(record['path'])
        except OSError as exc:
            record['present'] = None
            note(UNKNOWN, UNKNOWN_VOLUME_IDENTITY, f'lexists failed: {exc}')

        root_real = _real(approved_root)
        contained = (str(canonical) != str(root_real)
                     and str(canonical).startswith(str(root_real) + os.sep))
        record['checks']['beneath_approved_root'] = contained
        if not contained:
            note(BLOCKED, BLOCKED_OUTSIDE_APPROVED_ROOT,
                 f'{record["path"]} resolves to {canonical}, outside {root_real}')

        link = _symlink_component(record['path'], approved_root)
        record['checks']['symlink_component'] = link
        if link is not None:
            note(BLOCKED, BLOCKED_SYMLINK_ESCAPE,
                 f'symlinked path component: {link}')

        if not isinstance(expected_device, int):
            note(UNKNOWN, UNKNOWN_VOLUME_IDENTITY,
                 'expected_device is not an observed st_dev integer')
        else:
            try:
                record['device'] = os.stat(record['path']).st_dev
            except FileNotFoundError:
                record['device'] = None
            except OSError as exc:
                note(UNKNOWN, UNKNOWN_VOLUME_IDENTITY, f'stat failed: {exc}')
            root_device = os.stat(str(approved_root)).st_dev
            record['checks']['root_device'] = root_device
            if root_device != expected_device:
                note(BLOCKED, BLOCKED_VOLUME_IDENTITY_MISMATCH,
                     f'approved root device {root_device} != expected {expected_device}')
            if record['device'] is not None and record['device'] != expected_device:
                note(BLOCKED, BLOCKED_VOLUME_IDENTITY_MISMATCH,
                     f'resource device {record["device"]} != expected {expected_device}')

        if record['present'] is False:
            if item.get('disposal_receipt_id'):
                note(ELIGIBLE, OK_ALREADY_DISPOSED,
                     'absent and a disposal receipt already exists')
            else:
                note(UNKNOWN, UNKNOWN_ABSENT_WITHOUT_RECEIPT,
                     'absent with no disposal receipt: prior deletion unproven')

    if record['present'] is not False:
        clean_state = item.get('clean_state', 'NOT_APPLICABLE')
        if clean_state not in CLEAN_STATES:
            note(UNKNOWN, UNKNOWN_CLEAN_STATE,
                 f'clean_state {clean_state!r} is not one of {sorted(CLEAN_STATES)}')

        consumers = item.get('consumers') or []
        active = []
        for consumer in consumers:
            state = consumer.get('state') if isinstance(consumer, dict) else None
            if state not in CONSUMER_STATES:
                note(UNKNOWN, UNKNOWN_CONSUMER_STATE,
                     f'consumer {consumer!r} has no determinate state')
                continue
            if state == 'active':
                active.append(consumer.get('id'))
        record['checks']['active_consumers'] = active
        if active:
            note(DEFERRED, DEFERRED_ACTIVE_CONSUMER,
                 f'consumers still active: {sorted(str(c) for c in active)}')

        leases = item.get('lease_ids') or []
        if leases:
            note(DEFERRED, DEFERRED_LEASE_HELD, f'live leases: {sorted(leases)}')

        if item.get('has_unique_unmerged_work') or clean_state == 'DIRTY_UNIQUE':
            note(DEFERRED, DEFERRED_UNIQUE_UNMERGED_WORK,
                 'unique unmerged work must be preserved, never deleted')

        if resource_type in WORKTREE_TYPES and not (item.get('remote_merge_proof_ids') or []):
            note(BLOCKED, BLOCKED_MISSING_REMOTE_MERGE_PROOF,
                 'merged work is not proven present in the remote target')

        proof = None
        if resource_type in WORKTREE_TYPES and item.get('remote_merge_proof_ids'):
            proof = 'remote_merge_proof'
        existing = [p for p in (preserved_paths or ())
                    if os.path.lexists(str(p)) and not _beneath(str(p), record['path'])]
        if proof is None and existing:
            proof = 'caller_preserved'
        if proof is None and preserve_content:
            proof = 'immediate_copy'
        record['checks']['preservation'] = proof
        if proof is None:
            note(BLOCKED, BLOCKED_MISSING_PRESERVATION,
                 'no preserved content, no remote proof, and preserve_content is off')

    disposition = ELIGIBLE
    for candidate in PRECEDENCE:
        if any(f['disposition'] == candidate for f in findings):
            disposition = candidate
            break
    if disposition == ELIGIBLE and not findings:
        note(ELIGIBLE, OK_ELIGIBLE, 'all eligibility checks passed')

    ordered = sorted(findings, key=lambda f: PRECEDENCE.index(f['disposition']))
    record['disposition'] = disposition
    record['reasons'] = [f['code'] for f in ordered]
    record['reason'] = '; '.join(
        f'{f["code"]}: {f["detail"]}' for f in ordered
        if f['disposition'] == disposition) or None
    record['findings'] = ordered
    return record


def _receipt_destination_ok(receipt_path, approved_root, expected_device):
    parent = Path(receipt_path).parent
    try:
        if os.stat(str(parent)).st_dev != expected_device:
            return f'receipt parent device differs from expected {expected_device}'
    except OSError as exc:
        return f'receipt parent unreadable: {exc}'
    if not _beneath(parent, approved_root):
        return f'receipt parent {parent} is outside {approved_root}'
    link = _symlink_component(parent, approved_root)
    if link is not None:
        return f'receipt parent has symlinked component {link}'
    return None


def _write_receipt(receipt_path, payload):
    target = Path(receipt_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f'.{target.name}.tmp-{secrets.token_hex(8)}')
    data = json.dumps(payload, indent=1, sort_keys=True).encode()
    handle = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(target))
    finally:
        if os.path.lexists(str(temporary)):
            os.unlink(str(temporary))
    return json.loads(Path(target).read_text()) == payload


def dispatch(items, *, approved_root, expected_device, receipt_path,
             preserved_root=None, preserve_content=False, repo_path=None,
             now=time.time):
    """Immediately dispose every eligible resource; preserve, delete, then
    prove absence. Never forces. Returns the written receipt plus status.

    status is DISPATCHED only when every resource ended ELIGIBLE with proven
    absence. A DEFERRED, BLOCKED or UNKNOWN resource makes it INCOMPLETE --
    an unknown is never rendered as success.
    """
    destination_problem = _receipt_destination_ok(
        receipt_path, approved_root, expected_device)
    records = []
    deletions = []
    preservation = []

    for item in items:
        record = evaluate(
            item, approved_root=approved_root, expected_device=expected_device,
            preserved_paths=[preserved_root] if preserved_root else (),
            preserve_content=preserve_content)
        record['disposed'] = False

        if record['disposition'] != ELIGIBLE:
            records.append(record)
            continue

        if record['present'] is False:
            record['absence'] = prove_absence(record['path'])
            record['disposed'] = record['absence']['absent']
            records.append(record)
            continue

        if destination_problem is not None:
            record['disposition'] = BLOCKED
            record['reasons'].append(BLOCKED_RECEIPT_DESTINATION)
            record['reason'] = f'{BLOCKED_RECEIPT_DESTINATION}: {destination_problem}'
            records.append(record)
            continue

        try:
            if record['checks'].get('preservation') == 'immediate_copy':
                if preserved_root is None:
                    raise Refused('preserve_content requires preserved_root')
                preserved = preserve(record['path'], preserved_root, record['id'])
                record['preserved'] = preserved
                preservation.append(preserved)
            elif record['checks'].get('preservation') == 'remote_merge_proof':
                record['preserved'] = {
                    'proof': 'remote_merge_proof',
                    'proof_ids': list(item.get('remote_merge_proof_ids') or [])}
            else:
                record['preserved'] = {'proof': 'caller_preserved'}
        except (Refused, OSError, shutil.Error) as exc:
            record['disposition'] = BLOCKED
            record['reasons'].append(BLOCKED_PRESERVATION_FAILED)
            record['reason'] = (f'{BLOCKED_PRESERVATION_FAILED}: {exc} '
                                '(nothing deleted)')
            records.append(record)
            continue

        try:
            size_before = _path_bytes(record['path'])
            if record['resource_type'] in WORKTREE_TYPES and repo_path:
                command = worktree_remove_command(repo_path, record['path'])
                result = subprocess.run(command, capture_output=True,
                                        text=True, timeout=120)
                removal = {'method': 'git worktree remove', 'command': command,
                           'returncode': result.returncode,
                           'stderr': result.stderr.strip()}
                if result.returncode != 0:
                    raise Refused(f'git worktree remove failed: '
                                  f'{result.stderr.strip() or result.returncode}')
            else:
                _remove_tree(record['path'])
                removal = {'method': 'direct tree removal (no force)',
                           'command': None, 'returncode': 0, 'stderr': ''}
        except CleanupAuthorityUnavailable as exc:
            record['disposition'] = BLOCKED
            record['reasons'].append(BLOCKED_DELETION_AUTHORITY_UNAVAILABLE)
            record['reason'] = f'{BLOCKED_DELETION_AUTHORITY_UNAVAILABLE}: {exc}'
            records.append(record)
            continue
        except Refused as exc:
            record['disposition'] = BLOCKED
            record['reasons'].append(BLOCKED_REMOVAL_FAILED)
            record['reason'] = f'{BLOCKED_REMOVAL_FAILED}: {exc}'
            records.append(record)
            continue
        except OSError as exc:
            record['disposition'] = BLOCKED
            record['reasons'].append(BLOCKED_REMOVAL_FAILED)
            record['reason'] = (f'{BLOCKED_REMOVAL_FAILED}: '
                                f'{exc.strerror or exc} (tree preserved)')
            record['error_number'] = exc.errno
            records.append(record)
            continue

        absence = prove_absence(record['path'])
        record['absence'] = absence
        record['removal'] = removal
        record['bytes'] = size_before
        if not absence['absent']:
            record['disposition'] = BLOCKED
            record['reasons'].append(BLOCKED_REMOVAL_FAILED)
            record['reason'] = f'{BLOCKED_REMOVAL_FAILED}: path still present'
        else:
            record['disposed'] = True
            record['disposal_receipt_id'] = f'dispose-{record["id"]}-{int(now())}'
            deletions.append({'id': record['id'],
                              'path': record['path'],
                              'canonical_path': record['canonical_path'],
                              'device': record['device'],
                              'bytes': size_before,
                              'absence': absence})
        records.append(record)

    counts = {name: 0 for name in DISPOSITIONS}
    for record in records:
        counts[record['disposition']] = counts.get(record['disposition'], 0) + 1
    dispatched = all(record['disposition'] == ELIGIBLE and record['disposed']
                     for record in records) and bool(records)
    status = 'DISPATCHED' if dispatched else 'INCOMPLETE'

    payload = {
        'schema_version': SCHEMA_VERSION,
        'generated_at': now(),
        'approved_root': str(approved_root),
        'expected_device': expected_device,
        'status': status,
        'counts': counts,
        'items': records,
        'deletions': deletions,
        'preservation': preservation,
    }
    if destination_problem is not None:
        payload['reason'] = f'{BLOCKED_RECEIPT_DESTINATION}: {destination_problem}'
        payload['receipt_written'] = False
        payload['success'] = False
        return payload
    payload['receipt_written'] = True
    payload['receipt_read_back'] = _write_receipt(receipt_path, payload)
    payload['receipt_path'] = str(receipt_path)
    payload['success'] = status == 'DISPATCHED' and payload['receipt_read_back']
    return payload


def _path_bytes(path):
    p = Path(path)
    try:
        if p.is_file() and not p.is_symlink():
            return p.stat().st_size
    except OSError:
        return 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(str(p), followlinks=False):
        for name in filenames:
            full = Path(dirpath) / name
            try:
                if not full.is_symlink():
                    total += full.stat().st_size
            except OSError:
                continue
    return total
