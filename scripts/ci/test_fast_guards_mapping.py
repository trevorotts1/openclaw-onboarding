#!/usr/bin/env python3
"""CIO002 proof: for sample PR diffs, the guards that run AFTER the fold are
identical to the guards that ran BEFORE; every workflow parses; jobs per PR
commit before vs after.

  python3 scripts/ci/test_fast_guards_mapping.py [--base <git ref of the pre-fold tree>] [--commits N]

Default base is PRE_FOLD_REF, the commit the fold (95593fd51) replaced, so the
proof keeps its original meaning on every later tree. Two things have moved on
since the fold and are handled explicitly instead of failing the whole run:

  * a guard added AFTER the fold has no pre-fold workflow to compare with; its
    script and `bash -n` are still checked, which is all a new guard can claim;
  * a workflow that exists in the tree but not in the base tree was added after
    the fold; there is no before-state to compare, so it is not compared.

A guard whose pre-fold workflow still exists is reported as a duplicate finding
(one check running twice per commit) and does not fail the proof: that state is
deliberate on main (commit 14d888f0a, "duplicates are findings only"), where the
workflow keeps the pull_request trigger the fold does not carry.

Exit 1 on any mismatch or parse error.
"""
import argparse, glob, os, subprocess, sys, yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fast_guards as fg

# The commit the CIO002 fold (95593fd51) replaced. Pinned, never a merge-base:
# after the fold lands, HEAD is the folded tree and a merge-base comparison has
# nothing left to compare.
PRE_FOLD_REF = "95593fd51^"

ROOT = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()
os.chdir(ROOT)


def sh(*a):
    return subprocess.check_output(a, text=True)


def triggers(d):
    on = d.get(True, d.get('on'))
    if isinstance(on, str): return {on: {}}
    if isinstance(on, list): return {k: {} for k in on}
    return {k: (v or {}) for k, v in on.items()}


def fires(d, event, base_ref, files):
    """Would workflow doc d fire on `event` (pull_request|push) for this diff?"""
    t = triggers(d)
    if event not in t: return False
    c = t[event]
    assert 'paths-ignore' not in c and 'branches-ignore' not in c, 'unsupported filter'
    if event == 'pull_request':
        if 'branches' in c and not fg.branch_ok(c['branches'], base_ref): return False
    if event == 'push':
        if 'tags' in c and 'branches' not in c: return False  # tag-only push never fires for a branch push
        if 'branches' in c and not fg.branch_ok(c['branches'], base_ref): return False
    if 'paths' in c:
        rx = [fg.glob_re(p) for p in c['paths']]
        return any(r.match(f) for f in files for r in rx)
    return True


def load_tree(ref):
    docs = {}
    names = sh('git', 'ls-tree', '--name-only', ref, '.github/workflows/').split()
    for n in names:
        if n.endswith('.yml'):
            docs[os.path.basename(n)[:-4]] = yaml.safe_load(sh('git', 'show', f'{ref}:{n}'))
    return docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=None)
    ap.add_argument('--commits', type=int, default=40)
    ap.add_argument('--proof', action='store_true',
                    help='run the full before/after identity proof against --base '
                         '(a point-in-time proof; the default run is the standing gate)')
    a = ap.parse_args()
    base = a.base or PRE_FOLD_REF
    after = {os.path.basename(f)[:-4]: yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')}  # parse check
    guards = fg.load()
    folded = {g['name'] for g in guards}
    bad = 0

    # glob semantics sanity
    for p, f, want in [('a/*.sh', 'a/x.sh', 1), ('a/*.sh', 'a/b/x.sh', 0), ('a/**', 'a/b/x.sh', 1),
                       ('**/x.py', 'x.py', 1), ('**/x.py', 'a/b/x.py', 1), ('a/b?.md', 'a/bc.md', 1), ('a/b?.md', 'a/b/.md', 0)]:
        assert bool(fg.glob_re(p).match(f)) == bool(want), (p, f)

    # standing gate: every folded guard names a script that exists and bash-parses,
    # and every workflow file parses (the dict above raises otherwise). A guard whose
    # own workflow still exists runs its check twice per commit: a finding, not a
    # failure, because that is deliberate on main (commit 14d888f0a).
    for g in guards:
        if not os.path.isfile(g['script']):
            print('FAIL guard script missing:', g['script']); bad += 1
            continue
        if subprocess.run(['bash', '-n', g['script']]).returncode:
            print('FAIL bash -n', g['script']); bad += 1
        if g['name'] in after:
            print('note duplicate finding (the guard also exists as a workflow):', g['name'])
    if not a.proof:
        print(f'workflows={len(after)} folded guards={len(guards)}')
        print('RESULT:', 'FAIL (%d)' % bad if bad else 'PASS - every guard script exists and parses')
        return 1 if bad else 0

    before = load_tree(base)
    # structural, against the pre-fold tree: a folded guard with no pre-fold workflow
    # was added after the fold and has no before-state to compare with.
    for g in guards:
        if g['name'] not in before:
            print('note new guard added after the fold (no pre-fold workflow):', g['name'])
            continue
        # triggers of folded guards equal the base workflows' (branches/paths), push forced to main-only
        t = triggers(before[g['name']])
        for e in ('push', 'pull_request'):
            if (e in t) != (e in g['events']): print('FAIL event set differs', g['name'], e); bad += 1; continue
            if e in t:
                if t[e].get('paths') != g['events'][e]['paths']: print('FAIL paths differ', g['name'], e); bad += 1
                if t[e].get('branches') != g['events'][e]['branches']: print('FAIL branches differ', g['name'], e); bad += 1
    # every unfolded workflow that existed before the fold: same pull_request trigger as before;
    # push is main-only or unchanged. One added after the fold has no before-state to compare.
    for n, d in after.items():
        if n == 'fast-guards' or n not in before:
            continue
        tb, ta = triggers(before[n]), triggers(d)
        if tb.get('pull_request') != ta.get('pull_request'): print('FAIL pull_request trigger changed', n); bad += 1
        pb, pa = tb.get('push'), ta.get('push')
        if pb is not None and 'branches' not in pb and 'tags' not in pb:
            if pa.get('branches') != ['main'] or pa.get('paths') != pb.get('paths'): print('FAIL push not main-only', n); bad += 1
        elif pb != pa: print('FAIL push changed unexpectedly', n); bad += 1
        if 'concurrency' not in d: print('FAIL no concurrency', n); bad += 1

    # sample diffs: recent commits on origin/main plus synthetic file lists
    samples = []
    for c in sh('git', 'log', '--format=%H', f'-{a.commits}', 'origin/main').split():
        fl = [l for l in sh('git', 'diff', '--name-only', f'{c}^', c).split('\n') if l]
        if fl: samples.append((c[:8], fl))
    samples += [('syn:docs-only', ['README.md']), ('syn:version', ['version', 'CHANGELOG.md']),
                ('syn:update-skills', ['update-skills.sh', 'scripts/update-' + 'skills.sh']),
                ('syn:workflow-file', ['.github/workflows/model-selector-guard.yml']),
                ('syn:nothing-matches', ['zzz/unmatched.txt']),
                ('syn:persona', ['22-book-to-persona-coaching-leadership-system/SKILL.md', 'scripts/foo.sh'])]
    tot_b = tot_a = 0
    # The identity claim covers the checks that existed when the fold landed and
    # still exist now: a guard added afterwards was never a separate workflow, and
    # a workflow archived since (e.g. *.yml.ARCHIVED-*) has no after-state to be
    # identical to. Both are outside what this proof claims.
    surviving = (set(before) & (set(after) | folded)) | {g['name'] for g in guards if g['name'] in before}
    for label, files in samples:
        for ev in ('pull_request', 'push'):
            b = {n for n, d in before.items() if n in surviving and fires(d, ev, 'main', files)}
            af = {n for n, d in after.items() if n != 'fast-guards' and n in surviving and fires(d, ev, 'main', files)}
            af |= {g['name'] for g in guards if g['name'] in surviving and fg.selected(g, ev, 'main', files)}
            # push on a non-main (PR) branch: before = all unfiltered push workflows, after = none
            if ev == 'push':
                bb = {n for n, d in before.items() if fires(d, 'push', 'feature-branch', files)}
                aa = {n for n, d in after.items() if n != 'fast-guards' and fires(d, 'push', 'feature-branch', files)}
                if aa: print('FAIL after-fold push on feature branch still fires', label, sorted(aa)); bad += 1
                if label == samples[0][0]: pass
                tot_b += sum(len(before[n]['jobs']) for n in bb)
            if b != af:
                print(f'FAIL {label} {ev}: before-only={sorted(b - af)} after-only={sorted(af - b)}'); bad += 1
            if ev == 'pull_request':
                tot_b += sum(len(before[n]['jobs']) for n in b)
                tot_a += sum(len(after[n]['jobs']) for n in af if n in after) + (1 if af & folded else 1)  # fast-guards job always boots
        print(f'ok  {label:22} files={len(files):3}  guards-run(PR)={len({n for n, d in before.items() if fires(d, "pull_request", "main", files)})}')
    n = len(samples)
    print(f'\nsamples={n}  avg jobs per PR commit (PR+push-dup): before={tot_b / n:.1f}  after={tot_a / n:.1f}')
    print('workflow files before=%d after=%d (%d folded into 1)' % (len(before), len(after), len(guards)))
    print('RESULT:', 'FAIL (%d)' % bad if bad else 'PASS - identical guard set before vs after for every sample')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
