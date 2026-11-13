#!/usr/bin/env python3
"""CIO002 proof: for sample PR diffs, the guards that run AFTER the fold are
identical to the guards that ran BEFORE; every workflow parses; jobs per PR
commit before vs after.

  python3 scripts/ci/test_fast_guards_mapping.py [--base <git ref of the pre-fold tree>] [--commits N]

Default base is the merge-base of HEAD and origin/main (the pre-fold tree while
this change is in review). Exit 1 on any mismatch or parse error.

Only the guards folded BY THIS CHANGE are compared (their `was` workflow exists in the base
tree); guards folded by earlier changes have no base workflow left and are skipped. The
workflows changed on purpose by the checks-compress change are listed below.
"""
import argparse, glob, os, subprocess, sys, yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fast_guards as fg

ROOT = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()
os.chdir(ROOT)


def sh(*a):
    return subprocess.check_output(a, text=True)


# Pre-existing: the workflow had no concurrency block before this change and is kept as is (a two-OS matrix).
KNOWN_NO_CONCURRENCY = {'skill6-recipes-portability'}
# Workflow files that keep one or more jobs after a partial fold (the rest of the file stays).
PARTIAL_KEEP = {'embedding-integrity-guard.yml', 'prebuilt-index-section-tagged-guard.yml',
                'version-consistency.yml', 'presentation-release-matrix.yml'}
# Guards whose path filter was widened on purpose when folded (plan step 2.2).
INTENDED_PATH_CHANGES = {'unwired-checks-guard'}
# Workflows whose pull_request/push triggers were changed on purpose (plan steps 1 and 6, and the
# prebuilt-index file whose only job left is release/manual).
INTENDED_TRIGGER_CHANGES = {'launch-family-parity', 'claim-provenance-advisory',
                            'presentation-release-matrix', 'prebuilt-index-section-tagged-guard'}
# New workflows with no base counterpart: council, skill44 and macos-acceptance are checked by the 'new workflow' branch.


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
    a = ap.parse_args()
    base = a.base or sh('git', 'merge-base', 'HEAD', 'origin/main').strip()
    before = load_tree(base)
    after = {os.path.basename(f)[:-4]: yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')}  # parse check
    guards = [g for g in fg.load() if g['was'][:-4] in before]  # folded by this change
    folded = {g['was'][:-4] for g in guards}
    bad = 0

    # glob semantics sanity
    for p, f, want in [('a/*.sh', 'a/x.sh', 1), ('a/*.sh', 'a/b/x.sh', 0), ('a/**', 'a/b/x.sh', 1),
                       ('**/x.py', 'x.py', 1), ('**/x.py', 'a/b/x.py', 1), ('a/b?.md', 'a/bc.md', 1), ('a/b?.md', 'a/b/.md', 0)]:
        assert bool(fg.glob_re(p).match(f)) == bool(want), (p, f)

    # structural: every folded guard has its script, bash-parses, and was a real pre-fold workflow
    for g in guards:
        if g['was'] in PARTIAL_KEEP:
            if g['was'][:-4] not in after: print('FAIL partial-fold workflow was removed:', g['was']); bad += 1
        elif g['was'][:-4] in after: print('FAIL still present as workflow:', g['was']); bad += 1
        if subprocess.run(['bash', '-n', g['script']]).returncode: print('FAIL bash -n', g['script']); bad += 1
    # triggers of folded guards equal the base workflows' (branches/paths), push forced to main-only
    for g in guards:
        t = triggers(before[g['was'][:-4]])
        for e in ('push', 'pull_request'):
            if (e in t) != (e in g['events']): print('FAIL event set differs', g['name'], e); bad += 1; continue
            if e in t:
                if g['was'][:-4] not in INTENDED_PATH_CHANGES and t[e].get('paths') != g['events'][e]['paths']: print('FAIL paths differ', g['name'], e); bad += 1
                if t[e].get('branches') != g['events'][e]['branches']: print('FAIL branches differ', g['name'], e); bad += 1
    # every unfolded workflow: same pull_request trigger as before; push is main-only or unchanged
    for n, d in after.items():
        if n == 'fast-guards': continue
        if n not in before:
            print('new workflow (intended):', n)
            if 'concurrency' not in d: print('FAIL no concurrency', n); bad += 1
            continue
        if n in INTENDED_TRIGGER_CHANGES:
            print('trigger change (intended):', n); continue
        tb, ta = triggers(before[n]), triggers(d)
        if tb.get('pull_request') != ta.get('pull_request'): print('FAIL pull_request trigger changed', n); bad += 1
        pb, pa = tb.get('push'), ta.get('push')
        if pb is not None and 'branches' not in pb and 'tags' not in pb:
            if pa.get('branches') != ['main'] or pa.get('paths') != pb.get('paths'): print('FAIL push not main-only', n); bad += 1
        elif pb != pa: print('FAIL push changed unexpectedly', n); bad += 1
        if 'concurrency' not in d and n not in KNOWN_NO_CONCURRENCY: print('FAIL no concurrency', n); bad += 1

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
    for label, files in samples:
        for ev in ('pull_request', 'push'):
            skip = folded & INTENDED_PATH_CHANGES
            b = {n for n in folded - skip if fires(before[n], ev, 'main', files)}
            af = {g['was'][:-4] for g in guards if g['was'][:-4] not in skip and fg.selected(g, ev, 'main', files)}
            # push on a non-main (PR) branch: before = all unfiltered push workflows, after = none
            if ev == 'push':
                aa = {n for n, d in after.items() if n != 'fast-guards' and n in before and n not in INTENDED_TRIGGER_CHANGES
                      and fires(d, 'push', 'feature-branch', files) and not fires(before[n], 'push', 'feature-branch', files)}
                if aa: print('FAIL after-fold push on feature branch fires where it did not', label, sorted(aa)); bad += 1
            if b != af:
                print(f'FAIL {label} {ev}: before-only={sorted(b - af)} after-only={sorted(af - b)}'); bad += 1
        print(f'ok  {label:22} files={len(files):3}  folded workflows fired (PR)={len({n for n in folded if fires(before[n], "pull_request", "main", files)})}')
    n = len(samples)
    print(f'\nsamples={n}')
    print('workflow files before=%d after=%d (%d guards folded from %d workflows)' % (len(before), len(after), len(guards), len(folded)))
    print('RESULT:', 'FAIL (%d)' % bad if bad else 'PASS - identical guard set before vs after for every sample')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
