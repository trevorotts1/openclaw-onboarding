"""Skill 06 swarm controls (Master Plan v3.0 section 6).

Stdlib-only, deterministic, no LLM calls. Provides:
  - AdmissionLedger: agent slots (4 active at start, 6 max), 1 heavy job
    host-wide, 1 browser lease. Restart with the same owner resumes its
    tokens instead of duplicating them.
  - child_env(): route TMPDIR/npm/pip/xdg caches to the external run dirs
    for project children only; the parent environment is never mutated.
  - health_check(): the 60-second host-health/lease/storage check.
  - MergeLock: merge-ownership lock held for the whole batch critical
    section (flock), with persisted batch state and a fenced generation
    counter — never conversational memory as the lock. A crash frees the
    flock and leaves state for resume (same owner+batch, no duplicate) or
    takeover (generation bumped, stale writer fenced).

CLI (used by supervision loops and fault tests):
  python3 swarm_controls.py health --internal P --external P
  python3 swarm_controls.py claim-merge --state-dir D --owner O
      [--batch B] [--hold S] [--barrier FILE]
"""
import fcntl
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

GIB = 1024 ** 3

AGENT_START_CAP = 4
AGENT_MAX_CAP = 6
HEAVY_CAP = 1
BROWSER_CAP = 1


class SlotRefused(Exception):
    pass


class StaleGeneration(Exception):
    pass


class AdmissionLedger:
    """File-backed admission tokens (flock + JSON). One ledger per project."""

    def __init__(self, state_dir, now=time.time):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / 'admission-ledger.json'
        self.lock_path = self.state_dir / 'admission-ledger.lock'
        self._now = now

    def _locked(self):
        fh = open(self.lock_path, 'a+')
        fcntl.flock(fh, fcntl.LOCK_EX)
        return fh

    def _read(self):
        if not self.state_path.exists():
            return {'agent_cap': AGENT_START_CAP, 'tokens': {}}
        return json.loads(self.state_path.read_text())

    def _write(self, state):
        tmp = self.state_path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
        os.replace(tmp, self.state_path)

    def _cap(self, state, kind):
        if kind == 'agent':
            return state.get('agent_cap', AGENT_START_CAP)
        return {'heavy': HEAVY_CAP, 'browser': BROWSER_CAP}[kind]

    def acquire(self, kind, owner):
        """Return a token id. Same owner+kind resumes the existing token."""
        if kind not in ('agent', 'heavy', 'browser'):
            raise ValueError(kind)
        fh = self._locked()
        try:
            state = self._read()
            tokens = state['tokens']
            for tid, tok in tokens.items():
                if tok['kind'] == kind and tok['owner'] == owner:
                    tok['heartbeat_at'] = self._now()
                    self._write(state)
                    return tid
            held = sum(1 for t in tokens.values() if t['kind'] == kind)
            if held >= self._cap(state, kind):
                raise SlotRefused(f'{kind} cap reached ({held})')
            tid = f'{kind}-{os.urandom(4).hex()}'
            now = self._now()
            tokens[tid] = {'kind': kind, 'owner': owner,
                           'acquired_at': now, 'heartbeat_at': now}
            self._write(state)
            return tid
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()

    def heartbeat(self, token_id):
        fh = self._locked()
        try:
            state = self._read()
            tok = state['tokens'].get(token_id)
            if tok is None:
                raise SlotRefused(f'unknown token {token_id}')
            tok['heartbeat_at'] = self._now()
            self._write(state)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()

    def release(self, token_id):
        fh = self._locked()
        try:
            state = self._read()
            state['tokens'].pop(token_id, None)
            self._write(state)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()

    def sweep_stale(self, max_age_s=120):
        """Drop tokens whose heartbeat expired (dead workers free slots)."""
        fh = self._locked()
        try:
            state = self._read()
            now = self._now()
            stale = [tid for tid, t in state['tokens'].items()
                     if now - t['heartbeat_at'] > max_age_s]
            for tid in stale:
                del state['tokens'][tid]
            self._write(state)
            return stale
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()

    def expand_agent_cap(self):
        """Raise 4 -> 6 only after healthy measurements; clamps at max."""
        fh = self._locked()
        try:
            state = self._read()
            state['agent_cap'] = min(state.get('agent_cap', AGENT_START_CAP) + 2,
                                     AGENT_MAX_CAP)
            self._write(state)
            return state['agent_cap']
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()

    def counts(self):
        state = self._read()
        out = {'agent': 0, 'heavy': 0, 'browser': 0}
        for t in state['tokens'].values():
            out[t['kind']] += 1
        out['agent_cap'] = state.get('agent_cap', AGENT_START_CAP)
        return out


def child_env(base_env, external_root):
    """Env dict for a project child process with tmp/caches on the external
    run dirs. The caller's own environment is never touched (children only)."""
    root = Path(external_root)
    env = dict(base_env)
    env['TMPDIR'] = str(root / 'tmp')
    env['npm_config_cache'] = str(root / 'cache' / 'npm')
    env['PIP_CACHE_DIR'] = str(root / 'cache' / 'pip')
    env['XDG_CACHE_HOME'] = str(root / 'cache' / 'xdg')
    return env


def _disk_free_gib(path):
    return shutil.disk_usage(path).free / GIB


def _mem_free_gib():
    try:
        out = subprocess.run(['vm_stat'], capture_output=True, text=True,
                             timeout=5).stdout
        page = 4096
        free = 0
        for line in out.splitlines():
            if 'page size of' in line:
                page = int(line.split()[7])
            if line.startswith(('Pages free', 'Pages inactive')):
                free += int(line.split()[-1].rstrip('.'))
        return free * page / GIB
    except Exception:
        return None


def health_check(internal_root, external_root):
    """60-second deterministic host-health/lease/storage check (section 6.3
    initial thresholds). No LLM. Verdicts: start | hold | critical."""
    def band(free_gib, ok, hold):
        return 'start' if free_gib >= ok else ('hold' if free_gib >= hold else 'critical')

    internal_free = _disk_free_gib(internal_root)
    external_free = _disk_free_gib(external_root)
    internal_verdict = band(internal_free, 25, 10)
    external_verdict = band(external_free, 40, 15)
    order = {'start': 0, 'hold': 1, 'critical': 2}
    overall = max([internal_verdict, external_verdict], key=order.get)
    mem = _mem_free_gib()
    if mem is not None:
        mem_verdict = 'start' if mem >= 6 else ('hold' if mem >= 2 else 'critical')
        overall = max([overall, mem_verdict], key=order.get)
    return {
        'internal_free_gib': round(internal_free, 2),
        'external_free_gib': round(external_free, 2),
        'mem_free_gib': None if mem is None else round(mem, 2),
        'loadavg': list(os.getloadavg()),
        'internal_verdict': internal_verdict,
        'external_verdict': external_verdict,
        'overall': overall,
    }


class MergeLock:
    """Merge-ownership lock: the flock is HELD for the whole batch critical
    section (two live supervisors can never both own it). Batch state is
    persisted as JSON with a fenced generation counter.

    - Crash: the kernel frees the flock, state stays. The same owner+batch
      resumes at the same generation (restart resumes, never duplicates).
    - Takeover (different owner/batch after a crash): generation is bumped,
      so a returning stale writer's complete() is refused.
    - complete()/release() release the held flock when done."""

    def __init__(self, state_dir, now=time.time):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.state_dir / 'merge-batch.lock'
        self.state_path = self.state_dir / 'merge-batch-state.json'
        self._now = now
        self._held = None
        self._generation = None

    def _read(self):
        if not self.state_path.exists():
            return {'owner': None, 'batch_id': None, 'generation': 0,
                    'status': 'idle'}
        return json.loads(self.state_path.read_text())

    def _write(self, state):
        state['updated_at'] = self._now()
        tmp = self.state_path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
        os.replace(tmp, self.state_path)

    def _acquire_blocking(self, timeout_s=5.0):
        fh = open(self.lock_path, 'a+')
        deadline = time.time() + timeout_s
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fh
            except BlockingIOError:
                if time.time() >= deadline:
                    fh.close()
                    raise SlotRefused('merge lock busy')
                time.sleep(0.05)

    def _unlock(self):
        if self._held is not None:
            try:
                fcntl.flock(self._held, fcntl.LOCK_UN)
            except OSError:
                pass
            self._held.close()
            self._held = None

    def try_acquire(self, owner, batch_id):
        """Return (True, generation) when owned, (False, None) when another
        live supervisor holds the lock right now."""
        if self._held is not None:
            return (True, self._generation)  # already own it
        fh = open(self.lock_path, 'a+')
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            return (False, None)
        state = self._read()
        if (state.get('status') == 'active' and state.get('owner') == owner
                and state.get('batch_id') == batch_id):
            self._held = fh                    # restart resumes same batch
            self._generation = state['generation']
            return (True, state['generation'])
        state = {'owner': owner, 'batch_id': batch_id,
                 'generation': state.get('generation', 0) + 1,
                 'status': 'active'}
        self._write(state)
        self._held = fh
        self._generation = state['generation']
        return (True, state['generation'])

    def complete(self, expected_generation, result='merged'):
        """Fenced write: refuses if ownership moved since expected_generation."""
        fh = self._held if self._held is not None else self._acquire_blocking()
        try:
            state = self._read()
            if state.get('generation') != expected_generation:
                raise StaleGeneration(
                    f'generation {state.get("generation")} != {expected_generation}')
            state['status'] = 'done'
            state['result'] = result
            self._write(state)
        finally:
            if fh is self._held:
                self._unlock()
            else:
                try:
                    fcntl.flock(fh, fcntl.LOCK_UN)
                finally:
                    fh.close()

    def release(self):
        fh = self._held if self._held is not None else self._acquire_blocking()
        try:
            state = self._read()
            state['status'] = 'idle'
            self._write(state)
        finally:
            if fh is self._held:
                self._unlock()
            else:
                try:
                    fcntl.flock(fh, fcntl.LOCK_UN)
                finally:
                    fh.close()


def main(argv):
    import argparse
    p = argparse.ArgumentParser(description='Skill 06 swarm controls')
    sub = p.add_subparsers(dest='cmd', required=True)
    h = sub.add_parser('health')
    h.add_argument('--internal', required=True)
    h.add_argument('--external', required=True)
    c = sub.add_parser('claim-merge')
    c.add_argument('--state-dir', required=True)
    c.add_argument('--owner', required=True)
    c.add_argument('--batch', default='cli-batch')
    c.add_argument('--hold', type=float, default=0.0)
    c.add_argument('--barrier', default=None,
                   help='wait for this file to exist before racing to acquire')
    args = p.parse_args(argv)
    if args.cmd == 'health':
        print(json.dumps(health_check(args.internal, args.external), indent=1))
        return 0
    if args.barrier:
        deadline = time.time() + 10
        while not Path(args.barrier).exists():
            if time.time() > deadline:
                print('BARRIER_TIMEOUT')
                return 4
            time.sleep(0.01)
    lock = MergeLock(args.state_dir)
    ok, gen = lock.try_acquire(args.owner, args.batch)
    if not ok:
        print('REFUSED')
        return 3
    print(f'OWNED gen={gen}', flush=True)
    if args.hold > 0:
        time.sleep(args.hold)  # flock stays held: live supervisors stay excluded
    return 0  # exit without complete/release: crash semantics (state kept)


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
