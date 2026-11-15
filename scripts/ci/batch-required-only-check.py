#!/usr/bin/env python3
"""Batch pull requests run only the required checks.

Fails when:
  * a workflow that produces a required check (REQUIRED_WORKFLOWS) carries the
    batch skip condition, or
  * any other workflow with a pull_request trigger has a job without it.
The one deliberate exception is EXEMPT_WORKFLOWS (the aggregator that hosts this guard).

The read is a small block-style scan of the two things this guard needs (the
pull_request trigger and each job's `if:`), not a general YAML load: the guard
runs on the setup-python interpreter, which ships no YAML module, and a guard
that dies on its own import polices nothing. The scan is exact for this
repository's workflow files -- `on:` blocks only, job keys at two spaces, job
bodies at four -- and `--self-test` pins the three verdicts.
Self-test: python3 scripts/ci/batch-required-only-check.py --self-test
"""
import glob, os, re, sys

REQUIRED_WORKFLOWS = {'ghl-mcp-supervised-guard.yml', 'qc-static.yml', 'version-consistency.yml'}
EXEMPT_WORKFLOWS = set()
NEEDLE = "!startsWith(github.head_ref, 'batch/')"

TOP_KEY = re.compile(r"^([A-Za-z_][\w-]*|'[^']*'|\"[^\"]*\")\s*:\s*(.*)$")
JOB_KEY = re.compile(r"^  ([^\s#][^:]*?)\s*:\s*(?:#.*)?$")
JOB_IF = re.compile(r"^    if:\s*(.*)$")


def _indent(line):
    return len(line) - len(line.lstrip(' '))


def _block(lines, start):
    """Lines strictly inside the block opened at `start` (the key's line)."""
    base = _indent(lines[start])
    out = []
    for line in lines[start + 1:]:
        if not line.strip() or line.lstrip().startswith('#'):
            out.append(line)
            continue
        if _indent(line) <= base:
            break
        out.append(line)
    return out


def _scan_on(rest, body):
    """True when the `on:` this rest/body describes includes pull_request."""
    rest = rest.split(' #', 1)[0].strip()
    if rest:
        return bool(re.search(r"\bpull_request\b", rest))
    for line in body:
        text = line.strip()
        if re.match(r"^-?\s*['\"]?pull_request['\"]?\s*(?::|$)", text):
            return True
    return False


def _scan_jobs(body):
    """{job id: the text of that job's `if:` ('' when absent)}."""
    jobs, current = {}, None
    lines = ['jobs:'] + body
    for i, line in enumerate(lines):
        m = JOB_KEY.match(line)
        if m:
            current = m.group(1).strip().strip('\'"')
            jobs[current] = ''
            continue
        if current is None:
            continue
        m = JOB_IF.match(line)
        if m:
            value = m.group(1).split(' #', 1)[0].strip()
            if value[:1] in ('>', '|'):
                value = ' '.join(l.strip() for l in _block(lines, i))
            jobs[current] = value
    return jobs


def scan(text):
    """{'pull_request': bool, 'jobs': {id: if text}} for one workflow file."""
    lines = text.splitlines()
    result = {'pull_request': False, 'jobs': {}}
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip() or line.lstrip().startswith('#') or _indent(line):
            i += 1
            continue
        m = TOP_KEY.match(line)
        if m:
            key = m.group(1).strip('\'"')
            if key == 'on':
                result['pull_request'] = _scan_on(m.group(2), _block(lines, i))
            elif key == 'jobs':
                result['jobs'] = _scan_jobs(_block(lines, i))
        i += 1
    return result


def check(workflows):
    """workflows: {basename: scan() result}. Returns a list of problems."""
    bad = []
    for name, wf in sorted(workflows.items()):
        jobs = wf['jobs']
        has = {j: NEEDLE in (cond or '') for j, cond in jobs.items()}
        if name in REQUIRED_WORKFLOWS:
            bad += [f'{name}:{j} is a required-check job and must NOT skip batch PRs' for j, h in has.items() if h]
        elif wf['pull_request'] and name not in EXEMPT_WORKFLOWS:
            bad += [f'{name}:{j} lacks `if: ${{{{ {NEEDLE} }}}}` (batch PRs run only required checks)' for j, h in has.items() if not h]
    return bad


def load():
    out = {}
    for path in sorted(glob.glob('.github/workflows/*.yml')):
        with open(path, encoding='utf-8') as fh:
            out[os.path.basename(path)] = scan(fh.read())
    return out


def main():
    if '--self-test' in sys.argv:
        ok = {'a.yml': {'pull_request': True, 'jobs': {'j': '${{ %s }}' % NEEDLE}}}
        assert not check(ok)
        assert check({'a.yml': {'pull_request': True, 'jobs': {'j': ''}}}), 'missing skip must fail'
        assert check({'qc-static.yml': {'pull_request': True, 'jobs': {'j': NEEDLE}}}), 'required skip must fail'
        assert not check({'a.yml': {'pull_request': False, 'jobs': {'j': ''}}}), 'no pull_request trigger must not fail'
        assert scan("on:\n  pull_request:\njobs:\n  a:\n    runs-on: x\n") == {
            'pull_request': True, 'jobs': {'a': ''}}, scan("on:\n  pull_request:\njobs:\n  a:\n    runs-on: x\n")
        assert scan("on:\n  push:\njobs:\n  a:\n    if: ${{ %s }}\n" % NEEDLE) == {
            'pull_request': False, 'jobs': {'a': '${{ %s }}' % NEEDLE}}
        print('self-test OK')
        return 0
    bad = check(load())
    for b in bad:
        print('FAIL', b)
    print('batch-required-only: %s' % ('FAIL' if bad else 'OK'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
