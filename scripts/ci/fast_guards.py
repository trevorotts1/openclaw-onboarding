#!/usr/bin/env python3
"""Run the folded fast CI guards in one job (CIO002).

Each guard in fast-guards.json keeps the event/branch/paths filter its own
workflow used to have; the filter is applied here against the git diff, so a
guard runs exactly when its old workflow would have been triggered.
  --list [event]  print the guards selected for the file list on stdin
  (default)       detect the diff from the GitHub event env, run selected guards
Exit 1 if any selected guard fails. Prints "<guard>: PASS|FAIL|SKIP" per guard.
"""
import json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
# changing the fold itself re-runs every guard
RUN_ALL = re.compile(r'^(\.github/workflows/fast-guards\.yml|scripts/ci/(fast_guards\.py|fast-guards\.json|fast-guards\.d/.*))$')


def glob_re(p):
    out, i = '', 0
    while i < len(p):
        if p.startswith('**/', i): out += '(?:.*/)?'; i += 3
        elif p.startswith('**', i): out += '.*'; i += 2
        elif p[i] == '*': out += '[^/]*'; i += 1
        elif p[i] == '?': out += '[^/]'; i += 1
        else: out += re.escape(p[i]); i += 1
    return re.compile('^' + out + '$')


def branch_ok(patterns, name):
    return patterns is None or any(glob_re(p).match(name) for p in patterns)


def selected(g, event, base_ref, files):
    """True when guard g's old workflow would have fired for this event."""
    if event == 'workflow_dispatch' or files is None:
        return True
    ev = g['events'].get(event)
    if ev is None:
        return False
    if event == 'pull_request' and not branch_ok(ev['branches'], base_ref):
        return False
    if ev['paths'] is None:
        return True
    if any(RUN_ALL.match(f) for f in files):
        return True
    rx = [glob_re(p) for p in ev['paths']]
    return any(r.match(f) for f in files for r in rx)


def load():
    return json.load(open(os.path.join(HERE, 'fast-guards.json')))


def git_files(a, b, dots):
    r = subprocess.run(['git', 'diff', '--name-only', a + dots + b], capture_output=True, text=True)
    return [l for l in r.stdout.split('\n') if l] if r.returncode == 0 else None  # None = unknown, run all


def detect():
    ev = os.environ.get('GITHUB_EVENT_NAME', 'workflow_dispatch')
    if ev == 'pull_request':
        e = json.load(open(os.environ['GITHUB_EVENT_PATH']))['pull_request']
        return ev, os.environ.get('GITHUB_BASE_REF', ''), git_files(e['base']['sha'], e['head']['sha'], '...')
    if ev == 'push':
        before = json.load(open(os.environ['GITHUB_EVENT_PATH'])).get('before', '')
        if set(before) <= {'0'}:
            return ev, '', None
        return ev, '', git_files(before, os.environ['GITHUB_SHA'], '..')
    return ev, '', None


def main():
    guards = load()
    if '--list' in sys.argv:
        i = sys.argv.index('--list')
        ev = sys.argv[i + 1] if len(sys.argv) > i + 1 else 'pull_request'
        files = [l.strip() for l in sys.stdin if l.strip()]
        print('\n'.join(g['name'] for g in guards if selected(g, ev, 'main', files)))
        return 0
    ev, base, files = detect()
    ws = os.environ.get('GITHUB_WORKSPACE', os.getcwd())
    pyloc = os.environ.get('pythonLocation', '')
    path = os.environ['PATH']
    plain = ':'.join(p for p in path.split(':') if not (pyloc and p.startswith(pyloc)))
    results = []
    for g in guards:
        if not selected(g, ev, base, files):
            results.append((g['name'], 'SKIP')); print(f"{g['name']}: SKIP (paths/branch filter)", flush=True); continue
        print(f"::group::{g['name']}", flush=True)
        t = time.time()
        env = dict(os.environ, PATH=path if g['python311'] else plain)
        rc = subprocess.run(['bash', os.path.join(ws, g['script'])], env=env, cwd=ws).returncode
        subprocess.run('git checkout -q -- . && git clean -fdxq', shell=True, cwd=ws)  # isolate guards
        print('::endgroup::', flush=True)
        res = 'PASS' if rc == 0 else 'FAIL'
        results.append((g['name'], res))
        print(f"{g['name']}: {res} ({time.time() - t:.0f}s)" + ('' if rc == 0 else f"  ::error::{g['name']} failed (was workflow {g['was']})"), flush=True)
    print('\n=== fast-guards summary ===')
    for n, r in results:
        print(f'{r:5} {n}')
    bad = [n for n, r in results if r == 'FAIL']
    print(f"{sum(r == 'PASS' for _, r in results)} passed, {len(bad)} failed, {sum(r == 'SKIP' for _, r in results)} skipped")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
