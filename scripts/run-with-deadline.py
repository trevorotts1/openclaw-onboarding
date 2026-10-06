#!/usr/bin/env python3
"""Bound an isolated process group; retain output only in private diagnostics."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', required=True)
    parser.add_argument('--diagnostics', type=Path, required=True)
    parser.add_argument('--label', choices=('skills-info', 'qc-script'), required=True)
    parser.add_argument('--stdout', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    # Misconfiguration fails closed, with a finite maximum even for overrides.
    try:
        seconds = int(args.seconds)
        if not 1 <= seconds <= 3600 or not command:
            raise ValueError()
    except ValueError:
        return 125
    args.diagnostics.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.diagnostics.is_symlink():
        return 125
    args.diagnostics.chmod(0o700)
    folder = Path(tempfile.mkdtemp(prefix=args.label + '-', dir=args.diagnostics))
    started = time.monotonic()
    status, rc, proc = 'launch-failed', 125, None
    with open(folder / 'stdout.log', 'xb') as out, open(folder / 'stderr.log', 'xb') as err:
        os.chmod(out.name, 0o600)
        os.chmod(err.name, 0o600)
        try:
            proc = subprocess.Popen(command, stdout=out, stderr=err, start_new_session=True)
            try:
                rc = proc.wait(timeout=seconds)
                status = 'passed' if rc == 0 else 'failed'
            except subprocess.TimeoutExpired:
                status, rc = 'timeout', 124
        except OSError:
            # Never print command arguments or inherited environment values.
            pass
        finally:
            if proc is not None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                if status == 'timeout':
                    time.sleep(0.2)
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    # macOS may report EPERM for an already-reaped group.
                    # Never treat a still-running child as successfully stopped.
                    if proc.poll() is None:
                        raise
                proc.wait()
    receipt = dict(status=status, exitCode=rc, deadlineSeconds=seconds,
                   elapsedSeconds=round(time.monotonic() - started, 3))
    receipt_path = folder / 'status.json'
    with open(receipt_path, 'x') as handle:
        os.chmod(receipt_path, 0o600)
        json.dump(receipt, handle)
    if args.stdout and status != 'timeout':
        sys.stdout.buffer.write((folder / 'stdout.log').read_bytes())
        sys.stderr.buffer.write((folder / 'stderr.log').read_bytes())
    return rc if rc >= 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
