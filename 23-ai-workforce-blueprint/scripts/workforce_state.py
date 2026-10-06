"""Serialized, crash-safe workforce state updates (Python 3.9+, POSIX).

The persistent lock inode is never unlinked. Readers return a revisioned snapshot;
commits merge unrelated updates and reject changes to the same field. Shell
writers use `jq` mode, which holds the lock across read/filter/replace.
"""
from __future__ import annotations
import copy
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager

class StateConflict(RuntimeError):
    pass

class Snapshot(dict):
    def __init__(self, value):
        super().__init__(value)
        self.base = copy.deepcopy(value)

@contextmanager
def lock(path, blocking=True):
    p = Path(str(path) + '.write.lock')
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a+') as handle:
        deadline = time.monotonic() + float(os.environ.get('WORKFORCE_STATE_LOCK_TIMEOUT', '30'))
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not blocking:
                    raise
                if time.monotonic() >= deadline:
                    raise StateConflict('state writer busy; retry without overwriting: ' + str(path))
                time.sleep(0.05)
        try:
            yield handle
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)

def owns_runner(path):
    """Only an inherited, already-held descriptor proves nested runner ownership."""
    if os.environ.get('WORKFORCE_RUNNER_PATH') != str(Path(path).resolve()):
        return False
    try:
        fd=int(os.environ['WORKFORCE_RUNNER_FD'])
        held=os.fstat(fd); actual=os.stat(str(path)+'.write.lock')
        if (held.st_dev,held.st_ino)!=(actual.st_dev,actual.st_ino):return False
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return True
    except (KeyError,ValueError,OSError):return False

def read(path):
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        data = {}
    if not isinstance(data, dict):
        raise ValueError('build state must be an object')
    return Snapshot(data)

def atomic_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(value, handle, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

_MISSING = object()
def _merge(base, desired, current, location='state'):
    out = copy.deepcopy(current)
    for key in set(base) | set(desired):
        old, new, actual = base.get(key, _MISSING), desired.get(key, _MISSING), current.get(key, _MISSING)
        if old == new:
            continue
        if isinstance(old, dict) and isinstance(new, dict) and isinstance(actual, dict):
            out[key] = _merge(old, new, actual, location + '.' + key)
        elif actual != old and actual != new:
            raise StateConflict('concurrent change at ' + location + '.' + key)
        elif new is _MISSING:
            out.pop(key, None)
        else:
            out[key] = copy.deepcopy(new)
    return out

def commit(path, state):
    if not isinstance(state, Snapshot):
        raise TypeError('commit requires a snapshot from workforce_state.read')
    with lock(path):
        current = read(path)
        merged = _merge(state.base, state, current)
        merged['stateRevision'] = int(current.get('stateRevision', 0)) + 1
        atomic_write(path, merged)
    state.clear()
    state.update(merged)
    state.base = copy.deepcopy(merged)
    return state

def update(path, mutate):
    with lock(path):
        state = read(path)
        result = mutate(state)
        state['stateRevision'] = int(state.get('stateRevision', 0)) + 1
        atomic_write(path, state)
        return result

if __name__ == '__main__':
    mode, path, *args = sys.argv[1:]
    if mode == 'jq':
        def transform(state):
            run = subprocess.run(['jq', *args], input=json.dumps(state), text=True,
                                 capture_output=True, check=True, timeout=30)
            revised = json.loads(run.stdout)
            if not isinstance(revised, dict):
                raise ValueError('state filter must return one object')
            state.clear()
            state.update(revised)
        update(path, transform)
    elif mode == 'run':
        # OS releases on death; never age-unlock or delete someone else's inode.
        try:
            with lock(path, blocking=False) as held:
                env = dict(os.environ, WORKFORCE_RUNNER_OWNER=str(os.getpid()), WORKFORCE_RUNNER_PATH=str(Path(path).resolve()), WORKFORCE_RUNNER_FD=str(held.fileno()))
                raise SystemExit(subprocess.call(args, env=env, pass_fds=(held.fileno(),)))
        except BlockingIOError:
            print('workforce runner already active', file=sys.stderr)
            raise SystemExit(75)
    else:
        raise SystemExit('unknown mode')
