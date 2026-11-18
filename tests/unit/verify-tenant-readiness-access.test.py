#!/usr/bin/env python3
"""verify-tenant-readiness: a public host behind Cloudflare Access (302 to its login) is probed on loopback instead.

The Skill 32 installer stamped boxes done-degraded (tenantReadiness) because the authenticated readiness
probe called the PUBLIC hostname, Access answered 302 to the login page, and the probe failed with
"authenticated readiness probe failed: HTTPError". The probe must reach the Command Center on
127.0.0.1 with the public Host header and the bearer token, and it must never get weaker: a really
missing registry / persona context still fails, naming the receiver's exact missing fields.

Cloudflare also answers the stock Python-urllib User-Agent with its own 403 page before Access runs, so every
request carries an explicit User-Agent, and a 403 that is BOTH non-JSON AND marked by the Cloudflare edge
(cf-ray header or Server: cloudflare) is probed on loopback too. A receiver's own JSON 403 and an unmarked
HTML 403 keep their old meaning. The installer's FINAL call passes --env-file so the probe sees the client's
own identity even when the launch environment was not loaded.
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
        self.public, self.local, self.calls, self.agents = public, local if local is not None else (200, READY), [], []
    def open(self, opener, request, data=None, timeout=None):
        url = request.full_url
        self.calls.append((url, request.get_header('Host'), request.get_header('Authorization')))
        self.agents.append(request.get_header('User-agent'))
        if url.startswith('https://'):
            if self.public == 'access': raise http_error(url, 302, {'Location': ACCESS_LOGIN})
            if self.public == 'edge': raise http_error(url, 403, {'cf-ray': '8f0-IAD', 'Server': 'cloudflare'}, b'<html>Attention Required</html>')
            if self.public == 'edge-server-only': raise http_error(url, 403, {'Server': 'cloudflare'}, b'<html>blocked</html>')
            if self.public == 'edge-json': raise http_error(url, 403, {'cf-ray': '8f0-IAD'}, json.dumps({'ready': False, 'error': 'tenant_registration_or_identity_unverified'}).encode())
            if self.public == 'html-403': raise http_error(url, 403, {'Server': 'nginx'}, b'<html>blocked</html>')
            if self.public == 'edge-503': raise http_error(url, 503, {'cf-ray': '8f0-IAD', 'Server': 'cloudflare'}, b'<html>down</html>')
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


def verify(box, env=ENV, state=None):
    with mock.patch.object(urllib.request.OpenerDirector, 'open', lambda self, request, data=None, timeout=None: box.open(self, request, data, timeout)):
        return V.verify(state or {'companyId': 'fixture'}, env)


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


class CloudflareEdge(unittest.TestCase):
    """Cloudflare's own 403 page (non-JSON body AND a cf-ray header or Server: cloudflare) is probed on loopback."""
    def test_every_request_carries_an_explicit_user_agent(self):
        for public in ('access', 'edge', 'ready'):
            box = Box(public=public); verify(box)
            self.assertTrue(box.agents, public)
            for agent in box.agents:
                self.assertEqual(agent, V.USER_AGENT, public)
                self.assertFalse(agent.startswith('Python-urllib'), public)
    def test_edge_403_with_a_ready_loopback_passes(self):
        for public in ('edge', 'edge-server-only'):
            box = Box(public=public); receipt = verify(box)
            self.assertEqual((receipt['ready'], receipt['missing'], receipt['probe']), (True, [], 'loopback'), public)
            self.assertEqual([c[0] for c in box.calls], ['https://%s/api/auth/tenant-ready' % HOST, 'http://127.0.0.1:%s/api/auth/tenant-ready' % PORT], public)
    def test_edge_403_loopback_identity_is_still_exact(self):
        for key in ('tenantId', 'companyId', 'installationId', 'host', 'protocol'):
            receipt = verify(Box(public='edge', local=(200, dict(READY, **{key: 'foreign'}))))
            self.assertFalse(receipt['ready'], key); self.assertIn(key + ' mismatch', receipt['missing'])
    def test_edge_403_loopback_down_names_the_edge(self):
        receipt = verify(Box(public='edge', local=('refused', None)))
        self.assertFalse(receipt['ready'])
        self.assertTrue(any('blocked by the Cloudflare edge' in m for m in receipt['missing']), receipt)
    def test_receiver_json_403_is_still_a_refusal_even_behind_cloudflare(self):
        box = Box(public='edge-json'); receipt = verify(box)
        self.assertFalse(receipt['ready']); self.assertEqual(len(box.calls), 1)
        self.assertTrue(any('receiver refused readiness (HTTP 403)' in m and 'tenant_registration_or_identity_unverified' in m for m in receipt['missing']), receipt)
    def test_unmarked_html_403_and_edge_503_never_fall_back(self):
        for public in ('html-403', 'edge-503'):
            box = Box(public=public); receipt = verify(box)
            self.assertFalse(receipt['ready'], public); self.assertEqual(len(box.calls), 1, public)
            self.assertEqual(receipt['missing'], ['authenticated readiness probe failed: HTTPError'], public)


class IdentityFromState(unittest.TestCase):
    STATE = {'companyId': 'fixture', 'tenantId': 'tenant', 'installationId': 'install'}
    def test_tenant_and_installation_come_from_state_when_env_lacks_them(self):
        env = {k: v for k, v in ENV.items() if k not in ('MC_TENANT_ID', 'MC_INSTALLATION_ID', 'MC_COMPANY_ID')}
        receipt = verify(Box(), env, dict(self.STATE))
        self.assertEqual((receipt['ready'], receipt['missing']), (True, []), receipt)
    def test_state_wins_over_env(self):
        env = dict(ENV, MC_TENANT_ID='stale-tenant', MC_INSTALLATION_ID='stale-install')
        receipt = verify(Box(), env, dict(self.STATE))
        self.assertEqual((receipt['tenantId'], receipt['installationId'], receipt['ready']), ('tenant', 'install', True), receipt)
    def test_env_still_used_when_state_lacks_them(self):
        self.assertTrue(verify(Box(), ENV, {'companyId': 'fixture'})['ready'])
    def test_absent_everywhere_still_fails(self):
        env = {k: v for k, v in ENV.items() if k not in ('MC_TENANT_ID', 'MC_INSTALLATION_ID')}
        receipt = verify(Box(), env, {'companyId': 'fixture'})
        self.assertFalse(receipt['ready']); self.assertEqual(receipt['missing'], ['tenantId', 'installationId'])


class InstallerEntryPoint(unittest.TestCase):
    """The command run-full-install.sh runs: `verify-tenant-readiness.py <state> --port <port> --env-file <.env.local>`."""
    def run_main(self, box, env_file=None, ambient=None, state=None):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / '.workforce-build-state.json'
            path.write_text(json.dumps(state or {'companyId': 'fixture', 'buildId': 'b1'}))
            argv = ['verify-tenant-readiness.py', str(path), '--port', PORT]
            if env_file is not None:
                (Path(td) / '.env.local').write_text(env_file); argv += ['--env-file', str(Path(td) / '.env.local')]
            env = ambient if ambient is not None else {k: v for k, v in ENV.items() if k != 'DASHBOARD_PORT'}
            out = io.StringIO()
            with mock.patch.dict(os.environ, env), mock.patch.object(sys, 'argv', argv), \
                 mock.patch.object(urllib.request.OpenerDirector, 'open', lambda self, request, data=None, timeout=None: box.open(self, request, data, timeout)), \
                 mock.patch('sys.stdout', out):
                for k in [k for k in os.environ if k.startswith('MC_') or k in ('DASHBOARD_PORT', 'CC_PORT')]:
                    if k not in env: del os.environ[k]
                rc = V.main()
            return rc, json.loads(path.read_text()), out.getvalue()
    def test_access_fronted_box_is_stamped_ready_instead_of_degraded(self):
        rc, state, _ = self.run_main(Box())
        self.assertEqual((rc, state['commandCenterTenantReady']), (0, True))
        self.assertEqual(state['commandCenterTenantVerification']['probe'], 'loopback')
    def test_missing_registry_is_still_stamped_not_ready(self):
        rc, state, _ = self.run_main(Box(local=(403, {'ready': False, 'error': 'tenant_registration_or_identity_unverified'})))
        self.assertEqual((rc, state['commandCenterTenantReady']), (1, False))
    def test_edge_blocked_box_is_stamped_ready(self):
        rc, state, _ = self.run_main(Box(public='edge'))
        self.assertEqual((rc, state['commandCenterTenantReady'], state['commandCenterTenantVerification']['probe']), (0, True, 'loopback'))
    FILE = ''.join('%s=%s\n' % (k, v) for k, v in ENV.items() if k != 'DASHBOARD_PORT')
    def test_env_file_alone_supplies_the_identity(self):
        # No launch environment loaded: nothing ambient, everything from the client's own .env.local.
        rc, state, _ = self.run_main(Box(), env_file=self.FILE, ambient={})
        self.assertEqual((rc, state['commandCenterTenantReady']), (0, True), state)
    def test_env_file_never_moves_the_on_box_port(self):
        rc, state, _ = self.run_main(Box(), env_file=self.FILE + 'DASHBOARD_PORT=1\n', ambient={})
        self.assertEqual((rc, state['commandCenterTenantReady']), (0, True), state)   # --port wins over the file
    def test_unreadable_env_file_prints_json_not_ready_without_a_traceback(self):
        rc, state, out = self.run_main(Box(), env_file="COMPANY_NAME=Bob's $5 Shop\n")
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out), {'ready': False, 'missing': ['service environment unreadable: ValueError']})
        self.assertNotIn('commandCenterTenantReady', state)
    def test_env_file_conflict_is_still_refused(self):
        rc, _, out = self.run_main(Box(), env_file='MC_API_TOKEN=other-token\n')
        self.assertEqual((rc, json.loads(out)['missing']), (1, ['service/installer environment conflict: MC_API_TOKEN']))
    def test_final_installer_call_passes_the_client_env_file(self):
        source = (ROOT / '32-command-center-setup/scripts/run-full-install.sh').read_text()
        final = source[source.index('FINAL_STATUS="done"'):]
        call = next(line for line in final.splitlines() if 'verify-tenant-readiness.py' in line)
        self.assertIn('--port "$DASHBOARD_PORT"', call)
        self.assertIn('--env-file "$DASHBOARD_DIR/.env.local"', call)


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
                elif self.path == '/cf-html': self.reply(403, b'<html>Attention Required</html>', headers=[('cf-ray', '8f0-IAD')])
                elif self.path == '/cf-json': self.reply(403, json.dumps({'ready': False, 'missing': ['company_record']}).encode(), headers=[('cf-ray', '8f0-IAD')])
                elif self.path == '/cf-json-list': self.reply(403, b'[]', headers=[('cf-ray', '8f0-IAD')])
                elif self.path == '/agent': self.reply(200, json.dumps({'agent': self.headers.get('User-Agent')}).encode())
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
    def test_edge_page_is_classified_and_receiver_json_keeps_priority(self):
        with self.assertRaises(V.EdgeBlocked): V._probe(self.base + '/cf-html', {})
        with self.assertRaises(V.ReceiverRefused) as refused: V._probe(self.base + '/cf-json', {})
        self.assertEqual(refused.exception.names, ['company_record'])
        with self.assertRaises(urllib.error.HTTPError) as other: V._probe(self.base + '/cf-json-list', {})
        self.assertEqual(other.exception.code, 403)                          # a JSON body is never an edge page
    def test_the_wire_carries_the_explicit_user_agent(self):
        self.assertEqual(V._probe(self.base + '/agent', {}), {'agent': V.USER_AGENT})
        self.assertEqual(V._bounded_json(self.base + '/agent'), {'agent': V.USER_AGENT})


if __name__ == '__main__':
    unittest.main()
