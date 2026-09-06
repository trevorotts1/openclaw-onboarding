#!/usr/bin/env python3
"""Register native Linux PM2 reboot restoration; no live service restart.

Exit 3 means persistence is pending, never proven. Mac/container boot policy is
owned externally. Unit data is escaped for systemd, never interpreted by a shell.
"""
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import shlex
import subprocess
import tempfile
import sys

MARKER = '# OpenClaw managed PM2 boot v1'


class Pending(RuntimeError):
    pass


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=45, **kwargs)
    if result.returncode:
        raise Pending('Command failed: ' + Path(args[0]).name + ' ' + args[1])
    return result.stdout.strip()


def quoted(value, command=False):
    if any(c in value for c in '\n\r\x00'):
        raise Pending('Service paths/environment contain unsupported control characters')
    value = value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    if command:
        value = value.replace('$', '$$')
    return '"' + value + '"'


def container():
    if Path('/.dockerenv').exists() or Path('/run/.containerenv').exists():
        return True
    path = Path('/proc/1/cgroup')
    return path.exists() and bool(re.search(r'(docker|kubepods|libpod)', path.read_text()))


def compatible_existing(systemctl, unit_name, user, home, pm2_home, pm2, node):
    """Prove an external PM2 unit matches this daemon without rewriting it."""
    def field(name):
        return run([systemctl, 'show', '--property=' + name, '--value', unit_name])
    if field('User') != user or field('PIDFile') != str(Path(pm2_home) / 'pm2.pid'):
        return False
    # Loaded Environment does not include EnvironmentFile values or later
    # UnsetEnvironment removals. Unknown overlays cannot prove daemon ownership.
    if any(field(name) for name in ('EnvironmentFiles', 'UnsetEnvironment', 'RootDirectory', 'RootImage')):
        return False
    try:
        values = dict(item.split('=', 1) for item in shlex.split(field('Environment')))
    except ValueError:
        return False
    # Official PM2 units commonly omit HOME; systemd then uses the account home.
    account_home = pwd.getpwnam(user).pw_dir
    if values.get('HOME', account_home) != home or values.get('PM2_HOME') != pm2_home:
        return False
    if str(Path(node).parent) not in values.get('PATH', '').split(':'):
        return False
    # systemctl serializes ExecStart as a single command struct. If quoting or
    # multiple command records prevent an exact proof, leave it pending.
    command = field('ExecStart')
    match = re.fullmatch(r'\{ path=(.*?) ; argv\[\]=(.*?) ; [^{}]*\}', command)
    if not match or str(Path(match[1]).resolve()) != pm2:
        return False
    try:
        argv = shlex.split(match[2])
    except ValueError:
        return False
    return len(argv) == 2 and str(Path(argv[0]).resolve()) == pm2 and argv[1] == 'resurrect'


def ensure(unit_dir=Path('/etc/systemd/system')):
    if platform.system() != 'Linux':
        return {'status': 'external-policy', 'runtime': 'mac'}
    if container():
        return {'status': 'external-policy', 'runtime': 'container'}
    systemctl = shutil.which('systemctl')
    if not systemctl or run(['ps', '-p', '1', '-o', 'comm=']) != 'systemd':
        raise Pending('Native Linux init is not systemd; configure and verify its PM2 startup policy')
    uid = os.geteuid()
    user = pwd.getpwuid(uid).pw_name
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*\$?', user):
        raise Pending('Runtime username is not safe for a systemd unit name')
    home = os.environ.get('HOME', '')
    pm2_home = os.environ.get('PM2_HOME', str(Path(home) / '.pm2'))
    if not home.startswith('/') or not pm2_home.startswith('/'):
        raise Pending('HOME and PM2_HOME must be absolute runtime-user paths')
    pm2 = shutil.which('pm2')
    node = shutil.which('node')
    install = shutil.which('install')
    if not all((pm2, node, install)):
        raise Pending('PM2, Node and install must be available in the selected runtime PATH')
    pm2, node = str(Path(pm2).resolve()), str(Path(node).resolve())
    service_path = ':'.join(dict.fromkeys([str(Path(node).parent), str(Path(pm2).parent)] + os.environ.get('PATH', '').split(':')))
    env = dict(os.environ, HOME=home, PM2_HOME=pm2_home, PATH=service_path)
    prefix = []
    if uid != 0:
        sudo = shutil.which('sudo')
        if not sudo:
            raise Pending('PM2 boot registration requires root or passwordless sudo for the runtime user')
        prefix = [sudo, '-n']
        run(prefix + ['true'])
    unit = unit_dir / ('pm2-' + user + '.service')
    fragment = run([systemctl, 'show', '--property=FragmentPath', '--value', unit.name])
    external = unit.is_symlink() or (fragment and Path(fragment) != unit)
    # Never replace an operator's startup policy or switch its PM2 daemon root.
    if unit.exists():
        old = unit.read_text()
        if MARKER not in old or ('Environment=' + quoted('PM2_HOME=' + pm2_home)) not in old:
            external = True
    if external:
        if not compatible_existing(systemctl, unit.name, user, home, pm2_home, pm2, node):
            raise Pending('Existing PM2 startup unit does not prove the selected user, PM2_HOME, Node PATH and resurrect command; verify it explicitly')
        run([pm2, 'save'], env=env)
        run(prefix + [systemctl, 'enable', unit.name])
        if run([systemctl, 'is-enabled', unit.name]) != 'enabled':
            raise Pending('Existing PM2 startup unit was not verified enabled')
        return {'status': 'enabled', 'runtime': 'native-linux', 'unit': unit.name,
                'user': user, 'pm2Home': pm2_home, 'preservedExisting': True}
    content = MARKER + '\n[Unit]\nDescription=OpenClaw PM2 process restoration\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=forking\n'
    content += 'User=' + user + '\n'
    for key in ('HOME', 'PM2_HOME', 'PATH'):
        content += 'Environment=' + quoted(key + '=' + env[key]) + '\n'
    # PIDFile is a scalar path, not an Exec/Environment token: systemd retains
    # surrounding quotes literally. Only escape its percent specifiers.
    pid_file = str(Path(pm2_home) / 'pm2.pid')
    content += 'PIDFile=' + pid_file.replace('%', '%%') + '\n'
    content += 'ExecStart=' + quoted(pm2, True) + ' resurrect\n'
    content += 'ExecReload=' + quoted(pm2, True) + ' reload all\n'
    content += 'ExecStop=' + quoted(pm2, True) + ' kill\n'
    content += 'Restart=on-failure\n\n[Install]\nWantedBy=multi-user.target\n'
    # Save under the actual selected user before privileged unit installation.
    # PM2's dump retains application environment as raw data, not shell source.
    run([pm2, 'save'], env=env)
    with tempfile.TemporaryDirectory(prefix='openclaw-pm2-boot-') as tmp:
        source = Path(tmp) / unit.name
        source.write_text(content)
        run(prefix + [install, '-m', '0644', str(source), str(unit)])
    run(prefix + [systemctl, 'daemon-reload'])
    if run([systemctl, 'show', '--property=PIDFile', '--value', unit.name]) != pid_file:
        raise Pending('Loaded PM2 startup PIDFile does not match the selected PM2_HOME')
    if not compatible_existing(systemctl, unit.name, user, home, pm2_home, pm2, node):
        raise Pending('Loaded PM2 startup unit does not match the selected runtime; check systemd overrides')
    run(prefix + [systemctl, 'enable', unit.name])
    if run([systemctl, 'is-enabled', unit.name]) != 'enabled':
        raise Pending('PM2 startup unit was not verified enabled')
    return {'status': 'enabled', 'runtime': 'native-linux', 'unit': unit.name, 'user': user, 'pm2Home': pm2_home}


if __name__ == '__main__':
    try:
        result = ensure()
        if '--require-native' in sys.argv and result['status'] != 'enabled':
            raise Pending('Runtime topology changed; native systemd registration was not verified')
        print(json.dumps(result))
    except (Pending, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'pending', 'reason': str(exc)}))
        raise SystemExit(3)
