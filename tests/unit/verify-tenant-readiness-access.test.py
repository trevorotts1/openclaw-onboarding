#!/usr/bin/env python3
"""verify-tenant-readiness: a public host behind Cloudflare Access (302 to its login) is probed on loopback instead.

The Skill 32 installer stamped boxes done-degraded (tenantReadiness) because the authenticated readiness
probe called the PUBLIC hostname, Access answered 302 to the login page, and the probe failed with
"authenticated readiness probe failed: HTTPError". The probe must reach the Command Center on
127.0.0.1 with the public Host header and the bearer token, and it must never get weaker: a really
missing registry / persona context still fails, naming the receiver's exact missing fields.
"""
import http.client, http.server, importlib.util, io, json, os, sys, tempfile, threading, unittest, urllib.error, urllib.request
from pathlib import Path
from unittest import mock
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('verify_tenant_readiness', ROOT / '32-command-center-setup/scripts/verify-tenant-readiness.py')
V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)

HOST, PORT, TOKEN = 'client.invalid', '4123', 'fixture-only-token'
ACCESS_LOGIN = 'https://team.cloudflareaccess.com/cdn-cgi/access/login/client.invalid?kid=abc'
ENV = {'MC_TENANT_ID': 'tenant', 'MC_COMPANY_ID': 'fixture', 'MC_INSTALLATION_ID': 'install',
       'MC_TENANT_PUBLIC_URL': 'https://' + HOST, 'MC_API_TOKEN': TOKEN, 'DASHBOARD_PORT': PORT}
READY = {'ready': True, 'missing': [], 'tenantId': 'tenant', 'companyId': 'fixture', 'installationId': 'install',
         'host': HOST, 'kind': 'self', 'protocol': 'interview.v1'}


class Resp(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): return False


def http_error(url, code, headers=None, body=b''):
    message = http.client.HTTPMessage()
    for k, v in (headers or {}).items(): message[k] = v
    return urllib.error.HTTPError(url, code, 'x', message, io.BytesIO(body))


class Box:
    """Stands in for the network: the public https origin and the on-box loopback Command Center."""
    def __init__(self, public='access', local=None):
        self.public, self.local, self.calls = public, local if local is not None else (200, READY), []
    def open(self, opener, request, data=None, timeout=None):
        url = request.full_url
        self.calls.append((url, request.get_header('Host'), request.get_header('Authorization')))
        if url.startswith('https://'):
            if self.public == 'access': raise http_error(url, 302, {'Location': ACCESS_LOGIN})
            if self.public == 'other-redirect': raise http_error(url, 302, {'Location': 'https://login.example.invalid/'})
            if self.public == 'down': raise urllib.error.URLError('unreachable')
            if self.public == 'ready': return Resp(json.dumps(READY).encode())
        if url == 'http://127.0.0.1:%s/api/auth/tenant-ready' % PORT:
            assert request.get_header('Host') == HOST and request.get_header('Authorization') == 'Bearer ' + TOKEN
            code, body = self.local
            if code == 'refused': raise urllib.error.URLError(ConnectionRefusedError())
            if code != 200: raise http_error(url, code, body=json.dumps(body).encode())
            return Resp(json.dumps(body).encode())
        raise AssertionError('unexpected request ' + url)


def verify(box, env=ENV):
    with mock.patch.object(urllib.request.OpenerDirector, 'open', lambda self, request, data=None, timeout=None: box.open(self, request, data, timeout)):
        return V.verify({'companyId': 'fixture'}, env)


class AccessFrontedHost(unittest.TestCase):
    def test_302_to_access_with_a_ready_loopback_passes(self):
        box = Box(); receipt = verify(box)
        self.assertEqual((receipt['ready'], receipt['missing']), (True, []), receipt)
        self.assertEqual([c[0] for c in box.calls], ['https://%s/api/auth/tenant-ready' % HOST, 'http://127.0.0.1:%s/api/auth/tenant-ready' % PORT])
        self.assertEqual(receipt['probe'], 'loopback')
    def test_loopback_receipt_identity_is_still_exact(self):
        for key in ('tenantId', 'companyId', 'installationId', 'host', 'protocol'):
            receipt = verify(Box(local=(200, dict(READY, **{key: 'foreign'}))))
            self.assertFalse(receipt['ready'], key); self.assertIn(key + ' mismatch', receipt['missing'])
    def test_really_missing_context_still_fails_with_the_exact_missing_fields(self):
        body = dict(READY, ready=False, missing=['persona_company_context_or_catalog', 'company_record'])
        receipt = verify(Box(local=(503, body)))
        self.assertFalse(receipt['ready'])
        self.assertTrue(any('persona_company_context_or_catalog' in m and 'company_record' in m for m in receipt['missing']), receipt)
    def test_unregistered_host_still_fails_with_the_receivers_reason(self):
        receipt = verify(Box(local=(403, {'ready': False, 'error': 'tenant_registration_or_identity_unverified'})))
        self.assertFalse(receipt['ready'])
        self.assertTrue(any('tenant_registration_or_identity_unverified' in m for m in receipt['missing']), receipt)
    def test_a_ready_looking_body_on_an_error_status_never_passes(self):
        self.assertFalse(verify(Box(local=(503, READY)))['ready'])
    def test_loopback_down_fails(self):
        receipt = verify(Box(local=('refused', None)))
        self.assertFalse(receipt['ready']); self.assertTrue(any('authenticated readiness probe failed' in m for m in receipt['missing']), receipt)


class InstallerEntryPoint(unittest.TestCase):
    """The command run-full-install.sh runs: `verify-tenant-readiness.py <state> --port <port>`."""
    def run_main(self, box):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / '.workforce-build-state.json'
            state.write_text(json.dumps({'companyId': 'fixture', 'buildId': 'b1'}))
            env = {k: v for k, v in ENV.items() if k != 'DASHBOARD_PORT'}
            with mock.patch.dict(os.environ, env), mock.patch.object(sys, 'argv', ['verify-tenant-readiness.py', str(state), '--port', PORT]), \
                 mock.patch.object(urllib.request.OpenerDirector, 'open', lambda self, request, data=None, timeout=None: box.open(self, request, data, timeout)), \
                 mock.patch('builtins.print'):
                rc = V.main()
            return rc, json.loads(state.read_text())
    def test_access_fronted_box_is_stamped_ready_instead_of_degraded(self):
        rc, state = self.run_main(Box())
        self.assertEqual((rc, state['commandCenterTenantReady']), (0, True))
        self.assertEqual(state['commandCenterTenantVerification']['probe'], 'loopback')
    def test_missing_registry_is_still_stamped_not_ready(self):
        rc, state = self.run_main(Box(local=(403, {'ready': False, 'error': 'tenant_registration_or_identity_unverified'})))
        self.assertEqual((rc, state['commandCenterTenantReady']), (1, False))


class NoFallbackElsewhere(unittest.TestCase):
    def test_public_success_is_unchanged_and_never_touches_loopback(self):
        box = Box(public='ready'); receipt = verify(box)
        self.assertTrue(receipt['ready']); self.assertEqual(len(box.calls), 1)
    def test_only_a_cloudflare_access_redirect_triggers_the_loopback_probe(self):
        for public in ('other-redirect', 'down'):
            box = Box(public=public); receipt = verify(box)
            self.assertFalse(receipt['ready'], public); self.assertEqual(len(box.calls), 1, public)


class RealSockets(unittest.TestCase):
    """_probe over a real local HTTP server: redirects classified, never followed, Host header honoured."""
    @classmethod
    def setUpClass(cls):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def reply(self, code, body=b'', headers=()):
                self.send_response(code)
                for k, v in headers: self.send_header(k, v)
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_GET(self):
                if self.path == '/access': self.reply(302, headers=[('Location', ACCESS_LOGIN)])
                elif self.path == '/other': self.reply(302, headers=[('Location', 'https://login.example.invalid/')])
                elif self.path == '/ready':
                    ok = self.headers.get('Host') == HOST and self.headers.get('Authorization') == 'Bearer ' + TOKEN
                    self.reply(200 if ok else 403, json.dumps(READY if ok else {'ready': False}).encode())
                elif self.path == '/missing': self.reply(503, json.dumps({'ready': False, 'missing': ['company_record']}).encode())
                elif self.path == '/html': self.reply(403, b'<html>blocked</html>')
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = 'http://127.0.0.1:%d' % cls.server.server_address[1]
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close()
    def test_probe_classifies_without_following(self):
        self.assertEqual(V._probe(self.base + '/ready', {'Authorization': 'Bearer ' + TOKEN, 'Host': HOST}), READY)
        with self.assertRaises(V.AccessRedirect): V._probe(self.base + '/access', {})
        with self.assertRaises(urllib.error.HTTPError) as other: V._probe(self.base + '/other', {})
        self.assertEqual(other.exception.code, 302)                          # a non-Access redirect stays a plain failure
        with self.assertRaises(urllib.error.HTTPError): V._probe(self.base + '/html', {})
        with self.assertRaises(V.ReceiverRefused) as refused: V._probe(self.base + '/missing', {})
        self.assertEqual(refused.exception.names, ['company_record'])


if __name__ == '__main__':
    unittest.main()
