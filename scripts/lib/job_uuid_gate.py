"""S75-T02: a write path gated on the recurring job's UUID.

Invariant (literal reading of the unit title): if the expected job UUID is
wrong or missing, the affected writes are REFUSED. There is no fallback --
no first-match pick, no case folding, no whitespace trimming, no default job,
no writing a receipt that names the expected id instead of the observed one.
A prebuilder receipt can only be produced from a proven observation, and it
records the ACTUAL recurring jobID read from the scheduler listing.

Stdlib only. Refusal happens before any file is created, truncated or
replaced, so a refused write leaves the pre-existing bytes untouched.
"""
import hashlib
import json
import os
from pathlib import Path

JOB_UUID_MISSING = 'JOB_UUID_MISSING'
JOB_UUID_MISMATCH = 'JOB_UUID_MISMATCH'
JOB_UUID_AMBIGUOUS = 'JOB_UUID_AMBIGUOUS'
JOB_NOT_RECURRING = 'JOB_NOT_RECURRING'


class WriteRefused(Exception):
    """A gated write was refused. `reason` is one of the four codes."""

    def __init__(self, reason, detail=''):
        self.reason = reason
        self.detail = detail
        super().__init__(f'{reason}: {detail}' if detail else reason)


def _recurring(job):
    """True only when the listing SAYS recurring. Unknown is not recurring.

    An explicit ``recurring: False`` wins over any schedule string: the
    record denies recurrence, so a leftover/non-empty schedule is not
    evidence of it.
    """
    if job.get('recurring') is True:
        return True
    if job.get('recurring') is False:
        return False
    schedule = job.get('schedule')
    return isinstance(schedule, str) and bool(schedule.strip())


def prove_recurring_job_id(expected_job_id, observed_jobs):
    """Return the observed recurring job record, or raise WriteRefused.

    Exact string equality only. Any absent/ambiguous/non-recurring answer
    refuses; nothing is guessed.
    """
    if not isinstance(expected_job_id, str) or not expected_job_id:
        raise WriteRefused(JOB_UUID_MISSING, 'expected job UUID absent')
    jobs = list(observed_jobs)
    matches = [j for j in jobs if j.get('id') == expected_job_id]
    if not matches:
        raise WriteRefused(
            JOB_UUID_MISMATCH,
            f'{expected_job_id!r} not present in {len(jobs)} observed job(s)')
    if len(matches) > 1:
        raise WriteRefused(JOB_UUID_AMBIGUOUS,
                           f'{len(matches)} observed jobs share the id')
    job = matches[0]
    if not _recurring(job):
        raise WriteRefused(JOB_NOT_RECURRING,
                           f"{expected_job_id!r} is not recurring")
    return job


def guarded_write(path, payload, *, expected_job_id, observed_jobs):
    """Write `payload` (str or bytes) only after the UUID is proven.

    Refuses before touching the filesystem. Atomic replace on success.
    """
    job = prove_recurring_job_id(expected_job_id, observed_jobs)
    target = Path(path)
    data = payload.encode('utf-8') if isinstance(payload, str) else payload
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + '.tmp')
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return {'path': str(target), 'bytes': len(data),
            'actual_recurring_job_id': job['id']}


def build_prebuilder_receipt(*, expected_job_id, observed_jobs,
                             prompt_body=b''):
    """Receipt proving the actual recurring jobID. Raises when unproven."""
    jobs = list(observed_jobs)
    job = prove_recurring_job_id(expected_job_id, jobs)
    body = (prompt_body.encode('utf-8') if isinstance(prompt_body, str)
            else prompt_body)
    return {
        'unit': 'S75-T02',
        'expected_job_id': expected_job_id,
        'actual_recurring_job_id': job['id'],
        'job_uuid_proven': True,
        'job_recurring': True,
        'observation_count': len(jobs),
        'prompt_body_sha256': hashlib.sha256(body).hexdigest(),
        'prompt_body_bytes': len(body),
        'refusal': None,
    }


def write_prebuilder_receipt(path, **kwargs):
    """Emit the receipt as JSON, refusals included, with no partial file."""
    receipt = build_prebuilder_receipt(**kwargs)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + '.tmp')
    tmp.write_text(json.dumps(receipt, indent=1, sort_keys=True) + '\n')
    os.replace(tmp, target)
    return receipt
