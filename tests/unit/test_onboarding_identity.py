#!/usr/bin/env python3
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/onboarding-identity.py'
spec = importlib.util.spec_from_file_location('intake', SCRIPT)
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'

    def collect(self, **kwargs):
        return intake.ensure(self.root, self.workspace, **kwargs)

    def test_missing_answers_do_not_create_company_or_state(self):
        value = self.collect()
        self.assertEqual(value['status'], 'needs-input')
        self.assertEqual(len(value['questions']), 2)
        self.assertFalse((self.root / 'onboarding-identity.json').exists())
        self.assertFalse(self.workspace.exists())

    def test_explicit_names_saved_separately_and_resume_is_unchanged(self):
        first = self.collect(owner='  Fixture Owner  ', company='Fixture Business')
        self.assertEqual(first['ownerName'], 'Fixture Owner')
        self.assertEqual(first['companySlug'], 'fixture-business')
        path = self.root / 'onboarding-identity.json'
        original = path.read_bytes()
        self.assertEqual(self.collect()['companyName'], 'Fixture Business')
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_missing_company_does_not_use_owner(self):
        value = self.collect(owner='Fixture Owner')
        self.assertEqual(value['questions'], [intake.QUESTIONS['companyName']])

    def test_conflicts_leave_identity_untouched(self):
        self.collect(owner='Fixture Owner', company='Fixture Business')
        path = self.root / 'onboarding-identity.json'; before = path.read_bytes()
        for fields in ({'owner': 'Other'}, {'company': 'Other'}, {'slug': 'other'}):
            with self.assertRaises(ValueError): self.collect(**fields)
            self.assertEqual(path.read_bytes(), before)

    def test_established_client_never_restarts_or_changes_ids(self):
        self.workspace.mkdir()
        path = self.workspace / '.workforce-build-state.json'
        state = dict(companyId='uuid-fixture', companySlug='legacy-slug', companyName='Saved Business', answers={'1':'saved'}, interviewComplete=True)
        path.write_text(json.dumps(state)); before = path.read_bytes()
        value = self.collect()
        self.assertEqual(value['status'], 'existing')
        self.assertEqual(value['companyId'], 'uuid-fixture')
        self.assertEqual(value['companySlug'], 'legacy-slug')
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.root / 'onboarding-identity.json').exists())

    def test_same_slug_with_other_company_id_is_refused(self):
        self.collect(owner='Fixture Owner', company='Fixture Business')
        self.workspace.mkdir()
        statepath = self.workspace/'.workforce-build-state.json'
        state = dict(companyId='company-a', companySlug='fixture-business', companyName='Fixture Business', tenantId='tenant-a', installationId='install-a')
        statepath.write_text(json.dumps(state))
        self.collect()
        profile = self.root/'onboarding-identity.json'; before = profile.read_bytes()
        for key in ('companyId', 'tenantId', 'installationId'):
            statepath.write_text(json.dumps(dict(state, **{key:'foreign'})))
            with self.assertRaises(ValueError): self.collect()
            self.assertEqual(profile.read_bytes(), before)

    def test_vps_reexec_forwards_both_explicit_answers(self):
        # Exercise the real bootstrap instead of extracting one historical shell
        # spelling: topology selection now builds a safely quoted argv array.
        result = subprocess.run(
            [sys.executable, str(ROOT/'tests/unit/test_portable_bootstrap.py'),
             'PortableBootstrapTests.test_docker_host_reexec_preserves_identity_and_path_pins'],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_foreign_workspace_and_corrupt_state_fail_closed(self):
        self.collect(owner='One', company='Business')
        with self.assertRaises(ValueError): intake.ensure(self.root, self.root/'foreign')
        self.workspace.mkdir()
        (self.workspace/'.workforce-build-state.json').write_text('{')
        with self.assertRaises(ValueError): self.collect()

    def test_supplied_slug_is_preserved_and_unicode_names_work(self):
        value = self.collect(owner='Éva', company='会社', slug='existing-choice')
        self.assertEqual(value['companySlug'], 'existing-choice')
        self.assertEqual(value['companyName'], '会社')

    def test_long_business_name_gets_stable_dns_label(self):
        value = self.collect(owner='Owner', company='A'*100)
        self.assertLessEqual(len(value['companySlug']),63)
        self.assertEqual(self.collect()['companySlug'], value['companySlug'])

    def test_noninteractive_cli_exits_pending_with_questions(self):
        env = {k:v for k,v in os.environ.items() if k not in ('OPENCLAW_OWNER_NAME','OPENCLAW_COMPANY_NAME')}
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 8)
        self.assertEqual(len(json.loads(result.stdout)['questions']), 2)

    def test_real_installer_gate_exports_the_saved_business(self):
        import shlex
        source = (ROOT/'install.sh').read_text()
        start = source.index('collect_onboarding_identity() {')
        end = source.index('\n}\ncollect_onboarding_identity', start)+2
        function = source[start:end]
        driver = 'set -eu\n' + function + '\n' + '\n'.join([
            '_SCRIPT_DIR='+shlex.quote(str(ROOT)),
            'OC_CONFIG='+shlex.quote(str(self.root)),
            'OC_WORKSPACE_DEFAULT='+shlex.quote(str(self.workspace)),
            'export OPENCLAW_OWNER_NAME="Fixture Owner" OPENCLAW_COMPANY_NAME="Fixture Business"',
            'collect_onboarding_identity',
            'test "$OPENCLAW_OWNER_NAME" = "Fixture Owner"',
            'test "$OPENCLAW_COMPANY_NAME" = "Fixture Business"',
            'test "$OPENCLAW_COMPANY_SLUG" = "fixture-business"'])
        result = subprocess.run(['bash', '-c', driver], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.workspace.exists())

    def test_real_terminal_prompts_for_both_answers(self):
        pid, fd = pty.fork()
        if pid == 0:
            os.environ.pop('OPENCLAW_OWNER_NAME', None); os.environ.pop('OPENCLAW_COMPANY_NAME', None)
            os.execl(sys.executable, sys.executable, str(SCRIPT), '--root', str(self.root), '--interactive')
        output = b''; sent_owner = sent_company = False; deadline = time.monotonic()+10
        try:
            while time.monotonic() < deadline:
                if select.select([fd], [], [], .1)[0]:
                    try: chunk = os.read(fd, 8192)
                    except OSError: break
                    if not chunk: break
                    output += chunk
                    if b'owner of this ZHC?' in output and not sent_owner:
                        os.write(fd, b'Fixture Owner\n'); sent_owner = True
                    if b'name of the company?' in output and not sent_company:
                        os.write(fd, b'Fixture Business\n'); sent_company = True
                done, status = os.waitpid(pid, os.WNOHANG)
                if done: pid = 0; self.assertEqual(os.waitstatus_to_exitcode(status), 0); break
            self.assertTrue(sent_owner and sent_company, output)
            self.assertTrue((self.root/'onboarding-identity.json').exists(), output)
            value = json.loads((self.root/'onboarding-identity.json').read_text())
            self.assertEqual(value['ownerName'], 'Fixture Owner')
            self.assertEqual(value['companyName'], 'Fixture Business')
        finally:
            os.close(fd)
            if pid:
                done, _ = os.waitpid(pid, os.WNOHANG)
                if not done: os.kill(pid, 9); os.waitpid(pid, 0)


if __name__ == '__main__': unittest.main()
