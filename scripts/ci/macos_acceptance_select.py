#!/usr/bin/env python3
"""Decide which parts of the one macOS job (macos-acceptance.yml) a change needs.

Writes hardening=/bash32=/presentation= true|false to $GITHUB_OUTPUT. Each part's paths live in
scripts/ci/macos-acceptance-paths.json (pull_request and push lists, the same filters the three
old macOS jobs had; the presentation pull_request list is the narrowed one). A schedule or a
manual run runs every part. Fail-closed: if the changed files cannot be determined, every part runs.
"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fast_guards as fg

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = json.load(open(os.path.join(HERE, 'macos-acceptance-paths.json')))


def changed_files(event):
    if event == 'pull_request':
        a = os.environ.get('BASE_SHA', '')
    elif event == 'push':
        a = os.environ.get('BEFORE_SHA', '')
    else:
        return None
    if not a or set(a) <= {'0'}:
        return None
    if subprocess.run(['git', 'fetch', '--no-tags', '--depth=1', 'origin', a]).returncode:
        return None
    r = subprocess.run(['git', 'diff', '--name-only', a, 'HEAD'], capture_output=True, text=True)
    return [l for l in r.stdout.split('\n') if l] if r.returncode == 0 else None


def select(event, files):
    out = {}
    for part, lists in PARTS.items():
        pats = lists.get(event)
        if files is None or pats is None:
            out[part] = True
        else:
            rx = [fg.glob_re(p) for p in pats]
            out[part] = any(r.match(f) for f in files for r in rx)
    return out


def main():
    event = os.environ.get('GITHUB_EVENT_NAME', 'workflow_dispatch')
    sel = select(event, changed_files(event))
    for k, v in sel.items():
        print(f'{k}={"true" if v else "false"}')
    path = os.environ.get('GITHUB_OUTPUT')
    if path:
        with open(path, 'a') as fh:
            for k, v in sel.items():
                fh.write(f'{k}={"true" if v else "false"}\n')


if __name__ == '__main__':
    main()
