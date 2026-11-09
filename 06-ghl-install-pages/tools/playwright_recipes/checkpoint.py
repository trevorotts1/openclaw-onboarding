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


# Exact repository integration sources only. Never include a directory tree,
# client store, browser state, transcript, workforce file or arbitrary profile.
INTEGRATION_SOURCES = (
    '06-ghl-install-pages/tools/ghl_auth.py',
    '06-ghl-install-pages/tools/ghl_auth_activation.py',
    '06-ghl-install-pages/references/PLAYWRIGHT-AUTH-ACTIVATION.md',
    '44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py',
    '44-convert-and-flow-operator/tools/engine/tests/test_capability_breadth.py',
    '44-convert-and-flow-operator/tools/engine/tests/test_build_from_automation.py',
    '.github/workflows/skill6-recipes-portability.yml',
    '06-ghl-install-pages/SKILL.md', '06-ghl-install-pages/README.md',
    '06-ghl-install-pages/skill-version.txt', '06-ghl-install-pages/CHANGELOG.md',
    '44-convert-and-flow-operator/SKILL.md',
    '44-convert-and-flow-operator/skill-version.txt',
    '44-convert-and-flow-operator/CHANGELOG.md',
)
REPOSITORY_DEPENDENCIES = (
    '06-ghl-install-pages/tools/browser_manager.py',
    '06-ghl-install-pages/tools/ghl_auth.py',
    '06-ghl-install-pages/tools/ghl_auth_activation.py',
    '06-ghl-install-pages/tools/order_components.py',
    '44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/adapter.py',
    '44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/transport.py',
    '44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/capability.py',
    '44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/ghl_client.py',
)


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
        'PLAYWRIGHT-RECIPES.md', 'PLAYWRIGHT-PROGRESS.md', 'PLAYWRIGHT-REQUIREMENTS.md',
        'PLAYWRIGHT-COMPLETION-MATRIX.md')]
    integrations = {'included': [], 'missing': []}
    for relative in INTEGRATION_SOURCES:
        source = repo / relative
        if source.is_symlink():
            raise ValueError('Checkpoint integration source is a symlink: ' + relative)
        if source.is_file():
            files.append(source)
            integrations['included'].append(relative)
        else:
            integrations['missing'].append(relative)
    dependencies = {
        'requires_existing_repository': True,
        'standalone_installation': False,
        'required_existing_sources': list(REPOSITORY_DEPENDENCIES),
        'bundled_required_sources': [relative for relative in REPOSITORY_DEPENDENCIES if relative in integrations['included']],
        'unbundled_required_sources': [relative for relative in REPOSITORY_DEPENDENCIES if relative not in integrations['included']],
        'present_in_source_tree': [relative for relative in REPOSITORY_DEPENDENCIES if (repo / relative).is_file()],
        'missing_from_source_tree': [relative for relative in REPOSITORY_DEPENDENCIES if not (repo / relative).is_file()],
        'meaning': 'Allowlisted bundled dependencies are identified separately; restore the remaining dependencies from the existing Skill 6/44 repository and run its runtime preflight.',
    }
    contents = {}
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise ValueError('Checkpoint source missing or symlink: ' + path.name)
        contents[str(path.relative_to(repo))] = path.read_bytes()
    try:
        commit = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        base_commit = commit.stdout.strip() if commit.returncode == 0 else None
    except FileNotFoundError:
        # A downloaded/installed skill can be backed up without a Git install.
        base_commit = None
    manifest = {'schema': 'skill6-source-checkpoint/1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'base_commit': base_commit,
        'meaning': 'Exact recipe and allowlisted integration source snapshot, not a standalone installation or live-readiness proof; see PLAYWRIGHT-PROGRESS.md.',
        'integration_sources': integrations,
        'repository_dependencies': dependencies,
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
