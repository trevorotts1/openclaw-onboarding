"""Typed cleanup eligibility for scratch / merged / dirty / shared-consumer
resources, with immediate eligible dispatch (PBB-131 T-46, requirements R-32
and R-37).

Contract, in this order:

1. Every resource carries a typed disposition, never a bare boolean:
   ELIGIBLE, DEFERRED, BLOCKED or UNKNOWN. Only ELIGIBLE is dispatchable.
2. UNKNOWN outranks BLOCKED, which outranks DEFERRED. An input this module
   cannot determine is UNKNOWN with a reason code -- never success, never a
   silent ELIGIBLE, never a guessed default. A record that is not a mapping, a
   batch container that is not iterable, or a record whose list fields are the
   wrong shape, types as UNKNOWN_MALFORMED_ITEM and one such record never aborts
   a batch. An identity is a real single path segment (never whitespace only,
   never carrying a separator): it is the one segment of a preserved
   destination, so anything else is UNKNOWN_MISSING_IDENTITY.
3. Eligible resources are disposed inside the same call (immediate, no queue),
   content is preserved first -- a verified immediate copy when preserve_content
   is set, otherwise a caller copy only when the resource names its own
   preservation receipts AND a preserved copy whose content is proven
   byte-for-byte against the resource -- the receipt records the exact external
   path and its digest, and absence is proven by a real lstat after removal. A
   directory merely existing is never proof. The preserved destination is proven
   to sit inside the preserved root before and after the copy.
4. Deletion never forces. `git worktree remove` is taken from the repository's
   accepted cleanup transaction module (scripts/lib/cleanup_transaction.py) and
   must not carry --force in any of its forms (long, attached value, short
   cluster); direct tree removal calls shutil.rmtree with default error
   handling, so a failure surfaces as BLOCKED_REMOVAL_FAILED with the tree
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
import stat
import subprocess
import time
from collections.abc import Mapping
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
BLOCKED_UNSAFE_IDENTITY = 'BLOCKED_UNSAFE_IDENTITY'
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
UNKNOWN_MALFORMED_ITEM = 'UNKNOWN_MALFORMED_ITEM'

# List-shaped contract fields. A wrong shape is malformed data, never a default.
LIST_FIELDS = ('consumers', 'lease_ids', 'remote_merge_proof_ids',
               'preservation_receipt_ids')

PRECEDENCE = (UNKNOWN, BLOCKED, DEFERRED, ELIGIBLE)


class Refused(Exception):
    """A deletion precondition failed. Nothing was removed."""


class CleanupAuthorityUnavailable(Exception):
    """The repository's accepted no-force deletion module could not be loaded.
    Deletion is refused rather than reimplemented here."""


def _as_list(value):
    return list(value) if isinstance(value, (list, tuple)) else []


def _receipt_ref(value):
    """A receipt reference names real receipts. Anything else is no receipt at
    all, and no receipt means no right to delete."""
    if isinstance(value, str):
        return value.strip() != ''
    return (isinstance(value, (list, tuple)) and bool(value)
            and all(isinstance(entry, str) and entry.strip() != ''
                    for entry in value))


def _safe_segment(value):
    """One path segment, or None.

    An identity is used as the single filename of a preserved destination, so
    it is folded into one segment here (a branch name may carry separators) and
    anything left that could steer a write -- an empty segment, '.' or '..' --
    is refused. A caller-supplied identity can never choose a directory.
    """
    if not isinstance(value, str):
        return None
    folded = value.strip().replace('\x00', '')
    for sep in (os.sep, '/', '\\'):
        folded = folded.replace(sep, '_')
    if folded in ('', '.', '..'):
        return None
    return folded


def _identity_problem(value):
    """(disposition, code, detail) for an identity that cannot name a resource,
    or None when it can."""
    if not isinstance(value, str) or not value.strip():
        return (UNKNOWN, UNKNOWN_MISSING_IDENTITY,
                'id must be a non-blank string to name a resource')
    if any(part == '..' for part in value.replace('\\', '/').split('/')) \
            or '\x00' in value or value.startswith('/'):
        return (BLOCKED, BLOCKED_UNSAFE_IDENTITY,
                f'id {value!r} carries path traversal or absolute syntax')
    if _safe_segment(value) is None:
        return (UNKNOWN, UNKNOWN_MISSING_IDENTITY,
                'id does not fold into one safe path segment')
    return None


def _malformed_record(detail):
    """Typed UNKNOWN for a record this module cannot read. Fail closed: a record
    nobody can type is never ELIGIBLE and never deleted."""
    finding = {'disposition': UNKNOWN, 'code': UNKNOWN_MALFORMED_ITEM,
               'detail': detail}
    return {
        'id': '', 'resource_type': '', 'path': '', 'canonical_path': None,
        'device': None, 'present': None, 'checks': {},
        'disposition': UNKNOWN, 'reasons': [UNKNOWN_MALFORMED_ITEM],
        'reason': f'{UNKNOWN_MALFORMED_ITEM}: {detail}', 'findings': [finding],
    }


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


def _is_force_flag(part):
    """One spelling of force, in any of its forms.

    A forcing flag is '--force', '--force=<anything>', or a short cluster that
    carries 'f' ('-f', '-af'). The name is spelled apart from the guard so the
    guard cannot drift into matching one spelling only.
    """
    if not isinstance(part, str) or not part.startswith('-') or part == '-':
        return False
    if part.startswith('--'):
        return part == '--' + 'force' or part.startswith('--' + 'force=')
    return part[1:].isalpha() and 'f' in part[1:]


def worktree_remove_command(repo_path, target_path):
    """The exact removal command, owned by the accepted authority module."""
    module = deletion_authority()
    cmd = [str(part) for part in module.worktree_remove_cmd(repo_path, target_path)]
    if any(_is_force_flag(part) for part in cmd):
        raise Refused('deletion authority produced a forcing command')
    return cmd


def prove_absence(path):
    """Actual absence: a real lstat of the exact recorded path."""
    p = Path(path)
    present = os.path.lexists(str(p))
    return {'path': str(p), 'lexists': present, 'absent': not present}


def _real(path):
    return Path(os.path.realpath(str(path)))


def _within(child, root):
    """child is root itself or lies beneath it, after resolving both. The one
    containment test for receipts, preserved copies and their resources."""
    child_real, root_real = _real(child), _real(root)
    return (child_real == root_real
            or str(child_real).startswith(str(root_real).rstrip(os.sep) + os.sep))


def _symlink_component(path, root):
    """First symlinked component between root (exclusive) and path (inclusive).

    root and path may be written in different lexical forms (one relative, one
    absolute, one reached through a link), so the boundary between them is the
    first ancestor of path that resolves to the resolved root, not a lexical
    relative_to. A guard that silently returns None when the two forms differ
    is a guard that cannot fire on the case it exists for.
    """
    root_real = _real(root)
    node = Path(os.path.abspath(str(path)))
    chain = []
    found_root = False
    while True:
        if _real(node) == root_real:
            found_root = True
            break
        chain.append(node)
        parent = node.parent
        if parent == node:
            break
        node = parent
    chain.reverse()
    if not found_root:
        chain.append(Path(os.path.abspath(str(root))))
    for part in chain:
        if os.path.islink(str(part)):
            return str(part)
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
    """Copy resource content outside itself and prove the copy byte-for-byte.

    The destination is one folded segment beneath the preserved root and is
    proven contained before the copy is made and again before the receipt is
    handed back: an identity can never steer a write outside the preserved root.
    """
    source = Path(resource_path)
    root = Path(preserved_root)
    if _within(root, source) or _within(source, root):
        raise Refused('preserved root is the resource being disposed or inside it')
    root.mkdir(parents=True, exist_ok=True)
    segment = _safe_segment(resource_id)
    if segment is None:
        raise Refused(f'identity is not one safe path segment: {resource_id!r}')
    destination = root / segment
    if not _within(destination, root):
        raise Refused(f'preserved destination escapes the preserved root: {destination}')
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
    if not _within(destination, root):
        raise Refused(f'preserved copy landed outside the preserved root: {destination}')
    files = sum(1 for value in after.values() if value[0] == 'file')
    total = sum(value[2] for value in after.values() if value[0] == 'file')
    return {'destination': str(_real(destination)), 'verified': True,
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


def _named_copy_candidates(item, preserved_paths):
    """Where a caller copy of THIS resource may live: the exact external paths
    the record names first, then the per-resource entry beneath each approved
    preserved location. A bare preserved directory is a place, never proof."""
    named = item.get('preserved_path') or item.get('preserved_paths')
    for entry in _as_list(named) if not isinstance(named, str) else [named]:
        if isinstance(entry, str) and entry.strip():
            yield entry
    for location in (preserved_paths or ()):
        if location is None:
            continue
        yield str(location)
        segment = _safe_segment(item.get('id'))
        if segment is not None:
            yield str(Path(str(location)) / segment)


def _proven_copy(resource_path, candidate):
    """candidate holds exactly this resource's content, outside it: a real
    existence check plus a byte-for-byte tree digest. A directory merely
    existing is never proof. Returns the same proof shape preserve() returns."""
    source = Path(resource_path)
    copy = Path(candidate)
    if not os.path.lexists(str(copy)):
        return None
    if _within(copy, source) or _within(source, copy):
        return None
    before = _tree_digest(source)
    after = _tree_digest(copy)
    if after != before:
        return None
    files = sum(1 for value in after.values() if value[0] == 'file')
    total = sum(value[2] for value in after.values() if value[0] == 'file')
    return {'destination': str(_real(copy)), 'verified': True,
            'entries': len(after), 'files': files, 'bytes': total,
            'digest': hashlib.sha256(
                json.dumps(sorted(after.items()), default=str).encode()).hexdigest()}


def _usable_preserved_location(location, resource_path):
    """A place the module may write a preserved copy to: outside the resource
    in both directions, and not a file."""
    if location is None:
        return False
    place = Path(location)
    if os.path.lexists(str(place)) and (place.is_symlink() or not place.is_dir()):
        return False
    return not (_within(place, resource_path) or _within(resource_path, place))


def evaluate(item, *, approved_root, expected_device, preserved_paths=(),
             preserve_content=False):
    """Type one resource. Returns a record with a disposition and reason codes.

    Frozen precedence: UNKNOWN > BLOCKED > DEFERRED > ELIGIBLE.
    """
    findings = []

    def note(disposition, code, detail):
        findings.append({'disposition': disposition, 'code': code,
                         'detail': detail})

    if not isinstance(item, Mapping):
        return _malformed_record(
            f'resource record is {type(item).__name__}, not a mapping')
    malformed = [name for name in LIST_FIELDS
                 if item.get(name) is not None
                 and not isinstance(item.get(name), (list, tuple))]
    if malformed:
        return _malformed_record(
            f'list fields with the wrong shape: {sorted(malformed)}')

    resource_id = item.get('id')
    resource_type = item.get('resource_type')
    raw_path = item.get('path')
    record = {
        'id': resource_id.strip() if isinstance(resource_id, str) else '',
        'resource_type': resource_type if isinstance(resource_type, str) else '',
        'path': str(raw_path) if raw_path else '',
        'canonical_path': None,
        'device': None,
        'present': None,
        'checks': {},
    }

    problem = _identity_problem(resource_id)
    if problem is not None:
        note(problem[0], problem[1], problem[2])
    if not record['path']:
        note(UNKNOWN, UNKNOWN_MISSING_IDENTITY,
             'id and path are both required to type a resource')
    if resource_type not in RESOURCE_TYPES:
        note(UNKNOWN, UNKNOWN_RESOURCE_TYPE,
             f'resource_type {resource_type!r} is not one of {sorted(RESOURCE_TYPES)}')

    # Ownership is a definite fact: no usable receipt means no right to delete.
    if not _receipt_ref(item.get('ownership_receipt_id')):
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
        # The approved root itself is never a disposable resource.
        contained = canonical != root_real and _within(canonical, root_real)
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
            try:
                root_device = os.stat(str(approved_root)).st_dev
            except OSError as exc:
                root_device = None
                note(UNKNOWN, UNKNOWN_VOLUME_IDENTITY,
                     f'approved root stat failed: {exc}')
            record['checks']['root_device'] = root_device
            if root_device is not None and root_device != expected_device:
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
        # An absent clean_state or consumers key is an unobserved fact, never a
        # clean default: UNKNOWN, and no disposal on its strength.
        clean_state = item.get('clean_state')
        if clean_state not in CLEAN_STATES:
            note(UNKNOWN, UNKNOWN_CLEAN_STATE,
                 f'clean_state {clean_state!r} is not one of {sorted(CLEAN_STATES)}')

        if item.get('consumers') is None:
            note(UNKNOWN, UNKNOWN_CONSUMER_STATE,
                 'consumers were not recorded; an empty list means none')
        consumers = _as_list(item.get('consumers'))
        active = []
        for consumer in consumers:
            state = consumer.get('state') if isinstance(consumer, Mapping) else None
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

        leases = _as_list(item.get('lease_ids'))
        if leases:
            note(DEFERRED, DEFERRED_LEASE_HELD,
                 f'live leases: {sorted(str(x) for x in leases)}')

        if item.get('has_unique_unmerged_work') or clean_state == 'DIRTY_UNIQUE':
            note(DEFERRED, DEFERRED_UNIQUE_UNMERGED_WORK,
                 'unique unmerged work must be preserved, never deleted')

        remote_proofs = _as_list(item.get('remote_merge_proof_ids'))
        if resource_type in WORKTREE_TYPES and not remote_proofs:
            note(BLOCKED, BLOCKED_MISSING_REMOTE_MERGE_PROOF,
                 'merged work is not proven present in the remote target')

        # Preservation proof, strongest first. preserve_content is a promise the
        # module keeps itself, so it outranks a caller copy; a caller copy is
        # only proof when the resource names its own preservation receipts AND a
        # preserved copy of this resource is proven byte-for-byte at an exact
        # external path. A directory merely existing is never proof.
        receipts = _as_list(item.get('preservation_receipt_ids'))
        proof = None
        preserved = []
        if resource_type in WORKTREE_TYPES and remote_proofs:
            proof = 'remote_merge_proof'
            record['checks']['remote_merge_proof_ids'] = list(remote_proofs)
        if proof is None and preserve_content:
            target = None
            for candidate in preserved_paths or ():
                if _usable_preserved_location(candidate, record['path']):
                    target = candidate
                    break
            if target is None:
                note(BLOCKED, BLOCKED_PRESERVATION_FAILED,
                     'no preserved location outside the resource to copy into')
            else:
                proof = 'immediate_copy'
        if proof is None and receipts:
            for candidate in _named_copy_candidates(item, preserved_paths):
                copy = _proven_copy(record['path'], candidate)
                if copy is not None:
                    preserved.append(copy)
            if preserved:
                proof = 'caller_preserved'
                record['checks']['preservation_receipt_ids'] = list(receipts)
        record['checks']['preservation'] = proof
        if preserved:
            record['checks']['preserved_copies'] = preserved
        if proof is None and not any(
                f['code'] == BLOCKED_PRESERVATION_FAILED for f in findings):
            note(BLOCKED, BLOCKED_MISSING_PRESERVATION,
                 'no preserved content proven at an external path, no remote '
                 'proof, and preserve_content is off')

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
    if not _within(parent, approved_root):
        return f'receipt parent {parent} is outside {approved_root}'
    link = _symlink_component(parent, approved_root)
    if link is not None:
        return f'receipt parent has symlinked component {link}'
    return _receipt_target_probe(receipt_path)


def _receipt_target_probe(receipt_path):
    """Pre-flight, before the first removal: the target is absent or a regular
    file, and a sibling temporary file can be created, as _write_receipt does.
    No receipt possible means no deletion at all."""
    target = Path(receipt_path)
    try:
        if os.path.lexists(str(target)) and not stat.S_ISREG(os.lstat(str(target)).st_mode):
            return f'receipt target {target} exists and is not a regular file'
        probe = target.with_name(f'.{target.name}.probe-{secrets.token_hex(8)}')
        os.close(os.open(str(probe), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        os.unlink(str(probe))
    except OSError as exc:
        return f'receipt target {target} is not writable: {exc}'
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

    container_problem = None
    try:
        if isinstance(items, (Mapping, str, bytes, bytearray)):
            raise TypeError(
                f'batch container is {type(items).__name__}, not an iterable '
                'of resource records')
        batch = list(items)
    except Exception as exc:  # an unreadable batch types, it never raises
        batch = []
        container_problem = f'{type(exc).__name__}: {exc}'
    if container_problem is not None:
        record = _malformed_record(
            f'batch container cannot be read: {container_problem}')
        record['disposed'] = False
        records.append(record)

    for item in batch:
        try:
            record = evaluate(
                item, approved_root=approved_root, expected_device=expected_device,
                preserved_paths=[preserved_root] if preserved_root else (),
                preserve_content=preserve_content)
        except Exception as exc:  # one bad record never aborts the batch
            record = _malformed_record(f'record could not be typed: {exc}')
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
            proof = record['checks'].get('preservation')
            if proof == 'immediate_copy':
                if preserved_root is None:
                    raise Refused('preserve_content requires preserved_root')
                kept = preserve(record['path'], preserved_root, record['id'])
                record['preserved'] = kept
                preservation.append(kept)
            elif proof == 'remote_merge_proof':
                record['preserved'] = {
                    'proof': 'remote_merge_proof',
                    'proof_ids': list(
                        record['checks'].get('remote_merge_proof_ids') or [])}
            elif proof == 'caller_preserved':
                copies = record['checks'].get('preserved_copies') or []
                if not copies:
                    raise Refused('no proven preserved copy to record')
                kept = dict(copies[0])
                kept['proof'] = 'caller_preserved'
                kept['receipt_ids'] = list(
                    record['checks'].get('preservation_receipt_ids') or [])
                record['preserved'] = kept
                preservation.append(kept)
            else:
                raise Refused('no preservation proof was selected')
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
        except subprocess.TimeoutExpired as exc:
            record['disposition'] = BLOCKED
            record['reasons'].append(BLOCKED_REMOVAL_FAILED)
            record['absence'] = prove_absence(record['path'])
            record['reason'] = (f'{BLOCKED_REMOVAL_FAILED}: removal timed out '
                                f'after {exc.timeout}s; observed state '
                                f'{record["absence"]}')
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
            kept = record.get('preserved') or {}
            deletions.append({'id': record['id'],
                              'path': record['path'],
                              'canonical_path': record['canonical_path'],
                              'device': record['device'],
                              'bytes': size_before,
                              'absence': absence,
                              'preserved_proof': kept.get('proof'),
                              'preserved_destination': kept.get('destination'),
                              'preserved_digest': kept.get('digest')})
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
    payload['receipt_path'] = str(receipt_path)
    try:
        payload['receipt_read_back'] = _write_receipt(receipt_path, payload)
    except Exception as exc:  # a committed deletion is never stranded by a raise
        # The pre-flight passed, yet the write failed: the real deletions stay
        # recorded inline (path, canonical path, absence) in this typed result.
        payload['status'] = 'INCOMPLETE'
        payload['reason'] = (f'{BLOCKED_RECEIPT_DESTINATION}: receipt write '
                             f'failed after removal: {exc!r}')
        payload['receipt_written'] = False
        payload['receipt_read_back'] = False
        payload['success'] = False
        return payload
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
