#!/usr/bin/env python3
"""Hardening plan ITEM 08 — real paired fresh-install invitation acceptance.

The existing paired invitation check (interview-launch-contract.yml) scanned
source strings and MOCKED a successful receipt, so neither the PRES-046
missing-manifest refusal nor registration-dependent issuance was ever exercised.

This suite exercises the real thing, end to end, with fixture identities only:

  1. BUILD GUARD   — a fresh checkout is really built (`npm run build`), the
                     immutable manifest is written through CC's OWN writer
                     (`build-inventory.sh --manifest`, never hand-written), and
                     `--verify` proves it. Removing the manifest makes the real
                     `scripts/cc-start.sh` refuse with exit 78 + the PRES-046
                     receipt (the missing-manifest failure, reproduced).
  2. MISSING TRIPLE — against a real running app whose fixture registry entry
                     lacks issuer/audience/subjects: authenticated readiness is
                     503/ready:false with access_identity_unregistered in
                     `missing` and capabilities.enrollment=false (items 07+13),
                     while the actual invitation route refuses 409
                     access_identity_unregistered — the registration-dependent
                     issuance failure, reproduced.
  3. REAL MINT     — a second real run with the full Access triple: the REAL
                     onboarding validator (`shared-utils/interview_invitation.py`
                     resolve_public_origin + issue_invitation, real curl) reaches
                     the real readiness route and the real invitation route
                     through a local TLS edge and receives a real minted receipt
                     whose identity matches. Wrong identity and tampered output
                     then fail in the real validator. The edge fixture records
                     the service headers (Bearer + CF-Access-Client-Id/Secret)
                     proving the service-header path end to end.

Fixture Cloudflare edge and test identities only: no client key, no fleet
write, no client send (issuance mints; it never delivers). The ticket is NEVER
printed, logged or written to the proof. Zero skips: any skip is a failure of
the acceptance itself.

Run:
  CC_REPO=/path/to/blackceo-command-center python3 tests/unit/interview-paired-acceptance.test.py
Optional:
  INTERVIEW_ACCEPTANCE_PROOF=/tmp/proof.json   # paired revisions + verdicts
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import socketserver
import sqlite3
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
CC = Path(os.environ.get('CC_REPO', '')).resolve() if os.environ.get('CC_REPO') else None
HOST = 'fixture-acceptance.test'
TENANT = 'tenant-fixture-0001'
COMPANY = 'company-fixture-0001'
INSTALLATION = 'installation-fixture-0001'
API_TOKEN = 'fixture-bearer-token-no-real-secret'
CF_ID = 'fixture-access-client-id'
CF_SECRET = 'fixture-access-client-secret'
RECIPIENT = 'fixture-owner-chat-0001'
ISSUER = 'https://fixture-access.example.test'
AUDIENCE = 'fixture-access-audience'
SUBJECTS = ['owner@fixture.example.test']

PROOF = {'schema': 'interview-paired-acceptance/1', 'checks': {}}
_BUILT = {'done': False}


def record(name, ok, detail=''):
    PROOF['checks'][name] = {'ok': bool(ok), 'detail': detail}
    if not ok:
        raise AssertionError(f'{name}: {detail}')


def _run(cmd, cwd, env, timeout=900):
    return subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout)


def ensure_built():
    """Build the paired checkout once and seal it with CC's own manifest writer."""
    if _BUILT['done']:
        return
    if CC is None or not CC.is_dir():
        raise AssertionError('CC_REPO must name a real paired blackceo-command-center checkout (a missing checkout fails the acceptance; it is never a skip)')
    env = {**os.environ, 'HOME': os.environ.get('HOME', '/root')}
    build = _run(['npm', 'run', 'build'], CC, env)
    if build.returncode != 0:
        raise AssertionError('paired CC production build failed:\n' + (build.stdout + build.stderr)[-6000:])
    build_id = (CC / '.next' / 'BUILD_ID').read_text().strip()
    manifest = _run(['bash', 'scripts/lib/build-inventory.sh', '--manifest', str(CC), str(CC / '.next'), build_id, str(int(time.time()))], CC, env, timeout=120)
    if manifest.returncode != 0:
        raise AssertionError('build-inventory.sh --manifest failed:\n' + (manifest.stdout + manifest.stderr)[-3000:])
    verify = _run(['bash', 'scripts/lib/build-inventory.sh', '--verify', str(CC)], CC, env, timeout=120)
    if verify.returncode != 0 or '"verdict":"VERIFIED"' not in verify.stdout:
        raise AssertionError('sealed manifest does not verify: ' + verify.stdout[-1000:])
    _BUILT['done'] = True
    _BUILT['manifest'] = CC / '.next' / 'build-inventory.json'


def git_sha(cwd):
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(cwd), capture_output=True, text=True, timeout=30).stdout.strip() or 'unknown'
    except OSError:
        return 'unknown'


class Fixture:
    """One fresh install: own HOME, DB, workspace, runtime tree, registry."""

    def __init__(self, app_port, edge_port, with_triple):
        self.app_port = app_port
        self.edge_port = edge_port
        self.with_triple = with_triple
        self.tmp = tempfile.TemporaryDirectory(prefix='interview-acceptance-')
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.workspace = self.home / '.openclaw' / 'workspace'
        self.oc_root = self.home / '.openclaw'
        self.db = self.root / 'data' / 'mission-control.db'
        self.log = self.root / 'cc-server.log'
        self.registry = self._registry()
        self.proc = None
        self.edge = None
        self.edge_thread = None
        self.ca = None

    def _registry(self):
        entry = {'kind': 'self', 'tenantId': TENANT, 'companyId': COMPANY, 'installationId': INSTALLATION}
        if self.with_triple:
            entry.update({'issuer': ISSUER, 'audience': AUDIENCE, 'subjects': list(SUBJECTS)})
        return {HOST: dict(entry), 'localhost': dict(entry), '127.0.0.1': dict(entry)}

    def prepare(self):
        (self.home).mkdir(parents=True, exist_ok=True)
        (self.workspace / 'company-discovery').mkdir(parents=True, exist_ok=True)
        (self.oc_root / 'agents' / 'main' / 'agent').mkdir(parents=True, exist_ok=True)
        (self.root / 'data').mkdir(parents=True, exist_ok=True)
        (self.root / 'company').mkdir(parents=True, exist_ok=True)
        # Identity-stamped build state: interview NOT complete, flags present.
        (self.workspace / '.workforce-build-state.json').write_text(json.dumps({
            'interviewComplete': False,
            'tenantId': TENANT, 'companyId': COMPANY, 'installationId': INSTALLATION,
            'buildId': 'fixture-build-state',
        }, indent=2))
        # OpenClaw runtime the readiness prerequisites demand.
        (self.oc_root / 'openclaw.json').write_text(json.dumps({
            'gateway': {'auth': {'mode': 'token'}},
            'agents': {
                'list': [{'id': 'main', 'default': True, 'model': 'fixture-model',
                          'agentDir': str(self.oc_root / 'agents' / 'main' / 'agent'),
                          'workspace': str(self.workspace)}],
                'defaults': {'model': 'fixture-model', 'workspace': str(self.workspace),
                             'systemAgent': {'agentId': 'main'}},
            },
        }))
        # Persona company context + canonical catalog.
        company_cfg = {'companyId': COMPANY, 'companySlug': 'fixture-acceptance'}
        (self.root / 'company' / 'company-config.json').write_text(json.dumps(company_cfg))
        (self.root / 'company' / 'persona-catalog.json').write_text(json.dumps(
            {'personas': {'fixture-persona': {'id': 'fixture-persona'}}}))
        # Self-signed edge certificate (fixture Cloudflare edge stand-in).
        self.ca = self.root / 'edge-cert.pem'
        key = self.root / 'edge-key.pem'
        cert = subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '3',
            '-keyout', str(key), '-out', str(self.ca), '-subj', f'/CN={HOST}',
            '-addext', f'subjectAltName=DNS:{HOST}',
            '-addext', 'basicConstraints=critical,CA:TRUE',
            '-addext', 'keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign',
        ], capture_output=True, text=True, timeout=60)
        if cert.returncode != 0:
            raise AssertionError('openssl self-signed fixture certificate failed: ' + cert.stderr[-800:])
        # Real migrations on a fresh database, then the fixture company + workspace rows.
        env = self.env()
        push = _run(['npm', 'run', 'db:push'], CC, env, timeout=600)
        if push.returncode != 0:
            raise AssertionError('real migrations (npm run db:push) failed:\n' + (push.stdout + push.stderr)[-5000:])
        db = sqlite3.connect(self.db)
        try:
            cols = {r[1] for r in db.execute('PRAGMA table_info(workspaces)')}
            if 'company_id' in cols:
                db.execute('INSERT OR IGNORE INTO workspaces (id, name, slug, company_id) VALUES (?,?,?,?)',
                           ('ws-fixture', 'Fixture Workspace', 'fixture-workspace', COMPANY))
            else:
                db.execute('INSERT OR IGNORE INTO workspaces (id, name, slug) VALUES (?,?,?)',
                           ('ws-fixture', 'Fixture Workspace', 'fixture-workspace'))
            db.execute('INSERT OR IGNORE INTO companies (id, name, slug) VALUES (?,?,?)',
                       (COMPANY, 'Fixture Acceptance Company', 'fixture-acceptance'))
            db.commit()
        finally:
            db.close()
        self.write_state()

    def env(self):
        env = {
            **os.environ,
            'HOME': str(self.home),
            'OPENCLAW_ROOT': str(self.oc_root),
            'OPENCLAW_WORKSPACE_ROOT': str(self.workspace),
            'OPENCLAW_SKILL23_SCRIPTS': str(ROOT / '23-ai-workforce-blueprint' / 'scripts'),
            'OPENCLAW_GATEWAY_TOKEN': 'fixture-gateway-token',
            'OPENCLAW_GATEWAY_URL': 'ws://127.0.0.1:18789',
            'DATABASE_PATH': str(self.db),
            'MC_API_TOKEN': API_TOKEN,
            'MC_TENANT_ID': TENANT,
            'MC_COMPANY_ID': COMPANY,
            'MC_INSTALLATION_ID': INSTALLATION,
            'MC_TENANT_PUBLIC_URL': f'https://{HOST}',
            'MC_TENANT_REGISTRY_JSON': json.dumps(self.registry, separators=(',', ':')),
            'MC_PERSONA_COMPANY_CONTEXTS_JSON': json.dumps({COMPANY: {
                'companyRoot': str(self.root / 'company'),
                'companyConfig': str(self.root / 'company' / 'company-config.json'),
                'companySlug': 'fixture-acceptance',
                'personaCatalog': str(self.root / 'company' / 'persona-catalog.json'),
            }}),
            'CC_PORT': str(self.app_port),
            'CC_PORT_OVERRIDE_ACK': '1',
        }
        for key in ('CF_ACCESS_CLIENT_ID', 'CF_ACCESS_CLIENT_SECRET', 'MC_TENANT_PUBLIC_URL_OVERRIDE'):
            env.pop(key, None)
        return env

    def write_state(self):
        """Validator env: same fixture identity + service pair + pinned DB."""
        self.validator_env = {**self.env(), 'CF_ACCESS_CLIENT_ID': CF_ID, 'CF_ACCESS_CLIENT_SECRET': CF_SECRET}
        self.state = {
            'interviewComplete': False,
            'tenantId': TENANT, 'companyId': COMPANY, 'installationId': INSTALLATION,
            'buildId': 'fixture-build-state',
        }

    def start_server(self):
        self.proc = subprocess.Popen(['bash', 'scripts/cc-start.sh', '--port', str(self.app_port)],
                                     cwd=str(CC), env=self.env(),
                                     stdout=open(self.log, 'ab'), stderr=subprocess.STDOUT)
        deadline = time.time() + 180
        last = ''
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise AssertionError(f'cc-start exited early rc={self.proc.returncode}: {self.log.read_text()[-4000:]}')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{self.app_port}/api/health', timeout=3) as resp:
                    if resp.status == 200:
                        return
            except Exception as exc:  # noqa: BLE001 - boot is allowed to refuse briefly
                last = str(exc)
            time.sleep(1)
        raise AssertionError('real server never became healthy: ' + last + ' log: ' + self.log.read_text()[-4000:])

    # ── Fixture TLS edge: an HTTP CONNECT proxy that terminates TLS in-tunnel,
    #    forwards the raw request to the app, and records the service headers.
    #    curl never resolves the fixture hostname (it asks the proxy to connect),
    #    so no /etc/hosts or external DNS is involved anywhere.
    def start_edge(self):
        self.requests = []
        lock = threading.Lock()
        outer = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                f = self.request.makefile('rb', buffering=0)
                head = b''
                while b'\r\n\r\n' not in head and len(head) < 65536:
                    chunk = f.read(1)
                    if not chunk:
                        return
                    head += chunk
                if not head.startswith(b'CONNECT '):
                    self.request.sendall(b'HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n')
                    return
                self.request.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.load_cert_chain(str(outer.ca), str(outer.root / 'edge-key.pem'))
                try:
                    tls = ctx.wrap_socket(self.request, server_side=True)
                except (ssl.SSLError, OSError):
                    return
                app = socket.create_connection(('127.0.0.1', outer.app_port), timeout=30)
                scan = bytearray()

                def tls_to_app():
                    try:
                        while True:
                            data = tls.recv(65536)
                            if not data:
                                break
                            if len(scan) < 65536:
                                scan.extend(data)
                                if len(scan) >= 65536 or b'\r\n\r\n' in scan:
                                    text = bytes(scan).split(b'\r\n\r\n', 1)[0].decode('latin-1', 'replace')
                                    with lock:
                                        outer.requests.append(text)
                                    scan.clear()
                            app.sendall(data)
                    except OSError:
                        pass
                    finally:
                        try:
                            app.shutdown(socket.SHUT_WR)
                        except OSError:
                            pass

                def app_to_tls():
                    try:
                        while True:
                            data = app.recv(65536)
                            if not data:
                                break
                            tls.sendall(data)
                    except OSError:
                        pass
                    finally:
                        try:
                            tls.shutdown(socket.SHUT_WR)
                        except OSError:
                            pass

                t1 = threading.Thread(target=tls_to_app, daemon=True)
                t2 = threading.Thread(target=app_to_tls, daemon=True)
                t1.start(); t2.start(); t1.join(); t2.join()
                for s in (tls, app):
                    try:
                        s.close()
                    except OSError:
                        pass

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('127.0.0.1', self.edge_port))
        srv.listen(16)

        def serve():
            while True:
                try:
                    conn, _ = srv.accept()
                except OSError:
                    break
                threading.Thread(target=lambda c=conn: Handler(c, None, None), daemon=True).start()

        self._srv = srv
        self.edge_thread = threading.Thread(target=serve, daemon=True)
        self.edge_thread.start()

    @property
    def origin(self):
        return f'https://{HOST}'

    @property
    def proxy_env(self):
        return {'https_proxy': f'http://127.0.0.1:{self.edge_port}', 'CURL_CA_BUNDLE': str(self.ca), 'no_proxy': '', 'NO_PROXY': ''}

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill(); self.proc.wait(timeout=10)
        if getattr(self, '_srv', None):
            try:
                self._srv.close()
            except OSError:
                pass
        self.tmp.cleanup()


def load_validator():
    spec = importlib.util.spec_from_file_location('paired_invitation_validator', ROOT / 'shared-utils' / 'interview_invitation.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildGuard(unittest.TestCase):
    """Fresh build + immutable manifest + the PRES-046 missing-manifest refusal."""

    @classmethod
    def setUpClass(cls):
        ensure_built()

    def test_01_fresh_build_manifest_verifies(self):
        ensure_built()
        out = _run(['bash', 'scripts/lib/build-inventory.sh', '--verify', str(CC)], CC, {**os.environ}, timeout=120)
        record('fresh_build_manifest_verifies', out.returncode == 0 and '"verdict":"VERIFIED"' in out.stdout,
               f'rc={out.returncode} {out.stdout[:300]}')

    def test_02_missing_manifest_makes_real_cc_start_refuse_78(self):
        ensure_built()
        manifest = CC / '.next' / 'build-inventory.json'
        saved = manifest.read_bytes()
        receipt = CC / '.cc-state' / 'cc-start-refused.json'
        receipt.unlink(missing_ok=True)
        fixture = Fixture(4477, 0, with_triple=False)
        fixture.prepare()
        env = fixture.env()
        fixture.tmp.cleanup()  # only needed the env; state files are not consulted pre-boot
        try:
            manifest.unlink()
            proc = subprocess.run(['bash', 'scripts/cc-start.sh', '--port', '4477'], cwd=str(CC), env=env,
                                  capture_output=True, text=True, timeout=120)
            refused = receipt.exists() and proc.returncode == 78
            schema_ok = False
            if receipt.exists():
                body = json.loads(receipt.read_text())
                schema_ok = body.get('schema') == 'cc-start-refusal/1' and body.get('exit') == 78
            record('missing_manifest_refused_exit_78', refused,
                   f'rc={proc.returncode} receipt_present={receipt.exists()}')
            record('missing_manifest_refusal_receipt_schema', schema_ok, 'receipt schema/exit fields wrong')
        finally:
            manifest.write_bytes(saved)
            receipt.unlink(missing_ok=True)
            verify = _run(['bash', 'scripts/lib/build-inventory.sh', '--verify', str(CC)], CC, {**os.environ}, timeout=120)
            record('manifest_restored_and_verified', verify.returncode == 0, verify.stdout[:300])


class MissingAccessTriple(unittest.TestCase):
    """readiness 503/ready:false (items 07+13) + actual invitation route 409 access_identity_unregistered."""

    @classmethod
    def setUpClass(cls):
        ensure_built()
        cls.fixture = Fixture(4477, 3129, with_triple=False)
        cls.fixture.prepare()
        cls.fixture.start_edge()
        cls.fixture.start_server()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.stop()

    def _call(self, path, method='GET', body=None):
        f = self.fixture
        before = len(f.requests)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f.origin + path, data=data, method=method,
                                     headers={'Authorization': 'Bearer ' + API_TOKEN,
                                              'Content-Type': 'application/json',
                                              'CF-Access-Client-Id': CF_ID,
                                              'CF-Access-Client-Secret': CF_SECRET})
        # The fixture edge certificate is self-signed for this fixture only:
        # verify it explicitly against OUR CA rather than the system store.
        https_handler = urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(f.ca)))
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({'https': f.proxy_env['https_proxy'], 'http': f.proxy_env['https_proxy']}),
            https_handler)
        try:
            with opener.open(req, timeout=30) as out:
                return out.status, json.loads(out.read().decode()), f.requests[before:]
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode()), f.requests[before:]

    def test_01_readiness_is_not_ready_and_issuance_is_refused(self):
        # Post items 07 + 13 contract (CC batch PR #541 folds #537): the
        # incomplete Access triple is a machine-readable NOT-ready verdict on
        # readiness itself — 503, ready=false, the allowlisted reason in
        # `missing`, and the capability keys telling the truth about issuance —
        # while the actual invitation route keeps the same precise 409.
        status, receipt, _ = self._call('/api/auth/interview-ready')
        caps = receipt.get('capabilities') or {}
        record('missing_triple_readiness_503',
               status == 503 and receipt.get('ready') is False
               and 'access_identity_unregistered' in (receipt.get('missing') or []),
               f'status={status} ready={receipt.get("ready")} missing={receipt.get("missing")}')
        record('missing_triple_capabilities_tell_the_truth',
               caps.get('enrollment') is False and caps.get('invitationIssuable') is False
               and caps.get('signingSecretConfigured') is True,
               f'enrollment={caps.get("enrollment")} invitationIssuable={caps.get("invitationIssuable")} signingSecretConfigured={caps.get("signingSecretConfigured")}')
        mstatus, mbody, _ = self._call('/api/auth/interview-invitation', method='POST',
                                       body={'recipientHash': hashlib.sha256(RECIPIENT.encode()).hexdigest()})
        record('missing_triple_invitation_409_access_identity_unregistered',
               mstatus == 409 and mbody.get('error') == 'access_identity_unregistered',
               f'status={mstatus} error={mbody.get("error")}')
        record('missing_triple_never_minted', 'url' not in mbody and 'enroll=' not in json.dumps(mbody),
               'a ticket was minted without a registered Access identity')


class RealPairedMint(unittest.TestCase):
    """Full Access triple: the real validator mints a real invitation for real."""

    @classmethod
    def setUpClass(cls):
        ensure_built()
        cls.validator = load_validator()
        cls.fixture = Fixture(4478, 3130, with_triple=True)
        cls.fixture.prepare()
        cls.fixture.start_edge()
        cls.fixture.start_server()
        cls.mint_url = None
        os.environ.update(cls.fixture.proxy_env)

    @classmethod
    def tearDownClass(cls):
        for key in ('https_proxy', 'CURL_CA_BUNDLE', 'no_proxy', 'NO_PROXY'):
            os.environ.pop(key, None)
        cls.mint_url = None
        cls.fixture.stop()

    def test_01_real_readiness_and_real_mint_through_the_validator(self):
        f = self.fixture
        resolved = self.validator.resolve_public_origin(f.state, f.validator_env)
        record('real_readiness_passes_onboarding_validator', resolved['host'] == HOST and resolved['receipt'].get('ready') is True,
               'validate_receipt accepted the real readiness receipt')
        url = self.validator.issue_invitation(resolved, f.validator_env, RECIPIENT)
        self.mint_url = url
        record('real_mint_succeeds', isinstance(url, str) and url.startswith(f.origin + '/interview?enroll='),
               'real invitation route did not return a bound enrollment URL')
        record('mint_identity_matches_installation', resolved['companyId'] == COMPANY and resolved['tenantId'] == TENANT
               and resolved['installationId'] == INSTALLATION, 'validator-resolved identity drifted')

    def test_02_service_headers_reach_the_edge_path(self):
        f = self.fixture
        headers_ok = False
        for text in self.fixture.requests:
            if '/api/auth/interview-ready' in text or '/api/auth/interview-invitation' in text:
                lowered = text.lower()
                headers_ok = all(token in lowered for token in
                                 ('authorization: bearer', 'cf-access-client-id:', 'cf-access-client-secret:'))
                if headers_ok:
                    break
        record('service_headers_carried_end_to_end', headers_ok,
               'the edge never saw Bearer + CF-Access-Client-Id/-Secret on a real readiness/invitation request')
        # An incomplete service pair is refused BEFORE any network call.
        incomplete = dict(f.validator_env)
        incomplete.pop('CF_ACCESS_CLIENT_SECRET', None)
        try:
            self.validator.curl_auth_config(incomplete)
        except self.validator.Pending:
            record('incomplete_service_pair_refused', True, '')
        else:
            record('incomplete_service_pair_refused', False, 'an incomplete CF Access pair was accepted')

    def test_03_wrong_identity_fails_the_real_validator(self):
        f = self.fixture
        wrong = {**f.state, 'installationId': 'installation-foreign-0002'}
        env = {**f.validator_env, 'MC_INSTALLATION_ID': 'installation-foreign-0002'}
        try:
            self.validator.resolve_public_origin(wrong, env)
        except self.validator.Pending:
            record('wrong_identity_fails_validator', True, '')
        else:
            record('wrong_identity_fails_validator', False, 'a foreign installation identity passed the validator')

    def test_04_tampered_receipt_fails_the_real_validator(self):
        f = self.fixture
        resolved = self.validator.resolve_public_origin(f.state, f.validator_env)
        receipt = dict(resolved['receipt'])
        receipt['installationId'] = 'installation-foreign-0002'
        try:
            self.validator.validate_receipt(receipt, {'tenantId': TENANT, 'companyId': COMPANY, 'installationId': INSTALLATION}, HOST)
        except self.validator.Pending:
            record('tampered_readiness_receipt_fails', True, '')
        else:
            record('tampered_readiness_receipt_fails', False, 'a tampered receipt passed validate_receipt')

    def test_05_proof_records_paired_revisions_and_never_the_ticket(self):
        PROOF['pairedRevisions'] = {
            'openclawOnboarding': git_sha(ROOT),
            'blackceoCommandCenter': git_sha(CC) if CC else 'unknown',
            'pairedRef': os.environ.get('PAIRED_CC_REF', ''),
        }
        PROOF['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        PROOF['ticketPrinted'] = False
        PROOF['clientSend'] = False
        blob = json.dumps(PROOF, indent=2)
        record('proof_carries_every_check', all(v.get('ok') for v in PROOF['checks'].values()),
               'one or more acceptance checks failed: ' + ', '.join(k for k, v in PROOF['checks'].items() if not v.get('ok')))
        record('proof_never_contains_the_ticket', 'enroll=' not in blob and (self.mint_url is None or self.mint_url.split('enroll=')[0] not in blob),
               'the proof artifact leaked a ticket')
        out = os.environ.get('INTERVIEW_ACCEPTANCE_PROOF')
        if out:
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_text(blob + '\n')
        print('paired acceptance proof: ' + json.dumps({'checks': {k: v['ok'] for k, v in PROOF['checks'].items()},
                                                        'pairedRevisions': PROOF.get('pairedRevisions', {})}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
