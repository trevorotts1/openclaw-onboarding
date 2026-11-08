#!/usr/bin/env python3
"""Export the maintained recipe sources and handoff, never client credentials."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone


def snapshot(destination=None):
    package = Path(__file__).resolve().parent
    skill = package.parent.parent
    repo = skill.parent
    destination = Path(destination or Path.home() / 'Downloads' / 'BlackCEO-Skill6').expanduser()
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Explicit source set: do not walk evidence, profiles, auth files or browser state.
    files = sorted(package.glob('*.py')) + [package / 'catalog.json']
    files += sorted((package / 'examples').glob('*'))
    files += [skill / 'references' / name for name in (
        'PLAYWRIGHT-RECIPES.md', 'PLAYWRIGHT-PROGRESS.md', 'PLAYWRIGHT-REQUIREMENTS.md')]
    contents = {}
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise ValueError('Checkpoint source missing or symlink: ' + path.name)
        contents[str(path.relative_to(repo))] = path.read_bytes()
    commit = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    manifest = {'schema': 'skill6-source-checkpoint/1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'base_commit': commit.stdout.strip() if commit.returncode == 0 else None,
        'meaning': 'Exact source snapshot. No live readiness claim; see PLAYWRIGHT-PROGRESS.md.',
        'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = destination / ('skill6-checkpoint-' + stamp + '.tar.gz')
    fd, temp = tempfile.mkstemp(prefix='.checkpoint-', dir=destination)
    try:
        with os.fdopen(fd, 'wb') as stream:
            with tarfile.open(fileobj=stream, mode='w:gz') as archive:
                contents['MANIFEST.json'] = json.dumps(manifest, indent=2).encode()
                for name, data in contents.items():
                    info = tarfile.TarInfo(name)
                    info.size, info.mode = len(data), 0o600
                    archive.addfile(info, io.BytesIO(data))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, output)
    finally:
        Path(temp).unlink(missing_ok=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    print(snapshot(args.destination))
