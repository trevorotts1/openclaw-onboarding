"""Direct-upload behavior with fake transports; no network calls."""
import base64
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import studio_bridge as bridge
from studio_claim import LedgerError

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5ioAAAAASUVORK5CYII=')
CLIENT = 'c-' + 'a' * 32
UPLOAD = 'u_' + 'b' * 24
OBJECT = 'clients/' + CLIENT + '/intake/' + UPLOAD + '.png'
URL = 'https://' + 'c' * 32 + '.r2.cloudflarestorage.com/zhw-drama-studio/' + OBJECT + '?signed=private-sentinel'

class UploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = pathlib.Path(self.tmp.name) / 'photo.png'
        self.file.write_bytes(PNG)

    def post(self, method, url, *, key, body):
        self.assertEqual(method, 'POST')
        self.assertEqual(url, bridge.STUDIO_BASE_URL + '/api/studio/uploads')
        self.assertEqual(key, 'client-key-sentinel')
        self.assertEqual(body['header_bytes'], list(PNG[:16]))
        return 201, {'ok': True, 'upload_id': UPLOAD, 'object_path': OBJECT,
                     'upload': {'url': URL, 'content_type': 'image/png'}}

    def test_upload_streams_real_bytes_and_returns_identifiers(self):
        def put(url, fh, content_type, size):
            self.assertEqual(url, URL)
            self.assertEqual(content_type, 'image/png')
            self.assertEqual(size, len(PNG))
            self.assertEqual(fh.read(), PNG)
            return 200
        result = bridge.upload_file(self.file, env={'DS_KEY': 'client-key-sentinel'}, post=self.post, put=put)
        self.assertEqual(result, {'upload_id': UPLOAD, 'object_path': OBJECT})
        self.assertNotIn('private-sentinel', json.dumps(result))

    def test_channel_limits_match_service(self):
        for ext, channel, magic, cap in [('png', 'image', PNG, 25), ('mp3', 'audio', b'ID3\x00', 25), ('mp4', 'video', b'\x00\x00\x00\x18ftypisom', 200)]:
            p = pathlib.Path(self.tmp.name) / ('large.' + ext)
            with p.open('wb') as fh:
                fh.write(magic)
                fh.truncate(cap * 1024 * 1024)
            self.assertEqual(bridge.upload_request(p, channel)['size_bytes'], cap * 1024 * 1024)
            with p.open('ab') as fh: fh.write(b'x')
            with self.assertRaises(LedgerError) as caught: bridge.upload_request(p, channel)
            self.assertEqual(caught.exception.code, 'TOO_BIG')

    def test_renamed_program_is_refused(self):
        self.file.write_bytes(b'MZprogram')
        with self.assertRaises(LedgerError): bridge.photo_request(self.file)

    def test_put_failure_never_prints_signed_url_or_key(self):
        with patch.object(bridge, '_http', self.post), patch.object(bridge, '_put_file', return_value=403), patch.dict('os.environ', {'DS_KEY': 'client-key-sentinel'}):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream): code = bridge.main(['upload', str(self.file)])
        self.assertEqual(code, 2)
        self.assertIn('UPLOAD_PUT_REFUSED', stream.getvalue())
        self.assertNotIn('client-key-sentinel', stream.getvalue())
        self.assertNotIn('private-sentinel', stream.getvalue())
        self.assertNotIn('https:', stream.getvalue())

    def test_wrong_host_does_not_send_file(self):
        def post(*args, **kwargs):
            status, result = self.post(*args, **kwargs)
            result['upload']['url'] = 'https://example.com/file'
            return status, result
        with self.assertRaises(LedgerError) as caught:
            bridge.upload_file(self.file, env={'DS_KEY': 'client-key-sentinel'}, post=post, put=lambda *a: self.fail('bytes sent to wrong host'))
        self.assertEqual(caught.exception.code, 'UPLOAD_RESPONSE_INVALID')

    def test_unknown_put_outcome_is_not_success(self):
        with self.assertRaises(LedgerError) as caught:
            bridge.upload_file(self.file, env={'DS_KEY': 'client-key-sentinel'}, post=self.post, put=lambda *a: 0)
        self.assertEqual(caught.exception.code, 'TRANSPORT_UNKNOWN')

if __name__ == '__main__': unittest.main()
