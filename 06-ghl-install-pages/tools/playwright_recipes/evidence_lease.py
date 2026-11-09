"""One evidence-root writer lease for host and direct delivery entry points.

Nested provider calls inherit ownership only in the same thread, task and process.
This never interprets a journal as permission to retry a write.
"""
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
import asyncio
import fcntl
import os
import re
import stat
import sys
import threading

if __name__ == 'evidence_lease':
    sys.modules.setdefault('playwright_recipes.evidence_lease', sys.modules[__name__])
elif __name__ == 'playwright_recipes.evidence_lease':
    sys.modules.setdefault('evidence_lease', sys.modules[__name__])

if __package__:
    from .skill6_playwright import Stop
else:
    from skill6_playwright import Stop


@dataclass
class _Owner:
    root: Path
    location_id: str
    kind: str
    process_id: int
    thread_id: int
    task: object
    active: bool = True


_owned = ContextVar('skill6_evidence_lease', default=None)
JOURNALS = ('state.json', 'provider-state.json', 'community-portal-state.json',
            'community-details-state.json', 'community-access-state.json', 'community-event-state.json', 'delivery-state.json',
            'calendar-delivery-state.json', 'handoff.json', 'auth-stop.json')


def journal_present(path):
    path = Path(path)
    return path.exists() or path.is_symlink()


def read_journal(path):
    """Read a regular owned journal without following a substituted symlink."""
    import json
    path = Path(path)
    if path.is_symlink():
        raise Stop('Evidence journal is a symlink; reconciliation required')
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Stop('Evidence journal is not a regular file')
        with os.fdopen(fd, 'r') as stream:
            fd = None
            return json.load(stream)
    except (OSError, ValueError, TypeError):
        raise Stop('Evidence journal is unreadable; reconciliation required') from None
    finally:
        if fd is not None:
            os.close(fd)


def open_lease(path):
    """Never follow a lease-file symlink or chmod its external target."""
    fd = None
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Stop('Evidence lease is not a regular file')
        os.fchmod(fd, 0o600)
        return fd
    except (OSError, Stop):
        if fd is not None:
            os.close(fd)
        raise Stop('Evidence lease is unavailable or unsafe; reconciliation required') from None


def _current_task():
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None


def _journal_checks(root, kind, *, nested=False):
    # These journals belong to a different executor/fingerprint. Even a
    # completed journal is not authority to change lanes automatically.
    if any((root / name).is_symlink() for name in JOURNALS):
        raise Stop('Evidence journal is a symlink; reconciliation required')
    names = ['state.json', 'community-portal-state.json', 'handoff.json', 'auth-stop.json']
    if kind != 'community_details':
        names.append('community-details-state.json')
    if kind != 'community_access':
        names.append('community-access-state.json')
    if kind != 'community_event':
        names.append('community-event-state.json')
    if kind not in ('provider', 'provider_replay') and not nested:
        names.append('provider-state.json')
    if kind == 'provider':
        names.extend(('delivery-state.json', 'calendar-delivery-state.json'))
    elif kind == 'course':
        names.append('calendar-delivery-state.json')
    elif kind == 'calendar':
        names.append('delivery-state.json')
    elif kind in ('community_details', 'community_access', 'community_event'):
        names.extend(('delivery-state.json', 'calendar-delivery-state.json'))
    for name in names:
        if journal_present(root / name):
            raise Stop('Existing ' + name + ' requires reconciliation before another execution lane')


@contextmanager
def evidence_lease(root, location_id, *, kind):
    """Serialize one root across native editor, portal, provider and API writers.

    The host records its own provider intent before calling course/calendar
    executors. Only that live, same-thread provider owner may nest those calls;
    a caller-authored journal or JSON flag cannot grant nested ownership.
    provider_replay admits existing API journals only for returning a prior host
    receipt. It cannot nest a delivery write, even in the same thread/task.
    """
    if kind not in ('provider', 'provider_replay', 'course', 'calendar', 'community_details', 'community_access', 'community_event'):
        raise Stop('Unknown evidence-root writer')
    if not isinstance(location_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', location_id):
        raise Stop('A valid evidence-root location identity is required')
    root = Path(root).resolve()
    current = _owned.get()
    if current is not None:
        if (not current.active or current.root != root or current.location_id != location_id
                or current.process_id != os.getpid()
                or current.thread_id != threading.get_ident()
                or current.task is not _current_task()
                or current.kind != 'provider' or kind not in ('course', 'calendar', 'community_details')):
            raise Stop('Nested evidence-root ownership mismatch')
        _journal_checks(root, kind, nested=True)
        yield root
        return
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    leases = []
    token = None
    owner = None
    try:
        for name in ('.runner.lock', 'provider.lock'):
            fd = open_lease(root / name)
            leases.append(fd)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Stop('Evidence root already has an editor, portal or provider writer') from None
        _journal_checks(root, kind)
        owner = _Owner(root, location_id, kind, os.getpid(), threading.get_ident(), _current_task())
        token = _owned.set(owner)
        yield root
    finally:
        if owner is not None:
            owner.active = False
        if token is not None:
            _owned.reset(token)
        for fd in reversed(leases):
            os.close(fd)


def guard_delivery(kind):
    """Protect public direct API functions as well as host-dispatched calls."""
    def decorate(function):
        @wraps(function)
        def guarded(*args, **kwargs):
            inputs = kwargs.get('inputs', args[0] if args else None)
            root = kwargs.get('evidence_root', args[1] if len(args) > 1 else None)
            if not isinstance(inputs, Mapping) or root is None:
                raise Stop('Delivery requires location-bound inputs and an evidence root')
            with evidence_lease(root, inputs.get('location_id'), kind=kind):
                return function(*args, **kwargs)
        return guarded
    return decorate
