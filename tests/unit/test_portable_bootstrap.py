#!/usr/bin/env python3
"""Hermetic OS/container/path tests; no real Docker, services or package installs."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
COMMON = REPO / 'platform/common.sh'


class PortableBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(('OPENCLAW_', 'OC_', 'BASH_FUNC_')) and k not in ('BASH_ENV', 'ENV')}
        self.env.update(HOME=str(self.home), PATH=str(self.bin) + ':/usr/bin:/bin',
                        FIXTURE_OS='Linux', FIXTURE_CONTAINER='0', FIXTURE_DOCKER_NAMES='',
                        FIXTURE_DOCKER_ALL='', FIXTURE_DOCKER_USER='node',
                        FIXTURE_DOCKER_CALLS=str(self.root / 'docker-calls'))
        self.stub('uname', 'printf "%s\\n" "$FIXTURE_OS"')
        self.stub('df', "printf 'Filesystem Blocks Used Available Capacity Mounted\\nfixture 99999999 0 99999999 0%% /\\n'")
        self.stub('brew', 'exit 0')
        self.stub('curl', 'if [ -n "${FIXTURE_CURL_SCRIPT:-}" ]; then cat "$FIXTURE_CURL_SCRIPT"; else echo "Unexpected network access" >&2; exit 97; fi')
        # inspect/ps are isolated inventory; exec only records argv + forwarded env.
        self.stub('docker', '''
case "$1" in
  ps) if [ "${2:-}" = -a ]; then printf '%s\\n' "$FIXTURE_DOCKER_ALL"; else printf '%s\\n' "$FIXTURE_DOCKER_NAMES"; fi ;;
  inspect) printf '%s\\n' "$FIXTURE_DOCKER_USER" ;;
  exec) python3 - "$@" <<'PY'
import json, os, subprocess, sys
json.dump({'argv':sys.argv[1:], 'owner':os.environ.get('OPENCLAW_OWNER_NAME'),
           'company':os.environ.get('OPENCLAW_COMPANY_NAME'),
           'root':os.environ.get('OPENCLAW_ROOT'),
           'workspace':os.environ.get('OPENCLAW_WORKSPACE_PATH')},
          open(os.environ['FIXTURE_DOCKER_CALLS'],'w'))
if os.environ.get('FIXTURE_DOCKER_RUN') == '1':
    args = sys.argv[1:]
    raise SystemExit(subprocess.run(args[args.index('bash'):]).returncode)
PY
  ;;
  *) exit 97 ;;
esac''')

    def stub(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def run_shell(self, body, **env):
        values = dict(self.env, **env)
        script = ('set -e\nsource ' + shlex.quote(str(COMMON)) + '\n'
                  'oc_container_marked() { [[ "$FIXTURE_CONTAINER" == 1 ]]; }\n'
                  # Suppress Mac-only power-policy discovery by pointing at an
                  # empty fixture tree, never the repository's actual live helper.
                  '_SCRIPT_DIR=' + shlex.quote(str(self.root)) + '\n' + body)
        return subprocess.run(['/bin/bash', '-c', script], env=values, capture_output=True, text=True, timeout=15)

    def fields(self):
        return 'printf "RESULT:%s|%s|%s|%s\\n" "$OC_PLATFORM" "$OPENCLAW_RUNTIME_TOPOLOGY" "$OC_CONFIG" "$OC_WORKSPACE_DEFAULT"'

    def test_native_linux_is_vps_without_data_or_hostinger(self):
        result = self.run_shell('oc_set_platform_paths\n' + self.fields())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RESULT:vps|native|' + str(self.home / '.openclaw'), result.stdout)

    def test_mac_is_selected_by_os(self):
        result = self.run_shell('oc_set_platform_paths\n' + self.fields(), FIXTURE_OS='Darwin')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RESULT:mac|native|', result.stdout)

    def test_os_mismatch_fails_before_directory_creation(self):
        result = self.run_shell('oc_set_platform_paths', OPENCLAW_PLATFORM='mac')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / '.openclaw').exists())

    def test_custom_root_and_workspace_survive_native_vps_bootstrap(self):
        own = self.root / "Nicole's Company"
        workspace = own / 'custom workspace'
        result = self.run_shell('source ' + shlex.quote(str(REPO / 'platform/vps/bootstrap.sh')) + '\n' + self.fields(),
                                OPENCLAW_ROOT=str(own), OPENCLAW_WORKSPACE_PATH=str(workspace),
                                FIXTURE_DOCKER_NAMES='unrelated-openclaw')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(own) + '|' + str(workspace), result.stdout)
        self.assertFalse((self.root / 'docker-calls').exists())

    def test_saved_native_workspace_is_preserved(self):
        own = self.home / '.openclaw'
        own.mkdir()
        workspace = self.root / 'saved workspace'
        (own / 'openclaw.json').write_text(json.dumps({'agents': {'defaults': {'workspace': str(workspace)}}}))
        result = self.run_shell('oc_set_platform_paths\n' + self.fields())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('|' + str(workspace), result.stdout)

    def test_partial_native_root_never_switches_to_unrelated_container(self):
        own = self.home / '.openclaw'
        own.mkdir()
        (own / 'onboarding-identity.json').write_text('{"companyName":"Saved client"}')
        result = self.run_shell('source ' + shlex.quote(str(REPO / 'platform/vps/bootstrap.sh')) + '\n' + self.fields(),
                                FIXTURE_DOCKER_NAMES='openclaw-other')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(own), result.stdout)
        self.assertFalse((self.root / 'docker-calls').exists())

    def test_conflicting_workspace_pins_refuse(self):
        result = self.run_shell('oc_set_platform_paths', OPENCLAW_WORKSPACE_PATH='/one', OPENCLAW_WORKSPACE_ROOT='/two')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('conflict', result.stderr)

    def test_container_runtime_never_reexecs_into_docker(self):
        own = self.root / 'mounted-client-root'
        result = self.run_shell('source ' + shlex.quote(str(REPO / 'platform/vps/bootstrap.sh')) + '\n' + self.fields(),
                                FIXTURE_CONTAINER='1', OPENCLAW_ROOT=str(own), FIXTURE_DOCKER_NAMES='openclaw-sidecar')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('RESULT:vps|container|', result.stdout)
        self.assertFalse((self.root / 'docker-calls').exists())

    def test_docker_host_reexec_preserves_identity_and_path_pins(self):
        result = self.run_shell('source ' + shlex.quote(str(REPO / 'platform/vps/bootstrap.sh')),
                                OPENCLAW_CONTAINER_NAME='client-runtime', FIXTURE_DOCKER_NAMES='client-runtime',
                                OPENCLAW_OWNER_NAME="Nicole O'Brien", OPENCLAW_COMPANY_NAME="Nicole's",
                                OPENCLAW_ROOT='/srv/client root', OPENCLAW_WORKSPACE_PATH='/srv/client workspace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        captured = json.loads((self.root / 'docker-calls').read_text())
        self.assertEqual(captured['company'], "Nicole's")
        self.assertEqual(captured['owner'], "Nicole O'Brien")
        self.assertEqual(captured['root'], '/srv/client root')
        self.assertEqual(captured['workspace'], '/srv/client workspace')
        for key in ('OPENCLAW_COMPANY_NAME', 'OPENCLAW_OWNER_NAME', 'OPENCLAW_ROOT', 'OPENCLAW_WORKSPACE_PATH'):
            self.assertIn(key, captured['argv'])
        self.assertIn('OPENCLAW_NO_CONTAINER_REEXEC=1', captured['argv'])

    def test_empty_docker_user_means_root_not_hostinger_node(self):
        result = self.run_shell('source ' + shlex.quote(str(REPO / 'platform/vps/bootstrap.sh')),
                                FIXTURE_DOCKER_NAMES='openclaw-client', FIXTURE_DOCKER_USER='')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        args = json.loads((self.root / 'docker-calls').read_text())['argv']
        self.assertEqual(args[args.index('-u') + 1], 'root')

    def test_docker_update_uses_updater_and_forwards_literal_argv(self):
        child = self.root / 'child-script'
        child.write_text('''python3 - "$@" <<'PY'
import json, os, sys
json.dump({'args':sys.argv[1:], 'mode':os.environ.get('OPENCLAW_BOOTSTRAP_MODE')},
          open(os.environ['FIXTURE_CHILD_PROOF'],'w'))
PY
''')
        proof = self.root / 'child-proof'
        args = ['--only', "23-ai-workforce-blueprint,32-command-center-setup", '--note', "Nicole's $literal $(must-not-run)"]
        body = ('set -- ' + ' '.join(shlex.quote(value) for value in args) + '\nsource '
                + shlex.quote(str(REPO / 'platform/vps/bootstrap.sh')))
        result = self.run_shell(body, FIXTURE_DOCKER_NAMES='openclaw-client',
                                OPENCLAW_BOOTSTRAP_MODE='update', ONBOARDING_VERSION='v25.0.7',
                                FIXTURE_DOCKER_RUN='1', FIXTURE_CURL_SCRIPT=str(child), FIXTURE_CHILD_PROOF=str(proof))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        called = json.loads((self.root / 'docker-calls').read_text())['argv']
        self.assertIn('https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/v25.0.7/update-skills.sh', called)
        self.assertEqual(json.loads(proof.read_text()), {'args':args, 'mode':'update'})

    def test_installer_and_updater_choose_selected_root_over_downloads(self):
        legacy = self.home / 'Downloads/openclaw-master-files/23-old-skill'
        legacy.mkdir(parents=True)
        own = self.root / "Nicole's selected root"
        for script in ('install.sh', 'update-skills.sh'):
            with self.subTest(script=script):
                source = (REPO / script).read_text()
                start = source.index('discover_skills_dir() {')
                function = source[start:source.index('\n}', start)+2]
                result = self.run_shell('oc_set_platform_paths\n' + function + '\ndiscover_skills_dir',
                                        OPENCLAW_ROOT=str(own))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(), str(own / 'skills'))
        self.assertTrue(legacy.exists())

    def test_real_platform_delivery_blocks_use_selected_skill_root(self):
        source_bundle = self.root / 'bundle'
        (source_bundle / 'platform').mkdir(parents=True)
        (source_bundle / 'platform/common.sh').write_text('fixture-common\n')
        own = self.root / "Nicole's selected root"
        for script in ('install.sh', 'update-skills.sh'):
            with self.subTest(script=script):
                source = (REPO / script).read_text()
                start = source.index('# Platform helpers are runtime dependencies')
                end = source.index('# >>> CANONICAL-CONFIG-DELIVERY-BEGIN', start)
                body = ('oc_set_platform_paths\nSKILLS_DIR="$OC_SKILLS_DIR"\nONBOARDING_DIR='
                        + shlex.quote(str(source_bundle)) + '\n' + source[start:end])
                result = self.run_shell(body, OPENCLAW_ROOT=str(own))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((own / 'platform/common.sh').read_text(), 'fixture-common\n')
                self.assertFalse((self.home / '.openclaw/platform').exists())

    def test_updater_scripts_delivery_uses_pinned_root(self):
        source = (REPO / 'update-skills.sh').read_text()
        start = source.index('  _OC_SCRIPTS_DEST=')
        end = source.index('  # rc 0 = delivered+verified;', start)
        own = self.root / 'selected root'
        result = self.run_shell('oc_set_platform_paths\n' + source[start:end] + '\nprintf "%s" "$_OC_SCRIPTS_DEST"',
                                OPENCLAW_ROOT=str(own))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, str(own / 'scripts'))

    def test_updater_app_pin_never_falls_through_to_other_client(self):
        source = (REPO / 'update-skills.sh').read_text()
        start = source.index('  cc_resolve_existing_dir() {')
        function = source[start:source.index('\n  }', start)+4]
        own = self.root / "Nicole's command center"
        body = ('_CC_DIR_CANONICAL="$HOME/projects/command-center"\n'
                'cc_is_valid_checkout() { [ "$1" = "$_CC_DIR_CANONICAL" ] || '
                '{ [ "${FIXTURE_PIN_VALID:-}" = 1 ] && [ "$1" = "$CC_APP_DIR" ]; }; }\n'
                + function + '\ncc_resolve_existing_dir')
        result = self.run_shell(body, CC_APP_DIR=str(own), FIXTURE_PIN_VALID='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(own))
        missing = self.run_shell(body, CC_APP_DIR=str(own), FIXTURE_PIN_VALID='0')
        self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(missing.stdout, '')

    def test_installer_passes_selected_app_dir_to_real_bootstrap_entry(self):
        source = (REPO / 'install.sh').read_text()
        start = source.index('bootstrap_command_center_shell() {')
        function = source[start:source.index('\n}', start)+2]
        skills = self.root / 'skills'
        child = skills / '32-command-center-setup/scripts/run-full-install.sh'
        child.parent.mkdir(parents=True)
        child.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$FIXTURE_ARGS"\n')
        child.chmod(0o755)
        self.stub('pm2', 'echo "[]"')
        self.stub('lsof', 'exit 1')
        own = self.root / "Nicole's command center"
        proof = self.root / 'install-args'
        body = ('note() { :; }; warn() { :; }; success() { :; }\n' + function
                + '\nbootstrap_command_center_shell')
        result = self.run_shell(body, CC_APP_DIR=str(own), SKILLS_DIR=str(skills),
                                OPENCLAW_COMPANY_SLUG='nicole', OPENCLAW_COMPANY_NAME="Nicole's Company",
                                LOG_FILE=str(self.root / 'log'), FIXTURE_ARGS=str(proof))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(proof.read_text().splitlines(),
                         ['nicole', "Nicole's Company", 'pending+nicole@zerohumanworkforce.com', '--app-dir', str(own)])

    def test_ambiguous_or_stopped_container_never_creates_host_client(self):
        for values in ({'FIXTURE_DOCKER_NAMES': 'openclaw-a\nopenclaw-b'},
                       {'FIXTURE_DOCKER_ALL': 'openclaw-stopped'},
                       {'OPENCLAW_CONTAINER_NAME': 'client', 'FIXTURE_DOCKER_NAMES': 'client-other'}):
            with self.subTest(values=values):
                result = self.run_shell('source ' + shlex.quote(str(REPO / 'platform/vps/bootstrap.sh')), **values)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.root / 'docker-calls').exists())
                self.assertFalse((self.home / '.openclaw').exists())

    def test_mac_bootstrap_preserves_pins_and_uses_no_docker(self):
        own = self.root / 'client root'
        result = self.run_shell('source ' + shlex.quote(str(REPO / 'platform/mac/bootstrap.sh')) + '\n' + self.fields(),
                                FIXTURE_OS='Darwin', OPENCLAW_ROOT=str(own), OPENCLAW_WORKSPACE_ROOT=str(own / 'custom'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(own) + '|' + str(own / 'custom'), result.stdout)
        self.assertFalse((self.root / 'docker-calls').exists())


if __name__ == '__main__':
    unittest.main()
