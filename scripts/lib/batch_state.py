"""Skill 06 batch state machine, immutable candidates, merge gates
(Master Plan v3.0 section 7, checklist C3). Stdlib-only, deterministic.

Provides:
  - BatchLatch: ONE active batch at a time across CI waits (plan 7.1/7.2).
    Timer ticks coalesce to a single next_batch_requested flag (S04); two
    supervisors can never both start batches (S05).
  - BatchRecord: the plan 7.2 ladder
    COLLECTING -> FROZEN -> ASSEMBLING -> TESTING -> REVIEWED -> PUSHED
    -> REMOTE_CHECKS -> QUEUED_FOR_MERGE -> MERGING -> MERGE_VERIFICATION
    -> CLEANUP -> CLOSED, plus FAILED_PRESERVED (only with durable recovery
    refs + evidence) and MERGE_STATUS_UNKNOWN (stays ACTIVE until
    reconciled).
  - CandidateFreeze: immutable candidate SHAs with tests+QC recorded
    against exact heads (C3 line a). New commits after the freeze go to the
    next batch (S06); checks on old SHAs are never accepted (S07).
  - MergeTransaction: MERGED_VERIFIED only after server-side merge + target
    fetch + post-merge smoke (C3 line c). A merge timeout is an unknown
    result, reconciled, never blind-repeated (S08); a closed-unmerged PR is
    not landed (S10); a squash/rebase ancestry gap requires a retained
    recovery ref (S11).
"""
import fcntl
import json
import os
import re
import threading
import time
from pathlib import Path

LADDER = ('COLLECTING', 'FROZEN', 'ASSEMBLING', 'TESTING', 'REVIEWED',
          'PUSHED', 'REMOTE_CHECKS', 'QUEUED_FOR_MERGE', 'MERGING',
          'MERGE_VERIFICATION', 'CLEANUP', 'CLOSED')
FAILED_PRESERVED = 'FAILED_PRESERVED'
MERGE_STATUS_UNKNOWN = 'MERGE_STATUS_UNKNOWN'
TERMINAL_STATES = frozenset({LADDER[-1], FAILED_PRESERVED})

_SHA_RE = re.compile(r'^[0-9a-fA-F]{7,64}$')


class StateViolation(Exception):
    pass


class LatchRefused(Exception):
    pass


class MergeBlocked(Exception):
    pass


class StaleCandidate(Exception):
    pass


def _is_sha(value):
    return isinstance(value, str) and bool(_SHA_RE.match(value))


def _load(path, default):
    if not Path(path).exists():
        return dict(default)
    return json.loads(Path(path).read_text())


def _save(path, data):
    path = Path(path)
    # unique tmp per writer: concurrent readers/writers never collide
    tmp = path.with_name(
        f'.{path.name}.{os.getpid()}.{threading.get_ident()}.tmp')
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
    os.replace(tmp, path)


class BatchLatch:
    """Project-wide active-batch latch (plan 7.1: one owner, one queue, one
    active batch) with tick coalescing (plan 7.2 item 2). Every mutation is
    flock-guarded, so two supervisors racing in the same instant can never
    both start a batch."""

    def __init__(self, state_dir, now=time.time):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / 'active-batch-latch.json'
        self.lock_path = self.state_dir / 'active-batch-latch.lock'
        self._now = now

    def _locked(self):
        fh = open(self.lock_path, 'a+')
        fcntl.flock(fh, fcntl.LOCK_EX)
        return fh

    def _read(self):
        return _load(self.state_path, {'active_batch_id': None,
                                       'next_batch_requested': False,
                                       'tick_count': 0})

    def start_batch(self, batch_id):
        """Start (or resume) a batch. Refused while another batch is
        active — a second supervisor can never start a competing batch."""
        fh = self._locked()
        try:
            state = self._read()
            active = state.get('active_batch_id')
            if active is not None and active != batch_id:
                raise LatchRefused(f'batch {active} is still active')
            state['active_batch_id'] = batch_id
            state['started_at'] = self._now()
            _save(self.state_path, state)
            return batch_id
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()

    def tick(self):
        """Timer tick: coalesce to ONE next_batch_requested=True no matter
        how many ticks fire while the batch is active (S04)."""
        fh = self._locked()
        try:
            state = self._read()
            if state.get('active_batch_id') is not None:
                state['tick_count'] = state.get('tick_count', 0) + 1
                state['next_batch_requested'] = True   # coalescing write
                _save(self.state_path, state)
            return state.get('next_batch_requested', False)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()

    def finish_batch(self, batch_id):
        """Close the active batch. Returns the drained next-batch request."""
        fh = self._locked()
        try:
            state = self._read()
            if state.get('active_batch_id') != batch_id:
                raise LatchRefused(
                    f'batch {batch_id} is not the active batch')
            run_next = bool(state.get('next_batch_requested'))
            _save(self.state_path,
                  {'active_batch_id': None, 'next_batch_requested': False,
                   'tick_count': 0})
            return run_next
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()

    def status(self):
        return self._read()


class BatchRecord:
    """Persisted per-batch state machine (plan 7.2 ladder)."""

    def __init__(self, state_dir, batch_id, now=time.time):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.batch_id = batch_id
        self.state_path = self.state_dir / f'{batch_id}-state.json'
        self._now = now
        if not self.state_path.exists():
            _save(self.state_path, {
                'batch_id': batch_id, 'state': LADDER[0],
                'state_history': [{'state': LADDER[0], 'ts': self._now(),
                                   'note': 'created'}],
                'updated_at': self._now()})

    def _read(self):
        return json.loads(self.state_path.read_text())

    def transition(self, to, note=''):
        """Move (or annotate) the state. Ladder moves only forward (or the
        same state as an annotation, as real receipts do); FAILED_PRESERVED
        needs the fail() gate; MERGE_STATUS_UNKNOWN enters from the merge
        states and leaves only by reconciliation."""
        if to not in LADDER and to not in (FAILED_PRESERVED,
                                           MERGE_STATUS_UNKNOWN):
            raise StateViolation(f'unknown state {to!r}')
        data = self._read()
        cur = data['state']
        if cur in TERMINAL_STATES:
            raise StateViolation(f'batch already terminal: {cur}')
        if to == FAILED_PRESERVED:
            raise StateViolation('use fail(): FAILED_PRESERVED needs durable '
                                 'recovery refs and evidence')
        if to == MERGE_STATUS_UNKNOWN:
            if cur not in LADDER[LADDER.index('PUSHED'):
                                 LADDER.index('MERGING') + 1]:
                raise StateViolation(
                    f'MERGE_STATUS_UNKNOWN not valid from {cur}')
        elif cur == MERGE_STATUS_UNKNOWN:
            pass  # reconciliation may land on any ladder state
        elif to in LADDER:
            if to != cur and LADDER.index(to) < LADDER.index(cur):
                raise StateViolation(f'{cur} -> {to} is not forward progress')
        data['state'] = to
        data['state_history'].append({'state': to, 'ts': self._now(),
                                      'note': note})
        data['updated_at'] = self._now()
        _save(self.state_path, data)
        return to

    @property
    def state(self):
        return self._read()['state']

    def is_active(self):
        """Any nonterminal state keeps the active-batch latch set, including
        MERGE_STATUS_UNKNOWN until reconciled."""
        return self.state not in TERMINAL_STATES

    def fail(self, reason, recovery_ref, evidence_paths):
        """FAILED_PRESERVED only after recovery refs/evidence are durable
        (plan 7.2). It never silently reopens the lock to a second owner."""
        if not recovery_ref:
            raise StateViolation('FAILED_PRESERVED requires a durable '
                                 'recovery ref')
        if not evidence_paths:
            raise StateViolation('FAILED_PRESERVED requires preserved '
                                 'evidence paths')
        data = self._read()
        if data['state'] in TERMINAL_STATES:
            raise StateViolation(f'batch already terminal: {data["state"]}')
        data['state'] = FAILED_PRESERVED
        data['recovery_ref'] = recovery_ref
        data['evidence_paths'] = list(evidence_paths)
        data['state_history'].append(
            {'state': FAILED_PRESERVED, 'ts': self._now(), 'note': reason})
        data['updated_at'] = self._now()
        _save(self.state_path, data)
        return FAILED_PRESERVED


class CandidateFreeze:
    """Immutable candidate SHAs with tests+QC recorded against exact heads.

    freeze() fixes the candidate once CI/review begins (plan 7.3). Any new
    commit goes to the next batch via stage_after_freeze (S06). A repair
    that changes the candidate is a NEW revision (revise()) and the old
    revision's checks are never accepted for the new head (S07)."""

    def __init__(self, state_dir, batch_id, now=time.time):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.batch_id = batch_id
        self.path = self.state_dir / f'{batch_id}-candidate.json'
        self._now = now
        if not self.path.exists():
            _save(self.path, {'batch_id': batch_id, 'frozen': False,
                              'revision': 0, 'units': [], 'checks': [],
                              'next_batch_units': [], 'revisions': []})

    def _read(self):
        return json.loads(self.path.read_text())

    def _validate_units(self, candidate_sha, units):
        problems = []
        if not _is_sha(candidate_sha):
            problems.append(f'candidate_sha not a sha: {candidate_sha!r}')
        if not units:
            problems.append('no units')
        for u in units:
            name = u.get('name', '?')
            if not _is_sha(u.get('source_sha')):
                problems.append(f'unit {name}: missing immutable source_sha')
            for t in u.get('tests', []):
                if t.get('head_sha') != candidate_sha:
                    problems.append(
                        f'unit {name}: test {t.get("suite")} recorded at '
                        f'{t.get("head_sha")}, not candidate head')
                if t.get('verdict') != 'pass':
                    problems.append(f'unit {name}: test {t.get("suite")} '
                                    f'verdict {t.get("verdict")!r}')
            qc = u.get('qc') or {}
            if qc.get('head_sha') != candidate_sha:
                problems.append(f'unit {name}: QC recorded at '
                                f'{qc.get("head_sha")}, not candidate head')
            if qc.get('verdict') != 'pass':
                problems.append(f'unit {name}: QC verdict '
                                f'{qc.get("verdict")!r}')
            if not u.get('files'):
                problems.append(f'unit {name}: no declared files')
        return problems

    def freeze(self, base_sha, candidate_sha, units):
        """Freeze the candidate. Refused unless tests+QC are recorded
        against the exact candidate head and every unit is complete."""
        data = self._read()
        if data['frozen']:
            raise StaleCandidate('candidate already frozen; new work goes '
                                 'to the next batch (S06)')
        if not _is_sha(base_sha):
            raise StateViolation(f'base_sha not a sha: {base_sha!r}')
        problems = self._validate_units(candidate_sha, units)
        if problems:
            raise StateViolation('freeze refused: ' + '; '.join(problems))
        data.update({'frozen': True, 'revision': 1, 'base_sha': base_sha,
                     'candidate_sha': candidate_sha,
                     'units': [dict(u) for u in units],
                     'frozen_at': self._now()})
        _save(self.path, data)
        return candidate_sha

    def revise(self, candidate_sha, units):
        """A repair that changes the candidate creates a NEW revision
        (plan 7.3); the old revision is retained as the recovery mapping."""
        data = self._read()
        if not data['frozen']:
            raise StateViolation('revise() requires a frozen candidate')
        problems = self._validate_units(candidate_sha, units)
        if problems:
            raise StateViolation('revision refused: ' + '; '.join(problems))
        data['revisions'].append(
            {'revision': data['revision'],
             'candidate_sha': data['candidate_sha'],
             'base_sha': data.get('base_sha'), 'ts': self._now()})
        data.update({'revision': data['revision'] + 1,
                     'candidate_sha': candidate_sha,
                     'units': [dict(u) for u in units],
                     'frozen_at': self._now()})
        _save(self.path, data)
        return candidate_sha

    def stage_after_freeze(self, unit):
        """Post-freeze work is staged for the NEXT batch (S06) — the frozen
        candidate set is immutable."""
        data = self._read()
        if not data['frozen']:
            raise StateViolation('freeze the candidate first')
        data['next_batch_units'].append(dict(unit))
        _save(self.path, data)
        return list(data['next_batch_units'])

    def record_check(self, head_sha, name, verdict):
        """Record a CI/review result against the exact head it ran on."""
        if not _is_sha(head_sha):
            raise StateViolation(f'check head_sha not a sha: {head_sha!r}')
        data = self._read()
        data['checks'].append({'head_sha': head_sha, 'name': name,
                               'verdict': verdict, 'ts': self._now()})
        _save(self.path, data)

    def accepted_checks(self, at_sha=None):
        """Only checks recorded against the EXACT head count (S07: checks
        from an old SHA are never accepted for a newer one)."""
        data = self._read()
        head = data.get('candidate_sha') if at_sha is None else at_sha
        return [c for c in data['checks'] if c['head_sha'] == head]

    def checks_green(self, at_sha=None):
        accepted = self.accepted_checks(at_sha)
        return bool(accepted) and all(c['verdict'] == 'pass'
                                      for c in accepted)

    def verify(self):
        """(ok, problems): frozen set intact, tests+QC on exact heads."""
        data = self._read()
        problems = []
        if not data['frozen']:
            problems.append('not frozen')
        problems += self._validate_units(data.get('candidate_sha'),
                                         data.get('units', []))
        for old in data.get('revisions', []):
            if not _is_sha(old.get('candidate_sha')):
                problems.append(f'revision {old.get("revision")}: '
                                'lost candidate mapping')
        return (not problems, problems)

    @property
    def candidate_sha(self):
        return self._read().get('candidate_sha')

    @property
    def next_batch_units(self):
        return self._read().get('next_batch_units', [])


class MergeTransaction:
    """Merge gates of plan 7.4: MERGED_VERIFIED only after the server-side
    PR merge, a fetched target with proven inclusion, and a post-merge
    smoke pass."""

    def __init__(self, state_dir, batch_id, now=time.time):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.batch_id = batch_id
        self.path = self.state_dir / f'{batch_id}-merge.json'
        self._now = now
        if not self.path.exists():
            _save(self.path, {'batch_id': batch_id,
                              'merge_request_open': False,
                              'server_outcome': None, 'target_fetch': None,
                              'post_merge_smoke': None,
                              'status': 'NEW'})

    def _read(self):
        return json.loads(self.path.read_text())

    def record_candidate(self, candidate_sha, pr_number=None):
        data = self._read()
        data['candidate_sha'] = candidate_sha
        data['pr_number'] = pr_number
        _save(self.path, data)

    def request_merge(self):
        """Submit the merge through the repository's normal mechanism.
        Refused while a previous request is unresolved (S08: a timeout is
        reconciled, never blind-repeated)."""
        data = self._read()
        if data.get('merge_request_open') and data.get('status') \
                == MERGE_STATUS_UNKNOWN:
            raise MergeBlocked('merge result unknown: reconcile before any '
                               'new request (S08)')
        if data.get('merge_request_open'):
            raise MergeBlocked('merge request already open')
        data['merge_request_open'] = True
        data['status'] = 'MERGE_REQUESTED'
        data['requested_at'] = self._now()
        _save(self.path, data)

    def merge_timeout(self):
        """A timed-out request is an UNKNOWN result — the batch stays
        active (MERGE_STATUS_UNKNOWN) until reconciled."""
        data = self._read()
        if not data.get('merge_request_open'):
            raise MergeBlocked('no open merge request')
        data['status'] = MERGE_STATUS_UNKNOWN
        _save(self.path, data)
        return MERGE_STATUS_UNKNOWN

    def reconcile(self, server_state):
        """Resolve an unknown/claimed merge against observed server state:
        {merged, closed, merge_commit, method}. A closed-unmerged PR is
        NOT landed (S10)."""
        data = self._read()
        merged = bool(server_state.get('merged'))
        closed = bool(server_state.get('closed'))
        if merged:
            outcome = 'MERGED'
        elif closed:
            outcome = 'CLOSED_UNMERGED'
        else:
            outcome = 'STILL_OPEN'
        data['server_outcome'] = outcome
        data['merge_commit'] = server_state.get('merge_commit')
        data['merge_method'] = server_state.get('method')
        data['merge_request_open'] = False      # resolved, not re-fired
        data['status'] = outcome
        _save(self.path, data)
        return outcome

    def record_target_fetch(self, target_sha, ancestry_ok, content_matches,
                            recovery_ref=None):
        """Record the fetched target and the inclusion proof. A squash or
        rebase leaves an ancestry gap: content match plus a RETAINED
        recovery ref is then required (S11); without one it is refused."""
        if not _is_sha(target_sha):
            raise StateViolation(f'target_sha not a sha: {target_sha!r}')
        if not ancestry_ok and not (content_matches and recovery_ref):
            raise MergeBlocked('ancestry gap without content match + '
                               'retained recovery ref (S11)')
        data = self._read()
        data['target_fetch'] = {
            'target_sha': target_sha, 'ancestry_ok': bool(ancestry_ok),
            'content_matches': bool(content_matches),
            'recovery_ref': recovery_ref, 'ts': self._now()}
        _save(self.path, data)

    def record_post_merge_smoke(self, verdict):
        data = self._read()
        data['post_merge_smoke'] = {'verdict': verdict, 'ts': self._now()}
        _save(self.path, data)

    def merged_verified(self):
        """(ok, reasons): server-side merge + target inclusion + post-merge
        smoke — nothing less qualifies as landed (plan 8.1)."""
        data = self._read()
        reasons = []
        if data.get('server_outcome') != 'MERGED':
            reasons.append(f'server outcome {data.get("server_outcome")!r}')
        tf = data.get('target_fetch')
        if not tf:
            reasons.append('target not fetched/proven')
        else:
            if not tf.get('ancestry_ok') and not (
                    tf.get('content_matches') and tf.get('recovery_ref')):
                reasons.append('inclusion unproven (ancestry gap without '
                               'recovery ref)')
        smoke = data.get('post_merge_smoke')
        if not smoke or smoke.get('verdict') != 'pass':
            reasons.append('post-merge smoke not passed')
        return (not reasons, reasons)

    def mark_merged_verified(self):
        ok, reasons = self.merged_verified()
        if not ok:
            raise MergeBlocked('MERGED_VERIFIED withheld: ' + '; '.join(reasons))
        data = self._read()
        data['status'] = 'MERGED_VERIFIED'
        _save(self.path, data)
        return data['status']
