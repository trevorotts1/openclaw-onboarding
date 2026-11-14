#!/usr/bin/env python3
"""Batch pull requests run only the required checks.

Fails when:
  * a workflow that produces a required check (REQUIRED_WORKFLOWS) carries the
    batch skip condition, or
  * any other workflow with a pull_request trigger has a job without it.
The one deliberate exception is EXEMPT_WORKFLOWS (the aggregator that hosts this guard).
Self-test: python3 scripts/ci/batch-required-only-check.py --self-test
"""
import glob, os, sys
import yaml

REQUIRED_WORKFLOWS = {'ghl-mcp-supervised-guard.yml', 'qc-static.yml', 'version-consistency.yml'}
EXEMPT_WORKFLOWS = set()
NEEDLE = "!startsWith(github.head_ref, 'batch/')"


def triggers(d):
    on = d.get(True) or d.get('on') or {}
    return set(on) if isinstance(on, (dict, list)) else {on}


def check(docs):
    """docs: {basename: parsed yaml}. Returns a list of problems."""
    bad = []
    for name, d in sorted(docs.items()):
        jobs = d.get('jobs') or {}
        has = {j: NEEDLE in str(v.get('if', '')) for j, v in jobs.items()}
        if name in REQUIRED_WORKFLOWS:
            bad += [f'{name}:{j} is a required-check job and must NOT skip batch PRs' for j, h in has.items() if h]
        elif 'pull_request' in triggers(d) and name not in EXEMPT_WORKFLOWS:
            bad += [f'{name}:{j} lacks `if: ${{{{ {NEEDLE} }}}}` (batch PRs run only required checks)' for j, h in has.items() if not h]
    return bad


def load():
    return {os.path.basename(f): yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')}


def main():
    if '--self-test' in sys.argv:
        ok = {'a.yml': {True: {'pull_request': None}, 'jobs': {'j': {'if': '${{ %s }}' % NEEDLE}}}}
        assert not check(ok)
        assert check({'a.yml': {True: {'pull_request': None}, 'jobs': {'j': {}}}}), 'missing skip must fail'
        assert check({'qc-static.yml': {True: {'pull_request': None}, 'jobs': {'j': {'if': NEEDLE}}}}), 'required skip must fail'
        print('self-test OK')
        return 0
    bad = check(load())
    for b in bad:
        print('FAIL', b)
    print('batch-required-only: %s' % ('FAIL' if bad else 'OK'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
