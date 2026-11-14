import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { acceptUpload } from '../src/uploads.js';

// S75-083: the studio's own 7-day copy of a finished video had NO production
// writer, so nothing ever created a `clients/<id>/video/` key. The uploader
// half must mint that key, and the bridge validator must accept it — and only
// it — while everything sent in still lands under `intake/`.

const client = 'c-' + 'a'.repeat(32);
const env = { R2_ACCOUNT_ID: 'c'.repeat(32), R2_ACCESS_KEY_ID: 'fake-key', R2_SECRET_ACCESS_KEY: 'fake-secret' };
const store = { kvPut: async () => {} };
const mp4 = Buffer.concat([Buffer.from([0x00, 0x00, 0x00, 0x18]), Buffer.from('ftypisom'), Buffer.alloc(8)]);
const body = {
  channel: 'video',
  filename: 'final.mp4',
  size_bytes: mp4.length,
  content_type: 'video/mp4',
  header_bytes: [...mp4.subarray(0, 16)],
};

test('an R2 fallback upload is written under clients/<id>/video/', async () => {
  const out = await acceptUpload({
    store, env, clientId: client, body: { ...body, upload_kind: 'r2_fallback' },
    nowUtc: '2026-01-01T00:00:00.000Z',
  });
  assert.equal(out.ok, true, JSON.stringify(out));
  assert.equal(out.status, 201);
  assert.match(out.object_path, new RegExp(`^clients/${client}/video/u_[0-9a-f]{24}\\.mp4$`));
  assert.equal(new URL(out.upload.url).pathname, `/zhw-drama-studio/${out.object_path}`);
});

test('everything else still lands under intake/', async () => {
  const out = await acceptUpload({ store, env, clientId: client, body, nowUtc: '2026-01-01T00:00:00.000Z' });
  assert.equal(out.ok, true, JSON.stringify(out));
  assert.match(out.object_path, new RegExp(`^clients/${client}/intake/u_[0-9a-f]{24}\\.mp4$`));
});

test('an unknown upload_kind is refused and names no other folder', async () => {
  for (const upload_kind of ['other', 'video', '../video', 'toString']) {
    const out = await acceptUpload({ store, env, clientId: client, body: { ...body, upload_kind }, nowUtc: '2026-01-01T00:00:00.000Z' });
    assert.equal(out.ok, false, upload_kind);
    assert.equal(out.code, 'AF-DS-UP-REJECT-FIELD', upload_kind);
  }
});

test('the bridge has a production writer and its validator accepts only the matching folder', () => {
  const bridgeDir = fileURLToPath(new URL('../../../shared-bridge/', import.meta.url));
  const code = `
import sys, json, pathlib, tempfile
sys.path.insert(0, sys.argv[1])
import studio_bridge as b
from studio_claim import LedgerError

MP4 = b'\\x00\\x00\\x00\\x18ftypisom' + b'\\x00' * 8
CLIENT = 'c-' + 'a' * 32
UP = 'u_' + 'b' * 24

def post_for(segment):
    def post(method, url, *, key, body):
        path = 'clients/' + CLIENT + '/' + segment + '/' + UP + '.mp4'
        return 201, {'ok': True, 'upload_id': UP, 'object_path': path,
                     'upload': {'url': 'https://' + 'c' * 32 + '.r2.cloudflarestorage.com/zhw-drama-studio/' + path + '?sig',
                                'content_type': body['content_type']}}
    return post

out = {}
with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d) / 'final.mp4'
    p.write_bytes(MP4)
    seen = {}
    def spy(method, url, *, key, body):
        seen['upload_kind'] = body.get('upload_kind')
        return post_for('video')(method, url, key=key, body=body)
    out['writer_result'] = b.upload_fallback_video(p, env={'DS_KEY': 'k'}, post=spy, put=lambda *a: 200)
    out['writer_kind'] = seen.get('upload_kind')
    try:
        b.upload_fallback_video(p, env={'DS_KEY': 'k'}, post=post_for('intake'), put=lambda *a: 200)
        out['intake_answer'] = 'ACCEPTED'
    except LedgerError as exc:
        out['intake_answer'] = exc.code
    try:
        b.upload_file(p, env={'DS_KEY': 'k'}, upload_kind='other', post=post_for('video'), put=lambda *a: 200)
        out['bad_kind'] = 'ACCEPTED'
    except LedgerError as exc:
        out['bad_kind'] = exc.code
print(json.dumps(out))
`;
  const proc = spawnSync('python3', ['-c', code, bridgeDir], { encoding: 'utf8' });
  assert.equal(proc.status, 0, proc.stderr);
  const out = JSON.parse(proc.stdout);
  assert.deepEqual(out.writer_result, { upload_id: 'u_' + 'b'.repeat(24), object_path: `clients/${client}/video/u_${'b'.repeat(24)}.mp4` });
  assert.equal(out.writer_kind, 'r2_fallback');
  assert.equal(out.intake_answer, 'UPLOAD_RESPONSE_INVALID');
  assert.equal(out.bad_kind, 'UNSUPPORTED_KIND');
});
